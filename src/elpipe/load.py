"""
LOAD — Temiz satırları SQLite'a (yıldız şema) idempotent şekilde yazar.

  dim_team(team_code, team_name)
  dim_player(player_id, player_name)
  fact_game(game_id PK, season_code, gamecode, round, phase, game_date, stadium, home/away, skorlar)
  fact_team_game(game_id, team_code) PK  -> takım box score
  fact_player_game(game_id, player_id) PK -> oyuncu box score
  ingest_state(season_code PK, last_gamecode, updated_at) -> artımlı (incremental) yükleme

Aynı maç iki kez yüklenirse satırlar çoğalmaz (INSERT OR REPLACE). Her maç tek transaction'da yazılır.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .transform import STAT_COLS, GameBundle

_STATS_DDL = ",\n    ".join(f"{c} INTEGER NOT NULL DEFAULT 0" for c in STAT_COLS)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS dim_team (
    team_code TEXT PRIMARY KEY,
    team_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_player (
    player_id   TEXT PRIMARY KEY,
    player_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_game (
    game_id     TEXT PRIMARY KEY,
    season_code TEXT NOT NULL,
    gamecode    INTEGER NOT NULL,
    round       INTEGER,
    phase       TEXT,
    game_date   TEXT,
    stadium     TEXT,
    home_team   TEXT NOT NULL REFERENCES dim_team(team_code),
    away_team   TEXT NOT NULL REFERENCES dim_team(team_code),
    home_pts    INTEGER NOT NULL,
    away_pts    INTEGER NOT NULL,
    loaded_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_team_game (
    game_id   TEXT NOT NULL REFERENCES fact_game(game_id),
    team_code TEXT NOT NULL REFERENCES dim_team(team_code),
    opp_code  TEXT NOT NULL,
    is_home   INTEGER NOT NULL,
    opp_pts   INTEGER NOT NULL,
    won       INTEGER NOT NULL,
    {_STATS_DDL},
    PRIMARY KEY (game_id, team_code)
);
CREATE TABLE IF NOT EXISTS fact_player_game (
    game_id    TEXT NOT NULL REFERENCES fact_game(game_id),
    player_id  TEXT NOT NULL REFERENCES dim_player(player_id),
    team_code  TEXT NOT NULL REFERENCES dim_team(team_code),
    dorsal     TEXT,
    is_starter INTEGER NOT NULL,
    minutes    REAL NOT NULL,
    plus_minus INTEGER NOT NULL,
    {_STATS_DDL},
    PRIMARY KEY (game_id, player_id)
);
CREATE TABLE IF NOT EXISTS ingest_state (
    season_code   TEXT PRIMARY KEY,
    last_gamecode INTEGER NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_game_season ON fact_game(season_code, round);
CREATE INDEX IF NOT EXISTS ix_player_game_player ON fact_player_game(player_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _upsert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join(f":{c}" for c in row)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", row)


def load_game(conn: sqlite3.Connection, b: GameBundle) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with conn:  # tek transaction: ya hepsi ya hiçbiri
        for t in b.team_games:
            _upsert(conn, "dim_team", {"team_code": t["team_code"], "team_name": t["team_name"]})
        _upsert(conn, "fact_game", {**b.game, "loaded_at": now})
        for t in b.team_games:
            _upsert(conn, "fact_team_game", {k: v for k, v in t.items() if k != "team_name"})
        for p in b.player_games:
            _upsert(conn, "dim_player", {"player_id": p["player_id"], "player_name": p["player_name"]})
            _upsert(conn, "fact_player_game", {k: v for k, v in p.items() if k != "player_name"})


def get_last_gamecode(conn: sqlite3.Connection, season_code: str) -> int:
    row = conn.execute("SELECT last_gamecode FROM ingest_state WHERE season_code = ?", (season_code,)).fetchone()
    return row[0] if row else 0


def set_last_gamecode(conn: sqlite3.Connection, season_code: str, gamecode: int) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO ingest_state VALUES (?, ?, ?) "
            "ON CONFLICT(season_code) DO UPDATE SET last_gamecode = excluded.last_gamecode, updated_at = excluded.updated_at",
            (season_code, gamecode, now),
        )
