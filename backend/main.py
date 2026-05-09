from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from database import init_db, get_connection
from weather import fetch_forecast

app = FastAPI(title="Daily Weather Summary")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def serve_ui():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/cities-page")
def serve_cities_ui():
    return FileResponse(FRONTEND_DIR / "cities.html")


# ── Tracked cities ─────────────────────────────────────────────────────────────

@app.get("/cities")
def list_cities():
    with get_connection() as conn:
        rows = conn.execute("SELECT city FROM tracked_cities ORDER BY city").fetchall()
    return [r["city"] for r in rows]


@app.post("/cities")
def add_city(city: str = Query(..., description="City name to track")):
    city = city.strip().title()
    with get_connection() as conn:
        try:
            conn.execute("INSERT INTO tracked_cities (city) VALUES (?)", (city,))
            conn.commit()
        except Exception:
            raise HTTPException(status_code=409, detail=f"{city} is already tracked")
    return {"message": f"{city} added"}


@app.delete("/cities")
def remove_city(city: str = Query(..., description="City name to remove")):
    city = city.strip().title()
    with get_connection() as conn:
        conn.execute("DELETE FROM tracked_cities WHERE city = ?", (city,))
        conn.commit()
    return {"message": f"{city} removed"}


# ── Fetch & store today's forecast ────────────────────────────────────────────

@app.post("/weather/fetch")
def fetch_weather(city: str = Query(..., description="City name")):
    try:
        record = fetch_forecast(city)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather API error: {e}")

    record["fetched_at"] = datetime.utcnow().isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO weather_records (city, date, morning_temp, night_temp, temp_diff, is_rainy, fetched_at)
            VALUES (:city, :date, :morning_temp, :night_temp, :temp_diff, :is_rainy, :fetched_at)
            ON CONFLICT(city, date) DO UPDATE SET
                morning_temp = excluded.morning_temp,
                night_temp   = excluded.night_temp,
                temp_diff    = excluded.temp_diff,
                is_rainy     = excluded.is_rainy,
                fetched_at   = excluded.fetched_at
        """, record)
        conn.commit()

    return {"message": "Saved", "record": record}


# ── Summary stats ──────────────────────────────────────────────────────────────

@app.get("/weather/summary")
def get_summary(city: str = Query(..., description="City name")):
    city = city.strip().title()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                        AS total_days,
                SUM(is_rainy)                   AS rainy_days,
                ROUND(AVG(CASE WHEN is_rainy = 1 THEN 1.0 ELSE 0 END) * 100, 1) AS rainy_pct,
                ROUND(AVG(temp_diff), 2)        AS avg_temp_diff,
                ROUND(AVG(morning_temp), 2)     AS avg_morning_temp,
                ROUND(AVG(night_temp), 2)       AS avg_night_temp
            FROM weather_records
            WHERE city = ?
        """, (city,)).fetchone()

    if not row or row["total_days"] == 0:
        raise HTTPException(status_code=404, detail=f"No data found for {city}")

    return dict(row)


# ── Weekly average ─────────────────────────────────────────────────────────────

@app.get("/weather/weekly")
def get_weekly(city: str = Query(..., description="City name")):
    city = city.strip().title()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                        AS days_recorded,
                SUM(is_rainy)                   AS rainy_days,
                ROUND(AVG(morning_temp), 2)     AS avg_morning_temp,
                ROUND(AVG(night_temp), 2)       AS avg_night_temp,
                ROUND(AVG(temp_diff), 2)        AS avg_temp_diff
            FROM weather_records
            WHERE city = ?
              AND date >= date('now', '-6 days')
        """, (city,)).fetchone()

    if not row or row["days_recorded"] == 0:
        raise HTTPException(status_code=404, detail=f"No data in the last 7 days for {city}")

    return dict(row)


# ── History ────────────────────────────────────────────────────────────────────

@app.get("/weather/history")
def get_history(city: str = Query(..., description="City name")):
    city = city.strip().title()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT date, morning_temp, night_temp, temp_diff, is_rainy, fetched_at
            FROM weather_records
            WHERE city = ?
            ORDER BY date DESC
        """, (city,)).fetchall()

    return [dict(r) for r in rows]
