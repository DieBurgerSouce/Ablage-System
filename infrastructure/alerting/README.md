# Alerting Infrastructure - Ablage-System OCR

Multi-channel alerting system with Prometheus Alertmanager for production monitoring.

## 🚀 Quick Start

```bash
# Setup and start Alertmanager
cd infrastructure/alerting
./setup-alerting.sh setup

# Send test alert
./setup-alerting.sh test

# View logs
./setup-alerting.sh logs
```

## 📋 Features

### Multi-Channel Alerting

- **PagerDuty**: Critical alerts with on-call paging
- **OpsGenie**: Incident management and escalation
- **Slack**: Team notifications across multiple channels
- **Email**: HTML-formatted email alerts as backup

### Intelligent Routing

- **Severity-Based**: Different handling for critical/high/warning alerts
- **Service-Specific**: Dedicated channels for GPU, database, etc.
- **Time-Based**: Configurable repeat intervals
- **Inhibition Rules**: Prevent alert storms

## ⚙️ Configuration

### Environment Variables

Create `.env` file from template:

```bash
cp .env.example .env
nano .env
```

Required variables:

```bash
# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# PagerDuty
PAGERDUTY_SERVICE_KEY=your_service_key_here

# OpsGenie
OPSGENIE_API_KEY=your_api_key_here

# Email (SMTP)
ALERT_EMAIL_TO=alerts@yourdomain.com
ALERT_EMAIL_FROM=alertmanager@ablage-system.local
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password

# Webhook
WEBHOOK_SECRET=secure_random_string
```

### Slack Setup

1. **Create Slack App**: https://api.slack.com/apps
2. **Enable Incoming Webhooks**
3. **Create channels**:
   - `#alerts-critical` - Critical alerts
   - `#alerts-high` - High priority
   - `#alerts-warnings` - Warnings
   - `#alerts-gpu` - GPU-specific
   - `#alerts-database` - Database issues
4. **Add webhook URLs** to each channel
5. **Update** `alertmanager.yml` with channel webhook URLs

### PagerDuty Setup

1. **Create Service**: https://support.pagerduty.com/docs/services-and-integrations
2. **Integration Type**: Events API v2
3. **Copy Integration Key** to `.env` as `PAGERDUTY_SERVICE_KEY`
4. **Configure Escalation Policy**
5. **Test Integration**: `./setup-alerting.sh test`

### OpsGenie Setup

1. **Create Integration**: https://docs.opsgenie.com/docs/integration-overview
2. **Integration Type**: Prometheus
3. **Copy API Key** to `.env` as `OPSGENIE_API_KEY`
4. **Configure Teams** and routing rules
5. **Set up on-call schedules**

## 🔧 Alert Routing

### Severity Levels

**Critical** (🔴):
- **Channels**: PagerDuty + OpsGenie + Slack
- **Response Time**: Immediate paging
- **Repeat Interval**: 5 minutes
- **Examples**: Service down, GPU OOM, data loss

**High** (🟠):
- **Channels**: Slack (no paging off-hours)
- **Response Time**: 5 minutes
- **Repeat Interval**: 1 hour
- **Examples**: High error rate, elevated queue length

**Warning** (🟡):
- **Channels**: Slack only
- **Response Time**: Best effort
- **Repeat Interval**: 4 hours
- **Examples**: Resource warnings, slow queries

### Service-Specific Routing

```yaml
# GPU Alerts → #alerts-gpu
match_re:
  alertname: GPU.*

# Database Alerts → #alerts-database
match_re:
  service: postgres|database
```

### Inhibition Rules

Prevent alert storms:

```yaml
# Critical alerts suppress warnings for same service
source_match:
  severity: 'critical'
target_match:
  severity: 'warning'
equal: ['alertname', 'service']

# Service down suppresses all other alerts
source_match_re:
  alertname: '.*Down'
target_match_re:
  alertname: '.*'
equal: ['service']
```

## 📊 Alert Templates

### Slack Templates

Located in `templates/slack.tmpl`:

- `slack.critical.text` - Critical alerts with runbook links
- `slack.high.text` - High priority alerts
- `slack.warning.text` - Warning notifications
- `slack.gpu.text` - GPU-specific formatting
- `slack.database.text` - Database alert details

### PagerDuty Template

Located in `templates/pagerduty.tmpl`:

- Incident description with all context
- Links to Grafana dashboards
- Runbook URLs
- Service and instance details

### OpsGenie Template

Located in `templates/opsgenie.tmpl`:

- Rich message formatting
- Priority levels (P1-P5)
- Tags for filtering
- Detailed alert context

### Email Template

Located in `templates/email.tmpl`:

- HTML-formatted emails
- Color-coded by severity
- Embedded links to dashboards
- Complete alert details

## 🧪 Testing

### Send Test Alert

```bash
./setup-alerting.sh test
```

This sends a test warning alert to all configured channels.

### Manual Test Alert

```bash
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "service": "test"
    },
    "annotations": {
      "summary": "This is a test",
      "description": "Testing alerting system"
    }
  }]'
```

### Verify Alert Delivery

1. **Check Alertmanager UI**: http://localhost:9093
2. **Check Slack channels** for notifications
3. **Check PagerDuty** for incidents
4. **Check OpsGenie** for alerts
5. **Check email inbox**

## 📝 Prometheus Integration

### Configure Prometheus

Add to `prometheus.yml`:

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

rule_files:
  - "alerts/*.yml"
```

### Sample Alert Rules

Generate sample rules:

```bash
./setup-alerting.sh rules
```

This creates `sample-alert-rules.yml` with:

- API health alerts
- GPU monitoring alerts
- Database alerts
- Document processing alerts
- System resource alerts

### Add Rules to Prometheus

```bash
# Copy to Prometheus config
cp sample-alert-rules.yml /opt/ablage-system/infrastructure/monitoring/prometheus/alerts/

# Reload Prometheus
docker exec prometheus kill -HUP 1

# Verify rules loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | .name'
```

## 🌐 Webhook Receiver

Custom webhook endpoint for advanced integrations.

### Features

- **Database Storage**: Store all alerts in PostgreSQL
- **Custom Actions**: Trigger automated responses
- **Auto-Scaling**: Scale workers on high load
- **GPU Management**: Clear GPU cache on OOM warnings

### Endpoints

- `GET /health` - Health check
- `POST /webhook` - Receive alerts (requires X-Webhook-Secret header)
- `POST /webhook/test` - Test endpoint

### Configuration

```bash
# In alertmanager.yml
receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://webhook-receiver:5001/webhook'
        send_resolved: true
        http_config:
          headers:
            X-Webhook-Secret: '${WEBHOOK_SECRET}'
```

### Custom Actions

Edit `webhook-receiver/webhook_receiver.py`:

```python
def trigger_custom_action(alert: Dict[str, Any]) -> None:
    """Add your custom logic here."""
    alert_name = alert.get('labels', {}).get('alertname', '')

    # Example: Auto-scale on high queue length
    if alert_name == 'HighDocumentQueueLength':
        requests.post(f'{BACKEND_API_URL}/api/v1/workers/scale',
                     json={'desired_count': 5})
```

## 🔒 Security

### Webhook Security

- **Secret Header**: All webhook requests require `X-Webhook-Secret`
- **TLS Encryption**: Use HTTPS in production
- **IP Whitelisting**: Restrict webhook access to known IPs

### Credentials Management

- **Never commit** `.env` file to git
- **Use secrets management** (Vault, AWS Secrets Manager) in production
- **Rotate secrets** regularly
- **Audit access** to notification channels

## 🐛 Troubleshooting

### Alerts Not Firing

```bash
# Check Prometheus rules
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.state == "firing")'

# Check Alertmanager status
curl http://localhost:9093/api/v1/status

# View Alertmanager logs
docker logs ablage-alertmanager

# Check if Prometheus can reach Alertmanager
curl http://localhost:9090/api/v1/alertmanagers
```

### Slack Not Receiving Alerts

```bash
# Test webhook URL directly
curl -X POST "${SLACK_WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message"}'

# Check Alertmanager logs for errors
docker logs ablage-alertmanager 2>&1 | grep -i slack

# Verify webhook URL in alertmanager.yml
docker exec ablage-alertmanager cat /etc/alertmanager/alertmanager.yml | grep slack_api_url
```

### PagerDuty Not Creating Incidents

```bash
# Test PagerDuty API
curl -X POST https://events.pagerduty.com/v2/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "routing_key": "YOUR_SERVICE_KEY",
    "event_action": "trigger",
    "payload": {
      "summary": "Test alert",
      "severity": "critical",
      "source": "test"
    }
  }'

# Check service key in .env
cat .env | grep PAGERDUTY_SERVICE_KEY
```

### Email Not Sending

```bash
# Test SMTP connection
docker run --rm -it --entrypoint sh prom/alertmanager:v0.27.0 \
  -c "apk add --no-cache mailx && echo 'Test' | mail -s 'Test' -S smtp=smtp://SMTP_HOST:SMTP_PORT your@email.com"

# Check SMTP credentials
cat .env | grep SMTP

# View email-related logs
docker logs ablage-alertmanager 2>&1 | grep -i email
```

### Duplicate Alerts

```bash
# Check group_by configuration
# Adjust in alertmanager.yml:
route:
  group_by: ['alertname', 'cluster', 'service', 'severity']
  group_interval: 5m  # Increase if getting duplicates

# Reload configuration
docker exec ablage-alertmanager kill -HUP 1
```

### Alerts Not Resolving

```bash
# Check if Prometheus is sending resolved alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state == "inactive")'

# Verify send_resolved is true in receivers
docker exec ablage-alertmanager cat /etc/alertmanager/alertmanager.yml | grep send_resolved

# Check resolve_timeout
# In alertmanager.yml:
global:
  resolve_timeout: 5m  # Adjust if needed
```

## 📊 Monitoring

### Alertmanager Metrics

Access metrics: http://localhost:9093/metrics

Key metrics:

```promql
# Alerts received
alertmanager_alerts_received_total

# Alerts sent successfully
alertmanager_notifications_total{status="success"}

# Alerts failed to send
alertmanager_notifications_total{status="failure"}

# Alerts currently firing
alertmanager_alerts{state="active"}

# Silences active
alertmanager_silences{state="active"}
```

### Create Grafana Dashboard

Import dashboard ID: 9578 (Alertmanager dashboard)

Or create custom dashboard with panels:

- Alert rate (by severity)
- Notification delivery rate
- Notification latency
- Failed notifications
- Active alerts by service

## 🔄 Maintenance

### Reload Configuration

After editing `alertmanager.yml`:

```bash
# Validate configuration
docker run --rm -v "$(pwd)/alertmanager.yml:/tmp/alertmanager.yml:ro" \
  prom/alertmanager:v0.27.0 \
  amtool check-config /tmp/alertmanager.yml

# Reload Alertmanager
docker exec ablage-alertmanager kill -HUP 1

# Or restart
./setup-alerting.sh restart
```

### Silence Alerts

**Via UI**: http://localhost:9093/#/silences

**Via CLI**:

```bash
# Silence all alerts for a service
docker exec ablage-alertmanager amtool silence add \
  service=backend \
  --duration=1h \
  --comment="Planned maintenance"

# List active silences
docker exec ablage-alertmanager amtool silence query

# Remove silence
docker exec ablage-alertmanager amtool silence expire <SILENCE_ID>
```

### Backup Configuration

```bash
# Backup
tar -czf alertmanager-backup-$(date +%Y%m%d).tar.gz \
  alertmanager.yml \
  templates/ \
  .env

# Restore
tar -xzf alertmanager-backup-20250124.tar.gz
./setup-alerting.sh restart
```

## 📚 Resources

- [Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Slack Webhook Documentation](https://api.slack.com/messaging/webhooks)
- [PagerDuty Events API](https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgw-events-api-v2-overview)
- [OpsGenie Integration](https://docs.opsgenie.com/docs/prometheus-integration)
- [Alert Template Examples](https://prometheus.io/docs/alerting/latest/notification_examples/)

---

**Last Updated**: 2025-01-24
**Maintainer**: Ablage-System Team
