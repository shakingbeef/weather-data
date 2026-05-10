"""Tests for database.py — init and connection helpers."""

import sqlite3
import pytest

from database import init_db, get_connection


class TestInitDb:
    def test_creates_weather_records_table(self):
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='weather_records'"
            )
            assert cursor.fetchone() is not None

    def test_creates_tracked_cities_table(self):
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tracked_cities'"
            )
            assert cursor.fetchone() is not None

    def test_weather_records_schema(self):
        with get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(weather_records)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"id", "city", "date", "morning_temp", "night_temp",
                    "temp_diff", "is_rainy", "fetched_at"}
        assert expected == columns

    def test_tracked_cities_schema(self):
        with get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(tracked_cities)")
            columns = {row["name"] for row in cursor.fetchall()}

        assert {"id", "city"} == columns

    def test_idempotent_init(self):
        """Calling init_db twice should not raise."""
        init_db()
        init_db()

    def test_unique_constraint_on_city_date(self):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO weather_records (city, date, is_rainy, fetched_at) "
                "VALUES ('Test', '2024-01-01', 0, '2024-01-01T00:00:00')"
            )
            conn.commit()

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO weather_records (city, date, is_rainy, fetched_at) "
                    "VALUES ('Test', '2024-01-01', 1, '2024-01-01T01:00:00')"
                )

    def test_unique_constraint_on_tracked_city(self):
        with get_connection() as conn:
            conn.execute("INSERT INTO tracked_cities (city) VALUES ('London')")
            conn.commit()

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO tracked_cities (city) VALUES ('London')")


class TestGetConnection:
    def test_returns_connection(self):
        conn = get_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_row_factory_set(self):
        conn = get_connection()
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_can_query(self):
        with get_connection() as conn:
            result = conn.execute("SELECT 1 AS val").fetchone()
            assert result["val"] == 1
