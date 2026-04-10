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