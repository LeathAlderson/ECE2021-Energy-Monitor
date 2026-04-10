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
    df = conn.query('SELECT * FROM energy_data ORDER BY timestamp DESC LIMIT 50;', ttl="1s")
except Exception as e:
    st.error(f"Failed to connect to Neon or table doesn't exist: {e}")
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
    # Get the very first row (the newest data because of ORDER BY DESC)
    latest = df.iloc[0]
    
    metric_volts.metric("Voltage", f"{latest['voltage_V']} V")
    metric_amps.metric("Current", f"{latest['current_A']} A")
    metric_power.metric("Power", f"{latest['power_W']} W")
    
    # Reverse the dataframe so the chart plots left-to-right (oldest to newest)
    chart_df = df.iloc[::-1]
    chart_placeholder.line_chart(chart_df.set_index('timestamp')['power_W'])
else:
    st.info("Waiting for data in the Neon database...")

# Force Streamlit to refresh the page every 1 second to fetch new data
time.sleep(1)
st.rerun()
