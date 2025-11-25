#!/bin/bash
# Monitoring Setup Script - Ablage-System OCR
# Sets up Prometheus, Grafana, and alerting

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MONITORING_DIR="infrastructure/monitoring"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"

# Function to create directory structure
create_directories() {
    echo -e "${BLUE}📁 Creating monitoring directories...${NC}"

    mkdir -p "$MONITORING_DIR/prometheus"
    mkdir -p "$MONITORING_DIR/grafana/dashboards"
    mkdir -p "$MONITORING_DIR/grafana/provisioning/dashboards"
    mkdir -p "$MONITORING_DIR/grafana/provisioning/datasources"
    mkdir -p "$MONITORING_DIR/alertmanager"

    echo -e "${GREEN}✅ Directories created${NC}"
}

# Function to create Prometheus configuration
create_prometheus_config() {
    echo -e "${BLUE}⚙️  Creating Prometheus configuration...${NC}"

    cat > "$MONITORING_DIR/prometheus/prometheus.yml" <<'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'ablage-system'
    environment: 'production'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load rules
rule_files:
  - 'alerts.yml'

# Scrape configurations
scrape_configs:
  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Backend API
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'

  # Celery Worker
  - job_name: 'worker'
    static_configs:
      - targets: ['worker:9100']
    metrics_path: '/metrics'

  # PostgreSQL
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  # Redis
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  # MinIO
  - job_name: 'minio'
    static_configs:
      - targets: ['minio:9000']
    metrics_path: '/minio/v2/metrics/cluster'

  # Node Exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  # GPU Metrics (if available)
  - job_name: 'nvidia-gpu'
    static_configs:
      - targets: ['dcgm-exporter:9400']
EOF

    echo -e "${GREEN}✅ Prometheus configuration created${NC}"
}

# Function to create Prometheus alert rules
create_alert_rules() {
    echo -e "${BLUE}🚨 Creating Prometheus alert rules...${NC}"

    cat > "$MONITORING_DIR/prometheus/alerts.yml" <<'EOF'
groups:
  - name: ablage_system_alerts
    interval: 30s
    rules:
      # API Health Alerts
      - alert: APIDown
        expr: up{job="backend"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Ablage-System API is down"
          description: "The API has been down for more than 1 minute"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} (>5%)"

      - alert: SlowResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Slow API response time"
          description: "95th percentile response time is {{ $value }}s (>1s)"

      # Database Alerts
      - alert: DatabaseDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL database is down"
          description: "Database has been unreachable for 1 minute"

      - alert: DatabaseConnectionPoolExhausted
        expr: pg_stat_database_numbackends / pg_settings_max_connections > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Database connection pool near limit"
          description: "{{ $value | humanizePercentage }} of connections in use"

      # Redis Alerts
      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis is down"
          description: "Redis has been down for 1 minute"

      - alert: RedisMemoryHigh
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis memory usage high"
          description: "Redis using {{ $value | humanizePercentage }} of max memory"

      # GPU Alerts
      - alert: GPUMemoryHigh
        expr: dcgm_fb_used / dcgm_fb_total > 0.85
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "GPU memory usage high"
          description: "GPU memory at {{ $value | humanizePercentage }} (>85%)"

      - alert: GPUTemperatureHigh
        expr: dcgm_gpu_temp > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU temperature high"
          description: "GPU temperature is {{ $value }}°C (>80°C)"

      # System Alerts
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is {{ $value | humanize }}%"

      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanizePercentage }}"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Low disk space"
          description: "Only {{ $value | humanizePercentage }} disk space available"

      # OCR Processing Alerts
      - alert: OCRQueueBacklog
        expr: celery_queue_length > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "OCR processing queue backlog"
          description: "{{ $value }} documents waiting in queue"

      - alert: OCRProcessingFailed
        expr: rate(ocr_processing_failed_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High OCR failure rate"
          description: "OCR failing at {{ $value | humanizePercentage }}"
EOF

    echo -e "${GREEN}✅ Alert rules created${NC}"
}

# Function to create Grafana datasource configuration
create_grafana_datasources() {
    echo -e "${BLUE}📊 Creating Grafana datasources...${NC}"

    cat > "$MONITORING_DIR/grafana/provisioning/datasources/prometheus.yml" <<EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:$PROMETHEUS_PORT
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 15s
EOF

    echo -e "${GREEN}✅ Grafana datasources configured${NC}"
}

# Function to create Grafana dashboard provisioning
create_grafana_dashboard_provisioning() {
    echo -e "${BLUE}📊 Creating Grafana dashboard provisioning...${NC}"

    cat > "$MONITORING_DIR/grafana/provisioning/dashboards/default.yml" <<EOF
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
EOF

    echo -e "${GREEN}✅ Dashboard provisioning configured${NC}"
}

# Function to create docker-compose monitoring stack
create_docker_compose() {
    echo -e "${BLUE}🐳 Creating docker-compose monitoring configuration...${NC}"

    cat > "$MONITORING_DIR/docker-compose.monitoring.yml" <<EOF
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
      - '--storage.tsdb.retention.time=30d'
    ports:
      - "$PROMETHEUS_PORT:9090"
    volumes:
      - ./prometheus:/etc/prometheus
      - prometheus_data:/prometheus
    restart: unless-stopped
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "$GRAFANA_PORT:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=\${GRAFANA_ADMIN_PASSWORD:-admin}
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    depends_on:
      - prometheus
    restart: unless-stopped
    networks:
      - monitoring

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    command:
      - '--config.file=/etc/alertmanager/config.yml'
      - '--storage.path=/alertmanager'
    ports:
      - "$ALERTMANAGER_PORT:9093"
    volumes:
      - ./alertmanager:/etc/alertmanager
      - alertmanager_data:/alertmanager
    restart: unless-stopped
    networks:
      - monitoring

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    restart: unless-stopped
    networks:
      - monitoring

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    container_name: postgres-exporter
    environment:
      - DATA_SOURCE_NAME=postgresql://postgres:postgres@postgres:5432/ablage_ocr?sslmode=disable
    ports:
      - "9187:9187"
    restart: unless-stopped
    networks:
      - monitoring

  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis-exporter
    environment:
      - REDIS_ADDR=redis:6379
    ports:
      - "9121:9121"
    restart: unless-stopped
    networks:
      - monitoring

volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:

networks:
  monitoring:
    driver: bridge
EOF

    echo -e "${GREEN}✅ Docker Compose configuration created${NC}"
}

# Function to create Alertmanager configuration
create_alertmanager_config() {
    echo -e "${BLUE}🚨 Creating Alertmanager configuration...${NC}"

    cat > "$MONITORING_DIR/alertmanager/config.yml" <<'EOF'
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
      continue: true

    - match:
        severity: warning
      receiver: 'warning-alerts'

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://backend:8000/api/v1/alerts/webhook'

  - name: 'critical-alerts'
    # Add Slack, PagerDuty, or email configuration here
    webhook_configs:
      - url: 'http://backend:8000/api/v1/alerts/critical'

  - name: 'warning-alerts'
    webhook_configs:
      - url: 'http://backend:8000/api/v1/alerts/warning'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
EOF

    echo -e "${GREEN}✅ Alertmanager configuration created${NC}"
}

# Function to display summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Monitoring Setup Complete! 📊${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ Configuration files created in: $MONITORING_DIR${NC}"
    echo ""
    echo -e "${BLUE}📋 Components Configured:${NC}"
    echo -e "   • Prometheus (metrics collection)"
    echo -e "   • Grafana (visualization)"
    echo -e "   • Alertmanager (alerting)"
    echo -e "   • Node Exporter (system metrics)"
    echo -e "   • PostgreSQL Exporter"
    echo -e "   • Redis Exporter"
    echo ""
    echo -e "${BLUE}🚀 Start Monitoring Stack:${NC}"
    echo -e "   cd $MONITORING_DIR"
    echo -e "   docker-compose -f docker-compose.monitoring.yml up -d"
    echo ""
    echo -e "${BLUE}🌐 Access Dashboards:${NC}"
    echo -e "   Prometheus:    http://localhost:$PROMETHEUS_PORT"
    echo -e "   Grafana:       http://localhost:$GRAFANA_PORT"
    echo -e "   Alertmanager:  http://localhost:$ALERTMANAGER_PORT"
    echo ""
    echo -e "${BLUE}🔑 Default Credentials:${NC}"
    echo -e "   Grafana:  admin / admin (change on first login)"
    echo ""
    echo -e "${YELLOW}⚠️  Next Steps:${NC}"
    echo -e "   1. Review alert rules in prometheus/alerts.yml"
    echo -e "   2. Configure Alertmanager receivers (Slack, email, etc.)"
    echo -e "   3. Import Grafana dashboards"
    echo -e "   4. Set GRAFANA_ADMIN_PASSWORD environment variable"
    echo -e "   5. Test alerting with: make test-alerts"
    echo ""
}

# Main script
main() {
    echo -e "${BLUE}📊 Monitoring Setup Script${NC}"
    echo -e "${BLUE}═══════════════════════════${NC}"
    echo ""

    create_directories
    create_prometheus_config
    create_alert_rules
    create_grafana_datasources
    create_grafana_dashboard_provisioning
    create_docker_compose
    create_alertmanager_config
    show_summary

    echo -e "${GREEN}✅ Monitoring setup complete!${NC}"
}

# Run main function
main
