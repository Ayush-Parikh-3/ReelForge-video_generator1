Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "             Launching ReelForge Studio" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Server starting at: http://localhost:8000" -ForegroundColor Yellow
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
