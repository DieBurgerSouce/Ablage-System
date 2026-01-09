# DDoS Attack Mitigation Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-1 (Critical Security)
> RTO: 5 Minuten | RPO: N/A

## Alert

```
HighRequestRate - > 1000 req/s
SuspiciousTrafficPattern - Anomale Zugriffsmuster
NginxConnectionSpike - > 500 gleichzeitige Verbindungen
BandwidthSpike - > 100 Mbps eingehend
```

## Symptome

- Extrem langsame oder keine Antworten
- Nginx Connection Timeouts
- CPU/RAM-Auslastung auf 100%
- Legitime Benutzer können nicht zugreifen
- Ungewöhnlich hoher Traffic von wenigen IPs

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Angriffsmuster erkennen

```bash
# Traffic-Übersicht (letzte 5 Minuten)
docker logs ablage-nginx --since 5m 2>&1 | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -20

# Requests pro Sekunde
docker logs ablage-nginx --since 1m 2>&1 | wc -l

# Verdächtige User-Agents
docker logs ablage-nginx --since 5m 2>&1 | \
  awk -F'"' '{print $6}' | sort | uniq -c | sort -rn | head -10

# Angegriffene Endpunkte
docker logs ablage-nginx --since 5m 2>&1 | \
  awk '{print $7}' | sort | uniq -c | sort -rn | head -10
```

### 2. Top-Angreifer identifizieren

```bash
# Top 20 IPs nach Request-Anzahl
docker logs ablage-nginx --since 10m 2>&1 | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -20

# IPs mit verdächtiger Rate (> 100 req/min)
docker logs ablage-nginx --since 1m 2>&1 | \
  awk '{print $1}' | sort | uniq -c | \
  awk '$1 > 100 {print $2, $1}'
```

### 3. Sofort-Block der Top-Angreifer

```bash
# Top 10 IPs blockieren
TOP_IPS=$(docker logs ablage-nginx --since 5m 2>&1 | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -10 | awk '{print $2}')

for ip in $TOP_IPS; do
    echo "deny $ip;" >> /tmp/blocked_ddos.conf
done

# In Nginx einfügen
docker cp /tmp/blocked_ddos.conf ablage-nginx:/etc/nginx/conf.d/blocked_ddos.conf
docker exec ablage-nginx nginx -s reload
```

---

## Gegenmaßnahmen

### Option A: Nginx Rate Limiting aktivieren

```bash
# Temporäre Rate Limiting Konfiguration
cat > /tmp/rate_limit.conf << 'EOF'
# Limit-Zonen definieren
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=1r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# Limits anwenden
limit_req zone=api_limit burst=20 nodelay;
limit_conn conn_limit 10;

# Error-Seite für Rate Limiting
error_page 429 = @too_many_requests;
location @too_many_requests {
    return 429 '{"error": "Zu viele Anfragen"}';
    add_header Content-Type application/json;
}
EOF

docker cp /tmp/rate_limit.conf ablage-nginx:/etc/nginx/conf.d/rate_limit.conf
docker exec ablage-nginx nginx -t && docker exec ablage-nginx nginx -s reload
```

### Option B: IP-Basierte Geo-Blocking

```bash
# Falls Angriff aus bestimmten Regionen kommt
# GeoIP-Datenbank nutzen (falls konfiguriert)
docker exec ablage-nginx cat > /etc/nginx/conf.d/geoip_block.conf << 'EOF'
# Nur DACH-Region erlauben (temporär)
map $geoip_country_code $allowed_country {
    default no;
    DE yes;
    AT yes;
    CH yes;
}

# In server-Block:
# if ($allowed_country = no) { return 403; }
EOF
```

### Option C: Connection Limits

```bash
# Nginx Worker-Connections anpassen
docker exec ablage-nginx nginx -c "
events {
    worker_connections 2048;
}
http {
    keepalive_timeout 5;
    keepalive_requests 10;
}
"
docker exec ablage-nginx nginx -s reload
```

### Option D: Backend-Schutz aktivieren

```bash
# API-seitiges Rate Limiting
curl -X POST http://localhost:8000/api/v1/admin/emergency/rate-limit \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "global_limit": 100,
    "per_ip_limit": 10,
    "burst_allowance": 5,
    "duration_minutes": 30
  }'

# Maintenance Mode für kritische Endpunkte
curl -X POST http://localhost:8000/api/v1/admin/maintenance/partial \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "endpoints": ["/api/v1/documents/upload", "/api/v1/ocr/process"],
    "message": "Wartungsarbeiten"
  }'
```

### Option E: Fail2Ban aktivieren

```bash
# Fail2Ban Jail für Nginx
cat > /etc/fail2ban/jail.d/nginx-ddos.conf << 'EOF'
[nginx-ddos]
enabled = true
port = http,https
filter = nginx-ddos
logpath = /var/log/nginx/access.log
maxretry = 100
findtime = 60
bantime = 3600
action = iptables-multiport[name=nginx-ddos, port="http,https"]
EOF

# Fail2Ban Filter
cat > /etc/fail2ban/filter.d/nginx-ddos.conf << 'EOF'
[Definition]
failregex = ^<HOST> .* "(GET|POST|PUT|DELETE).*
ignoreregex =
EOF

systemctl restart fail2ban
```

---

## Diagnose

### 4. Angriffs-Charakteristiken analysieren

```bash
# Request-Verteilung über Zeit
docker logs ablage-nginx --since 30m 2>&1 | \
  awk '{print substr($4,2,17)}' | uniq -c

# HTTP-Methoden-Verteilung
docker logs ablage-nginx --since 10m 2>&1 | \
  awk '{print $6}' | tr -d '"' | sort | uniq -c | sort -rn

# Response-Codes
docker logs ablage-nginx --since 10m 2>&1 | \
  awk '{print $9}' | sort | uniq -c | sort -rn

# Payload-Größen
docker logs ablage-nginx --since 10m 2>&1 | \
  awk '{print $10}' | sort -n | tail -20
```

### 5. System-Auswirkungen prüfen

```bash
# Aktive Verbindungen
ss -s

# Nginx-Worker-Status
docker exec ablage-nginx nginx -T 2>&1 | grep worker

# Backend-Antwortzeiten
docker logs ablage-backend --since 5m 2>&1 | \
  grep "request_time" | \
  awk -F'request_time=' '{print $2}' | \
  awk '{sum+=$1; count++} END {print "Avg:", sum/count, "s"}'

# Redis-Verbindungen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD INFO clients

# PostgreSQL-Verbindungen
docker exec ablage-postgres psql -U ablage_admin -d ablage -c \
  "SELECT count(*) as connections FROM pg_stat_activity;"
```

### 6. Angriffs-Protokoll erstellen

```bash
# Forensik-Daten sammeln
INCIDENT_DIR="/tmp/ddos_incident_$(date +%Y%m%d_%H%M%S)"
mkdir -p $INCIDENT_DIR

# Logs sichern
docker logs ablage-nginx --since 1h > $INCIDENT_DIR/nginx.log
docker logs ablage-backend --since 1h > $INCIDENT_DIR/backend.log

# Top-Angreifer dokumentieren
docker logs ablage-nginx --since 1h 2>&1 | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -100 > $INCIDENT_DIR/top_ips.txt

# Netzwerk-Statistiken
ss -s > $INCIDENT_DIR/network_stats.txt
netstat -an | grep :80 | wc -l >> $INCIDENT_DIR/network_stats.txt

echo "Incident data saved to: $INCIDENT_DIR"
```

---

## Recovery

### Blockierungen schrittweise aufheben

```bash
# Rate Limiting lockern
curl -X POST http://localhost:8000/api/v1/admin/rate-limits/relax \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"factor": 2}'

# Einzelne IPs freigeben (nach Verifizierung)
docker exec ablage-nginx sed -i '/192.168.1.100/d' /etc/nginx/conf.d/blocked_ddos.conf
docker exec ablage-nginx nginx -s reload

# Fail2Ban-Bans prüfen
fail2ban-client status nginx-ddos
fail2ban-client set nginx-ddos unbanip 192.168.1.100
```

### Normale Betriebsparameter wiederherstellen

```bash
# Rate Limiting auf Normal
curl -X DELETE http://localhost:8000/api/v1/admin/emergency/rate-limit \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Maintenance Mode deaktivieren
curl -X DELETE http://localhost:8000/api/v1/admin/maintenance/partial \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Nginx-Limits zurücksetzen
docker exec ablage-nginx rm /etc/nginx/conf.d/rate_limit.conf
docker exec ablage-nginx rm /etc/nginx/conf.d/blocked_ddos.conf
docker exec ablage-nginx nginx -s reload
```

---

## Präventivmaßnahmen

### 1. Permanentes Rate Limiting

```nginx
# nginx.conf - Produktions-Limits
http {
    # API-Endpunkte
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;

    # Auth-Endpunkte (strenger)
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/s;

    # Upload-Endpunkte
    limit_req_zone $binary_remote_addr zone=upload:10m rate=2r/s;

    server {
        location /api/v1/ {
            limit_req zone=api burst=50 nodelay;
        }

        location /api/v1/auth/ {
            limit_req zone=auth burst=10 nodelay;
        }

        location /api/v1/documents/upload {
            limit_req zone=upload burst=5 nodelay;
        }
    }
}
```

### 2. Monitoring einrichten

```yaml
# Prometheus Alert Rules
- alert: HighRequestRate
  expr: rate(nginx_http_requests_total[1m]) > 1000
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Möglicher DDoS-Angriff"

- alert: SuspiciousIPActivity
  expr: |
    topk(10, sum by (remote_addr) (rate(nginx_http_requests_total[5m]))) > 100
  for: 2m
  labels:
    severity: warning
```

### 3. CDN/WAF-Integration

```bash
# Falls Cloudflare oder ähnlicher Dienst verfügbar:
# - DDoS-Protection aktivieren
# - Bot-Management einschalten
# - Rate Limiting auf Edge-Level

# Für On-Premises: HAProxy als zusätzliche Schutzschicht
cat > /etc/haproxy/ddos.cfg << 'EOF'
frontend http_front
    bind *:80

    # Stick-Table für Rate Limiting
    stick-table type ip size 1m expire 10s store conn_rate(10s)

    # Rate Limiting
    acl too_many_conn src_conn_rate gt 100
    tcp-request connection reject if too_many_conn

    default_backend web_back
EOF
```

---

## Verifikation

```bash
# Request-Rate nach Mitigation
watch -n 5 'docker logs ablage-nginx --since 1m 2>&1 | wc -l'

# Legitime Benutzer testen
curl -w "\nTime: %{time_total}s\n" http://localhost:8000/api/v1/health

# Blockierte IPs zählen
docker exec ablage-nginx grep -c "deny" /etc/nginx/conf.d/blocked*.conf

# Fail2Ban-Status
fail2ban-client status nginx-ddos
```

---

## Metriken & Dashboards

- **Grafana Dashboard**: "Security - DDoS Monitoring"
- **Prometheus Queries**:
  ```promql
  # Request-Rate pro IP
  topk(10, sum by (remote_addr) (rate(nginx_http_requests_total[5m])))

  # Blocked Requests
  rate(nginx_http_requests_total{status="429"}[5m])

  # Connection Count
  nginx_connections_active
  ```

---

## Eskalation

| Schweregrad | Aktion |
|-------------|--------|
| < 500 req/s | On-Call: Beobachten |
| 500-1000 req/s | Rate Limiting aktivieren |
| 1000-5000 req/s | IP-Blocking, Team informieren |
| 5000+ req/s | Eskalation an Netzwerk-Team/ISP |

---

## Kommunikation

### Interne Benachrichtigung

```bash
# Slack/Discord Alert
curl -X POST $SLACK_WEBHOOK \
  -H "Content-Type: application/json" \
  -d '{
    "text": "⚠️ DDoS-Angriff erkannt",
    "attachments": [{
      "color": "danger",
      "fields": [
        {"title": "Request-Rate", "value": "5000+ req/s", "short": true},
        {"title": "Top-Angreifer", "value": "192.168.1.x (3000 req)", "short": true},
        {"title": "Status", "value": "Mitigation aktiv", "short": true}
      ]
    }]
  }'
```

### Status-Page Update

```bash
# StatusPage/Statuspage.io Update
curl -X POST "https://api.statuspage.io/v1/pages/$PAGE_ID/incidents" \
  -H "Authorization: OAuth $STATUSPAGE_TOKEN" \
  -d '{
    "incident": {
      "name": "Erhöhte Last - Eingeschränkte Verfügbarkeit",
      "status": "investigating",
      "impact_override": "partial"
    }
  }'
```

---

## Verwandte Runbooks

- [Security Brute Force Response](security-brute-force-response.md)
- [API Error Rate Spike](api-error-rate-spike.md)
- [Nginx Configuration Recovery](nginx-configuration-recovery.md)
