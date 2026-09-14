#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ابزار تست و ارزیابی کابل‌های شبکه بین سوئیچ‌های سیسکو (Cisco Cable Tester)
اکوسیستم بوم‌بان / سیم‌بان
"""

import os
import sys
import time
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# اضافه کردن روت پروژه به مسیر پایتون جهت استفاده از ماژول‌ها و تنظیمات
# فایل در simban/scripts/test_cable.py است، بنابراین parent.parent پوشه simban و parent.parent.parent پوشه boomban-suite است
SIMBAN_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SIMBAN_DIR.parent

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "mojban"))

from dotenv import load_dotenv
load_dotenv(SIMBAN_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")

from netmiko import ConnectHandler

DB_PATH = SIMBAN_DIR / "data" / "network.db"

SWITCH_DEVICE_TYPE = os.getenv("SWITCH_DEVICE_TYPE", "cisco_ios_telnet")
SWITCH_USERNAME = os.getenv("SWITCH_USERNAME", "")
SWITCH_PASSWORD = os.getenv("SWITCH_PASSWORD", "")
SWITCH_SECRET = os.getenv("SWITCH_SECRET", "")
SWITCH_PORT = int(os.getenv("SWITCH_TELNET_PORT", 23))
SWITCH_TIMEOUT = int(os.getenv("SWITCH_TIMEOUT", 10))


def get_switches_from_db() -> List[Dict]:
    """دریافت لیست سوئیچ‌ها از دیتابیس سیم‌بان"""
    if not DB_PATH.exists():
        print(f"❌ دیتابیس سیم‌بان در مسیر {DB_PATH} یافت نشد.")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, ip, hostname, model, status 
        FROM switches 
        ORDER BY hostname ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def connect_to_switch(ip: str):
    """برقراری اتصال مستقیم با سوئیچ سیسکو با Netmiko"""
    device_params = {
        'device_type': SWITCH_DEVICE_TYPE,
        'ip': ip,
        'port': SWITCH_PORT,
        'username': SWITCH_USERNAME,
        'password': SWITCH_PASSWORD,
        'secret': SWITCH_SECRET,
        'timeout': SWITCH_TIMEOUT,
        'fast_cli': False,
    }
    net_connect = ConnectHandler(**device_params)
    if SWITCH_SECRET:
        net_connect.enable()
    return net_connect


def get_switch_ports(net_connect) -> List[Dict]:
    """دریافت لیست پورت‌های فیزیکی، وضعیت و کانفیگ آن‌ها"""
    out = net_connect.send_command("show interfaces status")
    ports = []
    lines = out.splitlines()
    
    # رد کردن خطوط هدر
    header_found = False
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.startswith("Port") and "Status" in line_clean:
            header_found = True
            continue
        if header_found:
            parts = line_clean.split()
            if len(parts) >= 4:
                port_name = parts[0]
                # فقط پورت‌های اترنت (Gi, Fa, Te, etc.)
                if any(port_name.lower().startswith(p) for p in ["gi", "fa", "te", "eth"]):
                    status = "connected" if "connected" in line_clean and "notconnect" not in line_clean else "notconnect"
                    if "err-disabled" in line_clean:
                        status = "err-disabled"
                    ports.append({
                        "name": port_name,
                        "raw_line": line_clean,
                        "status": status
                    })
    return ports


def show_spinner_wait(seconds: int, message: str = "در حال پردازش"):
    """نمایش مینی‌لودینگ چرخان همراه با نوار پیشرفت روان"""
    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    total_steps = seconds * 10
    start_time = time.time()
    
    for step in range(total_steps):
        elapsed = time.time() - start_time
        remaining = max(0, seconds - int(elapsed))
        frame = spinner_frames[step % len(spinner_frames)]
        progress_pct = int(((step + 1) / total_steps) * 100)
        filled_bar = "█" * (progress_pct // 10)
        empty_bar = "░" * (10 - (progress_pct // 10))
        
        text = f"   {frame} {message} [{filled_bar}{empty_bar}] {remaining:2d}s"
        print(text, end="\r", flush=True)
        time.sleep(0.1)
    
    print(" " * 60, end="\r", flush=True)


def run_cable_diagnostics(net_connect, port_name: str, switch_ip: Optional[str] = None) -> str:
    """اجرای تست TDR سیسکو روی پورت و دریافت تحلیل ۴ زوج سیم به صورت ایمن و با لودینگ"""
    print(f"⚡ در حال ارسال پالس سخت‌افزاری TDR بر روی پورت {port_name}...")
    try:
        out_cmd = net_connect.send_command_timing(f"test cable-diagnostics tdr interface {port_name}", strip_prompt=False)
        if "% Invalid input" in out_cmd or "% Incomplete command" in out_cmd:
            return f"⚠️ این مدل سوئیچ یا اینترفیس از دستور سخت‌افزاری TDR پشتیبانی نمی‌کند."
    except Exception as e:
        return f"⚠️ خطا حین ارسال دستور تست TDR: {e}"
    
    show_spinner_wait(6, f"تحلیل بازتاب فرکانسی جفت‌سیم‌های {port_name}")
    
    try:
        tdr_out = net_connect.send_command(f"show cable-diagnostics tdr interface {port_name}")
        return tdr_out
    except Exception as e:
        return f"⚠️ خطا در خواندن نتیجه TDR ({e})"


def run_error_check(net_connect, port_name: str) -> str:
    """بررسی شمارنده‌های خطا و CRC"""
    cmd = f"show interfaces {port_name} | include line protocol|input errors|CRC|output errors|collisions"
    return net_connect.send_command(cmd)


def send_traffic_test(net_connect, target_ip: str) -> str:
    """ارسال ۵۰ پکت تست پرحجم برای ارزیابی انتقال فریم بدون پکت‌لاس"""
    cmd = f"ping {target_ip} repeat 50 size 1400"
    return net_connect.send_command(cmd, read_timeout=20)


def select_item(prompt_title: str, items: List[str]) -> int:
    """نمایش لیست شماره‌دار و دریافت انتخاب معتبر از کاربر"""
    print(f"\n{prompt_title}:")
    for idx, item in enumerate(items, 1):
        print(f"  [{idx:2d}] {item}")
    
    while True:
        try:
            choice = input(f"\n👉 لطفاً شماره مورد نظر را وارد کنید (1-{len(items)}): ").strip()
            if choice.lower() in ('q', 'exit', 'quit'):
                print("خروج از برنامه.")
                sys.exit(0)
            val = int(choice)
            if 1 <= val <= len(items):
                return val - 1
            print("⚠️ شماره وارد شده در بازه مجاز نیست.")
        except ValueError:
            print("⚠️ لطفاً فقط عدد انگلیسی وارد کنید.")


def main():
    print("=" * 65)
    print("    🔍 ابزار تست جامع کابل شبکه سیسکو (Cisco Cable Tester)")
    print("       بوم‌بان / سیم‌بان - Cisco IOS Diagnostic Tool")
    print("=" * 65)

    # ۱. واکشی سوئیچ‌ها از سیم‌بان
    switches = get_switches_from_db()
    if not switches:
        print("هیچ سوئیچی در دیتابیس یافت نشد!")
        return

    switch_labels = [f"{s['hostname']:<16} ({s['ip']:<15}) [{s['model']}] - {s['status']}" for s in switches]

    # ۲. انتخاب حالت تست
    mode_options = [
        "تست یک‌طرفه سریع (استاندارد، بدون قطعی، مناسب برای همه پورت‌ها/دستگاه‌ها)",
        "تست دوطرفه پیشرفته (بین دو سوئیچ سیسکو همزمان)"
    ]
    mode_idx = select_item("۱) انتخاب نوع آزمایش کابل", mode_options)
    is_dual = (mode_idx == 1)

    # ۳. انتخاب سوئیچ مبدأ
    idx1 = select_item("۲) سوئیچ مورد نظر برای آزمایش", switch_labels)
    sw1 = switches[idx1]

    # ۴. انتخاب پورت در سوئیچ
    print(f"\n🔌 در حال اتصال به سوئیچ: {sw1['hostname']} ({sw1['ip']})...")
    conn1 = None
    try:
        conn1 = connect_to_switch(sw1['ip'])
        print(f"✅ اتصال به {sw1['hostname']} برقرار شد.")
    except Exception as e:
        print(f"❌ خطا در اتصال به {sw1['hostname']}: {e}")
        return

    ports1 = get_switch_ports(conn1)
    if not ports1:
        print("❌ پورت فعالی روی سوئیچ پیدا نشد.")
        conn1.disconnect()
        return

    port_labels1 = [f"{p['name']:<12} [وضعیت: {p['status']}]" for p in ports1]
    port_idx1 = select_item(f"۳) پورت متصل در سوئیچ ({sw1['hostname']})", port_labels1)
    chosen_port1 = ports1[port_idx1]['name']

    conn2 = None
    sw2 = None
    chosen_port2 = None

    if is_dual:
        idx2 = select_item("۴) سوئیچ دوم (مقصد ارتباط)", switch_labels)
        sw2 = switches[idx2]

        print(f"\n🔌 در حال اتصال به سوئیچ دوم: {sw2['hostname']} ({sw2['ip']})...")
        try:
            conn2 = connect_to_switch(sw2['ip'])
            print(f"✅ اتصال به {sw2['hostname']} برقرار شد.")
        except Exception as e:
            print(f"❌ خطا در اتصال به {sw2['hostname']}: {e}")
            conn1.disconnect()
            return

        ports2 = get_switch_ports(conn2)
        if not ports2:
            print("❌ پورت فعالی روی سوئیچ دوم پیدا نشد.")
            conn1.disconnect()
            conn2.disconnect()
            return

        port_labels2 = [f"{p['name']:<12} [وضعیت: {p['status']}]" for p in ports2]
        port_idx2 = select_item(f"۵) پورت متصل در سوئیچ دوم ({sw2['hostname']})", port_labels2)
        chosen_port2 = ports2[port_idx2]['name']

    print(f"\n🚀 در حال اجرای تست‌های تشخیصی روی پورت:")
    if is_dual and sw2:
        print(f"   [{sw1['hostname']}:{chosen_port1}] ⟷ [{sw2['hostname']}:{chosen_port2}]")
    else:
        print(f"   [{sw1['hostname']}:{chosen_port1}]")

    # الف) بررسی وضعیت پورت
    print("\n" + "═" * 55)
    print(f"📊 ۱. وضعیت لینک و سرعت ({sw1['hostname']}:{chosen_port1}):")
    print("─" * 55)
    print(conn1.send_command(f"show interfaces {chosen_port1} status"))

    if is_dual and conn2:
        print(f"\n📊 وضعیت لینک و سرعت در سوئیچ دوم ({sw2['hostname']}:{chosen_port2}):")
        print("─" * 55)
        print(conn2.send_command(f"show interfaces {chosen_port2} status"))

    # ب) تست دیاگنوستیک TDR
    print("\n" + "═" * 55)
    print(f"🧪 ۲. تست سخت‌افزاری کابل (TDR) از سمت {sw1['hostname']}:{chosen_port1}:")
    print("─" * 55)
    tdr_res1 = run_cable_diagnostics(conn1, chosen_port1)
    print(tdr_res1)

    # ج) شمارنده‌های خطا
    print("\n" + "═" * 55)
    print(f"⚠️ ۳. خطاهای لایه فیزیکی و شمارنده نویز (CRC) در {sw1['hostname']}:{chosen_port1}:")
    print("─" * 55)
    try:
        print(run_error_check(conn1, chosen_port1))
    except Exception as e:
        print(f"خطا در دریافت وضعیت خطاها: {e}")

    if is_dual and conn2:
        print(f"\n⚠️ خطاهای لایه فیزیکی در سمت دوم ({sw2['hostname']}:{chosen_port2}):")
        print("─" * 55)
        try:
            print(run_error_check(conn2, chosen_port2))
        except Exception as e:
            print(f"خطا در خواندن خطاهای پورت دوم: {e}")

        # د) تست ترافیک رفت و برگشت
        print("\n" + "═" * 55)
        print(f"📶 ۴. تست انتقال ترافیک ({sw1['hostname']} ➔ {sw2['hostname']} [{sw2['ip']}]):")
        print("─" * 55)
        try:
            ping_res = send_traffic_test(conn1, sw2['ip'])
            print(ping_res)
        except Exception as e:
            print(f"خطا در تست پینگ: {e}")

    try:
        conn1.disconnect()
    except Exception:
        pass
    if conn2:
        try:
            conn2.disconnect()
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("✅ ارزیابی کابل با موفقیت پایان یافت.")
    print("=" * 65)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nعملیات لغو شد.")
        sys.exit(0)
