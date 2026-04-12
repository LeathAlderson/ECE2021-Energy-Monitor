import streamlit as st
import pandas as pd
import altair as alt
import time

RATE_PER_KWH = 0.15

st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

conn = st.connection("neon", type="sql")

# --- STATE ---
if "time_window" not in st.session_state:
    st.session_state.time_window = "24h"

# --- WINDOW MAP (VIEW ONLY, NO AGGREGATION) ---
window_map = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "6h": "6 hours",
    "24h": "24 hours"
}

window_seconds = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400
}

# --- BUTTONS WITH ACTIVE STATE ---
cols = st.columns(len(window_map))

for i, key in enumerate(window_map.keys()):
    active = st.session_state.time_window == key
    if cols[i].button(key, use_container_width=True, type="primary" if active else "secondary"):
        st.session_state.time_window = key
        st.rerun()

selected = st.session_state.time_window
interval = window_map[selected]

# --- DATA QUERY (RAW ONLY) ---
try:
    readings = conn.query(f"""
        SELECT timestamp, voltage, current, power, total_energy
        FROM public.readings
        WHERE timestamp >= NOW() - INTERVAL '{interval}'
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
        SELECT MAX(total_energy) as total_energy
        FROM public.readings
        WHERE DATE(timestamp) = CURRENT_DATE;
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

# --- CHART ---
def chart(df, col, title, color):
    return alt.Chart(df).mark_line(color=color).encode(
        x=alt.X("timestamp:T", title="Time"),
        y=alt.Y(f"{col}:Q", scale=alt.Scale(zero=False))
    ).properties(height=250, title=title)

# --- GRAPHS ---
g1, g2 = st.columns(2)

with g1:
    st.altair_chart(chart(readings, "voltage", "Voltage (V)", "#7eb451"), use_container_width=True)
    st.altair_chart(chart(readings, "power", "Power (W)", "#ff4b4b"), use_container_width=True)

with g2:
    st.altair_chart(chart(readings, "current", "Current (A)", "#fb8500"), use_container_width=True)
    st.altair_chart(chart(readings, "total_energy", "Energy (Wh)", "#023e8a"), use_container_width=True)

# --- DAILY ENERGY ---
st.write("---")

daily_energy = float(daily.iloc[0]["total_energy"]) if not daily.empty and daily.iloc[0]["total_energy"] else 0.0
daily_cost = (daily_energy / 1000.0) * RATE_PER_KWH

m1, m2 = st.columns(2)

m1.markdown(f"""
<div style="text-align:center; padding:18px; border-radius:8px; background:rgba(2,62,138,0.08);">
<h4>Today's Energy</h4>
<h2 style="color:#023e8a;">{daily_energy:.4f} Wh</h2>
</div>
""", unsafe_allow_html=True)

m2.markdown(f"""
<div style="text-align:center; padding:18px; border-radius:8px; background:rgba(42,157,143,0.08);">
<h4>Today's Cost</h4>
<h2 style="color:#2a9d8f;">${daily_cost:.5f}</h2>
</div>
""", unsafe_allow_html=True)

# --- ALERTS ---
st.write("---")
st.subheader("🚨 Alerts")

st.markdown("""
<div style="
    max-height:160px;
    overflow-y:auto;
    border:1px solid rgba(255,255,255,0.1);
    border-radius:8px;
    padding:6px;
    background:rgba(255,255,255,0.02);
">
""", unsafe_allow_html=True)

for _, row in alerts.iterrows():
    msg = row["description"][:55] + ("..." if len(row["description"]) > 55 else "")
    time_str = row["time_stamp"].strftime("%H:%M:%S")

    cols = st.columns([8,1])

    with cols[0]:
        st.markdown(
            f"<div style='font-size:13px;'>"
            f"<span style='color:gray'>{time_str}</span> — {msg}"
            f"</div>",
            unsafe_allow_html=True
        )

    with cols[1]:
        if st.button("✕", key=f"del_{row['id']}"):
            with conn.session as s:
                s.execute(f"DELETE FROM public.alerts WHERE id = '{row['id']}'")
                s.commit()
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# --- DOWNLOAD ---
st.write("---")

download_df = conn.query("""
    SELECT timestamp, voltage, current, power, total_energy
    FROM public.readings
    WHERE timestamp >= NOW() - INTERVAL '24 hours'
    ORDER BY timestamp ASC;
""", ttl=10)

st.download_button(
    "Download Last 24h Data",
    download_df.to_csv(index=False).encode(),
    "energy_data.csv",
    "text/csv"
)

# --- REFRESH ---
time.sleep(1)
st.rerun()