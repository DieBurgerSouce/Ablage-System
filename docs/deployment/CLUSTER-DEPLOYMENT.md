# Cluster Deployment Guide

> **Version**: 1.0
> **Letzte Aktualisierung**: 2026-01-21
> **Zielumgebung**: On-Premises Cluster (2-3 Nodes)

---

## Uebersicht

Diese Anleitung beschreibt das Deployment des Ablage-Systems als hochverfuegbaren Cluster mit 2-3 Nodes. Die Architektur bietet:

- **High Availability**: Automatisches Failover bei Node-Ausfall
- **Load Balancing**: Verteilung der Last auf mehrere API-Server
- **Datenbankreplikation**: PostgreSQL mit Patroni fuer HA
- **Redis Sentinel**: Redis-Cluster mit automatischem Failover
- **GPU-Isolation**: Dedizierte GPU-Nodes fuer OCR-Workloads

---

## Architektur

```
                    ┌─────────────────────┐
                    │      HAProxy        │
                    │   Load Balancer     │
                    │   (Port 80, 443)    │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│    Node 1     │      │    Node 2     │      │    Node 3     │
│ ───────────── │      │ ───────────── │      │ ───────────── │
│  FastAPI      │      │  FastAPI      │      │  FastAPI      │
│  Celery Beat  │      │  Celery       │      │  Celery (GPU) │
│  Redis        │◄────►│  Redis        │◄────►│  Redis        │
│  (Sentinel)   │      │  (Sentinel)   │      │  (Sentinel)   │
│  PostgreSQL   │◄────►│  PostgreSQL   │      │  MinIO        │
│  (Primary)    │      │  (Replica)    │      │               │
└───────────────┘      └───────────────┘      └───────────────┘
        │                      │                      │
        └──────────────────────┴──────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Shared Storage    │
                    │   (NFS/GlusterFS)   │
                    └─────────────────────┘
```

---

## Hardware-Anforderungen

### Minimum (2 Nodes)

| Node | CPU | RAM | GPU | Speicher | Rolle |
|------|-----|-----|-----|----------|-------|
| Node 1 | 8 Cores | 32 GB | - | 500 GB SSD | API, DB Primary, Redis |
| Node 2 | 8 Cores | 32 GB | RTX 3080+ | 500 GB SSD | API, DB Replica, Worker GPU |

### Empfohlen (3 Nodes)

| Node | CPU | RAM | GPU | Speicher | Rolle |
|------|-----|-----|-----|----------|-------|
| Node 1 | 16 Cores | 64 GB | - | 1 TB NVMe | API, DB Primary, Redis Master |
| Node 2 | 16 Cores | 64 GB | - | 1 TB NVMe | API, DB Replica, Redis Replica |
| Node 3 | 8 Cores | 32 GB | RTX 4080 | 500 GB SSD | Worker GPU, MinIO |

### Netzwerk

- **Interne Kommunikation**: 10 Gbit empfohlen, 1 Gbit minimum
- **Latenz**: <1ms zwischen Nodes
- **Firewall**: Ports 5432, 6379, 26379, 8000, 9000 intern offen

---

## Voraussetzungen

### Auf allen Nodes

```bash
# Ubuntu 22.04 LTS
sudo apt update && sudo apt upgrade -y

# Docker installieren
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose v2
sudo apt install docker-compose-plugin

# Node 3: NVIDIA Driver + Container Toolkit
# Siehe: docs/deployment/GPU-SETUP.md
```

### Netzwerk-Konfiguration

```bash
# /etc/hosts auf allen Nodes
192.168.1.10  node1.ablage.local  node1
192.168.1.11  node2.ablage.local  node2
192.168.1.12  node3.ablage.local  node3
192.168.1.100 ablage.company.local  # VIP fuer HAProxy
```

---

## Installation

### 1. Repository auf allen Nodes klonen

```bash
git clone https://github.com/company/ablage-system.git /opt/ablage-system
cd /opt/ablage-system
```

### 2. Umgebungsvariablen konfigurieren

```bash
# Auf jedem Node
cp .env.cluster.example .env

# Anpassen:
nano .env
```

**Node-spezifische Variablen:**

```bash
# Node 1
NODE_ID=node1
NODE_ROLE=primary
POSTGRES_MODE=primary
REDIS_ROLE=master

# Node 2
NODE_ID=node2
NODE_ROLE=replica
POSTGRES_MODE=replica
REDIS_ROLE=slave

# Node 3
NODE_ID=node3
NODE_ROLE=worker
GPU_ENABLED=true
```

### 3. Shared Storage einrichten

```bash
# Option A: NFS (einfacher)
# Auf Node 1 (NFS Server)
sudo apt install nfs-kernel-server
sudo mkdir -p /srv/ablage-shared/{uploads,exports,models}
echo "/srv/ablage-shared 192.168.1.0/24(rw,sync,no_subtree_check)" | sudo tee -a /etc/exports
sudo exportfs -ra

# Auf Node 2 und 3 (NFS Clients)
sudo apt install nfs-common
sudo mkdir -p /opt/ablage-system/shared
sudo mount -t nfs node1:/srv/ablage-shared /opt/ablage-system/shared
# Fuer permanentes Mount: /etc/fstab anpassen
```

### 4. Cluster starten

```bash
# Node 1 zuerst (PostgreSQL Primary + Redis Master)
docker-compose -f docker-compose.cluster.yml --profile node1 up -d

# Warten bis PostgreSQL und Redis bereit sind
sleep 30

# Node 2 (PostgreSQL Replica + Redis Slave)
docker-compose -f docker-compose.cluster.yml --profile node2 up -d

# Node 3 (GPU Worker)
docker-compose -f docker-compose.cluster.yml --profile node3 up -d
```

### 5. HAProxy konfigurieren

HAProxy kann auf einem separaten Server oder auf Node 1 laufen.

```bash
# HAProxy installieren
sudo apt install haproxy

# Konfiguration kopieren
sudo cp infrastructure/cluster/haproxy.cfg /etc/haproxy/haproxy.cfg

# Starten
sudo systemctl enable haproxy
sudo systemctl start haproxy
```

### 6. Datenbank initialisieren

```bash
# Auf Node 1
docker-compose -f docker-compose.cluster.yml exec backend alembic upgrade head
docker-compose -f docker-compose.cluster.yml exec backend python -m app.scripts.create_admin
```

---

## Komponenten-Details

### PostgreSQL mit Patroni

Patroni verwaltet das automatische Failover der PostgreSQL-Cluster.

**Funktionsweise:**
1. Patroni ueberwacht den Primary-Node
2. Bei Ausfall waehlt Patroni automatisch einen neuen Primary
3. Replicas werden automatisch neu konfiguriert

**Konfiguration:** `infrastructure/cluster/patroni.yml`

```yaml
scope: ablage-cluster
name: ${NODE_ID}

restapi:
  listen: 0.0.0.0:8008
  connect_address: ${NODE_IP}:8008

etcd3:
  hosts:
    - node1:2379
    - node2:2379
    - node3:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      parameters:
        max_connections: 200
        shared_buffers: 4GB
        effective_cache_size: 12GB
        maintenance_work_mem: 1GB
        checkpoint_completion_target: 0.9
        wal_buffers: 64MB
        default_statistics_target: 100
        random_page_cost: 1.1
        effective_io_concurrency: 200
        work_mem: 20MB
        min_wal_size: 2GB
        max_wal_size: 8GB
        max_worker_processes: 8
        max_parallel_workers_per_gather: 4
        max_parallel_workers: 8
        max_parallel_maintenance_workers: 4

  initdb:
    - encoding: UTF8
    - data-checksums

postgresql:
  listen: 0.0.0.0:5432
  connect_address: ${NODE_IP}:5432
  data_dir: /var/lib/postgresql/data
  authentication:
    replication:
      username: replicator
      password: ${REPLICATION_PASSWORD}
    superuser:
      username: postgres
      password: ${POSTGRES_PASSWORD}
```

### Redis Sentinel

Redis Sentinel bietet automatisches Failover fuer Redis.

**Konfiguration:** `infrastructure/cluster/sentinel.conf`

```conf
# Sentinel-Konfiguration
port 26379
sentinel monitor ablage-redis node1 6379 2
sentinel auth-pass ablage-redis ${REDIS_PASSWORD}
sentinel down-after-milliseconds ablage-redis 5000
sentinel failover-timeout ablage-redis 60000
sentinel parallel-syncs ablage-redis 1
```

**Anwendung verbinden:**

```python
# app/core/config.py
REDIS_SENTINELS = [
    ("node1", 26379),
    ("node2", 26379),
    ("node3", 26379),
]
REDIS_MASTER_NAME = "ablage-redis"
```

### HAProxy Load Balancer

**Konfiguration:** `infrastructure/cluster/haproxy.cfg`

```cfg
global
    log /dev/log local0
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy
    daemon

defaults
    log global
    mode http
    option httplog
    option dontlognull
    timeout connect 5000
    timeout client  50000
    timeout server  50000

# Frontend fuer HTTPS
frontend https_front
    bind *:443 ssl crt /etc/haproxy/certs/ablage.pem
    http-request add-header X-Forwarded-Proto https
    default_backend api_servers

# Frontend fuer HTTP (Redirect zu HTTPS)
frontend http_front
    bind *:80
    redirect scheme https code 301

# Backend API Server
backend api_servers
    balance roundrobin
    option httpchk GET /api/v1/health
    http-check expect status 200

    server node1 192.168.1.10:8000 check inter 5s fall 3 rise 2
    server node2 192.168.1.11:8000 check inter 5s fall 3 rise 2

# Backend fuer MinIO
backend minio_servers
    balance roundrobin
    option httpchk GET /minio/health/live

    server node3 192.168.1.12:9000 check

# Stats-Seite
listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 10s
    stats admin if LOCALHOST
```

---

## Failover-Szenarien

### PostgreSQL Primary faellt aus

1. Patroni erkennt Ausfall (nach 30s)
2. Patroni waehlt Replica als neuen Primary
3. Anwendung verbindet sich automatisch neu
4. **Downtime**: ~30-60 Sekunden

**Manuelles Failover:**
```bash
patronictl -c /etc/patroni/config.yml switchover
```

### Redis Master faellt aus

1. Sentinel erkennt Ausfall (nach 5s)
2. Sentinel waehlt neuen Master
3. Anwendung verbindet sich ueber Sentinel neu
4. **Downtime**: ~5-10 Sekunden

### API-Node faellt aus

1. HAProxy Health-Check schlaegt fehl (3x)
2. HAProxy entfernt Node aus Pool
3. Traffic wird auf verbleibende Nodes verteilt
4. **Downtime**: 0 (keine Unterbrechung)

---

## Monitoring

### Prometheus Targets

```yaml
# infrastructure/prometheus/prometheus-cluster.yml
scrape_configs:
  - job_name: 'ablage-api'
    static_configs:
      - targets:
        - 'node1:8000'
        - 'node2:8000'

  - job_name: 'postgres'
    static_configs:
      - targets:
        - 'node1:9187'  # postgres_exporter
        - 'node2:9187'

  - job_name: 'redis'
    static_configs:
      - targets:
        - 'node1:9121'  # redis_exporter
        - 'node2:9121'
        - 'node3:9121'

  - job_name: 'haproxy'
    static_configs:
      - targets:
        - 'haproxy:8404'

  - job_name: 'patroni'
    static_configs:
      - targets:
        - 'node1:8008'
        - 'node2:8008'
```

### Grafana Dashboards

Vorkonfigurierte Dashboards:
- **Cluster Overview**: Alle Nodes auf einen Blick
- **PostgreSQL Replication**: Lag, Connections, Transactions
- **Redis Sentinel**: Master/Slave Status, Failovers
- **HAProxy**: Request Rate, Response Times, Backend Health

---

## Backup-Strategie

### PostgreSQL

```bash
# Auf Primary-Node (automatisch via cron)
pg_basebackup -h localhost -U replicator -D /backups/pg_backup_$(date +%Y%m%d) -Fp -Xs -P

# WAL-Archivierung fuer Point-in-Time Recovery
archive_mode = on
archive_command = 'cp %p /backups/wal_archive/%f'
```

### Redis

```bash
# RDB Snapshots (automatisch)
save 900 1
save 300 10
save 60 10000

# AOF fuer maximale Datensicherheit
appendonly yes
appendfsync everysec
```

### MinIO

```bash
# mc mirror fuer Replikation
mc mirror --watch /data/minio backup-server/minio-backup
```

---

## Skalierung

### Horizontal (mehr Nodes)

```bash
# Node 4 hinzufuegen (weiterer API-Server)
# 1. Docker installieren
# 2. Repository klonen
# 3. .env konfigurieren (NODE_ID=node4, NODE_ROLE=api)
# 4. docker-compose starten
# 5. In HAProxy-Config aufnehmen
```

### Vertikal (mehr Ressourcen)

```bash
# docker-compose.cluster.yml anpassen
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 16G
```

---

## Troubleshooting

### Patroni-Status pruefen

```bash
patronictl -c /etc/patroni/config.yml list

# Erwartete Ausgabe:
# +--------+--------+-----------+--------+---------+----+-----------+
# | Member | Host   | Role      | State  | TL      | Lag in MB    |
# +--------+--------+-----------+--------+---------+----+-----------+
# | node1  | node1  | Leader    | running | 5      | 0           |
# | node2  | node2  | Replica   | running | 5      | 0           |
# +--------+--------+-----------+--------+---------+----+-----------+
```

### Redis Sentinel-Status

```bash
redis-cli -p 26379 sentinel master ablage-redis
redis-cli -p 26379 sentinel slaves ablage-redis
redis-cli -p 26379 sentinel sentinels ablage-redis
```

### HAProxy-Status

```bash
# Stats-Seite
curl http://localhost:8404/stats

# Socket-Befehle
echo "show servers state" | socat stdio /run/haproxy/admin.sock
```

### Split-Brain verhindern

```bash
# etcd-Cluster fuer Patroni (3 Nodes empfohlen)
# Bei 2 Nodes: Quorum-Device einsetzen

# In patroni.yml:
postgresql:
  parameters:
    synchronous_commit: remote_apply
    synchronous_standby_names: '*'
```

---

## Checkliste vor Produktivbetrieb

- [ ] Alle Nodes erreichbar (ping, ssh)
- [ ] Docker auf allen Nodes installiert
- [ ] Shared Storage gemountet
- [ ] PostgreSQL-Replikation aktiv (`pg_stat_replication`)
- [ ] Redis Sentinel funktioniert (`sentinel master`)
- [ ] HAProxy Health-Checks gruen
- [ ] SSL-Zertifikate installiert
- [ ] Firewall-Regeln konfiguriert
- [ ] Backup-Jobs eingerichtet
- [ ] Monitoring aktiv (Grafana erreichbar)
- [ ] Failover getestet (Node manuell stoppen)
- [ ] Disaster Recovery dokumentiert

---

## Support

Bei Problemen:
1. Logs sammeln: `./scripts/collect_cluster_logs.sh`
2. Patroni-Status pruefen
3. Redis Sentinel-Status pruefen
4. HAProxy-Logs analysieren

---

*Erstellt fuer Ablage-System Phase 10: On-Premises Excellence*
