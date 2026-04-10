import streamlit as st
import paho.mqtt.client as mqtt
import json
import pandas as pd
import time
import ssl
from pathlib import Path

# --- Configuration ---
AWS_ENDPOINT = "a2n8xb6p9d7o9i-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = "Streamlit_Web_Dashboard"
TOPIC = "ece2021/energy_data"

import tempfile
import os


BASE_DIR = Path(__file__).parent.resolve()
CERTS_DIR = BASE_DIR / "certs"

CA_PATH = CERTS_DIR / "AmazonRootCA1.pem"
# Fixed the double 'ff' typo here!
CERT_PATH = CERTS_DIR / "c5ebb4459f6a3cb0303ae7b300e5215734a5484170cddf2dffe2c9bcc341520-certificate.pem.crt"
KEY_PATH = CERTS_DIR / "c5ebb4459f6a3cb0303ae7b300e5215734a5484170cddf2dffe2c9bcc341520-private.pem.key"

# 2. Diagnostic Check - This will halt the app and show the error in the UI
if not CA_PATH.exists():
    st.error(f"Missing Root CA! Python is looking here: {CA_PATH}")
    st.stop()
if not CERT_PATH.exists():
    st.error(f"Missing Certificate! Python is looking here: {CERT_PATH}")
    st.stop()
if not KEY_PATH.exists():
    st.error(f"Missing Private Key! Python is looking here: {KEY_PATH}")
    st.stop()
    
# --- Page Setup ---
st.set_page_config(page_title="Live Energy Monitor", layout="wide")
st.title("⚡ Live Energy Monitor Dashboard")

# FIX: Create a standard Python list that survives page refreshes
@st.cache_resource
def get_data_buffer():
    return []

# This is our shared "box" that both threads can talk to safely
data_buffer = get_data_buffer()

# --- MQTT Connection ---
@st.cache_resource
def init_mqtt():
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC)
            print("Dashboard connected to AWS and listening!")

    def on_message(client, userdata, msg):
        payload = json.loads(msg.payload.decode())
        
        # FIX: Append to the shared buffer instead of session_state
        data_buffer.append(payload)
        
        if len(data_buffer) > 50:
            data_buffer.pop(0)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    client.tls_set(
        ca_certs=str(CA_PATH),
        certfile=str(CERT_PATH),
        keyfile=str(KEY_PATH)
    )
    
    client.connect(AWS_ENDPOINT, 8883, 60)
    client.loop_start() 
    return client

client = init_mqtt()

# --- UI Layout ---
col1, col2, col3 = st.columns(3)
metric_volts = col1.empty()
metric_amps = col2.empty()
metric_power = col3.empty()

st.subheader("Live Power Draw (Watts)")
chart_placeholder = st.empty()

# --- The Live Update Loop ---
# FIX: Read from the shared buffer
if len(data_buffer) > 0:
    latest = data_buffer[-1]
    
    metric_volts.metric("Voltage", f"{latest['voltage_V']} V")
    metric_amps.metric("Current", f"{latest['current_A']} A")
    metric_power.metric("Power", f"{latest['power_W']} W")
    
    df = pd.DataFrame(data_buffer)
    chart_placeholder.line_chart(df.set_index('timestamp')['power_W'])
else:
    st.info("Waiting for data from Raspberry Pi... Make sure your analysis_outputs.py script is running!")

# Force Streamlit to automatically refresh the page every 1 second
time.sleep(1)
st.rerun()