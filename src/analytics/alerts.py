"""Rule-based alerting engine with modular notification dispatcher interface."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.load.models import Alert, AirQualityReading, WeatherReading, Location
from src.config import setup_logger

logger = setup_logger("alerts")
IST = ZoneInfo("Asia/Kolkata")


class NotificationDispatcher:
    """Base notification dispatcher interface for email, Telegram, or webhooks."""
    def send(self, alert: Dict[str, Any]) -> bool:
        logger.info(f"[Notification Stub] Alert: {alert['severity']} - {alert['message']}")
        return True


class AlertEngine:
    """Evaluates rule-based thresholds on fresh readings and persists alerts to database."""

    PM25_CRITICAL_THRESHOLD = 60.0  # µg/m³
    PM25_SURGE_PERCENTAGE = 30.0    # % rise over 3 hours
    STALE_DATA_THRESHOLD_HOURS = 2.0
    LOW_WIND_THRESHOLD_MS = 2.0     # 2 m/s = 7.2 km/h

    def __init__(self, session: Session, dispatcher: Optional[NotificationDispatcher] = None):
        self.session = session
        self.dispatcher = dispatcher or NotificationDispatcher()

    def evaluate_rules_for_location(
        self,
        location: Location,
        latest_aq: Optional[AirQualityReading],
        latest_w: Optional[WeatherReading],
        pm25_pct_change_3h: float
    ) -> List[Alert]:
        """Runs the rule checks for a single location and saves triggered alerts."""
        triggered: List[Alert] = []
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        now_ist = datetime.now(IST).replace(tzinfo=None)

        if not latest_aq:
            return triggered

        loc_name = location.location_name
        loc_id = location.location_id

        # Rule 1: AQI Category becomes Poor or Very Poor
        if latest_aq.openweather_aqi in [4, 5]:
            category = "Poor" if latest_aq.openweather_aqi == 4 else "Very Poor"
            msg = f"Air quality in {loc_name} reached {category} (OpenWeather AQI: {latest_aq.openweather_aqi})."
            alert = Alert(
                location_id=loc_id,
                alert_type="AQI_CATEGORY_POOR",
                severity="CRITICAL" if latest_aq.openweather_aqi == 5 else "WARNING",
                message=msg,
                triggered_at_utc=now_utc,
                triggered_at_ist=now_ist,
                is_active=True
            )
            triggered.append(alert)

        # Rule 2: PM2.5 rises by more than 30% in 3 hours
        if pm25_pct_change_3h > self.PM25_SURGE_PERCENTAGE:
            msg = f"Air quality is deteriorating rapidly: PM2.5 surged by {pm25_pct_change_3h:.1f}% in the last 3 hours in {loc_name}."
            alert = Alert(
                location_id=loc_id,
                alert_type="PM25_RAPID_SURGE",
                severity="WARNING",
                message=msg,
                triggered_at_utc=now_utc,
                triggered_at_ist=now_ist,
                is_active=True
            )
            triggered.append(alert)

        # Rule 3: PM2.5 crosses critical threshold
        if latest_aq.pm2_5 and latest_aq.pm2_5 >= self.PM25_CRITICAL_THRESHOLD:
            msg = f"High particulate matter: PM2.5 reached {latest_aq.pm2_5:.1f} µg/m³ (Threshold: {self.PM25_CRITICAL_THRESHOLD} µg/m³) in {loc_name}."
            alert = Alert(
                location_id=loc_id,
                alert_type="PM25_THRESHOLD_EXCEEDED",
                severity="WARNING",
                message=msg,
                triggered_at_utc=now_utc,
                triggered_at_ist=now_ist,
                is_active=True
            )
            triggered.append(alert)

        # Rule 4: Stagnant air / Low wind speed (< 7.2 km/h) while PM2.5 is rising
        if latest_w and latest_w.wind_speed_kph is not None:
            if latest_w.wind_speed_kph < (self.LOW_WIND_THRESHOLD_MS * 3.6) and pm25_pct_change_3h > 10.0:
                msg = f"Atmospheric stagnation in {loc_name}: Low wind ({latest_w.wind_speed_kph:.1f} km/h) is trapping rising PM2.5 (+{pm25_pct_change_3h:.1f}% in 3h)."
                alert = Alert(
                    location_id=loc_id,
                    alert_type="STAGNANT_AIR_INVERSION",
                    severity="INFO",
                    message=msg,
                    triggered_at_utc=now_utc,
                    triggered_at_ist=now_ist,
                    is_active=True
                )
                triggered.append(alert)

        # Rule 5: No update for more than 2 hours
        age_hours = (now_utc - latest_aq.observed_at_utc).total_seconds() / 3600.0
        if age_hours > self.STALE_DATA_THRESHOLD_HOURS:
            msg = f"Telemetry alert: No new air quality reading for {loc_name} in {age_hours:.1f} hours."
            alert = Alert(
                location_id=loc_id,
                alert_type="STALE_DATA_WARNING",
                severity="WARNING",
                message=msg,
                triggered_at_utc=now_utc,
                triggered_at_ist=now_ist,
                is_active=True
            )
            triggered.append(alert)

        # Persist and dispatch
        for al in triggered:
            self.session.add(al)
            self.dispatcher.send({
                "location_id": al.location_id,
                "severity": al.severity,
                "message": al.message,
                "triggered_at_ist": al.triggered_at_ist.isoformat(),
            })

        self.session.commit()
        return triggered
