#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ابزار تست سریع بنچ‌مارک کابل شبکه (Cisco Cable Bench Tester)
اختصاصی برای پورت‌های ۱ و ۲ سوئیچ IT-MIZ (VLAN 998 ایزوله)
اکوسیستم بوم‌بان / سیم‌بان
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

# تنظیم خروجی کنسول برای کاراکترهای فارسی و یونیکد
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# اضافه کردن مسیر پروژه
SIMBAN_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SIMBAN_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(SIMBAN_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")

from netmiko import ConnectHandler

# تنظیمات پیش‌فرض بنچ‌مارک تست
BENCH_SWITCH_IP = os.getenv("BENCH_SWITCH_IP", "192.168.30.13")
BENCH_PORT_1 = "GigabitEthernet1/0/1"
BENCH_PORT_2 = "GigabitEthernet1/0/2"

SWITCH_DEVICE_TYPE = os.getenv("SWITCH_DEVICE_TYPE", "cisco_ios_telnet")
SWITCH_USERNAME = os.getenv("SWITCH_USERNAME", "")
SWITCH_PASSWORD = os.getenv("SWITCH_PASSWORD", "")
SWITCH_SECRET = os.getenv("SWITCH_SECRET", "")
SWITCH_PORT = int(os.getenv("SWITCH_TELNET_PORT", 23))
SWITCH_TIMEOUT = int(os.getenv("SWITCH_TIMEOUT", 10))


def get_connection():
    """اتصال به سوئیچ بنچ‌مارک تست"""
    device_params = {
        'device_type': SWITCH_DEVICE_TYPE,
        'ip': BENCH_SWITCH_IP,
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


def run_tdr(net_connect, port: str) -> str:
    """اجرای تست بازتاب الکتریکی TDR و دریافت وضعیت جفت‌سیم‌ها همراه با مینی‌لودینگ"""
    print(f"⚡ در حال ارسال پالس TDR به پورت {port}...")
    try:
        net_connect.send_command_timing(f"test cable-diagnostics tdr interface {port}", strip_prompt=False)
    except Exception as e:
        return f"خطا در ارسال پالس: {e}"

    show_spinner_wait(6, f"تحلیل فرکانس و بازتاب امواج {port}")

    return net_connect.send_command(f"show cable-diagnostics tdr interface {port}")


def check_errors(net_connect, port: str) -> str:
    """بررسی شمارنده‌های سلامت لایه فیزیکی"""
    cmd = f"show interfaces {port} | include line protocol|input errors|CRC|output errors|collisions"
    return net_connect.send_command(cmd)


def main():
    print("=" * 68)
    print("\u200F🧪 ابزار تست سخت‌افزاری کابل شبکه (IT-MIZ Cable Bench)")
    print(f"   پورت‌های تست: {BENCH_PORT_1} <--> {BENCH_PORT_2}")
    print(f"   سوئیچ بنچ: {BENCH_SWITCH_IP} (VLAN 998 ایزوله)")
    print("=" * 68)

    print(f"\n\u200F🔌 در حال اتصال به سوئیچ تست ({BENCH_SWITCH_IP})...")
    try:
        conn = get_connection()
        print("✅ ارتباط با موفقیت برقرار شد.\n")
    except Exception as e:
        print(f"❌ خطا در برقراری ارتباط با سوئیچ: {e}")
        return

    # ۱. بررسی اتصال فیزیکی اولیه
    print("─" * 68)
    print("\u200F📊 [مرحله ۱] وضعیت اتصال فیزیکی دو پورت:")
    status_raw = conn.send_command("show interfaces status | include Gi1/0/1 |Gi1/0/2 ")
    print(status_raw)

    is_p1_connected = "connected" in conn.send_command(f"show interfaces {BENCH_PORT_1} status")
    is_p2_connected = "connected" in conn.send_command(f"show interfaces {BENCH_PORT_2} status")

    if not is_p1_connected and not is_p2_connected:
        print("\n\u200F⚠️ توجه: هیچ کابلی روی پورت ۱ یا ۲ تشخیص داده نشد.")
        print("\u200F   (اگر کابل وصل است و چراغ‌ها خاموش هستند، ممکن است کابل قطعی کامل داشته باشد)")

    # ۲. تست سخت‌افزاری پورت ۱
    print("\n" + "─" * 68)
    print(f"\u200F🔬 [مرحله ۲] تست بازتاب امواج الکتریکی (TDR) - پورت اول:")
    print(f"   اینترفیس: {BENCH_PORT_1}")
    tdr_1 = run_tdr(conn, BENCH_PORT_1)
    print(tdr_1)

    # ۳. تست سخت‌افزاری پورت ۲ (در صورت وصل بودن)
    print("\n" + "─" * 68)
    print(f"\u200F🔬 [مرحله ۳] تست بازتاب امواج الکتریکی (TDR) - پورت دوم:")
    print(f"   اینترفیس: {BENCH_PORT_2}")
    tdr_2 = run_tdr(conn, BENCH_PORT_2)
    print(tdr_2)

    # ۴. خطاهای لایه فیزیکی و نویز
    print("\n" + "─" * 68)
    print("\u200F⚠️ [مرحله ۴] بررسی خطاهای فیزیکی و شمارنده نویز CRC:")
    print(f"\u200F• پورت اول ({BENCH_PORT_1}):")
    print(check_errors(conn, BENCH_PORT_1))
    print(f"\n\u200F• پورت دوم ({BENCH_PORT_2}):")
    print(check_errors(conn, BENCH_PORT_2))

    # ۵. شمارنده بسته‌ها
    print("\n" + "─" * 68)
    print("\u200F📈 [مرحله ۵] آمار تبادل بسته‌ها روی لینک:")
    p1_pkts = conn.send_command(f"show interfaces {BENCH_PORT_1} | include packets input|packets output").strip()
    p2_pkts = conn.send_command(f"show interfaces {BENCH_PORT_2} | include packets input|packets output").strip()
    print(f"Port 1:\n{p1_pkts}")
    print(f"Port 2:\n{p2_pkts}")

    conn.disconnect()

    print("\n" + "=" * 68)
    print("✅ ارزیابی بنچ‌مارک به پایان رسید.")
    print("=" * 68)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nتست متوقف شد.")
        sys.exit(0)
