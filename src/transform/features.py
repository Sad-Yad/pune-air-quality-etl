"""Feature engineering: hourly aggregations, rush-hour/weekend flags, and outdoor activity scores."""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.load.models import WeatherReading, AirQualityReading, LocationHourlyFeature
from src.load.database import upsert_hourly_feature
from src.config import setup_logger

logger = setup_logger("features")


def is_pune_rush_hour(dt_ist: datetime) -> bool:
    """
    Rush-hour indicator in IST:
    Morning: 8:00 AM - 11:00 AM (inclusive of 8:00 up to 10:59)
    Evening: 5:00 PM - 9:00 PM (17:00 up to 20:59)
    """
    hour = dt_ist.hour
    return (8 <= hour < 11) or (17 <= hour < 21)


def is_pune_weekend(dt_ist: datetime) -> bool:
    """Returns True if the given IST datetime is Saturday (5) or Sunday (6)."""
    return dt_ist.weekday() in (5, 6)


def calculate_outdoor_activity_score(
    pm2_5: Optional[float],
    aqi: Optional[int | float],
    temp_c: Optional[float],
    humidity_pct: Optional[float],
    wind_speed_kph: Optional[float]
) -> float:
    """
    Computes an outdoor activity score from 0 (terrible) to 100 (ideal).
    Principles:
    - Base score: 100
    - Lower PM2.5 maintains high score; high PM2.5 applies strong penalty.
      (WHO guidelines: <= 15 is good; > 60 is poor; > 120 is severe)
    - Lower AQI keeps score high.
    - Moderate wind (6 to 20 km/h) improves score (dispersion); stagnant (< 3 km/h) or very high (> 35 km/h) penalizes.
    - Extreme temperature (< 15°C or > 35°C) or high humidity (> 75%) reduces score.
    """
    score = 100.0

    # 1. PM2.5 penalty (max 45 points penalty)
    if pm2_5 is not None:
        if pm2_5 <= 15.0:
            score -= (pm2_5 / 15.0) * 5.0  # 0 to 5 pts
        elif pm2_5 <= 35.0:
            score -= 5.0 + ((pm2_5 - 15.0) / 20.0) * 10.0  # 5 to 15 pts
        elif pm2_5 <= 75.0:
            score -= 15.0 + ((pm2_5 - 35.0) / 40.0) * 15.0  # 15 to 30 pts
        else:
            excess = min(pm2_5 - 75.0, 100.0)
            score -= 30.0 + (excess / 100.0) * 15.0  # up to 45 pts

    # 2. AQI penalty (max 25 points penalty)
    if aqi is not None:
        aqi_penalties = {1: 0.0, 2: 5.0, 3: 12.0, 4: 20.0, 5: 25.0}
        score -= aqi_penalties.get(int(round(aqi)), 10.0)

    # 3. Temperature comfort penalty (comfort zone: 20°C - 30°C) (max 15 pts)
    if temp_c is not None:
        if temp_c > 35.0:
            score -= min((temp_c - 35.0) * 3.0, 15.0)
        elif temp_c > 30.0:
            score -= (temp_c - 30.0) * 1.5
        elif temp_c < 15.0:
            score -= min((15.0 - temp_c) * 2.0, 10.0)

    # 4. Humidity penalty (comfort zone: 30% - 65%) (max 10 pts)
    if humidity_pct is not None:
        if humidity_pct > 75.0:
            score -= min((humidity_pct - 75.0) * 0.4, 10.0)
        elif humidity_pct < 20.0:
            score -= 4.0

    # 5. Wind factor (max 10 pts swing)
    if wind_speed_kph is not None:
        if 8.0 <= wind_speed_kph <= 22.0:
            # Good dispersion
            score += 2.0
        elif wind_speed_kph < 4.0:
            # Inversion / stagnant air penalty
            score -= 6.0
        elif wind_speed_kph > 35.0:
            score -= 6.0

    # Clamp score between 0.0 and 100.0
    return round(max(0.0, min(100.0, score)), 1)


def compute_hourly_features_for_location(
    session: Session,
    location_id: str,
    target_hour_utc: datetime
) -> Optional[LocationHourlyFeature]:
    """
    Aggregates readings for a given location and hour bucket, computes 3-hour trends,
    rush hour / weekend flags, and outdoor activity score.
    """
    hour_start = target_hour_utc.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    # Fetch weather readings in this hour
    w_readings = session.query(WeatherReading).filter(
        WeatherReading.location_id == location_id,
        WeatherReading.observed_at_utc >= hour_start,
        WeatherReading.observed_at_utc < hour_end
    ).all()

    # Fetch air quality readings in this hour
    aq_readings = session.query(AirQualityReading).filter(
        AirQualityReading.location_id == location_id,
        AirQualityReading.observed_at_utc >= hour_start,
        AirQualityReading.observed_at_utc < hour_end
    ).all()

    if not w_readings and not aq_readings:
        return None

    # Derive averages
    pm25_vals = [r.pm2_5 for r in aq_readings if r.pm2_5 is not None]
    pm10_vals = [r.pm10 for r in aq_readings if r.pm10 is not None]
    aqi_vals = [r.openweather_aqi for r in aq_readings if r.openweather_aqi is not None]
    
    temp_vals = [r.temperature_c for r in w_readings if r.temperature_c is not None]
    humidity_vals = [r.humidity_pct for r in w_readings if r.humidity_pct is not None]
    wind_vals = [r.wind_speed_kph for r in w_readings if r.wind_speed_kph is not None]

    avg_pm2_5 = round(sum(pm25_vals) / len(pm25_vals), 2) if pm25_vals else None
    max_pm2_5 = round(max(pm25_vals), 2) if pm25_vals else None
    avg_pm10 = round(sum(pm10_vals) / len(pm10_vals), 2) if pm10_vals else None
    avg_aqi = round(sum(aqi_vals) / len(aqi_vals), 1) if aqi_vals else None
    avg_temp = round(sum(temp_vals) / len(temp_vals), 1) if temp_vals else None
    avg_hum = round(sum(humidity_vals) / len(humidity_vals), 1) if humidity_vals else None
    avg_wind = round(sum(wind_vals) / len(wind_vals), 1) if wind_vals else None

    # Hour start in IST: UTC + 5h30m
    hour_start_ist = hour_start + timedelta(hours=5, minutes=30)

    # 3-hour trend calculation: compare with reading ~3 hours ago
    t_3h_ago = hour_start - timedelta(hours=3)
    past_aq = session.query(AirQualityReading).filter(
        AirQualityReading.location_id == location_id,
        AirQualityReading.observed_at_utc >= t_3h_ago - timedelta(minutes=30),
        AirQualityReading.observed_at_utc <= t_3h_ago + timedelta(minutes=30)
    ).order_by(AirQualityReading.observed_at_utc.desc()).first()

    pm2_5_trend_3h = None
    aqi_trend_3h = None
    if past_aq and avg_pm2_5 is not None and past_aq.pm2_5 is not None and past_aq.pm2_5 > 0:
        pct_change = ((avg_pm2_5 - past_aq.pm2_5) / past_aq.pm2_5) * 100.0
        pm2_5_trend_3h = round(pct_change, 1)

    if past_aq and avg_aqi is not None and past_aq.openweather_aqi is not None:
        aqi_trend_3h = round(avg_aqi - past_aq.openweather_aqi, 1)

    is_rush = is_pune_rush_hour(hour_start_ist)
    is_wknd = is_pune_weekend(hour_start_ist)
    outdoor_score = calculate_outdoor_activity_score(avg_pm2_5, avg_aqi, avg_temp, avg_hum, avg_wind)

    feature_data = {
        "location_id": location_id,
        "hour_start_utc": hour_start,
        "hour_start_ist": hour_start_ist,
        "avg_pm2_5": avg_pm2_5,
        "max_pm2_5": max_pm2_5,
        "avg_pm10": avg_pm10,
        "avg_openweather_aqi": avg_aqi,
        "avg_temperature_c": avg_temp,
        "avg_humidity_pct": avg_hum,
        "avg_wind_speed_kph": avg_wind,
        "pm2_5_trend_3h": pm2_5_trend_3h,
        "aqi_trend_3h": aqi_trend_3h,
        "is_rush_hour": is_rush,
        "is_weekend": is_wknd,
        "outdoor_activity_score": outdoor_score,
        "created_at_utc": datetime.utcnow(),
    }

    upsert_hourly_feature(session, feature_data)
    return feature_data
