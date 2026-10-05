"""
Pipeline orkestrasyonu — artımlı (incremental) yükleme.

Her sezon için ingest_state'teki son gamecode'dan devam eder; boş yanıt ya da henüz bitmemiş
maç gelince durur. Böylece günlük çalıştırma sadece yeni maçları çeker.

Kullanım:
  python -m elpipe.pipeline                       # varsayılan: E2026 (2026-27 sezonu)
  python -m elpipe.pipeline --season E2025 E2026  # geçmiş sezonu da doldur (backfill)
  python -m elpipe.pipeline --max-games 20        # deneme için sınırla
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .client import EuroLeagueClient
from .load import connect, get_last_gamecode, load_game, set_last_gamecode
from .transform import DataQualityError, is_complete, transform_game

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "euroleague.db"
log = logging.getLogger("elpipe")


@dataclass
class RunResult:
    season_code: str
    loaded: int = 0
    skipped_dq: int = 0
    stopped_at: int | None = None


def run_season(conn: sqlite3.Connection, client: EuroLeagueClient, season_code: str,
               max_games: int | None = None) -> RunResult:
    res = RunResult(season_code)
    gamecode = get_last_gamecode(conn, season_code) + 1
    while max_games is None or res.loaded + res.skipped_dq < max_games:
        header = client.header(season_code, gamecode)
        if header is None:                       # bu gamecode henüz yok -> sezon (şimdilik) bitti
            res.stopped_at = gamecode
            break
        box = client.boxscore(season_code, gamecode)
        if not is_complete(header, box):         # canlı / oynanmamış maç -> sonraki çalıştırmada tekrar dene
            res.stopped_at = gamecode
            break
        try:
            load_game(conn, transform_game(season_code, gamecode, header, box))
            res.loaded += 1
        except DataQualityError as e:            # bozuk veri hattı durdurmasın, logla ve geç
            log.warning("Veri kalitesi hatası, atlandı: %s", e)
            res.skipped_dq += 1
        set_last_gamecode(conn, season_code, gamecode)
        gamecode += 1
    return res


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="EuroLeague veri hattı")
    ap.add_argument("--season", nargs="+", default=["E2026"], help="Sezon kodları (E=EuroLeague, U=EuroCup)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    conn = connect(args.db)
    client = EuroLeagueClient()
    for s in args.season:
        r = run_season(conn, client, s, args.max_games)
        log.info("%s: %d maç yüklendi, %d atlandı (DQ), durduğu gamecode=%s",
                 s, r.loaded, r.skipped_dq, r.stopped_at)
    conn.close()


if __name__ == "__main__":
    main()
