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
    # Fetch Data
    # Pulling 24h of readings for the graphs/download
    live_df = conn.query("SELECT * FROM readings WHERE timestamp >= NOW() - INTERVAL '24 hours' ORDER BY timestamp DESC;", ttl="0s")
    
    # Pulling ALL alerts for the new history table
    all_alerts_df = conn.query("SELECT * FROM alerts ORDER BY time_stamp DESC;", ttl="0s")
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

if not live_df.empty:
    latest = live_df.iloc[0]
    
    # 1. LIVE METRICS
    p_now = latest['voltage'] * latest['current']
    c1, c2, c3 = st.columns(3)
    c1.metric("Voltage", f"{latest['voltage']:.2f} V")
    c2.metric("Current", f"{latest['current']:.2f} A")
    c3.metric("Power", f"{p_now:.2f} W")

    st.write("---")

    # 2. GRAPHS
    if 'time_window' not in st.session_state:
        st.session_state.time_window = "15 Minutes"
        
    def set_window(selected_window):
        st.session_state.time_window = selected_window
            
    options = ["5 Minutes", "15 Minutes", "1 Hour", "6 Hours", "24 Hours"]
    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        btn_color = "primary" if st.session_state.time_window == opt else "secondary"
        cols[i].button(opt, type=btn_color, use_container_width=True, on_click=set_window, args=(opt,), key=f"btn_{opt}")

    chart_df = live_df.iloc[::-1].copy()
    chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
    chart_df['power'] = chart_df['voltage'] * chart_df['current']
    
    v_chart = alt.Chart(chart_df).mark_line(color='#00b4d8').encode(x='timestamp:T', y=alt.Y('voltage:Q', scale=alt.Scale(zero=False))).properties(height=250, title="Voltage History")
    p_chart = alt.Chart(chart_df).mark_line(color='#ff4b4b').encode(x='timestamp:T', y='power:Q').properties(height=250, title="Power Draw (W)")
    
    st.altair_chart(v_chart, use_container_width=True)
    st.altair_chart(p_chart, use_container_width=True)

    # 3. DOWNLOAD SECTION
    # We place the download button here as a bridge between the live visuals and historical logs
    st.write("---")
    csv = live_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Raw 24h Telemetry (CSV)",
        data=csv,
        file_name=f"energy_data_{time.strftime('%Y%m%d-%H%M%S')}.csv",
        mime='text/csv',
        use_container_width=True
    )

    # 4. FULL ALERT HISTORY
    st.subheader("🚨 System Alert History")
    if not all_alerts_df.empty:
        # Clean up the alerts for display
        all_alerts_df['time_stamp'] = pd.to_datetime(all_alerts_df['time_stamp'])
        all_alerts_df['time_stamp'] = all_alerts_df['time_stamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        display_alerts = all_alerts_df[['description', 'time_stamp']].rename(
            columns={'description': 'Alert Message', 'time_stamp': 'Time Detected'}
        )
        
        # Display as a full-width dataframe for better scrolling of "all" alerts
        st.dataframe(display_alerts, use_container_width=True, hide_index=True)
    else:
        st.success("No alerts found in the database.")

else:
    st.info("Waiting for data... Ensure the Pi is connected and sending readings.")

# Refresh logic
time.sleep(2)
st.rerun()