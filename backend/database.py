import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "weather.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weather_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                city        TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                morning_temp REAL,
                night_temp  REAL,
                temp_diff   REAL,
                is_rainy    INTEGER NOT NULL DEFAULT 0,
                fetched_at  TEXT    NOT NULL,
                UNIQUE(city, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_cities (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT    NOT NULL UNIQUE
            )
        """)
        conn.commit()
