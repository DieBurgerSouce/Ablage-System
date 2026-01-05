# Test Orchestration MCP Server
# Runs the server in test mode (CLI) to verify functionality

$scriptPath = "$PSScriptRoot\orchestration_server.py"

Write-Host "🧪 Testing Orchestration MCP Server..." -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Gray

# Check if Python is available
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ Python not found in PATH" -ForegroundColor Red
    exit 1
}

# Run test mode
Write-Host "Running MCP Server test cases..." -ForegroundColor Yellow
Write-Host ""

try {
    python $scriptPath
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host ""
        Write-Host "=" * 60 -ForegroundColor Gray
        Write-Host "✅ MCP Server tests completed successfully" -ForegroundColor Green
    }
    else {
        Write-Host ""
        Write-Host "=" * 60 -ForegroundColor Gray
        Write-Host "❌ MCP Server tests failed (exit code: $exitCode)" -ForegroundColor Red
        exit $exitCode
    }
}
catch {
    Write-Host "❌ Error running tests: $_" -ForegroundColor Red
    exit 1
}
