"""Tests for weather.py — geocoding and forecast helpers."""

import pytest
from unittest.mock import patch, MagicMock

from weather import c_to_f, geocode_city, fetch_forecast


# ── c_to_f ────────────────────────────────────────────────────────────────────

class TestCToF:
    def test_zero_celsius(self):
        assert c_to_f(0) == 32.0

    def test_100_celsius(self):
        assert c_to_f(100) == 212.0

    def test_negative_celsius(self):
        assert c_to_f(-40) == -40.0

    def test_fractional_celsius(self):
        result = c_to_f(25.5)
        assert result == 77.9

    def test_none_returns_none(self):
        assert c_to_f(None) is None


# ── geocode_city ──────────────────────────────────────────────────────────────

class TestGeocodeCity:
    def test_successful_geocode(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"latitude": 51.5, "longitude": -0.12}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", return_value=mock_response) as mock_get:
            lat, lon = geocode_city("London")

        assert lat == 51.5
        assert lon == -0.12
        mock_get.assert_called_once()

    def test_city_not_found_raises_value_error(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": None}
        mock_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", return_value=mock_response):
            with pytest.raises(ValueError, match="City not found"):
                geocode_city("Nonexistentcityxyz")

    def test_empty_results_raises_value_error(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", return_value=mock_response):
            with pytest.raises(ValueError, match="City not found"):
                geocode_city("Nonexistentcityxyz")

    def test_http_error_propagates(self):
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=MagicMock()
        )

        with patch("weather.httpx.get", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                geocode_city("London")


# ── fetch_forecast ────────────────────────────────────────────────────────────

class TestFetchForecast:
    def _mock_forecast_data(self):
        """Return realistic Open-Meteo hourly response for one day."""
        hours = [f"2024-06-15T{h:02d}:00" for h in range(24)]
        temps = [
            15.0, 14.5, 14.0, 13.5, 13.0, 13.5,  # 00-05
            16.0, 18.0, 20.0, 22.0,                 # 06-09 (morning)
            24.0, 25.0, 26.0, 27.0, 27.5, 27.0,     # 10-15
            26.0, 24.0, 22.0, 20.0, 19.0,            # 16-20
            18.0, 17.0, 16.0,                         # 21-23 (night)
        ]
        precip = [0.0] * 24

        return {
            "hourly": {
                "time": hours,
                "temperature_2m": temps,
                "precipitation": precip,
            }
        }

    def test_successful_fetch(self):
        geo_response = MagicMock()
        geo_response.json.return_value = {
            "results": [{"latitude": 51.5, "longitude": -0.12}]
        }
        geo_response.raise_for_status = MagicMock()

        forecast_response = MagicMock()
        forecast_response.json.return_value = self._mock_forecast_data()
        forecast_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", side_effect=[geo_response, forecast_response]):
            result = fetch_forecast("London")

        assert result["city"] == "London"
        assert "date" in result
        assert result["morning_temp"] is not None
        assert result["night_temp"] is not None
        assert result["temp_diff"] is not None
        assert result["is_rainy"] == 0

    def test_rainy_day(self):
        geo_response = MagicMock()
        geo_response.json.return_value = {
            "results": [{"latitude": 51.5, "longitude": -0.12}]
        }
        geo_response.raise_for_status = MagicMock()

        data = self._mock_forecast_data()
        data["hourly"]["precipitation"][10] = 2.5  # rain at 10:00

        forecast_response = MagicMock()
        forecast_response.json.return_value = data
        forecast_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", side_effect=[geo_response, forecast_response]):
            result = fetch_forecast("London")

        assert result["is_rainy"] == 1

    def test_city_name_normalized(self):
        geo_response = MagicMock()
        geo_response.json.return_value = {
            "results": [{"latitude": 40.7, "longitude": -74.0}]
        }
        geo_response.raise_for_status = MagicMock()

        forecast_response = MagicMock()
        forecast_response.json.return_value = self._mock_forecast_data()
        forecast_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", side_effect=[geo_response, forecast_response]):
            result = fetch_forecast("  new york  ")

        assert result["city"] == "New York"

    def test_none_temps_handled(self):
        """When hourly temps are all None for morning/night, result should be None."""
        geo_response = MagicMock()
        geo_response.json.return_value = {
            "results": [{"latitude": 51.5, "longitude": -0.12}]
        }
        geo_response.raise_for_status = MagicMock()

        data = self._mock_forecast_data()
        # Set morning hours (06-09) and night hours (21-23) to None
        for i in range(6, 10):
            data["hourly"]["temperature_2m"][i] = None
        for i in range(21, 24):
            data["hourly"]["temperature_2m"][i] = None

        forecast_response = MagicMock()
        forecast_response.json.return_value = data
        forecast_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", side_effect=[geo_response, forecast_response]):
            result = fetch_forecast("London")

        assert result["morning_temp"] is None
        assert result["night_temp"] is None
        assert result["temp_diff"] is None

    def test_geocode_failure_propagates(self):
        geo_response = MagicMock()
        geo_response.json.return_value = {"results": None}
        geo_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", return_value=geo_response):
            with pytest.raises(ValueError, match="City not found"):
                fetch_forecast("Nonexistentcityxyz")

    def test_all_precipitation_none(self):
        """When all precipitation values are None, is_rainy should be 0."""
        geo_response = MagicMock()
        geo_response.json.return_value = {
            "results": [{"latitude": 51.5, "longitude": -0.12}]
        }
        geo_response.raise_for_status = MagicMock()

        data = self._mock_forecast_data()
        data["hourly"]["precipitation"] = [None] * 24

        forecast_response = MagicMock()
        forecast_response.json.return_value = data
        forecast_response.raise_for_status = MagicMock()

        with patch("weather.httpx.get", side_effect=[geo_response, forecast_response]):
            result = fetch_forecast("London")

        assert result["is_rainy"] == 0
