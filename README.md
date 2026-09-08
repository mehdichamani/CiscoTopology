# CiscoToolsV2

> [!NOTE]
> **اطلاعیه تغییر نام و یکپارچه‌سازی:** این پروژه به زودی با نام رسمی **سیم‌بان (Simban)** و با ساختار پوشه `simban` در قالب اکوسیستم **بوم‌بان (Boomban)** به عنوان ماژول تخصصی پایش، ترسیم توپولوژی و مدیریت سوییچ‌های سیسکو به فعالیت خود ادامه خواهد داد.

A web dashboard for discovering, mapping, and managing Cisco switches on a local network. Built with FastAPI + Netmiko, with a live terminal, topology view, and scheduled collection.

## Features

- **Subnet scanning** — probes IPs for Telnet/SSH reachable switches
- **CDP crawl** — walks CDP neighbors to build inter-switch links
- **Data collection** — pulls model, serial, IOS version, VLANs, connected devices
- **Topology view** — visual map of switches and links
- **Web terminal** — Telnet into any switch from the browser (WebSocket)
- **Scheduled tasks** — auto-refresh scans/collection on an interval (APScheduler)
- **Status checks** — online/offline monitoring of known switches

## Requirements

- Python 3.9+
## Setup & Run (راه‌اندازی و اجرا)

### Windows (PowerShell):
```powershell
# منوی تعاملی و مدیریت کامل
.\start.ps1

# یا اجرای مستقیم در پس‌زمینه
.\start.ps1 -Action start-bg -Port 29999
```

### Linux & macOS (Bash):
```bash
chmod +x start.sh
./start.sh
```

داشبورد به طور پیش‌فرض بر روی آدرس زیر در دسترس خواهد بود:
`http://localhost:29999` (یا `http://127.0.0.1:29999`)

Open the dashboard, enter your subnet CIDR and Cisco credentials, then run a scan or the full sequence (Scan → CDP Crawl → Collect).

## Tech Stack

- **FastAPI** + Uvicorn — backend & API
- **Netmiko** — switch connectivity (Telnet/SSH)
- **APScheduler** — scheduled tasks
- **Jinja2** — templates
- **SQLite** — local data store (`data/network.db`)

## Project Structure

```
app/
  main.py        # FastAPI app, routes, WebSocket terminal
  config.py      # paths
  db.py          # SQLite schema & queries
  scanner.py     # subnet scan, CDP crawl, status checks
  collector.py   # show commands parsing (version, VLANs, devices)
  scheduler.py   # APScheduler task jobs
  terminal.py    # Telnet WebSocket bridge
  static/        # CSS, JS, translations
  templates/     # index.html, terminal.html
data/            # SQLite DB (gitignored)
```

## Notes

- Credentials are stored locally in `data/network.db`. The dashboard binds to `127.0.0.1` only — do not expose it on a public network.
- Telnet transmits credentials in cleartext; prefer SSH-capable devices where possible.
