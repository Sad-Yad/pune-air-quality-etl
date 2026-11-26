# Pune Air Quality & Weather Intelligence

A complete, production-minded Python data-engineering pipeline and intelligence platform that ingests, validates, normalizes, stores, and analyzes environmental data for 6 key Pune urban and industrial corridors every 15 minutes.

---

## 1. System Architecture

```
[OpenWeather APIs]
 (Current Weather & Air Pollution)
         │
         ▼
[1. Extract Layer] (src/extract/openweather_client.py)
 ├── Exponential Backoff Retries (urllib3/requests)
 └── Hive Partitioned Raw JSON Archive (data/raw/)
         │
         ▼
[2. Transform & Validation] (src/transform/)
 ├── Pydantic Bounding Box & Range Checks (validate.py)
 ├── UTC/IST Conversion, m/s -> km/h, AQI Mapping (normalize.py)
 └── Hourly Aggregations & Outdoor Activity Score (features.py)
         │
         ▼
[3. Storage Layer] (src/load/database.py & models.py)
 ├── SQLAlchemy ORM (SQLite / PostgreSQL ready)
 └── Idempotent Upserts (Unique constraints on location + timestamp)
         │
         ├───► [4. Rule Alert Engine] (src/analytics/alerts.py)
         │      └── Rapid surges, Poor AQI, Inversion/Stagnation
         │
         └───► [5. Dashboard Layer] (dashboard/app.py)
                └── Streamlit & Plotly (Clean, non-neon, mobile-responsive)
```

---

## 2. Monitored Pune Locations

Monitored corridors are fully configurable in [config/locations.yaml](file:///c:/Users/wwwsa/Documents/Mini_pro/config/locations.yaml):
1. **Pashan / IITM**: `18.5204, 73.8567` (Western educational/green belt)
2. **Kothrud**: `18.5074, 73.8077` (High-density residential & arterial corridor)
3. **Hadapsar**: `18.5018, 73.9260` (Eastern IT and commercial zone)
4. **Bhosari**: `18.6296, 73.8485` (Northern industrial/manufacturing belt)
5. **Nigdi**: `18.6298, 73.7997` (PCMC residential & automotive cluster)
6. **Lohegaon**: `18.5793, 73.9177` (Northeastern airport & transit hub)

---

## 3. Database Schema

The database is built with SQLAlchemy and supports both SQLite (`data/pune_air_quality.db`) and PostgreSQL via the `DATABASE_URL` environment variable:

- **`locations`**: Metadata for all monitored geographical locations (`location_id`, `location_name`, `latitude`, `longitude`, `is_active`).
- **`raw_api_responses`**: Complete audit log of raw API calls (`response_id`, `location_id`, `source`, `endpoint`, `fetched_at_utc`, `response_status`, `response_json`, `created_at_utc`).
- **`weather_readings`**: Clean weather observations with unique constraint on `(location_id, observed_at_utc)` (`temperature_c`, `feels_like_c`, `humidity_pct`, `pressure_hpa`, `wind_speed_kph`, `precipitation_mm`, `data_quality_flag`).
- **`air_quality_readings`**: Clean air pollution measurements (`pm2_5`, `pm10`, `no2`, `o3`, `co`, `so2`, `openweather_aqi`, `aqi_category`, `data_quality_flag`).
- **`location_hourly_features`**: Aggregated rollups per hour bucket (`avg_pm2_5`, `max_pm2_5`, `avg_pm10`, `avg_temperature_c`, `pm2_5_trend_3h`, `is_rush_hour`, `is_weekend`, `outdoor_activity_score`).
- **`alerts`**: Rule-based alert log with severity tags and notification records (`alert_id`, `location_id`, `alert_type`, `severity`, `message`, `triggered_at_ist`, `is_active`).

---

## 4. Setup & Installation

### Prerequisites
- Python 3.11+
- Git

### Step 1: Clone & Install Dependencies
```bash
cd pune-air-quality-etl
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and set your OpenWeather API key:
```env
OPENWEATHER_API_KEY=your_actual_api_key_here
DATABASE_URL=sqlite:///data/pune_air_quality.db
INGEST_INTERVAL_MINUTES=15
LOG_LEVEL=INFO
```

#### How to get an OpenWeather API Key:
1. Sign up at [https://openweathermap.org/appid](https://openweathermap.org/appid).
2. Go to your API keys section and copy your free 32-character API key.
3. Paste it into `.env`.

---

## 5. Running the Application

### A. Run Ingestion Once (Manual Batch)
Runs a single extraction, transformation, feature computation, and alert evaluation cycle across all 6 locations:
```bash
python -m src.pipeline --once
```

### B. Run Background Scheduler (Periodic 15-Minute ETL)
Launches the APScheduler daemon that executes ingestion every 15 minutes:
```bash
python -m src.scheduler
```

### C. Launch Streamlit Dashboard
Start the clean, responsive monitoring UI:
```bash
streamlit run dashboard/app.py
```
Open your browser at `http://localhost:8501`.

---

## 6. Running Tests

The test suite covers bounding box validation, negative pollutant rejections, timestamp and unit conversions, outdoor activity scoring, rush-hour identification, and rule-based alerting:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
Or with pytest (if installed):
```bash
pytest -v
```

---

## 7. Analytics & Scoring Details

### Outdoor Activity Score (0 to 100)
- **Base Score:** 100
- **PM2.5 Penalty:** Scaled penalty based on WHO benchmarks ($\le 15$ µg/m³ is ideal; $> 75$ µg/m³ applies maximum penalty).
- **AQI Penalty:** Scaled across OpenWeather AQI 1 (Good) to 5 (Very Poor).
- **Thermal Comfort Zone:** Evaluated against 20°C–30°C temperature and 30%–65% relative humidity.
- **Dispersion Adjustment:** Low wind ($< 4$ km/h / stagnant air) applies an inversion penalty; moderate wind (8–22 km/h) applies an atmospheric dispersion bonus.

### Stagnation & Inversion Warning
When wind speed drops below 2 m/s (7.2 km/h) and relative humidity exceeds 70% while PM2.5 is rising, the system flags atmospheric stagnation.

---

## 8. Future Improvements
- **PostgreSQL / TimescaleDB Migration:** Set `DATABASE_URL=postgresql://user:pass@host:5432/db` for hypertable time-series partitioning.
- **Telegram / Slack Dispatcher:** Implement `NotificationDispatcher` subclasses to push real-time alert webhooks.
- **Forecast Ingestion:** Ingest 5-day / 3-hour forecasts to predict future outdoor windows.
