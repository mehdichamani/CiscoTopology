import re
import concurrent.futures
from netmiko import ConnectHandler
from app.db import get_settings, get_switches, upsert_switch, upsert_vlan, upsert_connected_device, upsert_link

def parse_show_version(output):
    model = "N/A"
    serial = "N/A"
    version = "N/A"
    
    m_ver = re.search(r"Version\s+([^\s,]+)", output, re.IGNORECASE)
    if m_ver: version = m_ver.group(1)
        
    m_mod = re.search(r"Model Number\s*:\s*([^\s\n]+)", output, re.IGNORECASE)
    if not m_mod:
        m_mod = re.search(r"cisco\s+([A-Z0-9\-]+)\s+.*processor", output, re.IGNORECASE)
    if m_mod: model = m_mod.group(1)
        
    m_sn = re.search(r"System Serial Number\s*:\s*([^\s\n]+)", output, re.IGNORECASE)
    if not m_sn:
        m_sn = re.search(r"Processor board ID\s+([^\s\n]+)", output, re.IGNORECASE)
    if m_sn: serial = m_sn.group(1)
        
    return model, serial, version

def parse_vlans(output):
    vlan_map = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("VLAN") or line.startswith("----") or line.startswith("0"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            vlan_id = int(parts[0])
            vlan_name = parts[1]
            ports = " ".join(parts[3:]) if len(parts) > 3 else ""
            vlan_map[vlan_id] = {
                "name": vlan_name,
                "ports": ports,
                "port_count": len(ports.split(",")) if ports else 0
            }
    return vlan_map

def query_single_switch(sw_dict, settings, log_callback=None):
    ip = sw_dict["ip"]
    username = settings.get("username", "")
    password = settings.get("password", "")
    device_type = settings.get("device_type", "cisco_ios_telnet")

    device_dict = {
        "device_type": device_type,
        "host": ip,
        "username": username,
        "password": password,
        "secret": password,
        "conn_timeout": 10,
    }

    try:
        if log_callback: log_callback(f"📥 Querying switch data from {ip}...")
        with ConnectHandler(**device_dict) as net:
            net.enable()
            prompt = net.find_prompt()
            hostname = prompt.strip("#>")

            ver_raw = net.send_command("show version", read_timeout=15)
            model, serial, version = parse_show_version(ver_raw)

            upsert_switch(
                ip=ip,
                hostname=hostname,
                model=model,
                serial_number=serial,
                ios_version=version,
                status="online"
            )

            # VLANs
            vlan_raw = net.send_command("show vlan brief", read_timeout=15)
            vlans = parse_vlans(vlan_raw)
            for v_id, v_data in vlans.items():
                upsert_vlan(
                    switch=hostname or ip,
                    vlan_id=v_id,
                    vlan_name=v_data["name"],
                    port_count=v_data["port_count"],
                    ports=v_data["ports"]
                )

            if log_callback: log_callback(f"  ✅ Completed collection for {hostname} ({ip})")
            return True
    except Exception as e:
        if log_callback: log_callback(f"  ❌ Error collecting from {ip}: {str(e)}")
        return False

def run_full_collection(log_callback=None):
    settings = get_settings()
    switches = get_switches()

    if not switches:
        if log_callback: log_callback("⚠️ No switches found in database! Run Initial Subnet Scan or CDP Crawler first.")
        return

    if log_callback:
        log_callback("=" * 50)
        log_callback(f"  PARALLEL SWITCH DATA COLLECTION STARTED ({len(switches)} switches)")
        log_callback("=" * 50 + "\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(query_single_switch, sw, settings, log_callback) for sw in switches]
        concurrent.futures.wait(futures)

    if log_callback:
        log_callback("\n" + "=" * 50)
        log_callback("✅ Switch Data Collection Finished!")
        log_callback("=" * 50)
