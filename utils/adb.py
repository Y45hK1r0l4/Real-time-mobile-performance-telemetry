import subprocess
import time
import re
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(name)s: %(asctime)s | %(levelname)s | %(filename)s:%(lineno)s >>> %(message)s", datefmt="%d-%m-%YT%H:%M:%SZ")

# Run adb commands.
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

# To get the connected devices
def get_connected_device():
    """Get the connected USB device."""
    output = run_adb_command(['devices'])
    lines = output.splitlines()
    for line in lines[1:]:
        if 'device' in line:
            device_id = line.split()[0]
            # wifi connections have a colon
            if ':' not in device_id:
                logging.info(f"USB device connected: {device_id}")
                return device_id
    logging.debug("No USB device found.")
    return None

# get the serial number of device
def get_device_serial_number(device_id):
    """ Get the actual serial number of the device. """
    try:
        # get serial number
        result = subprocess.run(
            ['adb', '-s', device_id, 'shell', 'getprop', 'ro.serialno'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            logging.error(f"Unable to retrieve retrieving serial number for device {device_id}")
            return None
        return result.stdout.strip()
    except Exception as e:
        logging.error(f"Exception while retrieving serial number: {e}")
        return None

#Gets unique devices(no repetitions)
def get_unique_devices():
    result = subprocess.run(['adb', 'devices'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # check if adb is installed.
    if result.returncode != 0:
        logging.critical("adb is not installed or not working correctly.")
        return {}
    
    # parse the output
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
    
    # unique devices based on the actual serial number
    logging.debug("Monitoring for unique devices based on serial numbers:")
    if devices:
        for serial, device_ids in devices.items():
            pass
            logging.debug(f"Serial Number: {serial} -> Device IDs: {', '.join(device_ids)}")
    else:
        logging.debug("No devices found.")
    
    return devices

# Extract model of device
def get_device_model(device_id):
    output = run_adb_command(['shell', 'getprop', 'ro.product.model'], device_id)
    return output.strip() if output else 'Unknown'

# Extract ip of device
def get_device_ip(device_id):
    output = run_adb_command(['shell', 'ip', 'addr', 'show', 'wlan0'], device_id)
    match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', output)
    return match.group(1) if match else None

# Establish connection through wifi.
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

# Get serial number of device
def get_device_serial(device_id):
    output = run_adb_command(['shell', 'getprop', 'ro.serialno'], device_id)
    return output.strip() if output else None


# Check number of initial devices connected during startup
def check_initial_devices():
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
    
# To Check the battery status
def get_battery_status(device_id):
    output = run_adb_command(['shell', 'dumpsys', 'battery'], device_id)
    battery_info = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('level:'):
            battery_info['level'] = int(line.split(':')[1].strip())
        elif line.startswith('temperature:'):
            battery_info['temperature'] = int(line.split(':')[1].strip()) / 10.0
    return battery_info
    

    # Check at startup
if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    has_devices = check_initial_devices()