# Canary Deployment Guide

## Uebersicht

Canary Deployments ermoeglichen schrittweise Rollouts mit automatischer
Ueberwachung und Rollback bei Problemen.

## Strategie

```
┌────────────────────────────────────────────────────────────┐
│                    CANARY DEPLOYMENT                       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Phase 1: 10% Traffic                                      │
│  ├── Dauer: 5 Minuten                                      │
│  ├── Monitoring: Error Rate, P95 Latency                   │
│  └── Rollback wenn: Error > 5% ODER Latency > 2000ms       │
│                                                            │
│  Phase 2: 50% Traffic                                      │
│  ├── Dauer: 10 Minuten                                     │
│  ├── Monitoring: Error Rate, P95 Latency                   │
│  └── Rollback wenn: Error > 5% ODER Latency > 2000ms       │
│                                                            │
│  Phase 3: 100% Traffic                                     │
│  ├── Full Rollout                                          │
│  └── Canary Container entfernt                             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Workflow starten

### Via GitHub Actions UI

1. Navigiere zu `Actions > Canary Deploy`
2. Klicke `Run workflow`
3. Fuelle die Parameter aus:
   - **version**: Tag oder Branch (z.B. `v1.2.3`)
   - **skip_staging**: Nur fuer Notfaelle
   - **max_error_rate**: Standard 5%
   - **max_latency_p95**: Standard 2000ms
4. Klicke `Run workflow`

### Via GitHub CLI

```bash
gh workflow run canary-deploy.yml \
  -f version=v1.2.3 \
  -f skip_staging=false \
  -f max_error_rate=5 \
  -f max_latency_p95=2000
```

## Architektur

### Traffic Splitting mit Nginx

```nginx
# 10% Canary Traffic
upstream backend_canary {
    server backend:8000 weight=90;
    server backend-canary:8000 weight=10;
}

# 50% Canary Traffic
upstream backend_canary {
    server backend:8000 weight=50;
    server backend-canary:8000 weight=50;
}
```

### Container Setup

```
┌─────────────────────────────────────────────────┐
│                    NGINX                        │
│              (Load Balancer)                    │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│    Backend      │   │ Backend-Canary  │
│   (Stable)      │   │   (New Ver)     │
│   weight=90     │   │   weight=10     │
└─────────────────┘   └─────────────────┘
```

## Monitoring Metriken

### Error Rate

```promql
# Error Rate fuer Canary
rate(http_requests_total{status=~"5..", instance="backend-canary"}[1m])
```

### P95 Latency

```promql
# P95 Latency fuer Canary
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{instance="backend-canary"}[1m])
)
```

### Vergleich Canary vs Stable

```promql
# Error Rate Differenz
rate(http_requests_total{status=~"5..", instance="backend-canary"}[5m])
-
rate(http_requests_total{status=~"5..", instance="backend"}[5m])
```

## Rollback Szenarien

### Automatischer Rollback

Der Workflow fuehrt automatisch ein Rollback durch wenn:

1. **Error Rate zu hoch**: > 5% (konfigurierbar)
2. **Latency zu hoch**: P95 > 2000ms (konfigurierbar)
3. **Health Check fehlschlaegt**

### Manueller Rollback

```bash
# Via GitHub CLI
gh run cancel <RUN_ID>

# Manuell auf Server
ssh prod@ablage-system.local
cd /opt/ablage-system

# Canary Config entfernen
rm -f /etc/nginx/conf.d/canary.conf

# Canary Container stoppen
docker-compose -f docker-compose.yml -f docker-compose.canary.yml stop backend-canary
docker-compose -f docker-compose.yml -f docker-compose.canary.yml rm -f backend-canary

# Nginx neu laden
docker-compose exec nginx nginx -s reload
```

## Best Practices

### Vor dem Canary Deployment

1. **Staging validieren**: Version muss auf Staging getestet sein
2. **Monitoring pruefen**: Grafana Dashboards verfuegbar
3. **Rollback Plan**: Team weiss wie manueller Rollback funktioniert
4. **Zeitpunkt**: Keine Peak-Zeiten, Team verfuegbar

### Waehrend des Deployments

1. **Monitoring beobachten**: Grafana Dashboard offen halten
2. **Logs pruefen**: Auf neue Fehler achten
3. **Bereit sein**: Fuer manuelles Eingreifen wenn noetig

### Nach dem Deployment

1. **30 Minuten beobachten**: Auch nach 100% Rollout
2. **Error Rates**: Auf Anomalien pruefen
3. **Performance**: Response Times vergleichen

## Grafana Dashboard

URL: `https://grafana.ablage-system.local/d/canary-monitoring`

### Panels

| Panel | Beschreibung |
|-------|--------------|
| Traffic Split | Aktuelle Verteilung Stable/Canary |
| Error Rate Comparison | Error Rate beider Instanzen |
| Latency Comparison | P50/P95/P99 beider Instanzen |
| Request Volume | Requests pro Sekunde |
| Health Status | Container Health Checks |

## Troubleshooting

### Canary startet nicht

```bash
# Container Logs pruefen
docker logs ablage-backend-canary

# Health Check manuell
docker exec ablage-backend-canary curl -f http://localhost:8000/health
```

### Traffic wird nicht gesplittet

```bash
# Nginx Config pruefen
docker exec ablage-nginx cat /etc/nginx/conf.d/canary.conf

# Nginx Reload
docker exec ablage-nginx nginx -s reload
```

### Metriken nicht verfuegbar

```bash
# Prometheus Targets pruefen
curl http://prometheus.ablage-system.local/api/v1/targets | jq '.data.activeTargets[] | select(.labels.instance | contains("canary"))'
```

## Konfiguration

### Schwellwerte anpassen

Die Standard-Schwellwerte koennen beim Workflow-Start angepasst werden:

| Parameter | Standard | Empfehlung |
|-----------|----------|------------|
| `max_error_rate` | 5% | 3-10% |
| `max_latency_p95` | 2000ms | 1000-5000ms |

### Timing anpassen

Um die Monitoring-Dauer zu aendern, editiere `.github/workflows/canary-deploy.yml`:

```yaml
env:
  MONITOR_INTERVAL_STEP1: 300  # 5 min -> anpassen
  MONITOR_INTERVAL_STEP2: 600  # 10 min -> anpassen
```

## Sicherheit

### Secrets erforderlich

| Secret | Beschreibung |
|--------|--------------|
| `PRODUCTION_SSH_KEY` | SSH Key fuer Production Server |
| `PRODUCTION_HOST` | Production Server Hostname |
| `PRODUCTION_USER` | SSH User |

### Environment Protection

Das Canary Deployment verwendet zwei Environments:
- `production-canary`: Fuer Canary Phasen
- `production`: Fuer Full Rollout

---

**Letzte Aktualisierung:** 2025-12-18
**Verantwortlich:** DevOps Team
