# Install Orchestration MCP Server as Windows Startup Service
# Registriert den MCP Server als Windows Scheduled Task für automatischen Start

param(
    [switch]$Uninstall,
    [switch]$Force
)

$taskName = "OrchestrationMCPServer"
$scriptPath = "$PSScriptRoot\orchestration_server.py"
$pythonCmd = "pythonw"  # Use pythonw for no console window

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "🚀 Orchestration MCP Server - Windows Auto-Start Setup" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# UNINSTALL MODE
# ============================================================================

if ($Uninstall) {
    Write-Host "🗑️ Uninstalling MCP Server auto-start..." -ForegroundColor Yellow

    # Stop any running instances
    & "$PSScriptRoot\stop.ps1"

    # Remove scheduled task
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "✅ Removed scheduled task: $taskName" -ForegroundColor Green
    } else {
        Write-Host "⚠️ No scheduled task found" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor Gray
    Write-Host "✅ MCP Server auto-start uninstalled successfully" -ForegroundColor Green
    Write-Host "=" * 80 -ForegroundColor Gray
    exit 0
}

# ============================================================================
# INSTALL MODE
# ============================================================================

# 1. Check Prerequisites
Write-Host "1️⃣ Checking prerequisites..." -ForegroundColor Cyan

# Check if Python is available
$pythonPath = Get-Command $pythonCmd -ErrorAction SilentlyContinue
if (-not $pythonPath) {
    $pythonCmd = "python"  # Try regular python
    $pythonPath = Get-Command $pythonCmd -ErrorAction SilentlyContinue

    if (-not $pythonPath) {
        Write-Host "❌ Python not found in PATH" -ForegroundColor Red
        Write-Host "   Please install Python 3.11+ and add to PATH" -ForegroundColor Red
        exit 1
    }

    Write-Host "⚠️ pythonw not found, using python (will show console window)" -ForegroundColor Yellow
}

Write-Host "   ✅ Python found: $($pythonPath.Source)" -ForegroundColor Green

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "❌ MCP Server script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "   ✅ MCP Server script found" -ForegroundColor Green

# Check if config exists
$configPath = "$PSScriptRoot\config.json"
if (-not (Test-Path $configPath)) {
    Write-Host "⚠️ Config file not found: $configPath" -ForegroundColor Yellow
    Write-Host "   Server will use default configuration" -ForegroundColor Yellow
} else {
    Write-Host "   ✅ Config file found" -ForegroundColor Green
}

Write-Host ""

# 2. Check for existing task
Write-Host "2️⃣ Checking for existing installation..." -ForegroundColor Cyan

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    if ($Force) {
        Write-Host "   ⚠️ Existing task found - removing due to -Force flag" -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "   ✅ Removed existing task" -ForegroundColor Green
    } else {
        Write-Host "❌ Scheduled task '$taskName' already exists" -ForegroundColor Red
        Write-Host "   Use -Force to reinstall or -Uninstall to remove" -ForegroundColor Red
        Write-Host ""
        Write-Host "   Current task status:" -ForegroundColor Yellow
        $existingTask | Format-List State, LastRunTime, NextRunTime
        exit 1
    }
} else {
    Write-Host "   ✅ No existing installation found" -ForegroundColor Green
}

Write-Host ""

# 3. Create Scheduled Task
Write-Host "3️⃣ Creating Windows scheduled task..." -ForegroundColor Cyan

try {
    # Task action: Run Python script with --server flag
    $action = New-ScheduledTaskAction `
        -Execute $pythonPath.Source `
        -Argument "`"$scriptPath`" --server" `
        -WorkingDirectory $PSScriptRoot

    # Task trigger: At system startup + At user logon
    $triggerStartup = New-ScheduledTaskTrigger -AtStartup
    $triggerLogon = New-ScheduledTaskTrigger -AtLogOn

    # Task settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    # Task principal (run as current user)
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType S4U `
        -RunLevel Limited

    # Register task
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $triggerStartup, $triggerLogon `
        -Settings $settings `
        -Principal $principal `
        -Description "Orchestration MCP Server for Claude Code - Automatic multi-model routing" `
        -ErrorAction Stop | Out-Null

    Write-Host "   ✅ Scheduled task created successfully" -ForegroundColor Green

} catch {
    Write-Host "❌ Failed to create scheduled task: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 4. Test Start
Write-Host "4️⃣ Testing MCP Server startup..." -ForegroundColor Cyan

try {
    # Start the task
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Write-Host "   ✅ Task started" -ForegroundColor Green

    # Wait for server to initialize
    Start-Sleep -Seconds 3

    # Check if process is running
    $runningProcess = Get-Process | Where-Object {
        $_.Name -like "*python*" -and $_.CommandLine -like "*orchestration_server*"
    }

    if ($runningProcess) {
        Write-Host "   ✅ MCP Server is running (PID: $($runningProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️ MCP Server process not detected" -ForegroundColor Yellow
        Write-Host "      Check task status with: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
    }

} catch {
    Write-Host "   ⚠️ Failed to start task: $_" -ForegroundColor Yellow
    Write-Host "      Task will auto-start on next system boot/login" -ForegroundColor Yellow
}

Write-Host ""

# 5. Summary
Write-Host "=" * 80 -ForegroundColor Gray
Write-Host "✅ MCP Server Auto-Start Installation Complete!" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Gray
Write-Host ""
Write-Host "📋 Installation Summary:" -ForegroundColor Cyan
Write-Host "   Task Name: $taskName" -ForegroundColor White
Write-Host "   Python: $($pythonPath.Source)" -ForegroundColor White
Write-Host "   Script: $scriptPath" -ForegroundColor White
Write-Host "   Triggers: System Startup, User Logon" -ForegroundColor White
Write-Host "   Status: Active" -ForegroundColor Green
Write-Host ""
Write-Host "🎯 Next Steps:" -ForegroundColor Cyan
Write-Host "   1. Update C:\Users\benfi\.clauderc with MCP server configuration" -ForegroundColor White
Write-Host "   2. Restart Claude Code to detect the MCP server" -ForegroundColor White
Write-Host "   3. MCP Server will auto-start on next system boot" -ForegroundColor White
Write-Host ""
Write-Host "📚 Useful Commands:" -ForegroundColor Cyan
Write-Host "   View task:    Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray
Write-Host "   Start task:   Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray
Write-Host "   Stop task:    Stop-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray
Write-Host "   Uninstall:    .\install.ps1 -Uninstall" -ForegroundColor Gray
Write-Host "   Manual start: .\start.ps1" -ForegroundColor Gray
Write-Host "   Manual stop:  .\stop.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Gray
