import os, sys, time, sqlite3
from pathlib import Path
from netmiko import ConnectHandler

SIMBAN_DIR = Path(r'c:/Users/Mehdi/projects/boomban-suite/simban')
DB_PATH = SIMBAN_DIR / 'data' / 'network.db'
STATE_FILE = SIMBAN_DIR / 'scripts' / '.vlan_update_done.txt'

SWITCH_DEVICE_TYPE = 'cisco_ios_telnet'
SWITCH_USERNAME = ''
SWITCH_PASSWORD = '@Aa3603912!'
SWITCH_SECRET = '@Aa3603912!'
SWITCH_PORT = 23

# افزایش چشم‌گیر تایم‌اوت‌ها به دلیل پکت‌لاس و ناپایداری خط
SWITCH_TIMEOUT = 30
GLOBAL_DELAY_FACTOR = 2

TARGET_VLANS = [
    (100, 'edari'),
    (400, 'camera'),
    (500, 'fiber'),
    (600, 'pishgaman-mostagim'),
    (700, 'hotspot'),
    (998, 'CABLE-TEST-ISOLATED'),
]

CONFIG_COMMANDS = []
for vid, vname in TARGET_VLANS:
    CONFIG_COMMANDS.extend([f'vlan {vid}', f' name {vname}'])

# خواندن سوئیچ‌هایی که قبلاً با موفقیت انجام شده‌اند
done_ips = set()
if STATE_FILE.exists():
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        done_ips = set(line.strip() for line in f if line.strip())

conn = sqlite3.connect(DB_PATH)
all_switches = conn.execute('SELECT ip, hostname FROM switches ORDER BY ip').fetchall()
conn.close()

# سوئیچ‌هایی که در اجرای اول شما موفق بودند را از قبل علامت می‌زنیم
initial_successes = {
    '192.168.30.13', '192.168.30.14', '192.168.30.22', '192.168.30.24',
    '192.168.30.25', '192.168.30.30', '192.168.30.31', '192.168.30.32'
}
done_ips.update(initial_successes)

pending_switches = [(ip, name) for ip, name in all_switches if ip not in done_ips]

print(f'Total switches: {len(all_switches)}')
print(f'Already completed: {len(done_ips)}')
print(f'Pending switches to process: {len(pending_switches)}')

success_this_run = 0
failed_this_run = 0

for ip, name in pending_switches:
    print(f'\n--> Connecting to {name} ({ip}) [Retries: 3, Timeout: {SWITCH_TIMEOUT}s]...')
    updated = False
    
    for attempt in range(1, 4):
        try:
            dev = {
                'device_type': SWITCH_DEVICE_TYPE,
                'ip': ip,
                'port': SWITCH_PORT,
                'username': SWITCH_USERNAME,
                'password': SWITCH_PASSWORD,
                'secret': SWITCH_SECRET,
                'timeout': SWITCH_TIMEOUT,
                'global_delay_factor': GLOBAL_DELAY_FACTOR,
                'fast_cli': False,
            }
            net = ConnectHandler(**dev)
            if SWITCH_SECRET:
                net.enable()
            
            # ارسال کانفیگ با هندل خطاهای پرامپت
            net.send_config_set(CONFIG_COMMANDS, read_timeout=30)
            
            # ذخیره با تایم‌اوت بالا
            net.send_command('write memory', expect_string=r'#|OK', read_timeout=30)
            net.disconnect()
            
            print(f'  [SUCCESS] {name} ({ip}) updated and saved!')
            done_ips.add(ip)
            with open(STATE_FILE, 'a', encoding='utf-8') as f:
                f.write(f'{ip}\n')
            
            updated = True
            success_this_run += 1
            break
        except Exception as e:
            print(f'  [Attempt {attempt}/3 failed] {name} ({ip}): {e}')
            time.sleep(2)
            
    if not updated:
        failed_this_run += 1

print(f'\nFinished! Success this run: {success_this_run}, Still failed: {failed_this_run}')
print(f'Overall Progress: {len(done_ips)} / {len(all_switches)} switches done.')
