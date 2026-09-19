#!/usr/bin/env bash
# ==============================================================================
# Simban - Native TUI Manager (Linux & macOS)
# سامانه مدیریت و پایش سوییچ‌های سیسکو - اکوسیستم بوم‌بان
# ==============================================================================

set -e

# مسیر اجرای اسکریپت
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# خواندن PORT از فایل .env در صورت وجود
if [ -f ".env" ]; then
    ENV_PORT=$(grep -E '^\s*PORT\s*=' .env | cut -d '=' -f2 | tr -d ' "\r\n' || echo "")
fi

PORT="${PORT:-${ENV_PORT:-23458}}"
NO_BROWSER=0

# مسیرهای PID و فایل استارت‌آپ خودکار
WEB_PID_FILE="$SCRIPT_DIR/data/simban_web.pid"
LEGACY_PID_FILE="$SCRIPT_DIR/data/ciscotopology_web.pid"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/simban.desktop"

# رنگ‌بندی ترمینال
BOLD='\033[1m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# پارس کردن آرگومان‌ها
ACTION=""
for arg in "$@"; do
    case "$arg" in
        --no-browser)
            NO_BROWSER=1
            ;;
        --port=*)
            PORT="${arg#*=}"
            ;;
        *)
            if [ -z "$ACTION" ]; then
                ACTION="$arg"
            elif [[ "$arg" =~ ^[0-9]+$ ]]; then
                PORT="$arg"
            fi
            ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────────────
# توابع چاپ دو زبانه و شکیل
# ──────────────────────────────────────────────────────────────────────────────

log_info() {
    local label="$1" en="$2" fa="$3"
    echo -e "  [${CYAN}${label}${NC}] ${WHITE}${en}${NC} | ${GRAY}${fa}${NC}"
}

log_ok() {
    local label="$1" en="$2" fa="$3"
    echo -e "  [${GREEN}OK${NC}] ${WHITE}${label}:${NC} ${WHITE}${en}${NC} | ${GRAY}${fa}${NC}"
}

log_warn() {
    local label="$1" en="$2" fa="$3"
    echo -e "  [${YELLOW}WARN${NC}] ${WHITE}${label}:${NC} ${WHITE}${en}${NC} | ${GRAY}${fa}${NC}"
}

log_err() {
    local label="$1" en="$2" fa="$3"
    echo -e "  [${RED}ERROR${NC}] ${WHITE}${label}:${NC} ${WHITE}${en}${NC} | ${GRAY}${fa}${NC}"
}

open_browser_url() {
    local url="$1"
    if [ "$NO_BROWSER" -eq 0 ]; then
        log_info "Browser" "Opening browser at $url..." "در حال باز کردن مرورگر..."
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$url" >/dev/null 2>&1 &
        elif command -v open >/dev/null 2>&1; then
            open "$url" >/dev/null 2>&1 &
        else
            log_warn "Browser" "Failed to open browser automatically." "خطا در باز کردن خودکار مرورگر."
        fi
    fi
}

ensure_uv() {
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$HOME/.astral/bin:$PATH"
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi

    log_warn "Astral uv" "Astral uv tool not found. Installing..." "ابزار uv یافت نشد. در حال نصب..."
    
    if command -v curl >/dev/null 2>&1 && curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; then
        export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$HOME/.astral/bin:$PATH"
    elif command -v python3 >/dev/null 2>&1 && python3 -m pip install --quiet uv >/dev/null 2>&1; then
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if command -v uv >/dev/null 2>&1; then
        log_ok "Astral uv" "Installed successfully." "با موفقیت نصب شد."
        return 0
    else
        log_warn "Astral uv" "Installation failed. Falling back to pip." "نصب uv ناموفق بود؛ استفاده از pip."
        return 1
    fi
}

ensure_venv() {
    ensure_uv || true
    if [ ! -f ".venv/bin/python" ]; then
        log_info "SETUP" "Creating virtual environment (.venv)..." "در حال ساخت محیط مجازی (.venv)..."
        if command -v uv >/dev/null 2>&1; then
            uv venv .venv >/dev/null 2>&1
        else
            python3 -m venv .venv
        fi
        if [ ! -f ".venv/bin/python" ]; then
            log_err "VENV" "Failed to create virtual environment." "ساخت محیط مجازی با خطا مواجه شد."
            return 1
        fi
        log_ok "VENV" "Virtual environment created." "محیط مجازی ساخته شد."
    fi
    return 0
}

ensure_env_files() {
    mkdir -p data
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            log_warn ".env" "Created from .env.example. Please review." "فایل .env از نمونه ساخته شد."
        fi
    fi
}

install_deps() {
    ensure_venv || return 1
    log_info "PACKAGES" "Installing dependencies..." "در حال نصب وابستگی‌ها..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install -r requirements.txt --python .venv/bin/python
    else
        .venv/bin/python -m pip install --quiet --upgrade pip
        .venv/bin/python -m pip install --quiet -r requirements.txt
    fi
    ensure_env_files
    log_ok "PACKAGES" "All dependencies installed successfully." "تمامی وابستگی‌ها نصب شدند."
}

update_deps() {
    ensure_venv || return 1
    log_info "PACKAGES" "Updating packages..." "در حال بروزرسانی بسته‌ها..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --upgrade -r requirements.txt --python .venv/bin/python
    else
        .venv/bin/python -m pip install --quiet --upgrade -r requirements.txt
    fi
    log_ok "PACKAGES" "All packages updated successfully." "تمامی بسته‌ها بروزرسانی شدند."
}

# بررسی پروسه‌های فعال سرور وب
get_active_processes() {
    WEB_PID=""

    if [ -f "$WEB_PID_FILE" ]; then
        local pid
        pid=$(cat "$WEB_PID_FILE" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            WEB_PID="$pid"
        fi
    fi
    if [ -z "$WEB_PID" ] && [ -f "$LEGACY_PID_FILE" ]; then
        local pid
        pid=$(cat "$LEGACY_PID_FILE" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            WEB_PID="$pid"
        fi
    fi
    if [ -z "$WEB_PID" ]; then
        WEB_PID=$(pgrep -f "app.main:app" | head -n 1 || echo "")
    fi
}

get_server_status() {
    get_active_processes

    if [ -n "$WEB_PID" ]; then
        echo -e "  [${GREEN}OK${NC}] ${WHITE}Web Service:${NC} ${GREEN}ACTIVE (PID: ${WEB_PID})${NC} | ${GRAY}سرویس وب فعال است${NC}"
        echo -e "       ${WHITE}Panel URL:${NC} ${CYAN}http://localhost:${PORT}${NC}"
        return 0
    else
        echo -e "  [${YELLOW}INFO${NC}] ${WHITE}Web Service:${NC} ${YELLOW}INACTIVE${NC} | ${GRAY}سرویس وب فعال نیست${NC}"
        return 1
    fi
}

health_check() {
    echo -e "\n${CYAN}══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "  ${CYAN}System Health Check | پایش سلامت سیستم سیم‌بان (Simban)${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════════════════════════${NC}"

    # Python
    if command -v python3 >/dev/null 2>&1; then
        PY_VER=$(python3 --version 2>&1)
        log_ok "Python" "$PY_VER" "پایتون آماده است"
    else
        log_err "Python" "Not Installed!" "پایتون نصب نیست!"
    fi

    # uv
    if command -v uv >/dev/null 2>&1; then
        UV_VER=$(uv --version 2>&1)
        log_ok "Astral uv" "$UV_VER" "ابزار uv آماده است"
    else
        log_warn "Astral uv" "Not found (using pip)" "ابزار uv یافت نشد"
    fi

    # .venv
    if [ -f ".venv/bin/python" ]; then
        log_ok "Virtual Env" "Ready (.venv)" "محیط مجازی آماده است"
    else
        log_err "Virtual Env" "Missing (.venv)" "محیط مجازی موجود نیست"
    fi

    # Database
    if [ -f "data/network.db" ]; then
        log_ok "Database" "Exists (data/network.db)" "پایگاه‌داده آماده است"
    else
        log_warn "Database" "Not initialized yet (auto-creates on first run)" "پایگاه‌داده در اولین اجرا ساخته می‌شود"
    fi

    # .env
    if [ -f ".env" ]; then
        log_ok "Config File" "Exists (.env)" "فایل پیکربندی موجود است"
    else
        log_warn "Config File" "Missing (.env)" "فایل پیکربندی ساخته نشده"
    fi

    # data/
    if [ -d "data" ]; then
        log_ok "Data Dir" "Exists (data/)" "دایرکتوری داده موجود است"
    else
        log_warn "Data Dir" "Missing (data/)" "دایرکتوری داده موجود نیست"
    fi

    echo -e "${CYAN}──────────────────────────────────────────────────────────────────────${NC}"
    echo -e "  ${WHITE}Service & System Status | وضعیت سرویس‌ها:${NC}"
    get_server_status || true

    echo -n "  Linux Auto-Start: "
    if [ -f "$AUTOSTART_FILE" ]; then
        echo -e "${GREEN}ENABLED | فعال است${NC}"
    else
        echo -e "${YELLOW}DISABLED | غیرفعال است${NC}"
    fi
    echo -e "${CYAN}══════════════════════════════════════════════════════════════════════${NC}\n"
    return 0
}

start_server() {
    if [ ! -f ".venv/bin/python" ]; then
        log_warn "Server" "Virtual env missing. Installing..." "محیط مجازی یافت نشد..."
        install_deps
    fi
    ensure_env_files

    echo -e "\n${GREEN}══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}Simban Server Running (FastAPI & Cisco Collector Active)${NC}"
    echo -e "  ${CYAN}Panel URL: http://localhost:${PORT}${NC}"
    echo -e "  ${YELLOW}Press Ctrl+C to Stop Server${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════════════${NC}\n"

    open_browser_url "http://localhost:${PORT}"

    log_info "Web" "Starting Uvicorn web server..." "در حال راه‌اندازی سرور وب Uvicorn..."
    .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
    return 0
}

start_server_background() {
    if [ ! -f ".venv/bin/python" ]; then
        log_warn "Server" "Virtual env missing. Installing..." "محیط مجازی یافت نشد..."
        install_deps
    fi
    ensure_env_files

    get_active_processes
    if [ -n "$WEB_PID" ]; then
        log_warn "Server" "Background service already running (PID $WEB_PID)." "سرویس پس‌زمینه قبلاً راه‌اندازی شده است."
        get_server_status || true
        open_browser_url "http://localhost:${PORT}"
        return 0
    fi

    log_info "Server" "Launching Simban background service..." "در حال راه‌اندازی پس‌زمینه سرویس وب..."

    nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" > data/simban_web.log 2>&1 &
    WEB_PID=$!

    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        echo "$WEB_PID" > "$WEB_PID_FILE"
        log_ok "Web" "Background web service started (PID $WEB_PID)" "سرویس وب پس‌زمینه با موفقیت اجرا شد"
    else
        log_err "Web" "Failed to start background web service." "راه‌اندازی سرویس وب ناموفق بود."
    fi

    echo -e "  ${GREEN}Panel URL: http://localhost:${PORT}${NC}"
    echo -e "  ${YELLOW}Note: You can safely close this terminal.${NC}"
    open_browser_url "http://localhost:${PORT}"
    return 0
}

stop_server() {
    log_info "Server" "Stopping Simban background service..." "در حال توقف سرویس پس‌زمینه..."
    local stopped=0

    if [ -f "$WEB_PID_FILE" ]; then
        local pid
        pid=$(cat "$WEB_PID_FILE" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
            log_ok "Web" "Stopped background web service (PID $pid)" "سرویس وب پس‌زمینه متوقف شد"
            stopped=1
        fi
        rm -f "$WEB_PID_FILE"
    fi

    if [ -f "$LEGACY_PID_FILE" ]; then
        local pid
        pid=$(cat "$LEGACY_PID_FILE" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
            stopped=1
        fi
        rm -f "$LEGACY_PID_FILE"
    fi

    local web_pids
    web_pids=$(pgrep -f "app.main:app" || echo "")
    if [ -n "$web_pids" ]; then
        for p in $web_pids; do
            kill "$p" 2>/dev/null || kill -9 "$p" 2>/dev/null || true
            log_ok "Web" "Terminated leftover Simban process (PID $p)" "پروسه وب متوقف شد"
            stopped=1
        done
    fi

    if [ "$stopped" -eq 0 ]; then
        echo -e "  ${YELLOW}[INFO] No active background services found | هیچ سرویس پسزمینه‌ای فعال نبود${NC}"
    fi
    return 0
}

enable_startup() {
    log_info "Startup" "Enabling Linux Auto-Start..." "در حال تنظیم راه‌اندازی خودکار..."
    mkdir -p "$AUTOSTART_DIR"
    cat <<EOF > "$AUTOSTART_FILE"
[Desktop Entry]
Type=Application
Name=Simban Service
Comment=Simban Auto-Start Background Service
Exec=bash -c "cd '$SCRIPT_DIR' && ./start.sh start-bg --no-browser"
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
    chmod +x "$AUTOSTART_FILE"
    log_ok "Startup" "Auto-Start enabled successfully." "راه‌اندازی خودکار فعال شد."
}

disable_startup() {
    if [ -f "$AUTOSTART_FILE" ]; then
        rm -f "$AUTOSTART_FILE"
        log_ok "Startup" "Auto-Start disabled." "راه‌اندازی خودکار غیرفعال شد."
    else
        echo -e "  ${YELLOW}[INFO] Auto-Start was not enabled | راه‌اندازی خودکار فعال نبود${NC}"
    fi
}

reset_data() {
    local force_flag=0
    if [ "$1" = "-f" ] || [ "$1" = "--force" ]; then
        force_flag=1
    fi

    if [ "$force_flag" -eq 0 ]; then
        echo -e "\n${RED}══════════════════════════════════════════════════════════════════════${NC}"
        echo -e "  ${RED}WARNING: FULL DATA RESET | هشدار: پاکسازی کامل داده‌ها${NC}"
        echo -e "${RED}══════════════════════════════════════════════════════════════════════${NC}"
        echo -e "  ${WHITE}This action will permanently delete all network topology databases and logs.${NC}"
        echo -e "  ${GRAY}این عملیات پایگاه‌داده توپولوژی شبکه و لاگ‌ها را به طور کامل حذف می‌کند.${NC}\n"
        read -rp "Are you sure you want to delete all data? [y/N] | آیا مطمئن هستید؟ " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Reset" "Operation cancelled by user." "عملیات لغو شد."
            return 0
        fi
    fi

    log_info "Reset" "Stopping background services first..." "در حال توقف سرویس‌ها..."
    stop_server >/dev/null 2>&1 || true

    log_info "Reset" "Wiping data directory..." "در حال حذف دایرکتوری داده..."
    rm -rf data
    mkdir -p data

    log_ok "Reset" "All data and database wiped successfully." "تمامی داده‌ها و دیتابیس با موفقیت پاکسازی شدند."
    return 0
}

show_menu() {
    while true; do
        clear 2>/dev/null || true
        get_active_processes
        local bg_status=" [INACTIVE]"
        if [ -n "$WEB_PID" ]; then
            bg_status=" [ACTIVE]"
        fi

        local startup_status=" [DISABLED]"
        if [ -f "$AUTOSTART_FILE" ]; then
            startup_status=" [ENABLED]"
        fi

        echo -e "${CYAN}══════════════════════════════════════════════════════════════════════${NC}"
        echo -e "               ${CYAN}Simban Native Manager (TUI)${NC}"
        echo -e "        ${GRAY}مدیریت بومی و استقرار سامانه سیم‌بان | System Management${NC}"
        echo -e "${CYAN}══════════════════════════════════════════════════════════════════════${NC}"
        echo -e "  ${WHITE}[1] Start Foreground Console    | اجرای مستقیم در کنسول${NC}"
        
        echo -n -e "  ${WHITE}[2] Start Background Service   | اجرای سرویس پسزمینه${NC}"
        if [ -n "$WEB_PID" ]; then
            echo -e "${GREEN}${bg_status}${NC}"
        else
            echo -e "${GRAY}${bg_status}${NC}"
        fi

        echo -e "  ${WHITE}[3] Stop Background Service    | توقف سرویس پسزمینه${NC}"
        echo -e "  ${WHITE}[4] Check Service Status       | مشاهده وضعیت سرویس${NC}"
        
        echo -n -e "  ${WHITE}[5] Enable Linux Startup       | فعالسازی اجرا خودکار${NC}"
        if [ -f "$AUTOSTART_FILE" ]; then
            echo -e "${GREEN}${startup_status}${NC}"
        else
            echo -e "${GRAY}${startup_status}${NC}"
        fi

        echo -e "  ${WHITE}[6] Disable Linux Startup      | غیرفعالسازی اجرا خودکار${NC}"
        echo -e "  ${WHITE}[7] Full Setup and Install     | نصب و پیکربندی اولیه${NC}"
        echo -e "  ${WHITE}[8] Update Packages            | بهروزرسانی بستهها${NC}"
        echo -e "  ${WHITE}[9] System Health Check        | بررسی سلامت سیستم${NC}"
        echo -e "  ${RED}[10] Reset All Data & DB       | پاکسازی و بازنشانی کامل داده‌ها${NC}"
        echo -e "  ${WHITE}[0] Exit                       | خروج${NC}"
        echo -e "${CYAN}══════════════════════════════════════════════════════════════════════${NC}"
        
        read -rp "Select Option [0-10] | انتخاب گزینه: " choice

        case "$choice" in
            1)
                start_server
                break
                ;;
            2)
                start_server_background
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            3)
                stop_server
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            4)
                echo -e "\n${CYAN}=== وضعیت سرویس‌ها (Service Status) ===${NC}"
                get_server_status || true
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            5)
                enable_startup
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            6)
                disable_startup
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            7)
                install_deps
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            8)
                update_deps
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            9)
                health_check
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            10)
                reset_data
                read -rp "Press Enter to return | جهت بازگشت کلید Enter را بزنید..."
                ;;
            0)
                echo -e "${GREEN}Goodbye! | خداحافظ!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid choice | گزینه نامعتبر است.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ──────────────────────────────────────────────────────────────────────────────
# ورودی خط فرمان (Non-interactive mode)
# ──────────────────────────────────────────────────────────────────────────────
case "$ACTION" in
    start|1)
        start_server
        ;;
    start-bg|2)
        start_server_background
        ;;
    stop|3)
        stop_server
        ;;
    status|4)
        if get_server_status; then
            exit 0
        else
            exit 1
        fi
        ;;
    enable-startup|5)
        enable_startup
        ;;
    disable-startup|6)
        disable_startup
        ;;
    install|7)
        install_deps
        ;;
    update|8)
        update_deps
        ;;
    check|9)
        health_check
        ;;
    reset-data|clean|10)
        reset_data "$2"
        ;;
    help|--help|-h)
        echo "Simban Help:"
        echo "  ./start.sh                           Interactive TUI Menu"
        echo "  ./start.sh start [PORT]              Start Foreground (Default: 23458)"
        echo "  ./start.sh start-bg                  Start Background Service"
        echo "  ./start.sh stop                      Stop Background Service"
        echo "  ./start.sh status                    Check Background Status (Exit Code 0=Active, 1=Inactive)"
        echo "  ./start.sh enable-startup            Enable Auto-Start"
        echo "  ./start.sh disable-startup           Disable Auto-Start"
        echo "  ./start.sh install                   Install Dependencies (uv / pip)"
        echo "  ./start.sh update                    Update Packages"
        echo "  ./start.sh check                     System Health Check"
        echo "  ./start.sh reset-data                Reset All Data & Database"
        ;;
    "")
        show_menu
        ;;
    *)
        show_menu
        ;;
esac
