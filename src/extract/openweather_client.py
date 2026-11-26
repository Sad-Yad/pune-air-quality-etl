"""OpenWeather API Client with exponential backoff, retry logic, and raw JSON storage."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import AppSettings, RAW_DATA_DIR, setup_logger

logger = setup_logger("openweather_client")


class OpenWeatherClient:
    """Handles communication with OpenWeather APIs with resilient retries and raw data dumping."""

    WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
    AIR_POLLUTION_URL = "https://api.openweathermap.org/data/2.5/air_pollution"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10, max_retries: int = 3):
        self.settings = AppSettings()
        self.api_key = api_key or self.settings.openweather_api_key
        if not self.api_key:
            logger.warning("OPENWEATHER_API_KEY is not set or empty. API calls will fail.")

        self.timeout = timeout
        self.max_retries = max_retries

        # Build session with backoff retry strategy for transient 5xx & connection errors
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1.0,  # wait 1s, 2s, 4s...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _save_raw_json(self, category: str, location_id: str, fetch_time_utc: datetime, payload: Dict[str, Any]) -> Path:
        """
        Saves raw JSON response according to the partition pattern:
        data/raw/{category}/location={location_id}/ingestion_date=YYYY-MM-DD/timestamp=YYYYMMDDTHHMMSSZ.json
        """
        date_str = fetch_time_utc.strftime("%Y-%m-%d")
        ts_str = fetch_time_utc.strftime("%Y%m%dT%H%M%SZ")
        
        target_dir = RAW_DATA_DIR / category / f"location={location_id}" / f"ingestion_date={date_str}"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = target_dir / f"timestamp={ts_str}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            
        logger.debug(f"Saved raw {category} payload to {file_path}")
        return file_path

    def get_current_weather(self, location_id: str, lat: float, lon: float) -> Tuple[Dict[str, Any], int, datetime]:
        """
        Fetches current weather for a location and saves raw payload.
        Returns: (payload_dict, status_code, fetched_at_utc)
        """
        fetch_time = datetime.now(timezone.utc)
        params = {
            "lat": lat,
            "lon": lon,
            "units": "metric",
            "appid": self.api_key
        }

        logger.info(f"Fetching current weather for {location_id} (lat: {lat}, lon: {lon})")
        try:
            response = self.session.get(self.WEATHER_URL, params=params, timeout=self.timeout)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to fetch weather for {location_id}: {exc}")
            raise

        # Wrap with ingestion metadata & save raw
        meta_payload = {
            "location_id": location_id,
            "source": "openweather",
            "endpoint": "weather",
            "requested_at": fetch_time.isoformat(),
            "response_status": status_code,
            "response_payload": payload
        }
        self._save_raw_json("weather", location_id, fetch_time, meta_payload)

        return payload, status_code, fetch_time

    def get_air_pollution(self, location_id: str, lat: float, lon: float) -> Tuple[Dict[str, Any], int, datetime]:
        """
        Fetches air pollution data for a location and saves raw payload.
        Returns: (payload_dict, status_code, fetched_at_utc)
        """
        fetch_time = datetime.now(timezone.utc)
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key
        }

        logger.info(f"Fetching air pollution for {location_id} (lat: {lat}, lon: {lon})")
        try:
            response = self.session.get(self.AIR_POLLUTION_URL, params=params, timeout=self.timeout)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to fetch air pollution for {location_id}: {exc}")
            raise

        # Wrap with ingestion metadata & save raw
        meta_payload = {
            "location_id": location_id,
            "source": "openweather",
            "endpoint": "air_pollution",
            "requested_at": fetch_time.isoformat(),
            "response_status": status_code,
            "response_payload": payload
        }
        self._save_raw_json("air_quality", location_id, fetch_time, meta_payload)

        return payload, status_code, fetch_time
