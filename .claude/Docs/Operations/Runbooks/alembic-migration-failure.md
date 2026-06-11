# Alembic Migration Failure Recovery Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High) - Deployment-Blocker
> RTO: 30 Minuten | RPO: N/A (Datenbank-Integrität kritisch)

## Alert

```
AlembicMigrationFailed - Migration fehlgeschlagen
AlembicVersionMismatch - Head stimmt nicht mit DB überein
AlembicLockTimeout - Migration-Lock nicht erhalten
```

## Symptome

- `alembic upgrade head` schlägt fehl
- Backend startet nicht (DB-Schema-Mismatch)
- "Target database is not up to date" Fehler
- Migration hängt (Lock-Problem)
- Datenbank in inkonsistentem Zustand

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Aktuellen Status prüfen

```bash
# Aktuelle DB-Version
docker exec ablage-backend alembic current

# Ausstehende Migrationen
docker exec ablage-backend alembic history --verbose

# Head-Version
docker exec ablage-backend alembic heads

# Vergleich DB vs. Code
docker exec ablage-backend alembic check
```

### 2. Fehler analysieren

```bash
# Letzte Migration-Logs
docker logs ablage-backend --since 10m 2>&1 | grep -E "alembic|migration|ALTER|CREATE"

# Detaillierter Fehler
docker exec ablage-backend alembic upgrade head --sql 2>&1 | tail -50

# PostgreSQL-Logs
docker logs ablage-postgres --since 10m 2>&1 | grep -E "ERROR|FATAL"
```

### 3. Datenbank-Verbindung testen

```bash
# Verbindung prüfen
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "SELECT 1;"

# Aktuelle Schema-Version aus alembic_version Tabelle
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT version_num FROM alembic_version;
"

# Aktive Locks prüfen
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT pid, state, query, wait_event_type
FROM pg_stat_activity
WHERE datname = 'ablage_system' AND state != 'idle';
"
```

---

## Häufige Fehler und Lösungen

### Fehler: "Revision not found"

```bash
# Fehlende Revision identifizieren
docker exec ablage-backend alembic history --verbose | grep -B2 -A2 "revision"

# Falls Revision fehlt: Manuell Version setzen
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
UPDATE alembic_version SET version_num = '<letzte_bekannte_revision>';
"

# Oder: Version komplett neu setzen
docker exec ablage-backend alembic stamp <bekannte_revision>
```

### Fehler: "Relation already exists"

```bash
# Migration bereits teilweise angewendet
# Option 1: Manuell korrigieren
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
-- Bereits existierende Objekte prüfen
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
SELECT column_name FROM information_schema.columns WHERE table_name = 'affected_table';
"

# Option 2: Version stampen (Migration überspringen)
docker exec ablage-backend alembic stamp <nächste_revision>
```

### Fehler: "Column does not exist"

```bash
# Fehlende Spalte identifizieren
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'table_name';
"

# Manuell hinzufügen (VORSICHT!)
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
ALTER TABLE table_name ADD COLUMN column_name data_type;
"
```

### Fehler: "Lock timeout"

```bash
# Blockierende Transaktionen finden
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT pid, usename, state, query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
"

# Blockierende Session beenden
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT pg_terminate_backend(<blocking_pid>);
"

# Migration erneut versuchen
docker exec ablage-backend alembic upgrade head
```

### Fehler: "Multiple heads"

```bash
# Heads anzeigen
docker exec ablage-backend alembic heads

# Merge-Revision erstellen
docker exec ablage-backend alembic merge -m "merge heads" <head1> <head2>

# Oder: Linearen Verlauf erzwingen
# (Nur wenn sicher, dass keine parallele Entwicklung)
docker exec ablage-backend alembic stamp <gewünschter_head>
```

---

## Rollback-Verfahren

### Zur vorherigen Version zurück

```bash
# Aktuelle Version prüfen
docker exec ablage-backend alembic current

# Downgrade um eine Revision
docker exec ablage-backend alembic downgrade -1

# Downgrade zu spezifischer Version
docker exec ablage-backend alembic downgrade <revision_id>

# SQL für Downgrade anzeigen (ohne Ausführung)
docker exec ablage-backend alembic downgrade -1 --sql
```

### Kompletter Reset (GEFÄHRLICH!)

```bash
# NUR für Entwicklung - NICHT in Produktion!
# Alle Tabellen löschen
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO public;
"

# alembic_version zurücksetzen
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
DROP TABLE IF EXISTS alembic_version;
"

# Alle Migrationen von Anfang an
docker exec ablage-backend alembic upgrade head
```

---

## Manuelle Migration

### SQL-basierte Korrektur

```bash
# Migration-SQL generieren
docker exec ablage-backend alembic upgrade head --sql > /tmp/migration.sql

# SQL manuell prüfen und bearbeiten
cat /tmp/migration.sql

# Manuell ausführen
docker exec -i ablage-postgres psql -U ablage_admin -d ablage_system < /tmp/migration.sql

# Version aktualisieren
docker exec ablage-backend alembic stamp head
```

### Fehlende Downgrade-Funktion

```python
# Wenn downgrade() fehlt oder leer ist:
# Migration bearbeiten und Downgrade hinzufügen

# migrations/versions/abc123_add_column.py
def downgrade():
    op.drop_column('table_name', 'column_name')
```

---

## Backup vor Migration

### Pre-Migration Backup

```bash
# Vollständiges Backup erstellen
docker exec ablage-postgres pg_dump -U ablage_admin -d ablage_system -F c -f /tmp/backup_pre_migration.dump

# Backup auf Host kopieren
docker cp ablage-postgres:/tmp/backup_pre_migration.dump ./backup_$(date +%Y%m%d_%H%M%S).dump

# Nach erfolgreicher Migration: Backup behalten (7 Tage)
```

### Restore nach fehlgeschlagener Migration

```bash
# Backend stoppen
docker-compose stop backend worker

# Datenbank wiederherstellen
docker exec ablage-postgres pg_restore -U ablage_admin -d ablage_system -c /tmp/backup_pre_migration.dump

# Version zurücksetzen
docker exec ablage-backend alembic stamp <backup_version>

# Services starten
docker-compose up -d backend worker
```

---

## Produktions-Checkliste

### Vor der Migration

```bash
# 1. Backup erstellen
docker exec ablage-postgres pg_dump -U ablage_admin -d ablage_system -F c -f /backup/pre_migration.dump

# 2. Aktive Verbindungen prüfen
docker exec ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT count(*) FROM pg_stat_activity WHERE datname = 'ablage_system';
"

# 3. Migration im Dry-Run testen
docker exec ablage-backend alembic upgrade head --sql > /tmp/migration_check.sql
cat /tmp/migration_check.sql

# 4. Wartungsfenster kommunizieren
```

### Während der Migration

```bash
# 1. Backend in Maintenance Mode
curl -X POST http://localhost:8000/api/v1/admin/maintenance/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Worker stoppen
docker-compose stop worker

# 3. Migration ausführen
docker exec ablage-backend alembic upgrade head

# 4. Schema validieren
docker exec ablage-backend python -c "
from app.db.models import *
from sqlalchemy import inspect
# Alle Tabellen prüfen
"
```

### Nach der Migration

```bash
# 1. Backend testen
curl http://localhost:8000/api/v1/health

# 2. Kritische Funktionen testen
curl http://localhost:8000/api/v1/documents?limit=1

# 3. Worker starten
docker-compose up -d worker

# 4. Maintenance Mode deaktivieren
curl -X DELETE http://localhost:8000/api/v1/admin/maintenance/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 5. Monitoring prüfen
```

---

## Automatische Migration im Deployment

### CI/CD Pipeline Integration

```yaml
# .github/workflows/deploy.yml
deploy:
  steps:
    - name: Backup Database
      run: |
        docker exec ablage-postgres pg_dump -U ablage_admin -d ablage_system -F c -f /backup/pre_deploy.dump

    - name: Run Migrations
      run: |
        docker exec ablage-backend alembic upgrade head
      continue-on-error: false

    - name: Rollback on Failure
      if: failure()
      run: |
        docker exec ablage-postgres pg_restore -U ablage_admin -d ablage_system -c /backup/pre_deploy.dump
```

### Startup-Migration

```python
# app/main.py
from alembic.config import Config
from alembic import command

def run_migrations():
    """Run pending migrations on startup."""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise SystemExit(1)

# Nur wenn ENABLE_AUTO_MIGRATION=true
if settings.ENABLE_AUTO_MIGRATION:
    run_migrations()
```

---

## Monitoring

### Prometheus Alerts

```yaml
groups:
  - name: alembic_alerts
    rules:
      - alert: AlembicVersionMismatch
        expr: |
          alembic_current_version != alembic_head_version
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Alembic Version Mismatch"

      - alert: AlembicMigrationDuration
        expr: alembic_migration_duration_seconds > 300
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Migration dauert > 5 Minuten"
```

### Version-Tracking

```python
# app/metrics.py
from prometheus_client import Info

alembic_version = Info('alembic_version', 'Current Alembic revision')

def update_alembic_metrics():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()
        head = script.get_current_head()

        alembic_version.info({
            'current': current or 'none',
            'head': head or 'none',
            'up_to_date': str(current == head)
        })
```

---

## Verifikation

```bash
# Aktuelle Version
docker exec ablage-backend alembic current

# Keine ausstehenden Migrationen
docker exec ablage-backend alembic check

# Schema-Validierung
docker exec ablage-backend python -c "
from sqlalchemy import create_engine, inspect
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
inspector = inspect(engine)

print('Tables:', inspector.get_table_names())
print('Indexes:', len(list(inspector.get_indexes('documents'))))
"

# API-Health
curl -s http://localhost:8000/api/v1/health | jq
```

---

## Eskalation

| Problem | Aktion |
|---------|--------|
| Einfacher Fehler | On-Call: Logs prüfen, Retry |
| Lock-Problem | DBA: Sessions beenden |
| Daten-Korruption | Backup-Restore, Senior Engineer |
| Multi-Head | DevOps: Merge-Revision erstellen |

---

## Verwandte Runbooks

- [PostgreSQL Connection Pool](postgresql-connection-pool-exhaustion.md)
- [Database Recovery](database-recovery.md)
- [Backup & Retention](backup-retention.md)
