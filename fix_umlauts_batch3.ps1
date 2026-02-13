# Batch 3 - Fix ASCII umlauts in assigned directories
$directories = @(
    "C:\Users\benfi\Ablage_System\frontend\src\features\workflows",
    "C:\Users\benfi\Ablage_System\frontend\src\features\document-quality",
    "C:\Users\benfi\Ablage_System\frontend\src\features\dashboard",
    "C:\Users\benfi\Ablage_System\frontend\src\features\notifications",
    "C:\Users\benfi\Ablage_System\frontend\src\features\ai-admin",
    "C:\Users\benfi\Ablage_System\frontend\src\features\documents",
    "C:\Users\benfi\Ablage_System\frontend\src\features\ocr-review",
    "C:\Users\benfi\Ablage_System\frontend\src\features\mobile",
    "C:\Users\benfi\Ablage_System\frontend\src\features\document-chains",
    "C:\Users\benfi\Ablage_System\frontend\src\features\contracts",
    "C:\Users\benfi\Ablage_System\frontend\src\features\collaboration",
    "C:\Users\benfi\Ablage_System\frontend\src\features\portal",
    "C:\Users\benfi\Ablage_System\frontend\src\features\product-tour"
)

$replacements = @{
    'fuer' = 'für'
    'ueber' = 'über'
    'zurueck' = 'zurück'
    'Aenderung' = 'Änderung'
    'aenderung' = 'änderung'
    'Uebersicht' = 'Übersicht'
    'uebersicht' = 'übersicht'
    'Pruefung' = 'Prüfung'
    'pruefung' = 'prüfung'
    'Ausfuehrung' = 'Ausführung'
    'ausfuehrung' = 'ausführung'
    'Gebuehr' = 'Gebühr'
    'gebuehr' = 'gebühr'
    'Verfuegbar' = 'Verfügbar'
    'verfuegbar' = 'verfügbar'
    'Loeschen' = 'Löschen'
    'loeschen' = 'löschen'
    'Moeglich' = 'Möglich'
    'moeglich' = 'möglich'
    'oeffentlich' = 'öffentlich'
    'Eroeffnung' = 'Eröffnung'
    'eroeffnung' = 'eröffnung'
    'Oeffentlich' = 'Öffentlich'
    'Rueckgabe' = 'Rückgabe'
    'Zuruecksetzen' = 'Zurücksetzen'
    'zuruecksetzen' = 'zurücksetzen'
    'Unterstuetzung' = 'Unterstützung'
    'Kuerzlich' = 'Kürzlich'
    'kuerzlich' = 'kürzlich'
    'Verknuepfung' = 'Verknüpfung'
    'verknuepfung' = 'verknüpfung'
    'Eintraege' = 'Einträge'
    'eintraege' = 'einträge'
    'Aenderungen' = 'Änderungen'
    'Ueberweisungen' = 'Überweisungen'
    'Pruefungen' = 'Prüfungen'
    'Gebuehren' = 'Gebühren'
    'Bestaetigung' = 'Bestätigung'
    'bestaetigt' = 'bestätigt'
    'Naechste' = 'Nächste'
    'naechste' = 'nächste'
    'Spaeter' = 'Später'
    'spaeter' = 'später'
    'Faellig' = 'Fällig'
    'faellig' = 'fällig'
    'Laeuft' = 'Läuft'
    'laeuft' = 'läuft'
    'Hinzufuegen' = 'Hinzufügen'
    'hinzufuegen' = 'hinzufügen'
    'Ausfuehren' = 'Ausführen'
    'ausfuehren' = 'ausführen'
    'Ausgefuehrt' = 'Ausgeführt'
    'ausgefuehrt' = 'ausgeführt'
    'Ungueltig' = 'Ungültig'
    'ungueltig' = 'ungültig'
    'Gueltig' = 'Gültig'
    'gueltig' = 'gültig'
    'Gruende' = 'Gründe'
    'gruende' = 'gründe'
    'Erhoehung' = 'Erhöhung'
    'Regelmaessig' = 'Regelmäßig'
    'regelmaessig' = 'regelmäßig'
    'Massnahme' = 'Maßnahme'
    'Massnahmen' = 'Maßnahmen'
    'Groesse' = 'Größe'
    'groesse' = 'größe'
    'Stoerung' = 'Störung'
    'Schaetzung' = 'Schätzung'
    'Abhaengigkeit' = 'Abhängigkeit'
    'Haeufigkeit' = 'Häufigkeit'
    'Waehrung' = 'Währung'
    'Ausloeser' = 'Auslöser'
    'Verzoegerung' = 'Verzögerung'
    'Rueckmeldung' = 'Rückmeldung'
    'Begruendung' = 'Begründung'
    'Zustaendig' = 'Zuständig'
    'zustaendig' = 'zuständig'
    'Anhaenge' = 'Anhänge'
    'Zusaetzliche' = 'Zusätzliche'
    'zusaetzliche' = 'zusätzliche'
    'ermoeglicht' = 'ermöglicht'
}

$fileCount = 0
$changeCount = 0

foreach ($dir in $directories) {
    if (Test-Path $dir) {
        Get-ChildItem -Path $dir -Include *.ts,*.tsx -Recurse | ForEach-Object {
            $file = $_
            $fileCount++
            $content = Get-Content $file.FullName -Raw -Encoding UTF8
            $modified = $false

            foreach ($key in $replacements.Keys) {
                if ($content -match $key) {
                    $content = $content -replace $key, $replacements[$key]
                    $modified = $true
                }
            }

            if ($modified) {
                Set-Content -Path $file.FullName -Value $content -Encoding UTF8 -NoNewline
                $changeCount++
                Write-Host "Fixed: $($file.FullName)"
            }
        }
    }
}

Write-Host "`nProcessed $fileCount files, modified $changeCount files"
