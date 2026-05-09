import httpx
from datetime import date
from typing import Optional


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def c_to_f(celsius: Optional[float]) -> Optional[float]:
    if celsius is None:
        return None
    return round(celsius * 9 / 5 + 32, 2)


def geocode_city(city: str) -> tuple[float, float]:
    """Return (latitude, longitude) for a city name."""
    response = httpx.get(GEOCODING_URL, params={"name": city, "count": 1})
    response.raise_for_status()
    results = response.json().get("results")
    if not results:
        raise ValueError(f"City not found: {city}")
    return results[0]["latitude"], results[0]["longitude"]


def fetch_forecast(city: str) -> dict:
    """
    Fetch today's hourly temperature and precipitation for a city.
    Returns a dict with morning_temp, night_temp, temp_diff, is_rainy.
    """
    lat, lon = geocode_city(city)

    response = httpx.get(FORECAST_URL, params={
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation",
        "forecast_days": 1,
        "timezone": "auto",
    })
    response.raise_for_status()
    data = response.json()

    hours = data["hourly"]["time"]          # list of ISO strings "2024-01-01T06:00"
    temps = data["hourly"]["temperature_2m"]
    precip = data["hourly"]["precipitation"]

    def avg_hours(start: int, end: int, values: list) -> Optional[float]:
        """Average values for hours [start, end) of the day."""
        subset = [values[i] for i, h in enumerate(hours)
                  if int(h[11:13]) in range(start, end) and values[i] is not None]
        return round(sum(subset) / len(subset), 2) if subset else None

    morning_temp = c_to_f(avg_hours(6, 10, temps))   # 06:00–09:00 in °F
    night_temp   = c_to_f(avg_hours(21, 24, temps))  # 21:00–23:00 in °F
    temp_diff    = round(morning_temp - night_temp, 2) if (morning_temp is not None and night_temp is not None) else None
    is_rainy     = int(any(p > 0 for p in precip if p is not None))

    return {
        "city": city.strip().title(),
        "date": str(date.today()),
        "morning_temp": morning_temp,
        "night_temp": night_temp,
        "temp_diff": temp_diff,
        "is_rainy": is_rainy,
    }
