"""
upgrade2sshwithenv.py
---------------------
اسکریپت جامع و خودکار جهت خواندن تنظیمات از فایل upgrade2ssh.env و ارتقای سوئیچ سیسکو از طریق Telnet:
- اتصال خودکار از طریق Telnet (پشتیبانی از ورود با رمز لاین یا یوزر/پسورد و رفتن به enable)
- تنظیم Hostname و Domain
- ساخت/بروزرسانی کاربر مدیر (admin) با Privilege 15 و Secret
- تولید Host Key از نوع RSA در صورت نیاز (فعال‌سازی سرویس SSHv2)
- پیکربندی تفکیک احراز هویت AAA طبق گام ۴.۵ مستند:
    * احراز هویت دیتابیس محلی برای SSH
    * متد احراز هویت لاین برای Telnet بدون نام‌کاربری و ورود مستقیم به سطح ۱۵
    * فعال‌سازی هم‌زمان ssh و telnet در transport input خطوط VTY
- استخراج خودکار هش MD5 کلید عمومی SSH کلاینت و تزریق آن از طریق key-hash
- ذخیره تنظیمات روی NVRAM سوئیچ (write memory)
- آزمایش خودکار اتصال SSH بدون نیاز به رمز عبور (Passwordless SSH Verification)
"""

import os
import sys
import time
import base64
import hashlib
import subprocess
from pathlib import Path
from netmiko import ConnectHandler

# جلوگیری از خطای UnicodeEncodeError در کنسول ویندوز (cp1256 / cp1252)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_env(env_path: Path) -> dict:
    """خواندن متغیرها از فایل env بدون نیاز به وابستگی‌های خارجی"""
    config = {}
    if not env_path.exists():
        return config
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            config[key.strip()] = val.strip().strip('"').strip("'")
    return config


def get_pubkey_md5(pubkey_path: str) -> str:
    """محاسبه هش MD5 کلید عمومی باینری OpenSSH جهت سازگاری با دستور key-hash سیسکو"""
    p = Path(os.path.expandvars(pubkey_path)).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"فایل کلید عمومی یافت نشد: {p}")
    with open(p, "r", encoding="utf-8") as f:
        line = f.read().strip()
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("فرمت کلید عمومی نامعتبر است.")
    raw_key = base64.b64decode(parts[1])
    return hashlib.md5(raw_key).hexdigest().upper()


def main():
    script_dir = Path(__file__).resolve().parent
    env_file = Path(sys.argv[1]) if len(sys.argv) > 1 else (script_dir / "upgrade2ssh.env")
    if not env_file.exists():
        env_file = script_dir.parent / ".env"

    if not env_file.exists():
        print(f"[x] خطا: فایل تنظیمات در مسیر {env_file} یافت نشد!")
        sys.exit(1)

    print(f"[*] بارگذاری تنظیمات از: {env_file.resolve()}")
    cfg = load_env(env_file)

    # اطلاعات اتصال تلنت
    telnet_host = cfg.get("TELNET_HOST") or cfg.get("SWITCH_IP", "192.168.30.135")
    telnet_port = int(cfg.get("TELNET_PORT", 23))
    telnet_user = cfg.get("TELNET_USERNAME", "")
    telnet_pass = cfg.get("TELNET_PASSWORD", "cisco")
    telnet_enable_pass = cfg.get("TELNET_ENABLE_PASSWORD", telnet_pass)
    telnet_timeout = int(cfg.get("TELNET_TIMEOUT", 15))

    # مشخصات جدید سوئیچ
    sw_user = cfg.get("SWITCH_USERNAME", "admin")
    sw_secret = cfg.get("SWITCH_SECRET", "Cisco123!")
    sw_privilege = cfg.get("SWITCH_PRIVILEGE", "15")
    sw_hostname = cfg.get("SWITCH_HOSTNAME", "").strip()
    sw_domain = cfg.get("SWITCH_DOMAIN", "").strip()
    new_telnet_pass = cfg.get("NEW_TELNET_PASSWORD", telnet_pass)

    pubkey_path = cfg.get("PUBKEY_PATH", r"C:\Users\Mehdi\.ssh\id_rsa_cisco.pub")
    gen_rsa = cfg.get("GENERATE_RSA_HOSTKEY", "true").lower() == "true"
    rsa_modulus = cfg.get("RSA_KEY_MODULUS", "2048")

    # استخراج هش کلید عمومی
    print(f"[*] بررسی کلید عمومی در مسیر: {pubkey_path}")
    try:
        key_hash = get_pubkey_md5(pubkey_path)
        print(f"[+] هش MD5 کلید عمومی محاسبه شد: {key_hash}")
    except Exception as e:
        print(f"[x] خطا در محاسبه هش کلید عمومی: {e}")
        sys.exit(1)

    # اتصال از طریق Telnet
    print(f"[*] در حال برقراری اتصال Telnet به {telnet_host}:{telnet_port} ...")
    device_params = {
        "device_type": "cisco_ios_telnet",
        "host": telnet_host,
        "port": telnet_port,
        "username": telnet_user,
        "password": telnet_pass,
        "secret": telnet_enable_pass,
        "conn_timeout": telnet_timeout,
        "fast_cli": False,
    }

    try:
        net = ConnectHandler(**device_params)
        net.enable()
        prompt = net.find_prompt()
        print(f"[+] اتصال Telnet با موفقیت برقرار شد. پرامپت فعلی: {prompt}")
    except Exception as e:
        print(f"[x] خطا در برقراری اتصال Telnet: {e}")
        sys.exit(1)

    try:
        # مرحله ۱: هویت پایه و کاربر مدیر
        print("[*] اعمال مشخصات پایه و کاربر مدیر...")
        base_cmds = []
        if sw_hostname:
            base_cmds.append(f"hostname {sw_hostname}")
        if sw_domain:
            base_cmds.append(f"ip domain-name {sw_domain}")
        base_cmds.extend([
            f"username {sw_user} privilege {sw_privilege} secret {sw_secret}",
            "ip ssh version 2",
        ])
        if base_cmds:
            out = net.send_config_set(base_cmds)
            print(out)

        # مرحله ۲: بررسی و تولید کلید RSA برای سرویس SSH در صورت نیاز
        if gen_rsa:
            print(f"[*] بررسی وضعیت کلید میزبان RSA...")
            key_check = net.send_command("show crypto key mypubkey rsa")
            if f"{sw_user}" in key_check or "Key name:" in key_check or "ssh-rsa" in key_check:
                print("[+] کلید میزبان RSA از قبل روی سوئیچ وجود دارد و فعال است.")
            else:
                print(f"[*] در حال تولید کلید میزبان RSA (modulus {rsa_modulus})...")
                # در سیسکو ابتدا دستور را بدون آرگومان در حالت کانفیگ اجرا می‌کنیم تا مدولوس را بپرسد یا با دستور کامل در مد کانفیگ
                rsa_out = net.send_config_set([f"crypto key generate rsa modulus {rsa_modulus}"])
                if "% Invalid input" in rsa_out or "% Incomplete" in rsa_out:
                    # اجرای تعاملی در صورت نیاز IOS قدیمی‌تر
                    rsa_out = net.send_command_timing("crypto key generate rsa")
                    if "modulus" in rsa_out.lower() or "how many bits" in rsa_out.lower() or ":" in rsa_out:
                        rsa_out += net.send_command_timing(f"{rsa_modulus}")
                    if "yes/no" in rsa_out.lower() or "replace" in rsa_out.lower():
                        rsa_out += net.send_command_timing("yes")
                print(rsa_out)
            time.sleep(1)

        # مرحله ۳: پیکربندی معماری AAA و VTY (گام ۴.۵ مستند)
        print("[*] پیکربندی معماری AAA و جداسازی ورود Telnet و SSH...")
        aaa_and_vty_cmds = [
            "aaa new-model",
            "aaa authentication login TELNET_AUTH line",
            "aaa authentication login default local",
            "aaa authorization exec default local if-authenticated",
            "line vty 0 15",
            "privilege level 15",
            f"password {new_telnet_pass}",
            "login authentication TELNET_AUTH",
            "transport input ssh telnet",
            "exit"
        ]
        out_vty = net.send_config_set(aaa_and_vty_cmds)
        print(out_vty)

        # مرحله ۴: تزریق کلید عمومی SSH با متد key-hash (گام ۴.۶ مستند)
        print(f"[*] تزریق کلید عمومی SSH برای کاربر '{sw_user}'...")
        pubkey_cmds = [
            "ip ssh pubkey-chain",
            f"username {sw_user}",
            f"key-hash ssh-rsa {key_hash}",
            "exit",
            "exit"
        ]
        out_pubkey = net.send_config_set(pubkey_cmds)
        print(out_pubkey)

        # مرحله ۵: ذخیره دائمی در حافظه NVRAM
        print("[*] ذخیره دائمی پیکربندی در NVRAM (write memory)...")
        out_save = net.send_command("write memory", read_timeout=20)
        print(out_save)
        print("[+] تمام تنظیمات با موفقیت روی سوئیچ ثبت شدند!")

    except Exception as e:
        print(f"[x] خطا هنگام ارسال فرامین به سوئیچ: {e}")
    finally:
        net.disconnect()
        print("[*] اتصال Telnet قطع شد.")

    # آزمایش و تست اتصال SSH
    print(f"\n[*] در حال آزمایش نهایی اتصال SSH به {telnet_host} با کلید عمومی...")
    test_ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        f"{sw_user}@{telnet_host}",
        "show version | include (Model|uptime|Version)"
    ]

    res = subprocess.run(test_ssh_cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("=" * 60)
        print("[+] تبریک! اتصال SSH بدون رمز عبور با موفقیت راستی‌آزمایی شد:")
        print(res.stdout.strip())
        print("=" * 60)
    else:
        print("=" * 60)
        print("[-] اتصال آزمایشی SSH مستقیم:")
        if res.stdout.strip():
            print("Output:\n", res.stdout.strip())
        if res.stderr.strip():
            print("Message / Notice:\n", res.stderr.strip())
        print("\nنکته: در صورتی که با خطای الگوریتم/سایفر مواجه شدید، تنظیمات ~/.ssh/config را طبق بخش ۵ مستند بررسی فرمایید.")
        print("=" * 60)


if __name__ == "__main__":
    main()
