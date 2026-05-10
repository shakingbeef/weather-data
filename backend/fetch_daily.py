"""
Standalone script to fetch weather data for all tracked cities.

Used by the GitHub Actions daily workflow. Can also be run manually:
    cd backend && python fetch_daily.py

If no tracked cities exist in the database yet, falls back to the
WEATHER_CITIES environment variable (comma-separated city names).
"""

import os
import sys
from datetime import datetime

from database import init_db, get_connection
from weather import fetch_forecast


def get_cities() -> list[str]:
    """Return cities from the DB; fall back to WEATHER_CITIES env var."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT city FROM tracked_cities ORDER BY city"
        ).fetchall()

    cities = [r["city"] for r in rows]

    if not cities:
        env = os.environ.get("WEATHER_CITIES", "")
        cities = [c.strip().title() for c in env.split(",") if c.strip()]

    return cities


def fetch_and_store(city: str) -> dict:
    """Fetch today's forecast for *city* and upsert into the database."""
    record = fetch_forecast(city)
    record["fetched_at"] = datetime.utcnow().isoformat()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO weather_records
                (city, date, morning_temp, night_temp, temp_diff, is_rainy, fetched_at)
            VALUES
                (:city, :date, :morning_temp, :night_temp, :temp_diff, :is_rainy, :fetched_at)
            ON CONFLICT(city, date) DO UPDATE SET
                morning_temp = excluded.morning_temp,
                night_temp   = excluded.night_temp,
                temp_diff    = excluded.temp_diff,
                is_rainy     = excluded.is_rainy,
                fetched_at   = excluded.fetched_at
            """,
            record,
        )
        conn.commit()

    return record


def main():
    init_db()
    cities = get_cities()

    if not cities:
        print(
            "No cities to fetch. Add cities via the API or set "
            "WEATHER_CITIES env var (comma-separated)."
        )
        sys.exit(1)

    print(f"Fetching weather for {len(cities)} city/cities: {', '.join(cities)}")

    errors: list[str] = []
    for city in cities:
        try:
            record = fetch_and_store(city)
            print(f"  ✓ {city}: morning={record['morning_temp']}°F, "
                  f"night={record['night_temp']}°F, rainy={bool(record['is_rainy'])}")
        except Exception as exc:
            errors.append(f"{city}: {exc}")
            print(f"  ✗ {city}: {exc}")

    if errors:
        print(f"\n{len(errors)} error(s) occurred.")
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
