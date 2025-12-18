# Deployment Approval Gates - Setup Guide

## Uebersicht

Dieses Dokument beschreibt die Konfiguration der GitHub Environment Protection Rules
fuer sichere Production Deployments mit manuellen Approval Gates.

## GitHub Environment Setup

### 1. Environments erstellen

Navigiere zu: `Repository > Settings > Environments`

Erstelle folgende Environments:

| Environment | Zweck |
|-------------|-------|
| `staging` | Staging-Umgebung (automatisch) |
| `production-approval` | Approval Gate vor Production |
| `production` | Production-Umgebung |

### 2. Production-Approval Environment konfigurieren

**Erforderliche Einstellungen:**

```yaml
Environment: production-approval
Required reviewers:
  - @team-leads
  - @devops
  - @security (optional)
Wait timer: 15 minutes (empfohlen)
Deployment branches:
  - main
  - release/*
  - refs/tags/v*
```

**Schritt-fuer-Schritt:**

1. Klicke auf `production-approval` Environment
2. Aktiviere `Required reviewers`
3. Fuege mindestens 2 Personen/Teams hinzu
4. Aktiviere `Wait timer` (15 Minuten)
5. Unter `Deployment branches` waehle "Selected branches"
6. Fuege Regeln hinzu:
   - `main`
   - `release/*` (Pattern)

### 3. Production Environment konfigurieren

**Erforderliche Einstellungen:**

```yaml
Environment: production
Required reviewers: (keine - Approval bereits in production-approval)
Deployment branches:
  - main
  - refs/tags/v*
Environment secrets:
  - PRODUCTION_SSH_KEY
  - PRODUCTION_HOST
  - PRODUCTION_USER
```

### 4. Staging Environment konfigurieren

```yaml
Environment: staging
Required reviewers: (keine - automatisch)
Environment secrets:
  - STAGING_SSH_KEY
  - STAGING_HOST
  - STAGING_USER
```

## Approval Workflow

```
┌─────────────────┐
│   CI/CD Tests   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Deploy Staging  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│    APPROVAL GATE                    │
│    ─────────────────────────────    │
│    - 15 Min Wait Timer              │
│    - Min. 2 Reviewer Approvals      │
│    - Checklist verifiziert          │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────┐
│Deploy Production│
└─────────────────┘
```

## Approval Checklist

Vor der Freigabe muessen Reviewer folgendes pruefen:

- [ ] Alle CI Tests bestanden
- [ ] Staging Deployment erfolgreich
- [ ] Staging Smoke Tests bestanden
- [ ] Database Migrations geprueft (falls vorhanden)
- [ ] Rollback Plan verstanden
- [ ] CAB (Change Advisory Board) informiert (bei kritischen Aenderungen)

## Change Advisory Board (CAB)

Fuer groessere Aenderungen sollte das CAB informiert werden:

**CAB-pflichtige Aenderungen:**
- Database Schema Aenderungen
- Security-relevante Updates
- Breaking API Changes
- Infrastruktur-Aenderungen
- Major Version Updates

**CAB-Prozess:**
1. Ticket im Issue Tracker erstellen
2. Aenderung dokumentieren
3. Risiko-Bewertung durchfuehren
4. CAB-Meeting abwarten (woechentlich)
5. Nach Freigabe: Deployment starten

## Rollback Strategie

Bei Problemen nach Production Deployment:

### Automatischer Rollback

Der Workflow fuehrt automatisch ein Rollback durch wenn:
- Post-Deployment Smoke Tests fehlschlagen
- Health Checks nicht bestanden werden
- Error Rate > 5% innerhalb 5 Minuten

### Manueller Rollback

```bash
# SSH auf Production Server
ssh prod@ablage-system.local

# Letztes Backup finden
ls -lt /opt/ablage-system/backups/pre-deployment-*.tar.gz | head -1

# Rollback ausfuehren
cd /opt/ablage-system
./scripts/restore.sh all backups/pre-deployment-YYYYMMDD_HHMMSS.tar.gz

# Services neu starten
docker-compose restart
```

## Monitoring nach Deployment

Nach jedem Production Deployment:

1. **Error Rate** pruefen (Grafana Dashboard)
2. **Response Times** beobachten (P95 < 500ms)
3. **GPU Memory** verifizieren (< 85%)
4. **Log Errors** auf neue Muster pruefen

Dashboard URL: `https://grafana.ablage-system.local/d/deployment-monitoring`

## Secrets Management

**Wichtig:** Alle Deployment Secrets muessen in GitHub Environment Secrets gespeichert werden:

| Secret | Environment | Beschreibung |
|--------|-------------|--------------|
| `STAGING_SSH_KEY` | staging | SSH Private Key fuer Staging |
| `STAGING_HOST` | staging | Staging Server Hostname |
| `STAGING_USER` | staging | SSH User fuer Staging |
| `PRODUCTION_SSH_KEY` | production | SSH Private Key fuer Production |
| `PRODUCTION_HOST` | production | Production Server Hostname |
| `PRODUCTION_USER` | production | SSH User fuer Production |

## Troubleshooting

### Approval nicht moeglich

**Problem:** Reviewer kann nicht approven

**Loesung:**
1. Pruefen ob Reviewer im Team ist
2. Pruefen ob Branch-Restriction greift
3. Repository Admin kontaktieren

### Wait Timer umgehen

**Problem:** Dringendes Deployment erforderlich

**Loesung:**
1. Repository Admin kann Timer umgehen
2. Emergency Deployment via Manual Workflow Dispatch
3. Dokumentation im Incident Report

### Deployment haengt

**Problem:** Job wartet endlos auf Approval

**Loesung:**
1. Workflow manuell abbrechen
2. Problem beheben
3. Neuen Workflow starten

---

**Letzte Aktualisierung:** 2025-12-18
**Verantwortlich:** DevOps Team
