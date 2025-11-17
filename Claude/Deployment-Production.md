PRODUCTION DEPLOYMENT GUIDE
Complete Deployment Strategy for OCR Multi-Backend System

📋 TABLE OF CONTENTS

Introduction & Overview
Docker & Docker Compose
Environment Configuration
Kubernetes Deployment
CI/CD Pipeline
SSL/TLS Setup
Reverse Proxy (Nginx)
Health Checks
Rolling Updates & Blue-Green Deployment
Monitoring & Logging
Troubleshooting
Checklists & Quick Reference


1. 🎯 INTRODUCTION & OVERVIEW
1.1 Deployment Architecture
┌─────────────────────────────────────────────────────────┐
│           PRODUCTION DEPLOYMENT ARCHITECTURE             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Internet                                               │
│     │                                                   │
│     ├──► CloudFlare (CDN + DDoS Protection)           │
│     │                                                   │
│     ├──► Nginx (Reverse Proxy + SSL Termination)      │
│           │                                             │
│           ├──► Load Balancer                           │
│                 │                                       │
│                 ├──► Backend A (DeepSeek) - GPU        │
│                 │     ├─ Docker Container              │
│                 │     └─ Port: 8001                    │
│                 │                                       │
│                 ├──► Backend B (GOT-OCR) - GPU         │
│                 │     ├─ Docker Container              │
│                 │     └─ Port: 8002                    │
│                 │                                       │
│                 └──► Backend C (Surya) - CPU           │
│                       ├─ Docker Container              │
│                       └─ Port: 8003                    │
│                                                         │
│  Supporting Services:                                   │
│  ├─ PostgreSQL (Database)                              │
│  ├─ Redis (Cache & Queue)                              │
│  ├─ Prometheus (Metrics)                               │
│  └─ Grafana (Dashboards)                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
1.2 Deployment Strategies Overview
yaml# deployment/strategies.yml

deployment_strategies:
  
  # For your OCR system, we'll use a combination:
  
  docker_compose:
    when_to_use: "Development, small production deployments"
    pros:
      - "Simple to setup"
      - "Easy to understand"
      - "Perfect for single-server deployments"
    cons:
      - "Limited scaling"
      - "No built-in load balancing"
      - "Manual orchestration"
    recommendation: "Dev + Small Production (< 1000 req/day)"
  
  kubernetes:
    when_to_use: "Large production, high availability needed"
    pros:
      - "Auto-scaling"
      - "Self-healing"
      - "Rolling updates"
      - "Load balancing"
    cons:
      - "Complex setup"
      - "Steep learning curve"
      - "Resource overhead"
    recommendation: "Production (> 10,000 req/day)"
  
  hybrid:
    when_to_use: "Growing from small to large"
    approach:
      - "Start with Docker Compose"
      - "Add Nginx load balancer"
      - "Migrate to K8s when needed"
    recommendation: "Your current situation (6 weeks timeline)"

2. 🐳 DOCKER & DOCKER COMPOSE
2.1 Production Docker Compose - Complete Stack
yaml# docker-compose.production.yml

version: '3.8'

# ============================================
# PRODUCTION OCR SYSTEM - COMPLETE STACK
# ============================================
#
# This compose file deploys:
# - 3 OCR backends (A, B, C)
# - PostgreSQL database
# - Redis cache
# - Nginx reverse proxy
# - Monitoring stack
#
# Usage:
#   docker-compose -f docker-compose.production.yml up -d
#
# ============================================

services:
  
  # ==========================================
  # BACKEND A: DeepSeek-Janus-Pro (GPU)
  # ==========================================
  
  backend-a:
    image: ${DOCKER_REGISTRY}/ocr-backend-deepseek:${VERSION}
    container_name: ocr-backend-a
    hostname: backend-a
    
    build:
      context: ./backends/deepseek
      dockerfile: Dockerfile.production
      args:
        PYTHON_VERSION: "3.11"
        CUDA_VERSION: "12.1"
    
    restart: unless-stopped
    
    environment:
      - BACKEND_NAME=deepseek
      - MODEL_NAME=deepseek-ai/Janus-Pro-7B
      - DEVICE=cuda
      - MAX_BATCH_SIZE=4
      - WORKER_TIMEOUT=300
      
      # Database
      - DATABASE_URL=${DATABASE_URL}
      - DB_POOL_SIZE=10
      
      # Redis
      - REDIS_URL=${REDIS_URL}
      
      # Logging
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - LOG_FORMAT=json
      - SENTRY_DSN=${SENTRY_DSN}
      
      # Performance
      - PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
      
      # Security
      - API_KEY=${BACKEND_A_API_KEY}
    
    volumes:
      - model-cache-deepseek:/root/.cache/huggingface
      - ./logs/backend-a:/var/log/app
      - /tmp/uploads:/tmp/uploads:ro
    
    ports:
      - "8001:8000"
    
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 24G
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"
        labels: "backend=deepseek,tier=gpu"
  
  # ==========================================
  # BACKEND B: GOT-OCR 2.0 (GPU)
  # ==========================================
  
  backend-b:
    image: ${DOCKER_REGISTRY}/ocr-backend-gotocr:${VERSION}
    container_name: ocr-backend-b
    hostname: backend-b
    
    build:
      context: ./backends/gotocr
      dockerfile: Dockerfile.production
    
    restart: unless-stopped
    
    environment:
      - BACKEND_NAME=gotocr
      - MODEL_NAME=ucaslcl/GOT-OCR2_0
      - DEVICE=cuda
      - MAX_BATCH_SIZE=8
      - WORKER_TIMEOUT=120
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - API_KEY=${BACKEND_B_API_KEY}
    
    volumes:
      - model-cache-gotocr:/root/.cache/huggingface
      - ./logs/backend-b:/var/log/app
    
    ports:
      - "8002:8000"
    
    deploy:
      resources:
        limits:
          cpus: '6'
          memory: 16G
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 90s
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"
  
  # ==========================================
  # BACKEND C: Surya + Docling (CPU)
  # ==========================================
  
  backend-c:
    image: ${DOCKER_REGISTRY}/ocr-backend-surya:${VERSION}
    container_name: ocr-backend-c
    hostname: backend-c
    
    build:
      context: ./backends/surya
      dockerfile: Dockerfile.production
    
    restart: unless-stopped
    
    environment:
      - BACKEND_NAME=surya
      - MODEL_NAME=vikp/surya_rec2
      - DEVICE=cpu
      - MAX_WORKERS=16
      - WORKER_TIMEOUT=180
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - API_KEY=${BACKEND_C_API_KEY}
    
    volumes:
      - model-cache-surya:/root/.cache/huggingface
      - ./logs/backend-c:/var/log/app
    
    ports:
      - "8003:8000"
    
    deploy:
      resources:
        limits:
          cpus: '16'
          memory: 32G
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"
  
  # ==========================================
  # POSTGRESQL DATABASE
  # ==========================================
  
  postgres:
    image: postgres:14-alpine
    container_name: ocr-postgres
    hostname: postgres
    
    restart: unless-stopped
    
    environment:
      - POSTGRES_DB=${POSTGRES_DB:-ocr_production}
      - POSTGRES_USER=${POSTGRES_USER:-ocr_user}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C
    
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d:ro
      - ./backups/postgres:/backups
    
    ports:
      - "5432:5432"
    
    command: >
      postgres
      -c shared_buffers=2GB
      -c effective_cache_size=6GB
      -c maintenance_work_mem=512MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100
      -c random_page_cost=1.1
      -c effective_io_concurrency=200
      -c work_mem=64MB
      -c min_wal_size=1GB
      -c max_wal_size=4GB
      -c max_worker_processes=4
      -c max_parallel_workers_per_gather=2
      -c max_parallel_workers=4
      -c max_parallel_maintenance_workers=2
    
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
  
  # ==========================================
  # REDIS CACHE & QUEUE
  # ==========================================
  
  redis:
    image: redis:7-alpine
    container_name: ocr-redis
    hostname: redis
    
    restart: unless-stopped
    
    command: >
      redis-server
      --appendonly yes
      --maxmemory 4gb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000
    
    volumes:
      - redis-data:/data
    
    ports:
      - "6379:6379"
    
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  
  # ==========================================
  # NGINX REVERSE PROXY
  # ==========================================
  
  nginx:
    image: nginx:alpine
    container_name: ocr-nginx
    hostname: nginx
    
    restart: unless-stopped
    
    ports:
      - "80:80"
      - "443:443"
    
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./nginx/logs:/var/log/nginx
      - certbot-etc:/etc/letsencrypt
      - certbot-var:/var/lib/letsencrypt
      - web-root:/var/www/html
    
    depends_on:
      - backend-a
      - backend-b
      - backend-c
    
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
  
  # ==========================================
  # CERTBOT (SSL CERTIFICATES)
  # ==========================================
  
  certbot:
    image: certbot/certbot
    container_name: ocr-certbot
    
    volumes:
      - certbot-etc:/etc/letsencrypt
      - certbot-var:/var/lib/letsencrypt
      - web-root:/var/www/html
    
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
    
    networks:
      - ocr-network
  
  # ==========================================
  # PROMETHEUS MONITORING
  # ==========================================
  
  prometheus:
    image: prom/prometheus:latest
    container_name: ocr-prometheus
    hostname: prometheus
    
    restart: unless-stopped
    
    ports:
      - "9090:9090"
    
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerts:/etc/prometheus/alerts:ro
      - prometheus-data:/prometheus
    
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  
  # ==========================================
  # GRAFANA DASHBOARDS
  # ==========================================
  
  grafana:
    image: grafana/grafana:latest
    container_name: ocr-grafana
    hostname: grafana
    
    restart: unless-stopped
    
    ports:
      - "3000:3000"
    
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_USER:-admin}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_SERVER_ROOT_URL=https://${DOMAIN}/grafana
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
    
    depends_on:
      - prometheus
    
    networks:
      - ocr-network
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

# ============================================
# VOLUMES
# ============================================

volumes:
  model-cache-deepseek:
    driver: local
  model-cache-gotocr:
    driver: local
  model-cache-surya:
    driver: local
  postgres-data:
    driver: local
  redis-data:
    driver: local
  prometheus-data:
    driver: local
  grafana-data:
    driver: local
  certbot-etc:
    driver: local
  certbot-var:
    driver: local
  web-root:
    driver: local

# ============================================
# NETWORKS
# ============================================

networks:
  ocr-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.25.0.0/16
2.2 Production Dockerfile - Backend Example
dockerfile# backends/deepseek/Dockerfile.production

# ============================================
# PRODUCTION DOCKERFILE - BACKEND A (DeepSeek)
# ============================================
#
# Multi-stage build for optimized production image
#
# ============================================

# ==========================================
# STAGE 1: Builder
# ==========================================

FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 AS builder

ARG PYTHON_VERSION=3.11
ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    python${PYTHON_VERSION} \
    python3-pip \
    python3-dev \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements
COPY requirements.txt requirements-prod.txt ./

# Install Python dependencies
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir -r requirements-prod.txt && \
    pip3 install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# ==========================================
# STAGE 2: Runtime
# ==========================================

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ARG PYTHON_VERSION=3.11
ARG DEBIAN_FRONTEND=noninteractive

# Metadata
LABEL maintainer="ben@agency.com"
LABEL version="1.0"
LABEL description="OCR Backend A - DeepSeek-Janus-Pro"

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    python${PYTHON_VERSION} \
    python3-pip \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app /var/log/app /tmp/uploads && \
    chown -R appuser:appuser /app /var/log/app /tmp/uploads

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python${PYTHON_VERSION}/dist-packages /usr/local/lib/python${PYTHON_VERSION}/dist-packages

WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint script
COPY --chown=appuser:appuser docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
2.3 Docker Entrypoint Script
bash#!/bin/bash
# docker-entrypoint.sh

# ============================================
# DOCKER ENTRYPOINT SCRIPT
# ============================================

set -e

# Function to wait for service
wait_for_service() {
    local host=$1
    local port=$2
    local service=$3
    local timeout=60
    local counter=0
    
    echo "Waiting for $service..."
    
    until nc -z "$host" "$port" 2>/dev/null; do
        counter=$((counter + 1))
        if [ $counter -ge $timeout ]; then
            echo "ERROR: $service not available after ${timeout}s"
            exit 1
        fi
        sleep 1
    done
    
    echo "✓ $service is ready"
}

# Parse database URL
if [ -n "$DATABASE_URL" ]; then
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    
    if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
        wait_for_service "$DB_HOST" "$DB_PORT" "PostgreSQL"
    fi
fi

# Parse Redis URL
if [ -n "$REDIS_URL" ]; then
    REDIS_HOST=$(echo "$REDIS_URL" | sed -n 's|redis://\([^:]*\).*|\1|p')
    REDIS_PORT=$(echo "$REDIS_URL" | sed -n 's|.*:\([0-9]*\).*|\1|p')
    
    if [ -n "$REDIS_HOST" ] && [ -n "$REDIS_PORT" ]; then
        wait_for_service "$REDIS_HOST" "$REDIS_PORT" "Redis"
    fi
fi

# Run database migrations (if applicable)
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head || echo "No migrations to run"
fi

# Download models if needed
if [ "$DOWNLOAD_MODELS" = "true" ]; then
    echo "Downloading models..."
    python3 -c "from transformers import AutoModel; AutoModel.from_pretrained('$MODEL_NAME')"
fi

# Start application
echo "Starting $BACKEND_NAME backend..."
exec "$@"
2.4 Docker Management Script
bash#!/bin/bash
# scripts/deploy_docker.sh

# ============================================
# DOCKER DEPLOYMENT SCRIPT
# ============================================

set -euo pipefail

ENVIRONMENT=${1:-"production"}
ACTION=${2:-"deploy"}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

# ============================================
# CONFIGURATION
# ============================================

COMPOSE_FILE="docker-compose.${ENVIRONMENT}.yml"
ENV_FILE=".env.${ENVIRONMENT}"

if [ ! -f "$COMPOSE_FILE" ]; then
    error "Compose file not found: $COMPOSE_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
    error "Environment file not found: $ENV_FILE"
fi

# ============================================
# FUNCTIONS
# ============================================

deploy() {
    log "Deploying to $ENVIRONMENT..."
    
    # Pull latest images
    log "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull
    
    # Build images if needed
    log "Building images..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --parallel
    
    # Start services
    log "Starting services..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans
    
    # Wait for health checks
    log "Waiting for services to be healthy..."
    sleep 10
    
    # Check health
    docker-compose -f "$COMPOSE_FILE" ps
    
    log "✅ Deployment complete!"
}

rollback() {
    log "Rolling back deployment..."
    
    # Get previous version
    PREVIOUS_VERSION=$(docker images --format "{{.Tag}}" | grep -v "latest" | sort -V | tail -n2 | head -n1)
    
    if [ -z "$PREVIOUS_VERSION" ]; then
        error "No previous version found"
    fi
    
    log "Rolling back to version: $PREVIOUS_VERSION"
    
    # Update version in env file
    sed -i "s/VERSION=.*/VERSION=$PREVIOUS_VERSION/" "$ENV_FILE"
    
    # Deploy previous version
    deploy
    
    log "✅ Rollback complete!"
}

status() {
    log "Service status:"
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo ""
    log "Resource usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
}

logs() {
    SERVICE=${3:-""}
    
    if [ -n "$SERVICE" ]; then
        docker-compose -f "$COMPOSE_FILE" logs -f --tail=100 "$SERVICE"
    else
        docker-compose -f "$COMPOSE_FILE" logs -f --tail=100
    fi
}

stop() {
    log "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" down
    log "✅ Services stopped"
}

restart() {
    SERVICE=${3:-""}
    
    if [ -n "$SERVICE" ]; then
        log "Restarting service: $SERVICE"
        docker-compose -f "$COMPOSE_FILE" restart "$SERVICE"
    else
        log "Restarting all services..."
        docker-compose -f "$COMPOSE_FILE" restart
    fi
    
    log "✅ Restart complete"
}

health_check() {
    log "Running health checks..."
    
    SERVICES=("backend-a" "backend-b" "backend-c" "postgres" "redis" "nginx")
    
    for service in "${SERVICES[@]}"; do
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "ocr-${service}" 2>/dev/null || echo "no container")
        
        if [ "$HEALTH" == "healthy" ]; then
            echo -e "  ${GREEN}✓${NC} $service: healthy"
        elif [ "$HEALTH" == "starting" ]; then
            echo -e "  ${YELLOW}⟳${NC} $service: starting"
        else
            echo -e "  ${RED}✗${NC} $service: unhealthy"
        fi
    done
}

# ============================================
# MAIN
# ============================================

case "$ACTION" in
    deploy)
        if [ "$ENVIRONMENT" == "production" ]; then
            warn "⚠️  Deploying to PRODUCTION!"
            read -p "Continue? (yes/no): " CONFIRM
            if [ "$CONFIRM" != "yes" ]; then
                error "Deployment cancelled"
            fi
        fi
        deploy
        ;;
    rollback)
        rollback
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    health)
        health_check
        ;;
    *)
        cat << EOF
Usage: $0 <environment> <action> [service]

Environments:
  development
  staging
  production

Actions:
  deploy      - Deploy services
  rollback    - Rollback to previous version
  status      - Show service status
  logs        - Show service logs
  stop        - Stop services
  restart     - Restart services
  health      - Run health checks

Examples:
  $0 production deploy
  $0 production status
  $0 production logs backend-a
  $0 production restart backend-a
EOF
        exit 1
        ;;
esac




PRODUCTION DEPLOYMENT GUIDE - TEIL 2

3. ⚙️ ENVIRONMENT CONFIGURATION
3.1 Environment Variables Structure
bash# .env.production

# ============================================
# PRODUCTION ENVIRONMENT CONFIGURATION
# ============================================
# 
# CRITICAL: Never commit this file to Git!
# Store in secure vault (Ansible Vault, etc.)
#
# ============================================

# ==========================================
# APPLICATION
# ==========================================

ENVIRONMENT=production
VERSION=1.2.3
DOCKER_REGISTRY=registry.company.com

# Domain
DOMAIN=api.company.com
API_URL=https://api.company.com

# ==========================================
# BACKEND A - DeepSeek
# ==========================================

BACKEND_A_ENABLED=true
BACKEND_A_MODEL=deepseek-ai/Janus-Pro-7B
BACKEND_A_DEVICE=cuda
BACKEND_A_MAX_BATCH_SIZE=4
BACKEND_A_WORKER_TIMEOUT=300
BACKEND_A_API_KEY=deepseek-prod-key-xxxxxxxxxxxxx

# ==========================================
# BACKEND B - GOT-OCR
# ==========================================

BACKEND_B_ENABLED=true
BACKEND_B_MODEL=ucaslcl/GOT-OCR2_0
BACKEND_B_DEVICE=cuda
BACKEND_B_MAX_BATCH_SIZE=8
BACKEND_B_WORKER_TIMEOUT=120
BACKEND_B_API_KEY=gotocr-prod-key-xxxxxxxxxxxxx

# ==========================================
# BACKEND C - Surya
# ==========================================

BACKEND_C_ENABLED=true
BACKEND_C_MODEL=vikp/surya_rec2
BACKEND_C_DEVICE=cpu
BACKEND_C_MAX_WORKERS=16
BACKEND_C_WORKER_TIMEOUT=180
BACKEND_C_API_KEY=surya-prod-key-xxxxxxxxxxxxx

# ==========================================
# DATABASE - PostgreSQL
# ==========================================

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ocr_production
POSTGRES_USER=ocr_user
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD_HERE

# Connection string (auto-generated from above)
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

# Pool settings
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600

# ==========================================
# REDIS
# ==========================================

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}

# Cache settings
REDIS_CACHE_TTL=3600
REDIS_MAX_CONNECTIONS=50

# ==========================================
# LOGGING
# ==========================================

LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_OUTPUT=stdout

# Sentry (Error tracking)
SENTRY_DSN=https://xxxxx@sentry.io/xxxxx
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1

# ==========================================
# SECURITY
# ==========================================

# JWT
SECRET_KEY=CHANGE_ME_RANDOM_SECRET_KEY_MIN_32_CHARS
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=8

# API Keys
API_KEY_HEADER=X-API-Key
REQUIRE_API_KEY=true

# CORS
CORS_ORIGINS=["https://app.company.com","https://admin.company.com"]
CORS_CREDENTIALS=true

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000

# ==========================================
# STORAGE
# ==========================================

# Local storage
UPLOAD_DIR=/var/app/uploads
MAX_UPLOAD_SIZE_MB=100
ALLOWED_EXTENSIONS=["pdf","jpg","jpeg","png","tiff"]

# S3 (optional)
USE_S3=false
S3_BUCKET=ocr-production-uploads
S3_REGION=eu-central-1
S3_ACCESS_KEY=
S3_SECRET_KEY=

# ==========================================
# MONITORING
# ==========================================

# Prometheus
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090

# Grafana
GRAFANA_USER=admin
GRAFANA_PASSWORD=CHANGE_ME_GRAFANA_PASSWORD
GRAFANA_PORT=3000

# Health check endpoint
HEALTH_CHECK_PATH=/health
HEALTH_CHECK_TIMEOUT=10

# ==========================================
# PERFORMANCE
# ==========================================

# Workers
WORKER_PROCESSES=4
WORKER_THREADS=8
WORKER_TIMEOUT=300
WORKER_KEEPALIVE=5

# GPU
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
CUDA_VISIBLE_DEVICES=0

# ==========================================
# BACKUP
# ==========================================

BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # 2 AM daily
BACKUP_RETENTION_DAYS=30
BACKUP_S3_BUCKET=ocr-backups

# ==========================================
# FEATURE FLAGS
# ==========================================

ENABLE_BATCH_PROCESSING=true
ENABLE_ASYNC_PROCESSING=true
ENABLE_CACHING=true
ENABLE_METRICS=true
ENABLE_PROFILING=false

# ==========================================
# EMAIL (for alerts)
# ==========================================

SMTP_HOST=smtp.company.com
SMTP_PORT=587
SMTP_USER=alerts@company.com
SMTP_PASSWORD=CHANGE_ME_SMTP_PASSWORD
SMTP_FROM=ocr-system@company.com
ALERT_EMAIL=devops@company.com
3.2 Environment-Specific Overrides
bash# .env.development

# Development overrides
ENVIRONMENT=development
LOG_LEVEL=DEBUG
LOG_FORMAT=colored

# Local URLs
DATABASE_URL=postgresql://ocr_user:dev@localhost:5432/ocr_dev
REDIS_URL=redis://localhost:6379/0

# Disable security for local dev
REQUIRE_API_KEY=false
RATE_LIMIT_ENABLED=false
CORS_ORIGINS=["http://localhost:3000"]

# Enable debugging
ENABLE_PROFILING=true
DEBUG_MODE=true

# Small batch sizes for testing
BACKEND_A_MAX_BATCH_SIZE=2
BACKEND_B_MAX_BATCH_SIZE=4
bash# .env.staging

# Staging environment
ENVIRONMENT=staging
DOMAIN=staging-api.company.com
API_URL=https://staging-api.company.com

# Staging database
DATABASE_URL=postgresql://ocr_user:staging_pass@staging-db:5432/ocr_staging

# Staging secrets (different from prod)
SECRET_KEY=staging-secret-key-different-from-prod
BACKEND_A_API_KEY=deepseek-staging-key-xxxxx

# More verbose logging
LOG_LEVEL=INFO
SENTRY_ENVIRONMENT=staging

# Lower rate limits
RATE_LIMIT_PER_MINUTE=30
RATE_LIMIT_PER_HOUR=500
3.3 Environment Management Script
bash#!/bin/bash
# scripts/manage_environment.sh

# ============================================
# ENVIRONMENT CONFIGURATION MANAGER
# ============================================

set -euo pipefail

ACTION=${1:-""}
ENVIRONMENT=${2:-""}

# ============================================
# FUNCTIONS
# ============================================

validate_env_file() {
    local env_file=$1
    
    echo "Validating $env_file..."
    
    # Required variables
    REQUIRED_VARS=(
        "ENVIRONMENT"
        "DATABASE_URL"
        "SECRET_KEY"
        "POSTGRES_PASSWORD"
    )
    
    # Source the file
    set -a
    source "$env_file"
    set +a
    
    # Check required variables
    for var in "${REQUIRED_VARS[@]}"; do
        if [ -z "${!var:-}" ]; then
            echo "❌ Missing required variable: $var"
            return 1
        else
            echo "✓ $var is set"
        fi
    done
    
    # Check for default passwords
    if [[ "$POSTGRES_PASSWORD" == "CHANGE_ME"* ]]; then
        echo "⚠️  WARNING: Using default PostgreSQL password!"
    fi
    
    if [[ "$SECRET_KEY" == "CHANGE_ME"* ]]; then
        echo "⚠️  WARNING: Using default secret key!"
    fi
    
    # Check password strength
    if [ ${#SECRET_KEY} -lt 32 ]; then
        echo "⚠️  WARNING: SECRET_KEY should be at least 32 characters!"
    fi
    
    echo "✅ Environment file validation complete"
}

generate_secrets() {
    echo "Generating secure secrets..."
    
    # Generate SECRET_KEY
    SECRET_KEY=$(openssl rand -base64 48)
    echo "SECRET_KEY=$SECRET_KEY"
    
    # Generate POSTGRES_PASSWORD
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
    
    # Generate API keys
    BACKEND_A_API_KEY=$(openssl rand -hex 32)
    echo "BACKEND_A_API_KEY=$BACKEND_A_API_KEY"
    
    BACKEND_B_API_KEY=$(openssl rand -hex 32)
    echo "BACKEND_B_API_KEY=$BACKEND_B_API_KEY"
    
    BACKEND_C_API_KEY=$(openssl rand -hex 32)
    echo "BACKEND_C_API_KEY=$BACKEND_C_API_KEY"
    
    echo ""
    echo "⚠️  Save these secrets securely!"
}

encrypt_env_file() {
    local env_file=$1
    
    if [ ! -f "$env_file" ]; then
        echo "❌ File not found: $env_file"
        return 1
    fi
    
    echo "Encrypting $env_file with Ansible Vault..."
    ansible-vault encrypt "$env_file"
    echo "✅ File encrypted: ${env_file}"
}

decrypt_env_file() {
    local env_file=$1
    
    if [ ! -f "$env_file" ]; then
        echo "❌ File not found: $env_file"
        return 1
    fi
    
    echo "Decrypting $env_file..."
    ansible-vault decrypt "$env_file"
    echo "✅ File decrypted: ${env_file}"
}

compare_environments() {
    local env1=$1
    local env2=$2
    
    if [ ! -f "$env1" ] || [ ! -f "$env2" ]; then
        echo "❌ One or both files not found"
        return 1
    fi
    
    echo "Comparing $env1 and $env2..."
    echo ""
    
    # Get all variable names from both files
    ALL_VARS=$(cat "$env1" "$env2" | grep -v "^#" | grep "=" | cut -d= -f1 | sort -u)
    
    echo "Variable differences:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    while IFS= read -r var; do
        # Source both files and compare
        val1=$(grep "^${var}=" "$env1" 2>/dev/null | cut -d= -f2- || echo "")
        val2=$(grep "^${var}=" "$env2" 2>/dev/null | cut -d= -f2- || echo "")
        
        if [ "$val1" != "$val2" ]; then
            if [ -z "$val1" ]; then
                echo "  ➕ $var: only in $env2"
            elif [ -z "$val2" ]; then
                echo "  ➖ $var: only in $env1"
            else
                echo "  ⚠️  $var: different values"
                echo "      $env1: $val1"
                echo "      $env2: $val2"
            fi
        fi
    done <<< "$ALL_VARS"
}

export_to_docker() {
    local env_file=$1
    
    echo "Exporting to Docker environment..."
    
    # Convert .env to Docker format
    grep -v "^#" "$env_file" | grep "=" > .env.docker
    
    echo "✅ Exported to .env.docker"
}

# ============================================
# MAIN
# ============================================

case "$ACTION" in
    validate)
        if [ -z "$ENVIRONMENT" ]; then
            echo "Usage: $0 validate <environment>"
            exit 1
        fi
        validate_env_file ".env.${ENVIRONMENT}"
        ;;
    
    generate-secrets)
        generate_secrets
        ;;
    
    encrypt)
        if [ -z "$ENVIRONMENT" ]; then
            echo "Usage: $0 encrypt <environment>"
            exit 1
        fi
        encrypt_env_file ".env.${ENVIRONMENT}"
        ;;
    
    decrypt)
        if [ -z "$ENVIRONMENT" ]; then
            echo "Usage: $0 decrypt <environment>"
            exit 1
        fi
        decrypt_env_file ".env.${ENVIRONMENT}"
        ;;
    
    compare)
        ENV2=${3:-""}
        if [ -z "$ENVIRONMENT" ] || [ -z "$ENV2" ]; then
            echo "Usage: $0 compare <env1> <env2>"
            exit 1
        fi
        compare_environments ".env.${ENVIRONMENT}" ".env.${ENV2}"
        ;;
    
    export-docker)
        if [ -z "$ENVIRONMENT" ]; then
            echo "Usage: $0 export-docker <environment>"
            exit 1
        fi
        export_to_docker ".env.${ENVIRONMENT}"
        ;;
    
    *)
        cat << EOF
Environment Configuration Manager

Usage: $0 <action> [environment]

Actions:
  validate          - Validate environment file
  generate-secrets  - Generate secure random secrets
  encrypt           - Encrypt environment file with Ansible Vault
  decrypt           - Decrypt environment file
  compare           - Compare two environment files
  export-docker     - Export to Docker .env format

Examples:
  $0 validate production
  $0 generate-secrets
  $0 encrypt production
  $0 compare development production
  $0 export-docker production
EOF
        exit 1
        ;;
esac
3.4 Configuration Template Generator
python#!/usr/bin/env python3
# scripts/generate_env_template.py

"""
Generate environment configuration template
"""

import os
import secrets
from typing import Dict, List

class EnvGenerator:
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.config = {}
    
    def generate_secret(self, length: int = 32) -> str:
        """Generate secure random secret"""
        return secrets.token_hex(length)
    
    def generate_password(self, length: int = 24) -> str:
        """Generate secure random password"""
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def build_config(self) -> Dict[str, str]:
        """Build configuration dictionary"""
        
        # Generate secrets
        secret_key = self.generate_secret(48)
        postgres_password = self.generate_password(32)
        api_key_a = self.generate_secret(32)
        api_key_b = self.generate_secret(32)
        api_key_c = self.generate_secret(32)
        
        config = {
            # Application
            "ENVIRONMENT": self.environment,
            "VERSION": "1.0.0",
            "DOCKER_REGISTRY": "registry.company.com",
            
            # Domain
            "DOMAIN": f"{'staging-' if self.environment == 'staging' else ''}api.company.com",
            
            # Database
            "POSTGRES_PASSWORD": postgres_password,
            "DB_POOL_SIZE": "20" if self.environment == "production" else "5",
            
            # Security
            "SECRET_KEY": secret_key,
            "BACKEND_A_API_KEY": api_key_a,
            "BACKEND_B_API_KEY": api_key_b,
            "BACKEND_C_API_KEY": api_key_c,
            
            # Logging
            "LOG_LEVEL": "INFO" if self.environment == "production" else "DEBUG",
            
            # Performance
            "WORKER_PROCESSES": "4" if self.environment == "production" else "1",
        }
        
        return config
    
    def generate_env_file(self, output_path: str = None):
        """Generate .env file"""
        
        if output_path is None:
            output_path = f".env.{self.environment}"
        
        config = self.build_config()
        
        with open(output_path, 'w') as f:
            f.write(f"# Generated environment file for {self.environment}\n")
            f.write(f"# Generated at: {os.popen('date').read()}\n")
            f.write("\n")
            
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        
        print(f"✅ Generated: {output_path}")
        print(f"⚠️  IMPORTANT: Review and update the file before use!")
        print(f"⚠️  Store secrets securely (use Ansible Vault or secret manager)")

if __name__ == "__main__":
    import sys
    
    env = sys.argv[1] if len(sys.argv) > 1 else "production"
    
    generator = EnvGenerator(env)
    generator.generate_env_file()

4. ☸️ KUBERNETES DEPLOYMENT
4.1 Kubernetes Architecture
yaml# kubernetes/architecture.yml

# ============================================
# KUBERNETES ARCHITECTURE FOR OCR SYSTEM
# ============================================

architecture:
  
  namespaces:
    - name: ocr-production
      description: "Main production namespace"
    - name: ocr-monitoring
      description: "Monitoring stack (Prometheus, Grafana)"
    - name: ocr-ingress
      description: "Ingress controllers"
  
  deployments:
    backend_a:
      replicas: 2
      strategy: RollingUpdate
      resources:
        requests:
          memory: "16Gi"
          cpu: "4"
          nvidia.com/gpu: 1
        limits:
          memory: "24Gi"
          cpu: "8"
          nvidia.com/gpu: 1
    
    backend_b:
      replicas: 3
      strategy: RollingUpdate
      resources:
        requests:
          memory: "12Gi"
          cpu: "3"
          nvidia.com/gpu: 1
        limits:
          memory: "16Gi"
          cpu: "6"
          nvidia.com/gpu: 1
    
    backend_c:
      replicas: 4
      strategy: RollingUpdate
      resources:
        requests:
          memory: "16Gi"
          cpu: "8"
        limits:
          memory: "32Gi"
          cpu: "16"
  
  services:
    - backend-a-service (ClusterIP)
    - backend-b-service (ClusterIP)
    - backend-c-service (ClusterIP)
    - postgres-service (ClusterIP)
    - redis-service (ClusterIP)
  
  ingress:
    - name: ocr-ingress
      class: nginx
      tls: true
      rules:
        - host: api.company.com
          paths:
            - /v1/deepseek → backend-a-service
            - /v1/gotocr → backend-b-service
            - /v1/surya → backend-c-service
4.2 Kubernetes Manifests - Namespace & ConfigMap
yaml# kubernetes/01-namespace.yml

apiVersion: v1
kind: Namespace
metadata:
  name: ocr-production
  labels:
    name: ocr-production
    environment: production
yaml# kubernetes/02-configmap.yml

apiVersion: v1
kind: ConfigMap
metadata:
  name: ocr-config
  namespace: ocr-production
data:
  # Application config
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
  
  # Backend A config
  BACKEND_A_MODEL: "deepseek-ai/Janus-Pro-7B"
  BACKEND_A_DEVICE: "cuda"
  BACKEND_A_MAX_BATCH_SIZE: "4"
  
  # Backend B config
  BACKEND_B_MODEL: "ucaslcl/GOT-OCR2_0"
  BACKEND_B_DEVICE: "cuda"
  BACKEND_B_MAX_BATCH_SIZE: "8"
  
  # Backend C config
  BACKEND_C_MODEL: "vikp/surya_rec2"
  BACKEND_C_DEVICE: "cpu"
  BACKEND_C_MAX_WORKERS: "16"
  
  # Database config (non-sensitive)
  POSTGRES_HOST: "postgres-service"
  POSTGRES_PORT: "5432"
  POSTGRES_DB: "ocr_production"
  
  # Redis config
  REDIS_HOST: "redis-service"
  REDIS_PORT: "6379"
4.3 Kubernetes Secrets
yaml# kubernetes/03-secrets.yml

apiVersion: v1
kind: Secret
metadata:
  name: ocr-secrets
  namespace: ocr-production
type: Opaque
stringData:
  # Database credentials
  POSTGRES_USER: ocr_user
  POSTGRES_PASSWORD: CHANGE_ME_STRONG_PASSWORD
  
  # Application secrets
  SECRET_KEY: CHANGE_ME_RANDOM_SECRET_KEY
  
  # API Keys
  BACKEND_A_API_KEY: deepseek-prod-key-xxxxx
  BACKEND_B_API_KEY: gotocr-prod-key-xxxxx
  BACKEND_C_API_KEY: surya-prod-key-xxxxx
  
  # Monitoring
  GRAFANA_PASSWORD: CHANGE_ME_GRAFANA_PASSWORD
  
  # Sentry
  SENTRY_DSN: https://xxxxx@sentry.io/xxxxx

---
# Create secrets from file (recommended)
# kubectl create secret generic ocr-secrets \
#   --from-env-file=.env.production \
#   --namespace=ocr-production
4.4 Backend A Deployment (DeepSeek)
yaml# kubernetes/10-backend-a-deployment.yml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-a-deepseek
  namespace: ocr-production
  labels:
    app: backend-a
    tier: gpu
    backend: deepseek
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  
  selector:
    matchLabels:
      app: backend-a
  
  template:
    metadata:
      labels:
        app: backend-a
        tier: gpu
        backend: deepseek
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    
    spec:
      # Node selector for GPU nodes
      nodeSelector:
        nvidia.com/gpu.present: "true"
        gpu-type: rtx-4080
      
      # Tolerations for GPU nodes
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      
      # Init container to download models
      initContainers:
        - name: download-models
          image: registry.company.com/ocr-backend-deepseek:1.0.0
          command: ['sh', '-c']
          args:
            - |
              python3 -c "
              from transformers import AutoModel
              AutoModel.from_pretrained('${BACKEND_A_MODEL}')
              "
          envFrom:
            - configMapRef:
                name: ocr-config
          volumeMounts:
            - name: model-cache
              mountPath: /root/.cache/huggingface
      
      containers:
        - name: backend-a
          image: registry.company.com/ocr-backend-deepseek:1.0.0
          imagePullPolicy: Always
          
          ports:
            - containerPort: 8000
              name: http
              protocol: TCP
          
          envFrom:
            - configMapRef:
                name: ocr-config
            - secretRef:
                name: ocr-secrets
          
          env:
            - name: BACKEND_NAME
              value: "deepseek"
            - name: DATABASE_URL
              value: "postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)"
            - name: REDIS_URL
              value: "redis://$(REDIS_HOST):$(REDIS_PORT)/0"
          
          resources:
            requests:
              memory: "16Gi"
              cpu: "4"
              nvidia.com/gpu: 1
            limits:
              memory: "24Gi"
              cpu: "8"
              nvidia.com/gpu: 1
          
          volumeMounts:
            - name: model-cache
              mountPath: /root/.cache/huggingface
            - name: tmp-uploads
              mountPath: /tmp/uploads
          
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 120
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 3
          
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 60
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 15"]
      
      volumes:
        - name: model-cache
          persistentVolumeClaim:
            claimName: model-cache-deepseek
        - name: tmp-uploads
          emptyDir: {}
      
      # Ensure pods are spread across nodes
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app
                      operator: In
                      values:
                        - backend-a
                topologyKey: kubernetes.io/hostname

---
apiVersion: v1
kind: Service
metadata:
  name: backend-a-service
  namespace: ocr-production
  labels:
    app: backend-a
spec:
  type: ClusterIP
  ports:
    - port: 8000
      targetPort: 8000
      protocol: TCP
      name: http
  selector:
    app: backend-a

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: model-cache-deepseek
  namespace: ocr-production
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 50Gi
  storageClassName: nfs-client
4.5 Horizontal Pod Autoscaler
yaml# kubernetes/15-hpa.yml

apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-a-hpa
  namespace: ocr-production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend-a-deepseek
  
  minReplicas: 2
  maxReplicas: 5
  
  metrics:
    # Scale based on CPU
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    
    # Scale based on memory
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    
    # Scale based on custom metric (requests per second)
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "100"
  
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 30
        - type: Pods
          value: 2
          periodSeconds: 30
      selectPolicy: Max

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-b-hpa
  namespace: ocr-production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend-b-gotocr
  minReplicas: 3
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-c-hpa
  namespace: ocr-production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend-c-surya
  minReplicas: 4
  maxReplicas: 12
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 75
4.6 Ingress Configuration
yaml# kubernetes/20-ingress.yml

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ocr-ingress
  namespace: ocr-production
  annotations:
    # Ingress controller
    kubernetes.io/ingress.class: nginx
    
    # SSL/TLS
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    
    # Rate limiting
    nginx.ingress.kubernetes.io/limit-rps: "100"
    nginx.ingress.kubernetes.io/limit-connections: "10"
    
    # Timeouts
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    
    # CORS
    nginx.ingress.kubernetes.io/enable-cors: "true"
    nginx.ingress.kubernetes.io/cors-allow-origin: "https://app.company.com"
    nginx.ingress.kubernetes.io/cors-allow-credentials: "true"
    
    # Request size
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    
    # Sticky sessions
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/session-cookie-name: "ocr-backend"
    nginx.ingress.kubernetes.io/session-cookie-max-age: "3600"

spec:
  tls:
    - hosts:
        - api.company.com
      secretName: api-company-com-tls
  
  rules:
    - host: api.company.com
      http:
        paths:
          # Backend A - DeepSeek
          - path: /v1/deepseek
            pathType: Prefix
            backend:
              service:
                name: backend-a-service
                port:
                  number: 8000
          
          # Backend B - GOT-OCR
          - path: /v1/gotocr
            pathType: Prefix
            backend:
              service:
                name: backend-b-service
                port:
                  number: 8000
          
          # Backend C - Surya
          - path: /v1/surya
            pathType: Prefix
            backend:
              service:
                name: backend-c-service
                port:
                  number: 8000
          
          # Health check
          - path: /health
            pathType: Exact
            backend:
              service:
                name: backend-a-service
                port:
                  number: 8000
4.7 Kubernetes Deployment Script
bash#!/bin/bash
# scripts/k8s_deploy.sh

# ============================================
# KUBERNETES DEPLOYMENT SCRIPT
# ============================================

set -euo pipefail

NAMESPACE=${1:-"ocr-production"}
ACTION=${2:-"deploy"}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[K8S]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

# ============================================
# FUNCTIONS
# ============================================

deploy_all() {
    log "Deploying to Kubernetes namespace: $NAMESPACE"
    
    # Create namespace
    log "Creating namespace..."
    kubectl apply -f kubernetes/01-namespace.yml
    
    # Apply ConfigMaps and Secrets
    log "Applying ConfigMaps and Secrets..."
    kubectl apply -f kubernetes/02-configmap.yml
    kubectl apply -f kubernetes/03-secrets.yml
    
    # Deploy PersistentVolumeClaims
    log "Creating PersistentVolumeClaims..."
    kubectl apply -f kubernetes/05-pvc.yml
    
    # Deploy PostgreSQL
    log "Deploying PostgreSQL..."
    kubectl apply -f kubernetes/06-postgres.yml
    
    # Deploy Redis
    log "Deploying Redis..."
    kubectl apply -f kubernetes/07-redis.yml
    
    # Wait for database
    log "Waiting for PostgreSQL to be ready..."
    kubectl wait --for=condition=ready pod \
        -l app=postgres \
        -n "$NAMESPACE" \
        --timeout=300s
    
    # Deploy backends
    log "Deploying Backend A (DeepSeek)..."
    kubectl apply -f kubernetes/10-backend-a-deployment.yml
    
    log "Deploying Backend B (GOT-OCR)..."
    kubectl apply -f kubernetes/11-backend-b-deployment.yml
    
    log "Deploying Backend C (Surya)..."
    kubectl apply -f kubernetes/12-backend-c-deployment.yml
    
    # Deploy HPA
    log "Deploying Horizontal Pod Autoscalers..."
    kubectl apply -f kubernetes/15-hpa.yml
    
    # Deploy Ingress
    log "Deploying Ingress..."
    kubectl apply -f kubernetes/20-ingress.yml
    
    # Wait for deployments
    log "Waiting for deployments to be ready..."
    kubectl wait --for=condition=available deployment \
        --all \
        -n "$NAMESPACE" \
        --timeout=600s
    
    log "✅ Deployment complete!"
    
    # Show status
    show_status
}

rollback() {
    REVISION=${3:-""}
    
    if [ -z "$REVISION" ]; then
        # Show rollout history
        log "Rollout history:"
        kubectl rollout history deployment -n "$NAMESPACE"
        
        read -p "Enter revision number to rollback to: " REVISION
    fi
    
    log "Rolling back to revision: $REVISION"
    
    kubectl rollout undo deployment backend-a-deepseek -n "$NAMESPACE" --to-revision="$REVISION"
    kubectl rollout undo deployment backend-b-gotocr -n "$NAMESPACE" --to-revision="$REVISION"
    kubectl rollout undo deployment backend-c-surya -n "$NAMESPACE" --to-revision="$REVISION"
    
    log "✅ Rollback complete!"
}

show_status() {
    log "Deployment status:"
    kubectl get all -n "$NAMESPACE"
    
    echo ""
    log "Pod status:"
    kubectl get pods -n "$NAMESPACE" -o wide
    
    echo ""
    log "Ingress status:"
    kubectl get ingress -n "$NAMESPACE"
}

show_logs() {
    SERVICE=${3:-"backend-a"}
    
    POD=$(kubectl get pods -n "$NAMESPACE" -l "app=$SERVICE" -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$POD" ]; then
        error "No pod found for service: $SERVICE"
    fi
    
    log "Streaming logs from: $POD"
    kubectl logs -f "$POD" -n "$NAMESPACE"
}

scale() {
    DEPLOYMENT=${3:-""}
    REPLICAS=${4:-""}
    
    if [ -z "$DEPLOYMENT" ] || [ -z "$REPLICAS" ]; then
        error "Usage: $0 $NAMESPACE scale <deployment> <replicas>"
    fi
    
    log "Scaling $DEPLOYMENT to $REPLICAS replicas..."
    kubectl scale deployment "$DEPLOYMENT" -n "$NAMESPACE" --replicas="$REPLICAS"
    
    log "✅ Scaling complete"
}

# ============================================
# MAIN
# ============================================

case "$ACTION" in
    deploy)
        deploy_all
        ;;
    rollback)
        rollback
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    scale)
        scale
        ;;
    *)
        cat << EOF
Kubernetes Deployment Script

Usage: $0 <namespace> <action> [options]

Actions:
  deploy      - Deploy all services
  rollback    - Rollback to previous version
  status      - Show deployment status
  logs        - Show pod logs
  scale       - Scale deployment

Examples:
  $0 ocr-production deploy
  $0 ocr-production status
  $0 ocr-production logs backend-a
  $0 ocr-production scale backend-a-deepseek 5
  $0 ocr-production rollback 3
EOF
        exit 1
        ;;
esac




  scale       - Scale deployment

Examples:
  $0 ocr-production deploy
  $0 ocr-production status
  $0 ocr-production logs backend-a
  $0 ocr-production scale backend-a-deepseek 5
  $0 ocr-production rollback 3
EOF
        exit 1
        ;;
esac

Weiter mit Teil 3 (Sections 5-6)? 🚀
Die nächsten Sections sind:

5. CI/CD Pipeline (GitHub Actions + GitLab CI)


SSL/TLS Setup


WiederholenBjaPrepared comprehensive CI/CD and SSL/TLS configuration guides.Der Nutzer möchte mit Teil 3 weitermachen, der die Sections 5 und 6 abdeckt:

5. CI/CD Pipeline (GitHub Actions + GitLab CI)


SSL/TLS Setup



Ich werde jetzt detaillierte CI/CD Pipeline Konfigurationen für sowohl GitHub Actions als auch GitLab CI erstellen, sowie eine umfassende SSL/TLS Setup Anleitung.🚀 PRODUCTION DEPLOYMENT GUIDE - TEIL 3

5. 🔄 CI/CD PIPELINE
5.1 CI/CD Architecture Overview
yaml# cicd/architecture.yml

# ============================================
# CI/CD PIPELINE ARCHITECTURE
# ============================================

pipeline_stages:
  
  stage_1_code_quality:
    name: "Code Quality & Linting"
    duration: "2-3 minutes"
    steps:
      - "Checkout code"
      - "Install dependencies"
      - "Run linters (black, flake8, mypy)"
      - "Security scan (bandit)"
      - "Dependency check"
    on_failure: "Block merge"
  
  stage_2_testing:
    name: "Testing"
    duration: "5-10 minutes"
    steps:
      - "Unit tests"
      - "Integration tests"
      - "API tests"
      - "Code coverage (minimum 80%)"
    on_failure: "Block merge"
  
  stage_3_build:
    name: "Build Docker Images"
    duration: "10-15 minutes"
    steps:
      - "Build Backend A image"
      - "Build Backend B image"
      - "Build Backend C image"
      - "Scan images for vulnerabilities"
      - "Tag images with version"
    on_failure: "Block deployment"
  
  stage_4_deploy_staging:
    name: "Deploy to Staging"
    duration: "5-10 minutes"
    trigger: "Merge to develop branch"
    steps:
      - "Push images to registry"
      - "Deploy to staging environment"
      - "Run smoke tests"
      - "Health checks"
    on_failure: "Rollback staging"
  
  stage_5_deploy_production:
    name: "Deploy to Production"
    duration: "10-20 minutes"
    trigger: "Manual approval + merge to main"
    steps:
      - "Backup production database"
      - "Blue-green deployment"
      - "Run smoke tests"
      - "Switch traffic"
      - "Monitor for 15 minutes"
    on_failure: "Auto-rollback"

deployment_strategies:
  
  development:
    trigger: "Every commit to feature branch"
    environment: "Development"
    auto_deploy: true
    run_tests: true
  
  staging:
    trigger: "Merge to develop"
    environment: "Staging"
    auto_deploy: true
    run_tests: true
    notifications: ["Slack #deployments"]
  
  production:
    trigger: "Manual approval on main branch"
    environment: "Production"
    auto_deploy: false
    requires_approval: true
    approvers: ["Tech Lead", "Product Manager"]
    run_tests: true
    health_check_duration: "15 minutes"
    rollback_on_failure: true
    notifications: ["Slack #production", "Email to team"]
5.2 GitHub Actions - Complete Workflow
yaml# .github/workflows/ci-cd.yml

name: CI/CD Pipeline

on:
  push:
    branches:
      - main
      - develop
      - 'feature/**'
  pull_request:
    branches:
      - main
      - develop
  release:
    types: [published]

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository_owner }}/ocr

jobs:
  # ==========================================
  # JOB 1: CODE QUALITY
  # ==========================================
  
  code-quality:
    name: Code Quality & Linting
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install black flake8 mypy bandit pytest
          pip install -r requirements.txt
      
      - name: Run Black (code formatter)
        run: |
          black --check --diff .
      
      - name: Run Flake8 (linter)
        run: |
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
          flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
      
      - name: Run MyPy (type checker)
        run: |
          mypy --ignore-missing-imports backends/
      
      - name: Run Bandit (security scanner)
        run: |
          bandit -r backends/ -ll
      
      - name: Check dependencies for vulnerabilities
        run: |
          pip install safety
          safety check --json
        continue-on-error: true

  # ==========================================
  # JOB 2: TESTS
  # ==========================================
  
  tests:
    name: Run Tests
    runs-on: ubuntu-latest
    needs: code-quality
    
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: ocr_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run unit tests
        env:
          DATABASE_URL: postgresql://postgres:testpass@localhost:5432/ocr_test
          REDIS_URL: redis://localhost:6379/0
        run: |
          pytest tests/unit -v --cov=backends --cov-report=xml --cov-report=term
      
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:testpass@localhost:5432/ocr_test
          REDIS_URL: redis://localhost:6379/0
        run: |
          pytest tests/integration -v
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests
          name: codecov-umbrella
      
      - name: Check coverage threshold
        run: |
          COVERAGE=$(python -c "import xml.etree.ElementTree as ET; tree = ET.parse('coverage.xml'); print(tree.getroot().attrib['line-rate'])")
          if (( $(echo "$COVERAGE < 0.80" | bc -l) )); then
            echo "Coverage is below 80%: $COVERAGE"
            exit 1
          fi

  # ==========================================
  # JOB 3: BUILD DOCKER IMAGES
  # ==========================================
  
  build:
    name: Build Docker Images
    runs-on: ubuntu-latest
    needs: tests
    if: github.event_name == 'push' || github.event_name == 'release'
    
    strategy:
      matrix:
        backend: [deepseek, gotocr, surya]
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-${{ matrix.backend }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-
            type=raw,value=latest,enable={{is_default_branch}}
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./backends/${{ matrix.backend }}
          file: ./backends/${{ matrix.backend }}/Dockerfile.production
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          build-args: |
            PYTHON_VERSION=3.11
            CUDA_VERSION=12.1
      
      - name: Scan image for vulnerabilities
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-${{ matrix.backend }}:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'

  # ==========================================
  # JOB 4: DEPLOY TO STAGING
  # ==========================================
  
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/develop'
    environment:
      name: staging
      url: https://staging-api.company.com
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up kubectl
        uses: azure/setup-kubectl@v3
      
      - name: Configure kubectl
        run: |
          echo "${{ secrets.KUBECONFIG_STAGING }}" | base64 -d > kubeconfig
          export KUBECONFIG=kubeconfig
      
      - name: Update image tags in manifests
        run: |
          cd kubernetes
          sed -i "s|image:.*backend-deepseek.*|image: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-deepseek:${{ github.sha }}|g" 10-backend-a-deployment.yml
          sed -i "s|image:.*backend-gotocr.*|image: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-gotocr:${{ github.sha }}|g" 11-backend-b-deployment.yml
          sed -i "s|image:.*backend-surya.*|image: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-surya:${{ github.sha }}|g" 12-backend-c-deployment.yml
      
      - name: Deploy to Kubernetes
        run: |
          export KUBECONFIG=kubeconfig
          kubectl apply -f kubernetes/ -n ocr-staging
      
      - name: Wait for rollout
        run: |
          export KUBECONFIG=kubeconfig
          kubectl rollout status deployment/backend-a-deepseek -n ocr-staging --timeout=10m
          kubectl rollout status deployment/backend-b-gotocr -n ocr-staging --timeout=10m
          kubectl rollout status deployment/backend-c-surya -n ocr-staging --timeout=10m
      
      - name: Run smoke tests
        run: |
          sleep 30
          curl -f https://staging-api.company.com/health || exit 1
          curl -f https://staging-api.company.com/v1/deepseek/health || exit 1
          curl -f https://staging-api.company.com/v1/gotocr/health || exit 1
          curl -f https://staging-api.company.com/v1/surya/health || exit 1
      
      - name: Notify Slack
        if: always()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Staging deployment: ${{ job.status }}'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}

  # ==========================================
  # JOB 5: DEPLOY TO PRODUCTION
  # ==========================================
  
  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://api.company.com
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up kubectl
        uses: azure/setup-kubectl@v3
      
      - name: Configure kubectl
        run: |
          echo "${{ secrets.KUBECONFIG_PRODUCTION }}" | base64 -d > kubeconfig
          export KUBECONFIG=kubeconfig
      
      - name: Backup database
        run: |
          echo "Creating database backup..."
          # Add backup script here
      
      - name: Blue-Green Deployment - Deploy to Green
        run: |
          export KUBECONFIG=kubeconfig
          
          # Create green deployment
          cd kubernetes
          sed -i 's/backend-a-deepseek/backend-a-deepseek-green/g' 10-backend-a-deployment.yml
          sed -i 's/backend-b-gotocr/backend-b-gotocr-green/g' 11-backend-b-deployment.yml
          sed -i 's/backend-c-surya/backend-c-surya-green/g' 12-backend-c-deployment.yml
          
          # Update image tags
          sed -i "s|image:.*backend-deepseek.*|image: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-deepseek:${{ github.sha }}|g" 10-backend-a-deployment.yml
          sed -i "s|image:.*backend-gotocr.*|image: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-gotocr:${{ github.sha }}|g" 11-backend-b-deployment.yml
          sed -i "s|image:.*backend-surya.*|image: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-surya:${{ github.sha }}|g" 12-backend-c-deployment.yml
          
          # Deploy green
          kubectl apply -f . -n ocr-production
      
      - name: Wait for green deployment
        run: |
          export KUBECONFIG=kubeconfig
          kubectl rollout status deployment/backend-a-deepseek-green -n ocr-production --timeout=15m
          kubectl rollout status deployment/backend-b-gotocr-green -n ocr-production --timeout=15m
          kubectl rollout status deployment/backend-c-surya-green -n ocr-production --timeout=15m
      
      - name: Run production smoke tests on green
        run: |
          sleep 60
          # Test green deployment through temporary service
          kubectl port-forward -n ocr-production deployment/backend-a-deepseek-green 8001:8000 &
          sleep 5
          curl -f http://localhost:8001/health || exit 1
      
      - name: Switch traffic to green
        run: |
          export KUBECONFIG=kubeconfig
          
          # Update service selectors to point to green
          kubectl patch service backend-a-service -n ocr-production -p '{"spec":{"selector":{"version":"green"}}}'
          kubectl patch service backend-b-service -n ocr-production -p '{"spec":{"selector":{"version":"green"}}}'
          kubectl patch service backend-c-service -n ocr-production -p '{"spec":{"selector":{"version":"green"}}}'
      
      - name: Monitor for 15 minutes
        run: |
          echo "Monitoring production for 15 minutes..."
          
          for i in {1..30}; do
            STATUS=$(curl -s https://api.company.com/health | jq -r '.status')
            if [ "$STATUS" != "healthy" ]; then
              echo "Health check failed! Rolling back..."
              exit 1
            fi
            echo "Health check $i/30: OK"
            sleep 30
          done
          
          echo "✅ Production deployment successful!"
      
      - name: Remove blue deployment
        if: success()
        run: |
          export KUBECONFIG=kubeconfig
          kubectl delete deployment backend-a-deepseek -n ocr-production || true
          kubectl delete deployment backend-b-gotocr -n ocr-production || true
          kubectl delete deployment backend-c-surya -n ocr-production || true
          
          # Rename green to blue for next deployment
          kubectl get deployment backend-a-deepseek-green -n ocr-production -o yaml | \
            sed 's/backend-a-deepseek-green/backend-a-deepseek/g' | \
            kubectl apply -f -
      
      - name: Rollback on failure
        if: failure()
        run: |
          export KUBECONFIG=kubeconfig
          
          echo "❌ Deployment failed! Rolling back..."
          
          # Switch traffic back to blue
          kubectl patch service backend-a-service -n ocr-production -p '{"spec":{"selector":{"version":"blue"}}}'
          kubectl patch service backend-b-service -n ocr-production -p '{"spec":{"selector":{"version":"blue"}}}'
          kubectl patch service backend-c-service -n ocr-production -p '{"spec":{"selector":{"version":"blue"}}}'
          
          # Delete green deployment
          kubectl delete deployment backend-a-deepseek-green -n ocr-production || true
          kubectl delete deployment backend-b-gotocr-green -n ocr-production || true
          kubectl delete deployment backend-c-surya-green -n ocr-production || true
      
      - name: Notify team
        if: always()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: |
            Production Deployment: ${{ job.status }}
            Version: ${{ github.sha }}
            By: ${{ github.actor }}
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
      
      - name: Create GitHub Release
        if: success() && github.event_name == 'release'
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          body: |
            Production deployment successful!
            
            Docker Images:
            - Backend A: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-deepseek:${{ github.sha }}
            - Backend B: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-gotocr:${{ github.sha }}
            - Backend C: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-surya:${{ github.sha }}
          draft: false
          prerelease: false
5.3 GitLab CI - Complete Pipeline
yaml# .gitlab-ci.yml

# ============================================
# GITLAB CI/CD PIPELINE
# ============================================

stages:
  - quality
  - test
  - build
  - deploy-staging
  - deploy-production

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"
  REGISTRY: registry.gitlab.com
  IMAGE_PREFIX: $CI_PROJECT_PATH

# ==========================================
# TEMPLATES
# ==========================================

.docker_template: &docker_template
  image: docker:24-dind
  services:
    - docker:24-dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY

.kubectl_template: &kubectl_template
  image: bitnami/kubectl:latest
  before_script:
    - echo "$KUBECONFIG" | base64 -d > /tmp/kubeconfig
    - export KUBECONFIG=/tmp/kubeconfig

# ==========================================
# STAGE 1: CODE QUALITY
# ==========================================

code-quality:
  stage: quality
  image: python:3.11
  
  before_script:
    - pip install black flake8 mypy bandit safety
    - pip install -r requirements.txt
  
  script:
    - echo "Running code quality checks..."
    - black --check --diff .
    - flake8 . --count --select=E9,F63,F7,F82 --show-source
    - mypy --ignore-missing-imports backends/
    - bandit -r backends/ -ll
    - safety check --json || true
  
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH'

# ==========================================
# STAGE 2: TESTS
# ==========================================

unit-tests:
  stage: test
  image: python:3.11
  
  services:
    - postgres:14
    - redis:7-alpine
  
  variables:
    POSTGRES_DB: ocr_test
    POSTGRES_USER: test_user
    POSTGRES_PASSWORD: test_pass
    DATABASE_URL: postgresql://test_user:test_pass@postgres:5432/ocr_test
    REDIS_URL: redis://redis:6379/0
  
  before_script:
    - pip install -r requirements.txt
    - pip install -r requirements-test.txt
  
  script:
    - pytest tests/unit -v --cov=backends --cov-report=xml --cov-report=term
    - pytest tests/integration -v
  
  coverage: '/(?i)total.*? (100(?:\.0+)?\%|[1-9]?\d(?:\.\d+)?\%)$/'
  
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
  
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH'

# ==========================================
# STAGE 3: BUILD
# ==========================================

build-backend-a:
  stage: build
  <<: *docker_template
  
  script:
    - cd backends/deepseek
    - docker build 
        -t $REGISTRY/$IMAGE_PREFIX/backend-deepseek:$CI_COMMIT_SHA
        -t $REGISTRY/$IMAGE_PREFIX/backend-deepseek:latest
        -f Dockerfile.production .
    - docker push $REGISTRY/$IMAGE_PREFIX/backend-deepseek:$CI_COMMIT_SHA
    - docker push $REGISTRY/$IMAGE_PREFIX/backend-deepseek:latest
  
  rules:
    - if: '$CI_COMMIT_BRANCH == "develop"'
    - if: '$CI_COMMIT_BRANCH == "main"'

build-backend-b:
  stage: build
  <<: *docker_template
  
  script:
    - cd backends/gotocr
    - docker build
        -t $REGISTRY/$IMAGE_PREFIX/backend-gotocr:$CI_COMMIT_SHA
        -t $REGISTRY/$IMAGE_PREFIX/backend-gotocr:latest
        -f Dockerfile.production .
    - docker push $REGISTRY/$IMAGE_PREFIX/backend-gotocr:$CI_COMMIT_SHA
    - docker push $REGISTRY/$IMAGE_PREFIX/backend-gotocr:latest
  
  rules:
    - if: '$CI_COMMIT_BRANCH == "develop"'
    - if: '$CI_COMMIT_BRANCH == "main"'

build-backend-c:
  stage: build
  <<: *docker_template
  
  script:
    - cd backends/surya
    - docker build
        -t $REGISTRY/$IMAGE_PREFIX/backend-surya:$CI_COMMIT_SHA
        -t $REGISTRY/$IMAGE_PREFIX/backend-surya:latest
        -f Dockerfile.production .
    - docker push $REGISTRY/$IMAGE_PREFIX/backend-surya:$CI_COMMIT_SHA
    - docker push $REGISTRY/$IMAGE_PREFIX/backend-surya:latest
  
  rules:
    - if: '$CI_COMMIT_BRANCH == "develop"'
    - if: '$CI_COMMIT_BRANCH == "main"'

# ==========================================
# STAGE 4: DEPLOY STAGING
# ==========================================

deploy-staging:
  stage: deploy-staging
  <<: *kubectl_template
  
  environment:
    name: staging
    url: https://staging-api.company.com
  
  variables:
    KUBECONFIG: $KUBECONFIG_STAGING
    NAMESPACE: ocr-staging
  
  script:
    - echo "Deploying to staging..."
    
    # Update image tags
    - cd kubernetes
    - sed -i "s|image:.*backend-deepseek.*|image: $REGISTRY/$IMAGE_PREFIX/backend-deepseek:$CI_COMMIT_SHA|g" 10-backend-a-deployment.yml
    - sed -i "s|image:.*backend-gotocr.*|image: $REGISTRY/$IMAGE_PREFIX/backend-gotocr:$CI_COMMIT_SHA|g" 11-backend-b-deployment.yml
    - sed -i "s|image:.*backend-surya.*|image: $REGISTRY/$IMAGE_PREFIX/backend-surya:$CI_COMMIT_SHA|g" 12-backend-c-deployment.yml
    
    # Deploy
    - kubectl apply -f . -n $NAMESPACE
    
    # Wait for rollout
    - kubectl rollout status deployment/backend-a-deepseek -n $NAMESPACE --timeout=10m
    - kubectl rollout status deployment/backend-b-gotocr -n $NAMESPACE --timeout=10m
    - kubectl rollout status deployment/backend-c-surya -n $NAMESPACE --timeout=10m
    
    # Smoke tests
    - sleep 30
    - curl -f https://staging-api.company.com/health || exit 1
  
  rules:
    - if: '$CI_COMMIT_BRANCH == "develop"'
  
  only:
    - develop

# ==========================================
# STAGE 5: DEPLOY PRODUCTION
# ==========================================

deploy-production:
  stage: deploy-production
  <<: *kubectl_template
  
  environment:
    name: production
    url: https://api.company.com
  
  variables:
    KUBECONFIG: $KUBECONFIG_PRODUCTION
    NAMESPACE: ocr-production
  
  script:
    - echo "Deploying to production..."
    
    # Blue-Green deployment script
    - ./scripts/blue_green_deploy.sh $CI_COMMIT_SHA
  
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
      when: manual
  
  only:
    - main
5.4 Blue-Green Deployment Script
bash#!/bin/bash
# scripts/blue_green_deploy.sh

# ============================================
# BLUE-GREEN DEPLOYMENT SCRIPT
# ============================================

set -euo pipefail

VERSION=${1:-"latest"}
NAMESPACE=${2:-"ocr-production"}

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[DEPLOY]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

# ============================================
# DETERMINE CURRENT COLOR
# ============================================

CURRENT_COLOR=$(kubectl get service backend-a-service -n $NAMESPACE -o jsonpath='{.spec.selector.color}' || echo "blue")
NEW_COLOR=$([ "$CURRENT_COLOR" = "blue" ] && echo "green" || echo "blue")

log "Current deployment: $CURRENT_COLOR"
log "New deployment: $NEW_COLOR"

# ============================================
# DEPLOY NEW COLOR
# ============================================

log "Deploying $NEW_COLOR environment..."

# Create new deployment with new color
for backend in backend-a backend-b backend-c; do
    log "Deploying $backend-$NEW_COLOR..."
    
    kubectl get deployment $backend -n $NAMESPACE -o yaml | \
        sed "s/$backend/$backend-$NEW_COLOR/g" | \
        sed "s/color: $CURRENT_COLOR/color: $NEW_COLOR/g" | \
        sed "s/version: .*/version: $VERSION/g" | \
        kubectl apply -f -
done

# ============================================
# WAIT FOR ROLLOUT
# ============================================

log "Waiting for rollout to complete..."

kubectl rollout status deployment/backend-a-$NEW_COLOR -n $NAMESPACE --timeout=15m || error "Backend A rollout failed"
kubectl rollout status deployment/backend-b-$NEW_COLOR -n $NAMESPACE --timeout=15m || error "Backend B rollout failed"
kubectl rollout status deployment/backend-c-$NEW_COLOR -n $NAMESPACE --timeout=15m || error "Backend C rollout failed"

# ============================================
# SMOKE TESTS
# ============================================

log "Running smoke tests on $NEW_COLOR..."

sleep 30

# Test through port-forward (before switching traffic)
kubectl port-forward -n $NAMESPACE deployment/backend-a-$NEW_COLOR 8001:8000 &
PF_PID=$!
sleep 5

if ! curl -f http://localhost:8001/health; then
    kill $PF_PID
    error "Smoke tests failed!"
fi

kill $PF_PID

log "✅ Smoke tests passed"

# ============================================
# SWITCH TRAFFIC
# ============================================

log "Switching traffic to $NEW_COLOR..."

# Update services to point to new color
kubectl patch service backend-a-service -n $NAMESPACE -p "{\"spec\":{\"selector\":{\"color\":\"$NEW_COLOR\"}}}"
kubectl patch service backend-b-service -n $NAMESPACE -p "{\"spec\":{\"selector\":{\"color\":\"$NEW_COLOR\"}}}"
kubectl patch service backend-c-service -n $NAMESPACE -p "{\"spec\":{\"selector\":{\"color\":\"$NEW_COLOR\"}}}"

log "Traffic switched to $NEW_COLOR"

# ============================================
# MONITOR
# ============================================

log "Monitoring for 5 minutes..."

for i in {1..10}; do
    if ! curl -f https://api.company.com/health; then
        error "Health check failed! Rolling back..."
    fi
    echo "Health check $i/10: OK"
    sleep 30
done

log "✅ Deployment successful!"

# ============================================
# CLEANUP OLD COLOR
# ============================================

log "Cleaning up $CURRENT_COLOR environment..."

kubectl delete deployment backend-a-$CURRENT_COLOR -n $NAMESPACE || true
kubectl delete deployment backend-b-$CURRENT_COLOR -n $NAMESPACE || true
kubectl delete deployment backend-c-$CURRENT_COLOR -n $NAMESPACE || true

log "✅ Blue-green deployment complete!"

6. 🔒 SSL/TLS SETUP
6.1 Let's Encrypt with Certbot
bash#!/bin/bash
# scripts/setup_ssl.sh

# ============================================
# SSL/TLS SETUP WITH LET'S ENCRYPT
# ============================================

set -euo pipefail

DOMAIN=${1:-"api.company.com"}
EMAIL=${2:-"admin@company.com"}

log() {
    echo "[SSL] $*"
}

# ============================================
# INSTALL CERTBOT
# ============================================

log "Installing Certbot..."

if ! command -v certbot &> /dev/null; then
    apt-get update
    apt-get install -y certbot python3-certbot-nginx
fi

# ============================================
# OBTAIN CERTIFICATE
# ============================================

log "Obtaining SSL certificate for $DOMAIN..."

certbot certonly \
    --nginx \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --domains "$DOMAIN" \
    --rsa-key-size 4096

# ============================================
# SETUP AUTO-RENEWAL
# ============================================

log "Setting up auto-renewal..."

# Create renewal hook
cat > /etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh << 'EOF'
#!/bin/bash
systemctl reload nginx
EOF

chmod +x /etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh

# Test renewal
certbot renew --dry-run

# Add to crontab
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet") | crontab -

log "✅ SSL setup complete!"
log "Certificate location: /etc/letsencrypt/live/$DOMAIN/"
6.2 Nginx SSL Configuration
nginx# nginx/ssl.conf

# ============================================
# NGINX SSL/TLS CONFIGURATION
# ============================================

# SSL Protocols and Ciphers
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
ssl_prefer_server_ciphers off;

# SSL Session
ssl_session_cache shared:SSL:50m;
ssl_session_timeout 1d;
ssl_session_tickets off;

# OCSP Stapling
ssl_stapling on;
ssl_stapling_verify on;
ssl_trusted_certificate /etc/letsencrypt/live/api.company.com/chain.pem;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;

# Security Headers
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;

# Diffie-Hellman parameter
ssl_dhparam /etc/nginx/ssl/dhparam.pem;
nginx# nginx/conf.d/ocr-api.conf

# ============================================
# OCR API - PRODUCTION CONFIGURATION
# ============================================

# HTTP → HTTPS Redirect
server {
    listen 80;
    listen [::]:80;
    server_name api.company.com;
    
    # ACME challenge for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.company.com;
    
    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/api.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.company.com/privkey.pem;
    
    # Include SSL config
    include /etc/nginx/ssl.conf;
    
    # Logging
    access_log /var/log/nginx/api-access.log main;
    error_log /var/log/nginx/api-error.log warn;
    
    # Client settings
    client_max_body_size 100M;
    client_body_buffer_size 128k;
    client_body_timeout 120s;
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    send_timeout 300s;
    
    # Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss;
    
    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=upload_limit:10m rate=10r/m;
    
    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
    
    # Backend A - DeepSeek
    location /v1/deepseek {
        limit_req zone=api_limit burst=10 nodelay;
        
        proxy_pass http://backend-a-service:8000;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        
        # Error handling
        proxy_intercept_errors on;
        error_page 502 503 504 = @backend_error;
    }
    
    # Backend B - GOT-OCR
    location /v1/gotocr {
        limit_req zone=api_limit burst=10 nodelay;
        
        proxy_pass http://backend-b-service:8000;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_intercept_errors on;
        error_page 502 503 504 = @backend_error;
    }
    
    # Backend C - Surya
    location /v1/surya {
        limit_req zone=api_limit burst=10 nodelay;
        
        proxy_pass http://backend-c-service:8000;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_intercept_errors on;
        error_page 502 503 504 = @backend_error;
    }
    
    # Upload endpoint (stricter rate limit)
    location /v1/upload {
        limit_req zone=upload_limit burst=5 nodelay;
        
        # Forward to appropriate backend based on query param
        proxy_pass http://backend-router:8000;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Error page
    location @backend_error {
        default_type application/json;
        return 503 '{"error": "Service temporarily unavailable", "status": 503}';
    }
    
    # Deny access to hidden files
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
6.3 Kubernetes cert-manager
yaml# kubernetes/25-cert-manager.yml

# ============================================
# CERT-MANAGER FOR AUTOMATIC SSL
# ============================================

# Install cert-manager first:
# kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    # Production Let's Encrypt server
    server: https://acme-v02.api.letsencrypt.org/directory
    
    # Email for notifications
    email: admin@company.com
    
    # Secret to store account key
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    
    # HTTP-01 challenge
    solvers:
      - http01:
          ingress:
            class: nginx

---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    # Staging Let's Encrypt server (for testing)
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    
    email: admin@company.com
    
    privateKeySecretRef:
      name: letsencrypt-staging-account-key
    
    solvers:
      - http01:
          ingress:
            class: nginx

---
# Certificate resource (automatically created by ingress annotation)
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: api-company-com-tls
  namespace: ocr-production
spec:
  secretName: api-company-com-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  commonName: api.company.com
  dnsNames:
    - api.company.com
    - www.api.company.com



PRODUCTION DEPLOYMENT GUIDE - TEIL 4 (FINAL)

7. 🔀 REVERSE PROXY (NGINX) - ADVANCED
7.1 Load Balancing Strategies
nginx# nginx/conf.d/load-balancing.conf

# ============================================
# ADVANCED LOAD BALANCING CONFIGURATION
# ============================================

# Upstream pool für Backend A (GPU - DeepSeek)
upstream backend_a_pool {
    # Load balancing method: least_conn, ip_hash, hash, random
    least_conn;
    
    # Keepalive connections
    keepalive 32;
    keepalive_requests 100;
    keepalive_timeout 60s;
    
    # Backend servers
    server backend-a-1:8000 max_fails=3 fail_timeout=30s weight=1;
    server backend-a-2:8000 max_fails=3 fail_timeout=30s weight=1;
    
    # Backup server (only used if all primary servers fail)
    # server backend-a-backup:8000 backup;
}

# Upstream pool für Backend B (GPU - GOT-OCR)
upstream backend_b_pool {
    least_conn;
    keepalive 32;
    
    server backend-b-1:8000 max_fails=3 fail_timeout=30s weight=1;
    server backend-b-2:8000 max_fails=3 fail_timeout=30s weight=1;
    server backend-b-3:8000 max_fails=3 fail_timeout=30s weight=1;
}

# Upstream pool für Backend C (CPU - Surya)
upstream backend_c_pool {
    # Weighted round-robin (CPU backend can handle more)
    least_conn;
    keepalive 64;
    
    server backend-c-1:8000 max_fails=3 fail_timeout=30s weight=2;
    server backend-c-2:8000 max_fails=3 fail_timeout=30s weight=2;
    server backend-c-3:8000 max_fails=3 fail_timeout=30s weight=2;
    server backend-c-4:8000 max_fails=3 fail_timeout=30s weight=2;
}

# Smart router - route to appropriate backend based on document complexity
upstream backend_router {
    # Hash based on request parameter
    hash $arg_complexity consistent;
    
    # Complex documents → Backend A (DeepSeek)
    server backend-a-pool:8000 max_fails=3 fail_timeout=30s;
    
    # Simple documents → Backend B (GOT-OCR)
    server backend-b-pool:8000 max_fails=2 fail_timeout=20s;
    
    # Fallback → Backend C (Surya)
    server backend-c-pool:8000 max_fails=2 fail_timeout=20s backup;
}
7.2 Advanced Caching
nginx# nginx/conf.d/caching.conf

# ============================================
# ADVANCED CACHING CONFIGURATION
# ============================================

# Cache paths
proxy_cache_path /var/cache/nginx/ocr-results
    levels=1:2
    keys_zone=ocr_cache:100m
    max_size=10g
    inactive=24h
    use_temp_path=off;

proxy_cache_path /var/cache/nginx/static
    levels=1:2
    keys_zone=static_cache:10m
    max_size=1g
    inactive=7d
    use_temp_path=off;

# Cache configuration
server {
    # ... other server config ...
    
    # Cache results endpoint
    location /v1/ocr {
        # Cache key includes: method, host, uri, and request body hash
        set $cache_key "$request_method$host$request_uri$request_body";
        
        proxy_cache ocr_cache;
        proxy_cache_key $cache_key;
        
        # Cache successful responses for 1 hour
        proxy_cache_valid 200 1h;
        
        # Cache 404 for 1 minute
        proxy_cache_valid 404 1m;
        
        # Don't cache errors
        proxy_cache_valid any 0;
        
        # Use stale cache if backend is down
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        
        # Background update
        proxy_cache_background_update on;
        
        # Lock to prevent cache stampede
        proxy_cache_lock on;
        proxy_cache_lock_timeout 5s;
        
        # Add cache status header
        add_header X-Cache-Status $upstream_cache_status always;
        
        # Bypass cache for certain conditions
        proxy_cache_bypass $http_pragma $http_authorization;
        proxy_no_cache $http_pragma $http_authorization;
        
        # Forward to backend
        proxy_pass http://backend_router;
    }
    
    # Cache static assets
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf)$ {
        proxy_cache static_cache;
        proxy_cache_valid 200 7d;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        
        add_header Cache-Control "public, immutable";
        add_header X-Cache-Status $upstream_cache_status;
        
        expires 7d;
    }
}

# Cache purge endpoint (protected)
server {
    listen 127.0.0.1:8080;
    
    location /purge {
        allow 127.0.0.1;
        deny all;
        
        proxy_cache_purge ocr_cache "$request_method$host$request_uri";
    }
}
7.3 Rate Limiting & DDoS Protection
nginx# nginx/conf.d/rate-limiting.conf

# ============================================
# RATE LIMITING & DDOS PROTECTION
# ============================================

# Define rate limiting zones
limit_req_zone $binary_remote_addr zone=global_limit:10m rate=100r/m;
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=upload_limit:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

# Connection limiting
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# Request body size limiting
client_body_buffer_size 128k;
client_max_body_size 100m;

server {
    # ... SSL config ...
    
    # Global connection limit
    limit_conn conn_limit 10;
    
    # API endpoints
    location /v1/ {
        # API rate limit
        limit_req zone=api_limit burst=20 nodelay;
        
        # Add rate limit headers
        add_header X-RateLimit-Limit "60" always;
        add_header X-RateLimit-Remaining $limit_req_remaining always;
        
        # Proxy to backend
        proxy_pass http://backend_router;
    }
    
    # Upload endpoint (stricter)
    location /v1/upload {
        limit_req zone=upload_limit burst=5 nodelay;
        
        # Larger body size for uploads
        client_max_body_size 100m;
        
        proxy_pass http://backend_router;
    }
    
    # Login endpoint (very strict)
    location /v1/auth/login {
        limit_req zone=login_limit burst=2 nodelay;
        
        proxy_pass http://backend_router;
    }
    
    # Return 429 with custom response
    error_page 429 = @ratelimit;
    location @ratelimit {
        default_type application/json;
        return 429 '{"error":"Rate limit exceeded","retry_after":60}';
    }
}

# GeoIP blocking (optional)
# Requires ngx_http_geoip_module
geo $blocked_country {
    default 0;
    # Block specific countries (example)
    # CN 1;  # China
    # RU 1;  # Russia
}

server {
    # ... other config ...
    
    if ($blocked_country) {
        return 403 '{"error":"Access denied from your location"}';
    }
}
7.4 Security Headers & Hardening
nginx# nginx/conf.d/security.conf

# ============================================
# SECURITY HARDENING
# ============================================

# Hide Nginx version
server_tokens off;
more_clear_headers Server;

# Security headers map
map $sent_http_content_type $content_security_policy {
    default "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none';";
}

server {
    # ... SSL config ...
    
    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy $content_security_policy always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    
    # HSTS (HTTP Strict Transport Security)
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    
    # Remove headers that might leak information
    proxy_hide_header X-Powered-By;
    proxy_hide_header X-AspNet-Version;
    proxy_hide_header X-AspNetMvc-Version;
    
    # Block common attack patterns
    location ~ (/\.git|/\.svn|/\.hg|/\.bzr|/\.env|/\.htaccess) {
        deny all;
        return 404;
    }
    
    # Block SQL injection attempts
    if ($args ~* "union.*select|insert.*into|drop.*table|update.*set|delete.*from") {
        return 403;
    }
    
    # Block XSS attempts
    if ($query_string ~* "(<|%3C).*script.*(>|%3E)") {
        return 403;
    }
    
    # Block path traversal
    if ($query_string ~* "\.\./") {
        return 403;
    }
}
7.5 Monitoring & Metrics
nginx# nginx/conf.d/monitoring.conf

# ============================================
# MONITORING & METRICS
# ============================================

# Prometheus metrics (requires nginx-module-vts)
server {
    listen 9145;
    server_name _;
    
    # Only allow internal access
    allow 172.25.0.0/16;  # Docker network
    allow 10.0.0.0/8;     # Internal network
    deny all;
    
    location /metrics {
        vhost_traffic_status_display;
        vhost_traffic_status_display_format prometheus;
    }
}

# Status endpoint
server {
    listen 8080;
    server_name _;
    
    allow 127.0.0.1;
    allow 172.25.0.0/16;
    deny all;
    
    location /nginx_status {
        stub_status on;
        access_log off;
    }
}

# Access log format for analytics
log_format analytics '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    '$request_time $upstream_response_time '
                    '$upstream_cache_status $ssl_protocol $ssl_cipher';

# Access log
access_log /var/log/nginx/access.log analytics;

# Error log with different levels per environment
error_log /var/log/nginx/error.log warn;

8. 🏥 HEALTH CHECKS
8.1 Application Health Check Endpoint
python# backends/common/health.py

"""
Comprehensive health check implementation
"""

from fastapi import APIRouter, status, Response
from typing import Dict, Any, List
import psutil
import asyncio
from datetime import datetime
import redis
from sqlalchemy import text
from database import engine

router = APIRouter()

# ============================================
# HEALTH CHECK LEVELS
# ============================================

async def check_database() -> Dict[str, Any]:
    """Check database connectivity and performance"""
    try:
        start = datetime.now()
        
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        latency = (datetime.now() - start).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
            "message": "Database connection successful"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "Database connection failed"
        }


async def check_redis() -> Dict[str, Any]:
    """Check Redis connectivity"""
    try:
        r = redis.from_url(os.getenv("REDIS_URL"))
        start = datetime.now()
        
        r.ping()
        
        latency = (datetime.now() - start).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
            "message": "Redis connection successful"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "Redis connection failed"
        }


async def check_gpu() -> Dict[str, Any]:
    """Check GPU availability and memory"""
    try:
        import torch
        
        if not torch.cuda.is_available():
            return {
                "status": "unavailable",
                "message": "GPU not available (CPU backend)"
            }
        
        device = torch.cuda.current_device()
        gpu_name = torch.cuda.get_device_name(device)
        
        # Memory info
        total_memory = torch.cuda.get_device_properties(device).total_memory
        allocated_memory = torch.cuda.memory_allocated(device)
        reserved_memory = torch.cuda.memory_reserved(device)
        
        memory_usage_percent = (allocated_memory / total_memory) * 100
        
        return {
            "status": "healthy",
            "device": gpu_name,
            "memory": {
                "total_gb": round(total_memory / 1024**3, 2),
                "allocated_gb": round(allocated_memory / 1024**3, 2),
                "reserved_gb": round(reserved_memory / 1024**3, 2),
                "usage_percent": round(memory_usage_percent, 2)
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "GPU check failed"
        }


async def check_model() -> Dict[str, Any]:
    """Check if model is loaded and ready"""
    try:
        from main import model  # Import model from main app
        
        if model is None:
            return {
                "status": "unhealthy",
                "message": "Model not loaded"
            }
        
        return {
            "status": "healthy",
            "model_name": os.getenv("MODEL_NAME"),
            "message": "Model loaded and ready"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "Model check failed"
        }


async def check_disk_space() -> Dict[str, Any]:
    """Check available disk space"""
    try:
        disk = psutil.disk_usage('/')
        
        usage_percent = disk.percent
        available_gb = disk.free / (1024**3)
        
        status_level = "healthy"
        if usage_percent > 90:
            status_level = "critical"
        elif usage_percent > 80:
            status_level = "warning"
        
        return {
            "status": status_level,
            "usage_percent": usage_percent,
            "available_gb": round(available_gb, 2),
            "total_gb": round(disk.total / (1024**3), 2)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def check_system_resources() -> Dict[str, Any]:
    """Check CPU and RAM usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        return {
            "status": "healthy",
            "cpu": {
                "usage_percent": cpu_percent,
                "cores": psutil.cpu_count()
            },
            "memory": {
                "usage_percent": memory.percent,
                "available_gb": round(memory.available / (1024**3), 2),
                "total_gb": round(memory.total / (1024**3), 2)
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================
# HEALTH ENDPOINTS
# ============================================

@router.get("/health")
async def health_check():
    """
    Simple health check - returns 200 if service is up
    Used by: Load balancers, Kubernetes liveness probe
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": os.getenv("BACKEND_NAME", "unknown")
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - returns 200 only if service is ready to accept traffic
    Used by: Kubernetes readiness probe
    """
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "model": await check_model()
    }
    
    # Service is ready only if all critical checks pass
    is_ready = all(
        check["status"] == "healthy" 
        for check in checks.values()
    )
    
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return Response(
        content=json.dumps({
            "ready": is_ready,
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat()
        }),
        status_code=status_code,
        media_type="application/json"
    )


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check - returns 200 if process is alive
    Used by: Kubernetes liveness probe
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check - comprehensive system status
    Used by: Monitoring, debugging
    """
    checks = await asyncio.gather(
        check_database(),
        check_redis(),
        check_gpu(),
        check_model(),
        check_disk_space(),
        check_system_resources(),
        return_exceptions=True
    )
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": os.getenv("BACKEND_NAME", "unknown"),
        "version": os.getenv("VERSION", "unknown"),
        "uptime_seconds": (datetime.now() - start_time).total_seconds(),
        "checks": {
            "database": checks[0],
            "redis": checks[1],
            "gpu": checks[2],
            "model": checks[3],
            "disk": checks[4],
            "resources": checks[5]
        }
    }
8.2 Kubernetes Health Probes
yaml# kubernetes/health-probes.yml

# ============================================
# KUBERNETES HEALTH PROBE EXAMPLES
# ============================================

apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-a-deepseek
  namespace: ocr-production
spec:
  template:
    spec:
      containers:
        - name: backend-a
          image: registry.company.com/ocr-backend-deepseek:1.0.0
          
          # ==========================================
          # STARTUP PROBE
          # ==========================================
          # Checks if application has started
          # Kubernetes will wait for this before checking liveness/readiness
          
          startupProbe:
            httpGet:
              path: /health/live
              port: 8000
            
            # Check every 10 seconds
            periodSeconds: 10
            
            # Wait up to 30 failures = 5 minutes max startup time
            failureThreshold: 30
            
            # First check after 30 seconds
            initialDelaySeconds: 30
          
          # ==========================================
          # LIVENESS PROBE
          # ==========================================
          # If this fails, Kubernetes will restart the pod
          
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
              httpHeaders:
                - name: X-Health-Check
                  value: "liveness"
            
            # Check every 30 seconds
            periodSeconds: 30
            
            # Timeout after 10 seconds
            timeoutSeconds: 10
            
            # Restart after 3 consecutive failures
            failureThreshold: 3
            
            # Wait 60 seconds before first check
            initialDelaySeconds: 60
          
          # ==========================================
          # READINESS PROBE
          # ==========================================
          # If this fails, pod is removed from service endpoints
          
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
              httpHeaders:
                - name: X-Health-Check
                  value: "readiness"
            
            # Check every 10 seconds
            periodSeconds: 10
            
            # Timeout after 5 seconds
            timeoutSeconds: 5
            
            # Remove from service after 3 consecutive failures
            failureThreshold: 3
            
            # Successful check after 1 success
            successThreshold: 1
            
            # Wait 30 seconds before first check
            initialDelaySeconds: 30
8.3 External Health Monitoring Script
bash#!/bin/bash
# scripts/health_monitor.sh

# ============================================
# EXTERNAL HEALTH MONITORING SCRIPT
# ============================================

set -euo pipefail

ENDPOINTS=(
    "https://api.company.com/health"
    "https://api.company.com/v1/deepseek/health"
    "https://api.company.com/v1/gotocr/health"
    "https://api.company.com/v1/surya/health"
)

SLACK_WEBHOOK=${SLACK_WEBHOOK:-""}
ALERT_EMAIL=${ALERT_EMAIL:-"devops@company.com"}

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================
# FUNCTIONS
# ============================================

check_endpoint() {
    local endpoint=$1
    local max_retries=3
    local timeout=10
    
    for i in $(seq 1 $max_retries); do
        response=$(curl -s -o /dev/null -w "%{http_code}" --max-time $timeout "$endpoint" || echo "000")
        
        if [ "$response" = "200" ]; then
            echo -e "${GREEN}✓${NC} $endpoint - OK"
            return 0
        fi
        
        if [ $i -lt $max_retries ]; then
            echo -e "${YELLOW}⟳${NC} $endpoint - Retry $i/$max_retries (HTTP $response)"
            sleep 5
        fi
    done
    
    echo -e "${RED}✗${NC} $endpoint - FAILED (HTTP $response)"
    return 1
}

send_slack_alert() {
    local message=$1
    
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{\"text\":\"🚨 Health Check Alert: $message\"}"
    fi
}

send_email_alert() {
    local message=$1
    
    echo "$message" | mail -s "OCR System Health Alert" "$ALERT_EMAIL"
}

# ============================================
# MAIN MONITORING LOOP
# ============================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OCR System Health Monitor"
echo "Started: $(date)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

failed_checks=0

for endpoint in "${ENDPOINTS[@]}"; do
    if ! check_endpoint "$endpoint"; then
        ((failed_checks++))
        
        # Alert on first failure
        alert_message="Endpoint failed: $endpoint"
        send_slack_alert "$alert_message"
        send_email_alert "$alert_message"
    fi
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $failed_checks -eq 0 ]; then
    echo -e "${GREEN}✅ All health checks passed${NC}"
    exit 0
else
    echo -e "${RED}❌ $failed_checks health checks failed${NC}"
    exit 1
fi

9. 🔄 ROLLING UPDATES & BLUE-GREEN DEPLOYMENT
9.1 Rolling Update Strategy
yaml# kubernetes/rolling-update-strategy.yml

# ============================================
# ROLLING UPDATE CONFIGURATION
# ============================================

apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-a-deepseek
  namespace: ocr-production
spec:
  replicas: 3
  
  # ==========================================
  # ROLLING UPDATE STRATEGY
  # ==========================================
  
  strategy:
    type: RollingUpdate
    rollingUpdate:
      # Maximum number of pods that can be unavailable during update
      # Can be absolute number (e.g., 1) or percentage (e.g., 25%)
      maxUnavailable: 1
      
      # Maximum number of pods that can be created above desired replicas
      # Can be absolute number (e.g., 1) or percentage (e.g., 25%)
      maxSurge: 1
  
  # Minimum time pod should be ready before considered available
  minReadySeconds: 30
  
  # Number of old ReplicaSets to retain
  revisionHistoryLimit: 10
  
  # Timeout for deployment progress
  progressDeadlineSeconds: 600
  
  template:
    metadata:
      labels:
        app: backend-a
        version: "{{ .Values.version }}"
    
    spec:
      # ==========================================
      # GRACEFUL SHUTDOWN
      # ==========================================
      
      # Grace period before forceful termination
      terminationGracePeriodSeconds: 60
      
      containers:
        - name: backend-a
          image: registry.company.com/ocr-backend-deepseek:{{ .Values.version }}
          
          # Lifecycle hooks
          lifecycle:
            # Pre-stop hook: drain connections before shutdown
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - |
                    # Stop accepting new requests
                    touch /tmp/shutdown
                    
                    # Wait for existing requests to complete
                    sleep 15
                    
                    # Graceful shutdown
                    kill -TERM 1
          
          # Health probes (see section 8.2)
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            periodSeconds: 30
            failureThreshold: 3
          
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            periodSeconds: 10
            failureThreshold: 3
9.2 Automated Rolling Update Script
bash#!/bin/bash
# scripts/rolling_update.sh

# ============================================
# AUTOMATED ROLLING UPDATE
# ============================================

set -euo pipefail

DEPLOYMENT=${1:-""}
IMAGE=${2:-""}
NAMESPACE=${3:-"ocr-production"}

if [ -z "$DEPLOYMENT" ] || [ -z "$IMAGE" ]; then
    echo "Usage: $0 <deployment> <image> [namespace]"
    echo "Example: $0 backend-a-deepseek registry.company.com/ocr-backend-deepseek:v1.2.3"
    exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[ROLLING UPDATE]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

# ============================================
# PRE-UPDATE CHECKS
# ============================================

log "Pre-update checks..."

# Check if deployment exists
if ! kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" &>/dev/null; then
    error "Deployment not found: $DEPLOYMENT"
fi

# Check if image exists
if ! docker manifest inspect "$IMAGE" &>/dev/null; then
    error "Image not found: $IMAGE"
fi

# Get current image
CURRENT_IMAGE=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}')
log "Current image: $CURRENT_IMAGE"
log "New image: $IMAGE"

# Check if same image
if [ "$CURRENT_IMAGE" = "$IMAGE" ]; then
    error "New image is same as current image"
fi

# ============================================
# BACKUP CURRENT STATE
# ============================================

log "Backing up current deployment..."

kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o yaml > "/tmp/${DEPLOYMENT}-backup-$(date +%Y%m%d-%H%M%S).yaml"

# ============================================
# UPDATE DEPLOYMENT
# ============================================

log "Updating deployment with new image..."

kubectl set image deployment/"$DEPLOYMENT" \
    "${DEPLOYMENT}=${IMAGE}" \
    -n "$NAMESPACE" \
    --record

# ============================================
# MONITOR ROLLOUT
# ============================================

log "Monitoring rollout progress..."

# Watch rollout status
if ! kubectl rollout status deployment/"$DEPLOYMENT" -n "$NAMESPACE" --timeout=15m; then
    error "Rollout failed or timed out!"
fi

# ============================================
# VERIFY DEPLOYMENT
# ============================================

log "Verifying deployment..."

# Wait a bit for pods to stabilize
sleep 30

# Check pod status
READY_PODS=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')
DESIRED_PODS=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')

if [ "$READY_PODS" != "$DESIRED_PODS" ]; then
    error "Not all pods are ready: $READY_PODS/$DESIRED_PODS"
fi

# Run smoke tests
log "Running smoke tests..."

POD=$(kubectl get pods -n "$NAMESPACE" -l "app=${DEPLOYMENT}" -o jsonpath='{.items[0].metadata.name}')

if ! kubectl exec -n "$NAMESPACE" "$POD" -- curl -f http://localhost:8000/health; then
    error "Smoke tests failed!"
fi

# ============================================
# SUCCESS
# ============================================

log "✅ Rolling update completed successfully!"

# Show deployment info
kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -l "app=${DEPLOYMENT}"
9.3 Canary Deployment Strategy
yaml# kubernetes/canary-deployment.yml

# ============================================
# CANARY DEPLOYMENT STRATEGY
# ============================================
# 
# Gradually shift traffic from stable to canary
# Monitor metrics, rollback if issues detected
#
# ============================================

---
# Stable deployment (v1)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-a-stable
  namespace: ocr-production
  labels:
    app: backend-a
    version: stable
spec:
  replicas: 9  # 90% of traffic
  selector:
    matchLabels:
      app: backend-a
      version: stable
  template:
    metadata:
      labels:
        app: backend-a
        version: stable
    spec:
      containers:
        - name: backend-a
          image: registry.company.com/ocr-backend-deepseek:v1.0.0

---
# Canary deployment (v2)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-a-canary
  namespace: ocr-production
  labels:
    app: backend-a
    version: canary
spec:
  replicas: 1  # 10% of traffic
  selector:
    matchLabels:
      app: backend-a
      version: canary
  template:
    metadata:
      labels:
        app: backend-a
        version: canary
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
    spec:
      containers:
        - name: backend-a
          image: registry.company.com/ocr-backend-deepseek:v2.0.0

---
# Service (routes to both stable and canary)
apiVersion: v1
kind: Service
metadata:
  name: backend-a-service
  namespace: ocr-production
spec:
  selector:
    app: backend-a  # Selects both stable and canary
  ports:
    - port: 8000
      targetPort: 8000
9.4 Canary Deployment Automation
bash#!/bin/bash
# scripts/canary_deploy.sh

# ============================================
# AUTOMATED CANARY DEPLOYMENT
# ============================================

set -euo pipefail

APP=${1:-"backend-a"}
NEW_VERSION=${2:-""}
NAMESPACE=${3:-"ocr-production"}

if [ -z "$NEW_VERSION" ]; then
    echo "Usage: $0 <app> <version> [namespace]"
    exit 1
fi

# Canary stages (percentage of traffic)
CANARY_STAGES=(10 25 50 75 100)

# Monitoring duration per stage (seconds)
MONITOR_DURATION=300

# ============================================
# FUNCTIONS
# ============================================

get_error_rate() {
    local version=$1
    
    # Query Prometheus for error rate
    ERROR_RATE=$(curl -s "http://prometheus:9090/api/v1/query?query=rate(http_requests_total{app=\"$APP\",version=\"$version\",status=~\"5..\"}[5m])" | \
        jq -r '.data.result[0].value[1] // 0')
    
    echo "$ERROR_RATE"
}

get_latency() {
    local version=$1
    
    # Query Prometheus for P95 latency
    LATENCY=$(curl -s "http://prometheus:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket{app=\"$APP\",version=\"$version\"}[5m]))" | \
        jq -r '.data.result[0].value[1] // 0')
    
    echo "$LATENCY"
}

scale_deployment() {
    local version=$1
    local replicas=$2
    
    kubectl scale deployment "${APP}-${version}" \
        -n "$NAMESPACE" \
        --replicas="$replicas"
}

rollback() {
    echo "❌ Canary deployment failed! Rolling back..."
    
    # Scale canary to 0
    scale_deployment "canary" 0
    
    # Scale stable to full capacity
    scale_deployment "stable" 10
    
    # Delete canary deployment
    kubectl delete deployment "${APP}-canary" -n "$NAMESPACE"
    
    exit 1
}

# ============================================
# DEPLOY CANARY
# ============================================

echo "Deploying canary version: $NEW_VERSION"

# Create canary deployment (initially 0 replicas)
kubectl create deployment "${APP}-canary" \
    --image="registry.company.com/ocr-${APP}:${NEW_VERSION}" \
    -n "$NAMESPACE" \
    --dry-run=client -o yaml | \
    kubectl label --local -f - version=canary -o yaml | \
    kubectl apply -f -

# Wait for canary to be ready
kubectl wait --for=condition=available \
    deployment/"${APP}-canary" \
    -n "$NAMESPACE" \
    --timeout=10m

# ============================================
# GRADUAL TRAFFIC SHIFT
# ============================================

TOTAL_REPLICAS=10

for stage in "${CANARY_STAGES[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Stage: ${stage}% traffic to canary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Calculate replicas
    CANARY_REPLICAS=$((TOTAL_REPLICAS * stage / 100))
    STABLE_REPLICAS=$((TOTAL_REPLICAS - CANARY_REPLICAS))
    
    # Scale deployments
    scale_deployment "canary" "$CANARY_REPLICAS"
    scale_deployment "stable" "$STABLE_REPLICAS"
    
    # Monitor metrics
    echo "Monitoring for ${MONITOR_DURATION}s..."
    
    for ((i=0; i<MONITOR_DURATION; i+=30)); do
        CANARY_ERROR_RATE=$(get_error_rate "canary")
        STABLE_ERROR_RATE=$(get_error_rate "stable")
        
        CANARY_LATENCY=$(get_latency "canary")
        STABLE_LATENCY=$(get_latency "stable")
        
        echo "  Canary: Error Rate=${CANARY_ERROR_RATE}, Latency=${CANARY_LATENCY}s"
        echo "  Stable: Error Rate=${STABLE_ERROR_RATE}, Latency=${STABLE_LATENCY}s"
        
        # Check if canary has higher error rate
        if (( $(echo "$CANARY_ERROR_RATE > $STABLE_ERROR_RATE * 2" | bc -l) )); then
            echo "⚠️  Canary error rate too high!"
            rollback
        fi
        
        # Check if canary has much higher latency
        if (( $(echo "$CANARY_LATENCY > $STABLE_LATENCY * 1.5" | bc -l) )); then
            echo "⚠️  Canary latency too high!"
            rollback
        fi
        
        sleep 30
    done
    
    echo "✓ Stage ${stage}% passed"
done

# ============================================
# FINALIZE
# ============================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Finalizing canary deployment..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Promote canary to stable
kubectl set image deployment/"${APP}-stable" \
    "${APP}=registry.company.com/ocr-${APP}:${NEW_VERSION}" \
    -n "$NAMESPACE"

# Wait for stable to roll out
kubectl rollout status deployment/"${APP}-stable" -n "$NAMESPACE"

# Delete canary
kubectl delete deployment "${APP}-canary" -n "$NAMESPACE"

# Scale stable back to full capacity
scale_deployment "stable" "$TOTAL_REPLICAS"

echo "✅ Canary deployment completed successfully!"



PRODUCTION DEPLOYMENT GUIDE - TEIL 5 (ABSOLUT FINAL)

10. 📊 MONITORING & LOGGING
10.1 Prometheus Monitoring Stack
yaml# monitoring/prometheus-complete.yml

# ============================================
# COMPLETE PROMETHEUS MONITORING SETUP
# ============================================

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'ocr-production'
    environment: 'production'

# ==========================================
# ALERTING
# ==========================================

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# ==========================================
# RULE FILES
# ==========================================

rule_files:
  - 'alerts/application.yml'
  - 'alerts/infrastructure.yml'
  - 'alerts/gpu.yml'
  - 'alerts/business.yml'

# ==========================================
# SCRAPE CONFIGS
# ==========================================

scrape_configs:
  
  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  
  # ==========================================
  # APPLICATION METRICS
  # ==========================================
  
  # Backend A - DeepSeek
  - job_name: 'backend-a'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - ocr-production
    
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: backend-a
      
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
      
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: pod
      
      - source_labels: [__meta_kubernetes_namespace]
        action: replace
        target_label: namespace
  
  # Backend B - GOT-OCR
  - job_name: 'backend-b'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - ocr-production
    
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: backend-b
      # ... same as backend-a
  
  # Backend C - Surya
  - job_name: 'backend-c'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - ocr-production
    
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: backend-c
      # ... same as backend-a
  
  # ==========================================
  # INFRASTRUCTURE METRICS
  # ==========================================
  
  # GPU Metrics
  - job_name: 'nvidia-gpu'
    static_configs:
      - targets:
          - 'gpu-server-1:9835'
          - 'gpu-server-2:9835'
        labels:
          tier: 'gpu'
  
  # Node Exporter (System Metrics)
  - job_name: 'node-exporter'
    kubernetes_sd_configs:
      - role: node
    
    relabel_configs:
      - source_labels: [__address__]
        regex: '(.*):10250'
        replacement: '${1}:9100'
        target_label: __address__
  
  # PostgreSQL
  - job_name: 'postgresql'
    static_configs:
      - targets: ['postgres-exporter:9187']
        labels:
          service: 'postgresql'
  
  # Redis
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
        labels:
          service: 'redis'
  
  # Nginx
  - job_name: 'nginx'
    static_configs:
      - targets: ['nginx:9145']
        labels:
          service: 'nginx'
  
  # ==========================================
  # KUBERNETES METRICS
  # ==========================================
  
  - job_name: 'kubernetes-apiservers'
    kubernetes_sd_configs:
      - role: endpoints
    
    scheme: https
    tls_config:
      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    
    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
    
    relabel_configs:
      - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
        action: keep
        regex: default;kubernetes;https
  
  - job_name: 'kubernetes-nodes'
    kubernetes_sd_configs:
      - role: node
    
    scheme: https
    tls_config:
      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    
    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
  
  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
10.2 Application Alert Rules
yaml# monitoring/alerts/application.yml

# ============================================
# APPLICATION ALERT RULES
# ============================================

groups:
  - name: application_alerts
    interval: 30s
    rules:
      
      # ==========================================
      # ERROR RATE ALERTS
      # ==========================================
      
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) 
          / 
          rate(http_requests_total[5m]) 
          > 0.05
        for: 5m
        labels:
          severity: critical
          component: application
        annotations:
          summary: "High error rate detected"
          description: |
            Error rate is {{ $value | humanizePercentage }} 
            for {{ $labels.backend }} backend
          runbook_url: "https://wiki.company.com/runbooks/high-error-rate"
      
      - alert: ElevatedErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) 
          / 
          rate(http_requests_total[5m]) 
          > 0.01
        for: 10m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "Elevated error rate"
          description: "Error rate is {{ $value | humanizePercentage }}"
      
      # ==========================================
      # LATENCY ALERTS
      # ==========================================
      
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, 
            rate(http_request_duration_seconds_bucket[5m])
          ) > 5
        for: 10m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "High request latency (P95)"
          description: |
            P95 latency is {{ $value }}s 
            for {{ $labels.backend }} backend
      
      - alert: CriticalLatency
        expr: |
          histogram_quantile(0.95, 
            rate(http_request_duration_seconds_bucket[5m])
          ) > 10
        for: 5m
        labels:
          severity: critical
          component: application
        annotations:
          summary: "Critical request latency!"
          description: "P95 latency is {{ $value }}s - SLA breach!"
      
      # ==========================================
      # THROUGHPUT ALERTS
      # ==========================================
      
      - alert: LowThroughput
        expr: |
          rate(http_requests_total[5m]) < 0.1
        for: 15m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "Low request throughput"
          description: |
            Request rate is {{ $value | humanize }} req/s 
            (expected > 0.1 req/s)
      
      - alert: NoTraffic
        expr: |
          rate(http_requests_total[5m]) == 0
        for: 5m
        labels:
          severity: critical
          component: application
        annotations:
          summary: "No traffic detected!"
          description: "Backend {{ $labels.backend }} receiving no requests"
      
      # ==========================================
      # QUEUE ALERTS
      # ==========================================
      
      - alert: QueueBacklog
        expr: queue_size > 100
        for: 10m
        labels:
          severity: warning
          component: queue
        annotations:
          summary: "Processing queue backlog"
          description: "Queue size is {{ $value }} (threshold: 100)"
      
      - alert: QueueCritical
        expr: queue_size > 500
        for: 5m
        labels:
          severity: critical
          component: queue
        annotations:
          summary: "Critical queue backlog!"
          description: "Queue size is {{ $value }} - system overloaded!"
      
      # ==========================================
      # AVAILABILITY ALERTS
      # ==========================================
      
      - alert: ServiceDown
        expr: up{job=~"backend-.*"} == 0
        for: 1m
        labels:
          severity: critical
          component: application
        annotations:
          summary: "Service is down!"
          description: "{{ $labels.job }} on {{ $labels.instance }} is down"
      
      - alert: PodCrashLooping
        expr: |
          rate(kube_pod_container_status_restarts_total[15m]) > 0
        for: 5m
        labels:
          severity: critical
          component: kubernetes
        annotations:
          summary: "Pod crash looping"
          description: |
            Pod {{ $labels.pod }} in namespace {{ $labels.namespace }} 
            is crash looping
      
      # ==========================================
      # BUSINESS METRICS
      # ==========================================
      
      - alert: LowOCRAccuracy
        expr: ocr_accuracy_score < 0.95
        for: 15m
        labels:
          severity: warning
          component: business
        annotations:
          summary: "Low OCR accuracy detected"
          description: |
            OCR accuracy is {{ $value | humanizePercentage }} 
            (threshold: 95%)
      
      - alert: HighGermanUmlautErrors
        expr: |
          rate(ocr_umlaut_errors_total[5m]) 
          / 
          rate(ocr_documents_total[5m]) 
          > 0.01
        for: 10m
        labels:
          severity: critical
          component: business
        annotations:
          summary: "High German umlaut recognition errors!"
          description: |
            Umlaut error rate is {{ $value | humanizePercentage }}
            This violates our core requirement!
10.3 Centralized Logging - ELK Stack
yaml# logging/elasticsearch.yml

# ============================================
# ELASTICSEARCH CONFIGURATION
# ============================================

apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: elasticsearch
  namespace: ocr-logging
spec:
  serviceName: elasticsearch
  replicas: 3
  selector:
    matchLabels:
      app: elasticsearch
  template:
    metadata:
      labels:
        app: elasticsearch
    spec:
      containers:
        - name: elasticsearch
          image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
          
          env:
            - name: cluster.name
              value: "ocr-logs"
            - name: node.name
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: discovery.seed_hosts
              value: "elasticsearch-0.elasticsearch,elasticsearch-1.elasticsearch,elasticsearch-2.elasticsearch"
            - name: cluster.initial_master_nodes
              value: "elasticsearch-0,elasticsearch-1,elasticsearch-2"
            - name: ES_JAVA_OPTS
              value: "-Xms2g -Xmx2g"
            - name: xpack.security.enabled
              value: "false"
          
          ports:
            - containerPort: 9200
              name: http
            - containerPort: 9300
              name: transport
          
          volumeMounts:
            - name: data
              mountPath: /usr/share/elasticsearch/data
          
          resources:
            requests:
              memory: "4Gi"
              cpu: "1"
            limits:
              memory: "4Gi"
              cpu: "2"
  
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 100Gi

---
# Kibana Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kibana
  namespace: ocr-logging
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kibana
  template:
    metadata:
      labels:
        app: kibana
    spec:
      containers:
        - name: kibana
          image: docker.elastic.co/kibana/kibana:8.11.0
          
          env:
            - name: ELASTICSEARCH_HOSTS
              value: "http://elasticsearch:9200"
            - name: SERVER_NAME
              value: "kibana"
            - name: SERVER_HOST
              value: "0.0.0.0"
          
          ports:
            - containerPort: 5601
          
          resources:
            requests:
              memory: "1Gi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "1"

---
# Logstash Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: logstash
  namespace: ocr-logging
spec:
  replicas: 2
  selector:
    matchLabels:
      app: logstash
  template:
    metadata:
      labels:
        app: logstash
    spec:
      containers:
        - name: logstash
          image: docker.elastic.co/logstash/logstash:8.11.0
          
          ports:
            - containerPort: 5044
              name: beats
            - containerPort: 9600
              name: http
          
          volumeMounts:
            - name: config
              mountPath: /usr/share/logstash/pipeline
          
          resources:
            requests:
              memory: "2Gi"
              cpu: "1"
            limits:
              memory: "4Gi"
              cpu: "2"
      
      volumes:
        - name: config
          configMap:
            name: logstash-config
10.4 Logstash Pipeline Configuration
ruby# logging/logstash-pipeline.conf

# ============================================
# LOGSTASH PIPELINE CONFIGURATION
# ============================================

input {
  # Beats input (from Filebeat)
  beats {
    port => 5044
    codec => json
  }
  
  # Direct TCP input (for structured logs)
  tcp {
    port => 5000
    codec => json_lines
  }
}

filter {
  # ==========================================
  # PARSE APPLICATION LOGS
  # ==========================================
  
  if [source] =~ /backend/ {
    
    # Parse JSON logs
    json {
      source => "message"
      target => "app"
    }
    
    # Extract backend name from source
    grok {
      match => { "source" => "/var/log/%{DATA:backend}/" }
    }
    
    # Add timestamp
    date {
      match => [ "[app][timestamp]", "ISO8601" ]
      target => "@timestamp"
    }
    
    # Extract log level
    mutate {
      add_field => { "log_level" => "%{[app][level]}" }
    }
    
    # Extract request ID for tracing
    if [app][request_id] {
      mutate {
        add_field => { "request_id" => "%{[app][request_id]}" }
      }
    }
    
    # Extract user information
    if [app][user_id] {
      mutate {
        add_field => { "user_id" => "%{[app][user_id]}" }
      }
    }
    
    # Extract error information
    if [app][error] {
      mutate {
        add_field => { 
          "error_type" => "%{[app][error][type]}"
          "error_message" => "%{[app][error][message]}"
        }
        add_tag => ["error"]
      }
    }
    
    # Extract OCR-specific metrics
    if [app][ocr_metrics] {
      mutate {
        add_field => {
          "ocr_duration" => "%{[app][ocr_metrics][duration]}"
          "ocr_accuracy" => "%{[app][ocr_metrics][accuracy]}"
          "document_type" => "%{[app][ocr_metrics][document_type]}"
        }
      }
    }
  }
  
  # ==========================================
  # PARSE NGINX ACCESS LOGS
  # ==========================================
  
  if [source] =~ /nginx/ {
    grok {
      match => { 
        "message" => '%{IPORHOST:client_ip} - %{DATA:user} \[%{HTTPDATE:timestamp}\] "%{WORD:method} %{DATA:url} HTTP/%{NUMBER:http_version}" %{NUMBER:status_code} %{NUMBER:bytes_sent} "%{DATA:referrer}" "%{DATA:user_agent}" %{NUMBER:request_time} %{NUMBER:upstream_time}'
      }
    }
    
    # Convert numeric fields
    mutate {
      convert => {
        "status_code" => "integer"
        "bytes_sent" => "integer"
        "request_time" => "float"
        "upstream_time" => "float"
      }
    }
    
    # Tag errors
    if [status_code] >= 400 {
      mutate {
        add_tag => ["error"]
      }
    }
    
    if [status_code] >= 500 {
      mutate {
        add_tag => ["critical"]
      }
    }
  }
  
  # ==========================================
  # GEOIP ENRICHMENT
  # ==========================================
  
  if [client_ip] {
    geoip {
      source => "client_ip"
      target => "geoip"
    }
  }
  
  # ==========================================
  # REMOVE UNNECESSARY FIELDS
  # ==========================================
  
  mutate {
    remove_field => ["host", "agent", "ecs", "input"]
  }
}

output {
  # ==========================================
  # ELASTICSEARCH OUTPUT
  # ==========================================
  
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    
    # Index pattern: ocr-logs-backend-YYYY.MM.DD
    index => "ocr-logs-%{backend}-%{+YYYY.MM.dd}"
    
    # Document ID (for deduplication)
    document_id => "%{[@metadata][fingerprint]}"
  }
  
  # ==========================================
  # CONDITIONAL OUTPUTS
  # ==========================================
  
  # Send errors to separate index
  if "error" in [tags] {
    elasticsearch {
      hosts => ["elasticsearch:9200"]
      index => "ocr-errors-%{+YYYY.MM.dd}"
    }
  }
  
  # Send critical logs to alerting system
  if "critical" in [tags] {
    http {
      url => "http://alertmanager:9093/api/v1/alerts"
      http_method => "post"
      format => "json"
    }
  }
  
  # Debug output (only in development)
  # stdout { codec => rubydebug }
}
10.5 Structured Logging Implementation
python# backends/common/logging_config.py

"""
Structured logging configuration
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict
import os
import traceback

class StructuredLogger:
    """
    Structured JSON logger for consistent logging across backends
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
        
        # Console handler with JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        self.logger.addHandler(handler)
        
        # Context (added to all logs)
        self.context = {
            "backend": os.getenv("BACKEND_NAME", "unknown"),
            "environment": os.getenv("ENVIRONMENT", "unknown"),
            "version": os.getenv("VERSION", "unknown")
        }
    
    def _build_log_entry(
        self, 
        level: str, 
        message: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Build structured log entry"""
        
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            **self.context,
            **kwargs
        }
        
        return entry
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        entry = self._build_log_entry("INFO", message, **kwargs)
        self.logger.info(json.dumps(entry))
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        entry = self._build_log_entry("WARNING", message, **kwargs)
        self.logger.warning(json.dumps(entry))
    
    def error(self, message: str, error: Exception = None, **kwargs):
        """Log error message"""
        
        error_info = {}
        if error:
            error_info = {
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc()
                }
            }
        
        entry = self._build_log_entry("ERROR", message, **error_info, **kwargs)
        self.logger.error(json.dumps(entry))
    
    def critical(self, message: str, **kwargs):
        """Log critical message"""
        entry = self._build_log_entry("CRITICAL", message, **kwargs)
        self.logger.critical(json.dumps(entry))
    
    def ocr_event(
        self,
        event_type: str,
        duration: float,
        accuracy: float = None,
        document_type: str = None,
        **kwargs
    ):
        """Log OCR-specific event"""
        
        ocr_metrics = {
            "ocr_metrics": {
                "event_type": event_type,
                "duration": duration,
                "accuracy": accuracy,
                "document_type": document_type
            }
        }
        
        entry = self._build_log_entry(
            "INFO", 
            f"OCR event: {event_type}",
            **ocr_metrics,
            **kwargs
        )
        
        self.logger.info(json.dumps(entry))


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter"""
    
    def format(self, record: logging.LogRecord) -> str:
        # If message is already JSON, return as-is
        try:
            json.loads(record.getMessage())
            return record.getMessage()
        except (json.JSONDecodeError, ValueError):
            # Otherwise, create JSON structure
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }
            
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            
            return json.dumps(log_data)


# ============================================
# USAGE EXAMPLE
# ============================================

# Initialize logger
logger = StructuredLogger("backend-a")

# Simple log
logger.info("Application started")

# Log with context
logger.info(
    "Processing OCR request",
    request_id="abc123",
    user_id="user456",
    document_type="invoice"
)

# Log OCR event
logger.ocr_event(
    event_type="document_processed",
    duration=2.5,
    accuracy=0.98,
    document_type="invoice",
    request_id="abc123"
)

# Log error
try:
    # ... some operation
    raise ValueError("Invalid document format")
except Exception as e:
    logger.error(
        "OCR processing failed",
        error=e,
        request_id="abc123",
        document_type="invoice"
    )

11. 🔍 TROUBLESHOOTING
11.1 Common Issues & Solutions
markdown# TROUBLESHOOTING GUIDE

## 🐛 COMMON DEPLOYMENT ISSUES

### Issue 1: Pods Stuck in "Pending" State

**Symptoms:**
```bash
$ kubectl get pods -n ocr-production
NAME                      READY   STATUS    RESTARTS   AGE
backend-a-xxx             0/1     Pending   0          5m
```

**Diagnosis:**
```bash
# Check pod events
kubectl describe pod backend-a-xxx -n ocr-production

# Common reasons:
# - Insufficient resources
# - Node selector not matching
# - PVC not available
```

**Solution:**
```bash
# Check available resources
kubectl top nodes

# If GPU required but not available:
kubectl get nodes -l nvidia.com/gpu.present=true

# Check PVC status
kubectl get pvc -n ocr-production

# Fix:
# 1. Scale down other deployments
# 2. Add more nodes
# 3. Fix node labels
# 4. Create missing PVCs
```

---

### Issue 2: High Memory Usage / OOM Kills

**Symptoms:**
```bash
# Pod restarts frequently
RESTARTS: 5

# In logs:
Killed
```

**Diagnosis:**
```bash
# Check memory usage
kubectl top pods -n ocr-production

# Check pod events for OOM
kubectl get events -n ocr-production --sort-by='.lastTimestamp'
```

**Solution:**
```yaml
# Increase memory limits
resources:
  limits:
    memory: "32Gi"  # Increase from 24Gi
  requests:
    memory: "24Gi"  # Increase requests too

# Or optimize application:
# - Reduce batch size
# - Enable model quantization
# - Clear GPU cache regularly
```

---

### Issue 3: SSL Certificate Issues

**Symptoms:**
```bash
$ curl https://api.company.com/health
curl: (60) SSL certificate problem: certificate has expired
```

**Diagnosis:**
```bash
# Check certificate expiry
openssl s_client -connect api.company.com:443 -servername api.company.com </dev/null 2>/dev/null | \
  openssl x509 -noout -dates

# Check cert-manager status
kubectl get certificate -n ocr-production
kubectl describe certificate api-company-com-tls -n ocr-production
```

**Solution:**
```bash
# Manual renewal
certbot renew --force-renewal

# For cert-manager:
# Delete and recreate certificate
kubectl delete certificate api-company-com-tls -n ocr-production
kubectl apply -f kubernetes/25-cert-manager.yml

# Check renewal
kubectl get certificate -n ocr-production -w
```

---

### Issue 4: Database Connection Failures

**Symptoms:**
```
ERROR: could not connect to database
FATAL: remaining connection slots are reserved
```

**Diagnosis:**
```bash
# Check PostgreSQL status
kubectl exec -it postgres-0 -n ocr-production -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check connection limits
kubectl exec -it postgres-0 -n ocr-production -- psql -U postgres -c "SHOW max_connections;"
```

**Solution:**
```bash
# Increase connection pool
# In postgres ConfigMap:
max_connections = 200  # Increase from 100

# Restart PostgreSQL
kubectl rollout restart statefulset/postgres -n ocr-production

# Or optimize application connection pooling
DB_POOL_SIZE=10  # Reduce per-backend pool
```

---

### Issue 5: Slow OCR Processing

**Symptoms:**
```
Request timeout after 300 seconds
P95 latency: 45s (expected < 10s)
```

**Diagnosis:**
```bash
# Check GPU utilization
nvidia-smi

# Check queue size
curl -s http://api.company.com/metrics | grep queue_size

# Check logs for errors
kubectl logs -f backend-a-xxx -n ocr-production | grep ERROR
```

**Solution:**
```bash
# 1. Scale up replicas
kubectl scale deployment backend-a-deepseek -n ocr-production --replicas=5

# 2. Optimize batch processing
MAX_BATCH_SIZE=8  # Increase batch size

# 3. Check model caching
# Ensure models are cached in PVC

# 4. Add more GPU backends
# Deploy additional GPU servers
```

---

### Issue 6: High Error Rate (5xx)

**Symptoms:**
```
Error rate: 8% (threshold: < 1%)
Many 503 Service Unavailable
```

**Diagnosis:**
```bash
# Check backend health
for pod in $(kubectl get pods -n ocr-production -l app=backend-a -o name); do
  echo "$pod:"
  kubectl exec -n ocr-production "$pod" -- curl -s http://localhost:8000/health
done

# Check nginx logs
kubectl logs -f nginx-xxx -n ocr-production | grep " 5[0-9][0-9] "

# Check Prometheus
# Query: rate(http_requests_total{status=~"5.."}[5m])
```

**Solution:**
```bash
# 1. Check resource constraints
kubectl top pods -n ocr-production

# 2. Increase timeouts
# In nginx config:
proxy_read_timeout 600s;

# 3. Scale up backends
kubectl scale deployment backend-a-deepseek --replicas=4

# 4. Check for application bugs
kubectl logs backend-a-xxx -n ocr-production --tail=100
```

---

### Issue 7: Ingress Not Working

**Symptoms:**
```bash
$ curl https://api.company.com
curl: (7) Failed to connect to api.company.com port 443: Connection refused
```

**Diagnosis:**
```bash
# Check ingress status
kubectl get ingress -n ocr-production
kubectl describe ingress ocr-ingress -n ocr-production

# Check ingress controller
kubectl get pods -n ingress-nginx
kubectl logs -f ingress-nginx-controller-xxx -n ingress-nginx

# Check service
kubectl get service -n ocr-production
```

**Solution:**
```bash
# 1. Verify DNS
nslookup api.company.com

# 2. Check ingress controller installation
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml

# 3. Verify certificate
kubectl get certificate -n ocr-production

# 4. Check backend services
kubectl get endpoints -n ocr-production
```
11.2 Debugging Commands Cheat Sheet
bash#!/bin/bash
# scripts/debug_cheatsheet.sh

# ============================================
# DEBUGGING COMMANDS CHEAT SHEET
# ============================================

cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║              KUBERNETES DEBUGGING COMMANDS                    ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POD DEBUGGING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# List all pods
kubectl get pods -n ocr-production

# Pod details
kubectl describe pod <pod-name> -n ocr-production

# Pod logs (live)
kubectl logs -f <pod-name> -n ocr-production

# Previous pod logs (after crash)
kubectl logs <pod-name> -n ocr-production --previous

# Logs from specific container
kubectl logs <pod-name> -c <container-name> -n ocr-production

# Execute command in pod
kubectl exec -it <pod-name> -n ocr-production -- bash

# Copy files from pod
kubectl cp ocr-production/<pod-name>:/path/to/file ./local-file

# Port forward to pod
kubectl port-forward <pod-name> 8000:8000 -n ocr-production

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEPLOYMENT DEBUGGING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Deployment status
kubectl get deployments -n ocr-production

# Deployment details
kubectl describe deployment <deployment-name> -n ocr-production

# Rollout status
kubectl rollout status deployment/<deployment-name> -n ocr-production

# Rollout history
kubectl rollout history deployment/<deployment-name> -n ocr-production

# Rollback to previous version
kubectl rollout undo deployment/<deployment-name> -n ocr-production

# Rollback to specific revision
kubectl rollout undo deployment/<deployment-name> --to-revision=2 -n ocr-production

# Scale deployment
kubectl scale deployment <deployment-name> --replicas=5 -n ocr-production

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SERVICE & NETWORKING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# List services
kubectl get services -n ocr-production

# Service endpoints
kubectl get endpoints -n ocr-production

# Service details
kubectl describe service <service-name> -n ocr-production

# Ingress status
kubectl get ingress -n ocr-production
kubectl describe ingress <ingress-name> -n ocr-production

# Test service connectivity
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- bash
# Inside pod:
# curl http://backend-a-service:8000/health

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESOURCE MONITORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Node resources
kubectl top nodes

# Pod resources
kubectl top pods -n ocr-production

# Resource quotas
kubectl get resourcequota -n ocr-production

# Limit ranges
kubectl get limitrange -n ocr-production

# PVC status
kubectl get pvc -n ocr-production

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVENTS & LOGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Recent events
kubectl get events -n ocr-production --sort-by='.lastTimestamp'

# Watch events
kubectl get events -n ocr-production --watch

# Events for specific resource
kubectl describe <resource-type> <resource-name> -n ocr-production

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIGURATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ConfigMaps
kubectl get configmap -n ocr-production
kubectl describe configmap <name> -n ocr-production

# Secrets
kubectl get secrets -n ocr-production
kubectl describe secret <name> -n ocr-production

# Get secret value (base64 encoded)
kubectl get secret <name> -n ocr-production -o jsonpath='{.data.key}' | base64 -d

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOCKER DEBUGGING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Container status
docker ps -a

# Container logs
docker logs -f <container-name>

# Execute in container
docker exec -it <container-name> bash

# Container stats
docker stats <container-name>

# Inspect container
docker inspect <container-name>

# Container processes
docker top <container-name>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOCKER COMPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Service status
docker-compose ps

# Service logs
docker-compose logs -f <service>

# Restart service
docker-compose restart <service>

# Rebuild service
docker-compose up -d --build <service>

# Execute in service
docker-compose exec <service> bash

EOF

12. ✅ CHECKLISTS & QUICK REFERENCE
12.1 Pre-Deployment Checklist
markdown# 📋 PRE-DEPLOYMENT CHECKLIST

## ☑️ CODE QUALITY

- [ ] All tests passing (unit, integration, e2e)
- [ ] Code coverage > 80%
- [ ] Linting passed (black, flake8, mypy)
- [ ] Security scan completed (no critical issues)
- [ ] Peer review completed
- [ ] Documentation updated

## ☑️ CONFIGURATION

- [ ] Environment variables validated
- [ ] Secrets encrypted (Ansible Vault)
- [ ] Database migrations tested
- [ ] Feature flags configured
- [ ] Resource limits defined
- [ ] Health check endpoints working

## ☑️ INFRASTRUCTURE

- [ ] Terraform plan reviewed
- [ ] Required resources available
- [ ] SSL certificates valid
- [ ] DNS records configured
- [ ] Firewall rules updated
- [ ] Backup systems tested

## ☑️ MONITORING

- [ ] Prometheus alerts configured
- [ ] Grafana dashboards created
- [ ] Log aggregation working
- [ ] APM (Application Performance Monitoring) setup
- [ ] Error tracking (Sentry) configured
- [ ] Slack notifications tested

## ☑️ SECURITY

- [ ] API keys rotated
- [ ] Secrets not in Git
- [ ] HTTPS enforced
- [ ] Rate limiting configured
- [ ] CORS properly set
- [ ] Security headers added

## ☑️ DISASTER RECOVERY

- [ ] Backup strategy defined
- [ ] Backup tested (restore)
- [ ] Rollback plan documented
- [ ] On-call schedule updated
- [ ] Runbooks updated
- [ ] Team notified

## ☑️ PERFORMANCE

- [ ] Load testing completed
- [ ] Performance benchmarks met
- [ ] Cache strategy validated
- [ ] Database queries optimized
- [ ] CDN configured
- [ ] Image optimization done

## ☑️ COMPLIANCE

- [ ] GDPR compliance checked
- [ ] Data retention policy set
- [ ] Audit logging enabled
- [ ] Terms of Service updated
- [ ] Privacy Policy updated
- [ ] Legal review completed (if needed)
12.2 Deployment Day Checklist
markdown# 🚀 DEPLOYMENT DAY CHECKLIST

## 🕐 T-24 Hours

- [ ] Final code freeze
- [ ] Staging deployment tested
- [ ] Load tests completed
- [ ] Stakeholders notified
- [ ] Maintenance window scheduled
- [ ] Team availability confirmed

## 🕑 T-1 Hour

- [ ] All tests passing
- [ ] Backup created
- [ ] Rollback plan ready
- [ ] Monitoring dashboards open
- [ ] Team in communication channel
- [ ] Change ticket created

## 🕒 Deployment Start

- [ ] Maintenance mode enabled (if needed)
- [ ] Start deployment
  - [ ] Database migrations (if any)
  - [ ] Backend deployments
  - [ ] Frontend deployment
- [ ] Monitor logs for errors
- [ ] Check metrics/dashboards

## 🕓 Post-Deployment (T+15 min)

- [ ] All services healthy
- [ ] Smoke tests passing
- [ ] Health checks green
- [ ] No error spikes in logs
- [ ] Response times normal
- [ ] Database connections stable

## 🕔 Post-Deployment (T+1 hour)

- [ ] Load tests passed
- [ ] User acceptance testing
- [ ] Business metrics normal
- [ ] No customer complaints
- [ ] Performance metrics acceptable
- [ ] Cache hit rate good

## 🕕 Post-Deployment (T+4 hours)

- [ ] All metrics stable
- [ ] No memory leaks
- [ ] No connection leaks
- [ ] Logs look clean
- [ ] Disable maintenance mode
- [ ] Team notified: SUCCESS

## 🔄 If Issues Arise

- [ ] Assess severity
- [ ] Try quick fix OR
- [ ] Execute rollback plan
- [ ] Notify stakeholders
- [ ] Post-mortem scheduled
12.3 Quick Reference Commands
bash# ============================================
# QUICK REFERENCE - MOST USED COMMANDS
# ============================================

# ==========================================
# DEPLOYMENT
# ==========================================

# Deploy to production
./scripts/deploy.sh production

# Deploy specific service
kubectl set image deployment/backend-a-deepseek \
  backend-a-deepseek=registry.company.com/ocr-backend-deepseek:v1.2.3 \
  -n ocr-production

# Rollback deployment
kubectl rollout undo deployment/backend-a-deepseek -n ocr-production

# ==========================================
# HEALTH CHECKS
# ==========================================

# Quick health check all backends
curl https://api.company.com/health
curl https://api.company.com/v1/deepseek/health
curl https://api.company.com/v1/gotocr/health
curl https://api.company.com/v1/surya/health

# Detailed health check
curl https://api.company.com/health/detailed | jq

# ==========================================
# LOGS
# ==========================================

# Tail logs (all backends)
kubectl logs -f -l app=backend-a -n ocr-production --tail=100

# Logs with grep
kubectl logs -l app=backend-a -n ocr-production | grep ERROR

# Docker logs
docker-compose logs -f --tail=100 backend-a

# ==========================================
# MONITORING
# ==========================================

# Prometheus queries
curl 'http://prometheus:9090/api/v1/query?query=up{job="backend-a"}'

# Pod resource usage
kubectl top pods -n ocr-production

# Node resource usage
kubectl top nodes

# ==========================================
# SCALING
# ==========================================

# Scale deployment
kubectl scale deployment backend-a-deepseek --replicas=5 -n ocr-production

# Auto-scaling status
kubectl get hpa -n ocr-production

# ==========================================
# DATABASE
# ==========================================

# Database shell
kubectl exec -it postgres-0 -n ocr-production -- psql -U postgres ocr_production

# Connection count
kubectl exec -it postgres-0 -n ocr-production -- \
  psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Backup database
./scripts/backup_database.sh

# ==========================================
# CERTIFICATES
# ==========================================

# Check SSL expiry
echo | openssl s_client -connect api.company.com:443 -servername api.company.com 2>/dev/null | \
  openssl x509 -noout -dates

# Renew certificate
certbot renew

# cert-manager status
kubectl get certificate -n ocr-production

# ==========================================
# EMERGENCY
# ==========================================

# Emergency rollback
./scripts/rollback.sh production

# Restart all backends
kubectl rollout restart deployment -n ocr-production

# Scale to zero (emergency stop)
kubectl scale deployment --all --replicas=0 -n ocr-production

🎉 ZUSAMMENFASSUNG
markdown# ✨ DEPLOYMENT GUIDE - COMPLETE!

## Was du jetzt hast:

### 📦 Docker & Orchestration
✅ Production Docker Compose Setup
✅ Multi-stage Dockerfiles
✅ Container Optimization
✅ Resource Management

### ⚙️ Configuration Management
✅ Environment Variables (dev/staging/prod)
✅ Secrets Management
✅ Configuration Validation
✅ Template Generation

### ☸️ Kubernetes Deployment
✅ Complete K8s Manifests
✅ Auto-scaling (HPA)
✅ Pod Disruption Budgets
✅ Health Probes
✅ Resource Quotas

### 🔄 CI/CD Pipeline
✅ GitHub Actions Workflow
✅ GitLab CI Pipeline
✅ Automated Testing
✅ Security Scanning
✅ Blue-Green Deployment
✅ Canary Deployment

### 🔒 Security
✅ SSL/TLS Setup (Let's Encrypt)
✅ cert-manager for K8s
✅ Security Headers
✅ Rate Limiting
✅ DDoS Protection

### 🔀 Load Balancing
✅ Nginx Configuration
✅ Advanced Caching
✅ Multiple Load Balancing Strategies
✅ Health-based Routing

### 🏥 Health & Monitoring
✅ Comprehensive Health Checks
✅ Liveness/Readiness Probes
✅ Prometheus Monitoring
✅ Grafana Dashboards
✅ Alert Rules

### 📊 Logging
✅ Centralized Logging (ELK)
✅ Structured JSON Logs
✅ Log Aggregation
✅ Log Analysis

### 🔍 Troubleshooting
✅ Common Issues & Solutions
✅ Debugging Commands
✅ Recovery Procedures

### ✅ Checklists
✅ Pre-Deployment Checklist
✅ Deployment Day Checklist
✅ Quick Reference Commands

## 🚀 Ready for Production!

Dein OCR-System kann jetzt:
- ✅ Automatisch deployed werden
- ✅ Auto-scaling basierend auf Last
- ✅ Selbst-heilend (self-healing)
- ✅ Zero-downtime deployments
- ✅ Vollständig überwacht
- ✅ Secure & compliant
- ✅ In Minuten wiederhergestellt werden

## 📚 Alle Guides sind fertig!

1. ✅ Mission.md - Projekt Overview
2. ✅ Architecture.md - System Design
3. ✅ API-Specification.md - API Docs
4. ✅ Backend-Implementation.md - Code Guide
5. ✅ Testing-QA.md - Testing Strategy
6. ✅ Infrastructure-IaC.md - Infrastructure
7. ✅ Deployment-Production.md - Deployment (DIESER GUIDE)

## 🎯 Nächste Schritte:

1. Review all guides
2. Customize for your specific needs
3. Start with development environment
4. Test in staging
5. Deploy to production!

## 💪 Du bist bereit!

Viel Erfolg mit deinem OCR-System! 🚀