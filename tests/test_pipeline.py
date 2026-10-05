import json

import pytest
from conftest import FakeClient, make_game

from elpipe.client import EuroLeagueClient
from elpipe.load import connect, get_last_gamecode, load_game
from elpipe.pipeline import run_season
from elpipe.report import collect, render
from elpipe.transform import DataQualityError, is_complete, minutes_to_float, parse_date, transform_game


# ---------- transform ----------
def test_minutes_parsing():
    assert minutes_to_float("25:30") == 25.5
    assert minutes_to_float("DNP") == 0.0
    assert minutes_to_float(None) == 0.0


def test_parse_date_formats():
    assert parse_date("02/10/2026") == "2026-10-02"
    assert parse_date("2026-10-02T20:45:00") == "2026-10-02"
    assert parse_date("garbage") is None


def test_transform_shapes(game):
    b = transform_game("E2026", 1, *game)
    assert b.game["game_id"] == "E2026_1"
    assert (b.game["home_pts"], b.game["away_pts"]) == (35, 22)
    assert [t["won"] for t in b.team_games] == [1, 0]
    assert len(b.player_games) == 6
    assert all(p["player_id"] == p["player_id"].strip() for p in b.player_games)
    assert {p["minutes"] for p in b.player_games if p["player_name"].startswith("BENCH")} == {0.0}


def test_incomplete_and_live_games_rejected():
    h, box = make_game(live=True)
    assert not is_complete(h, box)
    assert not is_complete(None, None)
    with pytest.raises(DataQualityError):
        transform_game("E2026", 1, h, box)


def test_dq_score_mismatch_detected(game):
    h, box = game
    h["ScoreA"] = "99"
    with pytest.raises(DataQualityError, match="skor"):
        transform_game("E2026", 1, h, box)


# ---------- load ----------
def test_load_is_idempotent(game):
    conn = connect(":memory:")
    b = transform_game("E2026", 1, *game)
    load_game(conn, b)
    load_game(conn, b)  # ikinci kez -> çoğalma yok
    assert conn.execute("SELECT COUNT(*) FROM fact_game").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM fact_player_game").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM dim_team").fetchone()[0] == 2


# ---------- pipeline ----------
def test_incremental_run_stops_and_resumes():
    games = {1: make_game(1), 2: make_game(2, a=("ULK", "FENERBAHCE BEKO ISTANBUL"), b=("PAN", "PANATHINAIKOS"))}
    conn = connect(":memory:")
    r = run_season(conn, FakeClient(games), "E2026")
    assert (r.loaded, r.stopped_at) == (2, 3)
    assert get_last_gamecode(conn, "E2026") == 2

    games[3] = make_game(3, round_=2, live=True)       # canlı maç -> yüklenmez, gamecode ilerlemez
    r = run_season(conn, FakeClient(games), "E2026")
    assert (r.loaded, r.stopped_at) == (0, 3)

    games[3] = make_game(3, round_=2)                   # maç bitti -> sıradaki çalıştırma alır
    fake = FakeClient(games)
    r = run_season(conn, fake, "E2026")
    assert r.loaded == 1 and get_last_gamecode(conn, "E2026") == 3
    assert fake.calls == 3                              # sadece 3 (header+box) ve 4 (header) çağrıldı


def test_bad_game_skipped_not_fatal():
    bad = make_game(2)
    bad[0]["ScoreA"] = "1"
    conn = connect(":memory:")
    r = run_season(conn, FakeClient({1: make_game(1), 2: bad, 3: make_game(3)}), "E2026")
    assert (r.loaded, r.skipped_dq) == (2, 1)


# ---------- marts + report ----------
def test_marts_and_dashboard():
    games = {1: make_game(1), 2: make_game(2, a=("MAD", "REAL MADRID"), b=("IST", "ANADOLU EFES ISTANBUL"),
                                           a_pts=(30, 20), b_pts=(10, 5))}
    conn = connect(":memory:")
    run_season(conn, FakeClient(games), "E2026")
    d = collect(conn, "E2026")
    st = {r["team_code"]: r for r in d["standings"]}
    assert (st["IST"]["w"], st["IST"]["l"]) == (1, 1)
    assert st["MAD"]["point_diff"] == (50 - 15) + (22 - 35)
    adv = {r["team_code"]: r for r in d["factors"]}
    assert adv["IST"]["net_rtg"] == -adv["MAD"]["net_rtg"] or abs(adv["IST"]["net_rtg"] + adv["MAD"]["net_rtg"]) < 0.2
    assert 0 < adv["IST"]["efg_pct"] < 150
    assert d["leaders"] and d["leaders"][0]["pir"] >= d["leaders"][-1]["pir"]
    page = render(d)
    assert "<table>" in page and "ANADOLU EFES" in page
    json.loads(page.split("const D=")[1].split(";")[0])  # grafik verisi geçerli JSON


def test_client_passes_params():
    seen = []
    c = EuroLeagueClient(fetch=lambda ep, params: seen.append((ep, params)) or {"ok": 1})
    c.header("E2026", 7)
    c.boxscore("U2026", 8)
    assert seen == [("Header", {"gamecode": 7, "seasoncode": "E2026"}),
                    ("Boxscore", {"gamecode": 8, "seasoncode": "U2026"})]
