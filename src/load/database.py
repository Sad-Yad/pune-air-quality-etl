"""Database connection and session management supporting SQLite and PostgreSQL."""
from contextlib import contextmanager
from typing import Generator, List, Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.config import AppSettings, setup_logger, load_locations
from src.load.models import Base, Location, WeatherReading, AirQualityReading, LocationHourlyFeature, Alert

logger = setup_logger("database")
settings = AppSettings()

# Connect_args for SQLite to handle multi-threaded dashboard access
connect_args = {}
db_url = settings.database_url

# Handle postgres:// and postgresql:// schema aliases
# Explicitly use postgresql+psycopg2:// so SQLAlchemy uses psycopg2-binary
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for safe database session lifecycles."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session rollback due to error: {e}")
        raise
    finally:
        session.close()


def init_db() -> None:
    """Creates database tables and seeds locations from configuration."""
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("Schema initialized.")

    # Seed locations
    locations = load_locations()
    with get_db_session() as session:
        for loc in locations:
            existing = session.query(Location).filter_by(location_id=loc.location_id).first()
            if not existing:
                new_loc = Location(
                    location_id=loc.location_id,
                    location_name=loc.location_name,
                    latitude=loc.latitude,
                    longitude=loc.longitude,
                    is_active=loc.is_active,
                )
                session.add(new_loc)
            else:
                existing.location_name = loc.location_name
                existing.latitude = loc.latitude
                existing.longitude = loc.longitude
                existing.is_active = loc.is_active
        session.commit()
        logger.info(f"Loaded {len(locations)} location configurations into database.")


def upsert_weather_reading(session: Session, data: Dict[str, Any]) -> bool:
    """
    Inserts or updates a weather reading idempotently.
    Returns True if inserted/updated.
    """
    reading = session.query(WeatherReading).filter_by(
        location_id=data["location_id"],
        observed_at_utc=data["observed_at_utc"]
    ).first()

    if reading:
        for key, value in data.items():
            setattr(reading, key, value)
    else:
        reading = WeatherReading(**data)
        session.add(reading)
    return True


def upsert_air_quality_reading(session: Session, data: Dict[str, Any]) -> bool:
    """
    Inserts or updates an air quality reading idempotently.
    Returns True if inserted/updated.
    """
    reading = session.query(AirQualityReading).filter_by(
        location_id=data["location_id"],
        observed_at_utc=data["observed_at_utc"]
    ).first()

    if reading:
        for key, value in data.items():
            setattr(reading, key, value)
    else:
        reading = AirQualityReading(**data)
        session.add(reading)
    return True


def upsert_hourly_feature(session: Session, data: Dict[str, Any]) -> bool:
    """
    Inserts or updates an hourly aggregated feature idempotently.
    """
    feature = session.query(LocationHourlyFeature).filter_by(
        location_id=data["location_id"],
        hour_start_utc=data["hour_start_utc"]
    ).first()

    if feature:
        for key, value in data.items():
            setattr(feature, key, value)
    else:
        feature = LocationHourlyFeature(**data)
        session.add(feature)
    return True
