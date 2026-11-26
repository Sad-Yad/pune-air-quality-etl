"""Analytics module for calculating trends, city averages, profiles, and recommendations."""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.load.models import WeatherReading, AirQualityReading, Location, LocationHourlyFeature
from src.config import setup_logger

logger = setup_logger("trends")


def get_latest_readings_all_locations(session: Session) -> pd.DataFrame:
    """Returns the most recent air quality & weather record for every active location."""
    query = text("""
        SELECT 
            l.location_id,
            l.location_name,
            l.latitude,
            l.longitude,
            aq.observed_at_ist,
            aq.pm2_5,
            aq.pm10,
            aq.no2,
            aq.o3,
            aq.co,
            aq.so2,
            aq.openweather_aqi,
            aq.aqi_category,
            w.temperature_c,
            w.feels_like_c,
            w.humidity_pct,
            w.pressure_hpa,
            w.wind_speed_kph,
            w.wind_direction_deg,
            w.precipitation_mm
        FROM locations l
        LEFT JOIN (
            SELECT aq1.* FROM air_quality_readings aq1
            INNER JOIN (
                SELECT location_id, MAX(observed_at_utc) as max_time
                FROM air_quality_readings
                GROUP BY location_id
            ) aq2 ON aq1.location_id = aq2.location_id AND aq1.observed_at_utc = aq2.max_time
        ) aq ON l.location_id = aq.location_id
        LEFT JOIN (
            SELECT w1.* FROM weather_readings w1
            INNER JOIN (
                SELECT location_id, MAX(observed_at_utc) as max_time
                FROM weather_readings
                GROUP BY location_id
            ) w2 ON w1.location_id = w2.location_id AND w1.observed_at_utc = w2.max_time
        ) w ON l.location_id = w.location_id
        WHERE l.is_active = TRUE
    """)
    df = pd.read_sql(query, session.bind)
    return df


def calculate_city_metrics(df_latest: pd.DataFrame) -> Dict[str, Any]:
    """Calculates city-wide average and median AQI & PM2.5."""
    if df_latest.empty or df_latest["openweather_aqi"].dropna().empty:
        return {
            "city_avg_aqi": None,
            "city_median_aqi": None,
            "city_avg_pm25": None,
            "city_median_pm25": None,
        }

    return {
        "city_avg_aqi": round(float(df_latest["openweather_aqi"].mean()), 2),
        "city_median_aqi": round(float(df_latest["openweather_aqi"].median()), 2),
        "city_avg_pm25": round(float(df_latest["pm2_5"].mean()), 2),
        "city_median_pm25": round(float(df_latest["pm2_5"].median()), 2),
    }


def calculate_location_trends(session: Session, location_id: str) -> Dict[str, Any]:
    """
    Calculates 1h, 3h, and 6h PM2.5 and AQI changes and 3h percentage change.
    """
    now = datetime.utcnow()
    readings = session.query(AirQualityReading).filter(
        AirQualityReading.location_id == location_id,
        AirQualityReading.observed_at_utc >= now - timedelta(hours=7)
    ).order_by(AirQualityReading.observed_at_utc.desc()).all()

    if not readings:
        return {
            "current_pm2_5": None,
            "trend_1h_pm2_5": 0.0,
            "trend_3h_pm2_5": 0.0,
            "trend_6h_pm2_5": 0.0,
            "pct_change_3h_pm2_5": 0.0,
            "trend_1h_aqi": 0.0,
            "trend_3h_aqi": 0.0,
            "trend_6h_aqi": 0.0,
        }

    current = readings[0]
    curr_pm = current.pm2_5 or 0.0
    curr_aqi = current.openweather_aqi or 0

    def find_past(hours: float) -> Optional[AirQualityReading]:
        target = current.observed_at_utc - timedelta(hours=hours)
        best = None
        best_diff = timedelta(hours=2)
        for r in readings[1:]:
            diff = abs(r.observed_at_utc - target)
            if diff < best_diff:
                best_diff = diff
                best = r
        return best

    r_1h = find_past(1.0)
    r_3h = find_past(3.0)
    r_6h = find_past(6.0)

    pm_1h = (curr_pm - r_1h.pm2_5) if (r_1h and r_1h.pm2_5 is not None) else 0.0
    pm_3h = (curr_pm - r_3h.pm2_5) if (r_3h and r_3h.pm2_5 is not None) else 0.0
    pm_6h = (curr_pm - r_6h.pm2_5) if (r_6h and r_6h.pm2_5 is not None) else 0.0

    pct_3h = ((pm_3h / r_3h.pm2_5) * 100.0) if (r_3h and r_3h.pm2_5 and r_3h.pm2_5 > 0) else 0.0

    aqi_1h = (curr_aqi - r_1h.openweather_aqi) if (r_1h and r_1h.openweather_aqi is not None) else 0
    aqi_3h = (curr_aqi - r_3h.openweather_aqi) if (r_3h and r_3h.openweather_aqi is not None) else 0
    aqi_6h = (curr_aqi - r_6h.openweather_aqi) if (r_6h and r_6h.openweather_aqi is not None) else 0

    return {
        "current_pm2_5": round(curr_pm, 1),
        "trend_1h_pm2_5": round(pm_1h, 1),
        "trend_3h_pm2_5": round(pm_3h, 1),
        "trend_6h_pm2_5": round(pm_6h, 1),
        "pct_change_3h_pm2_5": round(pct_3h, 1),
        "trend_1h_aqi": int(aqi_1h),
        "trend_3h_aqi": int(aqi_3h),
        "trend_6h_aqi": int(aqi_6h),
    }


def analyze_weather_pollution_context(
    wind_speed_kph: Optional[float],
    humidity_pct: Optional[float],
    pct_change_3h_pm25: Optional[float]
) -> Dict[str, Any]:
    """
    Identifies whether stagnant atmospheric conditions (low wind < 7.2 km/h (2 m/s) + high humidity > 70%)
    coincide with rising PM2.5.
    """
    is_low_wind = wind_speed_kph is not None and wind_speed_kph < 7.2
    is_high_humidity = humidity_pct is not None and humidity_pct > 70.0
    is_rising = pct_change_3h_pm25 is not None and pct_change_3h_pm25 > 10.0

    stagnant_inversion = is_low_wind and is_high_humidity and is_rising
    
    explanation = "Normal atmospheric dispersion."
    if stagnant_inversion:
        explanation = "Atmospheric stagnation detected: Low wind and high humidity are trapping particulate matter."
    elif is_low_wind and is_high_humidity:
        explanation = "Stagnant humid air: Risk of particulate buildup if emissions increase."
    elif is_rising:
        explanation = "PM2.5 is rising despite moderate atmospheric dispersion."

    return {
        "stagnant_inversion_detected": stagnant_inversion,
        "is_low_wind": is_low_wind,
        "is_high_humidity": is_high_humidity,
        "is_rising_pm25": is_rising,
        "explanation": explanation
    }


def find_outdoor_and_avoidance_windows(session: Session, location_id: str) -> Dict[str, Any]:
    """
    Examines hourly features over the past 24 hours to identify optimal outdoor activity periods
    and periods that should be avoided.
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)
    features = session.query(LocationHourlyFeature).filter(
        LocationHourlyFeature.location_id == location_id,
        LocationHourlyFeature.hour_start_utc >= cutoff
    ).order_by(LocationHourlyFeature.hour_start_utc.asc()).all()

    if not features:
        return {
            "best_window": "No historical feature data available yet.",
            "avoidance_window": "No historical feature data available yet.",
            "best_score": None
        }

    # Best 2-hour window: max 2-hour rolling average outdoor_activity_score
    best_score = -1.0
    best_time_str = "Midday (typically 12:00 PM - 2:00 PM IST)"
    
    avoidance_str = "None detected (pollution is stable)"
    worst_rising = -999.0

    for i in range(len(features) - 1):
        f1, f2 = features[i], features[i+1]
        s1 = f1.outdoor_activity_score or 0.0
        s2 = f2.outdoor_activity_score or 0.0
        avg_score = (s1 + s2) / 2.0
        if avg_score > best_score:
            best_score = avg_score
            t1 = f1.hour_start_ist.strftime("%I:%M %p")
            t2 = (f2.hour_start_ist + timedelta(hours=1)).strftime("%I:%M %p")
            best_time_str = f"{t1} to {t2} IST (Score: {best_score:.1f}/100)"

        # Check avoidance: high pm2.5 and positive trend
        trend = f1.pm2_5_trend_3h or 0.0
        if (f1.avg_pm2_5 or 0) > 40 and trend > worst_rising:
            worst_rising = trend
            t_start = f1.hour_start_ist.strftime("%I:%M %p")
            avoidance_str = f"Around {t_start} IST (PM2.5: {f1.avg_pm2_5:.1f} µg/m³, Trend: +{trend:.1f}%)"

    return {
        "best_window": best_time_str,
        "avoidance_window": avoidance_str,
        "best_score": round(best_score, 1) if best_score >= 0 else None
    }
