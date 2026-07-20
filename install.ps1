Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CiscoToolsV2 Setup & Installation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$venvPath = Join-Path $PSScriptRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv $venvPath
    Write-Host "Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "Virtual environment (.venv) already exists." -ForegroundColor Green
}

$pipExe = Join-Path $venvPath "Scripts\pip.exe"
$reqFile = Join-Path $PSScriptRoot "requirements.txt"

Write-Host "Installing requirements..." -ForegroundColor Yellow
& $pipExe install -r $reqFile

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CiscoToolsV2 setup completed successfully!" -ForegroundColor Green
Write-Host "To start the web dashboard, run: .\start.bat" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
