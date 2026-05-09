# Daily Weather Summary

A simple FastAPI app that fetches daily weather forecasts via [Open-Meteo](https://open-meteo.com/) (free, no API key required), stores results in SQLite, and displays stats in a plain HTML/JS UI.

## Features
- 🌤 Fetch today's forecast for any city
- 🗄 Store morning & night temperatures + rain flag per day
- 📊 View average rainy days and average morning–night temperature difference
- 🔗 `POST /weather/fetch` endpoint — wire your external scheduler to this

## Project Structure
```
weather-data/
├── backend/
│   ├── main.py        # FastAPI app
│   ├── database.py    # SQLite setup
│   └── weather.py     # Open-Meteo fetcher
├── frontend/
│   └── index.html     # UI
├── requirements.txt
└── weather.db         # Created on first run (gitignored)
```

## Getting Started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server (must run from inside backend/)
cd backend
uvicorn main:app --reload
```

Open **http://localhost:8000** in your browser.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/weather/fetch?city=London` | Fetch & store today's forecast |
| `GET`  | `/weather/summary?city=London` | Avg rainy days + avg temp diff |
| `GET`  | `/weather/history?city=London` | Full stored history |

## External Scheduler

To trigger daily fetches automatically, point your scheduler (cron, GitHub Actions, n8n, etc.) to:

```
POST http://your-host/weather/fetch?city=YourCity
```

## Data Model

Each record stores:
- `morning_temp` — average of hourly temps at 06:00–09:00 (°C)
- `night_temp` — average of hourly temps at 21:00–23:00 (°C)
- `temp_diff` — morning minus night (°C)
- `is_rainy` — 1 if any hourly precipitation > 0 mm
