import streamlit as st
import pandas as pd
import altair as alt
import time

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Helper Function ---
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

# --- Neon Database Connection ---
conn = st.connection("neon", type="sql")

try:
    live_df = conn.query("""
        SELECT timestamp, voltage, current, power, total_energy
        FROM public.readings
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
        ORDER BY timestamp DESC;
    """, ttl="0s")

    all_alerts_df = conn.query("""
        SELECT description, time_stamp
        FROM public.alerts
        ORDER BY time_stamp DESC;
    """, ttl="0s")

except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

if not live_df.empty:
    
    # --- Timezone Fix ---
    for df, col in [(live_df, 'timestamp'), (all_alerts_df, 'time_stamp')]:
        if not df.empty:
            df[col] = pd.to_datetime(df[col]).dt.tz_convert('America/Moncton')

    # Reverse for charting
    chart_df = live_df.iloc[::-1]
    latest_reading = live_df.iloc[0]

    # --- 1. LIVE METRICS ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Voltage", f"{latest_reading['voltage']:.2f} V")
    c2.metric("Live Current", f"{latest_reading['current']:.2f} A")
    c3.metric("Live Power", f"{latest_reading['power']:.2f} W")

    st.write("---")

    # --- 2. TIME WINDOW CONTROLS ---
    if 'time_window' not in st.session_state:
        st.session_state.time_window = "15 Minutes"
            
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
    cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
    display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

    # --- 3. GRAPHS ---
    g1, g2 = st.columns(2)

    with g1:
        st.altair_chart(make_chart(display_df, 'voltage', 'Voltage (V)', '#00b4d8'), use_container_width=True)
        st.altair_chart(make_chart(display_df, 'power', 'Power Draw (W)', '#ff4b4b'), use_container_width=True)

    with g2:
        st.altair_chart(make_chart(display_df, 'current', 'Current (A)', '#fb8500'), use_container_width=True)
        st.altair_chart(make_chart(display_df, 'total_energy', 'Total Energy Logged (Wh)', '#023e8a'), use_container_width=True)

    # --- 4. SUMMARY ---
    st.write("---")
    m1 = st.columns(1)[0]

    m1.markdown(f"""
        <div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
            <h3 style="margin-bottom: 0px;">Total Energy Logged</h3>
            <h1 style="color: #023e8a; font-size: 3rem; margin-top: 10px;">
                {latest_reading['total_energy']:.4f} Wh
            </h1>
        </div>
    """, unsafe_allow_html=True)

    # --- 5. ALERT TABLE ---
    st.write("---")
    st.subheader("🚨 Warning & Alert History")

    if not all_alerts_df.empty:
        alrt_disp = all_alerts_df.copy()
        alrt_disp['time_stamp'] = alrt_disp['time_stamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        alrt_disp.columns = ['Alert Message', 'Time Detected']

        st.dataframe(alrt_disp, use_container_width=True, hide_index=True)
    else:
        st.success("No alerts found in the database.")

    # --- 6. DOWNLOAD ---
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

# --- Auto Refresh ---
time.sleep(2)
st.rerun()