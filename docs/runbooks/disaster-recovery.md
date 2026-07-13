# Disaster-Recovery-Runbook — Ablage-System (Windows/Docker-Desktop, BEWIESEN)

> **Status:** Jeder Schritt dieses Runbooks wurde am **13.07.2026** in der Phönix-DR-Generalprobe
> real ausgeführt und bewiesen (Beleg: `docs/qa-reports/phoenix-2026-07/REPORT.md`).
> **Gemessene RTO: ≈ 9:33 min** vom Restore-Start bis `prove = "verified"` auf dem
> restaurierten Dokument (Minimal-Stack, 25 Dokumente / 90 MinIO-Objekte / 12-MiB-Snapshot).
> **RPO:** Alter des jüngsten restic-Snapshots (Soll: täglicher Lauf → ≤ 24 h).
>
> **Geltung:** Totalverlust/Zweitsystem-Wiederaufbau auf Windows + Docker Desktop.
> Einzelszenarien (nur PG kaputt, nur MinIO, Beat hängt) → `scripts/backup/DR_RUNBOOK.md`.
> Dieses Runbook ist für Nicht-Ben-Leser geschrieben: alles copy-paste-fähig (Git-Bash).

---

## 0. Was du brauchst (VOR dem Ernstfall sichern!)

| Artefakt | Fundort (Stand 07/2026) | Ohne das … |
|---|---|---|
| restic-Repo | `C:\restic-phoenix\repo` (lokal) — **Offsite-Bein (Hetzner) fehlt noch!** | … gibt es nichts zu restoren |
| restic-Passwortdatei | `C:\restic-phoenix\restic.pass` + **OFFLINE-Kopie (Papier/USB im Tresor) ist PFLICHT** | … ist das Repo endgültig unlesbar |
| Git-Zugriff aufs Repo | github (Branch master bzw. Stand des Backups) | … fehlen Compose/Code (nicht im Snapshot) |
| Docker Desktop + Git-Bash | Neuinstallation: Docker Desktop (WSL2), Git for Windows | — |
| restic-Binary | `scoop install restic` oder github.com/restic/restic/releases | — |

**Der Snapshot enthält:** Postgres-Dump (custom, verifiziert), alle MinIO-Buckets,
`.env` (alle Secrets!), nginx-TLS, GoBD-Signierschlüssel (`config/gobd_signing/`),
`alembic_version.txt`. **NICHT enthalten:** Code/Compose (git), Redis (bewusst — nur
Cache/Sessions/Schedule), Modell-Caches (werden neu geladen).

## 1. Backup erstellen / prüfen (der bewiesene Windows-Weg)

```bash
cd /c/Users/benfi/Ablage_System   # bzw. frischer Klon
set -a; source <(grep -E '^(DB_PASSWORD|MINIO_ROOT_USER|MINIO_ROOT_PASSWORD)=' .env); set +a
BACKUP_BASE="C:/restic-phoenix" \
RESTIC_REPO_LOCAL="C:/restic-phoenix/repo" \
RESTIC_PASSWORD_FILE="C:/restic-phoenix/restic.pass" \
bash scripts/backup/restic_backup.sh
# Erwartung: Exit 0; Log-Zeilen "pg_dump ok", "Bucket 'documents' gespiegelt",
# "GoBD-Signierschluessel eingesammelt", "[lokal] Snapshot erstellt".

restic -r C:/restic-phoenix/repo --password-file C:/restic-phoenix/restic.pass snapshots
restic -r C:/restic-phoenix/repo --password-file C:/restic-phoenix/restic.pass check   # "no errors were found"
```

## 2. Restore ins Zweitsystem — 12 Schritte (Sollzeiten aus der Generalprobe)

Der Zweitstack läuft ISOLIERT neben einer evtl. noch laufenden Produktion
(eigenes Compose-Projekt `ablage-phoenix`, eigene Ports 18000/15434/16380/19000/19001,
eigene Volumes/Netz). Für den ECHTEN Ersatzbetrieb siehe Abschnitt 5.

```bash
cd /c/Users/benfi/Ablage_System
PHX="docker compose --env-file C:/restic-phoenix/.env.phoenix -f docker/phoenix/docker-compose.phoenix.yml -p ablage-phoenix"
```

**Schritt 1 — Snapshot wiederherstellen** *(Soll: <1 min)*
```bash
restic -r C:/restic-phoenix/repo --password-file C:/restic-phoenix/restic.pass \
  restore latest --target C:/restic-phoenix/restore
STAGE=C:/restic-phoenix/restore/C/restic-phoenix/restic-stage   # Windows-Pfadlayout!
DUMP="$STAGE/postgres/ablage_system.dump"; ls -la "$DUMP"
```

**Schritt 2 — Secrets aus der restaurierten .env ableiten** *(<1 min)*
```bash
grep -E '^(DB_PASSWORD|POSTGRES_APP_USER|POSTGRES_APP_PASSWORD|REDIS_PASSWORD|MINIO_ROOT_USER|MINIO_ROOT_PASSWORD|SECRET_KEY|DEBUG)=' \
  "$STAGE/config/.env" > C:/restic-phoenix/.env.phoenix
printf 'POSTGRES_DB=ablage_system\nPOSTGRES_USER=ablage_admin\n' >> C:/restic-phoenix/.env.phoenix
```

**Schritt 3 — Infra starten** *(Soll: ~30 s bis healthy)*
```bash
$PHX up -d postgres redis minio
$PHX ps   # warten bis 3x "healthy"
```

**Schritt 4 — App-DB-Rolle VOR dem Restore anlegen** *(<1 min)*
Die App verbindet als `ablage_app` (RLS light). Ohne die Rolle bootet das Backend nicht.
Das Skript setzt auch `ALTER DEFAULT PRIVILEGES` — dadurch bekommen die gleich
restaurierten Tabellen ihre Grants automatisch.
```bash
source C:/restic-phoenix/.env.phoenix
MSYS_NO_PATHCONV=1 docker exec -i -e PGPASSWORD="$DB_PASSWORD" ablage-phoenix-postgres-1 \
  psql -q -U ablage_admin -d ablage_system \
  -v app_password="$POSTGRES_APP_PASSWORD" -v owner_role="ablage_admin" -f - \
  < scripts/db/create_app_role.sql
```

**Schritt 5 — Postgres-Dump einspielen (per STDIN!)** *(Soll: ~1,5 min)*
> ⚠️ NICHT `docker cp` nach `/tmp` versuchen — `/tmp` ist tmpfs, `docker cp` kann
> dort nicht hineinschreiben („No such file or directory“). Stdin-Streaming nutzen:
```bash
MSYS_NO_PATHCONV=1 docker exec -i -e PGPASSWORD="$DB_PASSWORD" ablage-phoenix-postgres-1 \
  pg_restore -h 127.0.0.1 -U ablage_admin -d ablage_system \
  --clean --if-exists --no-owner --no-privileges --exit-on-error < "$DUMP"
```

**Schritt 6 — Grants nachziehen** *(idempotenter Re-Run von Schritt 4, <30 s)*

**Schritt 7 — Kontrollzahlen** *(<30 s)*
```bash
MSYS_NO_PATHCONV=1 docker exec -e PGPASSWORD="$DB_PASSWORD" ablage-phoenix-postgres-1 \
  psql -h 127.0.0.1 -U ablage_admin -d ablage_system -At \
  -c "SELECT 'documents='||count(*) FROM documents" \
  -c "SELECT 'alembic='||version_num FROM alembic_version"
cat "$STAGE/config/alembic_version.txt"   # MUSS mit alembic= übereinstimmen!
```

**Schritt 8 — MinIO-Buckets zurückspielen** *(Soll: ~30 s)*
```bash
MSYS_NO_PATHCONV=1 docker run --rm --network ablage-phoenix_phoenix-net \
  -v "$STAGE/minio:/stage:ro" -e MU="$MINIO_ROOT_USER" -e MP="$MINIO_ROOT_PASSWORD" \
  --entrypoint sh minio/mc -c 'mc alias set phx http://minio:9000 "$MU" "$MP" >/dev/null && \
    for b in /stage/*/; do n=$(basename "$b"); mc mb --ignore-existing "phx/$n" >/dev/null && \
    mc mirror --overwrite "$b" "phx/$n" >/dev/null && \
    echo "Bucket $n: $(mc ls --recursive phx/$n | wc -l) Objekte"; done'
```

**Schritt 9 — Redis bleibt leer.** Bewusst: enthält nur Cache/Sessions/RedBeat-Schedule/
Rate-Limit-Zähler. Nutzer müssen sich neu einloggen, Beat baut seinen Schedule neu auf.

**Schritt 10 — Backend starten** *(Soll: ~90 s bis healthy)*
```bash
$PHX up -d backend
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/health   # bis 200 wiederholen
docker logs ablage-phoenix-backend-1 2>&1 | grep -E 'RUN_MIGRATIONS|api_started'
```
Hinweise: `RUN_MIGRATIONS=false` ist Absicht (Stand wurde in Schritt 7 verglichen).
`DEBUG=true` aus der restaurierten .env wird bei ENVIRONMENT=production automatisch
neutralisiert (Log: `debug_forced_off_in_production`) — kein Fehler.

**Schritt 11 — Abnahme: Beweis-Batterie** → Abschnitt 3. *(Soll: ~4 min)*

**Schritt 12 — Protokollieren:** Datum, Snapshot-ID/-Alter, Dauer je Schritt, Ergebnis
in `scripts/backup/DR_RUNBOOK.md` (Restore-Test-Protokoll) eintragen.

## 3. Abnahme-Beweis-Batterie (alle 6 müssen grün sein)

```bash
BASE=http://127.0.0.1:18000/api/v1
# 1) LOGIN (max. 4 Versuche — Rate-Limit 5/15min!)
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"<bekannter-user>","password":"<passwort>"}' \
  | sed -E 's/.*"access_token":"([^"]+)".*/\1/')
# 2) Company-ID ermitteln (psql: user_companies) und Dokument mit GoBD-Archiv suchen:
#    SELECT d.id FROM documents d JOIN document_archives da ON da.document_id=d.id LIMIT 5;
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Company-ID: <company-uuid>")
# 3) DOKUMENT:  curl -s "${AUTH[@]}" "$BASE/documents/<id>"                    → HTTP 200
# 4) BYTES:     curl -s "${AUTH[@]}" "$BASE/documents/<id>/download" -o f.bin  → HTTP 200
#    sha256sum f.bin  → MUSS dem stored_hash aus Schritt 6 entsprechen
#    (Download verlangt Owner/Shared — als Dokument-EIGENTÜMER einloggen, sonst 404!)
# 5) SUCHE:     curl -s "${AUTH[@]}" "$BASE/documents/search/?q=<wort>&search_type=fts"
#               → total ≥ 1   (search_type=fts! Semantik lädt erst ein 2-GB-Modell)
# 6) DIE KRONE: curl -s -X POST "${AUTH[@]}" "$BASE/integrity/documents/<id>/prove"
#               → "verdict":"verified", "file_hash_matches":true, chain.valid:true
```
Zusatzbeweis GoBD: `sha256sum "$STAGE/config/gobd_signing/gobd_signer_key.pem"` muss dem
Schlüssel-Hash der Quelle entsprechen (Signaturen der Verfahrensdoku bleiben verifizierbar).

## 4. Bekannte Fallstricke (alle in der Generalprobe real getroffen)

| Falle | Symptom | Lösung |
|---|---|---|
| `docker cp` in tmpfs-`/tmp` | `could not open input file: No such file or directory` | Dump per **stdin** streamen (Schritt 5) |
| Git-Bash mangelt Container-Pfade | `du: cannot access 'C:/Program Files/Git/data'` | `MSYS_NO_PATHCONV=1` vor jedes docker-Kommando mit Container-Pfaden |
| Settings-Import in Wegwerf-Containern | pydantic `Field required: DB_PASSWORD, MINIO_ACCESS_KEY, MINIO_SECRET_KEY` | die drei Env-Vars immer mitgeben (z. B. bei alembic/pytest-Containern) |
| Download als Nicht-Owner | HTTP 404 „keine Berechtigung“ trotz sichtbarem Dokument | Byte-Beweis als Dokument-Eigentümer fahren (Defense-in-Depth ist Absicht) |
| Login-Rate-Limit | HTTP 429 nach 5 Versuchen | max. 4 Versuche, dann 15 min warten |
| DEBUG=true in restaurierter .env | Log `debug_forced_off_in_production` | kein Fehler — Neutralisierung ist Absicht |
| `ablage_app` fehlt | Backend-CrashLoop (Login-Fehler an der DB) | Schritt 4 VOR dem Backend-Start |

## 5. Vom Phönix-Stack zum echten Ersatzbetrieb

Der Phönix-Stack ist die Beweis-/Notbetrieb-Topologie. Für den vollen Ersatzbetrieb
(Frontend :80/:443, Worker/OCR, Monitoring):

1. Restaurierte `.env` an den Repo-Root kopieren: `cp "$STAGE/config/.env" .env`
2. TLS zurück: `cp -r "$STAGE/config/nginx-ssl/." infrastructure/nginx/ssl/`
3. GoBD-Signierschlüssel ins outputs-Volume:
   `MSYS_NO_PATHCONV=1 docker run --rm -v ablage_system_outputs:/dst -v "$STAGE/config/gobd_signing:/src:ro" alpine sh -c 'mkdir -p /dst/gobd_signing && cp -a /src/. /dst/gobd_signing/'`
4. Regulär hochfahren: `docker compose up -d` (Prod-Compose; Migrationen laufen im
   Entrypoint; GPU-Worker nur bei vorhandener NVIDIA-Runtime)
5. DB/MinIO wie Schritte 4–8, aber gegen die Prod-Containernamen (`ablage-postgres`, `ablage-minio`)
6. Beweis-Batterie (Abschnitt 3) gegen `http://localhost:8000` wiederholen — erst dann „wiederhergestellt“ melden.

## 6. Quartals-Restore-Test (Pflicht, GoBD)

- [ ] Abschnitt 1 (frisches Backup) + Abschnitte 2–3 komplett durchspielen
- [ ] RTO/Snapshot-Alter notieren, Protokollzeile in `scripts/backup/DR_RUNBOOK.md`
- [ ] Phönix-Stack danach abbauen: `$PHX down -v` (Volumes `ablage-phoenix_*` prüfen)
- [ ] Klartext-Reste löschen: `rm -rf C:/restic-phoenix/restore C:/restic-phoenix/restic-stage`
      (enthalten .env-Kopie + unverschlüsselten Dump!)

---
*Erstellt aus der Phönix-DR-Generalprobe 2026-07-13; Beweise und Rohdaten in
`docs/qa-reports/phoenix-2026-07/REPORT.md`.*
