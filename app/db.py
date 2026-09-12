import sqlite3
import os
from app.config import DB_PATH, DATA_DIR

def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        subnet TEXT,
        username TEXT,
        password TEXT,
        device_type TEXT DEFAULT 'cisco_ios_telnet',
        seed_ips TEXT,
        auto_refresh_hours INTEGER DEFAULT 24,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Switches Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS switches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT UNIQUE NOT NULL,
        hostname TEXT,
        model TEXT DEFAULT 'N/A',
        serial_number TEXT DEFAULT 'N/A',
        ios_version TEXT DEFAULT 'N/A',
        total_ports INTEGER DEFAULT 0,
        poe_capable TEXT DEFAULT 'N/A',
        status TEXT DEFAULT 'online',
        last_seen DATETIME,
        latency_ms REAL DEFAULT 0.0,
        ports_total INTEGER DEFAULT 0,
        ports_up INTEGER DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Run safe column migrations on existing switches table
    cursor.execute("PRAGMA table_info(switches);")
    existing_switch_cols = [row[1] for row in cursor.fetchall()]
    if "last_seen" not in existing_switch_cols:
        cursor.execute("ALTER TABLE switches ADD COLUMN last_seen DATETIME;")
    if "latency_ms" not in existing_switch_cols:
        cursor.execute("ALTER TABLE switches ADD COLUMN latency_ms REAL DEFAULT 0.0;")
    if "ports_total" not in existing_switch_cols:
        cursor.execute("ALTER TABLE switches ADD COLUMN ports_total INTEGER DEFAULT 0;")
    if "ports_up" not in existing_switch_cols:
        cursor.execute("ALTER TABLE switches ADD COLUMN ports_up INTEGER DEFAULT 0;")

    # 3. Inter-Device Links Table (Metadata Links)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_switch TEXT NOT NULL,
        source_port TEXT NOT NULL,
        target_switch TEXT NOT NULL,
        target_port TEXT,
        protocol TEXT DEFAULT 'CDP',
        speed TEXT DEFAULT 'N/A',
        vlan TEXT DEFAULT 'Native',
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_switch, source_port, target_switch)
    );
    """)

    # 4. VLAN Summary Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vlans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        switch TEXT NOT NULL,
        vlan_id INTEGER NOT NULL,
        vlan_name TEXT,
        port_count INTEGER DEFAULT 0,
        ports TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(switch, vlan_id)
    );
    """)

    # 5. Connected Edge Devices Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS connected_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        switch_name TEXT,
        port TEXT,
        vlan TEXT,
        mac_address TEXT UNIQUE NOT NULL,
        ip_address TEXT,
        vendor TEXT,
        device_type TEXT DEFAULT 'Other',
        user TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 6. Switch Ports Table (Structured Ports & MAC correlation for Boomban)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS switch_ports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        switch_ip TEXT NOT NULL,
        port_name TEXT NOT NULL,
        status TEXT DEFAULT 'down',
        vlan TEXT DEFAULT '1',
        speed TEXT DEFAULT 'auto',
        duplex TEXT DEFAULT 'auto',
        mac_address TEXT DEFAULT '',
        connected_device TEXT DEFAULT '',
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(switch_ip, port_name)
    );
    """)

    # 7. Scheduled Tasks Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_schedules (
        task_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        action_name TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        interval_minutes INTEGER DEFAULT 60,
        last_run DATETIME,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Seed default tasks if empty
    cursor.execute("SELECT COUNT(*) FROM task_schedules")
    if cursor.fetchone()[0] == 0:
        default_tasks = [
            ("task_discovery", "کشف دستگاه‌های جدید", "scan", 1, 60),
            ("task_collector", "بروزرسانی اطلاعات سوئیچ‌ها", "collect", 1, 1440),
            ("task_status", "بررسی آنلاین بودن سوئیچ‌ها", "check_status", 1, 1),
        ]
        cursor.executemany("""
        INSERT INTO task_schedules (task_id, title, action_name, enabled, interval_minutes)
        VALUES (?, ?, ?, ?, ?)
        """, default_tasks)

    conn.commit()
    conn.close()

def get_task_schedules():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, title, action_name, enabled, interval_minutes, last_run, updated_at FROM task_schedules ORDER BY task_id")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_task_schedule(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, title, action_name, enabled, interval_minutes, last_run, updated_at FROM task_schedules WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_task_schedule(task_id, enabled=None, interval_minutes=None, update_last_run=False):
    conn = get_connection()
    cursor = conn.cursor()
    if update_last_run:
        cursor.execute("UPDATE task_schedules SET last_run = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?", (task_id,))
    else:
        if enabled is not None and interval_minutes is not None:
            cursor.execute("UPDATE task_schedules SET enabled = ?, interval_minutes = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?", (enabled, interval_minutes, task_id))
        elif enabled is not None:
            cursor.execute("UPDATE task_schedules SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?", (enabled, task_id))
        elif interval_minutes is not None:
            cursor.execute("UPDATE task_schedules SET interval_minutes = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?", (interval_minutes, task_id))
    conn.commit()
    conn.close()

def is_configured():
    settings = get_settings()
    return bool(settings and settings.get("subnet"))

def get_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT subnet, username, password, device_type, seed_ips, auto_refresh_hours, updated_at FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def save_settings(subnet, username="", password="", device_type="cisco_ios_telnet", seed_ips="", auto_refresh_hours=24):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO settings (id, subnet, username, password, device_type, seed_ips, auto_refresh_hours, updated_at)
    VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(id) DO UPDATE SET
        subnet=excluded.subnet,
        username=excluded.username,
        password=excluded.password,
        device_type=excluded.device_type,
        seed_ips=excluded.seed_ips,
        auto_refresh_hours=excluded.auto_refresh_hours,
        updated_at=CURRENT_TIMESTAMP;
    """, (subnet, username, password, device_type, seed_ips, auto_refresh_hours))
    conn.commit()
    conn.close()

def upsert_switch(ip, hostname="", model="N/A", serial_number="N/A", ios_version="N/A", total_ports=0, poe_capable="N/A", status="online", last_seen=None, latency_ms=0.0, ports_total=None, ports_up=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Retrieve current switch if exists to preserve ports counts if not provided
    cursor.execute("SELECT ports_total, ports_up, total_ports, last_seen, latency_ms FROM switches WHERE ip = ?", (ip,))
    row = cursor.fetchone()
    current_ports_total = ports_total if ports_total is not None else (row["ports_total"] if row and row["ports_total"] else (total_ports or 0))
    current_ports_up = ports_up if ports_up is not None else (row["ports_up"] if row and row["ports_up"] else 0)
    current_last_seen = last_seen if last_seen is not None else (row["last_seen"] if row else None)
    current_latency = latency_ms if latency_ms is not None else (row["latency_ms"] if row else 0.0)

    cursor.execute("""
    INSERT INTO switches (ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status, last_seen, latency_ms, ports_total, ports_up, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(ip) DO UPDATE SET
        hostname=COALESCE(NULLIF(excluded.hostname, ''), switches.hostname),
        model=CASE WHEN excluded.model != 'N/A' THEN excluded.model ELSE switches.model END,
        serial_number=CASE WHEN excluded.serial_number != 'N/A' THEN excluded.serial_number ELSE switches.serial_number END,
        ios_version=CASE WHEN excluded.ios_version != 'N/A' THEN excluded.ios_version ELSE switches.ios_version END,
        total_ports=CASE WHEN excluded.total_ports > 0 THEN excluded.total_ports ELSE switches.total_ports END,
        poe_capable=CASE WHEN excluded.poe_capable != 'N/A' THEN excluded.poe_capable ELSE switches.poe_capable END,
        status=excluded.status,
        last_seen=COALESCE(excluded.last_seen, switches.last_seen),
        latency_ms=CASE WHEN excluded.latency_ms > 0 THEN excluded.latency_ms ELSE switches.latency_ms END,
        ports_total=CASE WHEN excluded.ports_total > 0 THEN excluded.ports_total ELSE switches.ports_total END,
        ports_up=CASE WHEN excluded.ports_up >= 0 THEN excluded.ports_up ELSE switches.ports_up END,
        updated_at=CURRENT_TIMESTAMP;
    """, (ip, hostname, model, serial_number, ios_version, total_ports or current_ports_total, poe_capable, status, current_last_seen, current_latency, current_ports_total, current_ports_up))
    conn.commit()
    conn.close()

def update_switch_status(ip, status, latency_ms=None, last_seen=None):
    conn = get_connection()
    cursor = conn.cursor()
    if latency_ms is not None and last_seen is not None:
        cursor.execute("""
        UPDATE switches 
        SET status = ?, latency_ms = ?, last_seen = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE ip = ?
        """, (status, latency_ms, last_seen, ip))
    elif latency_ms is not None:
        cursor.execute("""
        UPDATE switches 
        SET status = ?, latency_ms = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE ip = ?
        """, (status, latency_ms, ip))
    elif last_seen is not None:
        cursor.execute("""
        UPDATE switches 
        SET status = ?, last_seen = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE ip = ?
        """, (status, last_seen, ip))
    else:
        cursor.execute("UPDATE switches SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE ip = ?", (status, ip))
    conn.commit()
    conn.close()

def update_switch_port_counts(ip, ports_total, ports_up):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE switches 
    SET ports_total = ?, ports_up = ?, total_ports = ?, updated_at = CURRENT_TIMESTAMP 
    WHERE ip = ?
    """, (ports_total, ports_up, ports_total, ip))
    conn.commit()
    conn.close()

def upsert_link(source_switch, source_port, target_switch, target_port="", protocol="CDP", speed="N/A", vlan="Native"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO links (source_switch, source_port, target_switch, target_port, protocol, speed, vlan, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(source_switch, source_port, target_switch) DO UPDATE SET
        target_port=excluded.target_port,
        protocol=excluded.protocol,
        speed=excluded.speed,
        vlan=excluded.vlan,
        updated_at=CURRENT_TIMESTAMP;
    """, (source_switch, source_port, target_switch, target_port, protocol, speed, vlan))
    conn.commit()
    conn.close()

def clear_links_for_switch(source_switch):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM links WHERE source_switch = ?", (source_switch,))
    conn.commit()
    conn.close()

def upsert_vlan(switch, vlan_id, vlan_name="Unknown", port_count=0, ports=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO vlans (switch, vlan_id, vlan_name, port_count, ports, updated_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(switch, vlan_id) DO UPDATE SET
        vlan_name=excluded.vlan_name,
        port_count=excluded.port_count,
        ports=excluded.ports,
        updated_at=CURRENT_TIMESTAMP;
    """, (switch, vlan_id, vlan_name, port_count, ports))
    conn.commit()
    conn.close()

def upsert_switch_port(switch_ip, port_name, status="down", vlan="1", speed="auto", duplex="auto", mac_address="", connected_device=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO switch_ports (switch_ip, port_name, status, vlan, speed, duplex, mac_address, connected_device, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(switch_ip, port_name) DO UPDATE SET
        status=excluded.status,
        vlan=excluded.vlan,
        speed=excluded.speed,
        duplex=excluded.duplex,
        mac_address=CASE WHEN excluded.mac_address != '' THEN excluded.mac_address ELSE switch_ports.mac_address END,
        connected_device=CASE WHEN excluded.connected_device != '' THEN excluded.connected_device ELSE switch_ports.connected_device END,
        updated_at=CURRENT_TIMESTAMP;
    """, (switch_ip, port_name, status, str(vlan), speed, duplex, mac_address, connected_device))
    conn.commit()
    conn.close()

def clear_switch_ports(switch_ip):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM switch_ports WHERE switch_ip = ?", (switch_ip,))
    conn.commit()
    conn.close()

def get_switch_ports(switch_ip):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT port_name, status, vlan, speed, duplex, mac_address, connected_device, updated_at
    FROM switch_ports
    WHERE switch_ip = ?
    ORDER BY port_name
    """, (switch_ip,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def upsert_connected_device(switch_name, port, vlan, mac_address, ip_address="", vendor="", device_type="Other", name="", user=""):
    if not mac_address: return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO connected_devices (switch_name, port, vlan, mac_address, ip_address, vendor, device_type, name, user, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(mac_address) DO UPDATE SET
        switch_name=excluded.switch_name,
        port=excluded.port,
        vlan=excluded.vlan,
        ip_address=excluded.ip_address,
        vendor=excluded.vendor,
        device_type=excluded.device_type,
        name=excluded.name,
        user=excluded.user,
        updated_at=CURRENT_TIMESTAMP;
    """, (switch_name, port, str(vlan), mac_address, ip_address, vendor, device_type, name, user))
    conn.commit()
    conn.close()

def get_switches():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status, 
           last_seen, latency_ms, ports_total, ports_up, updated_at 
    FROM switches 
    ORDER BY hostname, ip
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_links():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, source_switch, source_port, target_switch, target_port, protocol, speed, vlan, updated_at FROM links ORDER BY source_switch")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_vlans():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, switch, vlan_id, vlan_name, port_count, ports, updated_at FROM vlans ORDER BY switch, vlan_id")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_connected_devices():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, switch_name, port, vlan, mac_address, ip_address, vendor, device_type, name, user, updated_at FROM connected_devices ORDER BY switch_name, port")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_switch_details(switch_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status,
           last_seen, latency_ms, ports_total, ports_up, updated_at
    FROM switches WHERE ip = ? OR hostname = ? OR CAST(id AS TEXT) = ?
    """, (switch_id, switch_id, switch_id))
    sw_row = cursor.fetchone()
    if not sw_row:
        conn.close()
        return None
    sw = dict(sw_row)
    hostname = sw["hostname"] or sw["ip"]
    ip = sw["ip"]

    cursor.execute("""
    SELECT vlan_id, vlan_name, port_count, ports
    FROM vlans WHERE switch = ? OR switch = ? ORDER BY vlan_id
    """, (hostname, ip))
    vlans = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT source_switch, source_port, target_switch, target_port, protocol, speed, vlan
    FROM links WHERE source_switch = ? OR source_switch = ? OR target_switch = ? OR target_switch = ?
    ORDER BY source_port
    """, (hostname, ip, hostname, ip))
    links = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT port_name, status, vlan, speed, duplex, mac_address, connected_device
    FROM switch_ports WHERE switch_ip = ?
    ORDER BY port_name
    """, (ip,))
    ports = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT port, vlan, mac_address, ip_address, vendor, device_type
    FROM connected_devices WHERE switch_name = ? OR switch_name = ? ORDER BY port
    """, (hostname, ip))
    devices = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "switch": sw,
        "vlans": vlans,
        "links": links,
        "ports": ports,
        "devices": devices
    }

if __name__ == "__main__":
    init_db()
    print("Simban database initialized at:", DB_PATH)
