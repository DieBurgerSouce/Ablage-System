# PostgreSQL High Availability mit Patroni

**Version:** 1.0
**Letzte Aktualisierung:** 2025-12-18
**Status:** Geplant (Phase 3)

---

## 1. Übersicht

Dieses Dokument beschreibt die geplante Implementierung von PostgreSQL High Availability mit Patroni für das Ablage-System.

### Warum Patroni?

| Aspekt | Aktuell | Mit Patroni |
|--------|---------|-------------|
| **Failover** | Manuell (Minuten) | Automatisch (< 30s) |
| **Downtime** | Single Point of Failure | Keine bei Node-Ausfall |
| **Skalierung** | Vertikal | Horizontal (Read Replicas) |
| **Recovery** | Manuell | Automatisch |

---

## 2. Architektur

### 2.1 Komponenten

```
┌─────────────────────────────────────────────────────────┐
│                    HAProxy / VIP                        │
│                   (Virtual IP)                          │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
┌──────────────┬──────────────┬──────────────┐
│   Patroni    │   Patroni    │   Patroni    │
│   Node 1     │   Node 2     │   Node 3     │
│  (Primary)   │  (Replica)   │  (Replica)   │
│              │              │              │
│ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │
│ │PostgreSQL│ │ │PostgreSQL│ │ │PostgreSQL│ │
│ └──────────┘ │ └──────────┘ │ └──────────┘ │
└──────────────┴──────────────┴──────────────┘
        │            │            │
        └────────────┼────────────┘
                     │
              ┌──────┴──────┐
              │    etcd     │
              │  (3 Nodes)  │
              │    DCS      │
              └─────────────┘
```

### 2.2 Komponenten-Beschreibung

| Komponente | Funktion | Anzahl |
|------------|----------|--------|
| **Patroni** | PostgreSQL Cluster Manager | 3 |
| **etcd** | Distributed Configuration Store | 3 |
| **HAProxy** | Load Balancer / Connection Routing | 2 |
| **VIP** | Virtual IP für Failover | 1 |

---

## 3. Hardware-Anforderungen

### 3.1 Pro Patroni-Node

| Resource | Minimum | Empfohlen |
|----------|---------|-----------|
| CPU | 4 Cores | 8 Cores |
| RAM | 16 GB | 32 GB |
| Storage | 100 GB SSD | 500 GB NVMe |
| Netzwerk | 1 Gbit | 10 Gbit |

### 3.2 Pro etcd-Node

| Resource | Minimum | Empfohlen |
|----------|---------|-----------|
| CPU | 2 Cores | 4 Cores |
| RAM | 4 GB | 8 GB |
| Storage | 20 GB SSD | 50 GB NVMe |
| Netzwerk | 1 Gbit | 10 Gbit |

---

## 4. Implementierungsplan

### Phase 1: Vorbereitung (Woche 1)

```bash
# 1. Infrastruktur provisionieren
terraform apply -target=module.patroni

# 2. etcd Cluster aufsetzen
ansible-playbook playbooks/etcd-cluster.yml

# 3. Patroni Packages installieren
ansible-playbook playbooks/patroni-install.yml
```

### Phase 2: Primary Setup (Woche 2)

```yaml
# /etc/patroni/config.yml (Node 1 - Primary)
scope: ablage-postgres
name: postgres-node1

restapi:
  listen: 0.0.0.0:8008
  connect_address: node1.local:8008

etcd3:
  hosts:
    - etcd1.local:2379
    - etcd2.local:2379
    - etcd3.local:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        wal_level: replica
        hot_standby: "on"
        max_wal_senders: 10
        max_replication_slots: 10
        wal_keep_size: 1GB
        archive_mode: "on"
        archive_command: 'cp %p /var/lib/ablage/backups/wal/%f'

  initdb:
    - encoding: UTF8
    - data-checksums

  pg_hba:
    - host replication replicator 0.0.0.0/0 md5
    - host all all 0.0.0.0/0 md5

postgresql:
  listen: 0.0.0.0:5432
  connect_address: node1.local:5432
  data_dir: /var/lib/postgresql/16/main
  bin_dir: /usr/lib/postgresql/16/bin
  authentication:
    superuser:
      username: postgres
      password: '${POSTGRES_PASSWORD}'
    replication:
      username: replicator
      password: '${REPLICATION_PASSWORD}'
```

### Phase 3: Replicas hinzufügen (Woche 2-3)

```bash
# Auf Node 2 und 3
patronictl -c /etc/patroni/config.yml reinit ablage-postgres postgres-node2
patronictl -c /etc/patroni/config.yml reinit ablage-postgres postgres-node3

# Cluster-Status prüfen
patronictl -c /etc/patroni/config.yml list
```

### Phase 4: HAProxy Setup (Woche 3)

```haproxy
# /etc/haproxy/haproxy.cfg

global
    maxconn 1000

defaults
    mode tcp
    timeout connect 10s
    timeout client 30s
    timeout server 30s

frontend postgres_frontend
    bind *:5432
    default_backend postgres_backend

backend postgres_backend
    option httpchk GET /master
    http-check expect status 200
    default-server inter 3s fall 3 rise 2 on-marked-down shutdown-sessions
    server node1 node1.local:5432 check port 8008
    server node2 node2.local:5432 check port 8008
    server node3 node3.local:5432 check port 8008

frontend postgres_replica
    bind *:5433
    default_backend postgres_replica_backend

backend postgres_replica_backend
    option httpchk GET /replica
    http-check expect status 200
    default-server inter 3s fall 3 rise 2
    server node1 node1.local:5432 check port 8008
    server node2 node2.local:5432 check port 8008
    server node3 node3.local:5432 check port 8008
```

### Phase 5: Migration (Woche 4)

```bash
# 1. Wartungsfenster ankündigen
# 2. Anwendung stoppen
docker-compose stop backend worker

# 3. Finales Backup
pg_dump -h localhost -U postgres ablage > final_backup.sql

# 4. DNS/Connection String aktualisieren
# DATABASE_URL=postgresql://user:pass@haproxy.local:5432/ablage

# 5. Daten migrieren
psql -h haproxy.local -U postgres -d ablage < final_backup.sql

# 6. Anwendung starten
docker-compose up -d backend worker

# 7. Verifizierung
curl http://localhost:8000/api/v1/health
```

---

## 5. Betriebsanleitungen

### 5.1 Cluster-Status prüfen

```bash
# Übersicht
patronictl -c /etc/patroni/config.yml list

# Erwartete Ausgabe:
# +-------------+----------+---------+---------+----+-----------+
# | Member      | Host     | Role    | State   | TL | Lag in MB |
# +-------------+----------+---------+---------+----+-----------+
# | postgres-1  | node1    | Leader  | running |  5 |           |
# | postgres-2  | node2    | Replica | running |  5 |         0 |
# | postgres-3  | node3    | Replica | running |  5 |         0 |
# +-------------+----------+---------+---------+----+-----------+
```

### 5.2 Manueller Switchover

```bash
# Geplanter Switchover (kein Datenverlust)
patronictl -c /etc/patroni/config.yml switchover \
  --master postgres-node1 \
  --candidate postgres-node2 \
  --scheduled now

# Bestätigen
patronictl -c /etc/patroni/config.yml list
```

### 5.3 Notfall-Failover

```bash
# Bei Node-Ausfall
patronictl -c /etc/patroni/config.yml failover \
  --candidate postgres-node2 \
  --force

# Ausgefallenen Node wieder hinzufügen
patronictl -c /etc/patroni/config.yml reinit ablage-postgres postgres-node1
```

### 5.4 Replica hinzufügen

```bash
# Neuen Node provisionieren
ansible-playbook playbooks/patroni-node.yml -e "node_name=postgres-node4"

# In Cluster einbinden
patronictl -c /etc/patroni/config.yml reinit ablage-postgres postgres-node4
```

---

## 6. Monitoring

### 6.1 Prometheus Metriken

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'patroni'
    static_configs:
      - targets:
        - node1.local:8008
        - node2.local:8008
        - node3.local:8008
```

### 6.2 Alert Rules

```yaml
# patroni-alerts.yml
groups:
  - name: patroni
    rules:
      - alert: PatroniClusterNoLeader
        expr: sum(patroni_master) == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Patroni Cluster hat keinen Leader"

      - alert: PatroniReplicaLag
        expr: patroni_xlog_replayed_location - patroni_xlog_received_location > 1048576
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Replica Lag > 1MB"

      - alert: PatroniNodeDown
        expr: up{job="patroni"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Patroni Node nicht erreichbar"
```

### 6.3 Grafana Dashboard

- Cluster-Übersicht (Leader, Replicas, Status)
- Replication Lag pro Node
- Failover-Events Timeline
- Connection Pool Usage
- Query Performance

---

## 7. Backup-Strategie mit Patroni

### 7.1 WAL-Archivierung

```sql
-- postgresql.conf (via Patroni)
archive_mode = on
archive_command = 'pgbackrest --stanza=ablage archive-push %p'
```

### 7.2 pgBackRest Integration

```ini
# /etc/pgbackrest/pgbackrest.conf
[global]
repo1-path=/var/lib/ablage/backups/pgbackrest
repo1-retention-full=7
repo1-retention-diff=14

[ablage]
pg1-path=/var/lib/postgresql/16/main
```

### 7.3 Backup-Schedule

| Typ | Frequenz | Retention |
|-----|----------|-----------|
| Full Backup | Wöchentlich | 4 Wochen |
| Differential | Täglich | 14 Tage |
| WAL Archive | Kontinuierlich | 7 Tage |

---

## 8. Connection String Konfiguration

### 8.1 Anwendung (Primary)

```bash
# Schreiboperationen
DATABASE_URL=postgresql://user:pass@haproxy.local:5432/ablage
```

### 8.2 Read Replicas

```bash
# Leseoperationen (optional)
DATABASE_URL_READONLY=postgresql://user:pass@haproxy.local:5433/ablage
```

### 8.3 SQLAlchemy Konfiguration

```python
# app/core/config.py
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL_READONLY = os.getenv("DATABASE_URL_READONLY", DATABASE_URL)

# app/db/session.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # Wichtig für Failover
    pool_recycle=3600
)
```

---

## 9. Troubleshooting

### Problem: Split-Brain

```bash
# Symptom: Zwei Leader im Cluster

# Diagnose
patronictl -c /etc/patroni/config.yml list
etcdctl member list

# Lösung
# 1. Einen Leader manuell degradieren
patronictl -c /etc/patroni/config.yml pause

# 2. Cluster neu initialisieren
patronictl -c /etc/patroni/config.yml reinit ablage-postgres --force
```

### Problem: Replication Lag > 1GB

```bash
# Diagnose
psql -h replica -U postgres -c "SELECT pg_last_wal_receive_lsn() - pg_last_wal_replay_lsn();"

# Lösung
# 1. Replica-Last reduzieren
# 2. Netzwerk-Bandbreite prüfen
# 3. ggf. Replica neu initialisieren
patronictl -c /etc/patroni/config.yml reinit ablage-postgres postgres-node2
```

---

## 10. Rollback-Plan

Falls Patroni-Migration fehlschlägt:

```bash
# 1. Anwendung stoppen
docker-compose stop

# 2. DNS zurück auf Single-Node
# DATABASE_URL=postgresql://user:pass@old-postgres:5432/ablage

# 3. Daten von Patroni zurückspielen (falls nötig)
pg_dump -h haproxy.local -U postgres ablage | \
  psql -h old-postgres -U postgres -d ablage

# 4. Anwendung starten
docker-compose up -d
```

---

## 11. Kosten-Schätzung

| Komponente | Anzahl | Monatlich (On-Prem) |
|------------|--------|---------------------|
| Patroni VMs | 3 | Hardware-Abschreibung |
| etcd VMs | 3 | Hardware-Abschreibung |
| HAProxy VMs | 2 | Hardware-Abschreibung |
| Storage (NVMe) | 1.5 TB | Hardware-Abschreibung |
| **Gesamt** | **8 VMs** | Nur Hardware + Strom |

---

## 12. Timeline

| Phase | Dauer | Meilenstein |
|-------|-------|-------------|
| Planung | 1 Woche | Architektur finalisiert |
| Infrastruktur | 1 Woche | VMs provisioniert |
| etcd Cluster | 2 Tage | DCS läuft |
| Patroni Setup | 3 Tage | Primary + Replicas |
| HAProxy | 1 Tag | Load Balancing aktiv |
| Migration | 1 Tag | Daten migriert |
| Testing | 3 Tage | Failover-Tests bestanden |
| Go-Live | 1 Tag | Production-Umstellung |

**Geschätzte Gesamtdauer:** 3-4 Wochen

---

## 13. Änderungshistorie

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0 | 2025-12-18 | Initiale Planung |
