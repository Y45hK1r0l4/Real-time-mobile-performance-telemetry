import dash
import logging
import sys
import os

from utils.manager import ConnectionManager
from utils.monitoring import MonitoringState
from utils.monitoring import MonitoringController
from ui.callbacks import register_callbacks
from ui.layout import create_layout

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(name)s: %(asctime)s | %(levelname)s | %(filename)s:%(lineno)s >>> %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
    force=True
)

# Initialize core components
connection_manager = ConnectionManager()
monitoring_state = MonitoringState()
monitoring_controller = MonitoringController(connection_manager, monitoring_state)

# Initialize Dash app
app = dash.Dash(__name__, update_title=None)
app.title = "Real-time-mobile-performance-telemetry"

# Define app layout
app.layout = create_layout()

# Register all callbacks
notification_manager = register_callbacks(app, connection_manager, monitoring_state, monitoring_controller)
monitoring_controller.notification_manager = notification_manager

if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        logging.info("Starting ADB CPU Monitor Dashboard")
        logging.info("Please start monitoring using the dashboard controls")
    app.run(debug=True)