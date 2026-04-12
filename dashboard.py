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
    # Pull from all three tables (using TTL=0s to ensure live data)
    live_df = conn.query("SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
    financials_df = conn.query("SELECT * FROM financials WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
    all_alerts_df = conn.query("SELECT * FROM alerts ORDER BY time_stamp DESC;", ttl="0s")
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

if not live_df.empty and not financials_df.empty:
    latest_reading = live_df.iloc[0]
    latest_finance = financials_df.iloc[0]
    
    # --- 1. LIVE METRICS ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Voltage", f"{latest_reading['voltage']:.2f} V")
    c2.metric("Live Current", f"{latest_reading['current']:.2f} A")
    c3.metric("Live Power", f"{latest_reading['power']:.2f} W")

    st.write("---")

    # --- 2. TIME WINDOW CONTROLS ---
    if 'time_window' not in st.session_state:
        st.session_state.time_window = "15 Minutes"
        
    def set_window(selected_window):
        st.session_state.time_window = selected_window
            
    options = ["5 Minutes", "15 Minutes", "1 Hour", "6 Hours", "24 Hours"]
    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        btn_color = "primary" if st.session_state.time_window == opt else "secondary"
        cols[i].button(opt, type=btn_color, width='stretch', on_click=set_window, args=(opt,), key=f"btn_{opt}")

    # --- 3. DATA PREP ---
    # Reverse order for chronological graphing
    chart_df = live_df.iloc[::-1].copy()
    chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
    
    finance_chart_df = financials_df.iloc[::-1].copy()
    finance_chart_df['timestamp'] = pd.to_datetime(finance_chart_df['timestamp'])
    
    window_map = {"5 Minutes": 5, "15 Minutes": 15, "1 Hour": 60, "6 Hours": 360, "24 Hours": 1440}
    mins_back = window_map[st.session_state.time_window]
    
    # Filter datasets by selected time window
    cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
    display_df = chart_df[chart_df['timestamp'] >= cutoff_time]
    display_finance_df = finance_chart_df[finance_chart_df['timestamp'] >= cutoff_time]

    # --- 4. THE GRAPH GRID ---
    g1, g2 = st.columns(2)
    with g1:
        st.altair_chart(alt.Chart(display_df).mark_line(color='#00b4d8').encode(
            x='timestamp:T', y=alt.Y('voltage:Q', scale=alt.Scale(zero=False))).properties(title="Voltage (V)", height=250), width='stretch')
        st.altair_chart(alt.Chart(display_df).mark_line(color='#ff4b4b').encode(
            x='timestamp:T', y='power:Q').properties(title="Power Draw (W)", height=250), width='stretch')
    with g2:
        st.altair_chart(alt.Chart(display_df).mark_line(color='#fb8500').encode(
            x='timestamp:T', y=alt.Y('current:Q', scale=alt.Scale(zero=False))).properties(title="Current (A)", height=250), width='stretch')
        st.altair_chart(alt.Chart(display_df).mark_line(color='#023e8a').encode(
            x='timestamp:T', y='total_energy:Q').properties(title="Total Energy Logged (kWh)", height=250), width='stretch')

    # --- 5. LARGE SUMMARY METRICS ---
    st.write("---")
    metric_col1, metric_col2 = st.columns(2)
    
    with metric_col1:
        st.markdown(
            f"""<div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
                <h3 style="margin-bottom: 0px;">Total Energy Logged</h3>
                <h1 style="color: #023e8a; font-size: 3rem; margin-top: 10px;">{latest_reading['total_energy']:.4f} kWh</h1>
            </div>""", unsafe_allow_html=True)
        
    with metric_col2:
        st.markdown(
            f"""<div style="text-align: center; padding: 20px; background-color: rgba(42, 157, 143, 0.1); border-radius: 10px;">
                <h3 style="margin-bottom: 0px;">Cumulative Cost</h3>
                <h1 style="color: #2a9d8f; font-size: 3rem; margin-top: 10px;">${latest_finance['cumulative_cost']:.4f}</h1>
            </div>""", unsafe_allow_html=True)

    # --- 6. STATISTICS & ALERT TABLES ---
    st.write("---")
    table_col1, table_col2 = st.columns(2)

    with table_col1:
        st.subheader("💵 Financial Statistics (From Pi)")
        
        # Format financial data
        finance_display = financials_df[['timestamp', 'cost_per_hour', 'cost_delta', 'cumulative_cost']].copy()
        finance_display['timestamp'] = pd.to_datetime(finance_display['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        finance_display.rename(columns={
            'timestamp': 'Time', 
            'cost_per_hour': 'Cost/Hr Rate ($)', 
            'cost_delta': 'Cost Delta ($)',
            'cumulative_cost': 'Cumulative ($)'
        }, inplace=True)
        
        st.dataframe(
            finance_display.style.format({'Cost/Hr Rate ($)': '{:.4f}', 'Cost Delta ($)': '{:.6f}', 'Cumulative ($)': '{:.4f}'}), 
            width = 'stretch', 
            hide_index=True
        )

    with table_col2:
        st.subheader("🚨 Warning & Alert History")
        if not all_alerts_df.empty:
            all_alerts_df['time_stamp'] = pd.to_datetime(all_alerts_df['time_stamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
            display_alerts = all_alerts_df[['description', 'time_stamp']].rename(columns={'description': 'Alert Message', 'time_stamp': 'Time Detected'})
            st.dataframe(display_alerts, width='stretch', hide_index=True)
        else:
            st.success("No alerts found in the database.")

    # --- 7. EXPORT / DOWNLOAD SECTION ---
    st.write("---")
    st.subheader("📥 Export 24h Data")
    dl_col1, dl_col2 = st.columns(2)
    
    with dl_col1:
        telemetry_csv = live_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Telemetry (V, A, W) CSV", 
            data=telemetry_csv, 
            file_name=f"telemetry_data_{time.strftime('%Y%m%d_%H%M%S')}.csv", 
            mime='text/csv',
            width='stretch'
        )
        
    with dl_col2:
        financials_csv = financials_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Financials (Cost, Rate) CSV", 
            data=financials_csv, 
            file_name=f"financial_data_{time.strftime('%Y%m%d_%H%M%S')}.csv", 
            mime='text/csv',
            width='stretch'
        )

else:
    st.info("Waiting for data in the 'readings' and 'financials' tables...")

# Auto-refresh loop
time.sleep(2)
st.rerun()