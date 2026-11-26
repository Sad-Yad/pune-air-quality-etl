"""Unit tests for outdoor activity scores, rush-hour indicators, and alert rules."""
import unittest
from datetime import datetime
from src.transform.features import is_pune_rush_hour, is_pune_weekend, calculate_outdoor_activity_score
from src.analytics.alerts import AlertEngine
from src.load.models import Location, AirQualityReading, WeatherReading


class TestFeatures(unittest.TestCase):
    def test_rush_hour_indicator(self):
        """8-11 AM and 5-9 PM IST must trigger rush hour flag."""
        t_morning_rush = datetime(2024, 1, 15, 8, 30)
        t_morning_non_rush = datetime(2024, 1, 15, 11, 30)
        t_evening_rush = datetime(2024, 1, 15, 18, 0)
        t_night = datetime(2024, 1, 15, 23, 0)

        self.assertTrue(is_pune_rush_hour(t_morning_rush))
        self.assertFalse(is_pune_rush_hour(t_morning_non_rush))
        self.assertTrue(is_pune_rush_hour(t_evening_rush))
        self.assertFalse(is_pune_rush_hour(t_night))

    def test_weekend_indicator(self):
        """Saturday and Sunday must trigger weekend flag."""
        saturday = datetime(2024, 1, 13)
        sunday = datetime(2024, 1, 14)
        monday = datetime(2024, 1, 15)

        self.assertTrue(is_pune_weekend(saturday))
        self.assertTrue(is_pune_weekend(sunday))
        self.assertFalse(is_pune_weekend(monday))

    def test_outdoor_activity_score_behavior(self):
        """Ideal conditions score near 100; severe pollution strongly reduces score."""
        ideal_score = calculate_outdoor_activity_score(
            pm2_5=8.0,
            aqi=1,
            temp_c=24.0,
            humidity_pct=45.0,
            wind_speed_kph=12.0
        )
        self.assertGreaterEqual(ideal_score, 90.0)

        severe_score = calculate_outdoor_activity_score(
            pm2_5=120.0,
            aqi=5,
            temp_c=39.0,
            humidity_pct=88.0,
            wind_speed_kph=2.0
        )
        self.assertLess(severe_score, 40.0)

    def test_alert_rules_evaluation(self):
        """Rule engine generates appropriate alerts on bad conditions."""
        loc = Location(location_id="hadapsar", location_name="Hadapsar", latitude=18.5, longitude=73.9, is_active=True)
        
        latest_aq = AirQualityReading(
            location_id="hadapsar",
            observed_at_utc=datetime.utcnow(),
            observed_at_ist=datetime.now(),
            pm2_5=75.0,
            openweather_aqi=4
        )
        latest_w = WeatherReading(
            location_id="hadapsar",
            observed_at_utc=datetime.utcnow(),
            observed_at_ist=datetime.now(),
            wind_speed_kph=5.0
        )

        class MockSession:
            def __init__(self):
                self.added = []
            def add(self, obj):
                self.added.append(obj)
            def commit(self):
                pass

        mock_session = MockSession()
        engine = AlertEngine(session=mock_session)
        alerts = engine.evaluate_rules_for_location(
            location=loc,
            latest_aq=latest_aq,
            latest_w=latest_w,
            pm25_pct_change_3h=35.0
        )

        alert_types = [a.alert_type for a in alerts]
        self.assertIn("AQI_CATEGORY_POOR", alert_types)
        self.assertIn("PM25_RAPID_SURGE", alert_types)
        self.assertIn("PM25_THRESHOLD_EXCEEDED", alert_types)
        self.assertIn("STAGNANT_AIR_INVERSION", alert_types)


if __name__ == "__main__":
    unittest.main()
