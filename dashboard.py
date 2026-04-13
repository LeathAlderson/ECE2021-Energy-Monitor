import streamlit as st
import pandas as pd
import altair as alt
import time

RATE_PER_KWH = 0.15  # cost rate

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Chart Helper ---
def make_chart(data, y_col, title, color):
    return alt.Chart(data).mark_line(color=color).encode(
        x=alt.X('timestamp:T', title="Time"),
        y=alt.Y(f'{y_col}:Q', title=None, scale=alt.Scale(zero=False))
    ).properties(
        title=title,
        height=250
    ).configure_title(
        fontSize=16,
        anchor='start',
        dx=30
    ).configure_view(
        strokeWidth=0
    )

# --- DB Connection ---
conn = st.connection("neon", type="sql")

try:
    live_df = conn.query("""
        SELECT timestamp, voltage, current, power, total_energy
        FROM public.readings
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
        ORDER BY timestamp DESC;
    """, ttl="0s")

    alerts_df = conn.query("""
        SELECT description, time_stamp
        FROM public.alerts
        ORDER BY time_stamp DESC
        LIMIT 50;
    """, ttl="0s")

except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

if not live_df.empty:

    # --- Timezone Fix ---
    for df, col in [(live_df, 'timestamp'), (alerts_df, 'time_stamp')]:
        if not df.empty:
            df[col] = pd.to_datetime(df[col]).dt.tz_convert('America/Moncton')

    # Reverse for charts
    chart_df = live_df.iloc[::-1]
    latest = live_df.iloc[0]

    # --- LIVE METRICS ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Voltage", f"{latest['voltage']:.2f} V")
    c2.metric("Live Current", f"{latest['current']:.2f} A")
    c3.metric("Live Power", f"{latest['power']:.2f} W")

    st.write("---")

    # --- TIME WINDOW ---
    if 'time_window' not in st.session_state:
        st.session_state.time_window = "1 Hour"

    time_options = {
        "5 Minutes": 5,
        "15 Minutes": 15,
        "1 Hour": 60,
        "6 Hours": 360,
        "24 Hours": 1440
    }

    cols = st.columns(len(time_options))
    for i, opt in enumerate(time_options.keys()):
        btn_color = "primary" if st.session_state.time_window == opt else "secondary"
        if cols[i].button(opt, type=btn_color, use_container_width=True):
            st.session_state.time_window = opt
            st.rerun()

    mins_back = time_options[st.session_state.time_window]
    cutoff = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
    display_df = chart_df[chart_df['timestamp'] >= cutoff]

    # --- GRAPHS ---
    g1, g2 = st.columns(2)

    with g1:
        st.altair_chart(make_chart(display_df, 'voltage', 'Voltage (V)', '#00b4d8'), use_container_width=True)
        st.altair_chart(make_chart(display_df, 'power', 'Power Draw (W)', '#ff4b4b'), use_container_width=True)

    with g2:
        st.altair_chart(make_chart(display_df, 'current', 'Current (A)', '#fb8500'), use_container_width=True)
        st.altair_chart(make_chart(display_df, 'total_energy', 'Energy per Reading (Wh)', '#023e8a'), use_container_width=True)

    # --- ENERGY + COST (CORRECT AGGREGATION) ---
    total_energy_wh = live_df['total_energy'].sum()
    total_energy_kwh = total_energy_wh / 1000.0
    cost = total_energy_kwh * RATE_PER_KWH

    st.write("---")
    m1, m2 = st.columns(2)

    m1.markdown(f"""
        <div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
            <h3>Total Energy (Last 24h)</h3>
            <h1 style="color:#023e8a;">{total_energy_wh:.4f} Wh</h1>
        </div>
    """, unsafe_allow_html=True)

    m2.markdown(f"""
        <div style="text-align: center; padding: 20px; background-color: rgba(42, 157, 143, 0.1); border-radius: 10px;">
            <h3>Total Cost (Last 24h)</h3>
            <h1 style="color:#2a9d8f;">${cost:.4f}</h1>
        </div>
    """, unsafe_allow_html=True)

    # --- ALERTS (CODE 1 STYLE) ---
    st.write("---")
    st.subheader("🚨 Alerts")

    alert_rows = [
        [f"{r['time_stamp'].strftime('%Y/%m/%d %H:%M:%S')} — {r['description'][:80]}"]
        for _, r in alerts_df.iterrows()
    ]

    simple_alerts = pd.DataFrame(alert_rows, columns=["Alert"])

    st.dataframe(simple_alerts, use_container_width=True, height=180, hide_index=True)

    # --- DOWNLOAD ---
    st.write("---")
    st.subheader("📥 Export 24h Data")

    st.download_button(
        "Download Telemetry (CSV)",
        live_df.to_csv(index=False).encode('utf-8'),
        f"telemetry_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        "text/csv",
        use_container_width=True
    )

else:
    st.info("Waiting for data in the 'readings' table...")

# --- AUTO REFRESH ---
time.sleep(2)
st.rerun()