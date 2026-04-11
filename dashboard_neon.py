import streamlit as st
import pandas as pd
import altair as alt  # NEW: For smooth, locked-axis charts

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Threshold Settings (Sidebar) ---
st.sidebar.header("⚙️ Alert Settings")
st.sidebar.write("Adjust thresholds to trigger dashboard alerts:")
max_power = st.sidebar.number_input("Max Power Alert (W)", value=600.0, step=50.0)
max_voltage = st.sidebar.number_input("Max Voltage Alert (V)", value=125.0, step=1.0)

# --- Neon Database Connection ---
conn = st.connection("neon", type="sql")

# --- LIVE DASHBOARD FRAGMENT ---
# @st.fragment isolates this block so ONLY this section updates every 2 seconds.
# Your sidebar and the page background will no longer flash!
@st.fragment(run_every=2)
def live_dashboard():
    try:
        live_df = conn.query('SELECT * FROM readings ORDER BY timestamp DESC LIMIT 100;', ttl="1s")
    except Exception as e:
        st.error(f"Failed to connect or table doesn't exist: {e}")
        st.stop()

    if not live_df.empty:
        latest = live_df.iloc[0]
        calc_power = latest['voltage'] * latest['current']

        # 1. LIVE ALERTS
        if calc_power > max_power:
            st.error(f"🚨 ALERT: Power exceeded limit! Currently drawing {calc_power:.2f} W")
        if latest['voltage'] > max_voltage:
            st.warning(f"⚠️ WARNING: Voltage is unusually high: {latest['voltage']:.2f} V")

        # 2. LIVE METRICS
        col1, col2, col3 = st.columns(3)
        col1.metric("Live Voltage", f"{latest['voltage']:.2f} V")
        col2.metric("Live Current", f"{latest['current']:.2f} A")
        col3.metric("Live Power", f"{calc_power:.2f} W")
        
        # 3. SMOOTH CHART (Altair)
        st.subheader("Live Power Draw (Watts)")
        chart_df = live_df.iloc[::-1].copy()
        chart_df['power'] = chart_df['voltage'] * chart_df['current']
        
        # We lock the Y-axis from 0 to 20% higher than your max power threshold.
        # This stops the line from wildly resizing when new data arrives!
        smooth_chart = alt.Chart(chart_df).mark_line(color='#FF4B4B').encode(
            x=alt.X('timestamp:T', title='Time'),
            y=alt.Y('power:Q', title='Power (W)', scale=alt.Scale(domain=[0, max_power * 1.2]))
        ).properties(height=350)
        
        st.altair_chart(smooth_chart, use_container_width=True)

        # 4. LOGS & USAGE TABS
        st.write("---")
        tab1, tab2 = st.tabs(["📊 Daily Usage Estimate", "📋 Raw System Logs"])
        
        with tab1:
            st.subheader("Energy Consumption")
            st.info("This is an estimated rolling calculation based on recent average power draw.")
            avg_power = chart_df['power'].mean()
            estimated_kwh = (avg_power / 1000) * 24
            st.metric("Estimated 24h Usage", f"{estimated_kwh:.2f} kWh")
            
        with tab2:
            st.subheader("Recent Database Entries")
            st.dataframe(chart_df[['timestamp', 'voltage', 'current', 'power']], use_container_width=True, hide_index=True)

    else:
        st.info("Waiting for data in the database... Is your Pi sending data?")

# --- Run the Fragment ---
live_dashboard()

# Notice: You no longer need time.sleep() or st.rerun() down here!