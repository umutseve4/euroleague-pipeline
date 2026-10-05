"""
Marts view'larını kurar ve statik HTML panoyu üretir -> docs/index.html (GitHub Pages).

Kullanım:  python -m elpipe.report [--season E2026]
"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import DEFAULT_DB

ROOT = Path(__file__).resolve().parents[2]
MARTS = ROOT / "sql" / "marts.sql"
OUT = ROOT / "docs" / "index.html"
TR_TEAMS = ("efes", "fenerbah", "galatasaray", "besiktas", "beşiktaş", "turk telekom", "bursaspor", "tofas", "tofaş")


def build_marts(conn: sqlite3.Connection) -> None:
    conn.executescript(MARTS.read_text(encoding="utf-8"))


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def latest_season(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(season_code) FROM fact_game").fetchone()
    return row[0] if row else None


def collect(conn: sqlite3.Connection, season: str) -> dict:
    build_marts(conn)
    return {
        "season": season,
        "games": conn.execute("SELECT COUNT(*) FROM fact_game WHERE season_code = ?", (season,)).fetchone()[0],
        "players": conn.execute(
            "SELECT COUNT(DISTINCT p.player_id) FROM fact_player_game p JOIN fact_game g USING (game_id) "
            "WHERE g.season_code = ?", (season,)).fetchone()[0],
        "standings": query(conn, """
            SELECT s.*, a.off_rtg, a.def_rtg, a.net_rtg FROM v_standings s
            JOIN v_team_advanced a USING (season_code, team_code)
            WHERE s.season_code = ? ORDER BY w DESC, point_diff DESC""", (season,)),
        "factors": query(conn, """
            SELECT a.*, d.team_name FROM v_team_advanced a JOIN dim_team d USING (team_code)
            WHERE season_code = ? ORDER BY net_rtg DESC""", (season,)),
        "leaders": query(conn, """
            SELECT * FROM v_player_season WHERE season_code = ? AND gp >= ?
            ORDER BY pir DESC LIMIT 25""",
            (season, max(1, conn.execute("SELECT MAX(round) FROM fact_game WHERE season_code = ?",
                                         (season,)).fetchone()[0] // 2 or 1))),
        "recent": query(conn, """
            SELECT g.round, g.game_date, g.home_team, g.home_pts, g.away_pts, g.away_team
            FROM fact_game g WHERE season_code = ? ORDER BY gamecode DESC LIMIT 10""", (season,)),
    }


def render(d: dict) -> str:
    esc = lambda v: "–" if v is None else html.escape(str(v))  # noqa: E731
    is_tr = lambda name: any(k in str(name).lower() for k in TR_TEAMS)  # noqa: E731

    def table(rows: list[dict], cols: list[tuple[str, str]], tr_key: str | None = None) -> str:
        if not rows:
            return "<p class='muted'>Henüz veri yok.</p>"
        head = "".join(f"<th>{esc(label)}</th>" for _, label in cols)
        body = "".join(
            f"<tr class='{'tr' if tr_key and is_tr(r.get(tr_key)) else ''}'><td>{i}</td>"
            + "".join(f"<td>{esc(r.get(k))}</td>" for k, _ in cols) + "</tr>" for i, r in enumerate(rows, 1))
        return f"<table><thead><tr><th>#</th>{head}</tr></thead><tbody>{body}</tbody></table>"

    st = table(d["standings"], [("team_name", "Takım"), ("gp", "O"), ("w", "G"), ("l", "M"), ("win_pct", "G%"),
                                ("point_diff", "Av."), ("off_rtg", "OffRtg"), ("def_rtg", "DefRtg"),
                                ("net_rtg", "Net"), ("last5", "Son 5")], "team_name")
    ff = table(d["factors"], [("team_name", "Takım"), ("pace", "Tempo"), ("efg_pct", "eFG%"), ("tov_pct", "TOV%"),
                              ("oreb_pct", "OREB%"), ("ft_rate", "FT Rate"), ("three_rate", "3P Oranı")], "team_name")
    ld = table(d["leaders"], [("player_name", "Oyuncu"), ("team_code", "Takım"), ("gp", "O"), ("mpg", "Dk"),
                              ("ppg", "Sayı"), ("rpg", "Rib"), ("apg", "Ast"), ("ts_pct", "TS%"), ("pir", "PIR")])
    rc = table(d["recent"], [("round", "Tur"), ("game_date", "Tarih"), ("home_team", "Ev"), ("home_pts", ""),
                             ("away_pts", ""), ("away_team", "Deplasman")])
    chart = json.dumps([{"t": r["team_name"], "o": r["off_rtg"], "d": r["def_rtg"], "tr": is_tr(r["team_name"])}
                        for r in d["factors"]])
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")

    return f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>EuroLeague Analitik · {esc(d['season'])}</title>
<style>
:root{{--bg:#0d0f14;--card:#161a22;--b:#252a35;--t:#e9e9ec;--m:#8a90a2;--o:#ff7a1a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--t);font-family:system-ui,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:1150px;margin:auto;padding:26px 16px 50px}}h1{{margin:0;font-size:28px}}h1 span{{color:var(--o)}}
.sub,.muted{{color:var(--m);font-size:14px}}.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}}
.kpi,.panel{{background:var(--card);border:1px solid var(--b);border-radius:14px;padding:16px}}.kpi b{{font-size:28px;display:block}}
.panel{{margin-bottom:20px;overflow-x:auto}}h2{{font-size:17px;margin:0 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:8px;border-bottom:1px solid var(--b);text-align:right;white-space:nowrap}}
th:nth-child(-n+2),td:nth-child(-n+2){{text-align:left}}td:first-child{{color:var(--m)}}th{{color:var(--m)}}
tr.tr td{{background:#ff7a1a14}}tr.tr td:nth-child(2)::after{{content:" 🇹🇷"}}
canvas{{width:100%;height:420px}}footer{{color:var(--m);font-size:12px;text-align:center;line-height:1.8}}a{{color:var(--o)}}
</style></head><body><div class="wrap">
<h1>🏀 EuroLeague <span>Analitik</span></h1>
<div class="sub">Sezon {esc(d['season'])} · Son güncelleme {now} UTC · otomatik veri hattı (GitHub Actions)</div>
<div class="kpis"><div class="kpi"><b>{d['games']}</b>maç</div><div class="kpi"><b>{len(d['standings'])}</b>takım</div>
<div class="kpi"><b>{d['players']}</b>oyuncu</div><div class="kpi"><b>{d['games'] * 2}</b>takım box score</div></div>
<div class="panel"><h2>📊 Puan durumu</h2>{st}</div>
<div class="panel"><h2>🎯 Hücum vs savunma reytingi (100 pozisyon başına)</h2>
<p class="muted">Sağ alt = iyi hücum + iyi savunma. Turuncu = Türk takımları.</p><canvas id="c"></canvas></div>
<div class="panel"><h2>🧪 Dean Oliver'ın Four Factors'ı</h2>{ff}</div>
<div class="panel"><h2>⭐ PIR liderleri</h2>{ld}</div>
<div class="panel"><h2>🕒 Son maçlar</h2>{rc}</div>
<footer>Veri: live.euroleague.net (Header + Boxscore) · SQLite yıldız şema · SQL view'ları<br>
Kaynak kod: <a href="https://github.com/umutseve4/euroleague-pipeline">github.com/umutseve4/euroleague-pipeline</a></footer>
</div><script>
const D={chart};const c=document.getElementById("c");const x=c.getContext("2d");
function draw(){{const W=c.width=c.clientWidth*devicePixelRatio,H=c.height=c.clientHeight*devicePixelRatio,p=50*devicePixelRatio;
x.clearRect(0,0,W,H);if(!D.length)return;const o=D.map(a=>a.o),d=D.map(a=>a.d);
const [o0,o1]=[Math.min(...o)-2,Math.max(...o)+2],[d0,d1]=[Math.min(...d)-2,Math.max(...d)+2];
const X=v=>p+(v-o0)/(o1-o0)*(W-2*p),Y=v=>p+(v-d0)/(d1-d0)*(H-2*p);
x.strokeStyle="#252a35";x.strokeRect(p,p,W-2*p,H-2*p);x.font=12*devicePixelRatio+"px system-ui";x.fillStyle="#8a90a2";
x.fillText("Hücum reytingi →",W/2-40,H-12);x.save();x.translate(14,H/2+60);x.rotate(-Math.PI/2);x.fillText("← daha iyi savunma",0,0);x.restore();
D.forEach(a=>{{x.fillStyle=a.tr?"#ff7a1a":"#4ecdc4";x.beginPath();x.arc(X(a.o),Y(a.d),6*devicePixelRatio,0,7);x.fill();
x.fillStyle="#e9e9ec";x.fillText(a.t,X(a.o)+9*devicePixelRatio,Y(a.d)+4*devicePixelRatio);}});}}
draw();addEventListener("resize",draw);
</script></body></html>"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--season", default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    conn = sqlite3.connect(args.db)
    season = args.season or latest_season(conn)
    if not season:
        raise SystemExit("Veritabanında maç yok. Önce: python -m elpipe.pipeline")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(collect(conn, season)), encoding="utf-8")
    print(f"Pano yazıldı -> {args.out}")


if __name__ == "__main__":
    main()
