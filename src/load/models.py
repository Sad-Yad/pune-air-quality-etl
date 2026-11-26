"""SQLAlchemy ORM models for Pune Air Quality & Weather Intelligence."""
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Location(Base):
    """Monitored location entity."""
    __tablename__ = "locations"

    location_id = Column(String(50), primary_key=True)
    location_name = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    weather_readings = relationship("WeatherReading", back_populates="location", cascade="all, delete-orphan")
    air_quality_readings = relationship("AirQualityReading", back_populates="location", cascade="all, delete-orphan")
    hourly_features = relationship("LocationHourlyFeature", back_populates="location", cascade="all, delete-orphan")
    raw_responses = relationship("RawApiResponse", back_populates="location", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="location", cascade="all, delete-orphan")


class RawApiResponse(Base):
    """Archived API response metadata and JSON payload."""
    __tablename__ = "raw_api_responses"

    response_id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String(50), ForeignKey("locations.location_id"), nullable=False)
    source = Column(String(50), nullable=False)  # openweather
    endpoint = Column(String(100), nullable=False)  # weather or air_pollution
    fetched_at_utc = Column(DateTime, nullable=False)
    response_status = Column(Integer, nullable=False)
    response_json = Column(Text, nullable=False)
    created_at_utc = Column(DateTime, default=datetime.utcnow, nullable=False)

    location = relationship("Location", back_populates="raw_responses")


class WeatherReading(Base):
    """Normalized weather observation."""
    __tablename__ = "weather_readings"

    reading_id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String(50), ForeignKey("locations.location_id"), nullable=False)
    observed_at_utc = Column(DateTime, nullable=False)
    observed_at_ist = Column(DateTime, nullable=False)
    temperature_c = Column(Float, nullable=True)
    feels_like_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    pressure_hpa = Column(Float, nullable=True)
    wind_speed_kph = Column(Float, nullable=True)
    wind_direction_deg = Column(Float, nullable=True)
    precipitation_mm = Column(Float, nullable=True)
    data_quality_flag = Column(String(20), nullable=False, default="valid")
    ingested_at_utc = Column(DateTime, default=datetime.utcnow, nullable=False)

    location = relationship("Location", back_populates="weather_readings")

    __table_args__ = (
        UniqueConstraint("location_id", "observed_at_utc", name="uq_weather_location_time"),
        Index("idx_weather_loc_time", "location_id", "observed_at_utc"),
    )


class AirQualityReading(Base):
    """Normalized air pollution observation."""
    __tablename__ = "air_quality_readings"

    reading_id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String(50), ForeignKey("locations.location_id"), nullable=False)
    observed_at_utc = Column(DateTime, nullable=False)
    observed_at_ist = Column(DateTime, nullable=False)
    pm2_5 = Column(Float, nullable=True)
    pm10 = Column(Float, nullable=True)
    no2 = Column(Float, nullable=True)
    o3 = Column(Float, nullable=True)
    co = Column(Float, nullable=True)
    so2 = Column(Float, nullable=True)
    openweather_aqi = Column(Integer, nullable=True)
    aqi_category = Column(String(30), nullable=True)
    data_quality_flag = Column(String(20), nullable=False, default="valid")
    ingested_at_utc = Column(DateTime, default=datetime.utcnow, nullable=False)

    location = relationship("Location", back_populates="air_quality_readings")

    __table_args__ = (
        UniqueConstraint("location_id", "observed_at_utc", name="uq_aq_location_time"),
        Index("idx_aq_loc_time", "location_id", "observed_at_utc"),
    )


class LocationHourlyFeature(Base):
    """Hourly aggregated environmental features and outdoor activity scores."""
    __tablename__ = "location_hourly_features"

    feature_id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String(50), ForeignKey("locations.location_id"), nullable=False)
    hour_start_utc = Column(DateTime, nullable=False)
    hour_start_ist = Column(DateTime, nullable=False)
    avg_pm2_5 = Column(Float, nullable=True)
    max_pm2_5 = Column(Float, nullable=True)
    avg_pm10 = Column(Float, nullable=True)
    avg_openweather_aqi = Column(Float, nullable=True)
    avg_temperature_c = Column(Float, nullable=True)
    avg_humidity_pct = Column(Float, nullable=True)
    avg_wind_speed_kph = Column(Float, nullable=True)
    pm2_5_trend_3h = Column(Float, nullable=True)  # % change over 3 hours
    aqi_trend_3h = Column(Float, nullable=True)
    is_rush_hour = Column(Boolean, nullable=False, default=False)
    is_weekend = Column(Boolean, nullable=False, default=False)
    outdoor_activity_score = Column(Float, nullable=True)  # 0 to 100
    created_at_utc = Column(DateTime, default=datetime.utcnow, nullable=False)

    location = relationship("Location", back_populates="hourly_features")

    __table_args__ = (
        UniqueConstraint("location_id", "hour_start_utc", name="uq_feature_loc_hour"),
        Index("idx_feature_loc_hour", "location_id", "hour_start_utc"),
    )


class Alert(Base):
    """Rule-based air quality alerts."""
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String(50), ForeignKey("locations.location_id"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)  # INFO, WARNING, CRITICAL
    message = Column(Text, nullable=False)
    triggered_at_utc = Column(DateTime, default=datetime.utcnow, nullable=False)
    triggered_at_ist = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    location = relationship("Location", back_populates="alerts")
