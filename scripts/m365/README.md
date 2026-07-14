# M365-Toolkit — Firmen-E-Mail-Gedaechtnis (Saeule 1: Extraktion)

Werkzeuge zur **rein lesenden** Erfassung aller Firmen-E-Mails aus Microsoft 365
(Tenant „spargelmesserfirmenich") ueber die **Microsoft Graph API**. Teil des Projekts
*„Firmen-E-Mail-Gedaechtnis"* — Historie komplett archivieren, jeden Geschaeftsvorgang
verstehen, mit den Odoo-Vorgaengen und dem Ablage_System verknuepfen.

- **Plan:** `C:\Users\benfi\.claude\plans\gleaming-plotting-crown.md` (Saeule 1 = Abschnitt 5, Phasenplan = Abschnitt 8)
- **Einrichtung (Klickstrecke fuer Ben):** [`RUNBOOK_P0_BEN.md`](RUNBOOK_P0_BEN.md)
- **Grundsatz:** M365 wird **ausschliesslich lesend** angesprochen (nur GET). Kein Schreibzugriff.

## Schnellstart

```powershell
# 1) Abhaengigkeiten installieren
pip install -r requirements-m365.txt

# 2) Zugangsdaten anlegen (Vorlage kopieren + befuellen; siehe Runbook)
#    -> E:\m365_staging\secrets\.env.m365   (aus .env.m365.example)

# 3) Inventur starten (rein lesend)
python mail_00_inventur.py
```

Optionen der Inventur: `--no-folders` (Ordner-Zaehlung ueberspringen),
`--limit-users N` (Testlauf), `--json` (Rohdaten zusaetzlich), `--period D7|D30|D90|D180`.

Reports landen unter `STAGING_ROOT` (`inventur_report.csv` / `.md`), sonst im aktuellen
Verzeichnis (mit Warnung).

## Bausteine

```
scripts/m365/
├─ mail_lib/                 gemeinsames Paket
│  ├─ config.py              laedt .env.m365 (Zertifikat/Secret, Tenant, STAGING_ROOT)
│  ├─ auth.py                MSAL Client-Credentials (Zertifikat bevorzugt), Token-Cache
│  ├─ graph.py               httpx-GET-Client: 401-Refresh, 429/503-Backoff, Paging, stream_to_file
│  ├─ mailboxes.py           Postfach-Liste (exo_sizes.csv) + Adress-/Richtungs-Helfer
│  ├─ mindex.py              SQLite-Index (Schema S1.4, WAL) — Schreib-/Lese-Helfer
│  └─ log.py                 Datei-Log (<STAGING_ROOT>\logs\) + Konsole
├─ mail_00_inventur.py       P0: Postfach-Inventur (Nutzer, Nutzungsbericht, Ordner) → Report
├─ mail_01_extract.py        P1: Voll-Extraktion je Postfach (Traversal → .eml via $value), Dedup, Resume
├─ mail_02_verify.py         P1: Zaehl-/Hash-Abgleich Graph ↔ Staging → verify_report.md
├─ exo_sizes.csv             Postfach-Liste + Item-Counts (aus EXO-Cross-Check, P0)
├─ .env.m365.example         Vorlage fuer die Zugangsdaten
├─ requirements-m365.txt     msal, httpx (tnefparse optional/spaeter)
├─ RUNBOOK_P0_BEN.md         Schritt-fuer-Schritt-Einrichtung (Ben, M365-Admin)
└─ README.md                 diese Datei
```

## Extraktion (Phase P1)

```powershell
# Dry-Run (schreibt NICHTS; echte GET-Metadaten): kleinstes Postfach, 20 Mails
python mail_01_extract.py --mailbox webmaster@firmenich.de --limit-mails 20

# Voll-Lauf: alle Postfaecher, kleinste zuerst, EML+Index auf die SSD
#   (STAGING_ROOT in .env.m365 setzen ODER --staging E:\m365_staging)
python mail_01_extract.py --commit --staging E:\m365_staging

# Verifikation nach dem Lauf (Zaehl-Abgleich + Hash-Stichprobe)
python mail_02_verify.py --staging E:\m365_staging
```

`mail_01_extract.py`-Optionen: `--mailbox UPN` (wiederholbar), `--from-csv CSV`
(Default `exo_sizes.csv`), `--smallest-first`/`--no-smallest-first` (Default an),
`--limit-mails N` (Testlauf-Cap je Postfach), `--max-mailboxes N`, `--commit`
(sonst Dry-Run), `--staging PATH`, `--sleep-ms MS`.
`mail_02_verify.py`-Optionen: `--staging PATH`, `--sample N` (Default 20),
`--seed S` (Default 1337), `--fresh` (Soll frisch aus Graph statt folders-Tabelle),
`--no-hash` (nur Zaehl-Abgleich, kein Graph-Zugriff).

**Wichtig — Ordner-Listing via `/beta`:** Die Eigenschaft `wellKnownName` (sprach-
unabhaengige Erkennung von Deleted Items/Sent/Drafts) ist per `$select` nur auf dem
`/beta`-Endpunkt waehlbar; v1.0 liefert sie nicht. `mail_01_extract` listet Ordner
daher ueber `/beta`, holt Nachrichten-Metadaten und die MIME `/$value` aber ueber
stabiles `v1.0`. (Dieselbe v1.0-Einschraenkung liess die Graph-Ordnerzaehlung in
`mail_00_inventur` still scheitern — dort tragen die Zahlen aus `exo_sizes.csv`.)

**Speicher-Layout (unter `STAGING_ROOT`):** `raw\<upn>\<jahr>\<xx>\<sha256>.eml`
(Dir-Sharding) · `index.sqlite` (WAL) · `state\<upn>.json` (Checkpoints) · `logs\`.
Dedup global ueber `internetMessageId` (erste MIME = kanonisch, weitere Fundstellen
nur als `locations`-Zeile). Idempotent: Zweitlauf = 0 neue EML/Zeilen.

## Geplante Skripte (folgen mit den naechsten Phasen)

| Skript | Phase | Zweck |
|---|---|---|
| `mail_03_ingest.py`  | P5 | GoBD-Einbuchung in die Ablage (EML→MinIO + Document + Retention) |
| `mail_daily.py`      | P6 | Delta-Betrieb (Direkt-API) |
| `mail_watch.py`      | P6 | „Unbeantwortet"-Waechter → Slack `#ablage-alerts` |

> Analyse/Threading/Matching und die Odoo-Anreicherung liegen in `C:\Users\benfi\odoo\`
> (`_mcommon.py`, `_mailidx_*.py`, `_mailthread_*.py`) — siehe Plan Abschnitt 6/8.
> Das Volltext-/Anhang-/TNEF-Parsing (`messages.body_text`, `attachments`) macht
> spaeter `mail_prep` (Saeule 3); in P1 bleiben diese Felder/Tabelle bewusst leer.

## Datenschutz / Betrieb

- Nur **Mail** (kein Kalender/Kontakte/Teams). Rohdaten ausschliesslich auf der externen SSD.
- Zugangsdaten (`.env.m365`, `*.pem`) sind gitignored und gehoeren in `…\secrets\`.
- Sensibles/Privates wird spaeter (Saeule 3) vor jeder LLM-/Odoo-Nutzung geflaggt (Plan S3.2).
