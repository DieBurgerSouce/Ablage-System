#!/bin/bash

# Ablage-System Startup Script
# Starts the complete document processing system with GPU support

set -e

echo "========================================="
echo "  Ablage-System OCR - Enterprise Edition"
echo "  GPU-beschleunigte Dokumentverarbeitung"
echo "========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Überprüfe Voraussetzungen...${NC}"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker ist nicht installiert!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker gefunden${NC}"

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ Docker Compose ist nicht installiert!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker Compose gefunden${NC}"

    # Check NVIDIA Docker support
    if ! docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo -e "${YELLOW}⚠️  GPU-Unterstützung nicht verfügbar (Fallback auf CPU)${NC}"
        export USE_GPU=false
    else
        echo -e "${GREEN}✓ GPU-Unterstützung (RTX 4080) verfügbar${NC}"
        export USE_GPU=true
    fi
}

# Function to create .env file if it doesn't exist
setup_environment() {
    echo -e "${YELLOW}Konfiguriere Umgebung...${NC}"

    if [ ! -f .env ]; then
        echo -e "${YELLOW}Erstelle .env Datei...${NC}"
        cat > .env << EOF
# Ablage-System Environment Configuration
# Generated on $(date)

# Database
DB_PASSWORD=ablage_secure_$(openssl rand -hex 16)

# MinIO Object Storage
MINIO_ROOT_USER=ablage_admin
MINIO_ROOT_PASSWORD=minio_secure_$(openssl rand -hex 16)

# Application
SECRET_KEY=secret_$(openssl rand -hex 32)
CUDA_VISIBLE_DEVICES=0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false
LOG_LEVEL=INFO

# German Language Settings
DEFAULT_LANGUAGE=de
UMLAUT_VALIDATION=true

# GPU Settings
GPU_MEMORY_FRACTION=0.85
ENABLE_GPU=$USE_GPU
EOF
        echo -e "${GREEN}✓ .env Datei erstellt${NC}"
    else
        echo -e "${GREEN}✓ .env Datei vorhanden${NC}"
    fi
}

# Function to create required directories
create_directories() {
    echo -e "${YELLOW}Erstelle erforderliche Verzeichnisse...${NC}"

    mkdir -p test_documents
    mkdir -p uploads
    mkdir -p outputs
    mkdir -p logs
    mkdir -p infrastructure/postgres

    echo -e "${GREEN}✓ Verzeichnisse erstellt${NC}"
}

# Function to initialize database
init_database() {
    echo -e "${YELLOW}Initialisiere Datenbank...${NC}"

    # Create PostgreSQL init script with pgvector
    cat > infrastructure/postgres/init.sql << 'EOF'
-- Ablage-System Database Initialization
-- Create pgvector extension for embeddings
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- Create main schema
CREATE SCHEMA IF NOT EXISTS ablage;

-- Set default search path
ALTER DATABASE ablage_system SET search_path TO ablage, public;

-- Create document table
CREATE TABLE IF NOT EXISTS ablage.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_status VARCHAR(50) DEFAULT 'pending',
    ocr_backend VARCHAR(50),
    extracted_text TEXT,
    confidence_score FLOAT,
    processing_time_ms INTEGER,
    metadata JSONB,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_documents_status ON ablage.documents(processing_status);
CREATE INDEX idx_documents_upload_date ON ablage.documents(upload_date DESC);
CREATE INDEX idx_documents_embedding ON ablage.documents USING ivfflat (embedding vector_cosine_ops);

-- Create processing queue table
CREATE TABLE IF NOT EXISTS ablage.processing_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES ablage.documents(id),
    priority INTEGER DEFAULT 5,
    status VARCHAR(50) DEFAULT 'queued',
    backend VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Create statistics table
CREATE TABLE IF NOT EXISTS ablage.statistics (
    id SERIAL PRIMARY KEY,
    date DATE DEFAULT CURRENT_DATE,
    total_processed INTEGER DEFAULT 0,
    successful INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    avg_processing_time_ms INTEGER,
    gpu_usage_percent FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- German text validation function
CREATE OR REPLACE FUNCTION validate_german_text(text_input TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    -- Check for German umlauts
    RETURN text_input ~ '[äöüÄÖÜß]';
END;
$$ LANGUAGE plpgsql;

GRANT ALL PRIVILEGES ON SCHEMA ablage TO ablage_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ablage TO ablage_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA ablage TO ablage_admin;
EOF

    echo -e "${GREEN}✓ Datenbank-Initialisierung vorbereitet${NC}"
}

# Function to start services
start_services() {
    echo -e "${YELLOW}Starte Services...${NC}"

    # Start infrastructure services first
    docker-compose up -d postgres redis minio

    # Wait for PostgreSQL to be ready
    echo -e "${YELLOW}Warte auf PostgreSQL...${NC}"
    sleep 10

    # Start application services
    if [ "$USE_GPU" = true ]; then
        docker-compose up -d backend worker frontend
    else
        docker-compose up -d backend frontend
    fi

    echo -e "${GREEN}✓ Alle Services gestartet${NC}"
}

# Function to check service health
check_health() {
    echo -e "${YELLOW}Überprüfe Service-Status...${NC}"

    # Wait a bit for services to stabilize
    sleep 5

    # Check each service
    services=("postgres" "redis" "minio" "backend" "frontend")
    if [ "$USE_GPU" = true ]; then
        services+=("worker")
    fi

    all_healthy=true
    for service in "${services[@]}"; do
        if docker-compose ps | grep -q "ablage-$service.*Up"; then
            echo -e "${GREEN}✓ $service läuft${NC}"
        else
            echo -e "${RED}❌ $service nicht verfügbar${NC}"
            all_healthy=false
        fi
    done

    if [ "$all_healthy" = true ]; then
        echo -e "${GREEN}✓ Alle Services sind betriebsbereit${NC}"

        # Test API endpoint
        echo -e "${YELLOW}Teste API-Endpunkt...${NC}"
        if curl -s http://localhost:8000/health > /dev/null; then
            echo -e "${GREEN}✓ API ist erreichbar${NC}"

            # Show API info
            echo ""
            echo -e "${GREEN}=========================================${NC}"
            echo -e "${GREEN}  System erfolgreich gestartet!${NC}"
            echo -e "${GREEN}=========================================${NC}"
            echo ""
            echo "Zugriff auf die Services:"
            echo "  • Frontend: http://localhost/"
            echo "  • API: http://localhost:8000"
            echo "  • API Docs: http://localhost:8000/docs"
            echo "  • MinIO Console: http://localhost:9001"
            echo ""
            echo "Standard-Anmeldedaten MinIO:"
            echo "  • Benutzer: ablage_admin"
            echo "  • Passwort: siehe .env Datei"
            echo ""
            if [ "$USE_GPU" = true ]; then
                echo -e "${GREEN}GPU-Beschleunigung ist aktiv (RTX 4080)${NC}"
            else
                echo -e "${YELLOW}CPU-Modus (GPU nicht verfügbar)${NC}"
            fi
        else
            echo -e "${RED}❌ API antwortet nicht${NC}"
        fi
    else
        echo -e "${RED}❌ Einige Services sind nicht verfügbar${NC}"
        echo "Logs anzeigen mit: docker-compose logs -f"
    fi
}

# Function to show logs
show_logs() {
    echo ""
    echo -e "${YELLOW}Möchten Sie die Logs anzeigen? (j/n)${NC}"
    read -r answer
    if [ "$answer" = "j" ] || [ "$answer" = "J" ]; then
        docker-compose logs -f
    fi
}

# Function to stop services
stop_services() {
    echo -e "${YELLOW}Stoppe alle Services...${NC}"
    docker-compose down
    echo -e "${GREEN}✓ Services gestoppt${NC}"
}

# Main execution
main() {
    case "${1:-}" in
        stop)
            stop_services
            ;;
        restart)
            stop_services
            start_services
            check_health
            ;;
        logs)
            docker-compose logs -f "${2:-}"
            ;;
        status)
            docker-compose ps
            ;;
        *)
            check_prerequisites
            setup_environment
            create_directories
            init_database
            start_services
            check_health
            show_logs
            ;;
    esac
}

# Handle script interruption
trap 'echo -e "${RED}Script unterbrochen${NC}"; exit 1' INT TERM

# Run main function with all arguments
main "$@"