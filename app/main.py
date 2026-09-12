import asyncio
import queue
import threading
from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from app.config import STATIC_DIR, TEMPLATES_DIR
from app.db import (
    init_db, is_configured, get_settings, save_settings,
    get_switches, get_links, get_vlans, get_connected_devices, get_switch_ports,
    get_switch_details, get_task_schedules, get_task_schedule, save_task_schedule
)
from app.scheduler import start_scheduler, stop_scheduler, reload_task_jobs
from app.scanner import scan_subnet, crawl_cdp, check_all_switches_status
from app.collector import run_full_collection
from app.terminal import TelnetSession

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="Simban - Cisco Switch Intelligence & Web Terminal", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    configured = is_configured()
    settings = get_settings() if configured else {}
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "is_configured": configured,
            "settings": settings
        }
    )

@app.get("/terminal/{switch_ip:path}", response_class=HTMLResponse)
async def render_terminal(request: Request, switch_ip: str):
    return templates.TemplateResponse(
        request=request,
        name="terminal.html",
        context={"switch_ip": switch_ip}
    )

@app.websocket("/ws/terminal/{switch_ip:path}")
async def websocket_terminal(websocket: WebSocket, switch_ip: str):
    await websocket.accept()
    session = TelnetSession(ip=switch_ip, port=23)
    try:
        connected = await session.auto_login(websocket)
        if connected:
            await session.bridge(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"\r\n\x1b[31m❌ Terminal Error: {str(e)}\x1b[0m\r\n")
        except Exception:
            pass
    finally:
        session.close()


@app.get("/api/config")
async def fetch_config():
    return JSONResponse(get_settings())

@app.post("/api/config")
async def update_config(data: dict):
    subnet = data.get("subnet", "").strip()
    if not subnet:
        return JSONResponse({"status": "error", "message": "Subnet (CIDR) is required."}, status_code=400)

    save_settings(
        subnet=subnet,
        username=data.get("username", "").strip(),
        password=data.get("password", "").strip(),
        device_type=data.get("device_type", "cisco_ios_telnet").strip(),
        seed_ips=data.get("seed_ips", "").strip(),
        auto_refresh_hours=int(data.get("auto_refresh_hours", 24))
    )

    return JSONResponse({"status": "success", "message": "Settings saved successfully!"})

@app.get("/api/switches")
async def fetch_switches():
    """
    Standard machine-readable switch inventory & health endpoint for Boomban.
    Output:
    [
      {
        "id": "sw_192_168_1_10",
        "ip": "192.168.1.10",
        "hostname": "Switch-Anbar",
        "model": "WS-C2960-24TT-L",
        "status": "online",
        "last_seen": "2026-09-08T12:00:00Z",
        "latency_ms": 2.4,
        "ports_total": 24,
        "ports_up": 18
      }
    ]
    """
    raw_switches = get_switches()
    formatted = []
    for s in raw_switches:
        ip = s.get("ip", "")
        # Generate stable machine identifier
        sw_id = f"sw_{ip.replace('.', '_')}" if ip else f"sw_{s.get('id', 0)}"
        formatted.append({
            "id": sw_id,
            "ip": ip,
            "hostname": s.get("hostname") or ip,
            "model": s.get("model") or "N/A",
            "serial_number": s.get("serial_number") or "N/A",
            "ios_version": s.get("ios_version") or "N/A",
            "status": s.get("status") or "offline",
            "last_seen": s.get("last_seen"),
            "latency_ms": s.get("latency_ms", 0.0),
            "ports_total": s.get("ports_total", 0),
            "ports_up": s.get("ports_up", 0),
            "updated_at": s.get("updated_at")
        })
    return JSONResponse(formatted)

@app.get("/api/switches/{switch_ip:path}/ports")
async def fetch_switch_ports_endpoint(switch_ip: str):
    """
    Port status & MAC correlation endpoint for Boomban cameras/edge correlation.
    """
    ports = get_switch_ports(switch_ip)
    return JSONResponse({
        "switch_ip": switch_ip,
        "ports_count": len(ports),
        "ports": ports
    })

@app.get("/api/tasks")
async def fetch_tasks():
    return JSONResponse(get_task_schedules())

@app.post("/api/tasks/{task_id}")
async def update_task(task_id: str, data: dict):
    enabled = data.get("enabled")
    interval = data.get("interval_minutes")
    
    if enabled is not None:
        enabled = int(enabled)
    if interval is not None:
        interval = int(interval)

    save_task_schedule(task_id, enabled=enabled, interval_minutes=interval)
    reload_task_jobs()
    
    updated_task = get_task_schedule(task_id)
    return JSONResponse({"status": "success", "task": updated_task})

@app.get("/api/switch/{switch_id:path}")
async def fetch_switch_details(switch_id: str):
    details = get_switch_details(switch_id)
    if not details:
        return JSONResponse({"status": "error", "message": "Switch not found"}, status_code=404)
    return JSONResponse(details)

@app.get("/api/links")
async def fetch_links():
    """
    Returns all discovered inter-switch and CDP links.
    """
    return JSONResponse(get_links())

@app.get("/api/vlans")
async def fetch_vlans():
    return JSONResponse(get_vlans())

@app.get("/api/edge-devices")
async def fetch_edge_devices():
    return JSONResponse(get_connected_devices())

@app.get("/api/stream-log/{action}")
async def stream_log(action: str):
    log_queue = queue.Queue()

    def q_log(msg):
        log_queue.put(str(msg))

    def run_worker():
        try:
            if action == "scan":
                scan_subnet(log_callback=q_log)
            elif action == "crawl_cdp":
                crawl_cdp(log_callback=q_log)
            elif action == "collect":
                run_full_collection(log_callback=q_log)
            elif action == "check_status":
                check_all_switches_status(log_callback=q_log)
            elif action == "full_sequence":
                q_log("🚀 Launching Full Sequence (Scan → CDP Crawl → Collect Data)...")
                scan_subnet(log_callback=q_log)
                crawl_cdp(log_callback=q_log)
                run_full_collection(log_callback=q_log)
            else:
                q_log(f"Unknown action: {action}")
        except Exception as e:
            q_log(f"❌ Error during execution: {e}")
        finally:
            log_queue.put("[FINISHED]")

    threading.Thread(target=run_worker, daemon=True).start()

    async def event_generator():
        while True:
            try:
                # Poll queue asynchronously
                msg = await asyncio.to_thread(log_queue.get, timeout=1.0)
                yield f"data: {msg}\n\n"
                if msg == "[FINISHED]":
                    break
            except queue.Empty:
                yield "data: [PING]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
