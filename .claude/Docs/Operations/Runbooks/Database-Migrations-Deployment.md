# Database-Migrations im Deployment (Backup → Dry-Run → Upgrade → Verify → Rollback)

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High) — fehlerhafte Migration = Deployment-Blocker, schlimmstenfalls Datenverlust
> Scope: geplante Migrations-Ausführung bei Deployments (Staging + Production).
> Für **akute Migrations-Incidents** (Upgrade hängt/crasht) siehe `alembic-migration-failure.md`.

## Voraussetzungen

- Zugriff auf den Zielhost (`/opt/ablage-system`), laufender Docker-Stack.
- Containernamen (laut `docker-compose.yml` / `docker ps`): `ablage-backend`, `ablage-worker`, `ablage-postgres`, `ablage-redis`.
- DB: `ablage_system`, User `ablage_admin`, Postgres auf Host-Port `:5434`.
- Automatisierung: `deploy.yml` führt seit W1-006 genau diese Sequenz aus
  (`set -euo pipefail` in allen SSH-Heredocs, Dry-Run-SQL als Workflow-Artefakt
  `alembic-dry-run-staging|production`, Abbruch VOR Container-Restart bei Migrationsfehler).
  Dieses Runbook ist die manuelle Referenz-Prozedur + Rollback-Pfad.

---

## 1. Backup (PFLICHT, vor jeder Migration)

```bash
cd /opt/ablage-system

# Voll-Backup (DB + MinIO + Redis) — wird auch von deploy.yml ausgeführt
./scripts/backup.sh all

# Alternativ nur DB (Staging-Pfad in deploy.yml: ./scripts/backup.sh db)
docker exec ablage-postgres pg_dump -U ablage_admin -d ablage_system -Fc \
  > backups/ablage_system_pre_migration_$(date +%Y%m%d_%H%M%S).dump
```

**Konvention `backups/`**: Dumps liegen im Repo-Root unter `backups/` mit Präfix
`ablage_system_pre_<anlass>_<YYYYMMDD>.dump` (Beispiel real:
`backups/ablage_system_pre_offensive_20260611.dump`). `deploy.yml` archiviert
zusätzlich `backups/pre-deployment-<timestamp>.tar.gz` — der Rollback-Step sucht
exakt dieses Muster.

**Gate**: Ohne erfolgreiches Backup wird NICHT migriert (`set -e` bricht ab).

## 2. Dry-Run (`alembic upgrade --sql`)

```bash
# Offline-SQL rendern — validiert, dass die gesamte Migrationskette auflösbar ist.
# Hinweis: ohne Startrevision rendert Alembic base:head (Struktur-Check der Kette).
docker compose run --rm backend alembic upgrade head --sql > /tmp/alembic-dry-run.sql
wc -l /tmp/alembic-dry-run.sql

# Nur die AUSSTEHENDEN Migrationen rendern (Start = aktuelle DB-Revision):
CURRENT=$(docker exec ablage-backend alembic current 2>/dev/null | awk '{print $1}' | head -1)
docker compose run --rm backend alembic upgrade "${CURRENT}:head" --sql > /tmp/alembic-dry-run-delta.sql
```

**Review**: Delta-SQL auf destruktive Statements prüfen (`DROP TABLE`, `DROP COLUMN`,
`ALTER ... TYPE`, fehlende `IF EXISTS`-Guards). Bei destruktiven Änderungen:
Freigabe einholen, Wartungsfenster planen. In CI liegt das SQL als Artefakt
`alembic-dry-run-staging|production` am Workflow-Lauf (Retention 30/90 Tage).

**Gate**: Dry-Run-Fehler (z. B. Multiple Heads, Import-Fehler in einer Migration)
→ Abbruch, Deploy findet nicht statt.

## 3. Upgrade

```bash
# Single-Head-Invariante prüfen (mehrere Heads = vorher mergen!)
docker compose run --rm backend alembic heads

# Eigentliche Migration — bei Fehler KEINEN Container-Restart durchführen
docker compose run --rm backend alembic upgrade head
```

## 4. Verify

```bash
# 1) Revision: muss dem erwarteten Head entsprechen (Stand 2026-06-11: 268)
docker exec ablage-backend alembic current

# 2) App-Health nach Restart
docker compose up -d --force-recreate --no-deps backend worker
curl -f http://localhost:8000/health

# 3) Stichprobe Schema (Beispiel Migration 268)
docker exec ablage-postgres psql -U ablage_admin -d ablage_system \
  -c "SELECT column_name FROM information_schema.columns WHERE table_name='business_entities' AND column_name='company_id';"
```

**⚠️ Stamp-Reconcile-Falle (Lesson Learned 2026-06-11)**: Eine per `alembic stamp`
reconcilte DB hat die übersprungenen Migrationen NIE AUSGEFÜHRT — Revisionsnummer
korrekt, DDL-Seiteneffekte (Trigger, Views, Daten-Backfills) fehlen trotzdem.
Real passiert mit Migration 151: GoBD-INSERT-only-Trigger fehlten auf
`domain_events`/`gobd_audit_chain`. Reparatur (idempotent):

```bash
docker exec -i ablage-postgres psql -U ablage_admin -d ablage_system \
  -v ON_ERROR_STOP=1 < scripts/db/repair_gobd_triggers_20260611.sql
```

Nach jedem Stamp-Reconcile deshalb die DDL-Seiteneffekte der übersprungenen
Migrationen explizit verifizieren (Trigger: `\dft`, Views: `\dv`).

## 5. Rollback

**Bevorzugt: Restore aus dem Pre-Migration-Backup** (Alembic-`downgrade` ist bei
unserer Kettenlänge/Custom-DDL NICHT der verlässliche Pfad):

```bash
cd /opt/ablage-system

# a) Services stoppen, die auf die DB schreiben
docker compose stop backend worker worker-cpu beat

# b) Restore (Variante Voll-Backup, wie deploy.yml-Rollback-Step)
BACKUP_FILE=$(ls -t backups/pre-deployment-*.tar.gz | head -1)
./scripts/restore.sh all "$BACKUP_FILE"

# b-alt) Restore nur DB aus pg_dump-Custom-Format
docker exec -i ablage-postgres pg_restore -U ablage_admin -d ablage_system \
  --clean --if-exists < backups/ablage_system_pre_migration_<timestamp>.dump

# c) Alten Code-Stand auschecken (Version vor dem Deploy) + Services starten
git checkout <vorherige-version-oder-tag>
docker compose up -d

# d) Verifizieren
docker exec ablage-backend alembic current
curl -f http://localhost:8000/health
```

**Hinweise**:
- `deploy.yml` führt den Rollback bei fehlgeschlagenem Production-Deploy
  automatisch aus (Job `deploy-production`, Step „Rollback on Failure").
  Fehlschlagende **Production-Smoke-Tests** laufen als eigener Job NACH dem
  Deploy und triggern den automatischen Rollback NICHT → diese manuelle
  Prozedur nutzen.
- Zwischen Backup und Restore geschriebene Daten gehen verloren (RPO = Zeitpunkt
  des Backups) — Wartungsfenster bzw. Read-Only-Phase für kritische Migrationen.
- `alembic downgrade -1` nur für triviale, frisch eingespielte Einzelmigrationen
  mit sauberem `downgrade()`; vorher per `alembic downgrade -1 --sql` prüfen.

---

## Verwandte Dokumente

- `alembic-migration-failure.md` — Incident-Runbook (Upgrade hängt, Locks, Multiple Heads)
- `database-recovery.md`, `disaster-recovery.md` — vollständige Recovery-Prozeduren
- `.github/workflows/deploy.yml` — automatisierte Sequenz (W1-006/W1-025)
- `scripts/db/repair_gobd_triggers_20260611.sql` — Referenz-Reparatur für Stamp-Reconcile-Lücken
