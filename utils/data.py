import re
import os
import sqlite3
import logging
import threading
from datetime import datetime

#To ensure only on thread is written at a time in database.
db_lock = threading.Lock()


#Removes terminal color codes and escape sequences from ADB or shell outputs.
def remove_ansi_escape_codes(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

#Converts memory strings(1G->1024MB)
def parse_top_memory(value_str):
    value_str = value_str.upper().strip()
    if value_str.endswith("G"):
        return int(float(value_str[:-1]) * 1024)
    elif value_str.endswith("M"):
        return int(float(value_str[:-1]))
    elif value_str.endswith("K"):
        return int(value_str[:-1]) / 1024
    else:
        return int(value_str)


#Extracts Logs
def parse_top_summary(lines, device_serial=None):
    data = {}
    if len(lines) < 7:
        logging.error("Insufficient top output lines.")
        return None

    try:
        #Extract Task Count
        task_line = lines[0].replace('Tasks:', '').replace(',', '')
        task_matches = re.findall(r'(\d+)\s+(\w+)', task_line)
        for value, label in task_matches:
            data[f'tasks_{label.lower()}'] = int(value)
        
        # Extract Memory
        mem_line = lines[2] if 'Mem:' in lines[2] else lines[1]
        mem_matches = re.findall(r'(\d+[KMG]?)\s+(\w+)', mem_line)
        for value_str, label in mem_matches:
            data[f'mem_{label.lower()}'] = parse_top_memory(value_str)
        
        #Extract Swap Info
        swap_line_index = 3 if mem_line == lines[2] else 2
        swap_matches = re.findall(r'(\d+)K\s+(\w+)', lines[swap_line_index])
        for value, label in swap_matches:
            data[f'swap_{label.lower()}'] = int(value)

        #Extract CPU usage
        cpu_line = lines[6]
        cpu_matches = re.findall(r'(\d+)%(\w+)', cpu_line)
        for value, label in cpu_matches:
            data[f'cpu_{label.lower()}'] = int(value)

        # Store TimeStamp and Device Info
        data['timestamp'] = datetime.now()
        if device_serial:
            data['device_serial'] = device_serial

        return data
    except Exception as e:
        logging.error(f"Parsing failed: {e}")
        return None


#Creates the SQLite database and the table schema.
def initialize_database():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    db_path = os.path.join(root_dir, 'app.db')
    logging.info(f"Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS device_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        device_serial TEXT NOT NULL,
        model TEXT,
        connection_type TEXT,
        tasks_total INTEGER,
        tasks_running INTEGER,
        tasks_sleeping INTEGER,
        tasks_stopped INTEGER,
        tasks_zombie INTEGER,
        mem_total INTEGER,
        mem_used INTEGER,
        mem_free INTEGER,
        mem_buffers INTEGER,
        swap_total INTEGER,
        swap_used INTEGER,
        swap_free INTEGER,
        swap_cached INTEGER,
        cpu_cpu INTEGER,
        cpu_user INTEGER,
        cpu_nice INTEGER,
        cpu_sys INTEGER,
        cpu_idle INTEGER,
        cpu_iow INTEGER,
        cpu_irq INTEGER,
        cpu_sirq INTEGER,
        cpu_host INTEGER
    )
    ''')

    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")
    return db_path


#inserts one complete record
def save_data_to_db(data_point):
    db_path = DATABASE_PATH
    try:
        with db_lock:
            conn = sqlite3.connect(db_path, timeout=30)
            cursor = conn.cursor()

            fields = {
                'timestamp': data_point['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                'device_serial': data_point.get('device_serial', 'unknown'),
                'model': data_point.get('model', 'Unknown'),
                'connection_type': data_point.get('connection_type', 'Unknown'),
                'tasks_total': data_point.get('tasks_total', 0),
                'tasks_running': data_point.get('tasks_running', 0),
                'tasks_sleeping': data_point.get('tasks_sleeping', 0),
                'tasks_stopped': data_point.get('tasks_stopped', 0),
                'tasks_zombie': data_point.get('tasks_zombie', 0),
                'mem_total': data_point.get('mem_total', 0),
                'mem_used': data_point.get('mem_used', 0),
                'mem_free': data_point.get('mem_free', 0),
                'mem_buffers': data_point.get('mem_buffers', 0),
                'swap_total': data_point.get('swap_total', 0),
                'swap_used': data_point.get('swap_used', 0),
                'swap_free': data_point.get('swap_free', 0),
                'swap_cached': data_point.get('swap_cached', 0),
                'cpu_cpu': data_point.get('cpu_cpu', 0),
                'cpu_user': data_point.get('cpu_user', 0),
                'cpu_nice': data_point.get('cpu_nice', 0),
                'cpu_sys': data_point.get('cpu_sys', 0),
                'cpu_idle': data_point.get('cpu_idle', 0),
                'cpu_iow': data_point.get('cpu_iow', 0),
                'cpu_irq': data_point.get('cpu_irq', 0),
                'cpu_sirq': data_point.get('cpu_sirq', 0),
                'cpu_host': data_point.get('cpu_host', 0)
            }

            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['?'] * len(fields))
            values = tuple(fields.values())

            query = f"INSERT INTO device_metrics ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)

            conn.commit()
            conn.close()
            return True
    except Exception as e:
        print(f"[ERROR] Failed to save data to database: {e}")
        return False

if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    DATABASE_PATH = initialize_database()
else:
    DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adb_monitor.db')
#Updated upstream
#Stashed changes
