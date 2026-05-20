# Stop Orchestration MCP Server
# This script stops any running MCP Server processes

Write-Host "🛑 Stopping Orchestration MCP Server..." -ForegroundColor Cyan

# Find running MCP Server processes
$processes = Get-Process | Where-Object {
    $_.Name -like "*python*" -and $_.CommandLine -like "*orchestration_server*"
}

if (-not $processes) {
    Write-Host "✅ MCP Server is not running" -ForegroundColor Green
    exit 0
}

# Stop all found processes
$stoppedCount = 0
foreach ($proc in $processes) {
    try {
        Write-Host "   Stopping process PID: $($proc.Id)" -ForegroundColor Gray
        Stop-Process -Id $proc.Id -Force
        $stoppedCount++
    }
    catch {
        Write-Host "   ⚠️  Failed to stop PID $($proc.Id): $_" -ForegroundColor Yellow
    }
}

# Wait for cleanup
Start-Sleep -Seconds 1

# Verify stopped
$remaining = Get-Process | Where-Object {
    $_.Name -like "*python*" -and $_.CommandLine -like "*orchestration_server*"
}

if ($remaining) {
    Write-Host "❌ Some processes still running:" -ForegroundColor Red
    foreach ($proc in $remaining) {
        Write-Host "   PID: $($proc.Id)" -ForegroundColor Yellow
    }
    Write-Host "   Try manually: taskkill /F /PID <pid>" -ForegroundColor Gray
    exit 1
}
else {
    Write-Host "✅ MCP Server stopped successfully ($stoppedCount process(es))" -ForegroundColor Green
}
