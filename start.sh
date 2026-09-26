#!/usr/bin/env bash
# ==============================================================================
# Simban Native Manager (Bash TUI - Clean & Dual Language)
# Cisco Switch Management & Topology
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ACTION="${1:-}"
PORT="${2:-}"
NO_BROWSER=0
RELOAD=0
IN_PARENT_SESSION=0

# Parse arguments & flags
for arg in "$@"; do
    case "$arg" in
        --no-browser|-NoBrowser)
            NO_BROWSER=1
            ;;
        --reload|-Reload)
            RELOAD=1
            ;;
        --in-parent-session|-InParentSession)
            IN_PARENT_SESSION=1
            ;;
    esac
done

if [ -n "$BOOMBAN_PARENT" ]; then
    IN_PARENT_SESSION=1
fi

# Read PORT from .env if not supplied
if [ -z "$PORT" ] || [ "$PORT" = "--no-browser" ] || [ "$PORT" = "--reload" ] || [ "$PORT" = "--in-parent-session" ]; then
    PORT=23458
    if [ -f ".env" ]; then
        ENV_PORT=$(grep -E '^\s*PORT\s*=' .env | head -n1 | cut -d '=' -f2 | tr -d ' "\r\n')
        if [ -n "$ENV_PORT" ]; then
            PORT="$ENV_PORT"
        fi
    fi
fi

WEB_PID_FILE="$SCRIPT_DIR/data/simban_web.pid"
LEGACY_PID_FILE="$SCRIPT_DIR/data/ciscotopology_web.pid"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/simban.service"

# Styling & Logging
CYAN='\033[0;36m'
DARK_CYAN='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
WHITE='\033[1;37m'
DARK_GRAY='\033[1;30m'
NC='\033[0m'

write_log_info() {
    local label="$1" en="$2" fa="$3"
    printf "  ${CYAN}●${NC} ${DARK_CYAN}[%s]${NC} ${WHITE}%s${NC} " "$label" "$en"
    if [ -n "$fa" ]; then printf "${DARK_GRAY}│ %s${NC}\n" "$fa"; else printf "\n"; fi
}

write_log_ok() {
    local label="$1" en="$2" fa="$3"
    printf "  ${GREEN}●${NC} ${DARK_CYAN}[%s]${NC} ${WHITE}%s${NC} " "$label" "$en"
    if [ -n "$fa" ]; then printf "${DARK_GRAY}│ %s${NC}\n" "$fa"; else printf "\n"; fi
}

write_log_warn() {
    local label="$1" en="$2" fa="$3"
    printf "  ${YELLOW}●${NC} ${YELLOW}[WARN: %s]${NC} ${WHITE}%s${NC} " "$label" "$en"
    if [ -n "$fa" ]; then printf "${DARK_GRAY}│ %s${NC}\n" "$fa"; else printf "\n"; fi
}

write_log_err() {
    local label="$1" en="$2" fa="$3"
    printf "  ${RED}●${NC} ${RED}[ERROR: %s]${NC} ${WHITE}%s${NC} " "$label" "$en"
    if [ -n "$fa" ]; then printf "${DARK_GRAY}│ %s${NC}\n" "$fa"; else printf "\n"; fi
}

test_port_active() {
    local p="$1"
    if command -v nc >/dev/null 2>&1; then
        nc -z 127.0.0.1 "$p" >/dev/null 2>&1 && return 0 || return 1
    elif command -v ss >/dev/null 2>&1; then
        ss -tuln | grep -q ":$p " && return 0 || return 1
    elif command -v lsof >/dev/null 2>&1; then
        lsof -i :"$p" >/dev/null 2>&1 && return 0 || return 1
    else
        (timeout 1 bash -c "</dev/tcp/127.0.0.1/$p") >/dev/null 2>&1 && return 0 || return 1
    fi
}

open_browser_url() {
    local url="$1"
    if [ "$NO_BROWSER" -eq 0 ]; then
        write_log_info "Browser" "Opening browser at $url..." "در حال باز کردن مرورگر..."
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$url" >/dev/null 2>&1 &
        elif command -v wslview >/dev/null 2>&1; then
            wslview "$url" >/dev/null 2>&1 &
        elif command -v open >/dev/null 2>&1; then
            open "$url" >/dev/null 2>&1 &
        else
            write_log_warn "Browser" "No browser utility (xdg-open/wslview/open) found." "ابزار باز کردن مرورگر یافت نشد."
        fi
    fi
}

ensure_uv() {
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$HOME/.astral/bin:$PATH"
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi
    write_log_warn "Astral uv" "Astral uv tool not found. Installing..." "ابزار uv یافت نشد. در حال نصب..."
    if command -v python3 >/dev/null 2>&1; then
        python3 -m pip install -q uv 2>/dev/null || true
        if command -v uv >/dev/null 2>&1; then
            write_log_ok "Astral uv" "Installed successfully." "با موفقیت نصب شد."
            return 0
        fi
    fi
    write_log_warn "Astral uv" "Installation failed. Falling back to pip." "نصب uv ناموفق بود؛ استفاده از pip."
    return 1
}

ensure_venv() {
    local has_uv=0
    if ensure_uv; then has_uv=1; fi

    if [ ! -f ".venv/bin/python" ]; then
        write_log_info "SETUP" "Creating virtual environment (.venv)..." "در حال ساخت محیط مجازی (.venv)..."
        if [ "$has_uv" -eq 1 ]; then
            uv venv .venv --python python3 2>/dev/null || uv venv .venv
        else
            python3 -m venv .venv
        fi
        if [ $? -ne 0 ]; then
            write_log_err "VENV" "Failed to create virtual environment." "ساخت محیط مجازی با خطا مواجه شد."
            return 1
        fi
        write_log_ok "VENV" "Virtual environment created." "محیط مجازی ساخته شد."
    fi
    return 0
}

ensure_env_files() {
    mkdir -p data logs
    if [ ! -f ".env" ] && [ -f ".env.example" ]; then
        cp ".env.example" ".env"
        write_log_warn ".env" "Created from .env.example. Please review." "فایل .env از نمونه ساخته شد."
    fi
}

install_dependencies() {
    ensure_venv || return 1
    write_log_info "PACKAGES" "Installing dependencies..." "در حال نصب وابستگی‌ها..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install -r requirements.txt --python .venv/bin/python
    else
        .venv/bin/python -m pip install -q --upgrade pip
        .venv/bin/python -m pip install -q -r requirements.txt
    fi
    ensure_env_files
    write_log_ok "PACKAGES" "All dependencies installed successfully." "تمامی وابستگی‌ها نصب شدند."
}

update_dependencies() {
    ensure_venv || return 1
    write_log_info "PACKAGES" "Updating packages..." "در حال بروزرسانی بسته‌ها..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --upgrade -r requirements.txt --python .venv/bin/python
    else
        .venv/bin/python -m pip install -q --upgrade -r requirements.txt
    fi
    write_log_ok "PACKAGES" "All packages updated successfully." "تمامی بسته‌ها بروزرسانی شدند."
}

get_active_process() {
    WEB_PID=""
    if [ -f "$WEB_PID_FILE" ]; then
        local p
        p=$(cat "$WEB_PID_FILE" 2>/dev/null | tr -d ' \r\n')
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
            WEB_PID="$p"
        fi
    fi

    if [ -z "$WEB_PID" ] && [ -f "$LEGACY_PID_FILE" ]; then
        local p
        p=$(cat "$LEGACY_PID_FILE" 2>/dev/null | tr -d ' \r\n')
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
            WEB_PID="$p"
        fi
    fi

    if [ -z "$WEB_PID" ]; then
        local found
        found=$(pgrep -f "app.main:app" | head -n 1 || true)
        if [ -n "$found" ] && kill -0 "$found" 2>/dev/null; then
            WEB_PID="$found"
        fi
    fi
}

get_server_status() {
    get_active_process
    if [ -n "$WEB_PID" ]; then
        printf "  ${GREEN}●${NC} Web Service: ${GREEN}RUNNING (PID: %s)${NC}\n" "$WEB_PID"
        printf "  ${DARK_GRAY}→ URL: ${CYAN}http://localhost:%s${NC}\n" "$PORT"
        return 0
    else
        printf "  ${DARK_GRAY}●${NC} Web Service: ${DARK_GRAY}STOPPED${NC}\n"
        return 1
    fi
}

test_health_check() {
    printf "\n  ${CYAN}┌── System Health Check ───────────────────────────────────────────┐${NC}\n"
    printf "  ${CYAN}│ Simban Cisco Switch Management Verification                      │${NC}\n"
    printf "  ${CYAN}└──────────────────────────────────────────────────────────────────┘${NC}\n"

    if command -v python3 >/dev/null 2>&1; then
        local py_ver
        py_ver=$(python3 --version 2>&1 | tr -d '\r\n')
        write_log_ok "Python" "$py_ver" "پایتون آماده است"
    else
        write_log_err "Python" "Not Installed!" "پایتون نصب نیست!"
    fi

    if command -v uv >/dev/null 2>&1; then
        local uv_ver
        uv_ver=$(uv --version 2>&1 | tr -d '\r\n')
        write_log_ok "Astral uv" "$uv_ver" "ابزار uv آماده است"
    else
        write_log_warn "Astral uv" "Not found (using pip)" "ابزار uv یافت نشد"
    fi

    if [ -f ".venv/bin/python" ]; then
        write_log_ok "Virtual Env" "Ready (.venv)" "محیط مجازی آماده است"
    else
        write_log_err "Virtual Env" "Missing (.venv)" "محیط مجازی موجود نیست"
    fi

    if [ -f "data/network.db" ]; then
        local dbsize="0"
        if command -v du >/dev/null 2>&1; then
            dbsize=$(du -k "data/network.db" | cut -f1)
        fi
        write_log_ok "Database" "Exists (network.db - ${dbsize} KB)" "پایگاه‌داده آماده است"
    else
        write_log_warn "Database" "Not initialized yet (auto-creates on first run)" "پایگاه‌داده در اولین اجرا ساخته می‌شود"
    fi

    if [ -f ".env" ]; then
        write_log_ok "Config File" "Exists (.env)" "فایل پیکربندی موجود است"
    else
        write_log_warn "Config File" "Missing (.env - optional)" "فایل پیکربندی ساخته نشده"
    fi

    if [ -d "data" ]; then
        write_log_ok "Data Dir" "Exists (data/)" "دایرکتوری داده موجود است"
    else
        write_log_warn "Data Dir" "Missing (data/)" "دایرکتوری داده موجود نیست"
    fi

    printf "  ${DARK_CYAN}────────────────────────────────────────────────────────────────────${NC}\n"
    printf "  ${WHITE}Service Status:${NC}\n"
    get_server_status || true

    printf "  ${DARK_GRAY}Auto-Start (systemd user): ${NC}"
    if [ -f "$SERVICE_FILE" ]; then
        printf "${GREEN}ENABLED${NC}\n\n"
    else
        printf "${DARK_GRAY}DISABLED${NC}\n\n"
    fi
}

start_server() {
    if [ ! -f ".venv/bin/python" ]; then
        write_log_warn "Server" "Virtual env missing. Installing..." "محیط مجازی یافت نشد..."
        install_dependencies
    fi
    ensure_env_files

    printf "\n  ${GREEN}┌── Simban Console ────────────────────────────────────────────────┐${NC}\n"
    printf "  ${CYAN}│ Panel URL: http://localhost:%-38s │${NC}\n" "$PORT"
    printf "  ${DARK_GRAY}│ Press Ctrl+C to stop all services                                │${NC}\n"
    printf "  ${GREEN}└──────────────────────────────────────────────────────────────────┘${NC}\n\n"

    open_browser_url "http://localhost:$PORT"

    write_log_info "Web" "Starting Uvicorn web server..." "در حال راه‌اندازی سرور وب Uvicorn..."
    if [ "$RELOAD" -eq 1 ]; then
        .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
    else
        .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
    fi
}

start_server_background() {
    if [ ! -f ".venv/bin/python" ]; then
        write_log_warn "Server" "Virtual env missing. Installing..." "محیط مجازی یافت نشد..."
        install_dependencies
    fi
    ensure_env_files

    get_active_process
    if [ -n "$WEB_PID" ]; then
        write_log_warn "Server" "Background service already running (PID $WEB_PID)." "سرویس پس‌زمینه قبلاً راه‌اندازی شده است."
        get_server_status || true
        open_browser_url "http://localhost:$PORT"
        return 0
    fi

    mkdir -p logs
    local log_out="$SCRIPT_DIR/logs/simban-bg.out.log"
    local log_err="$SCRIPT_DIR/logs/simban-bg.err.log"

    write_log_info "Server" "Launching Simban background service..." "در حال راه‌اندازی پس‌زمینه سرویس وب..."

    nohup "$SCRIPT_DIR/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" > "$log_out" 2> "$log_err" &
    local w_pid=$!
    echo "$w_pid" > "$WEB_PID_FILE"

    sleep 1
    if kill -0 "$w_pid" 2>/dev/null; then
        write_log_ok "Web" "Background service started (PID $w_pid)" "سرویس وب پس‌زمینه با موفقیت اجرا شد"
    else
        write_log_err "Web" "Failed to start background web service." "راه‌اندازی سرویس وب ناموفق بود."
    fi

    printf "  ${GREEN}Panel URL: http://localhost:%s${NC}\n" "$PORT"
    printf "  ${YELLOW}Note: You can safely close this terminal.${NC}\n"
    open_browser_url "http://localhost:$PORT"
}

stop_server() {
    write_log_info "Server" "Stopping Simban background services..." "در حال توقف سرویس پس‌زمینه..."
    local stopped=0

    get_active_process
    if [ -n "$WEB_PID" ]; then
        kill -9 "$WEB_PID" 2>/dev/null || true
        write_log_ok "Web" "Stopped background web service (PID $WEB_PID)" "سرویس وب پس‌زمینه متوقف شد"
        stopped=1
    fi
    rm -f "$WEB_PID_FILE" "$LEGACY_PID_FILE"

    # Kill leftover uvicorn app.main
    local leftover
    leftover=$(pgrep -f "app.main:app" || true)
    if [ -n "$leftover" ]; then
        for p in $leftover; do
            kill -9 "$p" 2>/dev/null || true
            stopped=1
        done
    fi

    # Free port
    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
    fi

    if [ "$stopped" -eq 0 ]; then
        printf "  ${YELLOW}[INFO] No active background services found | هیچ سرویس پس‌زمینه‌ای فعال نبود${NC}\n"
    fi
}

restart_server() {
    write_log_info "Server" "Restarting Simban background service..." "در حال راه‌اندازی مجدد سرویس پس‌زمینه سیم‌بان..."
    stop_server
    sleep 1
    start_server_background
}

enable_startup() {
    write_log_info "Startup" "Enabling systemd user auto-start..." "در حال تنظیم راه‌اندازی خودکار با systemd..."
    mkdir -p "$SYSTEMD_USER_DIR"
    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Simban Cisco Management Background Service
After=network.target

[Service]
Type=forking
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/start.sh start-bg $PORT --no-browser
ExecStop=$SCRIPT_DIR/start.sh stop
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user daemon-reload || true
        systemctl --user enable simban.service || true
        write_log_ok "Startup" "Auto-Start enabled successfully via systemd user." "راه‌اندازی خودکار با موفقیت فعال شد."
    else
        write_log_warn "Startup" "Service file written to $SERVICE_FILE. systemctl not found." "فایل سرویس ذخیره شد اما systemctl در دسترس نیست."
    fi
}

disable_startup() {
    if [ -f "$SERVICE_FILE" ]; then
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --user disable simban.service >/dev/null 2>&1 || true
        fi
        rm -f "$SERVICE_FILE"
        write_log_ok "Startup" "Auto-Start disabled." "راه‌اندازی خودکار غیرفعال شد."
    else
        printf "  ${YELLOW}[INFO] Auto-Start was not enabled | راه‌اندازی خودکار فعال نبود${NC}\n"
    fi
}

reset_data() {
    local force="$1"
    if [ "$force" != "force" ]; then
        printf "\n${RED}══════════════════════════════════════════════════════════════════════${NC}\n"
        printf "  ${RED}WARNING: FULL DATA RESET | هشدار: پاکسازی کامل داده‌ها${NC}\n"
        printf "${RED}══════════════════════════════════════════════════════════════════════${NC}\n"
        printf "  This action will permanently delete all network topology databases and logs.\n"
        printf "  | این عملیات پایگاه‌داده توپولوژی شبکه و لاگ‌ها را به طور کامل حذف می‌کند.\n\n"
        read -r -p "Are you sure you want to delete all data? [y/N] | آیا مطمئن هستید؟ " confirm
        case "$confirm" in
            [yY][eE][sS]|[yY]) ;;
            *)
                write_log_info "Reset" "Operation cancelled by user." "عملیات لغو شد."
                return 0
                ;;
        esac
    fi

    write_log_info "Reset" "Stopping background services first..." "در حال توقف سرویس‌ها..."
    stop_server >/dev/null 2>&1 || true
    write_log_info "Reset" "Wiping data directory..." "در حال حذف دایرکتوری داده..."
    rm -rf data logs
    mkdir -p data logs
    write_log_ok "Reset" "All data and database wiped successfully." "تمامی داده‌ها و دیتابیس با موفقیت پاکسازی شدند."
}

show_menu() {
    while true; do
        clear || true
        get_active_process
        local srv_txt="STOPPED"
        local srv_col="$DARK_GRAY"
        if [ -n "$WEB_PID" ]; then
            srv_txt="RUNNING"
            srv_col="$GREEN"
        fi

        local startup_status="DISABLED"
        local startup_col="$DARK_GRAY"
        if [ -f "$SERVICE_FILE" ]; then
            startup_status="ENABLED"
            startup_col="$GREEN"
        fi

        local exit_text="    [0] Exit"
        if [ "$IN_PARENT_SESSION" -eq 1 ]; then
            exit_text="    [0] Return to Suite"
        fi

        printf "  ${DARK_CYAN}┌──────────────────────────────────────────────────────────────────┐${NC}\n"
        printf "  ${DARK_CYAN}│ ${CYAN}SIMBAN SUITE${NC}${DARK_CYAN}      │ Cisco Switch & Topology Management      │${NC}\n"
        printf "  ${DARK_CYAN}├──────────────────────────────────────────────────────────────────┤${NC}\n"
        printf "  ${DARK_CYAN}│ ${srv_col}●${NC} Web Service (:%s): [%s]                                   ${DARK_CYAN}│${NC}\n" "$PORT" "$srv_txt"
        printf "  ${DARK_CYAN}├──────────────────────────────────────────────────────────────────┤${NC}\n"
        printf "  ${DARK_CYAN}│ ${DARK_GRAY}System Auto-Start: ${startup_col}%-46s${NC}${DARK_CYAN}│${NC}\n" "$startup_status"
        printf "  ${DARK_CYAN}└──────────────────────────────────────────────────────────────────┘${NC}\n\n"

        printf "  ${CYAN}Service Control:${NC}\n"
        printf "    [1] Start Foreground Console     [2] Start Background Service\n"
        printf "    [3] Stop Background Service      [r] Restart Background Service\n"
        printf "    [4] Check Service Status\n\n"

        printf "  ${CYAN}Maintenance & System:${NC}\n"
        printf "    [7] Install Dependencies         [8] Update Packages\n"
        printf "    [9] System Health Check          [10] Reset All Data & DB\n\n"

        local st_opt="[5] Enable Auto-Start"
        if [ -f "$SERVICE_FILE" ]; then
            st_opt="[6] Disable Auto-Start"
        fi

        printf "  ${DARK_GRAY}General:${NC}\n"
        printf "    %s      [f] Refresh Status      %s\n" "$st_opt" "$exit_text"
        printf "  ${DARK_CYAN}────────────────────────────────────────────────────────────────────${NC}\n"

        read -r -p "  Choice: " choice
        case "$choice" in
            1) start_server; break ;;
            2)
                start_server_background
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            3)
                stop_server
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            r|R)
                restart_server
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            4)
                printf "\n=== وضعیت سرویس‌ها (Service Status) ===\n"
                get_server_status || true
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            5)
                enable_startup
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            6)
                disable_startup
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            7)
                install_dependencies
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            8)
                update_dependencies
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            9)
                test_health_check
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            10)
                reset_data
                read -r -p $'\nPress Enter to return | جهت بازگشت کلید Enter را بزنید...' _
                ;;
            f|F)
                ;;
            0)
                if [ "$IN_PARENT_SESSION" -eq 1 ]; then
                    printf "${GREEN}Returning to Boomban Suite... | در حال بازگشت به بوم‌بان...${NC}\n"
                else
                    printf "${GREEN}Goodbye! | خداحافظ!${NC}\n"
                fi
                return 0
                ;;
            *)
                printf "  ${RED}Invalid choice | گزینه نامعتبر است.${NC}\n"
                sleep 1
                ;;
        esac
    done
}

case "${ACTION,,}" in
    start)           start_server ;;
    start-bg)        start_server_background ;;
    stop)            stop_server ;;
    restart)         restart_server ;;
    status)
        if get_server_status; then exit 0; else exit 1; fi
        ;;
    enable-startup)  enable_startup ;;
    disable-startup) disable_startup ;;
    install)         install_dependencies ;;
    update)          update_dependencies ;;
    check)           test_health_check ;;
    reset-data|clean) reset_data ;;
    help)
        printf "Simban Help:\n"
        printf "  ./start.sh                           Interactive TUI Menu\n"
        printf "  ./start.sh start [PORT]              Start Foreground\n"
        printf "  ./start.sh start-bg [PORT]           Start Background Service\n"
        printf "  ./start.sh stop                      Stop Background Service\n"
        printf "  ./start.sh restart                   Restart Background Service\n"
        printf "  ./start.sh status                    Check Background Status\n"
        printf "  ./start.sh enable-startup            Enable Auto-Start (systemd)\n"
        printf "  ./start.sh disable-startup           Disable Auto-Start\n"
        printf "  ./start.sh install                   Install Dependencies\n"
        printf "  ./start.sh update                    Update Packages\n"
        printf "  ./start.sh check                     System Health Check\n"
        printf "  ./start.sh reset-data                Reset All Data & Database\n"
        ;;
    *)
        show_menu
        ;;
esac
