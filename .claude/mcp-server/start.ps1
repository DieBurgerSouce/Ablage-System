# Start Orchestration MCP Server in background
# This script starts the MCP Server as a background process

$processName = "orchestration_mcp_server"
$scriptPath = "$PSScriptRoot\orchestration_server.py"

Write-Host "🚀 Starting Orchestration MCP Server..." -ForegroundColor Cyan
Write-Host "   Script: $scriptPath" -ForegroundColor Gray

# Check if already running
$existing = Get-Process | Where-Object {
    $_.Name -like "*python*" -and $_.CommandLine -like "*orchestration_server*"
}

if ($existing) {
    Write-Host "✅ MCP Server already running (PID: $($existing.Id))" -ForegroundColor Green
    Write-Host "   Use stop.ps1 to stop the server" -ForegroundColor Gray
    exit 0
}

# Check if Python is available
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ Python not found in PATH" -ForegroundColor Red
    Write-Host "   Please install Python 3.11+ or add it to PATH" -ForegroundColor Yellow
    exit 1
}

# Start in background using pythonw (no console window) with --server flag
try {
    Start-Process pythonw -ArgumentList "$scriptPath --server" -WindowStyle Hidden -PassThru | Out-Null
    Write-Host "   Started background process" -ForegroundColor Gray
}
catch {
    Write-Host "❌ Failed to start MCP Server: $_" -ForegroundColor Red
    exit 1
}

# Wait for startup
Start-Sleep -Seconds 2

# Verify process started
$started = Get-Process | Where-Object {
    $_.Name -like "*python*" -and $_.CommandLine -like "*orchestration_server*"
}

if ($started) {
    Write-Host "✅ MCP Server started successfully (PID: $($started.Id))" -ForegroundColor Green
    Write-Host "   Server is running in background" -ForegroundColor Gray
    Write-Host "   Use stop.ps1 to stop the server" -ForegroundColor Gray
}
else {
    Write-Host "❌ Failed to start MCP Server - process not found" -ForegroundColor Red
    Write-Host "   Try running manually: python $scriptPath" -ForegroundColor Yellow
    exit 1
}
