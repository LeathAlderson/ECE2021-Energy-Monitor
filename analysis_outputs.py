import numpy as np
import os
import time
from datetime import datetime
from pathlib import Path
import json
import ssl
import paho.mqtt.client as mqtt
import threading

try:
    from RPLCD.i2c import CharLCD
    LCD_AVAILABLE = True
except ImportError:
    LCD_AVAILABLE = False
    print(" RPLCD library not found (Normal if running on Windows). LCD will be simulated.")



AWS_ENDPOINT = "a2n8xb6p9d7o9i-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = "PiEnergyMonitor"
TOPIC = "ece2021/energy_data"

# FIX #9: Use pathlib for cross-platform paths (works on Windows and Raspberry Pi)
CERTS_DIR = Path("C:/ECE2021/certs")
CA_PATH   = CERTS_DIR / "AmazonRootCA1.pem"
CERT_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-certificate.pem.crt"
KEY_PATH  = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-private.pem.key"

LOG_FILE = Path("C:/ECE2021/energy_log.csv")


def setup_aws_connection():
    print("Configuring AWS IoT connection...")

    connected_event = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("Successfully connected to AWS IoT!")
            connected_event.set()
        else:
            print(f"Connection failed with code: {reason_code}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect

    try:
        client.tls_set(
            ca_certs=str(CA_PATH),
            certfile=str(CERT_PATH),
            keyfile=str(KEY_PATH),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
            ciphers=None
        )
        def on_publish(client, userdata, mid, reason_code, properties):
            print(f"[Cloud Sync] PUBACK received for message id: {mid} | reason: {reason_code}")

        client.on_publish = on_publish
        
        client.connect(AWS_ENDPOINT, 8883, 60)
        client.loop_start()

        # Wait up to 10 seconds for the CONNACK before proceeding
        if not connected_event.wait(timeout=10):
            print("Connection timed out. Cloud sync will be disabled.")
            return None

        return client

    except FileNotFoundError:
        print("AWS Certs not found. Cloud sync will be disabled for this run.")
        return None


def upload_live_data(client, timestamp, voltage_V, current_A, power_W, total_energy_Wh):
    time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    live_payload = {
        "timestamp": time_str,
        "voltage_V": round(voltage_V, 2),
        "current_A": round(current_A, 2),
        "power_W": round(power_W, 2),
        "total_energy_Wh": round(total_energy_Wh, 4)
    }

    json_payload = json.dumps(live_payload)

    if client is not None:
        msg_info = client.publish(TOPIC, json_payload, qos=1)
        
        # Wait until the message is actually sent over the wire
        msg_info.wait_for_publish(timeout=5)
        
        if msg_info.is_published():
            print(f"[Cloud Sync] Published to AWS: {power_W} W")
        else:
            print(f"[Cloud Sync] WARNING: Message may not have been delivered!")
    else:
        print(f"[Cloud Sync - SIMULATED]: {power_W} W")


def store_reading(timestamp, voltage_V, current_A, power_W, total_energy_Wh):

    is_new_file = not LOG_FILE.exists()

    with open(LOG_FILE, "a") as file:
        if is_new_file:
            file.write("timestamp,voltage_V,current_A,power_W,total_energy_Wh\n")

        file.write(f"{timestamp},{voltage_V},{current_A},{power_W},{total_energy_Wh}\n")


def get_time_keys(timestamp):

    keys = {
        "minute": timestamp.strftime("%Y-%m-%d-%H:%M"),
        "hour":   timestamp.strftime("%Y-%m-%d-%H"),
        "day":    timestamp.strftime("%Y-%m-%d"),
        "week":   timestamp.strftime("%Y-W%V"),
        "month":  timestamp.strftime("%Y-%m")
    }
    return keys


def update_usage_statistics(timestamp, energy_increment_Wh, stats_dict):

    keys = get_time_keys(timestamp)

    for period, current_time_label in keys.items():
        if period not in stats_dict:
            stats_dict[period] = {}

        if current_time_label not in stats_dict[period]:
            stats_dict[period][current_time_label] = 0.0

        stats_dict[period][current_time_label] += energy_increment_Wh

    return stats_dict


def check_thresholds(power_W, previous_power_W, voltage_V, current_A):

    # FIX #2: Skip spike/dip check on the first reading to avoid false alerts vs. 0
    if previous_power_W > 0:
        if power_W >= previous_power_W * 1.5:
            return True, "Power spike detected"

        if power_W <= previous_power_W * 0.5:
            return True, "Power dip detected"

    if voltage_V >= 140:
        return True, "Voltage levels raised above threshold"
    if voltage_V <= 100:
        return True, "Voltage levels dropped below threshold"

    # FIX #7: Use actual voltage_V instead of hardcoded 120 for current threshold
    expected_current = power_W / voltage_V if voltage_V != 0 else 0
    if current_A >= expected_current * 1.5:
        return True, "Current levels raised above threshold"
    if current_A <= expected_current * 0.5:
        return True, "Current levels dropped below threshold"

    return False, ""


def generate_alert_message(timestamp, reason, voltage_V, current_A, power_W):

    time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    alert_payload = {
        "timestamp": time_str,
        "event_type": "URGENT_ALERT",
        "reason": reason,
        "readings": {
            "voltage_V": round(voltage_V, 2),
            "current_A": round(current_A, 2),
            "power_W": round(power_W, 2)
        }
    }

    return alert_payload


def send_alert(alert_payload):

    print("\n" + "=" * 45)
    print("TRANSMITTING ALERT TO WEB APP")
    print("=" * 45)
    print(json.dumps(alert_payload, indent=4))
    print("=" * 45 + "\n")


def format_display_lines(voltage_V, current_A, power_W, total_energy_Wh, alert_status):

    v_str = f"{voltage_V:.1f}"
    i_str = f"{current_A:.2f}"
    p_str = f"{power_W:.1f}"
    e_str = f"{total_energy_Wh:.2f}"

    if alert_status:
        line1 = "SYSTEM ALERT"
        line2 = f"V:{v_str}  I:{i_str}"
        line3 = f"Pwr: {p_str} W"
        line4 = f"NRG: {e_str} Wh"
    else:
        line1 = f"Voltage: {v_str} V"
        line2 = f"Current: {i_str} A"
        line3 = f"Power:   {p_str} W"
        line4 = f"Energy:  {e_str} Wh"

    raw_lines = [line1, line2, line3, line4]
    final_lines = [line.ljust(20)[:20] for line in raw_lines]

    return final_lines


def setup_lcd():
    """
    Initializes the physical I2C LCD screen. 
    Returns the lcd object if successful, or None if hardware is missing.
    """
    if not LCD_AVAILABLE:
        return None
        
    try:
        # 0x27 is the most common I2C address for these screens. 
        # If your screen doesn't turn on later, change this to 0x3F.
        lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=20, rows=4, dotsize=8)
        lcd.clear()
        print("Physical LCD Screen Initialized!")
        return lcd
    except Exception as e:
        print(f"Physical LCD Setup failed (Check wiring): {e}")
        return None

def update_physical_lcd(lcd, lines):
    """
    Pushes the formatted 20-character strings to the hardware screen.
    """
    if lcd is None:
        return # Skip hardware writing if we are on a PC

    # Loop through the 4 lines and write them to the physical rows (0, 1, 2, 3)
    for row_index, line in enumerate(lines):
        lcd.cursor_pos = (row_index, 0) # Move the hardware cursor to the start of the row
        lcd.write_string(line)          # Physically draw the text


def main():
    live_stats = {}
    previous_power_W = 0.0
    total_energy_Wh = 0.0

    # --- Simulated sensor values (replace with real sensor reads on the Pi) ---
    voltage_V = 100.0
    current_A = 2
    power_W = 220.0
    energy_increment_Wh = 0.05

    aws_client = setup_aws_connection()
    physical_lcd = setup_lcd()  # NEW: Initialize the physical screen

    print("Starting Energy Monitor Loop...\n")

    # FIX #10: Wrap loop in try/finally so MQTT is always cleaned up on exit
    try:
        for i in range(3):
            timestamp = datetime.now()  # FIX #4: capture a fresh timestamp each iteration

            store_reading(timestamp, voltage_V, current_A, power_W, total_energy_Wh)

            live_stats = update_usage_statistics(timestamp, energy_increment_Wh, live_stats)
            print("Updated usage statistics:", json.dumps(live_stats, indent=4), "\n")

            # FIX #5: Accumulate total energy each iteration
            total_energy_Wh += energy_increment_Wh

            # FIX #1 & #3: Always derive alert_status from is_abnormal so it resets each loop
            is_abnormal, alert_reason = check_thresholds(power_W, previous_power_W, voltage_V, current_A)
            alert_status = is_abnormal  # clean reset every iteration

            if is_abnormal:
                payload = generate_alert_message(timestamp, alert_reason, voltage_V, current_A, power_W)
                send_alert(payload)

            upload_live_data(aws_client, timestamp, voltage_V, current_A, power_W, total_energy_Wh)

            lcd_lines = format_display_lines(voltage_V, current_A, power_W, total_energy_Wh, alert_status)
            print("LCD Display Lines:")
            for line in lcd_lines:
                print(f"[{line}]")
                
            # NEW: Push the exact same lines to the physical hardware
            update_physical_lcd(physical_lcd, lcd_lines)

            previous_power_W = power_W
            time.sleep(2)
            print("\n")

    finally:
        if aws_client is not None:
            time.sleep(1)  # Allow any final queued messages to flush
            aws_client.loop_stop()
            aws_client.disconnect()
            print("MQTT connection closed.")
            
        # NEW: Cleanly shut down the LCD if the script stops
        if physical_lcd is not None:
            physical_lcd.clear()
            physical_lcd.write_string("System Offline")

if __name__ == "__main__":
    main()