from dash import dcc, html

def create_layout():
    layout = html.Div([
        # Header
        html.Div([
            html.Div([
                html.Div([
                    html.Div("DEVICE MONITOR", className="hdr-title"),
                    html.Div("Real-time Android performance telemetry", className="hdr-sub")
                ], className="hdr-left"),
                html.Div([
                    html.Div([
                        html.Span("STATUS", className="chip-k"),
                        html.Span(id="chip-status", className="chip-v")
                    ], className="chip"),
                    html.Div([
                        html.Span("DEVICE", className="chip-k"),
                        html.Span(id="chip-device", className="chip-v")
                    ], className="chip"),
                    html.Div([
                        html.Span("CONN", className="chip-k"),
                        html.Span(id="chip-conn", className="chip-v")
                    ], className="chip"),
                    html.Div([
                        html.Span("POINTS", className="chip-k"),
                        html.Span(id="chip-points", className="chip-v")
                    ], className="chip"),
                ], className="hdr-right")
            ], className="hdr-row"),
        ], className="hdr-card"),

        # Main grid
        html.Div([
            # Left sidebar
            html.Div([
                html.Div([
                    html.Div(id="device-id-title", className="device-id-title"),
                    html.Div(id="device-id-conn", className="device-id-conn")
                ], className="device-id-container"),     # <--- device name, always at sidebar top

                html.Div([
                    html.Div([
                        html.Label("Device:", className="lbl"),
                        dcc.Dropdown(
                            id='device-dropdown',
                            options=[], clearable=False,
                            className="w-100 ddl"
                        ),
                        html.Div([
                            html.Button('Refresh', id='refresh-button', n_clicks=0, className="btn"),
                            html.Button('Wi‑Fi Connect', id='wifi-connect-button', n_clicks=0, className="btn secondary"),
                        ], className="row gap")
                    ])
                ], className="card"),
                html.Div([
                    html.Div([
                        html.Label("Monitor every", className="lbl"),
                        dcc.Input(id='interval-input', type='number', min=1, max=60, value=5, className="num"),
                        html.Span("s", className="unit"),
                        dcc.Dropdown(
                            id='save-to-db-dropdown',
                            options=[
                                {'label': 'Save to DB', 'value': 'save'},
                                {'label': "Do not save", 'value': 'dont_save'}
                            ], value='save', clearable=False, searchable=False,
                            className="ddl compact"
                        ),
                    ], className="row gap wrap"),
                    html.Div([
                        html.Button('Start', id='start-button', n_clicks=0, className="btn primary"),
                        html.Button('Stop', id='stop-button', n_clicks=0, disabled=True, className="btn danger"),
                        html.Button('Clear', id='clear-button', n_clicks=0, className="btn ghost"),
                    ], className="row gap")
                ], className="card"),
                html.Div([
                    html.Div([
                        html.Label("For", className="lbl"),
                        dcc.Dropdown(
                            id='metric-selector-dropdown',
                            options=[
                                {'label': 'CPU', 'value': 'cpu'},
                                {'label': 'Memory', 'value': 'mem'},
                                {'label': 'Task', 'value': 'task'},
                                {'label': 'Battery', 'value': 'battery'}
                            ], value='cpu', clearable=False, searchable=False,
                            className="ddl sm"
                        ),
                        html.Label("show", className="lbl"),
                        dcc.Dropdown(
                            id='specific-metrics-dropdown',
                            options=[], value=[], multi=True,
                            placeholder="All metrics (select to filter)",
                            className="ddl lg"
                        ),
                    ], className="row gap wrap"),
                ], className="card"),
            ], className="col left"),

            # Right panel
            html.Div([
                html.Div([
                    dcc.Graph(
                        id='app-plot',
                        style={'height': '530px', 'width': '100%'},
                        config={"displayModeBar": False}
                    )
                ], className="card stretch"),
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div("CPU User", className="mini-k"),
                            html.Div(id="mini-cpu-user", className="mini-v")
                        ], className="mini"),
                        html.Div([
                            html.Div("CPU Sys", className="mini-k"),
                            html.Div(id="mini-cpu-sys", className="mini-v")
                        ], className="mini"),
                        html.Div([
                            html.Div("Idle", className="mini-k"),
                            html.Div(id="mini-cpu-idle", className="mini-v")
                        ], className="mini"),
                        html.Div([
                            html.Div("Mem Used", className="mini-k"),
                            html.Div(id="mini-mem-used", className="mini-v")
                        ], className="mini"),
                        html.Div([
                            html.Div("Tasks Run", className="mini-k"),
                            html.Div(id="mini-tasks-running", className="mini-v")
                        ], className="mini"),
                        html.Div([
                            html.Div("Battery", className="mini-k"),
                            html.Div(id="mini-batt-level", className="mini-v")
                        ], className="mini"),
                    ], className="mini-grid")
                ], className="card"),
            ], className="col right"),
        ], className="grid-2"),

        # Notifications, connection status, intervals & stores
        html.Div(id='connection-status', className='device-status-box band'),
        html.Div([
            html.Div(id='general-notification', className='notification-hidden'),
            dcc.Interval(id='notification-clear-interval', interval=1500, n_intervals=0, disabled=True),
        ], className="block"),
        dcc.Interval(id='interval-component', interval=1000, n_intervals=0),
        dcc.Interval(id='device-check-interval', interval=2000, n_intervals=0),
        html.Div(id='auto-stopped-state', style={'display': 'none'}),
        dcc.Store(id='available-metrics-store'),
    ], className='dash-container complex')

    return layout
