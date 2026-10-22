"""Browser-based Streamlit edition of Nexus TMS.

This is kept separate from start_project.py, which remains the Windows desktop app.
"""
from __future__ import annotations

import math
import os
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(page_title="Nexus TMS", page_icon="🚦", layout="wide")
ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("TRAFFIC_DB_PATH", ROOT / "traffic_control.db"))
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
.stApp { background: radial-gradient(ellipse at 8% 0%, #122743 0, #091321 42%, #080f19 100%); color: #e8f0fa; }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -.035em; }
h1 { color: #f5f9ff; font-size: 2.45rem !important; }
[data-testid="stMetric"] { background: linear-gradient(145deg, rgba(19,39,62,.96), rgba(12,25,41,.96)); border: 1px solid #203854; padding: 18px 20px; border-radius: 16px; box-shadow: 0 10px 28px rgba(0,0,0,.16); }
[data-testid="stMetricLabel"] { color: #98adc4; }
[data-testid="stMetricValue"] { color: #f2f7fd; }
[data-testid="stTabs"] button { color: #93a8bf; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #54d6c3; }
[data-testid="stSidebar"] { background: #0b1726; border-right: 1px solid #1e334b; }
[data-testid="stDataFrame"] { border: 1px solid #203854; border-radius: 12px; overflow: hidden; }
div.stButton > button { background: linear-gradient(90deg,#13a996,#1689c5); color: white; border: 0; border-radius: 10px; font-weight: 700; }
div.stButton > button:hover { border: 0; color: white; filter: brightness(1.12); }
</style>
""", unsafe_allow_html=True)

SEED_ROADS = [
    ("RD-01", "Inner Ring Road (AIIMS - Lajpat Nagar)", "South Corridor", 6.8, 60, 1200, 28.5672, 77.2100, 28.5685, 77.2260, 28.5695, 77.2430, 940, 880, 22.5, 78.3, "Heavy"),
    ("RD-02", "Connaught Outer Circle", "Central Hub", 4.2, 50, 900, 28.6328, 77.2197, 28.6304, 77.2167, 28.6345, 77.2230, 580, 540, 31.0, 64.4, "Moderate"),
    ("RD-03", "Sardar Patel Marg (Dhaula Kuan)", "West Express", 5.5, 70, 1100, 28.5921, 77.1650, 28.5985, 77.1780, 28.6040, 77.1920, 830, 810, 26.0, 75.5, "Heavy"),
    ("RD-04", "India Gate - Kartavya Path", "Central Hub", 3.4, 50, 800, 28.6129, 77.2295, 28.6135, 77.2180, 28.6143, 77.2050, 260, 290, 44.0, 32.5, "Smooth"),
    ("RD-05", "ITO Vikas Marg Crossing", "East Bridge", 4.9, 60, 1300, 28.6280, 77.2410, 28.6305, 77.2560, 28.6330, 77.2720, 1020, 960, 19.5, 78.5, "Heavy"),
    ("RD-06", "Barapullah Elevated Corridor", "South-East", 7.5, 70, 1400, 28.5890, 77.2320, 28.5820, 77.2460, 28.5750, 77.2590, 490, 510, 58.0, 35.0, "Smooth"),
    ("RD-07", "Aurobindo Marg (Green Park)", "South Corridor", 5.1, 60, 950, 28.5672, 77.2100, 28.5530, 77.2060, 28.5390, 77.2010, 510, 495, 36.5, 53.7, "Moderate"),
    ("RD-08", "Mathura Road (Pragati Maidan)", "Central-East", 6.0, 60, 1150, 28.6280, 77.2410, 28.6090, 77.2425, 28.5890, 77.2320, 610, 630, 39.0, 53.0, "Moderate"),
]


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def initialise():
    with connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS roads (
                road_id TEXT PRIMARY KEY, name TEXT NOT NULL, zone TEXT NOT NULL,
                length_km REAL NOT NULL, speed_limit INTEGER NOT NULL, capacity INTEGER NOT NULL,
                start_lat REAL NOT NULL, start_lon REAL NOT NULL, mid_lat REAL NOT NULL,
                mid_lon REAL NOT NULL, end_lat REAL NOT NULL, end_lon REAL NOT NULL,
                current_vehicles INTEGER DEFAULT 0, prev_vehicles INTEGER DEFAULT 0,
                avg_speed REAL DEFAULT 50, congestion_pct REAL DEFAULT 25,
                status TEXT DEFAULT 'Smooth', updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS traffic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, road_id TEXT NOT NULL,
                road_name TEXT NOT NULL, timestamp TEXT NOT NULL, date_str TEXT NOT NULL,
                hour INTEGER NOT NULL, day_of_week INTEGER NOT NULL, vehicle_count INTEGER NOT NULL,
                avg_speed REAL NOT NULL, congestion_pct REAL NOT NULL, status TEXT NOT NULL,
                is_simulated INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, severity TEXT NOT NULL,
                category TEXT NOT NULL, road_name TEXT NOT NULL, message TEXT NOT NULL,
                lat REAL, lon REAL, timestamp TEXT NOT NULL, active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS cameras (
                cam_id TEXT PRIMARY KEY, name TEXT NOT NULL, road_id TEXT NOT NULL,
                location_desc TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
                status TEXT NOT NULL, is_live_stream INTEGER DEFAULT 0, stream_url TEXT DEFAULT ''
            );
        """)
        if con.execute("SELECT COUNT(*) FROM roads").fetchone()[0] == 0:
            now = datetime.now()
            for road in SEED_ROADS:
                con.execute("INSERT INTO roads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*road, now.strftime("%Y-%m-%d %H:%M:%S")))
            hist = []
            for day in range(6, -1, -1):
                d = now - timedelta(days=day)
                for hour in range(24):
                    peak = math.exp(-.5*((hour-9)/1.8)**2) + math.exp(-.5*((hour-18)/2.2)**2)
                    for road in SEED_ROADS:
                        ratio = max(.08, min(.96, .18 + .38*peak + ((int(road[0][-1]) % 4)-1.5)*.045))
                        cong = round(ratio*100, 1)
                        speed = round(max(10, road[4]*(1-.72*ratio)), 1)
                        status = "Heavy" if cong >= 70 else "Moderate" if cong >= 45 else "Smooth"
                        ts = d.replace(hour=hour, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
                        hist.append((road[0], road[1], ts, d.strftime("%Y-%m-%d"), hour, d.weekday(), int(road[5]*ratio), speed, cong, status, 1))
            con.executemany("INSERT INTO traffic_history (road_id,road_name,timestamp,date_str,hour,day_of_week,vehicle_count,avg_speed,congestion_pct,status,is_simulated) VALUES (?,?,?,?,?,?,?,?,?,?,?)", hist)
            for alert in [
                ("CRITICAL", "Heavy Traffic", SEED_ROADS[4][1], "Congestion is high on the eastbound corridor. Allow extra travel time.", 28.628, 77.241),
                ("WARNING", "Roadwork", SEED_ROADS[2][1], "Roadwork may reduce capacity near the Dhaula Kuan loop.", 28.5985, 77.178),
                ("INFO", "Traffic Advisory", SEED_ROADS[1][1], "Traffic is moving at moderate speed around Connaught Place.", 28.6328, 77.2197),
            ]:
                con.execute("INSERT INTO alerts (severity,category,road_name,message,lat,lon,timestamp,active) VALUES (?,?,?,?,?,?,?,1)", (*alert, now.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()


def query_df(sql, params=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


def tomtom_key():
    """Read a key from Streamlit secrets or the local environment; never display it."""
    try:
        secret = st.secrets.get("TOMTOM_API_KEY", "")
    except Exception:
        secret = ""
    return str(secret or os.environ.get("TOMTOM_API_KEY", "")).strip()


def refresh_live_traffic(api_key):
    """Fetch TomTom flow for each configured road and persist successful readings."""
    roads_now = query_df("SELECT * FROM roads ORDER BY road_id")
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    successes, failures = 0, []
    with connect() as con:
        for road in roads_now.to_dict("records"):
            try:
                response = requests.get(
                    "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json",
                    params={"point": f"{road['mid_lat']},{road['mid_lon']}", "unit": "KMPH", "key": api_key},
                    timeout=8,
                )
                if response.status_code in (401, 403):
                    raise ValueError("TomTom rejected the API key (HTTP 401/403). Check that Traffic Flow API access is enabled.")
                response.raise_for_status()
                flow = response.json().get("flowSegmentData", {})
                speed = float(flow["currentSpeed"])
                free_speed = max(15.0, float(flow.get("freeFlowSpeed", road["speed_limit"])))
                current_tt = float(flow.get("currentTravelTime", 100.0))
                free_tt = max(10.0, float(flow.get("freeFlowTravelTime", 80.0)))
                if flow.get("roadClosure", False):
                    congestion, speed = 98.0, 5.0
                else:
                    speed_drop = max(0.0, 1 - speed / free_speed)
                    time_delay = max(0.0, (current_tt - free_tt) / max(1.0, current_tt))
                    congestion = round(max(8.0, min(97.0, (0.65 * speed_drop + 0.35 * time_delay) * 100 + 14)), 1)
                vehicles = int(road["capacity"] * congestion / 100)
                status = "Heavy" if congestion >= 70 else "Moderate" if congestion >= 45 else "Smooth"
                con.execute("UPDATE roads SET prev_vehicles=current_vehicles,current_vehicles=?,avg_speed=?,congestion_pct=?,status=?,updated_at=? WHERE road_id=?", (vehicles, round(speed, 1), congestion, status, stamp, road["road_id"]))
                con.execute("INSERT INTO traffic_history (road_id,road_name,timestamp,date_str,hour,day_of_week,vehicle_count,avg_speed,congestion_pct,status,is_simulated) VALUES (?,?,?,?,?,?,?,?,?,?,0)", (road["road_id"], road["name"], stamp, now.strftime("%Y-%m-%d"), now.hour, now.weekday(), vehicles, round(speed, 1), congestion, status))
                successes += 1
            except requests.RequestException:
                # Request exception text can contain the full URL, including the API key.
                failures.append(f"{road['name']}: TomTom request failed. Check network access and API quota.")
            except Exception as exc:
                failures.append(f"{road['name']}: {exc}")
        con.commit()
    return successes, failures


initialise()
st.title("NEXUS / TRAFFIC CONTROL")
st.caption("DELHI NETWORK OPERATIONS  ·  REAL-TIME CORRIDOR INTELLIGENCE")

api_key = tomtom_key()
last_sync = None
if api_key:
    try:
        last_sync = query_df("SELECT MAX(updated_at) AS last_sync FROM roads").iloc[0]["last_sync"]
    except Exception:
        pass

roads = query_df("SELECT * FROM roads ORDER BY congestion_pct DESC")
if roads.empty:
    st.error("No road data found in the database.")
    st.stop()

with st.sidebar:
    st.header("Controls")
    zones = ["All zones"] + sorted(roads.zone.dropna().unique().tolist())
    zone = st.selectbox("Corridor", zones)
    threshold = st.slider("Heavy traffic alert threshold", 40, 95, 70)
    st.caption(f"Database: `{DB_PATH.name}`")
    if api_key:
        st.success("TomTom key configured")
        if st.button("↻  Sync live traffic", use_container_width=True):
            with st.spinner("Fetching TomTom flow for each corridor…"):
                ok_count, errors = refresh_live_traffic(api_key)
            if ok_count:
                st.success(f"Updated {ok_count} of {ok_count + len(errors)} corridors.")
            if errors:
                st.warning(errors[0])
            st.rerun()
        if last_sync:
            st.caption(f"Last road update: {last_sync}")
    else:
        st.info("TomTom live mode is ready once you add TOMTOM_API_KEY in Streamlit Secrets.")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

view = roads if zone == "All zones" else roads[roads.zone == zone]
heavy = int((view.congestion_pct >= threshold).sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Road corridors", len(view))
c2.metric("Average congestion", f"{view.congestion_pct.mean():.1f}%")
c3.metric("Heavy congestion", heavy)
c4.metric("Average speed", f"{view.avg_speed.mean():.1f} km/h")

tab_overview, tab_map, tab_history, tab_alerts, tab_routes = st.tabs(["Overview", "Live map", "History", "Alerts", "Route planner"])
with tab_overview:
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Road status")
        st.dataframe(view[["road_id", "name", "zone", "current_vehicles", "avg_speed", "congestion_pct", "status"]].rename(columns={"road_id":"ID", "name":"Road", "zone":"Zone", "current_vehicles":"Vehicles", "avg_speed":"Speed km/h", "congestion_pct":"Congestion %", "status":"Status"}), hide_index=True, use_container_width=True)
    with right:
        st.subheader("Congestion by road")
        chart = px.bar(view.sort_values("congestion_pct"), x="congestion_pct", y="name", color="status", orientation="h", color_discrete_map={"Smooth":"#10b981", "Moderate":"#f59e0b", "Heavy":"#ef4444"}, labels={"congestion_pct":"Congestion (%)", "name":""})
        chart.update_layout(height=380, margin=dict(l=5,r=5,t=10,b=5), legend_title_text="Status")
        st.plotly_chart(chart, use_container_width=True)
with tab_map:
    st.subheader("Road corridors")
    st.caption("Markers show road midpoints; select a corridor in the sidebar to filter the map.")
    st.map(view.rename(columns={"mid_lat":"lat", "mid_lon":"lon"})[["lat", "lon"]], zoom=10)
    st.dataframe(view[["name", "zone", "mid_lat", "mid_lon", "status"]].rename(columns={"name":"Road", "zone":"Zone", "mid_lat":"Latitude", "mid_lon":"Longitude", "status":"Status"}), hide_index=True, use_container_width=True)
with tab_history:
    st.subheader("Traffic history")
    history = query_df("SELECT timestamp, road_name, vehicle_count, avg_speed, congestion_pct, status FROM traffic_history ORDER BY timestamp")
    if history.empty:
        st.info("History is empty. The included demo database is seeded automatically on first run.")
    else:
        history = history[history.road_name.isin(view.name)]
        roads_pick = st.multiselect("Roads", sorted(history.road_name.unique()), default=sorted(history.road_name.unique())[:3])
        history = history[history.road_name.isin(roads_pick)]
        history["timestamp"] = pd.to_datetime(history.timestamp, errors="coerce")
        if not history.empty:
            fig = px.line(history, x="timestamp", y="congestion_pct", color="road_name", labels={"timestamp":"Time", "congestion_pct":"Congestion (%)", "road_name":"Road"})
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(history.sort_values("timestamp", ascending=False).head(100), hide_index=True, use_container_width=True)
with tab_alerts:
    st.subheader("Active alerts")
    alerts = query_df("SELECT severity, category, road_name, message, timestamp FROM alerts WHERE active=1 ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, timestamp DESC")
    if alerts.empty:
        st.success("No active alerts.")
    else:
        st.dataframe(alerts.rename(columns={"severity":"Severity", "category":"Category", "road_name":"Road", "message":"Details", "timestamp":"Reported"}), hide_index=True, use_container_width=True)
with tab_routes:
    st.subheader("Route planner")
    origins = ["Dhaula Kuan", "Connaught Place", "AIIMS Flyover", "India Gate", "ITO Crossing", "Lajpat Nagar", "Pragati Maidan", "Nizamuddin Bridge"]
    a, b = st.columns(2)
    origin = a.selectbox("From", origins, index=0)
    dest = b.selectbox("To", origins, index=4)
    if origin == dest:
        st.info("Choose two different locations to compare routes.")
    else:
        route_roads = view.sort_values("congestion_pct")
        for i, row in enumerate(route_roads.head(3).itertuples(), 1):
            base_km = 5.0 + abs(origins.index(origin)-origins.index(dest))*1.4
            distance = base_km * (1 + (i-1)*.13)
            speed = max(12, row.avg_speed)
            minutes = distance/speed*60
            st.info(f"**Option {i}: {row.name}** · {distance:.1f} km · about {minutes:.0f} min · {row.congestion_pct:.0f}% congestion")

st.divider()
st.caption("When TomTom is configured, use **Sync live traffic** to fetch current corridor readings. Otherwise the dashboard shows the included demo data.")
