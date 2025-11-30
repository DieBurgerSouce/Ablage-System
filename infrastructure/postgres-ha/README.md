# PostgreSQL High Availability Setup

Enterprise-grade PostgreSQL HA Cluster fuer Ablage-System mit automatischem Failover.

## Architektur

```
                    ┌─────────────────────────────────────────────┐
                    │              HAProxy (Load Balancer)        │
                    │  Port 5432: Primary (R/W)                   │
                    │  Port 5433: Replicas (RO)                   │
                    │  Port 7000: Stats UI                        │
                    └─────────────────┬───────────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│   pg-node1      │        │   pg-node2      │        │   pg-node3      │
│   (Patroni)     │◀──────▶│   (Patroni)     │◀──────▶│   (Patroni)     │
│   PostgreSQL 16 │        │   PostgreSQL 16 │        │   PostgreSQL 16 │
└────────┬────────┘        └────────┬────────┘        └────────┬────────┘
         │                          │                          │
         │       Consensus via etcd (Distributed Lock)         │
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│     etcd1       │◀──────▶│     etcd2       │◀──────▶│     etcd3       │
│  (DCS Node 1)   │        │  (DCS Node 2)   │        │  (DCS Node 3)   │
└─────────────────┘        └─────────────────┘        └─────────────────┘
```

## Komponenten

| Komponente | Version | Funktion |
|------------|---------|----------|
| PostgreSQL | 16 | Datenbank |
| Patroni | 3.2.2 | HA Orchestrator |
| etcd | 3.5.11 | Distributed Configuration Store |
| HAProxy | 2.9 | Load Balancer + Health Checks |

## Features

- **Automatisches Failover**: < 30 Sekunden RTO
- **Synchrone Replikation**: RPO = 0 (kein Datenverlust)
- **Read/Write Splitting**: Separater Port fuer Leseoperationen
- **Health Checks**: Alle 2 Sekunden via Patroni REST API
- **Connection Pooling**: HAProxy mit bis zu 2000 Verbindungen
- **Self-Healing**: Automatischer Replica-Rebuild nach Ausfall

## Schnellstart

### 1. Umgebungsvariablen konfigurieren

```bash
cd infrastructure/postgres-ha
cp .env.example .env
# Passwörter in .env anpassen!
```

### 2. Cluster starten

```bash
docker-compose -f docker-compose.postgres-ha.yml up -d
```

### 3. Status pruefen

```bash
# Patroni Cluster Status
curl http://localhost:8008/cluster | jq

# HAProxy Stats
open http://localhost:7000/stats

# etcd Cluster Health
docker exec ablage-etcd1 etcdctl endpoint health --cluster
```

### 4. Mit Datenbank verbinden

```bash
# Primary (Read/Write)
psql -h localhost -p 5432 -U postgres -d ablage_system

# Replica (Read-Only)
psql -h localhost -p 5433 -U postgres -d ablage_system
```

## Ablage-System Integration

### Backend Konfiguration

```env
# .env fuer Hauptanwendung
DATABASE_URL=postgresql+asyncpg://ablage_admin:PASSWORD@localhost:5432/ablage_system

# Optional: Read-Only Verbindung fuer Leseoperationen
DATABASE_URL_READONLY=postgresql+asyncpg://ablage_admin:PASSWORD@localhost:5433/ablage_system
```

### SQLAlchemy Read/Write Splitting

```python
from sqlalchemy.ext.asyncio import create_async_engine

# Primary fuer Schreiboperationen
primary_engine = create_async_engine(
    "postgresql+asyncpg://ablage_admin:pwd@localhost:5432/ablage_system",
    pool_size=20,
    max_overflow=40
)

# Replica fuer Leseoperationen
replica_engine = create_async_engine(
    "postgresql+asyncpg://ablage_admin:pwd@localhost:5433/ablage_system",
    pool_size=50,
    max_overflow=100
)
```

## Failover-Szenarien

### Manueller Failover

```bash
# Failover zu bestimmtem Node
docker exec ablage-pg-node1 patronictl failover ablage-cluster --candidate pg-node2

# Switchover (geplant, ohne Datenverlust)
docker exec ablage-pg-node1 patronictl switchover ablage-cluster
```

### Automatischer Failover

Passiert automatisch wenn:
- Primary nicht mehr erreichbar (Healthcheck failed)
- etcd Lease abgelaufen (30 Sekunden TTL)
- Patroni waehlt neue Leader via etcd Konsens

### Replica Recovery

Nach Ausfall einer Replica:
```bash
# Patroni rebuilt automatisch
# Manuell: Reinitialize Node
docker exec ablage-pg-node2 patronictl reinit ablage-cluster pg-node2
```

## Monitoring

### Prometheus Metrics

Patroni exportiert Metrics auf Port 8008:
```
/metrics  - Prometheus Metrics
/health   - Health Status
/cluster  - Cluster Info
/leader   - Leader Check
/replica  - Replica Check
```

### Grafana Dashboard

Importiere das mitgelieferte Dashboard:
```bash
# Dashboard in infrastructure/grafana/dashboards/postgres-ha.json
```

### Alerting

Wichtige Alerts:
- `PostgreSQLNoLeader` - Kein Leader im Cluster
- `PostgreSQLReplicationLag` - Replikations-Lag > 1MB
- `PostgreSQLNodeDown` - Node nicht erreichbar
- `etcdClusterUnhealthy` - etcd Cluster-Problem

## Backup & Recovery

### Backup erstellen

```bash
# pg_dump vom Primary
docker exec ablage-pg-node1 pg_dump -U postgres ablage_system > backup.sql

# Point-in-Time Recovery vorbereiten
docker exec ablage-pg-node1 pg_basebackup -D /backup -Ft -z -P
```

### Point-in-Time Recovery

1. Cluster stoppen
2. Daten wiederherstellen
3. recovery.conf konfigurieren
4. Cluster starten

## Troubleshooting

### Cluster Status pruefen

```bash
# Patroni Status
docker exec ablage-pg-node1 patronictl list ablage-cluster

# etcd Cluster
docker exec ablage-etcd1 etcdctl member list

# HAProxy Backends
curl http://localhost:7000/stats?stats;csv
```

### Haeufige Probleme

**Problem: Kein Leader**
```bash
# Pruefen ob etcd erreichbar
docker exec ablage-etcd1 etcdctl endpoint health --cluster

# Patroni Logs pruefen
docker logs ablage-pg-node1
```

**Problem: Replication Lag**
```bash
# Lag pruefen
docker exec ablage-pg-node1 psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# WAL Position vergleichen
docker exec ablage-pg-node1 psql -U postgres -c "SELECT pg_current_wal_lsn();"
```

**Problem: Split Brain**
```bash
# Nur moeglich wenn etcd Quorum verloren
# Cluster manuell fixen
docker exec ablage-pg-node1 patronictl pause ablage-cluster
# Dann manuell Primary festlegen
docker exec ablage-pg-node1 patronictl resume ablage-cluster
```

## Performance Tuning

### PostgreSQL Parameter (in patroni.yml)

```yaml
postgresql:
  parameters:
    # Fuer 16GB RAM System
    shared_buffers: 4GB
    effective_cache_size: 12GB
    work_mem: 64MB
    maintenance_work_mem: 1GB

    # Fuer SSD Storage
    random_page_cost: 1.1
    effective_io_concurrency: 200

    # Connection Limits
    max_connections: 300
```

### HAProxy Tuning

```
global:
    maxconn 4000  # Erhoehen bei Bedarf

defaults:
    timeout connect 10s
    timeout client 60m   # Lange Queries
    timeout server 60m
```

## Sicherheit

### Netzwerk-Isolation

- etcd: Nur intern erreichbar
- PostgreSQL: Nur via HAProxy
- HAProxy Stats: Nur localhost

### Authentifizierung

- SCRAM-SHA-256 fuer PostgreSQL
- Basic Auth fuer Patroni REST API
- Basic Auth fuer HAProxy Stats

### TLS (fuer Production)

```yaml
# In patroni.yml
postgresql:
  parameters:
    ssl: on
    ssl_cert_file: /certs/server.crt
    ssl_key_file: /certs/server.key
```

## Ressourcen-Anforderungen

### Minimum (Development)

| Komponente | CPU | RAM | Disk |
|------------|-----|-----|------|
| etcd (3x) | 0.5 | 512MB | 1GB |
| PostgreSQL (3x) | 2 | 4GB | 50GB |
| HAProxy | 0.5 | 256MB | - |
| **Gesamt** | **8** | **14GB** | **153GB** |

### Empfohlen (Production)

| Komponente | CPU | RAM | Disk |
|------------|-----|-----|------|
| etcd (3x) | 2 | 2GB | 10GB SSD |
| PostgreSQL (3x) | 4 | 16GB | 500GB NVMe |
| HAProxy | 2 | 1GB | - |
| **Gesamt** | **20** | **55GB** | **1.5TB** |

## Migration von Single-Node

### 1. Backup erstellen

```bash
docker exec ablage-postgres pg_dump -U postgres ablage_system > backup.sql
```

### 2. HA Cluster starten

```bash
cd infrastructure/postgres-ha
docker-compose -f docker-compose.postgres-ha.yml up -d
```

### 3. Daten importieren

```bash
psql -h localhost -p 5432 -U postgres -d ablage_system < backup.sql
```

### 4. Ablage-System umkonfigurieren

```env
# Alt
DATABASE_URL=postgresql+asyncpg://...@postgres:5432/ablage_system

# Neu
DATABASE_URL=postgresql+asyncpg://...@haproxy:5432/ablage_system
```

### 5. Alten Container stoppen

```bash
docker stop ablage-postgres
```

---

**Letzte Aktualisierung**: 2025-11-30
**Maintainer**: Ablage-System Team
