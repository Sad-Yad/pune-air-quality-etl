"""Unit tests for coordinate, weather, and air quality validation models (pytest and unittest compatible)."""
import unittest
from pydantic import ValidationError
from src.transform.validate import (
    CoordinateValidator,
    WeatherPayloadValidation,
    AirPollutionPayloadValidation,
)


class TestValidate(unittest.TestCase):
    def test_coordinate_validation_inside_pune(self):
        """Coordinates within Pune bounds must pass."""
        coord = CoordinateValidator(latitude=18.5204, longitude=73.8567)
        self.assertEqual(coord.latitude, 18.5204)
        self.assertEqual(coord.longitude, 73.8567)

    def test_coordinate_validation_outside_pune(self):
        """Coordinates outside Pune bounds (e.g. Mumbai or Delhi) must raise ValidationError."""
        with self.assertRaises(ValidationError):
            CoordinateValidator(latitude=19.0760, longitude=72.8777)  # Mumbai

        with self.assertRaises(ValidationError):
            CoordinateValidator(latitude=28.6139, longitude=77.2090)  # Delhi

    def test_weather_payload_validation_success(self):
        """Valid weather payload structure passes validation."""
        payload = {
            "dt": 1700000000,
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "main": {"temp": 25.5, "humidity": 55, "pressure": 1012},
            "wind": {"speed": 3.5, "deg": 180}
        }
        validated = WeatherPayloadValidation.model_validate(payload)
        self.assertEqual(validated.main["temp"], 25.5)

    def test_weather_payload_invalid_metrics(self):
        """Absurd temperatures or humidities should fail validation."""
        payload_bad_temp = {
            "dt": 1700000000,
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "main": {"temp": 120.0, "humidity": 55, "pressure": 1012}
        }
        with self.assertRaises(ValidationError):
            WeatherPayloadValidation.model_validate(payload_bad_temp)

        payload_bad_hum = {
            "dt": 1700000000,
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "main": {"temp": 25.0, "humidity": 150, "pressure": 1012}
        }
        with self.assertRaises(ValidationError):
            WeatherPayloadValidation.model_validate(payload_bad_hum)

    def test_air_pollution_negative_pollutant_fails(self):
        """Negative pollutant values must fail validation."""
        bad_payload = {
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "list": [{
                "dt": 1700000000,
                "main": {"aqi": 2},
                "components": {"pm2_5": -12.5, "pm10": 40.0}
            }]
        }
        with self.assertRaises(ValidationError):
            AirPollutionPayloadValidation.model_validate(bad_payload)

    def test_air_pollution_invalid_aqi_fails(self):
        """AQI outside 1..5 range must fail."""
        bad_payload = {
            "coord": {"lat": 18.5204, "lon": 73.8567},
            "list": [{
                "dt": 1700000000,
                "main": {"aqi": 99},
                "components": {"pm2_5": 20.0, "pm10": 40.0}
            }]
        }
        with self.assertRaises(ValidationError):
            AirPollutionPayloadValidation.model_validate(bad_payload)


if __name__ == "__main__":
    unittest.main()
