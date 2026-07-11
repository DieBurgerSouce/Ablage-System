# Token NIE hartkodieren (Sicherheitsfund 2026-07-07, war ein abgelaufener Access-Token).
# Vor Aufruf setzen:  $env:ABLAGE_JWT = "<frischer Access-Token aus /api/v1/auth/login>"
$token = $env:ABLAGE_JWT
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "ERROR: `$env:ABLAGE_JWT ist nicht gesetzt (Access-Token via POST /api/v1/auth/login holen)." -ForegroundColor Red
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $token"
}

# Kunden importieren
$foliePath = "C:\Users\benfi\Ablage_System\Firmendaten\Alle Kunden und Lieferanten\Alle Kunden Folie\tmp5E8A.xlsx"
$messerPath = "C:\Users\benfi\Ablage_System\Firmendaten\Alle Kunden und Lieferanten\Alle Kunden Messer\tmpF4F1.xlsx"

Write-Host "Importiere Kunden..."
Write-Host "Folie: $foliePath"
Write-Host "Messer: $messerPath"

# Check if files exist
if (-not (Test-Path $foliePath)) {
    Write-Host "ERROR: Folie file not found!" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $messerPath)) {
    Write-Host "ERROR: Messer file not found!" -ForegroundColor Red
    exit 1
}

# Create multipart form data
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"

$folieBytes = [System.IO.File]::ReadAllBytes($foliePath)
$messerBytes = [System.IO.File]::ReadAllBytes($messerPath)

$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"folie_file`"; filename=`"tmp5E8A.xlsx`"",
    "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "",
    [System.Text.Encoding]::GetEncoding("ISO-8859-1").GetString($folieBytes),
    "--$boundary",
    "Content-Disposition: form-data; name=`"messer_file`"; filename=`"tmpF4F1.xlsx`"",
    "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "",
    [System.Text.Encoding]::GetEncoding("ISO-8859-1").GetString($messerBytes),
    "--$boundary",
    "Content-Disposition: form-data; name=`"skip_conflicts`"",
    "",
    "true",
    "--$boundary--"
) -join $LF

$contentType = "multipart/form-data; boundary=$boundary"

try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/lexware/import/customers" `
        -Method POST `
        -Headers $headers `
        -ContentType $contentType `
        -Body ([System.Text.Encoding]::GetEncoding("ISO-8859-1").GetBytes($bodyLines))

    Write-Host "Import erfolgreich!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
}
catch {
    Write-Host "Import fehlgeschlagen!" -ForegroundColor Red
    Write-Host $_.Exception.Message
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $reader.BaseStream.Position = 0
        $responseBody = $reader.ReadToEnd()
        Write-Host $responseBody
    }
}
