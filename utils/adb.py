import subprocess
import time
import re
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(asctime)s | %(levelname)s | %(filename)s:%(lineno)s >>> %(message)s",
    datefmt="%d-%m-%YT%H:%M:%SZ"
)


def run_adb_command(cmd, device_id=None):
    """Run an adb command and return the output."""
    base_cmd = ['adb']
    if device_id:
        base_cmd += ['-s', device_id]
    base_cmd += cmd
    try:
        result = subprocess.run(base_cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Command {cmd} timed out.")
        return None


def get_connected_device():
    """Get the connected USB device."""
    output = run_adb_command(['devices'])
    lines = output.splitlines()
    for line in lines[1:]:
        if 'device' in line:
            device_id = line.split()[0]
            # Wi-Fi connections have a colon
            if ':' not in device_id:
                logging.info(f"USB device connected: {device_id}")
                return device_id
    logging.debug("No USB device found.")
    return None


def get_device_serial_number(device_id):
    """Get the actual serial number of the device."""
    try:
        result = subprocess.run(
            ['adb', '-s', device_id, 'shell', 'getprop', 'ro.serialno'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            logging.error(f"Unable to retrieve serial number for device {device_id}")
            return None
        return result.stdout.strip()
    except Exception as e:
        logging.error(f"Exception while retrieving serial number: {e}")
        return None


def get_unique_devices():
    """Return unique devices based on serial numbers."""
    result = subprocess.run(['adb', 'devices'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logging.critical("adb is not installed or not working correctly.")
        return {}

    devices = {}
    lines = result.stdout.strip().split('\n')
    for line in lines[1:]:
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                serial, status = parts[0], parts[1]
                if status == 'device':
                    actual_serial = get_device_serial(serial)
                    if actual_serial:
                        if actual_serial not in devices:
                            devices[actual_serial] = []
                        devices[actual_serial].append(serial)

    if devices:
        for serial, device_ids in devices.items():
            logging.debug(f"Serial Number: {serial} -> Device IDs: {', '.join(device_ids)}")
    else:
        logging.debug("No devices found.")

    return devices


def get_device_model(device_id):
    output = run_adb_command(['shell', 'getprop', 'ro.product.model'], device_id)
    return output.strip() if output else 'Unknown'


def get_device_ip(device_id):
    output = run_adb_command(['shell', 'ip', 'addr', 'show', 'wlan0'], device_id)
    match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', output)
    return match.group(1) if match else None


def connect_wifi_adb(device_id, ip, port=5555):
    logging.info(f"Enabling ADB over TCP/IP on port {port}...")
    run_adb_command(['tcpip', str(port)], device_id)
    time.sleep(2)
    logging.info(f"Trying to connect to {ip}:{port}...")
    output = run_adb_command(['connect', f'{ip}:{port}'])
    if output and 'connected' in output.lower():
        logging.info(f"Connected to {ip}:{port}")
        return True
    logging.error(f"Could not connect to {ip}:{port}: {output}")
    return False


def get_device_serial(device_id):
    output = run_adb_command(['shell', 'getprop', 'ro.serialno'], device_id)
    return output.strip() if output else None


def check_initial_devices():
    """Check if any devices are connected at startup."""
    try:
        output = run_adb_command(['devices'])
        if output:
            lines = output.strip().split('\n')[1:]
            for line in lines:
                if line.strip() and 'device' in line:
                    logging.info(f"Device available at startup: {line.split()[0]}")
                    return True
        logging.info("No devices available at startup")
        return False
    except Exception as e:
        logging.error(f"Error checking initial devices: {e}")
        return False


def get_battery_status(device_id):
    """Fetch battery level and temperature."""
    output = run_adb_command(['shell', 'dumpsys', 'battery'], device_id)
    battery_info = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('level:'):
            battery_info['level'] = int(line.split(':')[1].strip())
        elif line.startswith('temperature:'):
            battery_info['temperature'] = int(line.split(':')[1].strip()) / 10.0
    return battery_info


# 🧠 NEW FUNCTION: Get CPU temperature via ADB
def get_cpu_temperature(device_id):
    """
    Attempt to read CPU temperature from the Android device.
    Tries multiple thermal zones until a valid temperature is found.
    """
    possible_paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone1/temp",
        "/sys/class/thermal/thermal_zone2/temp",
        "/sys/class/thermal/thermal_zone3/temp"
    ]

    for path in possible_paths:
        cmd = ['shell', 'cat', path]
        output = run_adb_command(cmd, device_id)
        if output and output.isdigit():
            temp_c = round(int(output) / 1000, 1) if int(output) > 1000 else int(output)
            logging.debug(f"CPU temperature from {path}: {temp_c}°C")
            return temp_c

    logging.warning(f"Could not read CPU temperature from any known path for {device_id}.")
    return None


# Check at startup
if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    has_devices = check_initial_devices()
