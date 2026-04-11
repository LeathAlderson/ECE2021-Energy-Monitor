import streamlit as st
import pandas as pd
import altair as alt
import time

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Neon Database Connection ---
conn = st.connection("neon", type="sql")

try:
    # 1. Pull Telemetry (Readings)
    query_readings = "SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;"
    live_df = conn.query(query_readings, ttl="0s") # Set ttl to 0 for live data

    # 2. Pull the Single Latest Alert from the dedicated table
    query_alerts = "SELECT * FROM alerts ORDER BY time_stamp DESC LIMIT 1;"
    latest_alert_df = conn.query(query_alerts, ttl="0s")
except Exception as e:
    st.error(f"Failed to connect to Neon: {e}")
    st.stop()

if not live_df.empty:
    latest = live_df.iloc[0]
    
    # --- 1. SEPARATE TABLE ALERT LOGIC ---
    if not latest_alert_df.empty:
        alert_row = latest_alert_df.iloc[0]
        alert_time = pd.to_datetime(alert_row['time_stamp'])
        
        # Only show the red alert bar if the alert happened in the last 60 seconds
        time_since_alert = (pd.Timestamp.now(tz='UTC') - alert_time).total_seconds()
        
        if time_since_alert < 60:
            st.error(f"🚨 SYSTEM ALERT: {alert_row['description']} (Detected {int(time_since_alert)}s ago)")

    # --- 2. LIVE METRICS ---
    # Using the columns from your 'readings' table screenshot
    calc_power = latest['voltage'] * latest['current']

    col1, col2, col3 = st.columns(3)
    col1.metric("Live Voltage", f"{latest['voltage']:.2f} V")
    col2.metric("Live Current", f"{latest['current']:.2f} A")
    col3.metric("Live Power", f"{calc_power:.2f} W")
    
    st.write("---")
    
    # --- 3. TIME WINDOW CONTROLS ---
    if 'time_window' not in st.session_state:
        st.session_state.time_window = "15 Minutes"
        
    def set_window(selected_window):
        st.session_state.time_window = selected_window
            
    options = ["5 Minutes", "15 Minutes", "30 Minutes", "1 Hour", "3 Hours", "6 Hours", "12 Hours", "24 Hours"]
    cols = st.columns(len(options))
    
    for i, opt in enumerate(options):
        btn_type = "primary" if st.session_state.time_window == opt else "secondary"
        cols[i].button(opt, type=btn_type, use_container_width=True, on_click=set_window, args=(opt,), key=f"btn_{opt}")

    # Map window selection to minutes
    window_map = {"5 Minutes": 5, "15 Minutes": 15, "30 Minutes": 30, "1 Hour": 60, "3 Hours": 180, "6 Hours": 360, "12 Hours": 720, "24 Hours": 1440}
    mins_back = window_map[st.session_state.time_window]
    
    # --- 4. DATA PROCESSING ---
    chart_df = live_df.iloc[::-1].copy() # Reverse to chronological order
    chart_df['power'] = chart_df['voltage'] * chart_df['current']
    chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
    
    # Calculate energy delta based on time between rows
    chart_df['time_diff_hours'] = chart_df['timestamp'].diff().dt.total_seconds() / 3600.0
    chart_df['energy_kwh'] = (chart_df['power'] * chart_df['time_diff_hours'].fillna(0)).cumsum() / 1000.0
    chart_df['cost_usd'] = chart_df['energy_kwh'] * 0.1521 
    
    cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
    display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

    # --- 5. GRAPHS ---
    g1, g2 = st.columns(2)
    with g1:
        st.altair_chart(alt.Chart(display_df).mark_line(color='#00b4d8').encode(
            x='timestamp:T', y=alt.Y('voltage:Q', scale=alt.Scale(zero=False))).properties(title="Voltage (V)", height=250), use_container_width=True)
        
        st.altair_chart(alt.Chart(display_df).mark_line(color='#ff4b4b').encode(
            x='timestamp:T', y='power:Q').properties(title="Power (W)", height=250), use_container_width=True)
        
    with g2:
        st.altair_chart(alt.Chart(display_df).mark_line(color='#fb8500').encode(
            x='timestamp:T', y=alt.Y('current:Q', scale=alt.Scale(zero=False))).properties(title="Current (A)", height=250), use_container_width=True)
        
        st.altair_chart(alt.Chart(display_df).mark_line(color='#023e8a').encode(
            x='timestamp:T', y='energy_kwh:Q').properties(title="Cumulative Energy (kWh)", height=250), use_container_width=True)

    # Cost Area Chart
    st.altair_chart(alt.Chart(display_df).mark_area(color='#2a9d8f', opacity=0.3).encode(
        x='timestamp:T', y='cost_usd:Q').properties(title="Cumulative Cost ($)", height=200), use_container_width=True)

    # --- 6. SUMMARY METRICS ---
    st.write("---")
    m1, m2 = st.columns(2)
    m1.metric("Total Energy (24h)", f"{chart_df['energy_kwh'].max():.4f} kWh")
    m2.metric("Total Cost (24h)", f"${chart_df['cost_usd'].max():.4f}")

    # --- 7. RAW LOGS ---
    st.write("---")
    st.subheader("📋 Raw System Logs")
    log_display = display_df[['timestamp', 'voltage', 'current', 'power']].sort_values(by='timestamp', ascending=False)
    st.dataframe(log_display, use_container_width=True, hide_index=True)

else:
    st.info("No data found in 'readings' table. Please check your backend connection.")

# Auto-refresh logic
time.sleep(2)
st.rerun()