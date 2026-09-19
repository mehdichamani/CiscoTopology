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
BENCH_SWITCH_IP = os.getenv("BENCH_SWITCH_IP", "192.168.30.12")
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


import re


def parse_tdr_pairs(tdr_output: str) -> Dict[str, Dict[str, str]]:
    """استخراج وضعیت زوج‌سیم‌ها از خروجی TDR"""
    pairs_data = {}
    pattern = re.compile(
        r'(Pair [A-D])\s+(\d+(?:\s*\+/-\s*\d+)?\s*(?:meters|m)?)\s+(?:(Pair [A-D]|N/A|\S+)\s+)?(Normal|Open|Short|Impedance Mismatch|Unknown|\w+)',
        re.IGNORECASE
    )
    for line in tdr_output.splitlines():
        match = pattern.search(line)
        if match:
            pair_name = match.group(1).title()
            length_str = match.group(2).strip()
            remote_pair = match.group(3) if match.group(3) else "-"
            status = match.group(4).capitalize()
            pairs_data[pair_name] = {
                "length": length_str,
                "remote": remote_pair,
                "status": status
            }
    return pairs_data


def parse_error_counters(error_output: str) -> Dict[str, int]:
    """استخراج خطاهای CRC و Input/Output errors"""
    data = {"crc": 0, "input_errors": 0, "output_errors": 0, "collisions": 0}
    crc_m = re.search(r'(\d+)\s+CRC', error_output, re.IGNORECASE)
    if crc_m:
        data["crc"] = int(crc_m.group(1))
    in_m = re.search(r'(\d+)\s+input errors', error_output, re.IGNORECASE)
    if in_m:
        data["input_errors"] = int(in_m.group(1))
    out_m = re.search(r'(\d+)\s+output errors', error_output, re.IGNORECASE)
    if out_m:
        data["output_errors"] = int(out_m.group(1))
    col_m = re.search(r'(\d+)\s+collisions', error_output, re.IGNORECASE)
    if col_m:
        data["collisions"] = int(col_m.group(1))
    return data


def print_executive_summary(p1_connected: bool, p2_connected: bool, tdr_p1: str, errors_p1: str, errors_p2: str):
    """رسم جعبه خلاصه و ارزیابی نهایی کابل شبکه"""
    pairs = parse_tdr_pairs(tdr_p1)
    err1 = parse_error_counters(errors_p1)
    err2 = parse_error_counters(errors_p2)
    total_crc = err1["crc"] + err2["crc"]

    print("\n" + "═" * 68)
    print("\u200F📋 خلاصه نتایج و ارزیابی نهایی سلامت کابل (Executive Summary):")
    print("═" * 68)

    # ۱. وضعیت جفت‌سیم‌ها
    pair_a = pairs.get("Pair A", {}).get("status", "Unknown")
    pair_b = pairs.get("Pair B", {}).get("status", "Unknown")
    pair_c = pairs.get("Pair C", {}).get("status", "Unknown")
    pair_d = pairs.get("Pair D", {}).get("status", "Unknown")

    print("\u200F🔹 وضعیت زوج‌سیم‌ها:")
    print(f"   • Pair A (1-2): {pair_a:<10} | Pair B (3-6): {pair_b:<10}")
    print(f"   • Pair C (4-5): {pair_c:<10} | Pair D (7-8): {pair_d:<10}")

    # طول کابل
    cable_length = pairs.get("Pair A", {}).get("length", "نامشخص")
    print(f"\n\u200F🔹 طول تخمینی کابل: {cable_length}")

    # نویز و خطا
    if total_crc == 0:
        print("\u200F🔹 خطای نویز فیزیکی (CRC): 0 (عالی - بدون نویز)")
    else:
        print(f"\u200F🔹 خطای نویز فیزیکی (CRC): {total_crc} ⚠️ (احتمال تداخل الکترومغناطیسی یا سربندی ضعیف)")

    # ارزیابی نهایی (Verdict)
    print("\n" + "─" * 68)
    if pair_a == "Normal" and pair_b == "Normal" and pair_c == "Normal" and pair_d == "Normal":
        print("\u200F🎯 وضعیت نهایی کابل: 🟢 سالم کامل (1000Mbps Gigabit Ready)")
        print("\u200F   هر ۴ جفت‌سیم سالم بوده و حداکثر پهنای باند گیگابیت در دسترس است.")
    elif pair_a == "Normal" and pair_b == "Normal" and (pair_c in ["Open", "Short"] or pair_d in ["Open", "Short"]):
        print("\u200F🎯 وضعیت نهایی کابل: 🟡 کابل دو زوج یا قطع در C/D (محدود به 100Mbps)")
        print("\u200F   جفت‌های دیتا سالم‌اند اما زوج‌های ۴-۵ یا ۷-۸ متصل نیستند (سرعت فراتر از ۱۰۰ مگابیت نمی‌رود).")
    elif not p1_connected and not p2_connected and pair_a in ["Open", "Unknown"]:
        print("\u200F🎯 وضعیت نهایی کابل: 🔴 قطع کامل یا کابل وصل نیست (Disconnected / Faulty)")
    else:
        print("\u200F🎯 وضعیت نهایی کابل: ⚠️ نیاز به بررسی سوکت و سربندی (سیم‌بندی ناقص یا ناپایدار)")
    print("═" * 68)


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
    raw_status = conn.send_command("show interfaces status")
    # فیلتر دقیق فقط برای پورت‌های بنچ‌مارک (یا پورت‌های اختصاص یافته به VLAN 998)
    bench_short_ports = ("Gi1/0/1 ", "Gi1/0/2 ")
    filtered_lines = [
        line for line in raw_status.splitlines()
        if line.startswith("Port") or any(line.startswith(p) for p in bench_short_ports)
    ]
    print("\n".join(filtered_lines))

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
    err_p1 = check_errors(conn, BENCH_PORT_1)
    print(err_p1)
    print(f"\n\u200F• پورت دوم ({BENCH_PORT_2}):")
    err_p2 = check_errors(conn, BENCH_PORT_2)
    print(err_p2)

    # ۵. شمارنده بسته‌ها
    print("\n" + "─" * 68)
    print("\u200F📈 [مرحله ۵] آمار تبادل بسته‌ها روی لینک:")
    p1_pkts = conn.send_command(f"show interfaces {BENCH_PORT_1} | include packets input|packets output").strip()
    p2_pkts = conn.send_command(f"show interfaces {BENCH_PORT_2} | include packets input|packets output").strip()
    print(f"Port 1:\n{p1_pkts}")
    print(f"Port 2:\n{p2_pkts}")

    conn.disconnect()

    # ۶. نمایش باکس خلاصه وضعیت و ارزیابی نهایی
    print_executive_summary(is_p1_connected, is_p2_connected, tdr_1, err_p1, err_p2)

    print("\n" + "=" * 68)
    print("✅ ارزیابی بنچ‌مارک به پایان رسید.")
    print("=" * 68)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nتست متوقف شد.")
        sys.exit(0)
