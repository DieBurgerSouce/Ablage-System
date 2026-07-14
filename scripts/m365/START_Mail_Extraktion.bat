@echo off
REM ============================================================
REM  M365-Mail-Extraktion starten (Projekt E-Mail-Gedaechtnis)
REM  Doppelklick genuegt. Laeuft mit Auto-Resume, bis alles
REM  extrahiert ist. Dieses Fenster einfach offen lassen
REM  (darf minimiert werden). Zum Abbrechen Fenster schliessen
REM  - der naechste Start setzt verlustfrei fort.
REM ============================================================
title M365-Mail-Extraktion (laeuft - Fenster offen lassen)
cd /d "C:\Users\benfi\Ablage_System\scripts\m365"
where pwsh >nul 2>&1
if %errorlevel%==0 (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "run_extract_loop.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "run_extract_loop.ps1"
)
echo.
echo Fertig oder abgebrochen. Fenster kann geschlossen werden.
pause
