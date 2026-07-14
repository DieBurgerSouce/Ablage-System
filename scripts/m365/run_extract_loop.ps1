# Auto-Resume-Wrapper fuer die M365-Voll-Extraktion.
# Startet mail_01_extract.py immer wieder neu, bis es sauber (exit 0) durch ist.
# Laeuft als eigenstaendiger Prozess (ueberlebt Claude-Sitzung + Abbrueche).
$ErrorActionPreference = "Continue"
Set-Location "C:\Users\benfi\Ablage_System\scripts\m365"
$log = "C:\Users\benfi\m365_staging\logs\extract_loop.log"
"$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')  ===== LOOP-START =====" | Add-Content $log
for ($i = 1; $i -le 500; $i++) {
    "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')  Versuch ${i}: starte mail_01_extract.py --commit" | Add-Content $log
    python mail_01_extract.py --commit *>> $log
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')  FERTIG — sauberer Abschluss (exit 0) nach $i Versuch(en)" | Add-Content $log
        break
    }
    "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')  beendet mit exit $code — Neustart (Resume) in 15 s" | Add-Content $log
    Start-Sleep -Seconds 15
}
"$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')  ===== LOOP-ENDE =====" | Add-Content $log