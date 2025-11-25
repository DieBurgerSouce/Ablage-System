#!/bin/bash
# Alerting Setup Script - Ablage-System OCR
# Automated setup and validation of Alertmanager

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}🚨 Alerting Setup Script${NC}"
echo -e "${BLUE}═══════════════════════${NC}"
echo ""

# Function to check prerequisites
check_prerequisites() {
    echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker is installed${NC}"

    # Check docker-compose
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ docker-compose is not installed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ docker-compose is installed${NC}"

    # Check if Prometheus is running (alerting requires Prometheus)
    if ! docker ps | grep -q "prometheus"; then
        echo -e "${YELLOW}⚠️  Prometheus is not running${NC}"
        echo -e "${YELLOW}   Alertmanager requires Prometheus for receiving alerts${NC}"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo -e "${GREEN}✅ Prometheus is running${NC}"
    fi
}

# Function to validate configuration
validate_config() {
    echo -e "${BLUE}🔍 Validating configuration...${NC}"

    # Check if .env file exists
    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        echo -e "${YELLOW}⚠️  .env file not found${NC}"
        echo -e "${BLUE}Creating .env from template...${NC}"

        if [ -f "$SCRIPT_DIR/.env.example" ]; then
            cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
            echo -e "${YELLOW}⚠️  Please edit .env file with your credentials${NC}"
            read -p "Open .env in editor? (Y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                ${EDITOR:-nano} "$SCRIPT_DIR/.env"
            fi
        else
            echo -e "${RED}❌ .env.example not found${NC}"
            exit 1
        fi
    fi

    # Validate alertmanager.yml
    if [ ! -f "$SCRIPT_DIR/alertmanager.yml" ]; then
        echo -e "${RED}❌ alertmanager.yml not found${NC}"
        exit 1
    fi

    # Check if templates directory exists
    if [ ! -d "$SCRIPT_DIR/templates" ]; then
        echo -e "${RED}❌ templates directory not found${NC}"
        exit 1
    fi

    # Validate YAML syntax using docker
    echo -e "${BLUE}Validating YAML syntax...${NC}"
    docker run --rm -v "$SCRIPT_DIR/alertmanager.yml:/tmp/alertmanager.yml:ro" \
        prom/alertmanager:v0.27.0 \
        amtool check-config /tmp/alertmanager.yml

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Configuration is valid${NC}"
    else
        echo -e "${RED}❌ Configuration validation failed${NC}"
        exit 1
    fi
}

# Function to create network
create_network() {
    echo -e "${BLUE}🔗 Creating Docker network...${NC}"

    if docker network ls | grep -q "ablage_network"; then
        echo -e "${YELLOW}⚠️  Network already exists${NC}"
    else
        docker network create ablage_network
        echo -e "${GREEN}✅ Network created${NC}"
    fi
}

# Function to start services
start_alertmanager() {
    echo -e "${BLUE}🚀 Starting Alertmanager...${NC}"

    cd "$SCRIPT_DIR"
    docker-compose -f docker-compose.alerting.yml up -d

    # Wait for Alertmanager to be ready
    echo -e "${BLUE}Waiting for Alertmanager to be ready...${NC}"
    sleep 5

    # Check if Alertmanager is healthy
    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if docker exec ablage-alertmanager wget --spider -q http://localhost:9093/-/healthy; then
            echo -e "${GREEN}✅ Alertmanager is healthy${NC}"
            break
        fi

        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
        sleep 2
    done

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo ""
        echo -e "${RED}❌ Alertmanager failed to become healthy${NC}"
        echo -e "${YELLOW}Checking logs...${NC}"
        docker logs ablage-alertmanager
        exit 1
    fi

    echo ""
    echo -e "${GREEN}✅ Alertmanager started successfully${NC}"
}

# Function to configure Prometheus integration
configure_prometheus() {
    echo -e "${BLUE}🔧 Configuring Prometheus integration...${NC}"

    # Check if Prometheus config exists
    PROMETHEUS_CONFIG="/opt/ablage-system/infrastructure/monitoring/prometheus/prometheus.yml"

    if [ ! -f "$PROMETHEUS_CONFIG" ]; then
        echo -e "${YELLOW}⚠️  Prometheus config not found at $PROMETHEUS_CONFIG${NC}"
        echo -e "${BLUE}Please add the following to your prometheus.yml:${NC}"
        cat <<EOF

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

rule_files:
  - "alerts/*.yml"
EOF
        return
    fi

    # Check if alertmanager is already configured
    if grep -q "alertmanager:9093" "$PROMETHEUS_CONFIG"; then
        echo -e "${GREEN}✅ Alertmanager already configured in Prometheus${NC}"
    else
        echo -e "${YELLOW}⚠️  Alertmanager not configured in Prometheus${NC}"
        echo -e "${BLUE}Add the configuration manually or restart Prometheus${NC}"
    fi
}

# Function to test alerts
test_alerts() {
    echo -e "${BLUE}🧪 Testing alert delivery...${NC}"

    echo -e "${YELLOW}Sending test alert to Alertmanager...${NC}"

    # Create test alert
    TEST_ALERT=$(cat <<EOF
[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "service": "alerting-test",
      "instance": "test-instance"
    },
    "annotations": {
      "summary": "This is a test alert from setup script",
      "description": "If you receive this, alerting is working correctly!"
    },
    "startsAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "endsAt": "$(date -u -d '+5 minutes' +"%Y-%m-%dT%H:%M:%SZ")"
  }
]
EOF
)

    # Send to Alertmanager
    curl -s -X POST http://localhost:9093/api/v1/alerts \
        -H "Content-Type: application/json" \
        -d "$TEST_ALERT" > /dev/null

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Test alert sent successfully${NC}"
        echo -e "${BLUE}Check your notification channels (Slack, PagerDuty, etc.)${NC}"
    else
        echo -e "${RED}❌ Failed to send test alert${NC}"
    fi

    # Show Alertmanager UI URL
    echo ""
    echo -e "${BLUE}Alertmanager UI: http://localhost:9093${NC}"
}

# Function to show status
show_status() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Alerting Setup Complete! 🎉${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ Alertmanager is running${NC}"
    echo ""
    echo -e "${BLUE}🌐 Access Points:${NC}"
    echo -e "   Alertmanager UI:  http://localhost:9093"
    echo -e "   Webhook Receiver: http://localhost:5001"
    echo ""
    echo -e "${BLUE}📊 Status:${NC}"
    docker-compose -f "$SCRIPT_DIR/docker-compose.alerting.yml" ps
    echo ""
    echo -e "${BLUE}📝 Useful Commands:${NC}"
    echo -e "   View logs:         docker logs -f ablage-alertmanager"
    echo -e "   Reload config:     docker exec ablage-alertmanager kill -HUP 1"
    echo -e "   Test alert:        curl -X POST http://localhost:9093/api/v1/alerts -d @test-alert.json"
    echo -e "   Stop:              docker-compose -f docker-compose.alerting.yml down"
    echo ""
    echo -e "${YELLOW}⚠️  Next Steps:${NC}"
    echo -e "   1. Configure your notification channels (.env file)"
    echo -e "   2. Add alerting rules to Prometheus"
    echo -e "   3. Test alert delivery with 'test' command"
    echo -e "   4. Monitor alerts in Alertmanager UI"
    echo ""
}

# Function to generate sample alert rules
generate_sample_rules() {
    echo -e "${BLUE}📝 Generating sample alert rules...${NC}"

    RULES_FILE="$SCRIPT_DIR/sample-alert-rules.yml"

    cat > "$RULES_FILE" <<'EOF'
# Sample Alert Rules for Ablage-System OCR
# Copy these to your Prometheus rules directory

groups:
  - name: ablage_system_alerts
    interval: 30s
    rules:
      # API Health Alerts
      - alert: APIDown
        expr: up{job="ablage-backend"} == 0
        for: 1m
        labels:
          severity: critical
          service: backend
        annotations:
          summary: "Ablage-System API is down"
          description: "API has been down for more than 1 minute"
          runbook_url: "https://wiki.ablage-system.local/runbooks/api-down"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: high
          service: backend
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"
          current_value: "{{ $value | humanizePercentage }}"
          threshold: "5%"

      # GPU Alerts
      - alert: GPUMemoryHigh
        expr: gpu_memory_usage_bytes / gpu_memory_total_bytes > 0.85
        for: 5m
        labels:
          severity: warning
          service: worker
        annotations:
          summary: "GPU memory usage is high"
          description: "GPU memory usage is {{ $value | humanizePercentage }}"
          current_value: "{{ $value | humanizePercentage }}"
          threshold: "85%"

      - alert: GPUTemperatureHigh
        expr: gpu_temperature_celsius > 85
        for: 10m
        labels:
          severity: high
          service: worker
        annotations:
          summary: "GPU temperature is high"
          description: "GPU temperature is {{ $value }}°C"
          current_value: "{{ $value }}°C"
          threshold: "85°C"

      # Database Alerts
      - alert: DatabaseConnectionsHigh
        expr: pg_stat_activity_count > 80
        for: 5m
        labels:
          severity: warning
          service: postgres
        annotations:
          summary: "Database connections are high"
          description: "Active connections: {{ $value }} (threshold: 80)"
          current_value: "{{ $value }}"
          threshold: "80"

      - alert: DatabaseSlowQueries
        expr: rate(pg_stat_statements_mean_exec_time[5m]) > 1000
        for: 10m
        labels:
          severity: warning
          service: postgres
        annotations:
          summary: "Slow database queries detected"
          description: "Average query time: {{ $value }}ms"

      # Document Processing Alerts
      - alert: HighDocumentQueueLength
        expr: document_queue_length > 100
        for: 15m
        labels:
          severity: high
          service: worker
        annotations:
          summary: "Document processing queue is backed up"
          description: "Queue length: {{ $value }} documents"
          action: "Consider scaling up workers"

      - alert: OCRProcessingFailureRate
        expr: rate(ocr_processing_failures_total[10m]) > 0.1
        for: 10m
        labels:
          severity: high
          service: worker
        annotations:
          summary: "High OCR processing failure rate"
          description: "Failure rate: {{ $value | humanizePercentage }}"

      # System Resource Alerts
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90
        for: 10m
        labels:
          severity: warning
          service: system
        annotations:
          summary: "High CPU usage detected"
          description: "CPU usage is {{ $value | humanizePercentage }}"

      - alert: HighMemoryUsage
        expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) > 0.90
        for: 10m
        labels:
          severity: warning
          service: system
        annotations:
          summary: "High memory usage detected"
          description: "Memory usage is {{ $value | humanizePercentage }}"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.10
        for: 5m
        labels:
          severity: critical
          service: system
        annotations:
          summary: "Disk space is low"
          description: "Available space: {{ $value | humanizePercentage }}"
EOF

    echo -e "${GREEN}✅ Sample alert rules created: $RULES_FILE${NC}"
    echo -e "${BLUE}Copy these rules to your Prometheus configuration${NC}"
}

# Main setup flow
main() {
    case "${1:-setup}" in
        setup)
            check_prerequisites
            echo ""
            validate_config
            echo ""
            create_network
            echo ""
            start_alertmanager
            echo ""
            configure_prometheus
            echo ""
            show_status
            ;;

        test)
            test_alerts
            ;;

        rules)
            generate_sample_rules
            ;;

        stop)
            echo -e "${BLUE}Stopping Alertmanager...${NC}"
            cd "$SCRIPT_DIR"
            docker-compose -f docker-compose.alerting.yml down
            echo -e "${GREEN}✅ Alertmanager stopped${NC}"
            ;;

        restart)
            echo -e "${BLUE}Restarting Alertmanager...${NC}"
            cd "$SCRIPT_DIR"
            docker-compose -f docker-compose.alerting.yml restart
            echo -e "${GREEN}✅ Alertmanager restarted${NC}"
            ;;

        logs)
            docker logs -f ablage-alertmanager
            ;;

        status)
            docker-compose -f "$SCRIPT_DIR/docker-compose.alerting.yml" ps
            echo ""
            echo -e "${BLUE}Alertmanager UI: http://localhost:9093${NC}"
            ;;

        help|-h|--help)
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  setup    - Initial setup and start Alertmanager (default)"
            echo "  test     - Send test alert"
            echo "  rules    - Generate sample alert rules"
            echo "  stop     - Stop Alertmanager"
            echo "  restart  - Restart Alertmanager"
            echo "  logs     - View Alertmanager logs"
            echo "  status   - Show Alertmanager status"
            echo "  help     - Show this help message"
            ;;

        *)
            echo -e "${RED}❌ Unknown command: $1${NC}"
            echo "Run '$0 help' for usage"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
