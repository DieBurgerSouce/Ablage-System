# Air-Gapped Installation Guide

> **Version**: 1.0
> **Letzte Aktualisierung**: 2026-01-21
> **Zielumgebung**: Vollstaendig isolierte Netzwerke ohne Internetzugang

---

## Uebersicht

Diese Anleitung beschreibt die Installation des Ablage-Systems in einer vollstaendig isolierten Umgebung (Air-Gapped) ohne Internetzugang. Dies ist erforderlich fuer:

- Hochsicherheitsumgebungen
- Behoerdliche Anforderungen
- Kritische Infrastruktur
- Datenschutz-sensible Bereiche

---

## Voraussetzungen

### Hardware-Anforderungen

| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| CPU | 8 Cores | 16 Cores |
| RAM | 32 GB | 64 GB |
| GPU | RTX 3080 (10GB) | RTX 4080 (16GB) |
| Speicher (System) | 100 GB SSD | 500 GB NVMe |
| Speicher (Daten) | 500 GB | 2 TB |
| Netzwerk | 1 Gbit | 10 Gbit |

### Software-Anforderungen (Zielserver)

- Ubuntu Server 22.04 LTS oder RHEL 8.x/9.x
- Docker 24.x oder neuer
- Docker Compose v2.20+
- NVIDIA Driver 535+ (fuer GPU)
- NVIDIA Container Toolkit

---

## Vorbereitung (Online-System)

Die Vorbereitung erfolgt auf einem System MIT Internetzugang.

### 1. Repository klonen

```bash
git clone https://github.com/company/ablage-system.git
cd ablage-system
```

### 2. Offline-Paket erstellen

```bash
# Skript ausfuehren (erfordert Docker + Internet)
./scripts/air-gapped/prepare_offline_package.sh

# Ausgabe: ablage-system-offline-YYYYMMDD.tar.gz (~15-25 GB)
```

### 3. Paket-Inhalt

Das Offline-Paket enthaelt:

| Komponente | Beschreibung | Groesse |
|------------|--------------|---------|
| Docker Images | Alle Container-Images | ~8 GB |
| Python Wheels | Backend-Dependencies | ~500 MB |
| NPM Packages | Frontend-Dependencies | ~300 MB |
| ML Models | OCR + Embedding Models | ~12 GB |
| Config Templates | Konfigurationsdateien | ~1 MB |
| Scripts | Installations-Skripte | ~50 KB |

### 4. ML-Modelle

Folgende Modelle werden offline gebuendelt:

```
models/
├── deepseek-janus-pro-7b/      # DeepSeek OCR (~7 GB)
├── got-ocr-2.0/                # GOT-OCR (~4 GB)
├── surya/                      # Surya OCR (~500 MB)
├── sentence-transformers/      # Embeddings (~400 MB)
│   └── paraphrase-multilingual-MiniLM-L12-v2/
└── spacy/                      # German NLP (~200 MB)
    └── de_core_news_lg/
```

---

## Transfer zum Air-Gapped System

### Option A: Physischer Transfer

```bash
# Auf USB-Laufwerk kopieren
cp ablage-system-offline-YYYYMMDD.tar.gz /media/usb-drive/

# Checksumme erstellen
sha256sum ablage-system-offline-YYYYMMDD.tar.gz > checksums.sha256
```

### Option B: Data Diode (Einweg-Transfer)

Fuer hochsichere Umgebungen mit Data-Diode:

1. Datei in Chunks aufteilen: `split -b 1G archive.tar.gz archive_part_`
2. Ueber Data-Diode uebertragen
3. Auf Zielseite zusammenfuegen: `cat archive_part_* > archive.tar.gz`

### Checksumme verifizieren

```bash
sha256sum -c checksums.sha256
# Erwartete Ausgabe: ablage-system-offline-YYYYMMDD.tar.gz: OK
```

---

## Installation (Air-Gapped System)

### 1. Paket entpacken

```bash
mkdir -p /opt/ablage-system
cd /opt/ablage-system
tar -xzf /path/to/ablage-system-offline-YYYYMMDD.tar.gz
```

### 2. Docker-Images laden

```bash
# Alle Images importieren
./scripts/air-gapped/load_docker_images.sh

# Verifizieren
docker images | grep ablage
```

### 3. ML-Modelle installieren

```bash
# Modelle in Zielverzeichnis kopieren
./scripts/air-gapped/install_models.sh

# Standard-Pfad: /opt/ablage-system/models/
# Alternativ: Pfad in .env konfigurieren
```

### 4. Konfiguration erstellen

```bash
# Template kopieren
cp .env.airgap.example .env

# Anpassen (Editor oeffnen)
nano .env
```

**Wichtige Einstellungen:**

```bash
# Netzwerk
EXTERNAL_HOST=ablage.internal.company.local
ALLOWED_HOSTS=ablage.internal.company.local,localhost

# Datenbank
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_PASSWORD=<STARKES_PASSWORT>

# Redis
REDIS_HOST=localhost
REDIS_PORT=6380

# Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=<ACCESS_KEY>
MINIO_SECRET_KEY=<SECRET_KEY>

# GPU
CUDA_VISIBLE_DEVICES=0
GPU_MEMORY_FRACTION=0.85

# Models (Offline-Pfade)
DEEPSEEK_MODEL_PATH=/opt/ablage-system/models/deepseek-janus-pro-7b
GOT_OCR_MODEL_PATH=/opt/ablage-system/models/got-ocr-2.0
SURYA_MODEL_PATH=/opt/ablage-system/models/surya
EMBEDDING_MODEL_PATH=/opt/ablage-system/models/sentence-transformers

# WICHTIG: Keine externen API-Aufrufe
DISABLE_EXTERNAL_APIS=true
OLLAMA_BASE_URL=http://localhost:11434
```

### 5. SSL-Zertifikate

Fuer Air-Gapped Umgebungen: Selbstsignierte oder interne CA-Zertifikate.

```bash
# Selbstsigniertes Zertifikat erstellen
./scripts/air-gapped/generate_ssl_cert.sh ablage.internal.company.local

# Oder: Interne CA-Zertifikate kopieren
cp /path/to/company-ca.crt ./infrastructure/ssl/
cp /path/to/ablage.crt ./infrastructure/ssl/
cp /path/to/ablage.key ./infrastructure/ssl/
```

### 6. System starten

```bash
# Mit Air-Gapped Compose-Datei starten
docker-compose -f docker-compose.airgap.yml up -d

# Logs pruefen
docker-compose -f docker-compose.airgap.yml logs -f
```

### 7. Initiale Einrichtung

```bash
# Datenbank initialisieren
docker-compose -f docker-compose.airgap.yml exec backend alembic upgrade head

# Admin-Benutzer erstellen
docker-compose -f docker-compose.airgap.yml exec backend python -m app.scripts.create_admin

# System-Health pruefen
curl -k https://ablage.internal.company.local/api/v1/health
```

---

## Offline-Updates

### Update-Paket erstellen (Online-System)

```bash
# Nur geaenderte Komponenten paketieren
./scripts/air-gapped/prepare_update_package.sh --from-version 1.0.0 --to-version 1.1.0

# Ausgabe: ablage-system-update-1.0.0-to-1.1.0.tar.gz
```

### Update installieren (Air-Gapped System)

```bash
# Backup erstellen (restic, siehe docs/runbooks/disaster-recovery.md §1)
bash scripts/backup/restic_backup.sh

# Update entpacken
tar -xzf ablage-system-update-1.0.0-to-1.1.0.tar.gz -C /opt/ablage-system/updates/

# Update ausfuehren
./scripts/air-gapped/apply_update.sh

# Bei Problemen: Rollback
./scripts/air-gapped/rollback_update.sh
```

---

## Troubleshooting

### Problem: Docker-Image nicht gefunden

```bash
# Images neu laden
docker load < images/ablage-backend.tar
docker load < images/ablage-frontend.tar
docker load < images/ablage-worker.tar

# Image-Tags pruefen
docker images | grep ablage
```

### Problem: GPU nicht erkannt

```bash
# NVIDIA-Treiber pruefen
nvidia-smi

# Container-Toolkit pruefen
docker run --rm --gpus all nvidia/cuda:12.1-base nvidia-smi

# Falls Fehler: NVIDIA Container Toolkit neu installieren
# (muss OFFLINE erfolgen - siehe offline-packages/nvidia/)
```

### Problem: ML-Modelle laden nicht

```bash
# Pfade pruefen
ls -la /opt/ablage-system/models/

# Berechtigungen korrigieren
chown -R 1000:1000 /opt/ablage-system/models/
chmod -R 755 /opt/ablage-system/models/

# Worker neu starten
docker-compose -f docker-compose.airgap.yml restart worker
```

### Problem: Zeitstempel-Synchronisation

Ohne Internet keine NTP-Synchronisation. Optionen:

1. **Lokaler NTP-Server**: Chrony/ntpd auf internem Server
2. **Manuelle Synchronisation**: `timedatectl set-time "2026-01-21 10:00:00"`
3. **GPS-basierte Zeit**: Fuer hochpraezise Anforderungen

```bash
# Chrony fuer lokales Netzwerk konfigurieren
cat > /etc/chrony/chrony.conf << EOF
server time.internal.company.local iburst
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
EOF

systemctl restart chronyd
```

---

## Sicherheitshinweise

### Daten-Handling

- **NIEMALS** Produktionsdaten auf Online-Systeme kopieren
- USB-Laufwerke nach Transfer sicher loeschen (DBAN/shred)
- Checksummen IMMER verifizieren vor Installation

### Netzwerk-Isolation

- Firewall-Regeln: Nur interne Netzwerke erlauben
- Keine Routing zum Internet konfigurieren
- DNS: Nur interne DNS-Server verwenden

### Audit-Logging

```bash
# Alle Aktionen werden protokolliert
tail -f /var/log/ablage-system/audit.log

# Logs exportieren (fuer externe Auditierung)
./scripts/export_audit_logs.sh --period=last-month
```

---

## Verifizierung

Nach der Installation:

```bash
# 1. System-Health
curl -k https://localhost/api/v1/health

# 2. GPU-Status
curl -k https://localhost/api/v1/health/gpu

# 3. OCR-Test
curl -k -X POST https://localhost/api/v1/ocr/test \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test-document.pdf"

# 4. Keine externen Verbindungen
ss -tuln | grep -v "127.0.0.1\|::1\|10.0.0\|192.168"
# Sollte LEER sein (keine externen Verbindungen)
```

---

## Support

Bei Problemen in Air-Gapped Umgebungen:

1. Logs sammeln: `./scripts/collect_support_bundle.sh`
2. Bundle per sicheren Kanal an Support senden
3. NIEMALS Produktionsdaten inkludieren

---

*Erstellt fuer Ablage-System Phase 10: On-Premises Excellence*
