# Rollback-Strategien

> **Ablage-System - Enterprise Rollback & Recovery Procedures**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Dieses Dokument beschreibt die Rollback-Strategien für alle Komponenten des Ablage-Systems. Ziel ist die schnelle Wiederherstellung bei fehlgeschlagenen Deployments oder kritischen Fehlern.

**Philosophie:** "Feinpoliert und durchdacht" - Jedes Deployment muss rückgängig machbar sein.

---

## Inhaltsverzeichnis

1. [Rollback-Prinzipien](#rollback-prinzipien)
2. [Deployment-Strategien](#deployment-strategien)
3. [Container-Rollback](#container-rollback)
4. [Datenbank-Rollback](#datenbank-rollback)
5. [Frontend-Rollback](#frontend-rollback)
6. [Konfigurations-Rollback](#konfigurations-rollback)
7. [Automatisierte Rollbacks](#automatisierte-rollbacks)
8. [Notfall-Prozeduren](#notfall-prozeduren)

---

## Rollback-Prinzipien

### Grundregeln

1. **Immer rollback-fähig deployen**
   - Keine Breaking Changes ohne Migrationspfad
   - Alte API-Versionen beibehalten (Deprecation-Zeitraum)
   - Feature-Flags für riskante Änderungen

2. **Backup vor jedem Deployment**
   ```bash
   # Automatisches Pre-Deployment-Backup
   ./scripts/pre-deploy-backup.sh
   ```

3. **Versionierung aller Artefakte**
   - Docker-Images: Semantic Versioning + Git-SHA
   - Datenbank: Alembic-Revisionen
   - Konfiguration: Git-Commits

4. **Dokumentierte Rollback-Schritte**
   - Jedes Deployment-Ticket enthält Rollback-Plan
   - Rollback-Runbook für jede Komponente

### Rollback-Entscheidungsmatrix

| Symptom | Schweregrad | Aktion | Zeitrahmen |
|---------|-------------|--------|------------|
| API-Fehler > 5% | Kritisch | Sofortiger Rollback | < 5 Min |
| Latenz > 5s (P95) | Hoch | Rollback nach Analyse | < 15 Min |
| Feature-Bug | Mittel | Feature-Flag deaktivieren | < 30 Min |
| UI-Problem | Niedrig | Hotfix oder nächstes Release | < 24h |

---

## Deployment-Strategien

### Blue-Green Deployment

```
┌─────────────────────────────────────────────────────┐
│                    Load Balancer                     │
└─────────────────────┬───────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   Blue (v1.2)   │     │  Green (v1.3)   │
│     AKTIV       │     │    STANDBY      │
└─────────────────┘     └─────────────────┘
```

**Deployment:**
```bash
#!/bin/bash
# blue-green-deploy.sh

CURRENT_ENV=$(docker-compose ps | grep -o 'blue\|green' | head -1)
NEW_ENV=$([ "$CURRENT_ENV" = "blue" ] && echo "green" || echo "blue")

echo "Deploying to $NEW_ENV environment..."

# 1. Neue Version deployen
docker-compose -f docker-compose.$NEW_ENV.yml up -d

# 2. Health-Check
./scripts/health-check.sh $NEW_ENV || {
    echo "Health check failed, aborting"
    docker-compose -f docker-compose.$NEW_ENV.yml down
    exit 1
}

# 3. Traffic umschalten
./scripts/switch-traffic.sh $NEW_ENV

# 4. Alte Umgebung stoppen (nach Wartezeit)
sleep 300  # 5 Minuten Beobachtung
docker-compose -f docker-compose.$CURRENT_ENV.yml down

echo "Deployment complete. Active: $NEW_ENV"
```

**Rollback:**
```bash
#!/bin/bash
# blue-green-rollback.sh

# Sofortiges Zurückschalten auf vorherige Umgebung
CURRENT_ENV=$(cat /var/run/ablage/current-env)
PREVIOUS_ENV=$(cat /var/run/ablage/previous-env)

echo "Rolling back from $CURRENT_ENV to $PREVIOUS_ENV..."

# 1. Traffic umschalten
./scripts/switch-traffic.sh $PREVIOUS_ENV

# 2. Neue (fehlerhafte) Umgebung stoppen
docker-compose -f docker-compose.$CURRENT_ENV.yml down

# 3. Status aktualisieren
echo $PREVIOUS_ENV > /var/run/ablage/current-env

echo "Rollback complete. Active: $PREVIOUS_ENV"
```

### Canary Deployment

```
┌─────────────────────────────────────────────────────┐
│                    Load Balancer                     │
│              (90% Stable / 10% Canary)              │
└─────────────────────┬───────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Stable (v1.2)  │     │  Canary (v1.3)  │
│    90% Traffic  │     │   10% Traffic   │
│    3 Replicas   │     │    1 Replica    │
└─────────────────┘     └─────────────────┘
```

**Canary-Script:**
```bash
#!/bin/bash
# canary-deploy.sh

VERSION=$1
CANARY_PERCENT=${2:-10}

echo "Starting canary deployment of $VERSION ($CANARY_PERCENT%)"

# 1. Canary deployen
docker-compose -f docker-compose.canary.yml up -d \
    -e IMAGE_TAG=$VERSION

# 2. Traffic-Split konfigurieren
./scripts/configure-traffic-split.sh $CANARY_PERCENT

# 3. Metriken überwachen
./scripts/monitor-canary.sh &
MONITOR_PID=$!

# 4. Warten auf manuelle Freigabe oder automatischen Rollback
echo "Canary running. Press Enter to promote or Ctrl+C to rollback..."
read

# 5. Vollständiges Rollout
./scripts/promote-canary.sh $VERSION
kill $MONITOR_PID
```

**Automatischer Canary-Rollback:**
```bash
#!/bin/bash
# monitor-canary.sh

THRESHOLD_ERROR_RATE=0.05
THRESHOLD_LATENCY_MS=2000

while true; do
    ERROR_RATE=$(curl -s localhost:9090/api/v1/query \
        --data-urlencode 'query=rate(http_requests_total{status=~"5.."}[1m])' | \
        jq -r '.data.result[0].value[1]')

    LATENCY=$(curl -s localhost:9090/api/v1/query \
        --data-urlencode 'query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))' | \
        jq -r '.data.result[0].value[1]')

    if (( $(echo "$ERROR_RATE > $THRESHOLD_ERROR_RATE" | bc -l) )); then
        echo "ERROR: Error rate $ERROR_RATE exceeds threshold"
        ./scripts/rollback-canary.sh
        exit 1
    fi

    if (( $(echo "$LATENCY * 1000 > $THRESHOLD_LATENCY_MS" | bc -l) )); then
        echo "ERROR: Latency ${LATENCY}s exceeds threshold"
        ./scripts/rollback-canary.sh
        exit 1
    fi

    sleep 30
done
```

---

## Container-Rollback

### Docker-Image-Rollback

```bash
#!/bin/bash
# container-rollback.sh

SERVICE=$1
TARGET_VERSION=${2:-"previous"}

echo "Rolling back $SERVICE to $TARGET_VERSION..."

if [ "$TARGET_VERSION" = "previous" ]; then
    # Hole vorherige Version aus History
    TARGET_VERSION=$(docker image ls --format "{{.Tag}}" ablage-$SERVICE | \
        grep -v latest | sort -rV | sed -n '2p')
fi

echo "Target version: $TARGET_VERSION"

# 1. Aktuelle Container stoppen
docker-compose stop $SERVICE

# 2. Mit alter Version neu starten
docker-compose up -d \
    -e ${SERVICE^^}_IMAGE_TAG=$TARGET_VERSION \
    $SERVICE

# 3. Health-Check
./scripts/health-check.sh $SERVICE || {
    echo "Rollback failed! Manual intervention required."
    exit 1
}

echo "Rollback of $SERVICE to $TARGET_VERSION successful"
```

### Komplettes System-Rollback

```bash
#!/bin/bash
# full-system-rollback.sh

BACKUP_TAG=$1

if [ -z "$BACKUP_TAG" ]; then
    echo "Usage: $0 <backup-tag>"
    echo "Available backups:"
    ls -la /backups/deployments/
    exit 1
fi

echo "=== FULL SYSTEM ROLLBACK TO $BACKUP_TAG ==="
echo "This will affect ALL services. Continue? (yes/no)"
read CONFIRM
[ "$CONFIRM" != "yes" ] && exit 1

# 1. Maintenance-Mode aktivieren
./scripts/maintenance-mode.sh enable

# 2. Alle Container stoppen
docker-compose down

# 3. Datenbank wiederherstellen
./scripts/restore-database.sh /backups/deployments/$BACKUP_TAG/database.dump

# 4. Konfiguration wiederherstellen
./scripts/restore-config.sh /backups/deployments/$BACKUP_TAG/config.tar.gz

# 5. Container mit alten Images starten
source /backups/deployments/$BACKUP_TAG/versions.env
docker-compose up -d

# 6. Health-Check
./scripts/full-health-check.sh || {
    echo "CRITICAL: Rollback failed! System may be unstable."
    exit 1
}

# 7. Maintenance-Mode deaktivieren
./scripts/maintenance-mode.sh disable

echo "=== ROLLBACK COMPLETE ==="
```

### Container-Versionierung

```yaml
# docker-compose.yml - Versionierungsstrategie
version: '3.8'

services:
  backend:
    image: ablage-backend:${BACKEND_VERSION:-latest}
    labels:
      - "ablage.version=${BACKEND_VERSION}"
      - "ablage.deployed_at=${DEPLOY_TIMESTAMP}"
      - "ablage.git_sha=${GIT_SHA}"
      - "ablage.previous_version=${PREVIOUS_BACKEND_VERSION}"

  worker:
    image: ablage-worker:${WORKER_VERSION:-latest}
    labels:
      - "ablage.version=${WORKER_VERSION}"
      - "ablage.deployed_at=${DEPLOY_TIMESTAMP}"

  frontend:
    image: ablage-frontend:${FRONTEND_VERSION:-latest}
    labels:
      - "ablage.version=${FRONTEND_VERSION}"
      - "ablage.deployed_at=${DEPLOY_TIMESTAMP}"
```

---

## Datenbank-Rollback

### Alembic-Migration-Rollback

```bash
#!/bin/bash
# database-rollback.sh

STEPS=${1:-1}

echo "Rolling back $STEPS migration(s)..."

# 1. Aktuelle Revision anzeigen
CURRENT=$(docker-compose exec -T backend alembic current 2>/dev/null | tail -1)
echo "Current revision: $CURRENT"

# 2. History anzeigen
echo "Migration history:"
docker-compose exec -T backend alembic history --verbose | head -20

# 3. Downgrade durchführen
docker-compose exec -T backend alembic downgrade -$STEPS

# 4. Neue Revision anzeigen
NEW=$(docker-compose exec -T backend alembic current 2>/dev/null | tail -1)
echo "New revision: $NEW"

# 5. Datenbank-Integrität prüfen
docker-compose exec -T postgres psql -U postgres -d ablage -c "
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position;
" > /tmp/schema_after_rollback.txt

echo "Database rollback complete. Schema saved to /tmp/schema_after_rollback.txt"
```

### Punkt-in-Zeit-Wiederherstellung (PITR)

```bash
#!/bin/bash
# database-pitr-restore.sh

TARGET_TIME=$1

if [ -z "$TARGET_TIME" ]; then
    echo "Usage: $0 '2025-01-08 14:30:00'"
    exit 1
fi

echo "Restoring database to $TARGET_TIME..."

# 1. PostgreSQL stoppen
docker-compose stop postgres

# 2. Datenverzeichnis sichern
mv /var/lib/postgresql/data /var/lib/postgresql/data_backup_$(date +%Y%m%d_%H%M%S)

# 3. Base-Backup wiederherstellen
pg_basebackup -D /var/lib/postgresql/data -Fp -Xs -P

# 4. Recovery-Konfiguration erstellen
cat > /var/lib/postgresql/data/recovery.signal << EOF
# Point-in-Time Recovery
EOF

cat >> /var/lib/postgresql/data/postgresql.auto.conf << EOF
restore_command = 'cp /var/lib/postgresql/wal_archive/%f %p'
recovery_target_time = '$TARGET_TIME'
recovery_target_action = 'promote'
EOF

# 5. PostgreSQL starten
docker-compose start postgres

echo "PITR to $TARGET_TIME initiated. Check logs for completion."
```

### Datenbank-Snapshot-Rollback

```bash
#!/bin/bash
# database-snapshot-restore.sh

SNAPSHOT=$1

if [ -z "$SNAPSHOT" ]; then
    echo "Available snapshots:"
    ls -la /backups/postgres/
    exit 1
fi

echo "Restoring from snapshot: $SNAPSHOT"

# 1. Maintenance-Mode
./scripts/maintenance-mode.sh enable

# 2. Bestehende Verbindungen trennen
docker-compose exec -T postgres psql -U postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = 'ablage' AND pid <> pg_backend_pid();
"

# 3. Datenbank löschen und neu erstellen
docker-compose exec -T postgres psql -U postgres -c "
    DROP DATABASE IF EXISTS ablage;
    CREATE DATABASE ablage;
"

# 4. Snapshot wiederherstellen
docker-compose exec -T postgres pg_restore \
    -U postgres -d ablage \
    --clean --if-exists \
    /backups/$SNAPSHOT

# 5. Berechtigungen setzen
docker-compose exec -T postgres psql -U postgres -d ablage -c "
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ablage_app;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ablage_app;
"

# 6. Maintenance-Mode beenden
./scripts/maintenance-mode.sh disable

echo "Database restored from $SNAPSHOT"
```

---

## Frontend-Rollback

### Nginx-basiertes Frontend-Rollback

```bash
#!/bin/bash
# frontend-rollback.sh

TARGET_VERSION=$1

if [ -z "$TARGET_VERSION" ]; then
    echo "Available versions:"
    ls -la /var/www/ablage/versions/
    exit 1
fi

echo "Rolling back frontend to $TARGET_VERSION..."

# 1. Aktuelle Version sichern
CURRENT_VERSION=$(readlink /var/www/ablage/current)
echo "Current version: $CURRENT_VERSION"

# 2. Symlink aktualisieren
ln -sfn /var/www/ablage/versions/$TARGET_VERSION /var/www/ablage/current

# 3. Nginx-Cache leeren
docker-compose exec nginx nginx -s reload

# 4. CDN-Cache invalidieren (falls vorhanden)
./scripts/invalidate-cdn-cache.sh

echo "Frontend rolled back to $TARGET_VERSION"
```

### Feature-Flag-Rollback

```python
# app/core/feature_flags.py
from redis import Redis

class FeatureFlags:
    def __init__(self, redis: Redis):
        self.redis = redis

    def disable_feature(self, feature_name: str) -> None:
        """Sofortiges Deaktivieren eines Features (Rollback)"""
        self.redis.set(f"feature:{feature_name}:enabled", "false")
        self.redis.publish("feature_flags", f"disabled:{feature_name}")

    def enable_feature(self, feature_name: str, rollout_percent: int = 100) -> None:
        """Feature aktivieren mit optionalem Rollout-Prozentsatz"""
        self.redis.set(f"feature:{feature_name}:enabled", "true")
        self.redis.set(f"feature:{feature_name}:rollout", str(rollout_percent))

    def emergency_disable_all(self) -> None:
        """Notfall: Alle neuen Features deaktivieren"""
        features = self.redis.keys("feature:*:enabled")
        for feature in features:
            if not feature.endswith(b":legacy"):
                self.redis.set(feature, "false")
```

**CLI für Feature-Rollback:**
```bash
# Feature-Flag sofort deaktivieren
docker-compose exec backend python -m app.cli features disable new_ocr_backend

# Alle experimentellen Features deaktivieren
docker-compose exec backend python -m app.cli features emergency-disable
```

---

## Konfigurations-Rollback

### Umgebungsvariablen-Rollback

```bash
#!/bin/bash
# config-rollback.sh

BACKUP_DATE=$1

if [ -z "$BACKUP_DATE" ]; then
    echo "Available config backups:"
    ls -la /backups/config/
    exit 1
fi

echo "Rolling back configuration to $BACKUP_DATE..."

# 1. Aktuelle Konfiguration sichern
cp /opt/ablage/.env /backups/config/.env.$(date +%Y%m%d_%H%M%S)

# 2. Backup wiederherstellen
cp /backups/config/.env.$BACKUP_DATE /opt/ablage/.env

# 3. Secrets wiederherstellen (verschlüsselt)
sops -d /backups/config/secrets.$BACKUP_DATE.yaml > /tmp/secrets.yaml
./scripts/apply-secrets.sh /tmp/secrets.yaml
rm /tmp/secrets.yaml

# 4. Services neu starten
docker-compose up -d

echo "Configuration rolled back to $BACKUP_DATE"
```

### Secrets-Rotation-Rollback

```bash
#!/bin/bash
# secrets-rollback.sh

# 1. Letzte Secrets-Version aus Vault holen
vault kv rollback -version=-1 secret/ablage/production

# 2. Neue Secrets in Container laden
docker-compose exec backend python -m app.cli secrets refresh

# 3. Services neu starten die Secrets nutzen
docker-compose restart backend worker

echo "Secrets rolled back to previous version"
```

---

## Automatisierte Rollbacks

### Prometheus Alert-basierter Rollback

```yaml
# prometheus/rules/rollback.yml
groups:
  - name: auto-rollback
    rules:
      - alert: AutoRollbackTrigger
        expr: |
          (
            rate(http_requests_total{status=~"5.."}[5m])
            / rate(http_requests_total[5m])
          ) > 0.10
        for: 2m
        labels:
          severity: critical
          action: auto_rollback
        annotations:
          summary: "Error rate > 10% - Auto-rollback triggered"

      - alert: AutoRollbackLatency
        expr: |
          histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 10
        for: 3m
        labels:
          severity: critical
          action: auto_rollback
        annotations:
          summary: "P99 latency > 10s - Auto-rollback triggered"
```

### Rollback-Webhook-Handler

```python
# app/api/v1/webhooks/rollback.py
from fastapi import APIRouter, BackgroundTasks
from app.services.deployment_service import DeploymentService

router = APIRouter()

@router.post("/prometheus-webhook")
async def handle_prometheus_alert(
    alert: AlertPayload,
    background_tasks: BackgroundTasks,
    deployment_service: DeploymentService = Depends()
):
    """Automatischer Rollback bei kritischen Alerts"""

    if alert.labels.get("action") == "auto_rollback":
        # Rollback im Hintergrund ausführen
        background_tasks.add_task(
            deployment_service.execute_rollback,
            reason=alert.annotations.get("summary"),
            alert_name=alert.labels.get("alertname")
        )

        # Sofortige Benachrichtigung
        await notify_team(
            channel="ops-critical",
            message=f"🚨 Auto-Rollback initiated: {alert.annotations.get('summary')}"
        )

        return {"status": "rollback_initiated"}

    return {"status": "ignored"}
```

### GitHub Actions Rollback-Workflow

```yaml
# .github/workflows/rollback.yml
name: Emergency Rollback

on:
  workflow_dispatch:
    inputs:
      target_version:
        description: 'Version to rollback to (e.g., v1.2.3 or "previous")'
        required: true
        default: 'previous'
      component:
        description: 'Component to rollback'
        required: true
        type: choice
        options:
          - all
          - backend
          - frontend
          - worker
      reason:
        description: 'Reason for rollback'
        required: true

jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure SSH
        uses: webfactory/ssh-agent@v0.8.0
        with:
          ssh-private-key: ${{ secrets.DEPLOY_SSH_KEY }}

      - name: Execute Rollback
        run: |
          ssh deploy@${{ secrets.PRODUCTION_HOST }} << 'EOF'
            cd /opt/ablage
            ./scripts/rollback.sh \
              --version ${{ inputs.target_version }} \
              --component ${{ inputs.component }} \
              --reason "${{ inputs.reason }}"
          EOF

      - name: Notify Team
        uses: slackapi/slack-github-action@v1.24.0
        with:
          payload: |
            {
              "text": "🔄 Rollback executed",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Rollback Summary*\n• Version: ${{ inputs.target_version }}\n• Component: ${{ inputs.component }}\n• Reason: ${{ inputs.reason }}\n• Triggered by: ${{ github.actor }}"
                  }
                }
              ]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

---

## Notfall-Prozeduren

### Kritischer Rollback-Checkliste

```
□ 1. Sofortmaßnahmen (< 2 Minuten)
  □ Maintenance-Page aktivieren
  □ Alerting-Team benachrichtigen
  □ Incident-Channel öffnen

□ 2. Analyse (< 5 Minuten)
  □ Fehlerquelle identifizieren
  □ Rollback-Scope bestimmen
  □ Backup-Verfügbarkeit prüfen

□ 3. Rollback ausführen (< 10 Minuten)
  □ Rollback-Script starten
  □ Health-Checks überwachen
  □ Traffic schrittweise freigeben

□ 4. Verifizierung (< 5 Minuten)
  □ Kernfunktionen testen
  □ Metriken normalisiert?
  □ Keine neuen Fehler?

□ 5. Nachbereitung
  □ Incident-Dokumentation
  □ Root-Cause-Analyse planen
  □ Preventive-Maßnahmen definieren
```

### Notfall-Kontakte

```
Rollback-Eskalation:
1. On-Call-Engineer: +49 XXX (PagerDuty)
2. Tech-Lead: +49 XXX
3. CTO: +49 XXX

Externe Partner:
- Hosting-Provider: support@hoster.de
- Datenbank-Support: dba@consulting.de
```

---

## Rollback-Dokumentation

### Post-Rollback-Template

```markdown
# Rollback-Bericht

**Datum:** YYYY-MM-DD HH:MM
**Ausführender:** Name
**Betroffene Version:** v1.2.3 → v1.2.2

## Auslöser
- Was hat den Rollback notwendig gemacht?

## Betroffene Komponenten
- [ ] Backend
- [ ] Frontend
- [ ] Worker
- [ ] Datenbank

## Timeline
- HH:MM - Problem erkannt
- HH:MM - Rollback gestartet
- HH:MM - Rollback abgeschlossen
- HH:MM - System stabil

## Root Cause
- Ursache des Problems

## Maßnahmen
- Kurzfristig: ...
- Langfristig: ...

## Lessons Learned
- Was können wir verbessern?
```

---

*Letzte Aktualisierung: Januar 2025*
