import logging
import pandas as pd
import threading
import time
from utils.data import save_data_to_db, remove_ansi_escape_codes, parse_top_summary
from utils.adb import get_battery_status, run_adb_command, get_cpu_temperature


class MonitoringController:
    def __init__(self, connection_manager, monitoring_state):
        self.connection_manager = connection_manager
        self.state = monitoring_state
        self.notification_manager = None

    def start_monitoring(self, interval=5, selected_device_id=None, monitoring_interval=2):
        if self.state.monitoring_active:
            logging.warning("Monitoring already active.")
            return False

        self.state.auto_stopped = False
        self.state.monitoring_interval = monitoring_interval

        if not self.connection_manager.setup_device_connection(selected_device_id):
            logging.error("Failed to set up device connection.")
            return False

        self.state.monitoring_active = True
        self.state.monitoring_thread = threading.Thread(target=self._monitor_device)
        self.state.monitoring_thread.daemon = True
        self.state.monitoring_thread.start()

        logging.info(f"Started monitoring with {self.state.monitoring_interval}s interval.")
        return True

    def stop_monitoring(self):
        if not self.state.monitoring_active:
            logging.warning("Monitoring not active.")
            return

        self.state.reset_monitoring_state()

        if self.state.monitoring_thread:
            self.state.monitoring_thread.join(timeout=1.0)

        logging.info("Monitoring stopped.")

    def _monitor_device(self):
        """Main monitoring loop with state-based handling"""
        while self.state.monitoring_active:
            try:
                if self.state.monitoring_paused:
                    self._handle_paused_state()
                else:
                    self._handle_active_monitoring()
            except Exception as e:
                logging.error(f"Monitoring error: {e}")

            time.sleep(self.state.monitoring_interval)

    def _handle_paused_state(self):
        """Handle monitoring when in paused state (reconnection)"""
        logging.info(f"Entering Paused state with a timeout of {self.state.max_pause_duration}")
        logging.info(f"Time left until waiting timeout : {self.state.pause_start_time + self.state.max_pause_duration - time.time()}")
        if self.notification_manager:
            self.notification_manager.set_notification("Monitoring paused.", "notification-error", 4)

        # Check for timeout
        if (
            self.state.pause_start_time
            and (time.time() - self.state.pause_start_time) > self.state.max_pause_duration
        ):
            logging.warning(f"Device reconnection timed out after {self.state.max_pause_duration} seconds. Stopping monitoring.")
            if self.notification_manager:
                self.notification_manager.set_notification(
                    "Monitoring stopped due to wait timeout.", "notification-error", 5
                )
            self.state.auto_stopped = True
            self.state.monitoring_active = False
            self.state.monitoring_paused = False
            return

        # Try to reconnect
        current_serial = self.connection_manager.device_info["persistent_id"]
        best_device_id, conn_type = self.connection_manager.find_device_connection(current_serial)

        if best_device_id:
            self.connection_manager.device_info["device_id"] = best_device_id
            self.connection_manager.device_info["connection_type"] = conn_type

            if self.connection_manager.check_device_connection(best_device_id):
                self.state.monitoring_paused = False
                self.state.pause_start_time = None
                self.state.reconnection_success = True
                logging.info(f"Successfully reconnected to device {current_serial} via {conn_type}")
                if self.notification_manager:
                    self.notification_manager.set_notification(
                        f"Successfully reconnected to device {current_serial} via {conn_type}",
                        "notification-success",
                        5,
                    )
                return

        self.state.reconnect_attempts += 1

    def _handle_active_monitoring(self):
        """Handle normal active monitoring state"""
        current_device_id = self.connection_manager.device_info["device_id"]

        if self.connection_manager.device_info["connection_type"] == "Wi-Fi":
            self.connection_manager.check_for_better_connection()

        if not self.connection_manager.check_device_connection(current_device_id):
            self._handle_connection_lost()
            return

        self._collect_device_data()

    def _handle_connection_lost(self):
        """Handle case when device connection is lost"""
        current_serial = self.connection_manager.device_info["persistent_id"]
        logging.warning(f"Device connection lost for {current_serial}")

        best_device_id, conn_type = self.connection_manager.find_device_connection(current_serial)

        if best_device_id and self.connection_manager.check_device_connection(best_device_id):
            self.connection_manager.device_info["device_id"] = best_device_id
            self.connection_manager.device_info["connection_type"] = conn_type
            logging.info(f"Reconnected to same device via {conn_type}: {best_device_id}")
        else:
            self.state.monitoring_paused = True
            self.state.pause_start_time = time.time()
            self.state.reconnect_attempts = 1
            logging.warning(f"Device {current_serial} disconnected. Monitoring paused.")

    def _collect_device_data(self):
        """Collect and process device data"""
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                raw_output = run_adb_command(["shell", "top", "-n", "1"], self.connection_manager.device_info["device_id"])

                if not raw_output:
                    if attempt < max_retries - 1:
                        logging.warning(f"No output received. Retry {attempt + 1}/{max_retries}...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logging.error("Failed to get data after max retries")
                        return

                clean_output = remove_ansi_escape_codes(raw_output)
                lines = clean_output.splitlines()

                data = parse_top_summary(
                    lines,
                    device_serial=self.connection_manager.device_info["persistent_id"],
                )

                if data:
                    device_id = self.connection_manager.device_info["device_id"]
                    conn_type = "Wi-Fi" if ":" in device_id else "USB"
                    if conn_type != self.connection_manager.device_info["connection_type"]:
                        self.connection_manager.device_info["connection_type"] = conn_type

                    data["model"] = self.connection_manager.device_info["model"]
                    data["connection_type"] = self.connection_manager.device_info["connection_type"]

                    # ==== New metrics fetching ====
                    battery_data = get_battery_status(device_id)
                    data["battery_level"] = battery_data.get("level", None)
                    data["battery_temp"] = battery_data.get("temperature", None)

                    # 🧠 CPU Temperature
                    cpu_temp = get_cpu_temperature(device_id)
                    data["cpu_temp"] = cpu_temp
                    logging.debug(f"CPU temperature collected: {cpu_temp}°C")

                    # ==== End new metrics ====

                    # Save to local DB if enabled
                    if self.state.save_to_local_db:
                        save_data_to_db(data)

                    # Device change handling and add to in-memory state
                    self._handle_device_change()
                    self.state.add_data_point(data)

                break

            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Error collecting data: {e}. Retry {attempt + 1}/{max_retries}...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Failed to collect data after {max_retries} attempts: {e}")

    def _handle_device_change(self):
        """Handle case when monitored device has changed"""
        if self.connection_manager.device_info["last_device_serial"] is None:
            self.connection_manager.device_info["last_device_serial"] = (
                self.connection_manager.device_info["persistent_id"]
            )
        elif self.connection_manager.device_info["last_device_serial"] != self.connection_manager.device_info["persistent_id"]:
            self.state.total_points = 0
            logging.info(
                f"Device changed from {self.connection_manager.device_info['last_device_serial']} to {self.connection_manager.device_info['persistent_id']}, clearing plot data"
            )
            self.state.collected_data.drop(self.state.collected_data.index, inplace=True)
            self.connection_manager.device_info["last_device_serial"] = (
                self.connection_manager.device_info["persistent_id"]
            )


class MonitoringState:
    def __init__(self):
        self.current_device = None
        self.monitoring_active = False
        self.monitoring_paused = False
        self.monitoring_thread = None
        self.monitoring_interval = 5
        self.auto_stopped = False
        self.save_to_local_db = True
        self.collected_data = pd.DataFrame()
        self.total_points = 0
        self.reconnect_attempts = 0
        self.pause_start_time = None
        self.max_pause_duration = 30
        self.reconnection_success = False

    def reset_reconnection_state(self):
        """Reset all reconnection-related state variables"""
        self.monitoring_paused = False
        self.reconnect_attempts = 0
        self.pause_start_time = None
        self.reconnection_success = False

    def reset_monitoring_state(self):
        """Reset monitoring state when stopping monitoring"""
        self.monitoring_active = False
        self.auto_stopped = False
        self.reset_reconnection_state()

    def clear_data(self):
        """Clear collected data"""
        self.collected_data.drop(self.collected_data.index, inplace=True)
        self.total_points = 0
        logging.info("Data cleared.")
        return True

    def add_data_point(self, data):
        new_df = pd.DataFrame([data])
        self.collected_data = pd.concat([self.collected_data, new_df], ignore_index=True)
        self.total_points += 1
        logging.debug(f"Added data point {self.total_points}, keys: {list(data.keys())}")
        cpu_keys = [k for k in data.keys() if k.startswith('cpu_')]
        logging.debug(f"CPU metric keys with values: {{}}".format({k: data[k] for k in cpu_keys}))
        if len(self.collected_data) > 100:
            self.collected_data = self.collected_data.iloc[-100:]
