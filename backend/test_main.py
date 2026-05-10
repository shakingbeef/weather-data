"""Tests for main.py — FastAPI endpoint tests."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from database import get_connection
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def _insert_weather_record(city="London", date="2024-06-15",
                           morning_temp=65.0, night_temp=55.0,
                           temp_diff=10.0, is_rainy=0,
                           fetched_at="2024-06-15T12:00:00"):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO weather_records
               (city, date, morning_temp, night_temp, temp_diff, is_rainy, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (city, date, morning_temp, night_temp, temp_diff, is_rainy, fetched_at),
        )
        conn.commit()


def _insert_city(city):
    with get_connection() as conn:
        conn.execute("INSERT INTO tracked_cities (city) VALUES (?)", (city,))
        conn.commit()


# ── Cities endpoints ──────────────────────────────────────────────────────────

class TestListCities:
    def test_empty_list(self, client):
        resp = client.get("/cities")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_tracked_cities(self, client):
        _insert_city("London")
        _insert_city("Paris")
        resp = client.get("/cities")
        assert resp.status_code == 200
        assert resp.json() == ["London", "Paris"]

    def test_cities_sorted_alphabetically(self, client):
        _insert_city("Zurich")
        _insert_city("Amsterdam")
        _insert_city("Munich")
        resp = client.get("/cities")
        assert resp.json() == ["Amsterdam", "Munich", "Zurich"]


class TestAddCity:
    def test_add_city(self, client):
        resp = client.post("/cities?city=London")
        assert resp.status_code == 200
        assert resp.json()["message"] == "London added"

    def test_city_name_normalized(self, client):
        resp = client.post("/cities?city=  new york  ")
        assert resp.status_code == 200
        assert resp.json()["message"] == "New York added"

    def test_duplicate_city_returns_409(self, client):
        client.post("/cities?city=London")
        resp = client.post("/cities?city=London")
        assert resp.status_code == 409

    def test_missing_city_param(self, client):
        resp = client.post("/cities")
        assert resp.status_code == 422


class TestRemoveCity:
    def test_remove_existing_city(self, client):
        _insert_city("London")
        resp = client.delete("/cities?city=London")
        assert resp.status_code == 200

        # Verify it's gone
        cities = client.get("/cities").json()
        assert "London" not in cities

    def test_remove_nonexistent_city_succeeds(self, client):
        """Note: This silently succeeds even if the city wasn't tracked."""
        resp = client.delete("/cities?city=Nowhere")
        assert resp.status_code == 200

    def test_missing_city_param(self, client):
        resp = client.delete("/cities")
        assert resp.status_code == 422


# ── Fetch weather endpoint ───────────────────────────────────────────────────

class TestFetchWeather:
    def _mock_forecast(self, city):
        return {
            "city": city.strip().title(),
            "date": "2024-06-15",
            "morning_temp": 65.0,
            "night_temp": 55.0,
            "temp_diff": 10.0,
            "is_rainy": 0,
        }

    def test_fetch_and_store(self, client):
        with patch("main.fetch_forecast", side_effect=self._mock_forecast):
            resp = client.post("/weather/fetch?city=London")

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Saved"
        assert data["record"]["city"] == "London"
        assert "fetched_at" in data["record"]

    def test_upsert_on_same_day(self, client):
        """Fetching twice for the same city+date should update, not duplicate."""
        with patch("main.fetch_forecast", side_effect=self._mock_forecast):
            client.post("/weather/fetch?city=London")
            resp = client.post("/weather/fetch?city=London")

        assert resp.status_code == 200

        # Verify only one record exists
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM weather_records WHERE city='London'"
            ).fetchone()["c"]
        assert count == 1

    def test_city_not_found(self, client):
        with patch("main.fetch_forecast", side_effect=ValueError("City not found: Xyz")):
            resp = client.post("/weather/fetch?city=Xyz")

        assert resp.status_code == 404
        assert "City not found" in resp.json()["detail"]

    def test_api_error(self, client):
        with patch("main.fetch_forecast", side_effect=RuntimeError("Connection timeout")):
            resp = client.post("/weather/fetch?city=London")

        assert resp.status_code == 502
        assert "Weather API error" in resp.json()["detail"]


# ── Summary endpoint ─────────────────────────────────────────────────────────

class TestGetSummary:
    def test_summary_with_data(self, client):
        _insert_weather_record("London", "2024-06-15", 65.0, 55.0, 10.0, 0)
        _insert_weather_record("London", "2024-06-16", 70.0, 58.0, 12.0, 1)

        resp = client.get("/weather/summary?city=London")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_days"] == 2
        assert data["rainy_days"] == 1
        assert data["rainy_pct"] == 50.0

    def test_summary_no_data(self, client):
        resp = client.get("/weather/summary?city=Unknown")
        assert resp.status_code == 404

    def test_summary_city_name_normalized(self, client):
        _insert_weather_record("London")
        resp = client.get("/weather/summary?city= london ")
        assert resp.status_code == 200
        assert resp.json()["total_days"] == 1

    def test_summary_all_rainy(self, client):
        _insert_weather_record("London", "2024-06-15", is_rainy=1)
        _insert_weather_record("London", "2024-06-16", is_rainy=1)
        resp = client.get("/weather/summary?city=London")
        data = resp.json()
        assert data["rainy_pct"] == 100.0

    def test_summary_with_none_temps(self, client):
        _insert_weather_record("London", "2024-06-15",
                               morning_temp=None, night_temp=None, temp_diff=None)
        resp = client.get("/weather/summary?city=London")
        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_morning_temp"] is None


# ── Weekly endpoint ───────────────────────────────────────────────────────────

class TestGetWeekly:
    def test_weekly_no_data(self, client):
        resp = client.get("/weather/weekly?city=London")
        assert resp.status_code == 404

    def test_weekly_old_data_excluded(self, client):
        # Insert a record from 30 days ago — should not appear in weekly
        _insert_weather_record("London", "2024-01-01")
        resp = client.get("/weather/weekly?city=London")
        assert resp.status_code == 404

    def test_weekly_with_recent_data(self, client):
        from datetime import date, timedelta

        today = str(date.today())
        yesterday = str(date.today() - timedelta(days=1))

        _insert_weather_record("London", today, 65.0, 55.0, 10.0, 0)
        _insert_weather_record("London", yesterday, 70.0, 58.0, 12.0, 1)

        resp = client.get("/weather/weekly?city=London")
        assert resp.status_code == 200
        data = resp.json()
        assert data["days_recorded"] == 2
        assert data["rainy_days"] == 1


# ── History endpoint ──────────────────────────────────────────────────────────

class TestGetHistory:
    def test_empty_history(self, client):
        resp = client.get("/weather/history?city=London")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_returns_records(self, client):
        _insert_weather_record("London", "2024-06-15")
        _insert_weather_record("London", "2024-06-16")

        resp = client.get("/weather/history?city=London")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 2

    def test_history_ordered_desc(self, client):
        _insert_weather_record("London", "2024-06-14")
        _insert_weather_record("London", "2024-06-16")
        _insert_weather_record("London", "2024-06-15")

        resp = client.get("/weather/history?city=London")
        dates = [r["date"] for r in resp.json()]
        assert dates == ["2024-06-16", "2024-06-15", "2024-06-14"]

    def test_history_scoped_to_city(self, client):
        _insert_weather_record("London", "2024-06-15")
        _insert_weather_record("Paris", "2024-06-15")

        resp = client.get("/weather/history?city=London")
        records = resp.json()
        assert len(records) == 1
        assert records[0]["date"] == "2024-06-15"

    def test_history_city_name_normalized(self, client):
        _insert_weather_record("London")
        resp = client.get("/weather/history?city= london ")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── Static file serving ──────────────────────────────────────────────────────

class TestStaticServing:
    def test_serve_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Daily Weather Summary" in resp.text

    def test_serve_cities_page(self, client):
        resp = client.get("/cities-page")
        assert resp.status_code == 200
        assert "My Cities" in resp.text
