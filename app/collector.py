import re
import concurrent.futures
from datetime import datetime, timezone
from netmiko import ConnectHandler
from app.config import build_netmiko_device
from app.db import (
    get_settings, get_switches, upsert_switch, upsert_vlan, 
    upsert_switch_port, clear_switch_ports, update_switch_port_counts,
    upsert_connected_device, get_excluded_ips_set
)

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

def parse_interfaces_status(output):
    """
    Parse Cisco 'show interfaces status' output:
    Port      Name               Status       Vlan       Duplex  Speed Type
    Fa0/1                        connected    1          a-full  a-100 10/100BaseTX
    Fa0/2                        notconnect   1            auto   auto 10/100BaseTX
    """
    ports = {}
    lines = output.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("Port") or line.startswith("----"):
            continue
        
        # Match typical port patterns (Fa0/1, Gi1/0/24, Te1/1, etc.)
        match = re.match(r"^([A-Za-z]{2,4}\s*[\d/]+)\s+(.*?)\s+(connected|notconnect|disabled|err-disabled|faulty)\s+(\S+)\s+(\S+)\s+(\S+)", line, re.IGNORECASE)
        if match:
            p_name = match.group(1).replace(" ", "")
            desc = match.group(2).strip()
            raw_status = match.group(3).lower()
            status = "up" if raw_status == "connected" else "down"
            vlan = match.group(4)
            duplex = match.group(5)
            speed = match.group(6)
            ports[p_name] = {
                "port_name": p_name,
                "status": status,
                "vlan": vlan,
                "duplex": duplex,
                "speed": speed,
                "description": desc
            }
    return ports

def parse_ip_interface_brief(output):
    """
    Fallback parser for 'show ip interface brief' when 'show interfaces status' is unavailable:
    Interface              IP-Address      OK? Method Status                Protocol
    FastEthernet0/1        unassigned      YES unset  up                    up
    """
    ports = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Interface") or line.startswith("----"):
            continue
        parts = line.split()
        if len(parts) >= 5:
            p_name = parts[0]
            status_col = parts[-2].lower()
            proto_col = parts[-1].lower()
            is_up = (status_col == "up" and proto_col == "up")
            ports[p_name] = {
                "port_name": p_name,
                "status": "up" if is_up else "down",
                "vlan": "1",
                "duplex": "auto",
                "speed": "auto",
                "description": ""
            }
    return ports

def parse_mac_address_table(output):
    """
    Parse 'show mac address-table' or 'show mac-address-table':
    Vlan    Mac Address       Type        Ports
    ----    -----------       --------    -----
       1    0014.a86b.cf12    DYNAMIC     Fa0/1
    """
    mac_map = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Vlan") or line.startswith("----") or line.startswith("Total"):
            continue
        m = re.search(r"([\da-fA-F]{4}\.[\da-fA-F]{4}\.[\da-fA-F]{4})\s+\S+\s+([A-Za-z]{2,4}\s*[\d/]+)", line)
        if m:
            mac = m.group(1).lower()
            port = m.group(2).replace(" ", "")
            if port not in mac_map:
                mac_map[port] = []
            mac_map[port].append(mac)
    return mac_map

def query_single_switch(sw_dict, settings, log_callback=None):
    ip = sw_dict["ip"]
    device_dict = build_netmiko_device(ip, settings)

    try:
        if log_callback: log_callback(f"📥 Querying switch data from {ip}...")
        with ConnectHandler(**device_dict) as net:
            net.enable()
            prompt = net.find_prompt()
            hostname = prompt.strip("#>").lower()


            # 1. Version & Hardware Info
            ver_raw = net.send_command("show version", read_timeout=15)
            model, serial, version = parse_show_version(ver_raw)

            # 2. Port Status Collection
            ports_data = {}
            try:
                if_status_raw = net.send_command("show interfaces status", read_timeout=15)
                if "Invalid input" not in if_status_raw and len(if_status_raw.strip()) > 30:
                    ports_data = parse_interfaces_status(if_status_raw)
            except Exception:
                pass

            if not ports_data:
                try:
                    ip_if_raw = net.send_command("show ip interface brief", read_timeout=15)
                    ports_data = parse_ip_interface_brief(ip_if_raw)
                except Exception:
                    pass

            # 3. MAC Address Table Collection
            mac_data = {}
            try:
                mac_raw = net.send_command("show mac address-table", read_timeout=15)
                if "Invalid input" in mac_raw:
                    mac_raw = net.send_command("show mac-address-table", read_timeout=15)
                mac_data = parse_mac_address_table(mac_raw)
            except Exception:
                pass

            # Calculate ports total and up
            physical_ports = [p for p in ports_data.values() if not p["port_name"].lower().startswith("vl")]
            ports_total = len(physical_ports) if physical_ports else len(ports_data)
            ports_up = sum(1 for p in (physical_ports or ports_data.values()) if p["status"] == "up")

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            upsert_switch(
                ip=ip,
                hostname=hostname,
                model=model,
                serial_number=serial,
                ios_version=version,
                total_ports=ports_total,
                status="online",
                last_seen=now_iso,
                ports_total=ports_total,
                ports_up=ports_up
            )

            # Save individual port details to switch_ports
            for p_name, p_info in ports_data.items():
                macs = mac_data.get(p_name, [])
                primary_mac = macs[0] if macs else ""
                upsert_switch_port(
                    switch_ip=ip,
                    port_name=p_name,
                    status=p_info["status"],
                    vlan=p_info.get("vlan", "1"),
                    speed=p_info.get("speed", "auto"),
                    duplex=p_info.get("duplex", "auto"),
                    mac_address=primary_mac,
                    connected_device=";".join(macs) if len(macs) > 1 else primary_mac
                )
                if primary_mac:
                    upsert_connected_device(
                        switch_name=hostname or ip,
                        port=p_name,
                        vlan=p_info.get("vlan", "1"),
                        mac_address=primary_mac
                    )

            # 4. VLANs
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

            if log_callback: log_callback(f"  ✅ Completed collection for {hostname} ({ip}) - Ports: {ports_up}/{ports_total} Up")
            return True
    except Exception as e:
        if log_callback: log_callback(f"  ❌ Error collecting from {ip}: {str(e)}")
        return False

def run_full_collection(log_callback=None):
    settings = get_settings()
    all_switches = get_switches()
    excluded_ips = get_excluded_ips_set()
    switches = [s for s in all_switches if s["ip"] not in excluded_ips]

    if not switches:
        if log_callback: log_callback("⚠️ No switches found in database! Run Initial Subnet Scan first.")
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
