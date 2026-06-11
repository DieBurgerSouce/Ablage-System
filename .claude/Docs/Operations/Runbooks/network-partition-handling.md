# Runbook: Network Partition Handling

> Diagnose und Recovery bei Netzwerkproblemen zwischen Containern

## Uebersicht

| Metrik | Wert |
|--------|------|
| Severity | HIGH |
| RTO | 10 Minuten |
| RPO | N/A |
| On-Call | Infrastructure Team |

## Symptome

- Services koennen sich nicht erreichen
- Intermittierende Verbindungsabbrueche
- DNS-Aufloesung schlaegt fehl
- Timeouts bei Service-Kommunikation

## Docker-Netzwerk-Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    frontend-network                          │
│  nginx ←→ backend                                           │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    backend-network                           │
│  backend ←→ worker ←→ redis                                 │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      data-network                            │
│  backend ←→ postgres ←→ minio                               │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   monitoring-network                         │
│  prometheus ←→ grafana ←→ loki                              │
└─────────────────────────────────────────────────────────────┘
```

## Diagnose

### 1. Netzwerk-Status pruefen

```bash
# Alle Docker-Netzwerke
docker network ls

# Netzwerk-Details
docker network inspect ablage_backend-network
docker network inspect ablage_data-network
docker network inspect ablage_frontend-network

# Container-Netzwerke
docker inspect --format='{{range .NetworkSettings.Networks}}{{.NetworkID}} {{.IPAddress}}{{end}}' ablage-backend
```

### 2. Verbindung zwischen Containern testen

```bash
# Von Backend zu Redis
docker compose exec backend ping -c 3 redis

# Von Backend zu PostgreSQL
docker compose exec backend ping -c 3 postgres

# Von Backend zu MinIO
docker compose exec backend ping -c 3 minio

# DNS-Aufloesung
docker compose exec backend nslookup redis
```

### 3. Ports pruefen

```bash
# Offene Ports in Container
docker compose exec backend netstat -tlnp

# Port-Erreichbarkeit
docker compose exec backend nc -zv redis 6379
docker compose exec backend nc -zv postgres 5432
docker compose exec backend nc -zv minio 9000
```

### 4. Haeufige Fehler

| Fehler | Ursache |
|--------|---------|
| `No route to host` | Netzwerk nicht verbunden |
| `Name resolution failed` | DNS-Problem |
| `Connection timed out` | Firewall oder Netzwerk-Partition |
| `Connection refused` | Service nicht gestartet |

## Recovery-Schritte

### Fall 1: Container nicht im Netzwerk

```bash
# Container zu Netzwerk hinzufuegen
docker network connect ablage_backend-network ablage-backend
docker network connect ablage_data-network ablage-backend

# Verifizieren
docker inspect --format='{{json .NetworkSettings.Networks}}' ablage-backend | jq
```

### Fall 2: Netzwerk korrupt

```bash
# Alle Container stoppen
docker compose down

# Netzwerke loeschen
docker network rm ablage_frontend-network ablage_backend-network ablage_data-network ablage_monitoring-network

# Netzwerke und Container neu erstellen
docker compose up -d
```

### Fall 3: DNS-Problem

```bash
# DNS-Cache in Container leeren (Container neu starten)
docker compose restart backend worker

# Falls systemweit:
sudo systemctl restart docker

# Oder: Explizite Hosts verwenden
# In docker-compose.yml:
# extra_hosts:
#   - "redis:172.20.0.2"
```

### Fall 4: IP-Konflikt

```bash
# IP-Adressen pruefen
docker network inspect ablage_backend-network | jq '.[0].Containers'

# Bei Konflikt: Netzwerk mit festem Subnet neu erstellen
docker network create \
  --driver bridge \
  --subnet 172.25.0.0/16 \
  --gateway 172.25.0.1 \
  ablage_backend-network
```

### Fall 5: Firewall blockiert

```bash
# UFW-Status pruefen
sudo ufw status

# Docker-Ports erlauben
sudo ufw allow from 172.16.0.0/12 to any

# iptables pruefen
sudo iptables -L -n | grep DOCKER
```

## Host-Netzwerk-Probleme

### DNS-Server nicht erreichbar

```bash
# DNS-Server in Docker-Daemon konfigurieren
# /etc/docker/daemon.json:
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}

# Docker-Daemon neu starten
sudo systemctl restart docker
```

### MTU-Probleme

```bash
# MTU pruefen
docker network inspect ablage_backend-network | grep -i mtu

# MTU in docker-compose.yml setzen:
# networks:
#   backend-network:
#     driver_opts:
#       com.docker.network.driver.mtu: 1400
```

## Verifizierung

Nach Recovery:

```bash
# 1. Netzwerk-Verbindungen
docker compose exec backend ping -c 1 redis
docker compose exec backend ping -c 1 postgres
docker compose exec backend ping -c 1 minio

# 2. Service-Erreichbarkeit
docker compose exec backend curl -s http://redis:6379 || echo "Redis OK"
docker compose exec backend curl -s http://minio:9000/minio/health/live

# 3. API-Health
curl http://localhost:8000/health/detailed

# 4. Alle Services testen
docker compose exec backend python -c "
from app.db.session import engine
from app.core.redis_client import redis_client
print('DB:', engine.connect())
print('Redis:', redis_client.ping())
"
```

## Debugging-Tools

### tcpdump

```bash
# Traffic auf Interface mitschneiden
docker run --rm --net=host -v /tmp:/tmp nicolaka/netshoot \
  tcpdump -i docker0 -w /tmp/docker.pcap
```

### netshoot Container

```bash
# Debugging-Container starten
docker run -it --rm --network ablage_backend-network nicolaka/netshoot

# Dann im Container:
ping redis
traceroute postgres
nmap -p 5432 postgres
```

## Eskalation

| Zeit | Aktion |
|------|--------|
| 5 min | Netzwerk-Diagnose |
| 10 min | Eskalation an Infrastructure Lead |
| 30 min | Eskalation an CTO |

## Praevention

- Netzwerke in docker-compose.yml explizit definieren
- Health-Checks fuer alle Services
- Network Policies (Kubernetes)
- Monitoring von Netzwerk-Latenzen
- Regelmaessige Netzwerk-Tests

---

*Letzte Aktualisierung: 2024-12*
