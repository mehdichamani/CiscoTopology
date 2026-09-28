import socket
import concurrent.futures
import ipaddress
import re
import collections
import subprocess
from netmiko import ConnectHandler
from app.config import build_netmiko_device
from app.db import (
    get_settings, get_switches, upsert_switch, upsert_link, 
    clear_links_for_switch, update_switch_status, get_excluded_ips_set, delete_switch
)

def log(msg, callback=None):
    if callback:
        callback(msg)
    else:
        try:
            print(msg)
        except Exception:
            try:
                print(msg.encode('utf-8', errors='replace').decode('utf-8'))
            except Exception:
                pass

def probe_port(ip, ports=(23, 22), timeout=0.8):
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex((str(ip), port))
            s.close()
            if res == 0:
                return str(ip), port
        except Exception:
            pass
    return None

def verify_cisco_banner_or_prompt(ip, port=23, timeout=1.5):
    """
    Lightweight banner and prompt probe to distinguish Cisco IOS devices
    from non-Cisco devices (e.g. MikroTik RouterOS, Ubiquiti AirOS radios).
    Returns (is_cisco: bool, detected_banner_info: str)
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((str(ip), port))
        
        banner_buf = b""
        if port == 23:
            # For Telnet: read initial banner / IAC negotiation
            try:
                data = s.recv(1024)
                banner_buf += data
                # Send CRLF to trigger prompt if quiet
                s.sendall(b"\r\n")
                data2 = s.recv(1024)
                banner_buf += data2
            except Exception:
                pass
        elif port == 22:
            # For SSH: read SSH version string (e.g. SSH-2.0-Cisco-1.25)
            try:
                data = s.recv(512)
                banner_buf += data
            except Exception:
                pass

        s.close()
        banner_text = banner_buf.decode('utf-8', errors='ignore').lower()

        # Non-Cisco signatures (Radios, Mikrotik, Ubiquiti, Linux servers)
        non_cisco_signatures = [
            "mikrotik", "routeros", "ubiquiti", "airos", "airmax", "cambium",
            "mimosa", "openwrt", "dropbear", "debian", "ubuntu", "raspbian"
        ]
        for sig in non_cisco_signatures:
            if sig in banner_text:
                return False, f"Non-Cisco signature detected: {sig}"

        # Positive Cisco signatures
        cisco_signatures = ["cisco", "catalyst", "ios", "c3750", "c2960", "c3560", "c9200", "c9300", "c3850", "c2950"]
        for sig in cisco_signatures:
            if sig in banner_text:
                return True, f"Cisco signature detected: {sig}"

        # If banner is standard Cisco switch login prompt
        if "user access verification" in banner_text or "cisco" in banner_text:
            return True, "Standard Cisco login prompt"

        if ("password:" in banner_text or "username:" in banner_text) and not any(r in banner_text for r in ["login:", "routeros", "airmax"]):
            # Also check if prompt ends with '>' or '#' after CRLF
            return True, "Cisco login prompt"

        return False, "Unknown non-Cisco banner/handshake"
    except Exception as e:
        return False, str(e)

import time
from datetime import datetime, timezone

def check_single_switch_status(sw_ip, timeout=1.0):
    """
    Check switch availability and measure latency in milliseconds.
    Returns (is_online: bool, latency_ms: float).
    """
    t_start = time.perf_counter()
    res = probe_port(sw_ip, ports=(23, 22, 80, 443, 8080), timeout=timeout)
    if res:
        latency = round((time.perf_counter() - t_start) * 1000.0, 2)
        return True, latency

    # Fallback to ICMP ping
    try:
        t_ping_start = time.perf_counter()
        cmd = ["ping", "-n", "1", "-w", "600", str(sw_ip)]
        output = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if output.returncode == 0:
            latency = round((time.perf_counter() - t_ping_start) * 1000.0, 2)
            return True, latency
    except Exception:
        pass

    return False, 0.0

def check_all_switches_status(log_callback=None):
    switches = get_switches()
    excluded_ips = get_excluded_ips_set()

    # Automatically prune any previously registered switch that is now in excluded_ips
    active_switches = []
    for sw in switches:
        if sw["ip"] in excluded_ips:
            log(f"🧹 Removing excluded IP {sw['ip']} from active switches...", log_callback)
            delete_switch(sw["ip"])
        else:
            active_switches.append(sw)

    if not active_switches:
        log("ℹ️ No switches in database to check status.", log_callback)
        return {}

    log(f"💓 Checking online status for {len(active_switches)} switch(es) in database...", log_callback)
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        future_to_sw = {executor.submit(check_single_switch_status, sw["ip"]): sw for sw in active_switches}
        for future in concurrent.futures.as_completed(future_to_sw):
            sw = future_to_sw[future]
            ip = sw["ip"]
            hostname = sw["hostname"] or ip
            try:
                is_online, latency_ms = future.result()
                status = "online" if is_online else "offline"
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if is_online else sw.get("last_seen")
                update_switch_status(ip, status, latency_ms=latency_ms if is_online else 0.0, last_seen=now_iso if is_online else None)
                results[ip] = {"status": status, "latency_ms": latency_ms if is_online else 0.0}
                icon = "🟢" if is_online else "🔴"
                lat_str = f" ({latency_ms} ms)" if is_online else ""
                log(f"  {icon} [{status.upper()}]{lat_str} Switch {hostname} ({ip})", log_callback)
            except Exception as e:
                update_switch_status(ip, "offline", latency_ms=0.0)
                results[ip] = {"status": "offline", "latency_ms": 0.0}
                log(f"  🔴 [OFFLINE] Switch {hostname} ({ip}) - Error: {e}", log_callback)

    log(f"✅ Switch status health check complete.", log_callback)
    return results

def scan_subnet(log_callback=None):
    settings = get_settings()
    subnet_str = settings.get("subnet", "")
    if not subnet_str:
        log("❌ ERROR: Subnet is not configured! Please configure it in Settings first.", log_callback)
        return []

    try:
        net = ipaddress.ip_network(subnet_str, strict=False)
    except ValueError:
        log(f"❌ ERROR: Invalid subnet CIDR '{subnet_str}'.", log_callback)
        return []

    excluded_ips = get_excluded_ips_set()
    if excluded_ips:
        log(f"🛡️ Excluded IPs active: {', '.join(sorted(excluded_ips))}", log_callback)

    hosts = [h for h in net.hosts() if str(h) not in excluded_ips]
    log(f"🔍 Starting multithreaded scan for {len(hosts)} IPs in {net} (excluding {len(excluded_ips)} IPs)...", log_callback)
    
    discovered = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(probe_port, ip): ip for ip in hosts}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                ip, port = res
                # Method 3: Validate if device looks like Cisco before registering
                is_cisco, desc = verify_cisco_banner_or_prompt(ip, port=port)
                if is_cisco:
                    discovered.append(ip)
                    log(f"  ✅ [Found Cisco Switch | Port {port}] IP: {ip} ({desc})", log_callback)
                    upsert_switch(ip=ip, status="online")
                else:
                    log(f"  ⏭️ [Ignored Non-Cisco / Radio | Port {port}] IP: {ip} ({desc})", log_callback)

    log(f"\n✅ Scan Complete! Discovered {len(discovered)} active Cisco switch IP(s).", log_callback)
    return discovered

def parse_cdp_detail(raw_output):
    entries = []
    raw_blocks = raw_output.split("Device ID:")
    for block in raw_blocks[1:]:
        lines = block.strip().splitlines()
        if not lines: continue
        device_id = lines[0].strip().split(".")[0]
        
        ip_addr = ""
        platform = ""
        capabilities = ""
        local_iface = ""
        remote_port = ""
        
        m_ip = re.search(r"IP address:\s*([\d.]+)", block, re.IGNORECASE)
        if m_ip: ip_addr = m_ip.group(1).strip()
            
        m_plat = re.search(r"Platform:\s*(.*?),", block, re.IGNORECASE)
        if m_plat: platform = m_plat.group(1).strip()
            
        m_cap = re.search(r"Capabilities:\s*(.*?)(?:\n|\r|$)", block, re.IGNORECASE)
        if m_cap: capabilities = m_cap.group(1).strip()
            
        m_if = re.search(r"Interface:\s*([^,\n]+)", block, re.IGNORECASE)
        if m_if: local_iface = m_if.group(1).strip()
            
        m_port = re.search(r"Port ID \(outgoing port\):\s*([^\n\r,]+)", block, re.IGNORECASE)
        if m_port: remote_port = m_port.group(1).strip()
            
        entries.append({
            "device_id": device_id,
            "ip": ip_addr,
            "platform": platform,
            "capabilities": capabilities,
            "local_port": local_iface,
            "remote_port": remote_port
        })
    return entries

def crawl_cdp(log_callback=None):
    settings = get_settings()
    subnet_str = settings.get("subnet", "")
    username = settings.get("username", "")
    password = settings.get("password", "")
    device_type = settings.get("device_type", "cisco_ios_telnet")
    seed_ips_str = settings.get("seed_ips", "")

    if not subnet_str:
        log("❌ ERROR: Subnet is not configured in Settings!", log_callback)
        return

    try:
        allowed_net = ipaddress.ip_network(subnet_str, strict=False)
    except ValueError:
        log(f"❌ ERROR: Invalid subnet CIDR '{subnet_str}'.", log_callback)
        return

    seed_ips = [s.strip() for s in seed_ips_str.split(",") if s.strip()]
    if not seed_ips:
        # Fallback to discovered switches in DB or first IP in subnet
        from app.db import get_switches
        existing = get_switches()
        if existing:
            seed_ips = [s["ip"] for s in existing]
        else:
            seed_ips = [str(list(allowed_net.hosts())[9])] if len(list(allowed_net.hosts())) > 9 else [str(list(allowed_net.hosts())[0])]

    log("=" * 50, log_callback)
    log("  SMART CDP/LLDP RECURSIVE CRAWLER STARTED", log_callback)
    log(f"  Target Subnet Bounds: {allowed_net}", log_callback)
    log(f"  Initial Seed IP(s): {', '.join(seed_ips)}", log_callback)
    log("=" * 50 + "\n", log_callback)

    queue = collections.deque(seed_ips)
    visited_ips = set()
    crawled_switches = set()

    while queue:
        ip = queue.popleft()
        if ip in visited_ips: continue
        visited_ips.add(ip)

        log(f"📡 Connecting to switch at IP: {ip}...", log_callback)

        device_dict = build_netmiko_device(ip, settings)

        try:
            with ConnectHandler(**device_dict) as net:
                net.enable()
                prompt = net.find_prompt()
                hostname = prompt.strip("#>").lower()

                log(f"  ✅ Connected: {hostname}", log_callback)
                crawled_switches.add(ip)
                upsert_switch(ip=ip, hostname=hostname, status="online")

                cdp_raw = net.send_command("show cdp neighbors detail", read_timeout=15)
                neighbors = parse_cdp_detail(cdp_raw)

                log(f"  🔍 Discovered {len(neighbors)} CDP neighbor link(s)", log_callback)

                clear_links_for_switch(hostname)
                for n in neighbors:
                    upsert_link(
                        source_switch=hostname,
                        source_port=n["local_port"],
                        target_switch=n["device_id"],
                        target_port=n["remote_port"],
                        protocol="CDP"
                    )

                    caps = n["capabilities"].lower()
                    if ("switch" in caps or "router" in caps or "trans bridge" in caps) and n["ip"]:
                        try:
                            addr = ipaddress.ip_address(n["ip"])
                            if addr not in allowed_net:
                                log(f"    ⏭️ Skipping neighbor switch {n['device_id']} ({n['ip']}): Outside allowed target subnet {allowed_net}", log_callback)
                                continue
                        except ValueError:
                            continue

                        if n["ip"] not in visited_ips and n["ip"] not in queue:
                            log(f"    ➕ Discovered neighbor switch: {n['device_id']} ({n['ip']}) -> Queueing", log_callback)
                            queue.append(n["ip"])

        except Exception as e:
            log(f"  ❌ Failed to connect/crawl {ip}: {str(e)}", log_callback)

    log("\n" + "=" * 50, log_callback)
    log(f"✅ CDP Crawling Completed! Switches processed: {len(crawled_switches)}", log_callback)
    log("=" * 50, log_callback)
