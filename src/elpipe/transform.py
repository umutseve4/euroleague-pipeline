"""
TRANSFORM — Ham Header + Boxscore JSON'unu temiz, tipli satırlara çevirir.

Çıktı (bir maç için):
  game        : 1 satır  (sezon, gamecode, tur, faz, tarih, ev/deplasman, skor)
  team_games  : 2 satır  (takım box score toplamları + rakip skoru + kazandı mı)
  player_games: N satır  (oyuncu box score; dakika "MM:SS" -> ondalık)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

STAT_MAP = {  # API alanı -> bizim kolon
    "Points": "pts",
    "FieldGoalsMade2": "fg2m", "FieldGoalsAttempted2": "fg2a",
    "FieldGoalsMade3": "fg3m", "FieldGoalsAttempted3": "fg3a",
    "FreeThrowsMade": "ftm", "FreeThrowsAttempted": "fta",
    "OffensiveRebounds": "oreb", "DefensiveRebounds": "dreb", "TotalRebounds": "reb",
    "Assistances": "ast", "Steals": "stl", "Turnovers": "tov",
    "BlocksFavour": "blk", "BlocksAgainst": "blk_against",
    "FoulsCommited": "pf", "FoulsReceived": "fouls_drawn",
    "Valuation": "pir",
}
STAT_COLS = list(STAT_MAP.values())


class DataQualityError(ValueError):
    """Ham veri beklenen kurallara uymuyor (ör. oyuncu sayıları takım toplamını tutmuyor)."""


@dataclass
class GameBundle:
    game: dict[str, Any]
    team_games: list[dict[str, Any]] = field(default_factory=list)
    player_games: list[dict[str, Any]] = field(default_factory=list)


def to_int(v: Any, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def minutes_to_float(v: Any) -> float:
    """'25:13' -> 25.22 · 'DNP' / None / '' -> 0.0"""
    s = str(v or "").strip()
    if ":" not in s:
        return 0.0
    mm, ss = s.split(":", 1)
    return round(to_int(mm) + to_int(ss) / 60, 2)


def parse_date(v: Any) -> str | None:
    """API tarihi farklı biçimlerde gelebilir; ISO (YYYY-MM-DD) döndür, çözemezsen None."""
    s = str(v or "").strip()
    candidates = (s, s[:19], s[:10])
    for fmt in ("%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%b %d, %Y", "%d %B %Y"):
        for c in candidates:
            try:
                return datetime.strptime(c, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def is_complete(header: dict | None, box: dict | None) -> bool:
    """Maç bitmiş ve iki takımın da box score'u dolu mu?"""
    if not header or not box or header.get("Live"):
        return False
    stats = box.get("Stats")
    return isinstance(stats, list) and len(stats) == 2 and all(t.get("PlayersStats") for t in stats)


def _stats(src: dict[str, Any]) -> dict[str, int]:
    return {col: to_int(src.get(api)) for api, col in STAT_MAP.items()}


def transform_game(season_code: str, gamecode: int, header: dict, box: dict) -> GameBundle:
    if not is_complete(header, box):
        raise DataQualityError(f"{season_code}/{gamecode}: maç tamamlanmamış")

    game_id = f"{season_code}_{gamecode}"
    codes = (header["CodeTeamA"].strip(), header["CodeTeamB"].strip())
    names = (str(header.get("TeamA", codes[0])).strip(), str(header.get("TeamB", codes[1])).strip())
    scores = (to_int(header.get("ScoreA")), to_int(header.get("ScoreB")))

    game = {
        "game_id": game_id, "season_code": season_code, "gamecode": gamecode,
        "round": to_int(header.get("Round")), "phase": str(header.get("Phase", "")).strip(),
        "game_date": parse_date(header.get("Date")), "stadium": str(header.get("Stadium", "")).strip() or None,
        "home_team": codes[0], "away_team": codes[1], "home_pts": scores[0], "away_pts": scores[1],
    }
    bundle = GameBundle(game=game)

    for i, team_box in enumerate(box["Stats"]):  # Stats sırası Header'daki A/B sırasıyla aynı
        code, opp = codes[i], codes[1 - i]
        totals = _stats(team_box["totr"])
        players = [p for p in team_box["PlayersStats"] if str(p.get("Player_ID", "")).strip()]

        player_pts = sum(to_int(p.get("Points")) for p in players)
        if player_pts != totals["pts"]:
            raise DataQualityError(f"{game_id} {code}: oyuncu sayıları {player_pts} ≠ takım toplamı {totals['pts']}")
        if totals["pts"] != scores[i]:
            raise DataQualityError(f"{game_id} {code}: box score {totals['pts']} ≠ skor {scores[i]}")

        bundle.team_games.append({
            "game_id": game_id, "team_code": code, "team_name": names[i], "opp_code": opp,
            "is_home": int(i == 0), "opp_pts": scores[1 - i], "won": int(scores[i] > scores[1 - i]),
            **totals,
        })
        for p in players:
            bundle.player_games.append({
                "game_id": game_id, "player_id": str(p["Player_ID"]).strip(),
                "player_name": " ".join(str(p.get("Player", "")).replace(" ,", ",").split()),
                "team_code": code, "dorsal": str(p.get("Dorsal", "")).strip(),
                "is_starter": to_int(p.get("IsStarter")), "minutes": minutes_to_float(p.get("Minutes")),
                "plus_minus": to_int(p.get("Plusminus")),
                **_stats(p),
            })
    return bundle
