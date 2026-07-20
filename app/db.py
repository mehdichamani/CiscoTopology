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
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Inter-Device Links Table (Topology Links)
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
        name TEXT,
        user TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

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

def upsert_switch(ip, hostname="", model="N/A", serial_number="N/A", ios_version="N/A", total_ports=0, poe_capable="N/A", status="online"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO switches (ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(ip) DO UPDATE SET
        hostname=excluded.hostname,
        model=excluded.model,
        serial_number=excluded.serial_number,
        ios_version=excluded.ios_version,
        total_ports=excluded.total_ports,
        poe_capable=excluded.poe_capable,
        status=excluded.status,
        updated_at=CURRENT_TIMESTAMP;
    """, (ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status))
    conn.commit()
    conn.close()

def update_switch_status(ip, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE switches SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE ip = ?", (status, ip))
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
    cursor.execute("SELECT id, ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status, updated_at FROM switches ORDER BY hostname, ip")
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
    SELECT id, ip, hostname, model, serial_number, ios_version, total_ports, poe_capable, status, updated_at
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
    SELECT port, vlan, mac_address, ip_address, vendor, device_type
    FROM connected_devices WHERE switch_name = ? OR switch_name = ? ORDER BY port
    """, (hostname, ip))
    devices = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "switch": sw,
        "vlans": vlans,
        "links": links,
        "devices": devices
    }

def get_vis_topology():
    """Generates Vis.js formatted nodes and edges for dynamic interactive topology."""
    switches = get_switches()
    links = get_links()
    
    node_map = {}
    nodes = []
    
    # 1. Switch Nodes
    for sw in switches:
        node_id = sw["hostname"] or sw["ip"]
        node_map[node_id] = node_id
        nodes.append({
            "id": node_id,
            "label": f"{node_id}\n({sw['ip']})",
            "group": "switch",
            "title": f"<b>Switch:</b> {node_id}<br><b>IP:</b> {sw['ip']}<br><b>Model:</b> {sw['model']}<br><b>Ports:</b> {sw['total_ports']}",
            "ip": sw["ip"],
            "model": sw["model"],
            "shape": "box",
            "color": {"background": "#1e293b", "border": "#3b82f6", "highlight": {"border": "#60a5fa", "background": "#334155"}},
            "font": {"color": "#f8fafc", "face": "Inter"}
        })

    # 2. Edges / Connections
    edges = []
    seen_links = set()
    for l in links:
        src = l["source_switch"]
        dst = l["target_switch"]
        
        # Ensure dst node exists if not in switch list
        if dst not in node_map:
            node_map[dst] = dst
            nodes.append({
                "id": dst,
                "label": dst,
                "group": "device",
                "title": f"<b>Device/Neighbor:</b> {dst}",
                "shape": "ellipse",
                "color": {"background": "#0f172a", "border": "#8b5cf6"},
                "font": {"color": "#cbd5e1", "face": "Inter"}
            })
            
        link_key = tuple(sorted([src, dst]))
        edges.append({
            "from": src,
            "to": dst,
            "label": f"{l['source_port']} ⇄ {l['target_port']}",
            "title": f"<b>Local Port:</b> {l['source_port']}<br><b>Remote Port:</b> {l['target_port']}<br><b>Protocol:</b> {l['protocol']}",
            "color": {"color": "#8b5cf6", "highlight": "#a78bfa"},
            "width": 2
        })

    return {"nodes": nodes, "edges": edges}

if __name__ == "__main__":
    init_db()
    print("CiscoToolsV2 database initialized at:", DB_PATH)
