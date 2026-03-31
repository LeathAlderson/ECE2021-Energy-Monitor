import random
import time
from datetime import datetime
from pathlib import Path
import json
import ssl
import threading
import paho.mqtt.client as mqtt

try:
    from RPLCD.i2c import CharLCD
    LCD_AVAILABLE = True
except ImportError:
    LCD_AVAILABLE = False
    print("RPLCD library not found. LCD will be simulated.")


AWS_ENDPOINT = "a2n8xb6p9d7o9i-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = "PiEnergyMonitor"
TOPIC = "ece2021/energy_data"

CERTS_DIR = Path("C:/ECE2021/certs")  # placeholder: update for Raspberry Pi path later
CA_PATH = CERTS_DIR / "AmazonRootCA1.pem"
CERT_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-certificate.pem.crt"
KEY_PATH = CERTS_DIR / "c5ebb4459ff6a3cb0303ae7b300e5215734a5a84170cddf2dffe2c98cc341520-private.pem.key"

LOG_FILE = Path("C:/ECE2021/energy_log.csv")  # placeholder: update for Raspberry Pi path later


def initialize_system():
    state = {}

    state["sample_interval_sec"] = 1

    state["total_energy_Wh"] = 0.0
    state["previous_power_W"] = None  # placeholder: previous measurement

    state["high_power_threshold_W"] = 1500
    state["low_power_threshold_W"] = 5

    state["last_alert_time"] = None  # placeholder: datetime later
    state["data_file_path"] = LOG_FILE  # replaced with partner's log path

    state["adc_initialized"] = False  # placeholder: will be True after SPI setup
    state["display_initialized"] = False  # placeholder: LCD object later
    state["cloud_connected"] = False  # placeholder: cloud client later

    state["spi"] = None  # placeholder: SPI object later
    state["voltage_channel"] = 0  # placeholder: confirm real MCP3008 channel
    state["current_channel"] = 1  # placeholder: confirm real MCP3008 channel
    state["test_mode"] = True  # placeholder: set False when hardware ADC is ready

    state["aws_client"] = None  # placeholder: MQTT client after setup_aws_connection()
    state["lcd"] = None  # placeholder: LCD object after setup_lcd()

    state["live_stats"] = {}
    state["system_start_time"] = datetime.now()

    return state


def get_timestamp():
    timestamp = datetime.now()  # placeholder: depends on system clock being correct
    return timestamp


def read_adc_channels(state):
    if state["test_mode"] is True:
        raw_voltage_adc = random.randint(500, 700)  # placeholder: fake ADC voltage reading
        raw_current_adc = random.randint(400, 600)  # placeholder: fake ADC current reading
        return raw_voltage_adc, raw_current_adc

    if state["adc_initialized"] is False:
        raise RuntimeError("ADC is not initialized.")

    voltage_channel = state["voltage_channel"]  # placeholder: real wiring/channel mapping
    current_channel = state["current_channel"]  # placeholder: real wiring/channel mapping

    raw_voltage_adc = 0  # placeholder: replace with real MCP3008 read
    raw_current_adc = 0  # placeholder: replace with real MCP3008 read

    return raw_voltage_adc, raw_current_adc


def convert_voltage(raw_voltage_adc):
    adc_max_value = 1023
    reference_voltage = 3.3
    voltage_scale_factor = 36.36  # placeholder: calibrate using real sensor data

    sensor_voltage = (raw_voltage_adc / adc_max_value) * reference_voltage
    voltage_V = sensor_voltage * voltage_scale_factor

    return voltage_V


def convert_current(raw_current_adc):
    adc_max_value = 1023
    reference_voltage = 3.3
    zero_current_voltage = 2.5  # placeholder: calibrate zero-current offset
    sensitivity_V_per_A = 0.185  # placeholder: confirm ACS712 model

    sensor_voltage = (raw_current_adc / adc_max_value) * reference_voltage
    adjusted_voltage = sensor_voltage - zero_current_voltage
    current_A = adjusted_voltage / sensitivity_V_per_A

    return current_A


def compute_power(voltage_V, current_A):
    power_W = voltage_V * current_A
    return power_W


def update_energy(power_W, dt_sec, total_energy_Wh):
    dt_hours = dt_sec / 3600.0
    energy_increment_Wh = power_W * dt_hours
    updated_total_energy_Wh = total_energy_Wh + energy_increment_Wh
    return energy_increment_Wh, updated_total_energy_Wh


def setup_aws_connection():
    connected_event = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            connected_event.set()

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

        client.connect(AWS_ENDPOINT, 8883, 60)
        client.loop_start()

        if not connected_event.wait(timeout=10):
            return None

        return client

    except FileNotFoundError:
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
        msg_info.wait_for_publish(timeout=5)
    else:
        print(f"[Cloud Sync - SIMULATED]: {json_payload}")  # placeholder: real cloud disabled


def store_reading(timestamp, voltage_V, current_A, power_W, total_energy_Wh):
    is_new_file = not LOG_FILE.exists()

    with open(LOG_FILE, "a") as file:
        if is_new_file:
            file.write("timestamp,voltage_V,current_A,power_W,total_energy_Wh\n")

        file.write(f"{timestamp},{voltage_V},{current_A},{power_W},{total_energy_Wh}\n")


def get_time_keys(timestamp):
    keys = {
        "minute": timestamp.strftime("%Y-%m-%d-%H:%M"),
        "hour": timestamp.strftime("%Y-%m-%d-%H"),
        "day": timestamp.strftime("%Y-%m-%d"),
        "week": timestamp.strftime("%Y-W%V"),
        "month": timestamp.strftime("%Y-%m")
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
    if previous_power_W is not None and previous_power_W > 0:
        if power_W >= previous_power_W * 1.5:
            return True, "Power spike detected"
        if power_W <= previous_power_W * 0.5:
            return True, "Power dip detected"

    if voltage_V >= 140:
        return True, "Voltage levels raised above threshold"
    if voltage_V <= 100:
        return True, "Voltage levels dropped below threshold"

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
    print("=" * 45 + "\n")  # placeholder: currently console output, not real web app send


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
    if not LCD_AVAILABLE:
        return None

    try:
        lcd = CharLCD(
            i2c_expander='PCF8574',
            address=0x27,  # placeholder: may need 0x3F depending on actual LCD backpack
            port=1,
            cols=20,
            rows=4,
            dotsize=8
        )
        lcd.clear()
        return lcd
    except Exception:
        return None


def update_physical_lcd(lcd, lines):
    if lcd is None:
        return  # placeholder: simulated/no LCD mode

    for row_index, line in enumerate(lines):
        lcd.cursor_pos = (row_index, 0)
        lcd.write_string(line)

#=================================main============================
def main():
    state = initialize_system()

    state["aws_client"] = setup_aws_connection()  # placeholder: requires certs
    state["lcd"] = setup_lcd()  # placeholder: requires hardware

    print("Starting Energy Monitor Loop...\n")

    try:
        while True:
            timestamp = get_timestamp()

            raw_voltage_adc, raw_current_adc = read_adc_channels(state)

            voltage_V = convert_voltage(raw_voltage_adc)
            current_A = convert_current(raw_current_adc)

            power_W = compute_power(voltage_V, current_A)

            energy_increment_Wh, state["total_energy_Wh"] = update_energy(
                power_W,
                state["sample_interval_sec"],
                state["total_energy_Wh"]
            )

            store_reading(
                timestamp,
                voltage_V,
                current_A,
                power_W,
                state["total_energy_Wh"]
            )

            state["live_stats"] = update_usage_statistics(
                timestamp,
                energy_increment_Wh,
                state["live_stats"]
            )

            previous_power = state["previous_power_W"] if state["previous_power_W"] is not None else 0.0

            is_abnormal, alert_reason = check_thresholds(
                power_W,
                previous_power,
                voltage_V,
                current_A
            )

            alert_status = is_abnormal

            if is_abnormal:
                alert_payload = generate_alert_message(
                    timestamp,
                    alert_reason,
                    voltage_V,
                    current_A,
                    power_W
                )
                send_alert(alert_payload)

            upload_live_data(
                state["aws_client"],
                timestamp,
                voltage_V,
                current_A,
                power_W,
                state["total_energy_Wh"]
            )

            lcd_lines = format_display_lines(
                voltage_V,
                current_A,
                power_W,
                state["total_energy_Wh"],
                alert_status
            )

            update_physical_lcd(state["lcd"], lcd_lines)

            for line in lcd_lines:
                print(line)

            state["previous_power_W"] = power_W

            time.sleep(state["sample_interval_sec"])

            print("\n")

    finally:
        if state["aws_client"] is not None:
            time.sleep(1)
            state["aws_client"].loop_stop()
            state["aws_client"].disconnect()

        if state["lcd"] is not None:
            state["lcd"].clear()
            state["lcd"].write_string("System Offline")

if __name__ == "__main__":
    main()