import streamlit as st
import pandas as pd
import altair as alt
import time
from datetime import datetime

# --- CONFIG ---
RATE_PER_KWH = 0.15

st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

conn = st.connection("neon", type="sql")

# --- SESSION STATE ---
if "time_window" not in st.session_state:
    st.session_state.time_window = "15m"

# --- TIME OPTIONS ---
time_map = {
    "5m": "INTERVAL '5 minutes'",
    "15m": "INTERVAL '15 minutes'",
    "1h": "INTERVAL '1 hour'",
    "6h": "INTERVAL '6 hours'",
    "24h": "INTERVAL '24 hours'"
}

# --- GLOBAL TIME SELECTOR ---
cols = st.columns(len(time_map))
for i, key in enumerate(time_map.keys()):
    if cols[i].button(key, use_container_width=True):
        st.session_state.time_window = key

interval_sql = time_map[st.session_state.time_window]

# --- QUERY (SMART, FILTERED) ---
try:
    readings = conn.query(f"""
        SELECT timestamp, voltage, current, power, total_energy
        FROM public.readings
        WHERE timestamp >= NOW() - {interval_sql}
        ORDER BY timestamp ASC;
    """, ttl=1)

    latest = conn.query("""
        SELECT voltage, current, power, total_energy
        FROM public.readings
        ORDER BY timestamp DESC
        LIMIT 1;
    """, ttl=1)

    alerts = conn.query("""
        SELECT id, description, time_stamp
        FROM public.alerts
        ORDER BY time_stamp DESC
        LIMIT 50;
    """, ttl=5)

    daily = conn.query("""
        SELECT total_energy
        FROM public.readings
        WHERE DATE(timestamp) = CURRENT_DATE
        ORDER BY timestamp DESC
        LIMIT 1;
    """, ttl=2)

except Exception as e:
    st.error(f"DB error: {e}")
    st.stop()

if readings.empty or latest.empty:
    st.info("Waiting for data...")
    st.stop()

# --- FORMAT ---
readings["timestamp"] = pd.to_datetime(readings["timestamp"])
alerts["time_stamp"] = pd.to_datetime(alerts["time_stamp"])

latest = latest.iloc[0]

# --- LIVE METRICS ---
c1, c2, c3 = st.columns(3)
c1.metric("Voltage", f"{latest['voltage']:.2f} V")
c2.metric("Current", f"{latest['current']:.2f} A")
c3.metric("Power", f"{latest['power']:.2f} W")

st.write("---")

# --- CHART FUNCTION ---
def make_chart(df, col, title, color):
    return alt.Chart(df).mark_line(color=color).encode(
        x=alt.X('timestamp:T', title="Time"),
        y=alt.Y(f'{col}:Q', scale=alt.Scale(zero=False))
    ).properties(height=250, title=title)

# --- GRAPHS ---
g1, g2 = st.columns(2)

with g1:
    st.altair_chart(make_chart(readings, "voltage", "Voltage (V)", "#7eb451"), use_container_width=True)
    st.altair_chart(make_chart(readings, "power", "Power (W)", "#ff4b4b"), use_container_width=True)

with g2:
    st.altair_chart(make_chart(readings, "current", "Current (A)", "#fb8500"), use_container_width=True)
    st.altair_chart(make_chart(readings, "total_energy", "Energy (Wh)", "#023e8a"), use_container_width=True)

# --- DAILY METRICS ---
st.write("---")

daily_energy = daily.iloc[0]["total_energy"] if not daily.empty else 0
daily_cost = (daily_energy / 1000.0) * RATE_PER_KWH

m1, m2 = st.columns(2)

m1.markdown(f"""
<div style="text-align:center; padding:20px; background-color: rgba(2,62,138,0.1); border-radius:10px;">
<h3>Today's Energy</h3>
<h1 style="color:#023e8a;">{daily_energy:.2f} Wh</h1>
</div>
""", unsafe_allow_html=True)

m2.markdown(f"""
<div style="text-align:center; padding:20px; background-color: rgba(42,157,143,0.1); border-radius:10px;">
<h3>Today's Cost</h3>
<h1 style="color:#2a9d8f;">${daily_cost:.4f}</h1>
</div>
""", unsafe_allow_html=True)

# --- ALERTS (SCROLLABLE + TRUNCATED) ---
st.write("---")
st.subheader("🚨 Alerts")

alert_container = st.container()

with alert_container:
    st.markdown("""
    <div style="max-height:300px; overflow-y:auto;">
    """, unsafe_allow_html=True)

    for i, row in alerts.iterrows():
        msg = row["description"][:80] + ("..." if len(row["description"]) > 80 else "")
        time_str = row["time_stamp"].strftime("%Y-%m-%d %H:%M:%S")

        col1, col2 = st.columns([6,1])
        with col1:
            st.markdown(f"**{time_str}** — {msg}")
        with col2:
            if st.button("X", key=f"del_{row['id']}"):
                conn.query(f"DELETE FROM alerts WHERE id = '{row['id']}'", ttl=0)
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# --- DOWNLOAD (SMART MERGE) ---
st.write("---")

download_df = conn.query("""
    SELECT r.timestamp, r.voltage, r.current, r.power, r.total_energy
    FROM public.readings r
    WHERE timestamp >= NOW() - INTERVAL '24 hours'
    ORDER BY timestamp ASC;
""", ttl=10)

csv = download_df.to_csv(index=False).encode()

st.download_button(
    "Download Last 24h Data",
    csv,
    "energy_data.csv",
    "text/csv"
)

# --- AUTO REFRESH (NO HARD FLICKER) ---
time.sleep(1)
st.experimental_rerun()