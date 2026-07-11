# Runbook P0 — M365-Extraktion einrichten (fuer Ben, M365-Global-Admin)

**Projekt:** Firmen-E-Mail-Gedaechtnis · **Phase:** P0 (Sofortmassnahmen + Inventur)
**Ziel:** Entra-App + Zugang schaffen, damit `mail_00_inventur.py` **rein lesend** alle
Postfaecher inventarisiert. Danach folgt P1 (Voll-Extraktion).
**Aufwand:** ~20–30 Min. · **Alles rein lesend** (nur GET), kein Schreibzugriff auf M365.

> Reihenfolge: **1 → 7**. Abschnitt **5 (EXO-Check) ist ZEITKRITISCH** (30-Tage-Fenster
> fuer geloeschte Postfaecher, u. a. Matthias) — am besten direkt zuerst kurz pruefen.

---

## 1. Externe SSD vorbereiten (Ben-Entscheid E-S1)

Grund: `C:\` hat nur ~20 GB frei; das Roh-Archiv (0,5–3 Mio Mails, ~50–300 GB) und die
Logs/Reports gehoeren auf eine externe SSD (1–2 TB).

1. SSD anschliessen, Laufwerksbuchstaben notieren (Beispiel unten: **`E:`**).
2. Verzeichnisse anlegen (PowerShell):
   ```powershell
   New-Item -ItemType Directory -Force E:\m365_staging\secrets | Out-Null
   New-Item -ItemType Directory -Force E:\m365_staging\logs    | Out-Null
   ```
3. Optional, empfohlen: **BitLocker-To-Go** auf der SSD aktivieren (Mails = personenbezogene Daten).

> Merke dir den Pfad `E:\m365_staging` — er wird gleich als `STAGING_ROOT` eingetragen.
> Weicht der Laufwerksbuchstabe ab, ueberall unten `E:` entsprechend ersetzen.

---

## 2. Entra-App registrieren (`ablage-m365-extract`)

1. **entra.microsoft.com** → **Identitaet** → **Anwendungen** → **App-Registrierungen** → **Neue Registrierung**.
2. Name: `ablage-m365-extract` · Kontotypen: **Nur dieser Organisation** (Single-Tenant) ·
   **keine** Redirect-URI. → **Registrieren**.
3. Auf der **Uebersicht** notieren:
   - **Anwendungs-ID (Client)** → `M365_CLIENT_ID`
   - **Verzeichnis-ID (Mandant/Tenant)** → `M365_TENANT_ID`
4. Links **API-Berechtigungen** → **Berechtigung hinzufuegen** → **Microsoft Graph** →
   **Anwendungsberechtigungen** (NICHT „Delegiert"!) → je einzeln suchen und hinzufuegen:
   - `Mail.Read`
   - `User.Read.All`
   - `Reports.Read.All`
5. Danach **„Administratorzustimmung fuer <Firma> erteilen"** klicken → Status muss bei allen
   dreien **gruen** („Erteilt fuer …") sein. Ohne Admin-Consent schlaegt alles fehl.

> **Application-Permissions** heisst: die App liest tenant-weit **ohne** angemeldeten Nutzer
> (App-only). Genau das brauchen wir fuer die Massen-Extraktion.

---

## 3. Anmeldung einrichten — Zertifikat (empfohlen) ODER Secret

### 3a. Variante A — Zertifikat (empfohlen, sicherer)

Alles in einer **PowerShell 7** (pwsh) ausfuehren. Ersetze `E:` bei Bedarf.

```powershell
# (a) Selbstsigniertes Zertifikat erstellen (24 Monate Gueltigkeit)
$cert = New-SelfSignedCertificate -Subject "CN=ablage-m365-extract" `
  -CertStoreLocation Cert:\CurrentUser\My -KeyExportPolicy Exportable `
  -KeySpec Signature -KeyLength 2048 -NotAfter (Get-Date).AddMonths(24)

# --> DAS ist dein M365_CERT_THUMBPRINT (notieren!):
$cert.Thumbprint

# (b) Oeffentlichen Teil als .cer exportieren (wird in der App hochgeladen)
Export-Certificate -Cert $cert -FilePath E:\m365_staging\secrets\ablage-m365.cer | Out-Null

# (c) Privaten Schluessel als PEM exportieren (fuer MSAL) — ohne OpenSSL, PowerShell 7+
$rsa   = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
$b64   = [Convert]::ToBase64String($rsa.ExportPkcs8PrivateKey())
$lines = @('-----BEGIN PRIVATE KEY-----')
for ($i = 0; $i -lt $b64.Length; $i += 64) {
  $lines += $b64.Substring($i, [Math]::Min(64, $b64.Length - $i))
}
$lines += '-----END PRIVATE KEY-----'
Set-Content -Path E:\m365_staging\secrets\ablage-m365.pem -Value $lines -Encoding ascii
```

Dann in der App hochladen:
**App-Registrierung → Zertifikate & Geheimnisse → Zertifikate → Zertifikat hochladen** →
`E:\m365_staging\secrets\ablage-m365.cer` waehlen.

Ergebnis fuer die `.env.m365`:
- `M365_CERT_PATH=E:\m365_staging\secrets\ablage-m365.pem`
- `M365_CERT_THUMBPRINT=` = der oben ausgegebene `$cert.Thumbprint`

<details>
<summary>Alternative fuer (c): PEM per OpenSSL (falls vorhanden)</summary>

```powershell
# PFX exportieren ...
$pw = ConvertTo-SecureString "temp-pass" -AsPlainText -Force
Export-PfxCertificate -Cert $cert -FilePath E:\m365_staging\secrets\ablage-m365.pfx -Password $pw | Out-Null
# ... und mit OpenSSL in unverschluesselte PEM wandeln:
openssl pkcs12 -in E:\m365_staging\secrets\ablage-m365.pfx -nocerts -nodes `
  -out E:\m365_staging\secrets\ablage-m365.pem -passin pass:temp-pass
```
Danach die `.pfx` loeschen (`Remove-Item …ablage-m365.pfx`).
</details>

> Der private Schluessel wird **ohne Passphrase** exportiert (MSAL erwartet das so).
> Die `.pem`/`.pfx` liegen nur in `…\secrets\` und sind gitignored — nie weitergeben.

### 3b. Variante B — Client-Secret (einfacher, weniger sicher; nur falls kein Zertifikat)

**App-Registrierung → Zertifikate & Geheimnisse → Neuer geheimer Clientschluessel** →
Beschreibung `ablage-m365`, Ablauf **12 Monate** → **Hinzufuegen**. Den **Wert** (nicht die
ID!) **sofort** kopieren (wird nur einmal angezeigt) → spaeter als `M365_CLIENT_SECRET`.

---

## 4. Report-Verschleierung deaktivieren (Klarnamen im Nutzungsbericht)

Sonst liefert `getMailboxUsageDetail` anonymisierte UPNs (kryptische GUIDs), und die
Inventur kann Postfaecher nicht zuordnen.

**admin.microsoft.com** → **Einstellungen** → **Organisationseinstellungen** → **Berichte** →
Haken bei **„Anonyme Identifikatoren anzeigen / Benutzer-, Gruppen- und Websitenamen in
Berichten verbergen"** **ENTFERNEN** → **Speichern**.

> Wirkt nach wenigen Minuten. Falls die Inventur trotzdem „VERSCHLEIERT" meldet: kurz warten
> und erneut laufen lassen.

---

## 5. ⚠️ ZEITKRITISCH — Exchange-Online-Check (einmalig, PowerShell)

Warum jetzt: **soft-deleted Postfaecher sind ohne Hold nur 30 Tage wiederherstellbar.**
Wenn Matthias' (Ex-Prokurist) Postfach im Fenster liegt, muss es **sofort** gesichert werden.

```powershell
# Modul (einmalig) installieren + verbinden
Install-Module ExchangeOnlineManagement -Scope CurrentUser
Connect-ExchangeOnline    # meldet dich als Admin an (Browser-Login)

# a) Kuerzlich GELOESCHTE Postfaecher (30-Tage-Fenster!) — nach Matthias suchen:
Get-Mailbox -SoftDeletedMailbox | Select DisplayName,PrimarySmtpAddress,WhenSoftDeleted

# b) Voll-Inventar inkl. Shared/Archiv/Hold (Graph liefert das NICHT):
Get-EXOMailbox -ResultSize Unlimited -PropertySets Minimum,Hold,Archive |
  Select UserPrincipalName,DisplayName,RecipientTypeDetails,ArchiveStatus,LitigationHoldEnabled,InPlaceHolds |
  Export-Csv E:\m365_staging\exo_mailboxes.csv -NoTypeInformation -Encoding UTF8
```

Bei Parameterfehlern in (b) als Fallback `-PropertySets All` verwenden:
```powershell
Get-EXOMailbox -ResultSize Unlimited -PropertySets All |
  Select UserPrincipalName,DisplayName,RecipientTypeDetails,ArchiveStatus,LitigationHoldEnabled,InPlaceHolds |
  Export-Csv E:\m365_staging\exo_mailboxes.csv -NoTypeInformation -Encoding UTF8
```

**Falls (a) etwas Relevantes zeigt (z. B. Matthias) — SOFORT handeln:**
```powershell
# Variante 1: In ein Ziel-Postfach wiederherstellen (GUID aus (a) als SourceMailbox):
New-MailboxRestoreRequest -SourceMailbox <SoftDeletedGuid> -TargetMailbox ziel@firmenich.de `
  -TargetRootFolder "Restore_Matthias" -AllowLegacyDNMismatch

# Variante 2: Gefaehrdete AKTIVE Postfaecher gegen Loeschung sichern (Hold setzen):
Set-Mailbox <upn> -LitigationHoldEnabled $true
```

> Ergebnis kurz an Claude/den Projekt-Thread melden: Gibt es Soft-Deleted-Treffer? Welche
> Postfaecher sind Shared/haben Archiv/Hold? Die Datei `exo_mailboxes.csv` erganzt die
> Graph-Inventur um genau die Infos, die Graph nicht sieht.

---

## 6. `.env.m365` befuellen

1. Vorlage kopieren:
   ```powershell
   Copy-Item C:\Users\benfi\Ablage_System\scripts\m365\.env.m365.example `
             E:\m365_staging\secrets\.env.m365
   ```
2. `E:\m365_staging\secrets\.env.m365` oeffnen und eintragen:
   - `M365_TENANT_ID` / `M365_CLIENT_ID` (aus Abschnitt 2)
   - **Zertifikat:** `M365_CERT_PATH` + `M365_CERT_THUMBPRINT` (aus 3a) —
     **oder** **Secret:** `M365_CLIENT_SECRET` (aus 3b)
   - `STAGING_ROOT=E:\m365_staging`
3. Speichern. Die Datei ist gitignored und bleibt nur auf der SSD.

> Das Skript findet die Datei automatisch ueber `STAGING_ROOT`. Alternativ kannst du den Pfad
> per Umgebungsvariable erzwingen: `$env:M365_ENV_FILE = "E:\m365_staging\secrets\.env.m365"`.

---

## 7. Inventur starten

```powershell
cd C:\Users\benfi\Ablage_System\scripts\m365

# einmalig: Abhaengigkeiten
pip install -r requirements-m365.txt

# Damit Skript + Log die SSD nutzen (falls .env nicht gelesen wird):
$env:STAGING_ROOT = "E:\m365_staging"

# Optional erst ein schneller Testlauf (5 Nutzer, ohne Ordner):
python mail_00_inventur.py --limit-users 5 --no-folders

# Dann der volle Lauf (rein lesend):
python mail_00_inventur.py
```

Ergebnis:
- `E:\m365_staging\inventur_report.csv`
- `E:\m365_staging\inventur_report.md`  ← lesbare Tabelle + Auffaelligkeiten + SSD-Empfehlung
- Log: `E:\m365_staging\logs\m365_<datum>.log`

**Beide Reports (`.md` + `.csv`) sowie `exo_mailboxes.csv` an Claude schicken** → daraus
leiten wir SSD-Groesse (E-S1), Prioritaeten und den P1-Extraktionsplan ab.

---

## Checkliste (kurz)

- [ ] SSD angeschlossen, `E:\m365_staging\{secrets,logs}` angelegt (Abschnitt 1)
- [ ] Entra-App `ablage-m365-extract`, 3 App-Permissions + **Admin-Consent gruen** (2)
- [ ] Zertifikat erstellt, `.cer` hochgeladen, `.pem` + Thumbprint notiert (3a) — oder Secret (3b)
- [ ] Report-Verschleierung deaktiviert (4)
- [ ] ⚠️ EXO-Check: Soft-Deleted (Matthias) geprueft, `exo_mailboxes.csv` erzeugt (5)
- [ ] `.env.m365` befuellt (6)
- [ ] `mail_00_inventur.py` gelaufen, Reports an Claude (7)

## Wenn etwas klemmt

| Meldung | Ursache / Loesung |
|---|---|
| `[KONFIG-FEHLER] … unvollstaendig` | `.env.m365` fehlt/unvollstaendig → Abschnitt 6; Pfad korrekt? |
| `[AUTH-FEHLER] … invalid_client` / Zertifikat | `.cer` in der App hochgeladen? Thumbprint korrekt? `.pem` = privater Schluessel ohne Passphrase? |
| `[GRAPH-FEHLER] HTTP 403 … Authorization_RequestDenied` | Admin-Consent fehlt oder Permission nicht gesetzt (Abschnitt 2) |
| Inventur meldet **VERSCHLEIERT** | Abschnitt 4 (Verschleierung) noch aktiv → deaktivieren, kurz warten, erneut |
| `Modul 'msal' fehlt` | `pip install -r requirements-m365.txt` |
| Reports landen in `scripts\m365\` statt SSD | `STAGING_ROOT` nicht gesetzt → `.env.m365` oder `$env:STAGING_ROOT` setzen |
