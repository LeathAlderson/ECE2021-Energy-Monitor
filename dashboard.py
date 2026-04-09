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

# --- Secure Certificate Handling ---
# Safely check if secrets exist without crashing
try:
    has_aws_secrets = "aws" in st.secrets
except Exception:
    has_aws_secrets = False

if has_aws_secrets:
    # We are running on Streamlit Cloud
    temp_dir = Path(tempfile.mkdtemp())
    
    CA_PATH = temp_dir / "AmazonRootCA1.pem"
    CA_PATH.write_text(st.secrets["aws"]["root_ca"])
    
    CERT_PATH = temp_dir / "certificate.pem.crt"
    CERT_PATH.write_text(st.secrets["aws"]["cert"])
    
    KEY_PATH = temp_dir / "private.pem.key"
    KEY_PATH.write_text(st.secrets["aws"]["private_key"])
else:
    # We are running locally in Codespaces
    CERTS_DIR = Path("./certs")
    CA_PATH = CERTS_DIR / "AmazonRootCA1.pem"
    CERT_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-certificate.pem.crt" 
    KEY_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-private.pem.key"

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
        keyfile=str(KEY_PATH),
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
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