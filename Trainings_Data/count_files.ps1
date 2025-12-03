$files = Get-ChildItem -Path 'C:\Users\benfi\Ablage_System\Trainings_Data' -Recurse -File
$stats = $files | Measure-Object -Property Length -Sum
Write-Host "Anzahl Dateien: $($stats.Count)"
Write-Host "Gesamtgröße GB: $([math]::Round($stats.Sum/1GB,2))"

# Format-Verteilung
$tif = ($files | Where-Object { $_.Extension -eq '.TIF' }).Count
$pdf = ($files | Where-Object { $_.Extension -eq '.PDF' }).Count
Write-Host "TIF-Dateien: $tif"
Write-Host "PDF-Dateien: $pdf"

# Durchschnittliche Dateigröße
$avgKB = [math]::Round(($stats.Sum / $stats.Count) / 1KB, 1)
Write-Host "Durchschnitt KB: $avgKB"
