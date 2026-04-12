import streamlit as st
import pandas as pd
import altair as alt
import time

# no change

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Helper Function ---
def make_chart(data, y_col, title, color):
    """Generates an Altair line chart with optimized title spacing."""
    return alt.Chart(data).mark_line(color=color).encode(
        x=alt.X('timestamp:T', title="Time"),
        y=alt.Y(f'{y_col}:Q', title=None, scale=alt.Scale(zero=False)) # 'title=None' removes the axis label to save space since the header has it
    ).properties(
        title=title, 
        height=250
    ).configure_title(
        fontSize=16,
        anchor='start',
        dx=30 # This offsets the title to the right so it doesn't hit the edge
    ).configure_view(
        strokeWidth=0 # Cleans up the border to give the title more breathing room
    )
# --- Neon Database Connection ---
conn = st.connection("neon", type="sql")

try:
    live_df = conn.query("SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
    financials_df = conn.query("SELECT * FROM financials WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
    all_alerts_df = conn.query("SELECT * FROM alerts ORDER BY time_stamp DESC;", ttl="0s")
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

if not live_df.empty and not financials_df.empty:
    
    # --- Data Prep & Timezone Standardization ---
    # Convert all timestamps to Atlantic Time immediately to prevent table/graph mismatches
    for df, col in [(live_df, 'timestamp'), (financials_df, 'timestamp'), (all_alerts_df, 'time_stamp')]:
        if not df.empty:
            df[col] = pd.to_datetime(df[col]).dt.tz_convert('America/Moncton')

    # Reverse dataframes for chronological graphing
    chart_df = live_df.iloc[::-1]
    
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
            
    time_options = {"5 Minutes": 5, "15 Minutes": 15, "1 Hour": 60, "6 Hours": 360, "24 Hours": 1440}
    cols = st.columns(len(time_options))
    
    for i, opt in enumerate(time_options.keys()):
        btn_color = "primary" if st.session_state.time_window == opt else "secondary"
        if cols[i].button(opt, type=btn_color, use_container_width=True):
            st.session_state.time_window = opt
            st.rerun()

    # Filter graph dataset by selected time window
    mins_back = time_options[st.session_state.time_window]
    cutoff_time = chart_df['timestamp'].max() - pd.Timedelta(minutes=mins_back)
    display_df = chart_df[chart_df['timestamp'] >= cutoff_time]

    # --- 3. THE GRAPH GRID ---
    g1, g2 = st.columns(2)
    with g1:
        st.altair_chart(make_chart(display_df, 'voltage', 'Voltage (V)', '#00b4d8'), use_container_width=True)
        st.altair_chart(make_chart(display_df, 'power', 'Power Draw (W)', '#ff4b4b'), use_container_width=True)
    with g2:
        st.altair_chart(make_chart(display_df, 'current', 'Current (A)', '#fb8500'), use_container_width=True)
        st.altair_chart(make_chart(display_df, 'total_energy', 'Total Energy Logged (kWh)', '#023e8a'), use_container_width=True)

    # --- 4. LARGE SUMMARY METRICS ---
    st.write("---")
    m1, m2 = st.columns(2)
    
    m1.markdown(f"""
        <div style="text-align: center; padding: 20px; background-color: rgba(2, 62, 138, 0.1); border-radius: 10px;">
            <h3 style="margin-bottom: 0px;">Total Energy Logged</h3>
            <h1 style="color: #023e8a; font-size: 3rem; margin-top: 10px;">{latest_reading['total_energy']:.4f} kWh</h1>
        </div>""", unsafe_allow_html=True)
        
    m2.markdown(f"""
        <div style="text-align: center; padding: 20px; background-color: rgba(42, 157, 143, 0.1); border-radius: 10px;">
            <h3 style="margin-bottom: 0px;">Cumulative Cost</h3>
            <h1 style="color: #2a9d8f; font-size: 3rem; margin-top: 10px;">${latest_finance['cumulative_cost']:.4f}</h1>
        </div>""", unsafe_allow_html=True)

    # --- 5. STATISTICS & ALERT TABLES ---
    st.write("---")
    t1, t2 = st.columns(2)

    with t1:
        st.subheader("💵 Financial Statistics")
        fin_disp = financials_df[['timestamp', 'cost_per_hour', 'cost_delta', 'cumulative_cost']].copy()
        fin_disp['timestamp'] = fin_disp['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        fin_disp.columns = ['Time', 'Cost/Hr Rate ($)', 'Cost Delta ($)', 'Cumulative ($)']
        
        st.dataframe(
            fin_disp.style.format({'Cost/Hr Rate ($)': '{:.4f}', 'Cost Delta ($)': '{:.6f}', 'Cumulative ($)': '{:.4f}'}), 
            use_container_width=True, hide_index=True
        )

    with t2:
        st.subheader("🚨 Warning & Alert History")
        if not all_alerts_df.empty:
            alrt_disp = all_alerts_df[['description', 'time_stamp']].copy()
            alrt_disp['time_stamp'] = alrt_disp['time_stamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            alrt_disp.columns = ['Alert Message', 'Time Detected']
            st.dataframe(alrt_disp, use_container_width=True, hide_index=True)
        else:
            st.success("No alerts found in the database.")

    # --- 6. EXPORT / DOWNLOAD ---
    st.write("---")
    st.subheader("📥 Export 24h Data")
    dl1, dl2 = st.columns(2)
    
    dl1.download_button(
        "Download Telemetry (CSV)", 
        live_df.to_csv(index=False).encode('utf-8'), 
        f"telemetry_{time.strftime('%Y%m%d_%H%M%S')}.csv", 
        "text/csv", use_container_width=True
    )
    dl2.download_button(
        "Download Financials (CSV)", 
        financials_df.to_csv(index=False).encode('utf-8'), 
        f"financials_{time.strftime('%Y%m%d_%H%M%S')}.csv", 
        "text/csv", use_container_width=True
    )

else:
    st.info("Waiting for data in the 'readings' and 'financials' tables...")

# Auto-refresh loop
time.sleep(2)
st.rerun()
