import streamlit as st
import pandas as pd
import altair as alt
import time
from datetime import datetime

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Neon Database Connection ---
conn = st.connection("neon", type="sql")

try:
    # Pull 24h of data so we definitely have the data since midnight
    live_df = conn.query("SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
    all_alerts_df = conn.query("SELECT * FROM alerts ORDER BY time_stamp DESC;", ttl="0s")
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

if not live_df.empty:
    latest = live_df.iloc[0]
    
    # 1. LIVE METRICS
    p_now = latest['voltage'] * latest['current']
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Voltage", f"{latest['voltage']:.2f} V")
    c2.metric("Live Current", f"{latest['current']:.2f} A")
    c3.metric("Live Power", f"{p_now:.2f} W")

    st.write("---")

    # 2. TIME WINDOW CONTROLS (For the Graphs only)
    if 'time_window' not in st.session_state:
        st.session_state.time_window = "15 Minutes"
        
    def set_window(selected_window):
        st.session_state.time_window = selected_window
            
    options = ["5 Minutes", "15 Minutes", "1 Hour", "6 Hours", "24 Hours"]
    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        btn_color = "primary" if st.session_state.time_window == opt else "secondary"
        cols[i].button(opt, type=btn_color, use_container_width=True, on_click=set_window, args=(opt,), key=f"btn_{opt}")

    # --- 3. DATA PROCESSING & MIDNIGHT RESET LOGIC ---
    chart_df = live_df.iloc[::-1].copy()
    chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
    chart_df['power'] = chart_df['voltage'] * chart_df['current']
    
    # Calculate time differences for the whole set
    chart_df['time_diff_hours'] = chart_df['timestamp'].diff().dt.total_seconds() / 3600.0
    chart_df['time_diff_hours'] = chart_df['time_diff_hours'].fillna(0)

    # --- THE RESET LOGIC ---
    # Find midnight of the current day (matching the DB timezone)
    today_midnight = pd.Timestamp.now(tz='UTC').normalize() 
    
    # Create a 'today' dataframe to calculate daily energy/cost
    today_df = chart_df[chart_df['timestamp'] >= today_midnight].copy()
    
    if not today_df.empty:
        # Calculate energy starting from 0 at midnight
        today_df['energy_kwh'] = (today_df['power'] * today_df['time_diff_hours']).cumsum() / 1000.0
        today_df['cost_usd'] = today_df['energy_kwh'] * 0.1521
        daily_energy = today_df['energy_kwh'].max()
        daily_cost = today_df['cost_usd'].max()
    else:
        # If the day just started and there's no data yet
        daily_energy = 0.0
        daily_cost = 0.0

    # For the graphs, we still use the cumulative values from the chart_df 
    # but we'll recalculate them for the graph display window
    chart_df['energy_kwh_graph'] = (chart_df['power'] * chart_df['time_diff_hours']).cumsum() / 1000.0
    
    # Filter display for graphs based on time window
    window_map = {"5 Minutes": 5, "15 Minutes": 15, "1 Hour": 60, "6 Hours": 360, "24 Hours": 1440}
    mins_back = window_map[st.session_state.time_window]
    cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
    display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

    # --- 4. THE GRAPH GRID ---
    g1, g2 = st.columns(2)
    with g1:
        st.altair_chart(alt.Chart(display_df).mark_line(color='#00b4d8').encode(
            x='timestamp:T', y=alt.Y('voltage:Q', scale=alt.Scale(zero=False))).properties(title="Voltage (V)", height=250), use_container_width=True)
        st.altair_chart(alt.Chart(display_df).mark_line(color='#ff4b4b').encode(
            x='timestamp:T', y='power:Q').properties(title="Power Draw (W)", height=250), use_container_width=True)
    with g2:
        st.altair_chart(alt.Chart(display_df).mark_line(color='#fb8500').encode(
            x='timestamp:T', y=alt.Y('current:Q', scale=alt.Scale(zero=False))).properties(title="Current (A)", height=250), use_container_width=True)
        st.altair_chart(alt.Chart(display_df).mark_line(color='#023e8a').encode(
            x='timestamp:T', y='energy_kwh_graph:Q').properties(title="Cumulative Energy (kWh)", height=250), use_container_width=True)

    # --- 5. DAILY SUMMARY METRICS (RESET AT 12AM) ---
    st.write("---")
    metric_col1, metric_col2 = st.columns(2)
    
    with metric_col1:
        st.markdown(
            f"""<div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
                <h3 style="margin-bottom: 0px;">Energy Consumed today</h3>
                <h1 style="color: #023e8a; font-size: 3rem; margin-top: 10px;">{daily_energy:.4f} kWh</h1>
            </div>""", unsafe_allow_html=True)
        
    with metric_col2:
        st.markdown(
            f"""<div style="text-align: center; padding: 20px; background-color: rgba(42, 157, 143, 0.1); border-radius: 10px;">
                <h3 style="margin-bottom: 0px;">Operating Cost today</h3>
                <h1 style="color: #2a9d8f; font-size: 3rem; margin-top: 10px;">${daily_cost:.4f}</h1>
            </div>""", unsafe_allow_html=True)

    # --- 6. DOWNLOAD & ALERTS ---
    st.write("---")
    csv = live_df.to_csv(index=False).encode('utf-8')
    st.download_button(label="📥 Download Raw 24h Telemetry (CSV)", data=csv, 
                       file_name=f"energy_data_{time.strftime('%Y%m%d')}.csv", mime='text/csv', use_container_width=True)

    st.subheader("🚨 System Alert History")
    if not all_alerts_df.empty:
        all_alerts_df['time_stamp'] = pd.to_datetime(all_alerts_df['time_stamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        display_alerts = all_alerts_df[['description', 'time_stamp']].rename(columns={'description': 'Alert Message', 'time_stamp': 'Time Detected'})
        st.dataframe(display_alerts, use_container_width=True, hide_index=True)
    else:
        st.success("No alerts found in the database.")

else:
    st.info("Waiting for data...")

time.sleep(2)
st.rerun()