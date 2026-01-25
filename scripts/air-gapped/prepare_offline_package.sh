#!/bin/bash
# =============================================================================
# Ablage-System: Offline Package Preparation Script
# =============================================================================
# Erstellt ein vollstaendiges Offline-Paket fuer Air-Gapped Installationen.
# Dieses Skript MUSS auf einem System MIT Internetzugang ausgefuehrt werden.
#
# Verwendung: ./prepare_offline_package.sh [--skip-models] [--output-dir DIR]
#
# Ausgabe: ablage-system-offline-YYYYMMDD.tar.gz
# =============================================================================

set -euo pipefail

# Farben fuer Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATE_TAG=$(date +%Y%m%d)
OUTPUT_DIR="${PROJECT_ROOT}/dist"
TEMP_DIR="/tmp/ablage-offline-${DATE_TAG}"
SKIP_MODELS=false

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Argumente parsen
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-models)
            SKIP_MODELS=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Verwendung: $0 [--skip-models] [--output-dir DIR]"
            echo ""
            echo "Optionen:"
            echo "  --skip-models    ML-Modelle nicht einschliessen (spart ~12GB)"
            echo "  --output-dir     Ausgabeverzeichnis (Standard: ./dist)"
            exit 0
            ;;
        *)
            log_error "Unbekannte Option: $1"
            exit 1
            ;;
    esac
done

# Voraussetzungen pruefen
check_prerequisites() {
    log_info "Pruefe Voraussetzungen..."

    # Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker nicht gefunden. Bitte installieren."
        exit 1
    fi

    # Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose v2 nicht gefunden."
        exit 1
    fi

    # Internet-Verbindung
    if ! ping -c 1 google.com &> /dev/null; then
        log_error "Keine Internetverbindung. Dieses Skript benoetigt Internet."
        exit 1
    fi

    # Speicherplatz (mindestens 30GB frei)
    FREE_SPACE=$(df -BG "$TEMP_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo "0")
    if [[ "$FREE_SPACE" -lt 30 ]]; then
        log_error "Nicht genuegend Speicherplatz. Benoetigt: 30GB, Verfuegbar: ${FREE_SPACE}GB"
        exit 1
    fi

    log_success "Alle Voraussetzungen erfuellt"
}

# Verzeichnisse erstellen
setup_directories() {
    log_info "Erstelle Verzeichnisstruktur..."

    rm -rf "$TEMP_DIR"
    mkdir -p "$TEMP_DIR"/{images,wheels,npm,models,config,scripts}
    mkdir -p "$OUTPUT_DIR"

    log_success "Verzeichnisse erstellt: $TEMP_DIR"
}

# Docker Images exportieren
export_docker_images() {
    log_info "Exportiere Docker Images..."

    cd "$PROJECT_ROOT"

    # Images bauen (falls nicht vorhanden)
    log_info "Baue Docker Images..."
    docker compose build --no-cache

    # Images auflisten
    IMAGES=(
        "ablage-system-backend:latest"
        "ablage-system-frontend:latest"
        "ablage-system-worker:latest"
        "postgres:16-alpine"
        "redis:7-alpine"
        "minio/minio:latest"
        "grafana/grafana:latest"
        "prom/prometheus:latest"
        "nginx:alpine"
    )

    for IMAGE in "${IMAGES[@]}"; do
        IMAGE_NAME=$(echo "$IMAGE" | tr '/:' '-')
        log_info "  Exportiere $IMAGE..."

        # Image pullen falls nicht lokal
        docker pull "$IMAGE" 2>/dev/null || true

        # Als tar exportieren
        docker save "$IMAGE" | gzip > "$TEMP_DIR/images/${IMAGE_NAME}.tar.gz"

        log_success "  $IMAGE exportiert"
    done

    log_success "Alle Docker Images exportiert"
}

# Python Wheels herunterladen
download_python_wheels() {
    log_info "Lade Python Wheels herunter..."

    cd "$PROJECT_ROOT"

    # Virtuelle Umgebung erstellen
    python3 -m venv "$TEMP_DIR/.venv"
    source "$TEMP_DIR/.venv/bin/activate"

    # pip upgraden
    pip install --upgrade pip wheel

    # Wheels herunterladen (fuer Linux x86_64)
    pip download \
        --dest "$TEMP_DIR/wheels" \
        --platform manylinux2014_x86_64 \
        --python-version 311 \
        --only-binary=:all: \
        -r requirements.txt || {
            log_warn "Einige Wheels konnten nicht heruntergeladen werden (source-only packages)"
        }

    # Auch Source-Packages fuer Fallback
    pip download \
        --dest "$TEMP_DIR/wheels" \
        --no-binary=:none: \
        -r requirements.txt 2>/dev/null || true

    deactivate

    # requirements.txt kopieren
    cp requirements.txt "$TEMP_DIR/wheels/"

    log_success "Python Wheels heruntergeladen: $(ls -1 "$TEMP_DIR/wheels" | wc -l) Dateien"
}

# NPM Packages herunterladen
download_npm_packages() {
    log_info "Lade NPM Packages herunter..."

    cd "$PROJECT_ROOT/frontend"

    # npm ci mit Cache
    npm ci --cache "$TEMP_DIR/npm-cache"

    # node_modules als tar
    tar -czf "$TEMP_DIR/npm/node_modules.tar.gz" node_modules/

    # package.json und package-lock.json
    cp package.json package-lock.json "$TEMP_DIR/npm/"

    log_success "NPM Packages heruntergeladen"
}

# ML-Modelle herunterladen
download_ml_models() {
    if [[ "$SKIP_MODELS" == "true" ]]; then
        log_warn "ML-Modelle werden uebersprungen (--skip-models)"
        return
    fi

    log_info "Lade ML-Modelle herunter... (Dies kann lange dauern)"

    # Python fuer Downloads
    source "$TEMP_DIR/.venv/bin/activate"
    pip install huggingface_hub transformers torch

    # Modell-Download-Skript
    python3 << 'PYTHON_SCRIPT'
import os
from huggingface_hub import snapshot_download

MODEL_DIR = os.environ.get('TEMP_DIR', '/tmp') + '/models'

models = [
    # Sentence Transformers (Embeddings)
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "sentence-transformers"),

    # Surya OCR
    ("vikp/surya_det", "surya/detection"),
    ("vikp/surya_rec", "surya/recognition"),

    # SpaCy German (wird separat behandelt)
]

for model_id, local_name in models:
    print(f"Downloading {model_id}...")
    try:
        snapshot_download(
            repo_id=model_id,
            local_dir=f"{MODEL_DIR}/{local_name}",
            local_dir_use_symlinks=False
        )
        print(f"  OK: {model_id}")
    except Exception as e:
        print(f"  ERROR: {model_id}: {e}")

print("ML-Modelle heruntergeladen")
PYTHON_SCRIPT

    # SpaCy German Model
    log_info "  Lade SpaCy German Model..."
    pip download de_core_news_lg -d "$TEMP_DIR/models/spacy/" \
        --extra-index-url https://github.com/explosion/spacy-models/releases/download || {
        log_warn "SpaCy Model konnte nicht heruntergeladen werden"
    }

    deactivate

    log_success "ML-Modelle heruntergeladen"
}

# Konfigurationsdateien kopieren
copy_config_files() {
    log_info "Kopiere Konfigurationsdateien..."

    cd "$PROJECT_ROOT"

    # .env Templates
    cp .env.example "$TEMP_DIR/config/.env.airgap.example"

    # Docker Compose fuer Air-Gapped
    cp docker-compose.yml "$TEMP_DIR/config/docker-compose.yml"

    # Air-Gapped spezifische Compose-Datei erstellen
    cat > "$TEMP_DIR/config/docker-compose.airgap.yml" << 'COMPOSE_EOF'
# Docker Compose fuer Air-Gapped Installation
# KEINE externen Netzwerk-Aufrufe

version: '3.8'

services:
  backend:
    image: ablage-system-backend:latest
    restart: unless-stopped
    environment:
      - DISABLE_EXTERNAL_APIS=true
      - OLLAMA_BASE_URL=http://ollama:11434
    volumes:
      - ./models:/opt/models:ro
      - ./data:/app/data
    depends_on:
      - db
      - redis
    networks:
      - internal

  frontend:
    image: ablage-system-frontend:latest
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - backend
    networks:
      - internal

  worker:
    image: ablage-system-worker:latest
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    environment:
      - CUDA_VISIBLE_DEVICES=0
      - DISABLE_EXTERNAL_APIS=true
    volumes:
      - ./models:/opt/models:ro
    depends_on:
      - db
      - redis
    networks:
      - internal

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_DB=ablage
      - POSTGRES_USER=ablage
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - internal

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - internal

  minio:
    image: minio/minio:latest
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    networks:
      - internal

networks:
  internal:
    driver: bridge
    internal: true  # KEIN Internet-Zugang

volumes:
  postgres_data:
  redis_data:
  minio_data:
COMPOSE_EOF

    # Nginx-Konfiguration
    mkdir -p "$TEMP_DIR/config/nginx"
    cp infrastructure/nginx/*.conf "$TEMP_DIR/config/nginx/" 2>/dev/null || true

    # Alembic Migrations
    cp -r alembic "$TEMP_DIR/config/"

    log_success "Konfigurationsdateien kopiert"
}

# Installations-Skripte kopieren
copy_scripts() {
    log_info "Kopiere Installations-Skripte..."

    # Load Images Skript
    cat > "$TEMP_DIR/scripts/load_docker_images.sh" << 'SCRIPT_EOF'
#!/bin/bash
set -euo pipefail

echo "Lade Docker Images..."

for IMAGE_FILE in images/*.tar.gz; do
    echo "  Lade $(basename "$IMAGE_FILE")..."
    gunzip -c "$IMAGE_FILE" | docker load
done

echo "Alle Images geladen. Verifizieren mit: docker images"
SCRIPT_EOF

    # Install Models Skript
    cat > "$TEMP_DIR/scripts/install_models.sh" << 'SCRIPT_EOF'
#!/bin/bash
set -euo pipefail

MODEL_TARGET="${1:-/opt/ablage-system/models}"

echo "Installiere ML-Modelle nach $MODEL_TARGET..."

mkdir -p "$MODEL_TARGET"
cp -r models/* "$MODEL_TARGET/"

# Berechtigungen setzen
chown -R 1000:1000 "$MODEL_TARGET"
chmod -R 755 "$MODEL_TARGET"

echo "Modelle installiert in: $MODEL_TARGET"
SCRIPT_EOF

    # SSL Certificate Generation
    cat > "$TEMP_DIR/scripts/generate_ssl_cert.sh" << 'SCRIPT_EOF'
#!/bin/bash
set -euo pipefail

DOMAIN="${1:-localhost}"
SSL_DIR="${2:-./ssl}"

echo "Generiere selbstsigniertes SSL-Zertifikat fuer $DOMAIN..."

mkdir -p "$SSL_DIR"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/ablage.key" \
    -out "$SSL_DIR/ablage.crt" \
    -subj "/CN=$DOMAIN/O=Ablage-System/C=DE"

echo "Zertifikat erstellt:"
echo "  - $SSL_DIR/ablage.crt"
echo "  - $SSL_DIR/ablage.key"
SCRIPT_EOF

    # Main Install Skript
    cat > "$TEMP_DIR/scripts/install.sh" << 'SCRIPT_EOF'
#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "Ablage-System Air-Gapped Installation"
echo "=========================================="

# 1. Docker Images laden
./scripts/load_docker_images.sh

# 2. Modelle installieren
./scripts/install_models.sh /opt/ablage-system/models

# 3. Konfiguration kopieren
cp config/.env.airgap.example .env
cp config/docker-compose.airgap.yml docker-compose.yml

# 4. SSL-Zertifikat (falls nicht vorhanden)
if [[ ! -f ssl/ablage.crt ]]; then
    ./scripts/generate_ssl_cert.sh "$(hostname -f)"
fi

echo ""
echo "Installation vorbereitet. Naechste Schritte:"
echo "1. .env Datei anpassen"
echo "2. docker-compose up -d"
echo "3. docker-compose exec backend alembic upgrade head"
echo ""
SCRIPT_EOF

    chmod +x "$TEMP_DIR/scripts/"*.sh

    log_success "Skripte kopiert"
}

# README erstellen
create_readme() {
    log_info "Erstelle README..."

    cat > "$TEMP_DIR/README.md" << 'README_EOF'
# Ablage-System Offline-Paket

Dieses Paket enthaelt alle Komponenten fuer eine Air-Gapped Installation.

## Inhalt

- `images/` - Docker Container Images
- `wheels/` - Python Dependencies
- `npm/` - Frontend Dependencies
- `models/` - ML-Modelle (falls inkludiert)
- `config/` - Konfigurationsdateien
- `scripts/` - Installations-Skripte

## Schnellstart

```bash
# 1. Entpacken
tar -xzf ablage-system-offline-*.tar.gz
cd ablage-system-offline-*

# 2. Installation ausfuehren
./scripts/install.sh

# 3. Konfiguration anpassen
nano .env

# 4. System starten
docker-compose up -d
```

## Ausfuehrliche Anleitung

Siehe: docs/deployment/AIR-GAPPED-INSTALLATION.md

## Checksummen

SHA256-Checksummen fuer alle Dateien in: checksums.sha256
README_EOF

    log_success "README erstellt"
}

# Checksummen erstellen
create_checksums() {
    log_info "Erstelle Checksummen..."

    cd "$TEMP_DIR"
    find . -type f -not -name "checksums.sha256" -exec sha256sum {} \; > checksums.sha256

    log_success "Checksummen erstellt"
}

# Finales Archiv erstellen
create_archive() {
    log_info "Erstelle finales Archiv..."

    ARCHIVE_NAME="ablage-system-offline-${DATE_TAG}.tar.gz"

    cd "$(dirname "$TEMP_DIR")"
    tar -czf "$OUTPUT_DIR/$ARCHIVE_NAME" "$(basename "$TEMP_DIR")"

    # Groesse anzeigen
    SIZE=$(du -h "$OUTPUT_DIR/$ARCHIVE_NAME" | cut -f1)

    log_success "Archiv erstellt: $OUTPUT_DIR/$ARCHIVE_NAME ($SIZE)"

    # Checksumme des Archivs
    cd "$OUTPUT_DIR"
    sha256sum "$ARCHIVE_NAME" > "${ARCHIVE_NAME}.sha256"

    log_success "Checksumme: ${ARCHIVE_NAME}.sha256"
}

# Aufraeumen
cleanup() {
    log_info "Raeume auf..."
    rm -rf "$TEMP_DIR"
    log_success "Temporaere Dateien entfernt"
}

# Hauptprogramm
main() {
    echo "=========================================="
    echo "Ablage-System Offline Package Preparation"
    echo "=========================================="
    echo ""

    check_prerequisites
    setup_directories
    export_docker_images
    download_python_wheels
    download_npm_packages
    download_ml_models
    copy_config_files
    copy_scripts
    create_readme
    create_checksums
    create_archive
    cleanup

    echo ""
    echo "=========================================="
    log_success "Offline-Paket erfolgreich erstellt!"
    echo "=========================================="
    echo ""
    echo "Ausgabe: $OUTPUT_DIR/ablage-system-offline-${DATE_TAG}.tar.gz"
    echo ""
    echo "Naechste Schritte:"
    echo "1. Paket auf USB-Stick/Medium kopieren"
    echo "2. Checksumme verifizieren"
    echo "3. Auf Air-Gapped System transferieren"
    echo "4. Installation gemaess AIR-GAPPED-INSTALLATION.md"
    echo ""
}

# Skript ausfuehren
main "$@"
