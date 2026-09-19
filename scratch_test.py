import os
from netmiko import ConnectHandler

key_path = os.path.expanduser("~/.ssh/id_rsa_cisco")

device = {
    "device_type": "cisco_ios",
    "host": "192.168.30.30",
    "username": "admin",
    "use_keys": True,
    "key_file": key_path,
    "allow_agent": False,
    "conn_timeout": 10,
    "disabled_algorithms": dict(pubkeys=["rsa-sha2-512", "rsa-sha2-256"]),
}

try:
    with ConnectHandler(**device) as net:
        prompt = net.find_prompt()
        print("Netmiko Connected! Prompt is:", prompt)
        res = net.send_command("show cdp neighbors")
        print("CDP neighbors lines:", len(res.splitlines()))
except Exception as e:
    print("Netmiko error:", type(e), e)
