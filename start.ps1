#Requires -Version 5.1
<#
.SYNOPSIS
    Simban Native Manager (PowerShell TUI - Clean and Dual Language)
.DESCRIPTION
    Interactive TUI launcher and environment manager for Simban (Cisco Switch Management) using Astral uv.
    Supports Persian and English dual-language output with clean layout alignment.
.EXAMPLE
    .\start.ps1
.EXAMPLE
    .\start.ps1 -Action start -Port 23458
#>

[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet("start", "start-bg", "stop", "restart", "status", "enable-startup", "disable-startup", "install", "update", "check", "reset-data", "clean", "help", "")]
    [string]$Action = "",

    [Parameter(Position=1)]
    [int]$Port = 23458,

    [switch]$NoBrowser,
    [switch]$Reload,
    [switch]$InParentSession
)

# تنظیم انکودینگ خروجی ترمینال به UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# بارگذاری متغیر PORT از .env در صورت عدم تغییر دستی
if ($PSBoundParameters.ContainsKey('Port') -eq $false -and (Test-Path ".env")) {
    $envLines = Get-Content ".env" -ErrorAction SilentlyContinue
    foreach ($line in $envLines) {
        if ($line -match '^\s*PORT\s*=\s*(\d+)') {
            $Port = [int]$matches[1]
            break
        }
    }
}

# مسیرهای ذخیره PID و استارت‌آپ ویندوز
$WebPidFile = Join-Path $ScriptDir "data\simban_web.pid"
$LegacyWebPidFile = Join-Path $ScriptDir "data\ciscotopology_web.pid"
$StartupFolder = [Environment]::GetFolderPath("Startup")
$StartupShortcut = Join-Path $StartupFolder "Simban.lnk"

# توابع چاپ دو زبانه و شکیل با همترازی تمیز
function Write-LogInfo ($label, $en, $fa) {
    Write-Host "  ● " -NoNewline -ForegroundColor Cyan
    Write-Host "[$label] " -NoNewline -ForegroundColor DarkCyan
    Write-Host "$en " -NoNewline -ForegroundColor White
    if ($fa) { Write-Host "│ $fa" -ForegroundColor DarkGray } else { Write-Host "" }
}

function Write-LogOk ($label, $en, $fa) {
    Write-Host "  ● " -NoNewline -ForegroundColor Green
    Write-Host "[$label] " -NoNewline -ForegroundColor DarkCyan
    Write-Host "$en " -NoNewline -ForegroundColor White
    if ($fa) { Write-Host "│ $fa" -ForegroundColor DarkGray } else { Write-Host "" }
}

function Write-LogWarn ($label, $en, $fa) {
    Write-Host "  ● " -NoNewline -ForegroundColor Yellow
    Write-Host "[WARN: $label] " -NoNewline -ForegroundColor Yellow
    Write-Host "$en " -NoNewline -ForegroundColor White
    if ($fa) { Write-Host "│ $fa" -ForegroundColor DarkGray } else { Write-Host "" }
}

function Write-LogErr ($label, $en, $fa) {
    Write-Host "  ● " -NoNewline -ForegroundColor Red
    Write-Host "[ERROR: $label] " -NoNewline -ForegroundColor Red
    Write-Host "$en " -NoNewline -ForegroundColor White
    if ($fa) { Write-Host "│ $fa" -ForegroundColor DarkGray } else { Write-Host "" }
}

# باز کردن خودکار مرورگر در صورت عدم غیرفعال بودن
function Open-BrowserUrl ($url) {
    if (-not $NoBrowser) {
        Write-LogInfo "Browser" "Opening browser at $url..." "در حال باز کردن مرورگر..."
        try {
            Start-Process $url
        } catch {
            Write-LogWarn "Browser" "Failed to open browser automatically." "خطا در باز کردن خودکار مرورگر."
        }
    }
}

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return $true
    }
    Write-LogWarn "Astral uv" "Astral uv tool not found. Installing..." "ابزار uv یافت نشد. در حال نصب..."
    try {
        python -m pip install -q uv 2>$null
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-LogOk "Astral uv" "Installed successfully." "با موفقیت نصب شد."
            return $true
        }
    } catch { }
    Write-LogWarn "Astral uv" "Installation failed. Falling back to pip." "نصب uv ناموفق بود؛ استفاده از pip."
    return $false
}

function Ensure-Venv {
    $hasUv = Ensure-Uv
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-LogInfo "SETUP" "Creating virtual environment (.venv)..." "در حال ساخت محیط مجازی (.venv)..."
        if ($hasUv) {
            uv venv .venv
        } else {
            python -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) {
            Write-LogErr "VENV" "Failed to create virtual environment." "ساخت محیط مجازی با خطا مواجه شد."
            return $false
        }
        Write-LogOk "VENV" "Virtual environment created." "محیط مجازی ساخته شد."
    }
    return $true
}

function Ensure-EnvFiles {
    if (-not (Test-Path "data")) {
        New-Item -ItemType Directory -Path "data" -Force | Out-Null
    }
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-LogWarn ".env" "Created from .env.example. Please review." "فایل .env از نمونه ساخته شد."
        }
    }
}

function Install-Dependencies {
    $venvOk = Ensure-Venv
    if (-not $venvOk) { return }
    Write-LogInfo "PACKAGES" "Installing dependencies..." "در حال نصب وابستگی‌ها..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv pip install -r requirements.txt --python .venv\Scripts\python.exe
    } else {
        & .venv\Scripts\python.exe -m pip install -q --upgrade pip
        & .venv\Scripts\python.exe -m pip install -q -r requirements.txt
    }
    Ensure-EnvFiles
    Write-LogOk "PACKAGES" "All dependencies installed successfully." "تمامی وابستگی‌ها نصب شدند."
}

function Update-Dependencies {
    $venvOk = Ensure-Venv
    if (-not $venvOk) { return }
    Write-LogInfo "PACKAGES" "Updating packages..." "در حال بروزرسانی بسته‌ها..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv pip install --upgrade -r requirements.txt --python .venv\Scripts\python.exe
    } else {
        & .venv\Scripts\python.exe -m pip install -q --upgrade -r requirements.txt
    }
    Write-LogOk "PACKAGES" "All packages updated successfully." "تمامی بسته‌ها بروزرسانی شدند."
}

# بررسی پروسه فعال سرور وب
function Get-ActiveServerProcess {
    $webProc = $null

    if (Test-Path $WebPidFile) {
        $savedPid = Get-Content $WebPidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            $webProc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        }
    }
    if (-not $webProc -and (Test-Path $LegacyWebPidFile)) {
        $savedPid = Get-Content $LegacyWebPidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            $webProc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        }
    }

    # اگر در فایل نبود، بررسی بر اساس نام و خط فرمان
    if (-not $webProc) {
        $pyProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue
        if ($pyProcs) {
            foreach ($p in $pyProcs) {
                try {
                    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($p.Id)").CommandLine
                    if ($cmdLine -like "*app.main:app*" -or $cmdLine -like "*uvicorn*app.main*") {
                        $webProc = $p
                        break
                    }
                } catch {}
            }
        }
    }

    return $webProc
}

function Get-ServerStatus {
    $webProc = Get-ActiveServerProcess

    $hasActive = $false
    $srvTxt = if ($webProc) { "RUNNING (PID: $($webProc.Id))" } else { "STOPPED" }
    $srvCol = if ($webProc) { "Green" } else { "DarkGray" }

    Write-Host "  ● " -NoNewline -ForegroundColor $srvCol
    Write-Host "Web Service: " -NoNewline -ForegroundColor White
    Write-Host "$srvTxt" -ForegroundColor $srvCol

    if ($webProc) {
        Write-Host "  → URL: " -NoNewline -ForegroundColor DarkGray
        Write-Host "http://localhost:$Port" -ForegroundColor Cyan
        $hasActive = $true
    }

    return $hasActive
}

function Test-HealthCheck {
    Write-Host "`n  ┌── System Health Check ───────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host "  │ Simban Cisco Switch Management Verification                      │" -ForegroundColor Cyan
    Write-Host "  └──────────────────────────────────────────────────────────────────┘" -ForegroundColor Cyan
    
    # Python
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        $pyVer = (python --version 2>&1) | Out-String
        $pyVer = $pyVer.Trim()
        Write-LogOk "Python" "$pyVer" "پایتون آماده است"
    } else {
        Write-LogErr "Python" "Not Installed!" "پایتون نصب نیست!"
    }

    # uv
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        $uvVer = (uv --version 2>&1) | Out-String
        $uvVer = $uvVer.Trim()
        Write-LogOk "Astral uv" "$uvVer" "ابزار uv آماده است"
    } else {
        Write-LogWarn "Astral uv" "Not found (using pip)" "ابزار uv یافت نشد"
    }

    # .venv
    if (Test-Path ".venv\Scripts\python.exe") {
        Write-LogOk "Virtual Env" "Ready (.venv)" "محیط مجازی آماده است"
    } else {
        Write-LogErr "Virtual Env" "Missing (.venv)" "محیط مجازی موجود نیست"
    }

    # Database
    if (Test-Path "data\network.db") {
        $dbSize = [math]::Round(((Get-Item "data\network.db").Length / 1KB), 1)
        Write-LogOk "Database" "Exists (network.db - $dbSize KB)" "پایگاه‌داده آماده است"
    } else {
        Write-LogWarn "Database" "Not initialized yet (auto-creates on first run)" "پایگاه‌داده در اولین اجرا ساخته می‌شود"
    }

    # .env
    if (Test-Path ".env") {
        Write-LogOk "Config File" "Exists (.env)" "فایل پیکربندی موجود است"
    } else {
        Write-LogWarn "Config File" "Missing (.env - optional)" "فایل پیکربندی ساخته نشده"
    }

    # data/
    if (Test-Path "data") {
        Write-LogOk "Data Dir" "Exists (data/)" "دایرکتوری داده موجود است"
    } else {
        Write-LogWarn "Data Dir" "Missing (data/)" "دایرکتوری داده موجود نیست"
    }

    Write-Host "  ────────────────────────────────────────────────────────────────────" -ForegroundColor DarkCyan
    Write-Host '  Service Status:' -ForegroundColor White
    Get-ServerStatus | Out-Null

    Write-Host "  Windows Auto-Start: " -NoNewline -ForegroundColor DarkGray
    if (Test-Path $StartupShortcut) {
        Write-Host "ENABLED" -ForegroundColor Green
    } else {
        Write-Host "DISABLED" -ForegroundColor DarkGray
    }
    Write-Host ""
}

# راه‌اندازی سرویس وب به صورت Foreground (با پنجره کنسول)
function Start-Server {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-LogWarn "Server" "Virtual env missing. Installing..." "محیط مجازی یافت نشد..."
        Install-Dependencies
    }
    Ensure-EnvFiles

    Write-Host "`n  ┌── Simban Console ────────────────────────────────────────────────┐" -ForegroundColor Green
    Write-Host "  │ Panel URL: http://localhost:$Port                                  │" -ForegroundColor Cyan
    Write-Host "  │ Press Ctrl+C to stop all services                                │" -ForegroundColor DarkGray
    Write-Host "  └──────────────────────────────────────────────────────────────────┘`n" -ForegroundColor Green

    Open-BrowserUrl "http://localhost:$Port"

    Write-LogInfo "Web" "Starting Uvicorn web server..." "در حال راه‌اندازی سرور وب Uvicorn..."
    if ($Reload) {
        & .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $Port --reload
    } else {
        & .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $Port
    }
}

# راه‌اندازی سرویس وب به صورت پس‌زمینه (Background)
function Start-ServerBackground {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-LogWarn "Server" "Virtual env missing. Installing..." "محیط مجازی یافت نشد..."
        Install-Dependencies
    }
    Ensure-EnvFiles

    $webProc = Get-ActiveServerProcess
    if ($webProc) {
        Write-LogWarn "Server" "Background service already running (PID $($webProc.Id))." "سرویس پس‌زمینه قبلاً راه‌اندازی شده است."
        Get-ServerStatus | Out-Null
        Open-BrowserUrl "http://localhost:$Port"
        return
    }

    if (-not (Test-Path "logs")) {
        New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    }
    $logOut = Join-Path $ScriptDir "logs\simban-bg.out.log"
    $logErr = Join-Path $ScriptDir "logs\simban-bg.err.log"

    $pythonPath = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    Write-LogInfo "Server" "Launching Simban background service..." "در حال راه‌اندازی پس‌زمینه سرویس وب..."
    
    $argList = "-m uvicorn app.main:app --host 0.0.0.0 --port $Port"
    $webProc = Start-Process -FilePath $pythonPath -ArgumentList $argList -WorkingDirectory $ScriptDir -WindowStyle Hidden -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru

    if ($webProc -and -not $webProc.HasExited) {
        $webProc.Id | Out-File -FilePath $WebPidFile -Encoding utf8
        Write-LogOk "Web" "Background service started (PID $($webProc.Id))" "سرویس وب پس‌زمینه با موفقیت اجرا شد"
    } else {
        Write-LogErr "Web" "Failed to start background web service." "راه‌اندازی سرویس وب ناموفق بود."
    }

    Write-Host "  Panel URL: http://localhost:$Port" -ForegroundColor Green
    Write-Host "  Note: You can safely close this terminal." -ForegroundColor Yellow
    Open-BrowserUrl "http://localhost:$Port"
}

function Restart-Server {
    Write-LogInfo "Server" "Restarting Simban background service..." "در حال راه‌اندازی مجدد سرویس پس‌زمینه سیم‌بان..."
    Stop-Server
    Start-Sleep -Seconds 1
    Start-ServerBackground
}

# توقف سرویس پس‌زمینه
function Stop-Server {
    Write-LogInfo "Server" "Stopping Simban background services..." "در حال توقف سرویس پس‌زمینه..."
    $stopped = $false

    if (Test-Path $WebPidFile) {
        $savedPid = Get-Content $WebPidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
                Write-LogOk "Web" "Stopped background web service (PID $savedPid)" "سرویس وب پس‌زمینه متوقف شد"
                $stopped = $true
            }
        }
        Remove-Item $WebPidFile -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path $LegacyWebPidFile) {
        $savedPid = Get-Content $LegacyWebPidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
                $stopped = $true
            }
        }
        Remove-Item $LegacyWebPidFile -Force -ErrorAction SilentlyContinue
    }

    # اطمینان نهایی: بررسی و توقف پردازنده متصل به پورت در صورت باقی ماندن
    try {
        $net = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($net) {
            foreach ($conn in $net) {
                if ($conn.OwningProcess) {
                    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
                    Write-LogOk "Web" "Freed port $Port (PID $($conn.OwningProcess))" "پورت $Port آزاد شد"
                    $stopped = $true
                }
            }
        }
    } catch {}

    if (-not $stopped) {
        Write-Host "  [INFO] No active background services found | هیچ سرویس پسزمینه‌ای فعال نبود" -ForegroundColor Yellow
    }
}

function Enable-Startup {
    Write-LogInfo "Startup" "Enabling Windows Auto-Start..." "در حال تنظیم راه‌اندازی خودکار..."
    try {
        $wshShell = New-Object -ComObject WScript.Shell
        $shortcut = $wshShell.CreateShortcut($StartupShortcut)
        $shortcut.TargetPath = "powershell.exe"
        $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptDir\start.ps1`" -Action start-bg -Port $Port -NoBrowser"
        $shortcut.WorkingDirectory = $ScriptDir
        $shortcut.Description = "Simban Auto-Start Background Service"
        $shortcut.Save()

        Write-LogOk "Startup" "Auto-Start enabled successfully." "راه‌اندازی خودکار فعال شد."
    } catch {
        Write-LogErr "Startup" "Failed to enable Auto-Start: $_" "خطا در فعال‌سازی استارت‌آپ"
    }
}

function Disable-Startup {
    if (Test-Path $StartupShortcut) {
        Remove-Item $StartupShortcut -Force
        Write-LogOk "Startup" "Auto-Start disabled." "راه‌اندازی خودکار غیرفعال شد."
    } else {
        Write-Host '  [INFO] Auto-Start was not enabled | راه‌اندازی خودکار فعال نبود' -ForegroundColor Yellow
    }
}

function Reset-Data {
    param([switch]$Force)

    if (-not $Force) {
        Write-Host "`n══════════════════════════════════════════════════════════════════════" -ForegroundColor Red
        Write-Host "  WARNING: FULL DATA RESET | هشدار: پاکسازی کامل داده‌ها" -ForegroundColor Red
        Write-Host "══════════════════════════════════════════════════════════════════════" -ForegroundColor Red
        Write-Host "  This action will permanently delete all network topology databases and logs." -ForegroundColor White
        Write-Host "  | این عملیات پایگاه‌داده توپولوژی شبکه و لاگ‌ها را به طور کامل حذف می‌کند." -ForegroundColor Gray
        Write-Host ""
        $confirm = Read-Host "Are you sure you want to delete all data? [y/N] | آیا مطمئن هستید؟"
        if ($confirm -notmatch "^[Yy]$") {
            Write-LogInfo "Reset" "Operation cancelled by user." "عملیات لغو شد."
            return
        }
    }

    Write-LogInfo "Reset" "Stopping background services first..." "در حال توقف سرویس‌ها..."
    Stop-Server | Out-Null

    Write-LogInfo "Reset" "Wiping data directory..." "در حال حذف دایرکتوری داده..."
    if (Test-Path "data") {
        Remove-Item -Path "data" -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path "data" -Force | Out-Null

    Write-LogOk "Reset" "All data and database wiped successfully." "تمامی داده‌ها و دیتابیس با موفقیت پاکسازی شدند."
}

function Show-Menu {
    while ($true) {
        Clear-Host
        $webProc = Get-ActiveServerProcess
        $srvTxt = if ($webProc) { "RUNNING" } else { "STOPPED" }
        $srvCol = if ($webProc) { "Green" } else { "DarkGray" }
        $hasStartup = Test-Path $StartupShortcut
        $startupStatus = if ($hasStartup) { "ENABLED" } else { "DISABLED" }
        $startupCol = if ($hasStartup) { "Green" } else { "DarkGray" }

        $exitText = if ($InParentSession) { "    [0] Return to Suite" } else { "    [0] Exit" }

        Write-Host "  ┌──────────────────────────────────────────────────────────────────┐" -ForegroundColor DarkCyan
        Write-Host "  │ " -NoNewline -ForegroundColor DarkCyan
        Write-Host "SIMBAN SUITE" -NoNewline -ForegroundColor Cyan
        Write-Host "      │ Cisco Switch & Topology Management      │" -ForegroundColor DarkCyan
        Write-Host "  ├──────────────────────────────────────────────────────────────────┤" -ForegroundColor DarkCyan
        Write-Host "  │ " -NoNewline -ForegroundColor DarkCyan
        Write-Host "●" -NoNewline -ForegroundColor $srvCol
        Write-Host " Web Service (:23458): [$srvTxt]" -NoNewline -ForegroundColor White
        Write-Host "                                   │" -ForegroundColor DarkCyan
        Write-Host "  ├──────────────────────────────────────────────────────────────────┤" -ForegroundColor DarkCyan
        Write-Host "  │ Windows Auto-Start: " -NoNewline -ForegroundColor DarkGray
        Write-Host "$startupStatus" -NoNewline -ForegroundColor $startupCol
        Write-Host "                                        │" -ForegroundColor DarkCyan
        Write-Host "  └──────────────────────────────────────────────────────────────────┘" -ForegroundColor DarkCyan

        Write-Host ""
        Write-Host "  Service Control:" -ForegroundColor Cyan
        Write-Host "    [1] Start Foreground Console     [2] Start Background Service" -ForegroundColor White
        Write-Host "    [3] Stop Background Service      [r] Restart Background Service" -ForegroundColor White
        Write-Host "    [4] Check Service Status" -ForegroundColor White
        Write-Host ""
        Write-Host "  Maintenance & System:" -ForegroundColor Cyan
        Write-Host "    [7] Install Dependencies         [8] Update Packages" -ForegroundColor White
        Write-Host "    [9] System Health Check          [10] Reset All Data & DB" -ForegroundColor White
        Write-Host ""
        $stOpt = if ($hasStartup) { "[6] Disable Auto-Start" } else { "[5] Enable Auto-Start" }
        Write-Host "  General:" -ForegroundColor DarkGray
        Write-Host "    $stOpt      [f] Refresh Status          $exitText" -ForegroundColor DarkGray
        Write-Host "  ────────────────────────────────────────────────────────────────────" -ForegroundColor DarkCyan
        
        $choice = Read-Host "  Choice"

        switch ($choice.ToLower()) {
            "1" { Start-Server; break }
            "2" {
                Start-ServerBackground
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "3" {
                Stop-Server
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "r" {
                Restart-Server
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "4" {
                Write-Host "`n=== وضعیت سرویس‌ها (Service Status) ===" -ForegroundColor Cyan
                Get-ServerStatus | Out-Null
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "5" {
                Enable-Startup
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "6" {
                Disable-Startup
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "7" {
                Install-Dependencies
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "8" {
                Update-Dependencies
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "9" {
                Test-HealthCheck
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "10" {
                Reset-Data
                Read-Host "`nPress Enter to return | جهت بازگشت کلید Enter را بزنید..."
                break
            }
            "f" {
                # رفرش وضعیت منو
                break
            }
            "0" {
                $byeText = if ($InParentSession) { "Returning to Boomban Suite... | در حال بازگشت به بوم‌بان..." } else { "Goodbye! | خداحافظ!" }
                Write-Host "$byeText" -ForegroundColor Green
                return
            }
            default {
                Write-Host "Invalid choice | گزینه نامعتبر است." -ForegroundColor Red
                Start-Sleep -Seconds 1
            }
        }
    }
}

switch ($Action.ToLower()) {
    "start"           { Start-Server }
    "start-bg"        { Start-ServerBackground }
    "stop"            { Stop-Server }
    "restart"         { Restart-Server }
    "status"          {
        $isActive = Get-ServerStatus
        if ($isActive) { exit 0 } else { exit 1 }
    }
    "enable-startup"  { Enable-Startup }
    "disable-startup" { Disable-Startup }
    "install"         { Install-Dependencies }
    "update"          { Update-Dependencies }
    "check"           { Test-HealthCheck }
    "reset-data"      { Reset-Data }
    "clean"           { Reset-Data }
    "help"            {
        Write-Host "Simban Help:"
        Write-Host "  .\start.ps1                          Interactive TUI Menu"
        Write-Host "  .\start.ps1 -Action start -Port 23458 Start Foreground"
        Write-Host "  .\start.ps1 -Action start-bg         Start Background Service"
        Write-Host "  .\start.ps1 -Action stop             Stop Background Service"
        Write-Host "  .\start.ps1 -Action restart          Restart Background Service"
        Write-Host "  .\start.ps1 -Action status           Check Background Status (Exit Code 0=Active, 1=Inactive)"
        Write-Host "  .\start.ps1 -Action enable-startup   Enable Auto-Start"
        Write-Host "  .\start.ps1 -Action disable-startup  Disable Auto-Start"
        Write-Host "  .\start.ps1 -Action install          Install Dependencies (uv / pip)"
        Write-Host "  .\start.ps1 -Action update           Update Packages"
        Write-Host "  .\start.ps1 -Action check            System Health Check"
        Write-Host "  .\start.ps1 -Action reset-data       Reset All Data & Database"
    }
    default           { Show-Menu }
}
