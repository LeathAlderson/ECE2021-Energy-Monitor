import streamlit as st
import paho.mqtt.client as mqtt
import json
import pandas as pd
import time
import tempfile
import os
from pathlib import Path

# --- 1. Define Paths based on Environment ---

# Safely check if we are in the cloud with valid secrets
is_cloud_deployment = False
try:
    if "aws" in st.secrets:
        is_cloud_deployment = True
except Exception:
    # If secrets don't exist at all (like in Codespaces), it safely falls down here
    pass

if is_cloud_deployment:
    # ☁️ STREAMLIT CLOUD ENVIRONMENT
    temp_dir = tempfile.mkdtemp()
    CERTS_DIR = Path(temp_dir)
    
    CA_PATH = CERTS_DIR / "AmazonRootCA1.pem"
    CERT_PATH = CERTS_DIR / "certificate.pem.crt"
    KEY_PATH = CERTS_DIR / "private.pem.key"
    
    CA_PATH.write_text(st.secrets["aws"]["ca_cert"])
    CERT_PATH.write_text(st.secrets["aws"]["cert"])
    KEY_PATH.write_text(st.secrets["aws"]["private_key"])
    
else:
    # 💻 LOCAL CODESPACES ENVIRONMENT
    BASE_DIR = Path(__file__).parent.resolve()
    CERTS_DIR = BASE_DIR / "certs"

    # Using the exact filenames found on your local drive
    CA_PATH = CERTS_DIR / "AmazonRootCA1.pem"
    CERT_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-certificate.pem.crt"
    KEY_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-private.pem.key"

# --- 2. Diagnostic Check ---
if not CA_PATH.exists():
    st.error(f"Missing Root CA! Python is looking here: {CA_PATH}")
    st.stop()
if not CERT_PATH.exists():
    st.error(f"Missing Certificate! Python is looking here: {CERT_PATH}")
    st.stop()
if not KEY_PATH.exists():
    st.error(f"Missing Private Key! Python is looking here: {KEY_PATH}")
    st.stop()

# (The rest of your init_mqtt() and Streamlit code stays exactly the same)
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