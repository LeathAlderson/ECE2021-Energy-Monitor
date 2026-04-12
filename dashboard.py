import streamlit as st
import pandas as pd
import altair as alt
import time

RATE_PER_KWH = 0.15

st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

conn = st.connection("neon", type="sql")

# ---------------- STATE ----------------
if "time_window" not in st.session_state:
    st.session_state.time_window = "24h"

WINDOWS = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "6h": "6 hours",
    "24h": "24 hours"
}

# ---------------- BUTTONS ----------------
cols = st.columns(len(WINDOWS))

for i, key in enumerate(WINDOWS.keys()):
    active = st.session_state.time_window == key
    if cols[i].button(key, use_container_width=True, type="primary" if active else "secondary"):
        st.session_state.time_window = key
        st.rerun()

selected = st.session_state.time_window
window = WINDOWS[selected]

# ---------------- DATA (RAW SLICE ONLY) ----------------
try:
    readings = conn.query(f"""
        SELECT timestamp, voltage, current, power, total_energy
        FROM public.readings
        WHERE timestamp >= NOW() - INTERVAL '{window}'
        ORDER BY timestamp ASC;
    """, ttl=1)

    latest = conn.query("""
        SELECT voltage, current, power, total_energy
        FROM public.readings
        ORDER BY timestamp DESC
        LIMIT 1;
    """, ttl=1)

    alerts = conn.query("""
        SELECT description, time_stamp
        FROM public.alerts
        ORDER BY time_stamp DESC
        LIMIT 50;
    """, ttl=2)

    daily = conn.query("""
        SELECT MAX(total_energy) as total_energy
        FROM public.readings
        WHERE DATE(timestamp) = CURRENT_DATE;
    """, ttl=5)

except Exception as e:
    st.error(f"DB error: {e}")
    st.stop()

if readings.empty or latest.empty:
    st.info("Waiting for sensor data...")
    st.stop()

# ---------------- FORMAT ----------------
readings["timestamp"] = pd.to_datetime(readings["timestamp"])
alerts["time_stamp"] = pd.to_datetime(alerts["time_stamp"])
latest = latest.iloc[0]

# ---------------- METRICS ----------------
c1, c2, c3 = st.columns(3)
c1.metric("Voltage", f"{latest['voltage']:.2f} V")
c2.metric("Current", f"{latest['current']:.2f} A")
c3.metric("Power", f"{latest['power']:.2f} W")

st.write("---")

# ---------------- AXIS FORMAT ----------------
def axis_fmt(window_key):
    if window_key == "5m":
        return "%H:%M:%S"
    elif window_key == "15m":
        return "%H:%M:%S"
    elif window_key == "1h":
        return "%H:%M"
    elif window_key == "6h":
        return "%H:%M"
    else:
        return "%Y/%m/%d"

fmt = axis_fmt(selected)

# ---------------- CHART (FIXED CROSSHAIR STYLE) ----------------
def make_chart(df, col, title, color):
    hover = alt.selection_point(
        nearest=True,
        on="mouseover",
        fields=["timestamp"],
        empty=False
    )

    base = alt.Chart(df).encode(
        x=alt.X("timestamp:T", axis=alt.Axis(format=fmt), title=None),
        y=alt.Y(f"{col}:Q", scale=alt.Scale(zero=False))
    )

    line = base.mark_line(color=color)

    points = base.mark_point(size=60, color=color).transform_filter(hover)

    rule = base.mark_rule(color="gray").transform_filter(hover)

    return (
        line + points + rule
    ).add_params(hover).properties(height=240, title=title)

# ---------------- GRAPHS ----------------
g1, g2 = st.columns(2)

with g1:
    st.altair_chart(make_chart(readings, "voltage", "Voltage (V)", "#7eb451"),
                    use_container_width=True)

    st.altair_chart(make_chart(readings, "power", "Power (W)", "#ff4b4b"),
                    use_container_width=True)

with g2:
    st.altair_chart(make_chart(readings, "current", "Current (A)", "#fb8500"),
                    use_container_width=True)

    st.altair_chart(make_chart(readings, "total_energy", "Energy (Wh)", "#023e8a"),
                    use_container_width=True)

# ---------------- DAILY ----------------
st.write("---")

daily_energy = float(daily.iloc[0]["total_energy"] or 0)
daily_cost = (daily_energy / 1000.0) * RATE_PER_KWH

m1, m2 = st.columns(2)

m1.markdown(f"""
<div style="text-align:center;padding:16px;border-radius:10px;background:rgba(2,62,138,0.08);">
<h4>Today's Energy</h4>
<h2 style="color:#023e8a;">{daily_energy:.4f} Wh</h2>
</div>
""", unsafe_allow_html=True)

m2.markdown(f"""
<div style="text-align:center;padding:16px;border-radius:10px;background:rgba(42,157,143,0.08);">
<h4>Today's Cost</h4>
<h2 style="color:#2a9d8f;">${daily_cost:.5f}</h2>
</div>
""", unsafe_allow_html=True)

# ---------------- ALERTS ----------------
st.write("---")
st.subheader("🚨 Alerts")

rows = []
for _, row in alerts.iterrows():
    t = row["time_stamp"].strftime("%Y/%m/%d %H:%M:%S")
    msg = row["description"][:80] + ("..." if len(row["description"]) > 80 else "")
    rows.append([f"{t} — {msg}"])

st.dataframe(pd.DataFrame(rows, columns=["Alert"]),
             use_container_width=True,
             height=180,
             hide_index=True)

# ---------------- DOWNLOAD (RESTORED) ----------------
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

# ---------------- REFRESH ----------------
time.sleep(1)
st.rerun()