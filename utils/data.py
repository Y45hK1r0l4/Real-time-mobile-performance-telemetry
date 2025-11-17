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

    # Devices table to track devices
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_serial TEXT UNIQUE NOT NULL,
        model TEXT,
        connection_type TEXT,
        cpu_table TEXT,
        memory_table TEXT,
        tasks_table TEXT,
        swap_table TEXT,
        battery_table TEXT
    )
    ''')

    # Check for missing columns and add if necessary
    cursor.execute("PRAGMA table_info(devices);")
    existing_cols = [r[1] for r in cursor.fetchall()]
    for col in ['cpu_table', 'memory_table', 'tasks_table', 'swap_table', 'battery_table']:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE devices ADD COLUMN {col} TEXT;")

    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")
    return db_path

def create_device_tables(conn, device_serial):
    sanitized = re.sub(r'\W+', '_', device_serial.lower())
    cpu_table = f"{sanitized}_cpu"
    memory_table = f"{sanitized}_memory"
    tasks_table = f"{sanitized}_tasks"
    swap_table = f"{sanitized}_swap"
    battery_table = f"{sanitized}_battery"

    cursor = conn.cursor()
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {cpu_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
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
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {memory_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        mem_total INTEGER,
        mem_used INTEGER,
        mem_free INTEGER,
        mem_buffers INTEGER
    )
    ''')
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {tasks_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        tasks_total INTEGER,
        tasks_running INTEGER,
        tasks_sleeping INTEGER,
        tasks_stopped INTEGER,
        tasks_zombie INTEGER
    )
    ''')
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {swap_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        swap_total INTEGER,
        swap_used INTEGER,
        swap_free INTEGER,
        swap_cached INTEGER
    )
    ''')
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {battery_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        battery_level INTEGER,
        battery_health TEXT,
        battery_temperature REAL,
        charging_status TEXT
    )
    ''')
    conn.commit()
    return cpu_table, memory_table, tasks_table, swap_table, battery_table

def get_or_create_device(conn, device_serial, model='Unknown', connection_type='Unknown'):
    cursor = conn.cursor()
    cursor.execute("SELECT id, cpu_table, memory_table, tasks_table, swap_table, battery_table FROM devices WHERE device_serial=?", (device_serial,))
    row = cursor.fetchone()
    if row:
        return row
    else:
        cpu_table, memory_table, tasks_table, swap_table, battery_table = create_device_tables(conn, device_serial)
        cursor.execute('''
        INSERT INTO devices (device_serial, model, connection_type, cpu_table, memory_table, tasks_table, swap_table, battery_table)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (device_serial, model, connection_type, cpu_table, memory_table, tasks_table, swap_table, battery_table))
        conn.commit()
        device_id = cursor.lastrowid
        return (device_id, cpu_table, memory_table, tasks_table, swap_table, battery_table)


#inserts one complete record
def save_data_to_db(data_point):
    db_path = DATABASE_PATH
    try:
        with db_lock:
            conn = sqlite3.connect(db_path, timeout=30)
            device_serial = data_point.get('device_serial', 'unknown')
            model = data_point.get('model', 'Unknown')
            connection_type = data_point.get('connection_type', 'Unknown')
            device_id, cpu_table, memory_table, tasks_table, swap_table, battery_table = get_or_create_device(conn,model, model, connection_type)

            timestamp = data_point['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            cursor = conn.cursor()

            cursor.execute(f'''
                INSERT INTO {cpu_table} (
                    timestamp, cpu_cpu, cpu_user, cpu_nice, cpu_sys, cpu_idle,
                    cpu_iow, cpu_irq, cpu_sirq, cpu_host
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                data_point.get('cpu_cpu', 0),
                data_point.get('cpu_user', 0),
                data_point.get('cpu_nice', 0),
                data_point.get('cpu_sys', 0),
                data_point.get('cpu_idle', 0),
                data_point.get('cpu_iow', 0),
                data_point.get('cpu_irq', 0),
                data_point.get('cpu_sirq', 0),
                data_point.get('cpu_host', 0),
            ))

            cursor.execute(f'''
                INSERT INTO {memory_table} (
                    timestamp, mem_total, mem_used, mem_free, mem_buffers
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                timestamp,
                data_point.get('mem_total', 0),
                data_point.get('mem_used', 0),
                data_point.get('mem_free', 0),
                data_point.get('mem_buffers', 0),
            ))

            cursor.execute(f'''
                INSERT INTO {tasks_table} (
                    timestamp, tasks_total, tasks_running, tasks_sleeping,
                    tasks_stopped, tasks_zombie
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                data_point.get('tasks_total', 0),
                data_point.get('tasks_running', 0),
                data_point.get('tasks_sleeping', 0),
                data_point.get('tasks_stopped', 0),
                data_point.get('tasks_zombie', 0),
            ))

            cursor.execute(f'''
                INSERT INTO {swap_table} (
                    timestamp, swap_total, swap_used, swap_free, swap_cached
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                timestamp,
                data_point.get('swap_total', 0),
                data_point.get('swap_used', 0),
                data_point.get('swap_free', 0),
                data_point.get('swap_cached', 0),
            ))

            if any(key in data_point for key in ['battery_level', 'battery_health', 'battery_temperature', 'charging_status']):
                cursor.execute(f'''
                    INSERT INTO {battery_table} (
                        timestamp, battery_level, battery_health, battery_temperature, charging_status
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    data_point.get('battery_level'),
                    data_point.get('battery_health'),
                    data_point.get('battery_temp'),
                    data_point.get('charging_status'),
                ))

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

