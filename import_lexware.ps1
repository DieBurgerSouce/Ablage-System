$token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNDRjZjA5NS0wMmU4LTQ1YjEtYjcwMC02NGM2NWVkZDdkYzAiLCJlbWFpbCI6ImFkbWluQGxvY2FsaG9zdC5jb20iLCJ1c2VybmFtZSI6ImFkbWluIiwiZXhwIjoxNzY4MDIyMzYzLCJpYXQiOjE3NjgwMjE0NjMsInR5cGUiOiJhY2Nlc3MiLCJqdGkiOiJrOFJWQXNWMmJuODl1bkg5cHFGNGxiQkp1YUM5QkhGekFXbW5Yb185Y3E4In0.MRqCR_uATkRHZE694lMQDvASdM5cs4cHLYjM7Gs33YM"

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
