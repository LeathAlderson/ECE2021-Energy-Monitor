import streamlit as st
import pandas as pd
import altair as alt

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Neon Database Connection ---
conn = st.connection("neon", type="sql")

# --- LIVE DASHBOARD FRAGMENT ---
@st.fragment(run_every=2)
def live_dashboard():
    try:
        query = "SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;"
        live_df = conn.query(query, ttl="2s")
    except Exception as e:
        st.error(f"Failed to connect or table doesn't exist: {e}")
        st.stop()

    if not live_df.empty:
        latest = live_df.iloc[0]
        calc_power = latest['voltage'] * latest['current']

        # 1. DATABASE-DRIVEN ALERTS
        # We grab the 'alerts' column from the newest row in the database
        db_alert = latest.get('alerts', 'Normal')
        
        # If it's not empty, not "Normal", and not a missing NaN value, flash the warning!
        if pd.notna(db_alert) and str(db_alert).strip() not in ["", "Normal", "None"]:
            st.error(f"🚨 SYSTEM ALERT: {db_alert}")

        # 2. LIVE METRICS
        col1, col2, col3 = st.columns(3)
        col1.metric("Live Voltage", f"{latest['voltage']:.2f} V")
        col2.metric("Live Current", f"{latest['current']:.2f} A")
        col3.metric("Live Power", f"{calc_power:.2f} W")
        
        st.write("---")
        
        # 3. TIME SLIDER CONTROL
        st.subheader("Historical Data Explorer")
        time_window = st.select_slider(
            "Select Graph Time Window",
            options=["5 Minutes", "15 Minutes", "30 Minutes", "1 Hour", "3 Hours", "6 Hours", "12 Hours", "24 Hours"],
            value="15 Minutes"
        )
        
        window_map = {
            "5 Minutes": 5, "15 Minutes": 15, "30 Minutes": 30, "1 Hour": 60, 
            "3 Hours": 180, "6 Hours": 360, "12 Hours": 720, "24 Hours": 1440
        }
        mins_back = window_map[time_window]

        # 4. DATA PROCESSING & MATH
        chart_df = live_df.iloc[::-1].copy()
        chart_df['power'] = chart_df['voltage'] * chart_df['current']
        chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
        
        chart_df['time_diff_hours'] = chart_df['timestamp'].diff().dt.total_seconds() / 3600.0
        chart_df['time_diff_hours'] = chart_df['time_diff_hours'].fillna(0)
        chart_df['energy_kwh'] = (chart_df['power'] * chart_df['time_diff_hours']).cumsum() / 1000.0
        
        cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
        display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

        # 5. THE 2x2 GRAPH GRID
        graph_col1, graph_col2 = st.columns(2)
        
        with graph_col1:
            v_chart = alt.Chart(display_df).mark_line(color='#00b4d8').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('voltage:Q', title='Voltage (V)', scale=alt.Scale(zero=False))
            ).properties(height=250, title="Voltage")
            st.altair_chart(v_chart, use_container_width=True)
            
            # Since we removed the slider, the Power chart will now auto-scale to fit the data
            p_chart = alt.Chart(display_df).mark_line(color='#ff4b4b').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('power:Q', title='Power (W)', scale=alt.Scale(zero=True))
            ).properties(height=250, title="Power Draw")
            st.altair_chart(p_chart, use_container_width=True)
            
        with graph_col2:
            c_chart = alt.Chart(display_df).mark_line(color='#fb8500').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('current:Q', title='Current (A)', scale=alt.Scale(zero=False))
            ).properties(height=250, title="Current")
            st.altair_chart(c_chart, use_container_width=True)
            
            e_chart = alt.Chart(display_df).mark_line(color='#023e8a').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('energy_kwh:Q', title='Cumulative Energy (kWh)')
            ).properties(height=250, title="Energy Consumed")
            st.altair_chart(e_chart, use_container_width=True)

        # 6. LARGE ENERGY DISPLAY
        st.write("---")
        actual_24h_kwh = chart_df['energy_kwh'].max()
        st.markdown(
            f"""
            <div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
                <h3 style="margin-bottom: 0px;">Total Energy Consumed (Last 24h)</h3>
                <h1 style="color: #023e8a; font-size: 3rem; margin-top: 10px;">{actual_24h_kwh:.4f} kWh</h1>
            </div>
            """, 
            unsafe_allow_html=True
        )

# 7. RAW SYSTEM LOGS TABLE
        st.write("---")
        st.subheader("📋 Raw System Logs")
        
        # We use .sort_values() to flip the dataframe so the newest timestamp is at the very top
        sorted_logs = display_df[['timestamp', 'voltage', 'current', 'power', 'alerts']].sort_values(by='timestamp', ascending=False)
        
        st.dataframe(sorted_logs, use_container_width=True, hide_index=True)

    else:
        st.info("Waiting for data in the database... Is your Pi sending data?")

# --- Run the Fragment ---
live_dashboard()