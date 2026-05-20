# Incident Response Runbook

**Version:** 1.0
**Letzte Aktualisierung:** 2025-12-18
**Verantwortlich:** Operations Team

---

## 1. Severity-Klassifizierung

| Severity | Beschreibung | Response Time | Eskalation |
|----------|--------------|---------------|------------|
| **SEV-1 (Kritisch)** | System komplett ausgefallen, Datenverlust möglich | < 15 min | Sofort: Team Lead + CTO |
| **SEV-2 (Hoch)** | Hauptfunktionen beeinträchtigt, Workaround möglich | < 30 min | Innerhalb 1h: Team Lead |
| **SEV-3 (Mittel)** | Einzelne Features betroffen, keine kritischen Pfade | < 2h | Innerhalb 4h: Team |
| **SEV-4 (Niedrig)** | Kosmetisch, Performance-Degradation | < 24h | Nächster Arbeitstag |

---

## 2. Sofortmaßnahmen bei Incident

### 2.1 Erste Schritte (ALLE Incidents)

```bash
# 1. Incident-Kanal öffnen (Slack/Teams)
# 2. Incident Commander benennen
# 3. Status-Seite aktualisieren

# 4. Systemstatus prüfen
curl -s http://localhost:8000/api/v1/health | jq .

# 5. Logs sammeln
docker-compose logs --tail=1000 backend > incident_$(date +%Y%m%d_%H%M%S)_backend.log
docker-compose logs --tail=1000 worker > incident_$(date +%Y%m%d_%H%M%S)_worker.log
```

### 2.2 Incident-Typen und Reaktionen

#### A) API nicht erreichbar (SEV-1)

```bash
# Diagnose
curl -v http://localhost:8000/api/v1/health

# Container-Status prüfen
docker-compose ps

# Backend neu starten
docker-compose restart backend

# Bei Nginx-Problem
docker-compose restart frontend

# Logs prüfen
docker-compose logs backend --tail=200
```

#### B) Datenbank-Verbindung fehlgeschlagen (SEV-1)

```bash
# PostgreSQL Status
docker exec ablage-postgres pg_isready -U postgres

# Connection Pool prüfen
docker exec ablage-postgres psql -U postgres -c "SELECT * FROM pg_stat_activity;"

# PgBouncer Status (falls verwendet)
docker exec ablage-pgbouncer pgbouncer -d /etc/pgbouncer/pgbouncer.ini

# Notfall: Postgres neu starten
docker-compose restart postgres

# WARNUNG: Erst Backup prüfen!
```

#### C) GPU Out of Memory (SEV-2)

```bash
# GPU Status
nvidia-smi

# GPU-Speicher freigeben
docker-compose restart worker

# VRAM-intensive Prozesse killen
docker exec ablage-worker pkill -f "python.*ocr"

# GPU Recovery Service triggern
curl -X POST http://localhost:8000/api/v1/health/gpu/recover
```

#### D) Redis-Verbindung unterbrochen (SEV-2)

```bash
# Redis Status
docker exec ablage-redis redis-cli ping

# Memory-Usage prüfen
docker exec ablage-redis redis-cli info memory

# Bei Memory-Overflow
docker exec ablage-redis redis-cli FLUSHDB

# Celery Worker neu starten
docker-compose restart worker
```

#### E) MinIO Storage nicht verfügbar (SEV-2)

```bash
# MinIO Health Check
curl -f http://localhost:9000/minio/health/live

# Buckets prüfen
docker exec ablage-minio mc ls local/

# MinIO neu starten
docker-compose restart minio

# Bucket wiederherstellen (falls gelöscht)
docker exec ablage-minio mc mb local/documents
docker exec ablage-minio mc mb local/backups
```

---

## 3. Eskalationsmatrix

| Level | Wer | Wann | Kontakt |
|-------|-----|------|---------|
| L1 | On-Call Engineer | Sofort | #incident-channel |
| L2 | Team Lead | Nach 30 min oder SEV-1 | Telefon |
| L3 | CTO/Management | Nach 1h oder Datenverlust | Telefon + Email |

---

## 4. Kommunikation während Incident

### 4.1 Status-Updates

- **Alle 15 Minuten** bei SEV-1/SEV-2
- **Alle 30 Minuten** bei SEV-3
- Format: `[SEV-X] [Status] [Kurzinfo] [Nächste Schritte]`

### 4.2 Status-Seite aktualisieren

```bash
# Status-Endpoint
curl -X POST http://localhost:8000/api/v1/health/status \
  -H "Content-Type: application/json" \
  -d '{"status": "degraded", "message": "OCR-Verarbeitung verlangsamt"}'
```

---

## 5. Post-Incident

### 5.1 Checkliste nach Behebung

- [ ] Alle Services laufen (`docker-compose ps`)
- [ ] Health Check erfolgreich (`curl localhost:8000/api/v1/health`)
- [ ] Keine Fehler in Logs der letzten 10 Minuten
- [ ] Prometheus-Metriken normalisiert
- [ ] Backup verifiziert
- [ ] Status-Seite auf "Operational" gesetzt

### 5.2 Post-Mortem Template

```markdown
# Post-Mortem: [Incident-Titel]

**Datum:** YYYY-MM-DD
**Dauer:** X Stunden Y Minuten
**Severity:** SEV-X
**Incident Commander:** [Name]

## Zusammenfassung
[1-2 Sätze zur Beschreibung]

## Timeline
- HH:MM - Incident entdeckt
- HH:MM - Erste Maßnahmen
- HH:MM - Root Cause identifiziert
- HH:MM - Fix implementiert
- HH:MM - Incident geschlossen

## Root Cause
[Detaillierte Beschreibung der Ursache]

## Impact
- Betroffene Benutzer: X
- Betroffene Funktionen: [Liste]
- Datenverlust: Ja/Nein

## Lessons Learned
1. Was ging gut?
2. Was ging schlecht?
3. Was war Glück?

## Action Items
- [ ] [Action 1] - Owner - Due Date
- [ ] [Action 2] - Owner - Due Date
```

---

## 6. Notfall-Kontakte

| Rolle | Name | Telefon | Email |
|-------|------|---------|-------|
| On-Call Primary | [TBD] | [TBD] | [TBD] |
| On-Call Secondary | [TBD] | [TBD] | [TBD] |
| Team Lead | [TBD] | [TBD] | [TBD] |
| CTO | [TBD] | [TBD] | [TBD] |

---

## 7. Wichtige Links

- Grafana Dashboard: http://localhost:3002
- Prometheus: http://localhost:9090
- API Docs: http://localhost:8000/docs
- MinIO Console: http://localhost:9001
- Logs (Loki): Via Grafana "Explore"

---

## Anhang: Häufige Fehler-Codes

| Code | Beschreibung | Lösung |
|------|--------------|--------|
| `GPU_OOM_ERROR` | GPU-Speicher voll | Worker neu starten, Batch-Size reduzieren |
| `DB_CONNECTION_POOL_EXHAUSTED` | Keine DB-Verbindungen frei | PgBouncer prüfen, Connections freigeben |
| `REDIS_TIMEOUT` | Redis antwortet nicht | Redis Memory prüfen, ggf. FLUSHDB |
| `STORAGE_QUOTA_EXCEEDED` | MinIO Speicherplatz voll | Alte Dokumente archivieren/löschen |
| `OCR_BACKEND_UNAVAILABLE` | OCR-Engine nicht erreichbar | Worker-Container prüfen, GPU-Status |
