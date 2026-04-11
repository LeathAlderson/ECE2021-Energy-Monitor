import streamlit as st
import pandas as pd
import time

# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# --- Neon Database Connection ---
# This single line replaces your entire init_mqtt() setup!
# It automatically looks for [connections.neon] in st.secrets
conn = st.connection("neon", type="sql")

# --- Query the Data ---
# We query the last 50 rows. 
# ttl="1s" tells Streamlit to cache the query for 1 second so you don't spam Neon
try:
    # UPDATED: Query the 'readings' table instead of 'energy_data'
    df = conn.query('SELECT * FROM readings ORDER BY timestamp DESC LIMIT 50;', ttl="1s")
except Exception as e:
    st.error(f"Failed to connect or table doesn't exist: {e}")
    st.stop()

# --- UI Layout ---
col1, col2, col3 = st.columns(3)
metric_volts = col1.empty()
metric_amps = col2.empty()
metric_power = col3.empty()

st.subheader("Live Power Draw (Watts)")
chart_placeholder = st.empty()

# --- The Live Update Logic ---
if not df.empty:
    latest = df.iloc[0]
    
    # NEW: Calculate power dynamically (Voltage * Current)
    calc_power = latest['voltage'] * latest['current']
    
    # UPDATED: Use the exact column names from your screenshot
    metric_volts.metric("Voltage", f"{latest['voltage']:.2f} V")
    metric_amps.metric("Current", f"{latest['current']:.2f} A")
    metric_power.metric("Power", f"{calc_power:.2f} W")
    
    # Reverse the dataframe for the chart (oldest to newest)
    chart_df = df.iloc[::-1].copy()
    
    # Calculate power for the entire dataframe so the chart can graph it
    chart_df['power'] = chart_df['voltage'] * chart_df['current']
    chart_placeholder.line_chart(chart_df.set_index('timestamp')['power'])
else:
    st.info("Waiting for data in the database... Is your Pi sending data?")

# Force Streamlit to refresh the page every 1 second
time.sleep(1)
st.rerun()