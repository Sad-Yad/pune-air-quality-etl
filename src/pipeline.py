"""ETL Pipeline orchestrator for Pune Air Quality & Weather Intelligence."""
import argparse
import time
from datetime import datetime
from typing import Dict, Any, List
from src.config import setup_logger, load_locations
from src.extract.openweather_client import OpenWeatherClient
from src.transform.normalize import normalize_weather_data, normalize_air_quality_data
from src.transform.features import compute_hourly_features_for_location
from src.load.database import (
    get_db_session,
    init_db,
    upsert_weather_reading,
    upsert_air_quality_reading
)
from src.load.models import RawApiResponse, Location, AirQualityReading, WeatherReading
from src.analytics.trends import calculate_location_trends
from src.analytics.alerts import AlertEngine

logger = setup_logger("pipeline")


class ETLPipeline:
    """Coordinates extract, transform, load, feature computation, and alert triggers."""

    def __init__(self):
        self.locations = load_locations()
        self.client = OpenWeatherClient()

    def run_location(self, session, loc) -> Dict[str, Any]:
        """Runs the ETL lifecycle for a single location."""
        loc_id = loc.location_id
        loc_name = loc.location_name
        lat = loc.latitude
        lon = loc.longitude

        logger.info(f"Processing location: {loc_name} ({loc_id})")

        # 1. EXTRACT
        w_payload, w_status, w_time = self.client.get_current_weather(loc_id, lat, lon)
        aq_payload, aq_status, aq_time = self.client.get_air_pollution(loc_id, lat, lon)

        # Store raw response in DB for audit trail
        session.add(RawApiResponse(
            location_id=loc_id,
            source="openweather",
            endpoint="weather",
            fetched_at_utc=w_time.replace(tzinfo=None),
            response_status=w_status,
            response_json=str(w_payload)
        ))
        session.add(RawApiResponse(
            location_id=loc_id,
            source="openweather",
            endpoint="air_pollution",
            fetched_at_utc=aq_time.replace(tzinfo=None),
            response_status=aq_status,
            response_json=str(aq_payload)
        ))

        # 2. TRANSFORM & NORMALIZE
        w_record = normalize_weather_data(loc_id, w_payload)
        aq_record = normalize_air_quality_data(loc_id, aq_payload)

        # 3. LOAD / UPSERT
        upsert_weather_reading(session, w_record)
        upsert_air_quality_reading(session, aq_record)
        session.commit()

        # 4. HOURLY FEATURE AGGREGATION
        obs_utc = aq_record["observed_at_utc"]
        compute_hourly_features_for_location(session, loc_id, obs_utc)

        # 5. ALERT EVALUATION
        trend_stats = calculate_location_trends(session, loc_id)
        latest_aq = session.query(AirQualityReading).filter_by(
            location_id=loc_id, observed_at_utc=obs_utc
        ).first()
        latest_w = session.query(WeatherReading).filter_by(
            location_id=loc_id, observed_at_utc=w_record["observed_at_utc"]
        ).first()
        loc_model = session.query(Location).filter_by(location_id=loc_id).first()

        alert_engine = AlertEngine(session)
        alerts = alert_engine.evaluate_rules_for_location(
            location=loc_model,
            latest_aq=latest_aq,
            latest_w=latest_w,
            pm25_pct_change_3h=trend_stats.get("pct_change_3h_pm2_5", 0.0)
        )

        return {
            "location_id": loc_id,
            "status": "success",
            "weather_quality": w_record["data_quality_flag"],
            "aq_quality": aq_record["data_quality_flag"],
            "alerts_count": len(alerts)
        }

    def run(self) -> Dict[str, Any]:
        """Executes full pipeline iteration across all configured active locations."""
        start_time = time.time()
        start_dt = datetime.utcnow()
        logger.info(f"--- ETL PIPELINE RUN STARTED at {start_dt.isoformat()} UTC ---")

        results = []
        failures = 0
        successes = 0

        with get_db_session() as session:
            for loc in self.locations:
                if not loc.is_active:
                    continue
                try:
                    res = self.run_location(session, loc)
                    results.append(res)
                    successes += 1
                except Exception as exc:
                    failures += 1
                    logger.error(f"Failed pipeline run for location {loc.location_id}: {exc}", exc_info=True)
                    results.append({
                        "location_id": loc.location_id,
                        "status": "failed",
                        "error": str(exc)
                    })

        duration = round(time.time() - start_time, 2)
        summary = {
            "start_time": start_dt.isoformat(),
            "duration_seconds": duration,
            "total_locations": len(self.locations),
            "successes": successes,
            "failures": failures,
            "details": results
        }
        logger.info(f"--- ETL PIPELINE COMPLETED in {duration}s. Success: {successes}, Failures: {failures} ---")
        return summary


def main():
    """CLI entrypoint supporting --once execution."""
    parser = argparse.ArgumentParser(description="Pune Air Quality & Weather ETL Pipeline")
    parser.add_argument("--once", action="store_true", help="Run ingestion once and exit")
    args = parser.parse_args()

    # Ensure schema is ready
    init_db()

    pipeline = ETLPipeline()
    summary = pipeline.run()
    print(f"Pipeline finished: {summary['successes']} succeeded, {summary['failures']} failed in {summary['duration_seconds']}s")


if __name__ == "__main__":
    main()
