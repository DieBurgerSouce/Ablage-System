# Holt Groesse + Item-Count je Postfach via Exchange Online (zuverlaessiger als Graph-Report).
# Device-Login: Code im Terminal eingeben. Rein lesend.
Import-Module ExchangeOnlineManagement
Connect-ExchangeOnline -Device -ShowBanner:$false

function Get-Bytes($sizeObj) {
    if (-not $sizeObj) { return 0 }
    $s = $sizeObj.ToString()
    if ($s -match '\(([\d\.,]+)\s*bytes\)') {
        return [int64]($matches[1] -replace '[.,]', '')
    }
    return 0
}

$rows = Get-EXOMailbox -ResultSize Unlimited | ForEach-Object {
    $mb = $_
    $st = $null
    try { $st = Get-EXOMailboxStatistics -Identity $mb.UserPrincipalName -Properties TotalItemSize,ItemCount,TotalDeletedItemSize,DeletedItemCount -ErrorAction Stop } catch {}
    $bytes = Get-Bytes $st.TotalItemSize
    $delBytes = Get-Bytes $st.TotalDeletedItemSize
    [PSCustomObject]@{
        UPN            = $mb.UserPrincipalName
        DisplayName    = $mb.DisplayName
        Typ            = $mb.RecipientTypeDetails
        ItemCount      = if ($st) { $st.ItemCount } else { $null }
        SizeMB         = [math]::Round($bytes / 1MB, 1)
        DeletedItems   = if ($st) { $st.DeletedItemCount } else { $null }
        DeletedSizeMB  = [math]::Round($delBytes / 1MB, 1)
    }
}

$csv = "C:\Users\benfi\Ablage_System\scripts\m365\exo_sizes.csv"
$rows | Sort-Object SizeMB -Descending | Export-Csv $csv -NoTypeInformation -Encoding UTF8
"CSV: $csv"
$rows | Sort-Object SizeMB -Descending | Format-Table UPN,Typ,ItemCount,SizeMB,DeletedItems,DeletedSizeMB -AutoSize | Out-String -Width 200

$sumItems = ($rows | Measure-Object ItemCount -Sum).Sum
$sumMB    = ($rows | Measure-Object SizeMB -Sum).Sum
$sumDel   = ($rows | Measure-Object DeletedItems -Sum).Sum
"=== SUMMEN ==="
"Postfaecher:        $($rows.Count)"
"Items gesamt:       $sumItems  (+ geloescht: $sumDel)"
"Groesse gesamt:     $([math]::Round($sumMB/1024,1)) GB"
"SSD-Empfehlung:     ~$([math]::Ceiling($sumMB/1024*1.3)) GB (x1,3 fuer EML/Anhang-Overhead)"
Disconnect-ExchangeOnline -Confirm:$false
