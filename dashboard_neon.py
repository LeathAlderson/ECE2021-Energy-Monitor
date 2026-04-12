import streamlit as st
import pandas as pd
import altair as alt
import time
from datetime import datetime

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- 1. TIME WINDOW CONTROLS (Outside the live loop!) ---
# Native widgets hold their state automatically and won't get swallowed.
options = ["5 Minutes", "15 Minutes", "1 Hour", "6 Hours", "24 Hours"]
selected_window = st.radio("Select Timeframe:", options, index=1, horizontal=True, label_visibility="collapsed")
# Pro-tip: If you are on Streamlit >= 1.39, you can replace st.radio with st.pills for a cleaner button look:
# selected_window = st.pills("Select Timeframe:", options, default="15 Minutes", label_visibility="collapsed")

st.write("---")

# --- 2. LIVE DASHBOARD FRAGMENT ---
# This decorator tells Streamlit to only rerun this specific function every 2 seconds.
# It will NOT interrupt your UI clicks outside of it.
@st.fragment(run_every="2s")
def render_dashboard(time_window):
    conn = st.connection("neon", type="sql")

    try:
        # Pull 24h of data so we definitely have the data since midnight
        live_df = conn.query("SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
        all_alerts_df = conn.query("SELECT * FROM alerts ORDER BY time_stamp DESC;", ttl="0s")
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return # Use return instead of st.stop() inside a fragment

    if not live_df.empty:
        latest = live_df.iloc[0]
        
        # 1. LIVE METRICS
        p_now = latest['voltage'] * latest['current']
        c1, c2, c3 = st.columns(3)
        c1.metric("Live Voltage", f"{latest['voltage']:.2f} V")
        c2.metric("Live Current", f"{latest['current']:.2f} A")
        c3.metric("Live Power", f"{p_now:.2f} W")

        # 2. DATA PROCESSING & MIDNIGHT RESET LOGIC
        chart_df = live_df.iloc[::-1].copy()
        chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
        chart_df['power'] = chart_df['voltage'] * chart_df['current']
        
        # Calculate time differences for the whole set
        chart_df['time_diff_hours'] = chart_df['timestamp'].diff().dt.total_seconds() / 3600.0
        chart_df['time_diff_hours'] = chart_df['time_diff_hours'].fillna(0)

        # THE RESET LOGIC
        today_midnight = pd.Timestamp.now(tz='UTC').normalize() 
        today_df = chart_df[chart_df['timestamp'] >= today_midnight].copy()
        
        if not today_df.empty:
            today_df['energy_kwh'] = (today_df['power'] * today_df['time_diff_hours']).cumsum() / 1000.0
            today_df['cost_usd'] = today_df['energy_kwh'] * 0.1521
            daily_energy = today_df['energy_kwh'].max()
            daily_cost = today_df['cost_usd'].max()
        else:
            daily_energy = 0.0
            daily_cost = 0.0

        chart_df['energy_kwh_graph'] = (chart_df['power'] * chart_df['time_diff_hours']).cumsum() / 1000.0
        
        # Filter display for graphs based on time window
        window_map = {"5 Minutes": 5, "15 Minutes": 15, "1 Hour": 60, "6 Hours": 360, "24 Hours": 1440}
        mins_back = window_map[time_window]
        cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
        display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

        # 3. THE GRAPH GRID
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

        # 4. DAILY SUMMARY METRICS
        st.write("---")
        metric_col1, metric_col2 = st.columns(2)
        
        with metric_col1:
            st.markdown(
                f"""<div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
                    <h3 style="margin-bottom: 0px;">Energy Consumed Today</h3>
                    <h1 style="color: #023e8a; font-size: 3rem; margin-top: 10px;">{daily_energy:.4f} kWh</h1>
                </div>""", unsafe_allow_html=True)
            
        with metric_col2:
            st.markdown(
                f"""<div style="text-align: center; padding: 20px; background-color: rgba(42, 157, 143, 0.1); border-radius: 10px;">
                    <h3 style="margin-bottom: 0px;">Operating Cost Today</h3>
                    <h1 style="color: #2a9d8f; font-size: 3rem; margin-top: 10px;">${daily_cost:.4f}</h1>
                </div>""", unsafe_allow_html=True)

        # 5. DOWNLOAD & ALERTS
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

# --- 3. EXECUTE THE FRAGMENT ---
# Run the live dashboard, passing in the current state of the selection widget.
render_dashboard(selected_window)