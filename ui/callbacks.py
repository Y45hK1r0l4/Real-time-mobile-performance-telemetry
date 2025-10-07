import time
import logging
import dash
import plotly.graph_objs as go
from dash.dependencies import Input, Output, State
from dash import html
from utils.adb import get_device_model, get_unique_devices
from utils.manager import NotificationManager

def register_callbacks(
    app, connection_manager, monitoring_state, monitoring_controller
):
    notification_manager = NotificationManager()

    @app.callback(
        Output("device-dropdown", "options"),
        [
            Input("device-check-interval", "n_intervals"),
            Input("refresh-button", "n_clicks"),
        ],
    )
    def update_device_dropdown(_, refresh_clicks):
        """Update the device dropdown list with available devices"""
        # get unique devices first.
        unique_devices = get_unique_devices()
        options = []

        for serial_number, device_ids in unique_devices.items():
            model = get_device_model(device_ids[0])
            usb_available = any(":" not in dev_id for dev_id in device_ids)
            wifi_available = any(":" in dev_id for dev_id in device_ids)

            # connection type indicators
            conn_types = []
            if usb_available:
                conn_types.append("USB")
            if wifi_available:
                conn_types.append("Wi-Fi")

            conn_type_str = " & ".join(conn_types)

            # don't remove serial_number from the option text, this is parsed by wifi_connect!
            # improve logic later
            option_text = f"{model} - Serial: {serial_number} ({conn_type_str})"
            options.append({"label": option_text, "value": f"serial:{serial_number}"})
        
        return options

    @app.callback(Input("clear-button", "n_clicks"), prevent_initial_call=True)
    def clear_data(n_clicks):
        """Clear data button callback"""
        if n_clicks>0:
            logging.info("Clear data button clicked.")
            # also tries to clear notifications.
            notification_manager.clear_notification()
            # also handle clear data functionality
            if len(monitoring_state.collected_data) == 0:
                logging.warning("No data to clear.")
                notification_manager.set_notification(
                    "No data to clear.", "notification-error", priority=3
                )
            else:
                monitoring_state.collected_data.drop(
                    monitoring_state.collected_data.index, inplace=True
                )
                monitoring_state.total_points = 0
                logging.info("Data cleared.")
                notification_manager.set_notification(
                    "Data cleared.", "notification-success", priority=3
                )
            
    @app.callback(Input("save-to-db-dropdown", "value"))
    def handle_save_to_db(save_value):
        """Handle save to DB dropdown changes"""

        monitoring_state.save_to_local_db = save_value == "save"
        msg = (
            "Saving to local database is enabled."
            if monitoring_state.save_to_local_db
            else "Saving to local database is disabled."
        )

        notification_manager.set_notification(
            msg,
            "notification-success"
            if monitoring_state.save_to_local_db
            else "notification-error",
            priority=3,
        )

    @app.callback([Input("wifi-connect-button", "n_clicks")],[State("device-dropdown", "value")])
    def handle_wifi_connect(n_clicks,selected_device):
        """Handle Wi-Fi connect button clicks"""
        if n_clicks > 0:
            logging.info("Wi-Fi connect button clicked.")
            # check if a device is selected
            if not selected_device:
                logging.error("No device was selected for initiating Wi-Fi connection.")
                notification_manager.set_notification(
                    "No device selected. Please select a device first.",
                    "notification-error",
                    priority=5,
                )
            else:
                # check if device is already connected via Wi-Fi
                serial_number = selected_device.split("serial:")[1]
                current_devices = get_unique_devices()
                if len(current_devices[serial_number])>0:
                    logging.info("Found USB connection of device, trying to connect via Wi-Fi")
                    success, message = connection_manager.try_wifi_connect(serial_number)
                    class_name = "notification-success" if success else "notification-error"
                    notification_manager.set_notification(message, class_name, priority=5)
                else:
                    logging.info("No USB connection was found for selected device.")
                    notification_manager.set_notification("Device must be connected via USB first.","notification-error",priority=5)

    @app.callback(
    Output("mini-cpu-user", "children"),
    Output("mini-cpu-sys", "children"),
    Output("mini-cpu-idle", "children"),
    Output("mini-mem-used", "children"),
    Output("mini-tasks-running", "children"),
    Output("mini-batt-level", "children"),
    Input("interval-component", "n_intervals")
    )
    def update_mini_metrics(n_intervals):
        latest = monitoring_state.collected_data.iloc[-1] if not monitoring_state.collected_data.empty else {}
        return (
            latest.get("cpu_user", "--"),
            latest.get("cpu_sys", "--"),
            latest.get("cpu_idle", "--"),
            latest.get("mem_used", "--"),
            latest.get("tasks_running", "--"),
            latest.get("battery_level", "--"),
        )



    @app.callback(
        Output("general-notification", "children"),
        Output("general-notification", "className"),
        Output("notification-clear-interval", "disabled"),
        [
            Input("interval-component", "n_intervals"),
            Input("notification-clear-interval", "n_intervals"),
        ],prevent_initial_call=True,
    )
    def notification_handler(
        interval_check,
        notification_clear_interval,
    ):
        """handler for all notification-related events"""


        ctx = dash.callback_context
        if not ctx.triggered:

            return "", "notification-hidden", True, False

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if trigger_id == "notification-clear-interval":
            current_time = time.time()
            if current_time > notification_manager.expiry_time:
                notification_manager.clear_notification()

        message, class_name, clear_disabled = (
            notification_manager.get_notification_state()
        )
        return message, class_name, clear_disabled

    @app.callback(
        Output("app-plot", "figure"),
        [
            Input("interval-component", "n_intervals"),
            Input("stop-button", "n_clicks"),
            Input("metric-selector-dropdown", "value"),
            Input("specific-metrics-dropdown", "value"),
        ],
        [
            State("app-plot", "figure"),
            State("available-metrics-store", "data"),
        ],
    )

    def update_graph(_, stop_clicks, metric, selected_metrics, current_fig, available_metrics):
        fig = go.Figure()
        df = monitoring_state.collected_data

        labels = {
            "cpu": {
                "all_metrics": [
                    "cpu_cpu", "cpu_user", "cpu_nice", "cpu_sys", "cpu_idle",
                    "cpu_iow", "cpu_irq", "cpu_sirq", "cpu_host"
                ],
                "ylabel": "CPU Usage (%)",
                "max": 100,
            },
            "mem": {
                "all_metrics": [
                    "mem_total", "mem_used", "mem_free", "mem_buffers",
                    "swap_total", "swap_used", "swap_free", "swap_cached"
                ],
                "ylabel": "Memory (MB)",
                "max": 4096,
            },
            "task": {
                "all_metrics": [
                    "tasks_total", "tasks_running", "tasks_sleeping",
                    "tasks_stopped", "tasks_zombie"
                ],
                "ylabel": "Task Count",
                "max": 100,
            },
            "battery": {
                "all_metrics": ["battery_level", "battery_temp"],
                "ylabel": "Battery",
                "max": 100,
            }
        }

        if metric in labels:
            all_metrics = labels[metric]["all_metrics"]
            ylabel = labels[metric]["ylabel"]
            y_max = labels[metric]["max"]
        else:
            all_metrics = []
            ylabel = "Value"
            y_max = 100

        # Only keep selected metrics if any are chosen, else all by default
        metrics = [m for m in all_metrics if selected_metrics and m in selected_metrics] or all_metrics

        # Add traces for all selected metrics
        if not df.empty:
            for m in metrics:
                if m in df.columns:
                    name = m.replace("cpu_", "").replace("mem_", "").replace("tasks_", "").capitalize()
                    fig.add_trace(
                        go.Scatter(
                            x=df["timestamp"], y=df[m], mode="lines+markers", name=name
                        )
                    )
        fig.update_layout(
            title="",
            xaxis_title="Time",
            yaxis_title=ylabel,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            margin=dict(l=40, r=40, t=50, b=40),
            hovermode="closest",
            template="plotly_white",
            yaxis=dict(range=[0, y_max], autorange=True),
        )

        return fig

    @app.callback(
        [Output("specific-metrics-dropdown", "options"),
        Output("specific-metrics-dropdown", "value"),
        Output("available-metrics-store", "data")],
        [Input("metric-selector-dropdown", "value")]
    )
    def update_specific_metrics_options(metric_category):
        """Update the specific metrics dropdown options based on the selected category."""
        if metric_category == "cpu":
            metrics = [
                {"label": "CPU Overall", "value": "cpu_cpu"},
                {"label": "User", "value": "cpu_user"},
                {"label": "Nice", "value": "cpu_nice"},
                {"label": "System", "value": "cpu_sys"},
                {"label": "Idle", "value": "cpu_idle"},
                {"label": "I/O Wait", "value": "cpu_iow"},
                {"label": "IRQ", "value": "cpu_irq"},
                {"label": "Soft IRQ", "value": "cpu_sirq"},
                {"label": "Host", "value": "cpu_host"},
            ]
        elif metric_category == "mem":
            metrics = [
                {"label": "Total Memory", "value": "mem_total"},
                {"label": "Used Memory", "value": "mem_used"},
                {"label": "Free Memory", "value": "mem_free"},
                {"label": "Buffers", "value": "mem_buffers"},
                {"label": "Swap Total", "value": "swap_total"},
                {"label": "Swap Used", "value": "swap_used"},
                {"label": "Swap Free", "value": "swap_free"},
                {"label": "Swap Cached", "value": "swap_cached"},
            ]
        elif metric_category == "task":
            metrics = [
                {"label": "Total Tasks", "value": "tasks_total"},
                {"label": "Running Tasks", "value": "tasks_running"},
                {"label": "Sleeping Tasks", "value": "tasks_sleeping"},
                {"label": "Stopped Tasks", "value": "tasks_stopped"},
                {"label": "Zombie Tasks", "value": "tasks_zombie"},
            ]
        else:
            metrics = []
        
        metric_values = [m["value"] for m in metrics]
        
        return metrics, [], metric_values
    
    @app.callback(
    Output("chip-status", "children"),
    Output("chip-device", "children"),
    Output("chip-conn", "children"),
    Output("chip-points", "children"),
    Input("interval-component", "n_intervals")
    )
    def _chip_update(_):
        status = "Active" if monitoring_state.monitoring_active else ("Paused" if monitoring_state.monitoring_paused else "Idle")
        dev = connection_manager.device_info.get("model","–")
        conn = connection_manager.device_info.get("connection_type","–")
        pts = str(monitoring_state.total_points)
        return status, dev, conn, pts
    
    @app.callback(
    Output("device-id-title", "children"),
    Output("device-id-conn", "children"),
    Input("interval-component", "n_intervals")
    )
    def update_device_title(_):
        dev = connection_manager.device_info.get("model", "No Device")
        conn = connection_manager.device_info.get("connection_type", "")
        return dev, conn



    @app.callback(
        Output("start-button", "disabled"),
        Output("stop-button", "disabled"),
        Output("device-dropdown", "disabled"),
        Output("interval-input", "disabled"),
        Output("refresh-button", "disabled"),
        Output("save-to-db-dropdown", "disabled"),
        Output("device-dropdown", "value"),
        [
            Input("start-button", "n_clicks"),
            Input("stop-button", "n_clicks"),
            Input("device-check-interval", "n_intervals"),
        ],
        [State("interval-input", "value"), State("device-dropdown", "value")],
        prevent_initial_call=True,
    )
    def manage_monitoring(
        start_clicks, stop_clicks, n_intervals, interval_value, selected_device
    ):
        ctx = dash.callback_context
        trigger_id = (
            ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None
        )
        
        if monitoring_state.auto_stopped:
            logging.info("Auto-stopped state detected.")
            monitoring_state.auto_stopped = False
            return False, True, False, False, False, False, selected_device
        

        if selected_device is None:

            unique_devices = get_unique_devices()
            if unique_devices:

                first_serial = next(iter(unique_devices))
                logging.info(f"No device specified, auto-selecting first available device: {first_serial}")

                first_device_value = f"serial:{first_serial}"
                logging.info(f"Auto-selected device value: {first_device_value}")
                selected_device = first_device_value
        
        if trigger_id == "device-dropdown" and monitoring_state.monitoring_active:
            # a change occured in device-dropdown while monitoring was active
            # most likely, device lost connection, since device controls are disabled during monitoring
            if selected_device is None:
                logging.critical("Lost connection while monitoring.")
                monitoring_state.monitoring_paused = True


        if trigger_id == "start-button" and start_clicks > 0:
            if not monitoring_state.monitoring_active:
                try:
                    logging.info("Start Button clicked. Initiate monitoring...")
                    monitoring_state.current_device = selected_device
                    logging.info(f"Device which is selected for monitoring is : {monitoring_state.current_device}")
                    success = monitoring_controller.start_monitoring(
                        monitoring_interval=interval_value, selected_device_id=selected_device
                    )
                    logging.info(f"Monitoring started: {success}")
                except Exception as e:
                    logging.error(f"Error starting monitoring: {e}")
                logging.info(
                    f"Monitoring start {'successful' if success else 'failed'}"
                )

                return True, False, True, True, True, True, selected_device
        
        elif trigger_id == "stop-button" and stop_clicks > 0:
            if monitoring_state.monitoring_active:
                monitoring_controller.stop_monitoring()

                return False, True, False, False, False, False, selected_device
        

        return (
            monitoring_state.monitoring_active,
            not monitoring_state.monitoring_active,
            monitoring_state.monitoring_active,
            monitoring_state.monitoring_active,
            monitoring_state.monitoring_active,
            monitoring_state.monitoring_active,
            selected_device,
        )
    return notification_manager