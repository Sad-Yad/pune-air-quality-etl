"""Unit tests for data normalization and conversions."""
import unittest
from datetime import datetime
from src.transform.normalize import (
    unix_to_utc_and_ist,
    ms_to_kph,
    normalize_weather_data,
    normalize_air_quality_data,
    AQI_CATEGORY_MAP
)


class TestNormalize(unittest.TestCase):
    def test_unix_timestamp_to_utc_and_ist(self):
        """Checks accurate conversion from Unix timestamp to UTC and IST (+5h 30m)."""
        unix_ts = 1700000000
        dt_utc, dt_ist = unix_to_utc_and_ist(unix_ts)
        self.assertEqual(dt_utc.strftime("%Y-%m-%d %H:%M:%S"), "2023-11-14 22:13:20")
        self.assertEqual(dt_ist.strftime("%Y-%m-%d %H:%M:%S"), "2023-11-15 03:43:20")

    def test_ms_to_kph_conversion(self):
        """Validates wind speed conversion factor (3.6x)."""
        self.assertIsNone(ms_to_kph(None))
        self.assertEqual(ms_to_kph(0.0), 0.0)
        self.assertEqual(ms_to_kph(2.0), 7.2)
        self.assertEqual(ms_to_kph(10.0), 36.0)

    def test_aqi_category_mapping(self):
        """Ensures exact mapping for OpenWeather AQI 1..5."""
        self.assertEqual(AQI_CATEGORY_MAP[1], "Good")
        self.assertEqual(AQI_CATEGORY_MAP[2], "Fair")
        self.assertEqual(AQI_CATEGORY_MAP[3], "Moderate")
        self.assertEqual(AQI_CATEGORY_MAP[4], "Poor")
        self.assertEqual(AQI_CATEGORY_MAP[5], "Very Poor")

    def test_normalize_weather_data(self):
        """Tests normalization of raw weather dictionary into database schema."""
        raw = {
            "dt": 1700000000,
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "main": {"temp": 28.4, "feels_like": 29.1, "humidity": 60, "pressure": 1010},
            "wind": {"speed": 3.0, "deg": 270},
            "rain": {"1h": 1.2}
        }
        normalized = normalize_weather_data("kothrud", raw)
        self.assertEqual(normalized["location_id"], "kothrud")
        self.assertEqual(normalized["temperature_c"], 28.4)
        self.assertEqual(normalized["humidity_pct"], 60.0)
        self.assertEqual(normalized["wind_speed_kph"], 10.8)
        self.assertEqual(normalized["precipitation_mm"], 1.2)
        self.assertEqual(normalized["data_quality_flag"], "valid")

    def test_normalize_air_quality_preserves_nulls(self):
        """Tests that missing pollutant components are preserved as None (NULL)."""
        raw = {
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "list": [{
                "dt": 1700000000,
                "main": {"aqi": 3},
                "components": {
                    "pm2_5": 38.5,
                    "pm10": 72.0
                }
            }]
        }
        normalized = normalize_air_quality_data("bhosari", raw)
        self.assertEqual(normalized["location_id"], "bhosari")
        self.assertEqual(normalized["pm2_5"], 38.5)
        self.assertIsNone(normalized["no2"])
        self.assertEqual(normalized["openweather_aqi"], 3)
        self.assertEqual(normalized["aqi_category"], "Moderate")
        self.assertEqual(normalized["data_quality_flag"], "valid")


if __name__ == "__main__":
    unittest.main()
