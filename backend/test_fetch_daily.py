"""Tests for fetch_daily.py — daily batch fetch script."""

import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from database import get_connection
from fetch_daily import get_cities, fetch_and_store, main


def _insert_city(city):
    with get_connection() as conn:
        conn.execute("INSERT INTO tracked_cities (city) VALUES (?)", (city,))
        conn.commit()


# ── get_cities ────────────────────────────────────────────────────────────────

class TestGetCities:
    def test_returns_cities_from_db(self):
        _insert_city("London")
        _insert_city("Paris")
        cities = get_cities()
        assert cities == ["London", "Paris"]

    def test_falls_back_to_env_var(self):
        with patch.dict(os.environ, {"WEATHER_CITIES": "Tokyo, Berlin, Rome"}):
            cities = get_cities()
        assert cities == ["Tokyo", "Berlin", "Rome"]

    def test_empty_when_no_db_or_env(self):
        with patch.dict(os.environ, {"WEATHER_CITIES": ""}, clear=False):
            cities = get_cities()
        assert cities == []

    def test_env_var_normalizes_names(self):
        with patch.dict(os.environ, {"WEATHER_CITIES": "new york, los angeles"}):
            cities = get_cities()
        assert cities == ["New York", "Los Angeles"]

    def test_env_var_skips_empty_entries(self):
        with patch.dict(os.environ, {"WEATHER_CITIES": "London,,, Paris,"}):
            cities = get_cities()
        assert cities == ["London", "Paris"]

    def test_db_takes_priority_over_env(self):
        _insert_city("London")
        with patch.dict(os.environ, {"WEATHER_CITIES": "Tokyo"}):
            cities = get_cities()
        assert cities == ["London"]


# ── fetch_and_store ───────────────────────────────────────────────────────────

class TestFetchAndStore:
    def _mock_forecast(self, city):
        return {
            "city": city.strip().title(),
            "date": "2024-06-15",
            "morning_temp": 65.0,
            "night_temp": 55.0,
            "temp_diff": 10.0,
            "is_rainy": 0,
        }

    def test_stores_record_in_db(self):
        with patch("fetch_daily.fetch_forecast", side_effect=self._mock_forecast):
            record = fetch_and_store("London")

        assert record["city"] == "London"
        assert "fetched_at" in record

        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM weather_records").fetchall()
        assert len(rows) == 1
        assert rows[0]["city"] == "London"

    def test_upsert_overwrites_same_day(self):
        with patch("fetch_daily.fetch_forecast", side_effect=self._mock_forecast):
            fetch_and_store("London")
            fetch_and_store("London")

        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM weather_records WHERE city='London'"
            ).fetchone()["c"]
        assert count == 1

    def test_forecast_error_propagates(self):
        with patch("fetch_daily.fetch_forecast", side_effect=ValueError("City not found")):
            with pytest.raises(ValueError):
                fetch_and_store("Nonexistent")


# ── main ──────────────────────────────────────────────────────────────────────

class TestMain:
    def test_exits_with_no_cities(self):
        with patch.dict(os.environ, {"WEATHER_CITIES": ""}, clear=False):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_successful_run(self):
        _insert_city("London")

        mock_record = {
            "city": "London",
            "date": "2024-06-15",
            "morning_temp": 65.0,
            "night_temp": 55.0,
            "temp_diff": 10.0,
            "is_rainy": 0,
            "fetched_at": "2024-06-15T12:00:00",
        }

        with patch("fetch_daily.fetch_and_store", return_value=mock_record):
            main()  # should not raise

    def test_exits_on_errors(self):
        _insert_city("London")

        with patch("fetch_daily.fetch_and_store", side_effect=RuntimeError("API down")):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
