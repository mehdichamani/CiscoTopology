import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "network.db")
TEMPLATES_DIR = os.path.join(BASE_DIR, "app", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# SSH Key and Client Settings for Cisco Passwordless Auth
SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa_cisco")
SSH_CONFIG_PATH = os.path.expanduser("~/.ssh/config")

def build_netmiko_device(ip: str, settings: dict = None) -> dict:
    """
    Build standard Netmiko device parameters supporting passwordless SSH key authentication.
    Falls back gracefully if telnet or custom credentials are requested.
    """
    if settings is None:
        settings = {}
    
    device_type = settings.get("device_type") or "cisco_ios_ssh"
    username = settings.get("username") or "admin"
    password = settings.get("password") or ""

    device_dict = {
        "device_type": "cisco_ios" if "ssh" in device_type else "cisco_ios_telnet",
        "host": str(ip),
        "username": username,
        "conn_timeout": 10,
    }

    if password:
        device_dict["password"] = password
        device_dict["secret"] = password

    if "ssh" in device_type:
        if os.path.isfile(SSH_KEY_PATH):
            device_dict["use_keys"] = True
            device_dict["key_file"] = SSH_KEY_PATH
            device_dict["allow_agent"] = False
            device_dict["disabled_algorithms"] = dict(pubkeys=["rsa-sha2-512", "rsa-sha2-256"])
        if os.path.isfile(SSH_CONFIG_PATH):
            device_dict["ssh_config_file"] = SSH_CONFIG_PATH

    return device_dict


