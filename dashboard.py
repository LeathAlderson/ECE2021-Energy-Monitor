import streamlit as st
import pandas as pd
import altair as alt
import time
from datetime import datetime, timedelta

# --- CONFIG ---
RATE_PER_KWH = 0.15  # adjust if needed

st.set_page_config(page_title="Energy Monitor", layout="wide")
st.title("⚡ Energy Monitor")

conn = st.connection("neon", type="sql")

# --- SESSION STATE ---
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = datetime.now().date()

if "time_windows" not in st.session_state:
    st.session_state.time_windows = {
        "voltage": "15m",
        "current": "15m",
        "power": "15m"
    }

# --- HELPERS ---
def safe_tz(df, col):
    try:
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert('America/Moncton')
    except:
        df[col] = pd.to_datetime(df[col])
    return df

def make_chart(data, y, title):
    return alt.Chart(data).mark_line().encode(
        x='timestamp:T',
        y=alt.Y(f'{y}:Q', scale=alt.Scale(zero=False))
    ).properties(height=250, title=title)

def compute_power(df):
    df["power"] = df["voltage"] * df["current"]
    return df

def compute_daily_energy(df):
    df = df.sort_values("timestamp")
    df["dt"] = df["timestamp"].diff().dt.total_seconds().fillna(0)
    df["energy"] = (df["power"] * df["dt"]) / 3600.0  # Wh
    return df["energy"].sum()

# --- FETCH DATA ---
try:
    readings = conn.query("SELECT * FROM readings ORDER BY timestamp DESC LIMIT 10000;", ttl=0)
    alerts = conn.query("SELECT * FROM alerts ORDER BY time_stamp DESC;", ttl=0)
    history = conn.query("SELECT * FROM daily_history ORDER BY date DESC;", ttl=0)
except Exception as e:
    st.error(f"DB error: {e}")
    st.stop()

if readings.empty:
    st.info("Waiting for data...")
    st.stop()

# --- CLEAN DATA ---
readings = safe_tz(readings, "timestamp")
readings = compute_power(readings)
readings = readings.sort_values("timestamp")

latest = readings.iloc[-1]

# --- LIVE METRICS ---
c1, c2, c3 = st.columns(3)
c1.metric("Voltage", f"{latest['voltage']:.2f} V")
c2.metric("Current", f"{latest['current']:.2f} A")
c3.metric("Power", f"{latest['power']:.2f} W")

st.divider()

# --- GRAPH FILTER ---
def filter_time(df, key):
    mapping = {"5m":5, "15m":15, "1h":60, "6h":360, "24h":1440}
    mins = mapping[st.session_state.time_windows[key]]
    cutoff = df["timestamp"].max() - pd.Timedelta(minutes=mins)
    return df[df["timestamp"] >= cutoff]

def time_buttons(key):
    opts = ["5m", "15m", "1h", "6h", "24h"]
    cols = st.columns(len(opts))
    for i, o in enumerate(opts):
        if cols[i].button(o, key=f"{key}_{o}"):
            st.session_state.time_windows[key] = o

# --- GRAPHS ---
g1, g2 = st.columns(2)

with g1:
    time_buttons("voltage")
    st.altair_chart(make_chart(filter_time(readings, "voltage"), "voltage", "Voltage"), use_container_width=True)

    time_buttons("power")
    st.altair_chart(make_chart(filter_time(readings, "power"), "power", "Power"), use_container_width=True)

with g2:
    time_buttons("current")
    st.altair_chart(make_chart(filter_time(readings, "current"), "current", "Current"), use_container_width=True)

# --- DAILY ENERGY ---
today = readings[readings["timestamp"].dt.date == datetime.now().date()]
daily_energy = compute_daily_energy(today)
daily_cost = (daily_energy / 1000.0) * RATE_PER_KWH

# --- SAVE DAILY BEFORE RESET ---
now = datetime.now()

if now.date() != st.session_state.last_reset_date:
    try:
        conn.query(f"""
        INSERT INTO daily_history (date, total_energy, total_cost)
        VALUES ('{st.session_state.last_reset_date}', {daily_energy}, {daily_cost})
        ON CONFLICT (date)
        DO UPDATE SET
            total_energy = EXCLUDED.total_energy,
            total_cost = EXCLUDED.total_cost;
        """, ttl=0)
    except Exception as e:
        st.error(f"History save failed: {e}")

    st.session_state.last_reset_date = now.date()

# --- SUMMARY CARDS ---
m1, m2 = st.columns(2)

m1.metric("Today's Energy (Wh)", f"{daily_energy:.2f}")
m2.metric("Today's Cost ($)", f"{daily_cost:.4f}")

# --- ALERTS ---
st.divider()
st.subheader("Alerts")

if alerts.empty:
    st.success("No alerts")
else:
    for i, row in alerts.iterrows():
        col1, col2 = st.columns([6,1])
        with col1:
            st.write(f"{row['time_stamp']} — {row['description']}")
        with col2:
            if st.button("X", key=f"del_{i}"):
                conn.query(f"DELETE FROM alerts WHERE id = '{row['id']}'", ttl=0)
                st.rerun()

# --- DOWNLOAD (MERGED) ---
st.divider()

merged = readings.copy()

if not history.empty:
    history["date"] = pd.to_datetime(history["date"])
    merged["date"] = merged["timestamp"].dt.date
    merged = merged.merge(history, left_on="date", right_on="date", how="left")

csv = merged.to_csv(index=False).encode()

st.download_button(
    "Download Data",
    csv,
    "energy_data.csv",
    "text/csv"
)

# --- AUTO REFRESH ---
time.sleep(1)
st.rerun()