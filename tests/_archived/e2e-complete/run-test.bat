@echo off
echo ========================================================
echo   ABLAGE-SYSTEM - Vollstaendiger E2E Test
echo ========================================================
echo.
echo Starte umfassenden Test aller Seiten und Features...
echo.

cd /d %~dp0\..\..

node tests\e2e-complete\comprehensive-test.js

echo.
echo ========================================================
echo   Test beendet! Reports in tests\e2e-complete\reports\
echo ========================================================
pause
