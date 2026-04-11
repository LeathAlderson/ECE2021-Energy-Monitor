import streamlit as st
import pandas as pd
import altair as alt

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
@st.fragment(run_every=2)
def live_dashboard():
    try:
        # UPDATED: Pull exactly the last 24 hours of data instead of a fixed limit
        query = "SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;"
        live_df = conn.query(query, ttl="2s")
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
        
        st.write("---")
        
        # 3. TIME SLIDER CONTROL
        st.subheader("Historical Data Explorer")
        time_window = st.select_slider(
            "Select Graph Time Window",
            options=["5 Minutes", "15 Minutes", "30 Minutes", "1 Hour", "3 Hours", "6 Hours", "12 Hours", "24 Hours"],
            value="15 Minutes"
        )
        
        # Map the text selection to actual minutes
        window_map = {
            "5 Minutes": 5, "15 Minutes": 15, "30 Minutes": 30, "1 Hour": 60, 
            "3 Hours": 180, "6 Hours": 360, "12 Hours": 720, "24 Hours": 1440
        }
        mins_back = window_map[time_window]

        # 4. DATA PROCESSING & MATH
        # Reverse to chronological order (oldest to newest)
        chart_df = live_df.iloc[::-1].copy()
        chart_df['power'] = chart_df['voltage'] * chart_df['current']
        chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
        
        # Calculus: Accumulate Power over Time to get Energy (kWh)
        chart_df['time_diff_hours'] = chart_df['timestamp'].diff().dt.total_seconds() / 3600.0
        chart_df['time_diff_hours'] = chart_df['time_diff_hours'].fillna(0) # Handle the very first row
        chart_df['energy_kwh'] = (chart_df['power'] * chart_df['time_diff_hours']).cumsum() / 1000.0
        
        # Filter the dataframe down to just what the slider requested
        cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
        display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

        # 5. THE 2x2 GRAPH GRID
        graph_col1, graph_col2 = st.columns(2)
        
        with graph_col1:
            # VOLTAGE CHART (zero=False lets the Y-axis zoom in on 110-125V)
            v_chart = alt.Chart(display_df).mark_line(color='#00b4d8').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('voltage:Q', title='Voltage (V)', scale=alt.Scale(zero=False))
            ).properties(height=250, title="Voltage")
            st.altair_chart(v_chart, use_container_width=True)
            
            # POWER CHART (Locked to the Max Power threshold for visual scaling)
            p_chart = alt.Chart(display_df).mark_line(color='#ff4b4b').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('power:Q', title='Power (W)', scale=alt.Scale(domain=[0, max_power * 1.2]))
            ).properties(height=250, title="Power Draw")
            st.altair_chart(p_chart, use_container_width=True)
            
        with graph_col2:
            # CURRENT CHART
            c_chart = alt.Chart(display_df).mark_line(color='#fb8500').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('current:Q', title='Current (A)', scale=alt.Scale(zero=False))
            ).properties(height=250, title="Current")
            st.altair_chart(c_chart, use_container_width=True)
            
            # TOTAL ENERGY CHART
            e_chart = alt.Chart(display_df).mark_line(color='#023e8a').encode(
                x=alt.X('timestamp:T', title='Time'),
                y=alt.Y('energy_kwh:Q', title='Cumulative Energy (kWh)')
            ).properties(height=250, title="Energy Consumed (Last 24h)")
            st.altair_chart(e_chart, use_container_width=True)

        # 6. LOGS & USAGE TABS
        st.write("---")
        tab1, tab2 = st.tabs(["📊 Daily Usage", "📋 Raw System Logs"])
        
        with tab1:
            st.subheader("Energy Consumption")
            st.info("This is the actual calculated energy consumed over the last 24 hours of recorded data.")
            # Because we calculate cumulative energy, the very last row contains the grand total!
            actual_24h_kwh = chart_df['energy_kwh'].max()
            st.metric("Total 24h Usage", f"{actual_24h_kwh:.4f} kWh")
            
        with tab2:
            st.subheader("Recent Database Entries")
            # We display the filtered data so it matches the slider
            st.dataframe(display_df[['timestamp', 'voltage', 'current', 'power', 'alerts']], use_container_width=True, hide_index=True)

    else:
        st.info("Waiting for data in the database... Is your Pi sending data?")

# --- Run the Fragment ---
live_dashboard()