"""Data normalization: converts raw API structures to standard schema with UTC & IST datetimes."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, Tuple
from src.transform.validate import (
    WeatherPayloadValidation,
    AirPollutionPayloadValidation,
    CoordinateValidator,
)
from src.config import setup_logger

logger = setup_logger("normalize")

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

AQI_CATEGORY_MAP = {
    1: "Good",
    2: "Fair",
    3: "Moderate",
    4: "Poor",
    5: "Very Poor",
}


def unix_to_utc_and_ist(unix_ts: int) -> Tuple[datetime, datetime]:
    """Converts a Unix epoch timestamp to naive UTC and IST datetimes for clean SQL storage."""
    dt_utc = datetime.fromtimestamp(unix_ts, tz=UTC)
    dt_ist = dt_utc.astimezone(IST)
    # Return as naive datetimes representing UTC and IST
    return dt_utc.replace(tzinfo=None), dt_ist.replace(tzinfo=None)


def ms_to_kph(wind_speed_ms: float | None) -> float | None:
    """Converts wind speed from meters/sec to km/h."""
    if wind_speed_ms is None:
        return None
    return round(wind_speed_ms * 3.6, 2)


def normalize_weather_data(location_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and normalizes raw weather API response.
    Returns normalized dictionary matching WeatherReading schema.
    """
    quality_flag = "valid"
    try:
        WeatherPayloadValidation.model_validate(payload)
    except Exception as e:
        logger.warning(f"Weather validation partial/invalid for {location_id}: {e}")
        quality_flag = "partial"

    dt_raw = payload.get("dt")
    if dt_raw is None:
        quality_flag = "invalid"
        observed_utc, observed_ist = datetime.utcnow(), datetime.now(IST).replace(tzinfo=None)
    else:
        observed_utc, observed_ist = unix_to_utc_and_ist(dt_raw)

    main = payload.get("main", {})
    wind = payload.get("wind", {})
    rain = payload.get("rain", {})

    temp_c = main.get("temp")
    feels_like_c = main.get("feels_like")
    humidity_pct = main.get("humidity")
    pressure_hpa = main.get("pressure")
    
    wind_speed_ms = wind.get("speed")
    wind_speed_kph = ms_to_kph(wind_speed_ms)
    wind_direction_deg = wind.get("deg")

    # rain.1h is OpenWeather standard rain volume in mm
    precip_mm = rain.get("1h", 0.0) if rain else 0.0

    return {
        "location_id": location_id,
        "observed_at_utc": observed_utc,
        "observed_at_ist": observed_ist,
        "temperature_c": float(temp_c) if temp_c is not None else None,
        "feels_like_c": float(feels_like_c) if feels_like_c is not None else None,
        "humidity_pct": float(humidity_pct) if humidity_pct is not None else None,
        "pressure_hpa": float(pressure_hpa) if pressure_hpa is not None else None,
        "wind_speed_kph": wind_speed_kph,
        "wind_direction_deg": float(wind_direction_deg) if wind_direction_deg is not None else None,
        "precipitation_mm": float(precip_mm) if precip_mm is not None else 0.0,
        "data_quality_flag": quality_flag,
        "ingested_at_utc": datetime.utcnow(),
    }


def normalize_air_quality_data(location_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and normalizes raw air pollution API response.
    Returns normalized dictionary matching AirQualityReading schema.
    """
    quality_flag = "valid"
    try:
        AirPollutionPayloadValidation.model_validate(payload)
    except Exception as e:
        logger.warning(f"Air quality validation partial/invalid for {location_id}: {e}")
        quality_flag = "partial"

    data_list = payload.get("list", [])
    if not data_list:
        quality_flag = "invalid"
        return {
            "location_id": location_id,
            "observed_at_utc": datetime.utcnow(),
            "observed_at_ist": datetime.now(IST).replace(tzinfo=None),
            "pm2_5": None,
            "pm10": None,
            "no2": None,
            "o3": None,
            "co": None,
            "so2": None,
            "openweather_aqi": None,
            "aqi_category": None,
            "data_quality_flag": "invalid",
            "ingested_at_utc": datetime.utcnow(),
        }

    item = data_list[0]
    dt_raw = item.get("dt")
    if dt_raw is None:
        quality_flag = "partial"
        observed_utc, observed_ist = datetime.utcnow(), datetime.now(IST).replace(tzinfo=None)
    else:
        observed_utc, observed_ist = unix_to_utc_and_ist(dt_raw)

    components = item.get("components", {})
    aqi_val = item.get("main", {}).get("aqi")
    aqi_category = AQI_CATEGORY_MAP.get(aqi_val, "Unknown")

    return {
        "location_id": location_id,
        "observed_at_utc": observed_utc,
        "observed_at_ist": observed_ist,
        "pm2_5": float(components.get("pm2_5")) if components.get("pm2_5") is not None else None,
        "pm10": float(components.get("pm10")) if components.get("pm10") is not None else None,
        "no2": float(components.get("no2")) if components.get("no2") is not None else None,
        "o3": float(components.get("o3")) if components.get("o3") is not None else None,
        "co": float(components.get("co")) if components.get("co") is not None else None,
        "so2": float(components.get("so2")) if components.get("so2") is not None else None,
        "openweather_aqi": aqi_val,
        "aqi_category": aqi_category,
        "data_quality_flag": quality_flag,
        "ingested_at_utc": datetime.utcnow(),
    }
