📊 MONITORING DASHBOARD - GRAFANA CONFIGURATION
Complete Grafana Setup for OCR System Monitoring

📋 TABLE OF CONTENTS

Introduction
Installation & Setup
Data Sources Configuration
Dashboard Overview
System Metrics Dashboard
OCR Performance Dashboard
User Activity Dashboard
Error Monitoring Dashboard
Database Performance Dashboard
Alerts Configuration
Custom Queries
Deployment
Best Practices


🎯 INTRODUCTION
What We'll Monitor
┌─────────────────────────────────────────────────────────────┐
│                    OCR SYSTEM MONITORING                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  📊 SYSTEM METRICS                                           │
│  • CPU, RAM, Disk Usage                                      │
│  • Network I/O                                               │
│  • Container Health                                          │
│                                                               │
│  🔄 OCR PERFORMANCE                                          │
│  • Processing Time per Backend                               │
│  • Success/Failure Rates                                     │
│  • Queue Length & Throughput                                 │
│  • VRAM/GPU Usage                                            │
│                                                               │
│  👥 USER ACTIVITY                                            │
│  • Active Users                                              │
│  • Document Uploads                                          │
│  • API Request Rates                                         │
│                                                               │
│  ⚠️ ERRORS & ALERTS                                          │
│  • Error Rates by Type                                       │
│  • Failed Jobs                                               │
│  • System Health                                             │
│                                                               │
│  💾 DATABASE PERFORMANCE                                     │
│  • Query Performance                                         │
│  • Connection Pool                                           │
│  • Slow Queries                                              │
│                                                               │
└─────────────────────────────────────────────────────────────┘

📦 INSTALLATION & SETUP
1. Docker Compose Setup
yaml# docker-compose.monitoring.yml

version: '3.8'

services:
  # Grafana
  grafana:
    image: grafana/grafana:10.2.3
    container_name: ocr-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin123  # Change in production!
      - GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-piechart-panel
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_AUTH_ANONYMOUS_ENABLED=false
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    networks:
      - monitoring
    restart: unless-stopped

  # Prometheus (metrics collector)
  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: ocr-prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    networks:
      - monitoring
    restart: unless-stopped

  # Node Exporter (system metrics)
  node-exporter:
    image: prom/node-exporter:v1.7.0
    container_name: ocr-node-exporter
    ports:
      - "9100:9100"
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    networks:
      - monitoring
    restart: unless-stopped

  # Postgres Exporter (database metrics)
  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:v0.15.0
    container_name: ocr-postgres-exporter
    ports:
      - "9187:9187"
    environment:
      - DATA_SOURCE_NAME=postgresql://user:password@postgres:5432/ocr_db?sslmode=disable
    networks:
      - monitoring
    restart: unless-stopped

volumes:
  grafana-data:
  prometheus-data:

networks:
  monitoring:
    driver: bridge
2. Start Monitoring Stack
bash# Start all monitoring services
docker-compose -f docker-compose.monitoring.yml up -d

# Check status
docker-compose -f docker-compose.monitoring.yml ps

# View logs
docker-compose -f docker-compose.monitoring.yml logs -f grafana
```

### 3. Access Grafana
```
URL: http://localhost:3000
Username: admin
Password: admin123

First time login:
1. Change default password
2. Configure data sources
3. Import dashboards

🔌 DATA SOURCES CONFIGURATION
1. Prometheus Data Source
yaml# grafana/provisioning/datasources/prometheus.yml

apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
    jsonData:
      httpMethod: POST
      timeInterval: 15s
2. PostgreSQL Data Source
yaml# grafana/provisioning/datasources/postgres.yml

apiVersion: 1

datasources:
  - name: PostgreSQL
    type: postgres
    access: proxy
    url: postgres:5432
    database: ocr_db
    user: grafana_reader
    secureJsonData:
      password: 'grafana_password'
    jsonData:
      sslmode: 'disable'
      maxOpenConns: 10
      maxIdleConns: 10
      connMaxLifetime: 14400
      postgresVersion: 1500  # PostgreSQL 15
      timescaledb: false
3. Create Read-Only Database User
sql-- Create Grafana read-only user
CREATE USER grafana_reader WITH PASSWORD 'grafana_password';

-- Grant read permissions
GRANT CONNECT ON DATABASE ocr_db TO grafana_reader;
GRANT USAGE ON SCHEMA public TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;

-- For pg_stat_statements (query performance)
GRANT pg_read_all_stats TO grafana_reader;
4. Prometheus Configuration
yaml# prometheus/prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'ocr-production'
    environment: 'production'

scrape_configs:
  # Node Exporter - System Metrics
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
        labels:
          instance: 'ocr-server'

  # Postgres Exporter - Database Metrics
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
        labels:
          instance: 'ocr-db'

  # OCR Backend Metrics (if you export custom metrics)
  - job_name: 'ocr-backend'
    static_configs:
      - targets: ['ocr-backend:8000']
        labels:
          service: 'ocr-api'

  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

---

## 📊 DASHBOARD OVERVIEW

### Dashboard Structure
```
1. SYSTEM OVERVIEW (Home Dashboard)
   ├── Key Metrics Summary
   ├── System Health Status
   └── Recent Alerts

2. SYSTEM METRICS
   ├── CPU Usage
   ├── Memory Usage
   ├── Disk I/O
   └── Network Traffic

3. OCR PERFORMANCE
   ├── Processing Time by Backend
   ├── Success/Failure Rates
   ├── Queue Length
   └── Throughput

4. USER ACTIVITY
   ├── Active Users
   ├── Document Uploads
   ├── API Requests
   └── Popular Features

5. ERROR MONITORING
   ├── Error Rate Over Time
   ├── Error Types Distribution
   ├── Failed Jobs
   └── Top Errors

6. DATABASE PERFORMANCE
   ├── Query Performance
   ├── Connection Pool
   ├── Slow Queries
   └── Table Statistics

💻 SYSTEM METRICS DASHBOARD
Complete Dashboard JSON
json{
  "dashboard": {
    "title": "OCR System Metrics",
    "tags": ["system", "infrastructure"],
    "timezone": "browser",
    "schemaVersion": 16,
    "version": 1,
    "refresh": "30s",
    
    "panels": [
      {
        "id": 1,
        "title": "CPU Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "100 - (avg by (instance) (irate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "yaxes": [
          {"format": "percent", "max": 100, "min": 0},
          {"format": "short"}
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {"params": [80], "type": "gt"},
              "operator": {"type": "and"},
              "query": {"params": ["A", "5m", "now"]},
              "reducer": {"params": [], "type": "avg"},
              "type": "query"
            }
          ],
          "executionErrorState": "alerting",
          "frequency": "1m",
          "handler": 1,
          "name": "High CPU Usage",
          "noDataState": "no_data",
          "notifications": []
        }
      },
      
      {
        "id": 2,
        "title": "Memory Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
            "legendFormat": "Memory Usage",
            "refId": "A"
          }
        ],
        "yaxes": [
          {"format": "percent", "max": 100, "min": 0},
          {"format": "short"}
        ]
      },
      
      {
        "id": 3,
        "title": "Disk Usage",
        "type": "gauge",
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "(1 - (node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"})) * 100",
            "refId": "A"
          }
        ],
        "options": {
          "showThresholdLabels": false,
          "showThresholdMarkers": true
        },
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 70},
                {"color": "red", "value": 85}
              ]
            },
            "unit": "percent",
            "min": 0,
            "max": 100
          }
        }
      },
      
      {
        "id": 4,
        "title": "Network Traffic",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 6, "y": 8},
        "targets": [
          {
            "expr": "rate(node_network_receive_bytes_total[5m]) * 8",
            "legendFormat": "Receive - {{device}}",
            "refId": "A"
          },
          {
            "expr": "rate(node_network_transmit_bytes_total[5m]) * 8",
            "legendFormat": "Transmit - {{device}}",
            "refId": "B"
          }
        ],
        "yaxes": [
          {"format": "bps"},
          {"format": "short"}
        ]
      },
      
      {
        "id": 5,
        "title": "System Load Average",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 18, "y": 8},
        "targets": [
          {
            "expr": "node_load1",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 4},
                {"color": "red", "value": 8}
              ]
            },
            "decimals": 2
          }
        }
      },
      
      {
        "id": 6,
        "title": "Disk I/O",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
        "targets": [
          {
            "expr": "rate(node_disk_read_bytes_total[5m])",
            "legendFormat": "Read - {{device}}",
            "refId": "A"
          },
          {
            "expr": "rate(node_disk_written_bytes_total[5m])",
            "legendFormat": "Write - {{device}}",
            "refId": "B"
          }
        ],
        "yaxes": [
          {"format": "Bps"},
          {"format": "short"}
        ]
      }
    ]
  }
}
Panel Queries Explained
promql# CPU Usage (percentage)
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory Usage (percentage)
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Disk Usage (percentage)
(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100

# Network Receive (bits per second)
rate(node_network_receive_bytes_total[5m]) * 8

# Network Transmit (bits per second)
rate(node_network_transmit_bytes_total[5m]) * 8

🔄 OCR PERFORMANCE DASHBOARD
Dashboard Configuration
json{
  "dashboard": {
    "title": "OCR Performance Metrics",
    "tags": ["ocr", "performance"],
    "refresh": "10s",
    
    "panels": [
      {
        "id": 10,
        "title": "Processing Time by Backend",
        "type": "graph",
        "gridPos": {"h": 10, "w": 12, "x": 0, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('minute', created_at) as time,\n  backend_type,\n  AVG(processing_time_ms) as avg_time\nFROM processing_jobs\nWHERE\n  $__timeFilter(created_at)\n  AND success = true\nGROUP BY 1, 2\nORDER BY 1",
            "format": "time_series",
            "refId": "A"
          }
        ],
        "yaxes": [
          {"format": "ms", "label": "Processing Time"},
          {"format": "short"}
        ]
      },
      
      {
        "id": 11,
        "title": "Success Rate by Backend",
        "type": "stat",
        "gridPos": {"h": 5, "w": 6, "x": 12, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  backend_type as metric,\n  (COUNT(*) FILTER (WHERE success = true)::float / COUNT(*)::float * 100) as value\nFROM processing_jobs\nWHERE $__timeFilter(created_at)\nGROUP BY backend_type",
            "format": "table",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 90},
                {"color": "green", "value": 95}
              ]
            }
          }
        }
      },
      
      {
        "id": 12,
        "title": "Documents Processed (24h)",
        "type": "stat",
        "gridPos": {"h": 5, "w": 6, "x": 18, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT COUNT(*) as value\nFROM processing_jobs\nWHERE created_at > NOW() - INTERVAL '24 hours'\n  AND success = true",
            "format": "table",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "short",
            "thresholds": {
              "steps": [
                {"color": "blue", "value": null}
              ]
            }
          }
        }
      },
      
      {
        "id": 13,
        "title": "Processing Queue Length",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 10},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('minute', created_at) as time,\n  COUNT(*) as queue_length\nFROM processing_jobs\nWHERE\n  $__timeFilter(created_at)\n  AND status IN ('pending', 'processing')\nGROUP BY 1\nORDER BY 1",
            "format": "time_series",
            "refId": "A"
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {"params": [100], "type": "gt"},
              "query": {"params": ["A", "5m", "now"]},
              "reducer": {"params": [], "type": "avg"},
              "type": "query"
            }
          ],
          "name": "High Queue Length"
        }
      },
      
      {
        "id": 14,
        "title": "Throughput (docs/min)",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 10},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('minute', completed_at) as time,\n  COUNT(*) as throughput\nFROM processing_jobs\nWHERE\n  $__timeFilter(completed_at)\n  AND success = true\nGROUP BY 1\nORDER BY 1",
            "format": "time_series",
            "refId": "A"
          }
        ]
      },
      
      {
        "id": 15,
        "title": "Average Confidence by Backend",
        "type": "bargauge",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 18},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  backend_type as metric,\n  AVG(confidence_score) as value\nFROM processing_jobs\nWHERE\n  $__timeFilter(created_at)\n  AND success = true\n  AND confidence_score IS NOT NULL\nGROUP BY backend_type",
            "format": "table",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 70},
                {"color": "green", "value": 85}
              ]
            }
          }
        }
      },
      
      {
        "id": 16,
        "title": "VRAM Usage by Backend",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 18},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('minute', created_at) as time,\n  backend_type,\n  AVG(vram_used_mb) as avg_vram\nFROM processing_jobs\nWHERE\n  $__timeFilter(created_at)\n  AND vram_used_mb IS NOT NULL\nGROUP BY 1, 2\nORDER BY 1",
            "format": "time_series",
            "refId": "A"
          }
        ],
        "yaxes": [
          {"format": "mbytes", "label": "VRAM Usage"},
          {"format": "short"}
        ]
      }
    ]
  }
}

👥 USER ACTIVITY DASHBOARD
SQL Queries for User Metrics
json{
  "dashboard": {
    "title": "User Activity Dashboard",
    "tags": ["users", "activity"],
    "refresh": "1m",
    
    "panels": [
      {
        "id": 20,
        "title": "Active Users (Last Hour)",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT COUNT(DISTINCT user_id) as value\nFROM user_sessions\nWHERE last_activity_at > NOW() - INTERVAL '1 hour'\n  AND is_active = true",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 21,
        "title": "Documents Uploaded Today",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT COUNT(*) as value\nFROM documents\nWHERE DATE(created_at) = CURRENT_DATE",
            "format": "table"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {
              "steps": [
                {"color": "green", "value": null}
              ]
            }
          }
        }
      },
      
      {
        "id": 22,
        "title": "API Requests per Minute",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('minute', created_at) as time,\n  COUNT(*) as requests\nFROM audit_logs\nWHERE\n  $__timeFilter(created_at)\nGROUP BY 1\nORDER BY 1",
            "format": "time_series"
          }
        ]
      },
      
      {
        "id": 23,
        "title": "Top 10 Active Users",
        "type": "table",
        "gridPos": {"h": 10, "w": 12, "x": 12, "y": 4},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  u.email,\n  u.username,\n  COUNT(d.id) as documents,\n  COUNT(DISTINCT DATE(d.created_at)) as active_days\nFROM users u\nJOIN documents d ON d.user_id = u.id\nWHERE d.created_at > NOW() - INTERVAL '30 days'\nGROUP BY u.id, u.email, u.username\nORDER BY documents DESC\nLIMIT 10",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 24,
        "title": "Document Types Distribution",
        "type": "piechart",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  document_type as metric,\n  COUNT(*) as value\nFROM documents\nWHERE created_at > NOW() - INTERVAL '7 days'\nGROUP BY document_type",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 25,
        "title": "User Registrations Over Time",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('day', created_at) as time,\n  COUNT(*) as registrations\nFROM users\nWHERE $__timeFilter(created_at)\nGROUP BY 1\nORDER BY 1",
            "format": "time_series"
          }
        ]
      }
    ]
  }
}

⚠️ ERROR MONITORING DASHBOARD
json{
  "dashboard": {
    "title": "Error Monitoring",
    "tags": ["errors", "monitoring"],
    "refresh": "30s",
    
    "panels": [
      {
        "id": 30,
        "title": "Error Rate (Last Hour)",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  (COUNT(*) FILTER (WHERE severity IN ('error', 'critical'))::float / NULLIF(COUNT(*), 0) * 100) as value\nFROM error_logs\nWHERE created_at > NOW() - INTERVAL '1 hour'",
            "format": "table"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "thresholds": {
              "steps": [
                {"color": "green", "value": 0},
                {"color": "yellow", "value": 1},
                {"color": "red", "value": 5}
              ]
            }
          }
        }
      },
      
      {
        "id": 31,
        "title": "Total Errors (24h)",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT COUNT(*) as value\nFROM error_logs\nWHERE created_at > NOW() - INTERVAL '24 hours'\n  AND severity IN ('error', 'critical')",
            "format": "table"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "steps": [
                {"color": "green", "value": 0},
                {"color": "yellow", "value": 100},
                {"color": "red", "value": 500}
              ]
            }
          }
        }
      },
      
      {
        "id": 32,
        "title": "Unresolved Errors",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT COUNT(*) as value\nFROM error_logs\nWHERE resolved = false\n  AND severity IN ('error', 'critical')",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 33,
        "title": "Failed Jobs (24h)",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT COUNT(*) as value\nFROM processing_jobs\nWHERE created_at > NOW() - INTERVAL '24 hours'\n  AND success = false",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 34,
        "title": "Errors Over Time",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  DATE_TRUNC('minute', created_at) as time,\n  severity,\n  COUNT(*) as errors\nFROM error_logs\nWHERE $__timeFilter(created_at)\nGROUP BY 1, 2\nORDER BY 1",
            "format": "time_series"
          }
        ]
      },
      
      {
        "id": 35,
        "title": "Error Types Distribution",
        "type": "piechart",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  error_type as metric,\n  COUNT(*) as value\nFROM error_logs\nWHERE created_at > NOW() - INTERVAL '24 hours'\nGROUP BY error_type\nORDER BY value DESC\nLIMIT 10",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 36,
        "title": "Top 10 Errors",
        "type": "table",
        "gridPos": {"h": 10, "w": 24, "x": 0, "y": 12},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  error_type,\n  error_message,\n  severity,\n  COUNT(*) as occurrences,\n  MAX(created_at) as last_seen\nFROM error_logs\nWHERE created_at > NOW() - INTERVAL '24 hours'\nGROUP BY error_type, error_message, severity\nORDER BY occurrences DESC\nLIMIT 10",
            "format": "table"
          }
        ]
      }
    ]
  }
}

💾 DATABASE PERFORMANCE DASHBOARD
json{
  "dashboard": {
    "title": "Database Performance",
    "tags": ["database", "postgresql"],
    "refresh": "1m",
    
    "panels": [
      {
        "id": 40,
        "title": "Active Connections",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  NOW() as time,\n  COUNT(*) FILTER (WHERE state = 'active') as active,\n  COUNT(*) FILTER (WHERE state = 'idle') as idle,\n  COUNT(*) as total\nFROM pg_stat_activity\nWHERE datname = current_database()",
            "format": "time_series"
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {"params": [50], "type": "gt"},
              "query": {"params": ["total", "5m", "now"]},
              "reducer": {"params": [], "type": "avg"},
              "type": "query"
            }
          ],
          "name": "High Database Connections"
        }
      },
      
      {
        "id": 41,
        "title": "Query Performance",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  NOW() as time,\n  AVG(mean_exec_time) as avg_query_time\nFROM pg_stat_statements\nWHERE calls > 0",
            "format": "time_series"
          }
        ],
        "yaxes": [
          {"format": "ms"},
          {"format": "short"}
        ]
      },
      
      {
        "id": 42,
        "title": "Slow Queries (>100ms)",
        "type": "table",
        "gridPos": {"h": 10, "w": 24, "x": 0, "y": 8},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  SUBSTRING(query, 1, 100) as query,\n  calls,\n  ROUND(mean_exec_time::numeric, 2) as avg_time_ms,\n  ROUND(total_exec_time::numeric, 2) as total_time_ms,\n  ROUND((100 * total_exec_time / SUM(total_exec_time) OVER ())::numeric, 2) as percentage\nFROM pg_stat_statements\nWHERE mean_exec_time > 100\nORDER BY total_exec_time DESC\nLIMIT 20",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 43,
        "title": "Cache Hit Ratio",
        "type": "gauge",
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 18},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  ROUND((SUM(blks_hit)::float / NULLIF(SUM(blks_hit + blks_read), 0) * 100)::numeric, 2) as value\nFROM pg_stat_database\nWHERE datname = current_database()",
            "format": "table"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 90},
                {"color": "green", "value": 95}
              ]
            }
          }
        }
      },
      
      {
        "id": 44,
        "title": "Database Size",
        "type": "stat",
        "gridPos": {"h": 4, "w": 8, "x": 8, "y": 18},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  pg_size_pretty(pg_database_size(current_database())) as value",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 45,
        "title": "Largest Tables",
        "type": "table",
        "gridPos": {"h": 8, "w": 8, "x": 16, "y": 18},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  schemaname || '.' || tablename as table,\n  pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as size\nFROM pg_tables\nWHERE schemaname = 'public'\nORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC\nLIMIT 10",
            "format": "table"
          }
        ]
      },
      
      {
        "id": 46,
        "title": "Transaction Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 26},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  NOW() as time,\n  xact_commit as commits,\n  xact_rollback as rollbacks\nFROM pg_stat_database\nWHERE datname = current_database()",
            "format": "time_series"
          }
        ]
      },
      
      {
        "id": 47,
        "title": "Index Usage",
        "type": "table",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 26},
        "datasource": "PostgreSQL",
        "targets": [
          {
            "rawSql": "SELECT\n  schemaname || '.' || tablename as table,\n  indexname,\n  idx_scan as scans,\n  idx_tup_read as tuples_read,\n  pg_size_pretty(pg_relation_size(indexrelid)) as size\nFROM pg_stat_user_indexes\nWHERE schemaname = 'public'\n  AND idx_scan = 0\nORDER BY pg_relation_size(indexrelid) DESC\nLIMIT 10",
            "format": "table"
          }
        ]
      }
    ]
  }
}

🔔 ALERTS CONFIGURATION
1. Alert Rules
yaml# grafana/provisioning/alerting/rules.yml

apiVersion: 1

groups:
  - name: system_alerts
    interval: 1m
    rules:
      - uid: high_cpu_usage
        title: High CPU Usage
        condition: A
        data:
          - refId: A
            queryType: prometheus
            datasourceUid: prometheus
            model:
              expr: '100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
        for: 5m
        annotations:
          description: 'CPU usage is above 80% for 5 minutes'
        labels:
          severity: warning
        
      - uid: high_memory_usage
        title: High Memory Usage
        condition: A
        data:
          - refId: A
            queryType: prometheus
            datasourceUid: prometheus
            model:
              expr: '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
        for: 5m
        annotations:
          description: 'Memory usage is above 85%'
        labels:
          severity: critical
        
      - uid: disk_space_low
        title: Low Disk Space
        condition: A
        data:
          - refId: A
            queryType: prometheus
            datasourceUid: prometheus
            model:
              expr: '(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100'
        for: 10m
        annotations:
          description: 'Disk usage is above 85%'
        labels:
          severity: warning

  - name: ocr_alerts
    interval: 1m
    rules:
      - uid: high_error_rate
        title: High OCR Error Rate
        condition: A
        data:
          - refId: A
            queryType: postgres
            datasourceUid: postgres
            model:
              rawSql: "SELECT (COUNT(*) FILTER (WHERE success = false)::float / COUNT(*) * 100) as value FROM processing_jobs WHERE created_at > NOW() - INTERVAL '15 minutes'"
        for: 5m
        annotations:
          description: 'OCR error rate above 10% for 5 minutes'
        labels:
          severity: critical
        
      - uid: high_queue_length
        title: High Processing Queue
        condition: A
        data:
          - refId: A
            queryType: postgres
            datasourceUid: postgres
            model:
              rawSql: "SELECT COUNT(*) as value FROM processing_jobs WHERE status IN ('pending', 'processing')"
        for: 5m
        annotations:
          description: 'Processing queue has more than 100 pending jobs'
        labels:
          severity: warning

  - name: database_alerts
    interval: 1m
    rules:
      - uid: high_db_connections
        title: High Database Connections
        condition: A
        data:
          - refId: A
            queryType: postgres
            datasourceUid: postgres
            model:
              rawSql: "SELECT COUNT(*) as value FROM pg_stat_activity WHERE datname = current_database()"
        for: 5m
        annotations:
          description: 'Database has more than 50 active connections'
        labels:
          severity: warning
        
      - uid: slow_queries
        title: Slow Database Queries
        condition: A
        data:
          - refId: A
            queryType: postgres
            datasourceUid: postgres
            model:
              rawSql: "SELECT COUNT(*) as value FROM pg_stat_statements WHERE mean_exec_time > 1000"
        for: 5m
        annotations:
          description: 'Database has queries averaging >1000ms'
        labels:
          severity: warning
2. Notification Channels
yaml# grafana/provisioning/notifiers/notifications.yml

apiVersion: 1

notifiers:
  - name: Email Alerts
    type: email
    uid: email_alerts
    org_id: 1
    is_default: true
    send_reminder: true
    settings:
      addresses: 'admin@example.com;ops@example.com'
      autoResolve: true
  
  - name: Slack Alerts
    type: slack
    uid: slack_alerts
    org_id: 1
    settings:
      url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
      username: 'Grafana Alerts'
      icon_emoji: ':bell:'
      uploadImage: true
      
  - name: PagerDuty
    type: pagerduty
    uid: pagerduty
    org_id: 1
    settings:
      integrationKey: 'YOUR_PAGERDUTY_INTEGRATION_KEY'
      autoResolve: true
      severity: 'critical'

  - name: Discord
    type: discord
    uid: discord
    org_id: 1
    settings:
      url: 'https://discord.com/api/webhooks/YOUR/WEBHOOK'
      message: '{{ template "default.message" . }}'
      avatar_url: 'https://grafana.com/static/img/grafana_icon.svg'
3. Alert Templates
yaml# grafana/provisioning/alerting/templates.yml

apiVersion: 1

templates:
  - name: default
    template: |
      {{ define "default.title" }}
      [{{ .Status | toUpper }}{{ if eq .Status "firing" }}:{{ .Alerts.Firing | len }}{{ end }}] {{ .GroupLabels.alertname }}
      {{ end }}
      
      {{ define "default.message" }}
      {{ if gt (len .Alerts.Firing) 0 }}
      **Firing:**
      {{ range .Alerts.Firing }}
      - {{ .Labels.alertname }}: {{ .Annotations.description }}
        Value: {{ .Value }}
        Started: {{ .StartsAt.Format "2006-01-02 15:04:05" }}
      {{ end }}
      {{ end }}
      
      {{ if gt (len .Alerts.Resolved) 0 }}
      **Resolved:**
      {{ range .Alerts.Resolved }}
      - {{ .Labels.alertname }}
        Resolved: {{ .EndsAt.Format "2006-01-02 15:04:05" }}
      {{ end }}
      {{ end }}
      {{ end }}

🔍 CUSTOM QUERIES
Performance Analysis Queries
sql-- 1. Documents processed per hour by backend
SELECT
  DATE_TRUNC('hour', completed_at) as hour,
  backend_type,
  COUNT(*) as documents,
  AVG(processing_time_ms) as avg_time,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY processing_time_ms) as p95_time
FROM processing_jobs
WHERE completed_at > NOW() - INTERVAL '24 hours'
  AND success = true
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- 2. User growth over time
SELECT
  DATE_TRUNC('week', created_at) as week,
  COUNT(*) as new_users,
  SUM(COUNT(*)) OVER (ORDER BY DATE_TRUNC('week', created_at)) as total_users
FROM users
WHERE created_at > NOW() - INTERVAL '6 months'
GROUP BY 1
ORDER BY 1 DESC;

-- 3. Document processing funnel
SELECT
  'Uploaded' as stage,
  COUNT(*) as count,
  100.0 as percentage
FROM documents
WHERE created_at > NOW() - INTERVAL '24 hours'

UNION ALL

SELECT
  'Processing Started',
  COUNT(*),
  COUNT(*)::float / (SELECT COUNT(*) FROM documents WHERE created_at > NOW() - INTERVAL '24 hours') * 100
FROM processing_jobs
WHERE created_at > NOW() - INTERVAL '24 hours'

UNION ALL

SELECT
  'Successfully Completed',
  COUNT(*),
  COUNT(*)::float / (SELECT COUNT(*) FROM documents WHERE created_at > NOW() - INTERVAL '24 hours') * 100
FROM processing_jobs
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND success = true;

-- 4. Error rate by hour
SELECT
  DATE_TRUNC('hour', created_at) as hour,
  error_type,
  COUNT(*) as occurrences,
  STRING_AGG(DISTINCT error_message, ' | ') as sample_messages
FROM error_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND severity IN ('error', 'critical')
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC;

-- 5. Top slow queries
SELECT
  SUBSTRING(query, 1, 100) as query_preview,
  calls,
  ROUND(mean_exec_time::numeric, 2) as avg_ms,
  ROUND(total_exec_time::numeric, 2) as total_ms,
  ROUND((stddev_exec_time)::numeric, 2) as stddev_ms,
  ROUND((100 * total_exec_time / SUM(total_exec_time) OVER ())::numeric, 2) as pct_total
FROM pg_stat_statements
WHERE calls > 10
ORDER BY mean_exec_time DESC
LIMIT 20;

-- 6. System health summary
SELECT
  'Documents Processed Today' as metric,
  COUNT(*)::text as value
FROM processing_jobs
WHERE DATE(completed_at) = CURRENT_DATE
  AND success = true

UNION ALL

SELECT
  'Active Users (Last Hour)',
  COUNT(DISTINCT user_id)::text
FROM user_sessions
WHERE last_activity_at > NOW() - INTERVAL '1 hour'

UNION ALL

SELECT
  'Error Rate (%)',
  ROUND((COUNT(*) FILTER (WHERE severity IN ('error', 'critical'))::float / 
         NULLIF(COUNT(*), 0) * 100)::numeric, 2)::text
FROM error_logs
WHERE created_at > NOW() - INTERVAL '1 hour'

UNION ALL

SELECT
  'Avg Processing Time (ms)',
  ROUND(AVG(processing_time_ms)::numeric, 0)::text
FROM processing_jobs
WHERE completed_at > NOW() - INTERVAL '1 hour'
  AND success = true;

🚀 DEPLOYMENT
1. Production Deployment Script
bash#!/bin/bash
# deploy-monitoring.sh

set -e

echo "🚀 Deploying Grafana Monitoring Stack..."

# Create directories
mkdir -p grafana/provisioning/{datasources,dashboards,notifiers,alerting}
mkdir -p grafana/dashboards
mkdir -p prometheus

# Set permissions
sudo chown -R 472:472 grafana/  # Grafana UID
sudo chmod -R 755 grafana/

# Copy configurations
echo "📝 Copying configuration files..."
cp configs/prometheus.yml prometheus/
cp configs/datasources/* grafana/provisioning/datasources/
cp configs/dashboards/*.json grafana/dashboards/

# Start services
echo "🐳 Starting Docker containers..."
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for Grafana
echo "⏳ Waiting for Grafana to start..."
sleep 10

# Import dashboards
echo "📊 Importing dashboards..."
for dashboard in grafana/dashboards/*.json; do
  curl -X POST \
    -H "Content-Type: application/json" \
    -u admin:admin123 \
    -d @"$dashboard" \
    http://localhost:3000/api/dashboards/db
done

# Check health
echo "🏥 Checking service health..."
docker-compose -f docker-compose.monitoring.yml ps

echo "✅ Deployment complete!"
echo "📊 Grafana: http://localhost:3000 (admin/admin123)"
echo "📈 Prometheus: http://localhost:9090"
2. Backup Script
bash#!/bin/bash
# backup-dashboards.sh

BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "💾 Backing up Grafana dashboards..."

# Export all dashboards
curl -s -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:3000/api/search?type=dash-db \
  | jq -r '.[] | .uid' \
  | while read uid; do
    curl -s -H "Authorization: Bearer YOUR_API_KEY" \
      "http://localhost:3000/api/dashboards/uid/$uid" \
      | jq '.dashboard' \
      > "$BACKUP_DIR/${uid}.json"
    echo "Backed up: $uid"
  done

# Backup data sources
curl -s -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:3000/api/datasources \
  > "$BACKUP_DIR/datasources.json"

echo "✅ Backup complete: $BACKUP_DIR"
3. Health Check Script
bash#!/bin/bash
# health-check.sh

echo "🏥 Checking Monitoring Stack Health..."

# Check Grafana
if curl -s http://localhost:3000/api/health | grep -q "ok"; then
  echo "✅ Grafana: Healthy"
else
  echo "❌ Grafana: Unhealthy"
fi

# Check Prometheus
if curl -s http://localhost:9090/-/healthy | grep -q "Prometheus"; then
  echo "✅ Prometheus: Healthy"
else
  echo "❌ Prometheus: Unhealthy"
fi

# Check Node Exporter
if curl -s http://localhost:9100/metrics | grep -q "node_"; then
  echo "✅ Node Exporter: Healthy"
else
  echo "❌ Node Exporter: Unhealthy"
fi

# Check Postgres Exporter
if curl -s http://localhost:9187/metrics | grep -q "pg_"; then
  echo "✅ Postgres Exporter: Healthy"
else
  echo "❌ Postgres Exporter: Unhealthy"
fi
```

---

## ✅ BEST PRACTICES

### 1. Dashboard Organization
```
✅ DO:
- Group related panels together
- Use consistent time ranges
- Add descriptions to panels
- Use meaningful panel titles
- Set appropriate refresh rates
- Define alert thresholds

❌ DON'T:
- Overload dashboards (max 15 panels)
- Use auto-refresh < 10s
- Mix different data granularities
- Forget to set Y-axis labels
- Use default panel titles
2. Query Optimization
sql-- ✅ GOOD: Use time filters
SELECT COUNT(*)
FROM documents
WHERE created_at > NOW() - INTERVAL '1 hour'

-- ❌ BAD: No time filter (scans entire table)
SELECT COUNT(*)
FROM documents

-- ✅ GOOD: Use indexes
SELECT *
FROM processing_jobs
WHERE user_id = $user_id  -- indexed column
  AND created_at > $__timeFilter

-- ✅ GOOD: Aggregate in database
SELECT
  DATE_TRUNC('hour', created_at) as time,
  COUNT(*) as count
FROM documents
WHERE $__timeFilter(created_at)
GROUP BY 1

-- ❌ BAD: Fetch all rows and aggregate in Grafana
SELECT created_at
FROM documents
WHERE $__timeFilter(created_at)
3. Alert Configuration
yaml# ✅ GOOD alert configuration
- name: critical_error_rate
  condition: A
  for: 5m  # Wait 5 minutes before firing
  annotations:
    description: 'Detailed description with context'
    runbook_url: 'https://wiki.example.com/runbooks/error-rate'
  labels:
    severity: critical
    team: backend

# ❌ BAD alert configuration
- name: alert1
  condition: A
  for: 0m  # Fires immediately (too sensitive)
  annotations:
    description: 'Error'  # Not helpful
4. Security
yaml# Secure Grafana configuration

# 1. Change default credentials
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}

# 2. Disable anonymous access
GF_AUTH_ANONYMOUS_ENABLED: false

# 3. Enable HTTPS
GF_SERVER_PROTOCOL: https
GF_SERVER_CERT_FILE: /etc/grafana/ssl/grafana.crt
GF_SERVER_CERT_KEY: /etc/grafana/ssl/grafana.key

# 4. Use read-only database user
datasources:
  - name: PostgreSQL
    user: grafana_reader  # Read-only user
    
# 5. Enable audit logging
GF_LOG_FILTERS: alerting.notifier:debug
```

### 5. Performance
```
Optimization Tips:

1. Query Performance
   - Always use time filters ($__timeFilter)
   - Add indexes on filtered columns
   - Use aggregation in database
   - Limit result sets

2. Dashboard Performance
   - Set appropriate refresh intervals (≥30s)
   - Use query caching
   - Avoid complex transformations
   - Limit panel count (≤15 per dashboard)

3. Data Retention
   - Prometheus: 30 days (configurable)
   - Postgres: Archive old data
   - Grafana: Clean old snapshots

4. Resource Usage
   - Monitor Grafana CPU/RAM
   - Scale horizontally if needed
   - Use dedicated monitoring DB
```

---

## 🎓 SUMMARY

### Quick Start Checklist

- [ ] Install Docker & Docker Compose
- [ ] Start monitoring stack
- [ ] Configure data sources
- [ ] Import dashboards
- [ ] Set up alerts
- [ ] Configure notifications
- [ ] Test alert rules
- [ ] Document runbooks
- [ ] Train team on dashboards
- [ ] Schedule regular reviews

### Dashboard URLs
```
Main Dashboards:
├── System Overview:      http://localhost:3000/d/system-overview
├── OCR Performance:      http://localhost:3000/d/ocr-performance
├── User Activity:        http://localhost:3000/d/user-activity
├── Error Monitoring:     http://localhost:3000/d/error-monitoring
└── Database Performance: http://localhost:3000/d/database-performance

Services:
├── Grafana:          http://localhost:3000
├── Prometheus:       http://localhost:9090
├── Node Exporter:    http://localhost:9100/metrics
└── Postgres Exporter: http://localhost:9187/metrics
```

### Key Metrics to Monitor
```
🔴 CRITICAL (Alert immediately)
- Error rate > 10%
- CPU usage > 90%
- Disk usage > 95%
- Database connections > max_connections
- Queue length > 1000

🟡 WARNING (Monitor closely)
- Error rate > 5%
- CPU usage > 80%
- Memory usage > 85%
- Slow queries > 1000ms
- Queue length > 100

🟢 NORMAL (Track trends)
- Processing time
- User activity
- Document uploads
- API request rates