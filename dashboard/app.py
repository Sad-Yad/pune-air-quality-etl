"""Streamlit Dashboard for Pune Air Quality & Weather Intelligence.
Plain, functional, accessible layout avoiding neon/glass aesthetics.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Ensure project root is in sys.path when running from Streamlit Cloud
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import text

from src.load.database import get_db_session, init_db
from src.analytics.trends import (
    get_latest_readings_all_locations,
    calculate_city_metrics,
    calculate_location_trends,
    analyze_weather_pollution_context,
    find_outdoor_and_avoidance_windows
)

# Page configuration
st.set_page_config(
    page_title="Pune Air Quality & Weather Intelligence",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Minimal, clean CSS styling: standard fonts, crisp borders, plain background
st.markdown("""
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    }
    .status-card {
        padding: 12px 16px;
        margin-bottom: 14px;
        border: 1px solid #d0d7de;
        border-radius: 4px;
        background-color: #f6f8fa;
    }
    .advisory-good {
        border-left: 5px solid #2da44e;
        color: #1a7f37;
    }
    .advisory-moderate {
        border-left: 5px solid #d4a72c;
        color: #9a6700;
    }
    .advisory-poor {
        border-left: 5px solid #cf222e;
        color: #cf222e;
    }
    .metric-box {
        border: 1px solid #e1e4e8;
        border-radius: 4px;
        padding: 10px;
        background: #ffffff;
        text-align: center;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 20px;
        font-weight: 600;
        margin-top: 4px;
        color: #24292f;
    }
    .metric-label {
        font-size: 12px;
        color: #57606a;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def load_all_latest():
    init_db()
    with get_db_session() as session:
        return get_latest_readings_all_locations(session)


@st.cache_data(ttl=60)
def load_history(location_id: str, days: int = 7):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    query = text("""
        SELECT 
            aq.observed_at_ist,
            aq.pm2_5,
            aq.pm10,
            aq.openweather_aqi,
            aq.aqi_category,
            w.temperature_c,
            w.humidity_pct,
            w.wind_speed_kph
        FROM air_quality_readings aq
        LEFT JOIN weather_readings w 
            ON aq.location_id = w.location_id 
            AND aq.observed_at_utc = w.observed_at_utc
        WHERE aq.location_id = :loc_id
          AND aq.observed_at_utc >= :cutoff
        ORDER BY aq.observed_at_utc ASC
    """)
    with get_db_session() as session:
        df = pd.read_sql(query, session.bind, params={"loc_id": location_id, "cutoff": cutoff})
    return df


@st.cache_data(ttl=60)
def load_recent_alerts(limit: int = 15):
    query = text("""
        SELECT 
            a.triggered_at_ist,
            l.location_name,
            a.severity,
            a.alert_type,
            a.message
        FROM alerts a
        JOIN locations l ON a.location_id = l.location_id
        ORDER BY a.triggered_at_utc DESC
        LIMIT :limit
    """)
    with get_db_session() as session:
        return pd.read_sql(query, session.bind, params={"limit": limit})


# Application Header
st.title("Pune Air Quality & Weather Intelligence")
st.caption("Real-time environmental monitoring, hourly analytics, and outdoor activity intelligence across Pune.")

df_latest = load_all_latest()

if df_latest.empty or df_latest["observed_at_ist"].dropna().empty:
    st.warning("No data found in database. Run ingestion using `python -m src.pipeline --once` to fetch current readings.")
    st.stop()

# Sidebar: Controls & City Metrics
st.sidebar.header("Station & Controls")
locations_map = dict(zip(df_latest["location_name"], df_latest["location_id"]))
selected_loc_name = st.sidebar.selectbox("Select Monitoring Station", options=list(locations_map.keys()))
selected_loc_id = locations_map[selected_loc_name]

# Filter selected row
loc_row = df_latest[df_latest["location_id"] == selected_loc_id].iloc[0]

# City Averages Sidebar Summary
city_stats = calculate_city_metrics(df_latest)
st.sidebar.markdown("---")
st.sidebar.subheader("Pune City Summary")
col_s1, col_s2 = st.sidebar.columns(2)
col_s1.metric("City Avg PM2.5", f"{city_stats['city_avg_pm25']} µg/m³" if city_stats['city_avg_pm25'] else "N/A")
col_s2.metric("City Avg AQI", f"{city_stats['city_avg_aqi']}" if city_stats['city_avg_aqi'] else "N/A")

# Data Freshness Indicator
last_obs_ist = loc_row["observed_at_ist"]
if pd.notnull(last_obs_ist):
    if isinstance(last_obs_ist, str):
        obs_dt = pd.to_datetime(last_obs_ist)
    else:
        obs_dt = last_obs_ist
    freshness_str = obs_dt.strftime("%d %b %Y, %I:%M %p IST")
else:
    freshness_str = "Unknown"

# Fetch trends & context for selected location
with get_db_session() as session:
    trends = calculate_location_trends(session, selected_loc_id)
    windows = find_outdoor_and_avoidance_windows(session, selected_loc_id)

stagnation = analyze_weather_pollution_context(
    loc_row.get("wind_speed_kph"),
    loc_row.get("humidity_pct"),
    trends.get("pct_change_3h_pm2_5")
)

# Advisory Banner
aqi_num = loc_row.get("openweather_aqi")
pm25_val = loc_row.get("pm2_5")
pct_change = trends.get("pct_change_3h_pm2_5", 0.0)

if aqi_num in [4, 5] or (pm25_val and pm25_val > 60):
    advisory_class = "advisory-poor"
    advisory_title = "Avoid prolonged outdoor exposure"
    advisory_text = f"Air quality is poor in {selected_loc_name}. Sensitive groups, joggers, and children should limit outdoor physical exertion."
elif pct_change > 25.0:
    advisory_class = "advisory-moderate"
    advisory_title = "Air quality is deteriorating rapidly"
    advisory_text = f"PM2.5 has risen by +{pct_change:.1f}% over the past 3 hours. Exercise caution if planning extended outdoor activities."
else:
    advisory_class = "advisory-good"
    advisory_title = "Good window for outdoor activity"
    advisory_text = f"Environmental parameters in {selected_loc_name} are currently favorable for walking, commuting, and standard outdoor routines."

st.markdown(f"""
<div class="status-card {advisory_class}">
    <strong>{advisory_title}</strong><br/>
    <span style="font-size: 14px;">{advisory_text}</span><br/>
    <span style="font-size: 12px; color: #57606a;">Last updated: {freshness_str}</span>
</div>
""", unsafe_allow_html=True)

# Key Metrics Row
col1, col2, col3, col4, col5, col6 = st.columns(6)

def metric_card(col, label, value, subtext=""):
    with col:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div style="font-size: 11px; color: #57606a; margin-top:2px;">{subtext}</div>
        </div>
        """, unsafe_allow_html=True)

aqi_cat = loc_row.get("aqi_category") or "N/A"
trend_arrow = "↑" if pct_change > 5 else ("↓" if pct_change < -5 else "→")

metric_card(col1, "AQI Index", f"{aqi_num or 'N/A'}", f"Category: {aqi_cat}")
metric_card(col2, "PM2.5", f"{pm25_val:.1f} µg/m³" if pd.notnull(pm25_val) else "N/A", f"3h Trend: {trend_arrow} {pct_change:+.1f}%")
metric_card(col3, "PM10", f"{loc_row['pm10']:.1f} µg/m³" if pd.notnull(loc_row.get("pm10")) else "N/A", "Particulate")
metric_card(col4, "Temperature", f"{loc_row['temperature_c']:.1f} °C" if pd.notnull(loc_row.get("temperature_c")) else "N/A", f"Feels like: {loc_row.get('feels_like_c', 'N/A')}°C")
metric_card(col5, "Humidity", f"{loc_row['humidity_pct']:.0f} %" if pd.notnull(loc_row.get("humidity_pct")) else "N/A", "Relative")
metric_card(col6, "Wind Speed", f"{loc_row['wind_speed_kph']:.1f} km/h" if pd.notnull(loc_row.get("wind_speed_kph")) else "N/A", f"Dir: {loc_row.get('wind_direction_deg', 'N/A')}°")

st.markdown("<br/>", unsafe_allow_html=True)

# Tabs for Structured Exploration
tab1, tab2, tab3, tab4 = st.tabs([
    "Trends & Outdoor Window",
    "City Comparison",
    "Weather-Pollution Context",
    "Alerts & Health Logs"
])

with tab1:
    col_t1, col_t2 = st.columns([2, 1])
    with col_t2:
        st.subheader("Action Recommendations")
        st.write(f"**Best time to be outdoors today:**\n\n{windows['best_window']}")
        st.write(f"**Avoid outdoor exposure:**\n\n{windows['avoidance_window']}")
        st.write(f"**Atmospheric Context:**\n\n{stagnation['explanation']}")

    with col_t1:
        st.subheader("24-Hour PM2.5 & AQI Telemetry")
        df_hist = load_history(selected_loc_id, days=1)
        if not df_hist.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(df_hist["observed_at_ist"]),
                y=df_hist["pm2_5"],
                name="PM2.5 (µg/m³)",
                line=dict(color="#24292f", width=2)
            ))
            fig.add_hline(y=60, line_dash="dash", line_color="#cf222e", annotation_text="Poor Threshold (60 µg/m³)")
            fig.update_layout(
                margin=dict(l=20, r=20, t=30, b=20),
                height=300,
                xaxis_title="Time (IST)",
                yaxis_title="PM2.5 (µg/m³)",
                template="simple_white"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Collecting 24-hour telemetry... Historical readings will render here.")

    st.subheader("7-Day PM2.5 Progression")
    df_week = load_history(selected_loc_id, days=7)
    if not df_week.empty:
        fig_week = px.line(
            df_week,
            x="observed_at_ist",
            y="pm2_5",
            labels={"observed_at_ist": "Date & Time (IST)", "pm2_5": "PM2.5 (µg/m³)"},
            template="simple_white"
        )
        fig_week.update_layout(height=260, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_week, use_container_width=True)
    else:
        st.info("7-day trend requires accumulating continuous data.")

with tab2:
    st.subheader("Pune Stations Comparison")
    df_comp = df_latest.dropna(subset=["pm2_5"]).sort_values("pm2_5", ascending=True)
    if not df_comp.empty:
        fig_comp = px.bar(
            df_comp,
            x="pm2_5",
            y="location_name",
            orientation="h",
            labels={"pm2_5": "Current PM2.5 (µg/m³)", "location_name": "Location"},
            color="openweather_aqi",
            color_continuous_scale=["#2da44e", "#d4a72c", "#cf222e"],
            template="simple_white"
        )
        fig_comp.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_comp, use_container_width=True)
    
    st.dataframe(
        df_latest[[
            "location_name", "openweather_aqi", "aqi_category", "pm2_5", "pm10",
            "temperature_c", "humidity_pct", "wind_speed_kph"
        ]].rename(columns={
            "location_name": "Station",
            "openweather_aqi": "AQI",
            "aqi_category": "Category",
            "pm2_5": "PM2.5 (µg/m³)",
            "pm10": "PM10 (µg/m³)",
            "temperature_c": "Temp (°C)",
            "humidity_pct": "Humidity (%)",
            "wind_speed_kph": "Wind (km/h)"
        }),
        use_container_width=True,
        hide_index=True
    )

with tab3:
    st.subheader("Weather & Pollution Dynamics")
    st.write(
        "Low wind speeds (< 7.2 km/h / 2 m/s) coupled with high humidity reduce atmospheric mixing, "
        "often trapping vehicular and industrial exhaust near ground level."
    )
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        st.metric("Current Wind Speed", f"{loc_row.get('wind_speed_kph', 'N/A')} km/h", 
                  "Below 7.2 km/h traps pollutants" if (loc_row.get('wind_speed_kph') or 0) < 7.2 else "Adequate dispersion")
    with col_w2:
        st.metric("Current Humidity", f"{loc_row.get('humidity_pct', 'N/A')} %",
                  "High humidity favors aerosol formation" if (loc_row.get('humidity_pct') or 0) > 70 else "Normal")

with tab4:
    st.subheader("System Alerts & Diagnostics")
    df_alerts = load_recent_alerts(limit=20)
    if not df_alerts.empty:
        st.dataframe(
            df_alerts.rename(columns={
                "triggered_at_ist": "Time (IST)",
                "location_name": "Location",
                "severity": "Severity",
                "alert_type": "Alert Type",
                "message": "Description"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No active alerts triggered yet. System operating within normal thresholds.")
###  