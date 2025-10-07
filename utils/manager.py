import logging
import time

from utils.adb import run_adb_command, get_unique_devices, get_device_model, get_device_serial, get_device_ip, connect_wifi_adb

class NotificationManager:
    def __init__(self):
        self.current_message = ""
        self.current_class = "notification-hidden"
        self.clear_disabled = True
        self.last_update_time = 0
        self.expiry_time = 0
        self.priority = 0 
    
    def set_notification(self, message, class_name="notification-info", priority=1, duration=1):
        """Set a notification with priority level"""
        current_time = time.time()
        
        if (priority > self.priority) or (current_time > self.expiry_time):
            self.current_message = message
            self.current_class = class_name
            self.last_update_time = current_time
            self.expiry_time = current_time + duration
            self.priority = priority
            self.clear_disabled = False if message else True
            return True
        return False
    
    def clear_notification(self):
        """Clear the current notification"""
        self.current_message = ""
        self.current_class = "notification-hidden"
        self.clear_disabled = True
        self.priority = 0
        self.expiry_time = 0
    
    def get_notification_state(self):
        """Get the current notification state"""
        return self.current_message, self.current_class, self.clear_disabled


class ConnectionManager:
    """Class to manage device connections via ADB (Android Debug Bridge)"""
    def __init__(self):
        logging.debug("Initializing ConnectionManager")
        self.device_info = {
            'device_id': None,
            'model': 'Unknown',
            'connection_type': 'Unknown',
            'persistent_id': None,
            'last_device_serial': None
        }
        self.wifi_connect_ip = None
        self.wifi_connect_serial = None
        logging.debug("ConnectionManager initialized")

    def get_best_connection_for_serial(self, serial_number):
        """Return the best connection ID for a given serial number, preferring USB over WiFi"""
        devices = get_unique_devices()
        logging.info(f"Finding best connection for serial : {serial_number}")
        if serial_number in devices:
            device_ids = devices[serial_number]
            # more priority for USB connections
            for device_id in device_ids:
                if ':' not in device_id:
                    logging.info(f"Found USB connection for serial {serial_number}: {device_id}")
                    return device_id, "USB"
                    
            # if no USB, use Wifi
            for device_id in device_ids:
                if ':' in device_id:
                    logging.info(f"Found WiFi connection for serial {serial_number}: {device_id}")
                    return device_id, "Wi-Fi"
                
        return None, None
    
    def setup_device_connection(self, selected_device_id=None):
        logging.info(f"Setting up device connection with ID: {selected_device_id}")
        selected_serial = None
        if selected_device_id:
            if selected_device_id.startswith("serial:"):
                selected_serial = selected_device_id.split("serial:")[1]
                logging.info(f"Selected device by serial: {selected_serial}")
                # check which conn is avaiable for the selected serial
                best_device_id, conn_type = self.get_best_connection_for_serial(selected_serial)
                if best_device_id:
                    self.device_info['device_id'] = best_device_id
                    self.device_info['persistent_id'] = selected_serial
                    self.device_info['connection_type'] = conn_type
                    self.device_info['model'] = get_device_model(best_device_id)
                    logging.info(f"Using {conn_type} connection: {best_device_id}")
                    return True
            else:
                self.device_info['device_id'] = selected_device_id
                self.device_info['persistent_id'] = get_device_serial(selected_device_id)
                self.device_info['connection_type'] = "Wi-Fi" if ":" in selected_device_id else "USB"
                self.device_info['model'] = get_device_model(selected_device_id)
                logging.info(f"Selected device by device ID: {selected_device_id}")
                return True
        
        # No specific device selected - try to find any available device
        unique_devices = get_unique_devices()
        if not unique_devices:
            logging.error("No devices found.")
            return False
            
        # just take the first available device if not selected
        
        first_serial = next(iter(unique_devices))
        logging.info(f"No device specified, auto-selecting first available device: {first_serial}")
        best_device_id, conn_type = self.get_best_connection_for_serial(first_serial)
        
        if best_device_id:
            self.device_info['device_id'] = best_device_id
            self.device_info['persistent_id'] = first_serial
            self.device_info['connection_type'] = conn_type
            self.device_info['model'] = get_device_model(best_device_id)
            logging.info(f"Auto-selected device {first_serial} with {conn_type} connection: {best_device_id}")
            return True
        
        logging.critical("Failed to find a usable device connection.")
        return False
    
    def check_for_better_connection(self):
        """Check if there's a better connection available for the current device"""
        if not self.device_info['persistent_id']:
            return False
            
        # keep checking for USB
        if self.device_info['connection_type'] == "USB":
            return False
            
        best_device_id, conn_type = self.get_best_connection_for_serial(self.device_info['persistent_id'])
        
        if best_device_id and conn_type == "USB" and self.device_info['connection_type'] == "Wi-Fi":
            logging.info(f"Switching from Wi-Fi to USB connection: {best_device_id}")
            self.device_info['device_id'] = best_device_id
            self.device_info['connection_type'] = "USB"
            logging.info("Switched to USB connection.")
            return True
            
        return False
    
    def try_wifi_connect(self, serial_number):
        """Connect to a device via Wi-Fi using its serial number"""
                
        try:
            logging.info(f"Starting Wi-Fi connection attempt for serial: {serial_number}")
            devices = get_unique_devices()
            if serial_number not in devices:
                logging.error(f"Device with serial {serial_number} not found")
                return False, f"Device with serial {serial_number} not found. Make sure it's connected via USB first."
                
            device_ids = devices[serial_number]
            usb_device_id = None
            logging.info(f"Available device IDs for {serial_number}: {device_ids}")
            # check if already connected via Wi-Fi
            for device_id in device_ids:
                if ':' in device_id:
                    # test if the Wi-Fi connection is actually responsive
                    logging.info(f"Found existing Wi-Fi connection in device ids : {device_id}")
                    logging.info(f"Checking state of {device_id} using get-state in adb...")
                    device_state = run_adb_command(['get-state'], device_id)
                    logging.info(f"Found Wi-Fi connection, checking Wi-Fi connection state for {device_id}: {device_state}")
                    if device_state and 'device' in device_state.lower():
                        logging.info(f"Device state : {device_state}")
                        logging.info(f"Device {serial_number} is already connected via Wi-Fi at {device_id}")
                        return True, "Selected device is already connected via Wi-Fi"
                    else:
                        logging.info(f"Device {serial_number} has a stale Wi-Fi connection at {device_id}. Will reconnect.")
            
            # USB connection
            for device_id in device_ids:
                if ':' not in device_id:
                    device_state = run_adb_command(['get-state'], device_id)
                    logging.info(f"Existing Wi-Fi connection not found, checking USB connection state for {device_id}: {device_state}")
                    if device_state and 'device' in device_state.lower():
                        logging.info(f"Found active USB connection for {serial_number}: {device_id}")
                        usb_device_id = device_id
                        
            if not usb_device_id:
                logging.error(f"No active USB connection found for serial {serial_number}")
                return False, "Device must be connected via USB first. Please check your USB connection."
                
            # get the device's IP address
            ip_output = get_device_ip(usb_device_id)
            if not ip_output:
                logging.error(f"Failed to get IP address for device {usb_device_id}")
                return False, f"Failed to get device IP address for {usb_device_id}."
            else:
                logging.info(f"Found IP address: {ip_output} for {usb_device_id}")
                wifi_status = connect_wifi_adb(usb_device_id, ip_output)
            
            if wifi_status:
                logging.info(f"Connected to {usb_device_id} via Wi-Fi at {ip_output}")
                # set flags for checking connection status
                self.wifi_connect_ip = ip_output
                self.wifi_connect_serial = serial_number
                return True, f"Connecting to {serial_number} via Wi-Fi at {ip_output}... This may take a few moments."      
            else:
                logging.error(f"Failed to connect: {ip_output}")
                return False, f"Connection failed: {ip_output}. Please check device Wi-Fi settings."
                
        except Exception as e:
            logging.error(f"Error connecting via Wi-Fi: {e}")
            return False, f"Error: {str(e)}"
    
    def check_device_connection(self, device_id):
        """Check if a device connection is still valid"""
        if not device_id:
            return False
            
        device_state = run_adb_command(['get-state'], device_id)
        return device_state and 'device' in device_state.lower()
    
    def find_device_connection(self, serial_number):
        """Try to find any valid connection for a device with the given serial number"""
        if not serial_number:
            return None, None
            
        unique_devices = get_unique_devices()
        if serial_number in unique_devices:
            return self.get_best_connection_for_serial(serial_number)
            
        return None, None