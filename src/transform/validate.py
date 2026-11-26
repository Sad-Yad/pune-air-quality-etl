"""Data validation models using Pydantic for incoming raw data."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, model_validator


# Pune approximate bounding box: Lat ~ 18.2 to 18.8, Lon ~ 73.5 to 74.2
PUNE_LAT_MIN = 18.2
PUNE_LAT_MAX = 18.8
PUNE_LON_MIN = 73.5
PUNE_LON_MAX = 74.2


class CoordinateValidator(BaseModel):
    """Validates that geographical coordinates lie within Pune's bounding box."""
    latitude: float
    longitude: float

    @field_validator("latitude")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not (PUNE_LAT_MIN <= v <= PUNE_LAT_MAX):
            raise ValueError(f"Latitude {v} is outside Pune bounding box [{PUNE_LAT_MIN}, {PUNE_LAT_MAX}]")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not (PUNE_LON_MIN <= v <= PUNE_LON_MAX):
            raise ValueError(f"Longitude {v} is outside Pune bounding box [{PUNE_LON_MIN}, {PUNE_LON_MAX}]")
        return v


class WeatherPayloadValidation(BaseModel):
    """Validates raw OpenWeather Current Weather response."""
    dt: int
    coord: Dict[str, float]
    main: Dict[str, Any]
    wind: Optional[Dict[str, Any]] = None
    rain: Optional[Dict[str, Any]] = None

    @field_validator("dt")
    @classmethod
    def validate_dt(cls, v: int) -> int:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        # OpenWeather timestamp shouldn't be more than 15 minutes in the future
        if v > now_ts + 900:
            raise ValueError(f"Observation timestamp {v} is in the future compared to current time {now_ts}")
        return v

    @field_validator("coord")
    @classmethod
    def validate_coordinates(cls, v: Dict[str, float]) -> Dict[str, float]:
        lat = v.get("lat")
        lon = v.get("lon")
        if lat is None or lon is None:
            raise ValueError("Missing latitude or longitude in weather response coord")
        CoordinateValidator(latitude=lat, longitude=lon)
        return v

    @field_validator("main")
    @classmethod
    def validate_main_metrics(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        temp = v.get("temp")
        humidity = v.get("humidity")
        pressure = v.get("pressure")

        if temp is not None and not (-10.0 <= temp <= 60.0):
            raise ValueError(f"Plausibility check failed: Temperature {temp}°C out of range (-10 to 60°C)")
        if humidity is not None and not (0.0 <= humidity <= 100.0):
            raise ValueError(f"Plausibility check failed: Humidity {humidity}% out of range (0 to 100%)")
        if pressure is not None and not (800.0 <= pressure <= 1100.0):
            raise ValueError(f"Plausibility check failed: Pressure {pressure} hPa out of range (800 to 1100)")
        return v


class AirPollutionPayloadValidation(BaseModel):
    """Validates raw OpenWeather Air Pollution response."""
    coord: Dict[str, float]
    list: List[Dict[str, Any]]

    @field_validator("coord")
    @classmethod
    def validate_coords(cls, v: Dict[str, float]) -> Dict[str, float]:
        lat = v.get("lat") or v.get("latitude")
        lon = v.get("lon") or v.get("longitude")
        if lat is None or lon is None:
            raise ValueError("Missing coordinates in air pollution response")
        CoordinateValidator(latitude=lat, longitude=lon)
        return v

    @field_validator("list")
    @classmethod
    def validate_pollutant_list(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not v:
            raise ValueError("Air pollution response contained empty data list")
        
        entry = v[0]
        dt = entry.get("dt")
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if dt and dt > now_ts + 900:
            raise ValueError(f"Pollution observation timestamp {dt} is in the future")

        components = entry.get("components", {})
        for pollutant, val in components.items():
            if val is not None and val < 0:
                raise ValueError(f"Pollutant {pollutant} has negative value: {val}")

        aqi = entry.get("main", {}).get("aqi")
        if aqi is not None and aqi not in [1, 2, 3, 4, 5]:
            raise ValueError(f"Invalid OpenWeather AQI value: {aqi}. Must be 1 to 5.")
        return v
