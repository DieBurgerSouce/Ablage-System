# Deployment Guide - Ablage-System OCR

> Production Deployment Anleitung fuer On-Premises Enterprise-Umgebungen

## Voraussetzungen

### Hardware-Anforderungen

| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| CPU | 8 Cores | 16+ Cores |
| RAM | 32 GB | 64 GB |
| GPU | RTX 3080 (10GB) | RTX 4080 (16GB) |
| Storage | 500 GB SSD | 1 TB NVMe |
| Network | 1 Gbps | 10 Gbps |

### Software-Anforderungen

- Ubuntu 22.04 LTS (Server)
- Docker 24.x + Docker Compose 2.x
- NVIDIA Driver 535+ mit CUDA 12.x
- Git 2.40+

### Netzwerk-Ports

| Port | Service | Beschreibung |
|------|---------|--------------|
| 80 | Nginx | HTTP (Redirect zu HTTPS) |
| 443 | Nginx | HTTPS |
| 8000 | Backend | FastAPI (intern) |
| 5433 | PostgreSQL | Datenbank (intern) |
| 6380 | Redis | Cache/Queue (intern) |
| 9000 | MinIO | Object Storage (intern) |
| 9001 | MinIO Console | Admin UI |
| 3000 | Grafana | Monitoring Dashboard |
| 9090 | Prometheus | Metrics (intern) |

---

## Deployment-Optionen

### Option 1: Docker Compose (Empfohlen)

Fuer Single-Server Deployments mit bis zu 1000 Dokumenten/Tag.

### Option 2: Kubernetes (K3s)

Fuer Multi-Node Deployments mit hoher Verfuegbarkeit.

### Option 3: Ansible Automation

Fuer wiederholbare, versionierte Deployments.

---

## Docker Compose Deployment

### Schritt 1: Server vorbereiten

```bash
# System aktualisieren
sudo apt update && sudo apt upgrade -y

# Docker installieren
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose installieren
sudo apt install docker-compose-plugin

# NVIDIA Container Toolkit installieren
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# GPU verifizieren
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### Schritt 2: Repository klonen

```bash
cd /opt
sudo git clone https://github.com/your-org/ablage-system.git
sudo chown -R $USER:$USER ablage-system
cd ablage-system
```

### Schritt 3: Umgebungsvariablen konfigurieren

```bash
# .env aus Template erstellen
cp .env.example .env

# .env editieren
nano .env
```

**Wichtige Variablen:**

```bash
# Security (MUSS geaendert werden!)
SECRET_KEY=<generieren: openssl rand -hex 32>
DATABASE_PASSWORD=<sicheres Passwort>
REDIS_PASSWORD=<sicheres Passwort>
MINIO_ROOT_PASSWORD=<sicheres Passwort>

# Domain
DOMAIN=ablage-system.example.com
ALLOWED_HOSTS=ablage-system.example.com

# GPU
GPU_ENABLED=true
MAX_GPU_MEMORY_PERCENT=85

# Email (optional)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=notifications@example.com
SMTP_PASSWORD=<smtp Passwort>
```

### Schritt 4: SSL-Zertifikate

**Option A: Let's Encrypt (Internet-Zugang erforderlich)**

```bash
# Certbot installieren
sudo apt install certbot

# Zertifikat erstellen
sudo certbot certonly --standalone -d ablage-system.example.com

# Zertifikate kopieren
sudo cp /etc/letsencrypt/live/ablage-system.example.com/fullchain.pem infrastructure/nginx/certs/
sudo cp /etc/letsencrypt/live/ablage-system.example.com/privkey.pem infrastructure/nginx/certs/
```

**Option B: Self-Signed (Intranet)**

```bash
# Selbstsigniertes Zertifikat erstellen
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout infrastructure/nginx/certs/privkey.pem \
  -out infrastructure/nginx/certs/fullchain.pem \
  -subj "/CN=ablage-system.example.com"
```

### Schritt 5: Services starten

```bash
# Alle Services starten
docker compose up -d

# Logs pruefen
docker compose logs -f backend worker

# Health Check
curl -f http://localhost:8000/health
```

### Schritt 6: Datenbank initialisieren

```bash
# Migrationen ausfuehren
docker compose exec backend alembic upgrade head

# Admin-User erstellen
docker compose exec backend python -m app.scripts.create_admin \
  --email admin@example.com \
  --password <sicheres Passwort>
```

### Schritt 7: Verifizieren

```bash
# API Health
curl https://ablage-system.example.com/api/v1/health

# Frontend
curl https://ablage-system.example.com/

# Grafana (admin/admin beim ersten Login)
curl https://ablage-system.example.com:3000/
```

---

## Ansible Deployment

Fuer automatisierte, wiederholbare Deployments.

### Schritt 1: Inventory konfigurieren

```bash
cd infrastructure/ansible
cp inventories/production/hosts.example inventories/production/hosts
nano inventories/production/hosts
```

```ini
[ablage_servers]
ablage-prod-01 ansible_host=192.168.1.100 ansible_user=deploy

[ablage_servers:vars]
ansible_python_interpreter=/usr/bin/python3
domain=ablage-system.example.com
```

### Schritt 2: Vault-Secrets konfigurieren

```bash
# Vault-Passwort erstellen
echo "your-vault-password" > ~/.ansible-vault-pass
chmod 600 ~/.ansible-vault-pass

# Secrets verschluesseln
ansible-vault encrypt inventories/production/group_vars/all/vault.yml
```

### Schritt 3: Deployment ausfuehren

```bash
# Dry-Run (Check Mode)
ansible-playbook -i inventories/production playbooks/deploy.yml --check

# Tatsaechliches Deployment
ansible-playbook -i inventories/production playbooks/deploy.yml
```

### Deployment-Phasen

| Phase | Beschreibung |
|-------|--------------|
| provision | Server-Grundkonfiguration |
| docker | Docker + NVIDIA Runtime |
| ssl | SSL-Zertifikate |
| deploy | Anwendung deployen |
| monitoring | Prometheus + Grafana |
| backup | Backup-Jobs konfigurieren |

---

## Kubernetes (K3s) Deployment

Fuer Multi-Node Deployments mit hoher Verfuegbarkeit.

### Schritt 1: K3s installieren

```bash
# Master Node
curl -sfL https://get.k3s.io | sh -s - --disable traefik

# Worker Nodes
curl -sfL https://get.k3s.io | K3S_URL=https://<master-ip>:6443 \
  K3S_TOKEN=<node-token> sh -
```

### Schritt 2: NVIDIA Device Plugin

```bash
# NVIDIA Operator installieren
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml
```

### Schritt 3: Helm Charts deployen

```bash
cd infrastructure/kubernetes

# Secrets erstellen
kubectl create secret generic ablage-secrets \
  --from-literal=database-password=<password> \
  --from-literal=redis-password=<password> \
  --from-literal=secret-key=<key>

# Helm Release installieren
helm install ablage ./charts/ablage-system \
  --namespace ablage \
  --create-namespace \
  --values values.production.yaml
```

---

## Updates & Upgrades

### Rolling Update (Zero-Downtime)

```bash
# Neue Version pullen
git pull origin main

# Images neu bauen
docker compose build

# Rolling Update
docker compose up -d --no-deps --scale backend=2 backend
sleep 30
docker compose up -d --no-deps --scale backend=1 backend
```

### Blue-Green Deployment

```bash
# Siehe deploy.yml GitHub Action fuer automatisiertes Blue-Green
gh workflow run deploy.yml -f environment=production -f version=v2.0.0
```

### Canary Deployment

```bash
# Siehe canary-deploy.yml GitHub Action
gh workflow run "Canary Deploy" -f version=v2.0.0
```

---

## Backup & Recovery

### Automatische Backups

Backups werden automatisch erstellt:
- **Taeglich 02:30 UTC**: Vollstaendiges Backup
- **Sonntag 03:00 UTC**: Retention Policy (alte Backups loeschen)
- **Taeglich 04:00 UTC**: Remote-Sync (falls konfiguriert)

### Manuelles Backup

```bash
# Vollstaendiges Backup
docker compose exec backend ./scripts/backup.sh all

# Nur PostgreSQL
docker compose exec backend ./scripts/backup.sh db

# Backup-Liste anzeigen
ls -la /opt/ablage-system/backups/
```

### Restore

```bash
# Restore aus Backup
docker compose exec backend ./scripts/restore.sh all backups/backup_full_20241201.tar.gz

# Nur PostgreSQL wiederherstellen
docker compose exec backend ./scripts/restore.sh db backups/postgres_20241201.sql.gz
```

### Disaster Recovery

| RTO | RPO | Beschreibung |
|-----|-----|--------------|
| 4 Stunden | 24 Stunden | Standard (Backup-Restore) |
| 1 Stunde | 1 Stunde | Mit Streaming Replication |
| 15 Minuten | 0 | Mit Hot-Standby + WAL Shipping |

---

## Monitoring

### Grafana Dashboards

Zugriff: `https://ablage-system.example.com:3000/`

| Dashboard | Beschreibung |
|-----------|--------------|
| Ablage Overview | System-Ueberblick |
| OCR Performance | OCR-Metriken, Latenz |
| GPU Monitoring | VRAM, Temperatur, Auslastung |
| ML Routing | Drift Detection, A/B Tests |
| Backup Status | Backup-Erfolg/Fehler |

### Alerts konfigurieren

```bash
# Alert Rules sind in infrastructure/prometheus/rules/ definiert
# Alertmanager-Config: infrastructure/prometheus/alertmanager.yml

# Slack Webhook hinzufuegen
nano infrastructure/prometheus/alertmanager.yml
```

```yaml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/xxx'
        channel: '#alerts'
```

---

## Troubleshooting

### GPU nicht erkannt

```bash
# NVIDIA Driver pruefen
nvidia-smi

# Docker GPU Test
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Container neu starten
docker compose restart worker
```

### Out of Memory (OOM)

```bash
# VRAM pruefen
nvidia-smi

# Batch-Size reduzieren in .env
MAX_BATCH_SIZE=4
MAX_GPU_MEMORY_PERCENT=75

# Worker neu starten
docker compose restart worker
```

### Datenbank-Verbindungsprobleme

```bash
# PostgreSQL-Status
docker compose exec postgres pg_isready

# Verbindung testen
docker compose exec backend python -c "
from app.db.session import engine
print(engine.connect())
"
```

### Langsame OCR-Verarbeitung

```bash
# GPU-Auslastung pruefen
nvidia-smi -l 1

# Worker-Logs pruefen
docker compose logs -f worker

# Queue-Status
docker compose exec backend celery -A app.workers.celery_app inspect active
```

---

## Sicherheits-Checkliste

- [ ] Alle Standard-Passwoerter geaendert
- [ ] SSL/TLS aktiviert (keine selbstsignierten Zertifikate in Production)
- [ ] Firewall konfiguriert (nur 80, 443 extern)
- [ ] SSH Key-basierte Authentifizierung
- [ ] Regelmaeessige Backups verifiziert
- [ ] Monitoring-Alerts konfiguriert
- [ ] Log-Rotation aktiviert
- [ ] Updates-Strategie definiert

---

## Support & Kontakt

- **Dokumentation**: [CLAUDE.md](./CLAUDE.md)
- **API-Referenz**: [API_REFERENCE.md](./API_REFERENCE.md)
- **Issues**: https://github.com/your-org/ablage-system/issues

---

*Version: 1.0 | Letzte Aktualisierung: 2024-12*
