"""Sahte (ama gerçek API şemasında) Header/Boxscore üreten yardımcılar — testler ağa çıkmaz."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _player(pid, name, team, pts, fg2m, fg3m, ftm, minutes="20:30", **kw):
    return {
        "Player_ID": f"{pid}   ", "Player": name, "Team": team, "Dorsal": str(kw.get("dorsal", 1)),
        "IsStarter": kw.get("starter", 1), "IsPlaying": 0, "Minutes": minutes, "Points": pts,
        "FieldGoalsMade2": fg2m, "FieldGoalsAttempted2": fg2m * 2,
        "FieldGoalsMade3": fg3m, "FieldGoalsAttempted3": fg3m * 3,
        "FreeThrowsMade": ftm, "FreeThrowsAttempted": ftm + 1,
        "OffensiveRebounds": 1, "DefensiveRebounds": 3, "TotalRebounds": 4,
        "Assistances": 2, "Steals": 1, "Turnovers": 2, "BlocksFavour": 0, "BlocksAgainst": 0,
        "FoulsCommited": 2, "FoulsReceived": 3, "Valuation": pts // 2 + 4, "Plusminus": kw.get("pm", 3),
    }


def _team(name, code, players):
    keys = [k for k in players[0] if isinstance(players[0][k], int) and k not in ("IsStarter", "IsPlaying", "Plusminus")]
    totr = {k: sum(p[k] for p in players) for k in keys}
    totr["Minutes"] = "200:00"
    return {"Team": name, "Coach": "X", "PlayersStats": players, "tmr": {}, "totr": totr}


def make_game(gamecode=1, round_=1, a=("IST", "ANADOLU EFES ISTANBUL"), b=("MAD", "REAL MADRID"),
              a_pts=(20, 15), b_pts=(10, 12), live=False, season="E2026"):
    """a_pts / b_pts: her takımın iki oyuncusunun sayıları (2'lik + serbest atış ile üretilir)."""
    def players(code, pts_list, base):
        out = []
        for i, pts in enumerate(pts_list):
            fg3m = 1 if pts >= 3 else 0
            rest = pts - 3 * fg3m
            fg2m, ftm = rest // 2, rest % 2
            out.append(_player(f"P{base + i:06d}", f"PLAYER{i}, {code}", code, pts, fg2m, fg3m, ftm,
                               dorsal=i + 1, starter=int(i == 0)))
        out.append(_player(f"P{base + 9:06d}", f"BENCH, {code}", code, 0, 0, 0, 0, minutes="DNP", starter=0))
        return out

    header = {"Live": live, "pcom": f"{season} ", "Round": str(round_), "Phase": "REGULAR SEASON",
              "Date": "02/10/2026", "Stadium": "Arena", "TeamA": a[1], "TeamB": b[1],
              "CodeTeamA": a[0], "CodeTeamB": b[0], "ScoreA": str(sum(a_pts)), "ScoreB": str(sum(b_pts))}
    box = {"Live": live, "Stats": [_team(a[1], a[0], players(a[0], a_pts, 100 + gamecode * 20)),
                                   _team(b[1], b[0], players(b[0], b_pts, 500 + gamecode * 20))]}
    return header, box


class FakeClient:
    """gamecode -> (header, box) sözlüğüyle çalışan sahte istemci; olmayan gamecode -> None."""

    def __init__(self, games: dict):
        self.games = games
        self.calls = 0

    def header(self, season, gamecode):
        self.calls += 1
        return self.games.get(gamecode, (None, None))[0]

    def boxscore(self, season, gamecode):
        self.calls += 1
        return self.games.get(gamecode, (None, None))[1]


@pytest.fixture
def game():
    return make_game()
