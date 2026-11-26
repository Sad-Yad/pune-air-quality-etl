"""Application configuration and logging setup."""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
LOG_DIR = DATA_DIR / "logs"

# Ensure data and log directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


class LocationConfig(BaseModel):
    """Configuration schema for a monitored location."""
    location_id: str
    location_name: str
    latitude: float
    longitude: float
    is_active: bool = True


class AppSettings(BaseModel):
    """Global application settings."""
    openweather_api_key: str = Field(default_factory=lambda: os.getenv("OPENWEATHER_API_KEY", ""))
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'pune_air_quality.db'}"))
    ingest_interval_minutes: int = Field(default_factory=lambda: int(os.getenv("INGEST_INTERVAL_MINUTES", "15")))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


def load_locations(config_path: Optional[Path] = None) -> List[LocationConfig]:
    """Loads location configurations from a YAML file."""
    path = config_path or (CONFIG_DIR / "locations.yaml")
    if not path.exists():
        raise FileNotFoundError(f"Locations configuration file not found at {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    locations = [LocationConfig(**loc) for loc in data.get("locations", [])]
    return locations


def setup_logger(name: str = "pune_air_quality") -> logging.Logger:
    """Configures and returns a rotating file and console logger."""
    settings = AppSettings()
    logger = logging.getLogger(name)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Rotating file handler: 5MB max, 5 backups
    log_file = LOG_DIR / "pipeline.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger
