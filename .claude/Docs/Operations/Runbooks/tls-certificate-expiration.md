# TLS Certificate Expiration Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-1 (wenn < 24h) / SEV-2 (wenn < 7 Tage)
> RTO: 30 Minuten | RPO: N/A

## Alert

```
TLSCertificateExpiringSoon - Zertifikat läuft in < 7 Tagen ab
TLSCertificateCritical - Zertifikat läuft in < 24 Stunden ab
TLSCertificateExpired - Zertifikat ist abgelaufen
```

## Symptome

- Browser zeigt "Nicht sicher" oder Zertifikatsfehler
- HTTPS-Verbindungen schlagen fehl
- API-Clients melden SSL-Fehler
- Benutzer können sich nicht anmelden
- Webhooks zu externen Diensten schlagen fehl

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Zertifikatsstatus prüfen

```bash
# Aktuelles Zertifikat anzeigen
echo | openssl s_client -servername localhost -connect localhost:443 2>/dev/null | \
  openssl x509 -noout -dates -subject

# Ablaufdatum extrahieren
echo | openssl s_client -servername localhost -connect localhost:443 2>/dev/null | \
  openssl x509 -noout -enddate

# Tage bis Ablauf berechnen
EXPIRY=$(echo | openssl s_client -servername localhost -connect localhost:443 2>/dev/null | \
  openssl x509 -noout -enddate | cut -d= -f2)
EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))
echo "Tage bis Ablauf: $DAYS_LEFT"
```

### 2. Alle Zertifikate prüfen

```bash
# Nginx-Zertifikate
docker exec ablage-nginx ls -la /etc/nginx/ssl/

# Zertifikatskette validieren
docker exec ablage-nginx openssl verify -CAfile /etc/nginx/ssl/ca-bundle.crt \
  /etc/nginx/ssl/server.crt

# MinIO-Zertifikate
docker exec ablage-minio ls -la /root/.minio/certs/
```

### 3. Let's Encrypt Status (falls verwendet)

```bash
# Certbot-Status
certbot certificates

# Renewal-Versuch (Dry-Run)
certbot renew --dry-run

# Aktuelle Zertifikate
ls -la /etc/letsencrypt/live/
```

---

## Erneuerung

### Option A: Let's Encrypt Auto-Renewal

```bash
# Certbot Renewal erzwingen
certbot renew --force-renewal

# Nach erfolgreicher Erneuerung: Nginx neu laden
docker exec ablage-nginx nginx -s reload

# Automatische Renewal via Cronjob prüfen
cat /etc/cron.d/certbot
# Sollte enthalten: 0 0,12 * * * root certbot renew --quiet
```

### Option B: Manuelles Let's Encrypt

```bash
# Neues Zertifikat anfordern
certbot certonly --webroot -w /var/www/html \
  -d ablage_system.example.de \
  -d www.ablage.example.de

# Zertifikate in Container kopieren
docker cp /etc/letsencrypt/live/ablage.example.de/fullchain.pem \
  ablage-nginx:/etc/nginx/ssl/server.crt
docker cp /etc/letsencrypt/live/ablage.example.de/privkey.pem \
  ablage-nginx:/etc/nginx/ssl/server.key

# Nginx neu laden
docker exec ablage-nginx nginx -t && docker exec ablage-nginx nginx -s reload
```

### Option C: Selbstsigniertes Zertifikat (Notfall)

```bash
# Nur für Notfälle - KEINE Produktionslösung!
# Generiert selbstsigniertes Zertifikat (1 Jahr gültig)

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/selfsigned.key \
  -out /tmp/selfsigned.crt \
  -subj "/C=DE/ST=Bayern/L=Muenchen/O=Ablage/CN=ablage.local"

# In Container kopieren
docker cp /tmp/selfsigned.crt ablage-nginx:/etc/nginx/ssl/server.crt
docker cp /tmp/selfsigned.key ablage-nginx:/etc/nginx/ssl/server.key

# Nginx neu laden
docker exec ablage-nginx nginx -t && docker exec ablage-nginx nginx -s reload

echo "WARNUNG: Selbstsigniertes Zertifikat - Browser werden Warnung anzeigen!"
```

### Option D: Kommerzielles Zertifikat

```bash
# CSR (Certificate Signing Request) erstellen
openssl req -new -newkey rsa:2048 -nodes \
  -keyout /tmp/ablage.key \
  -out /tmp/ablage.csr \
  -subj "/C=DE/ST=Bayern/L=Muenchen/O=Ablage GmbH/CN=ablage.example.de"

# CSR an CA senden (DigiCert, Sectigo, etc.)
cat /tmp/ablage.csr

# Nach Erhalt des Zertifikats:
# 1. Zertifikat speichern als /tmp/ablage.crt
# 2. Intermediate-Zertifikate herunterladen
# 3. Kette erstellen
cat /tmp/ablage.crt /tmp/intermediate.crt > /tmp/fullchain.crt

# In Container kopieren
docker cp /tmp/fullchain.crt ablage-nginx:/etc/nginx/ssl/server.crt
docker cp /tmp/ablage.key ablage-nginx:/etc/nginx/ssl/server.key

docker exec ablage-nginx nginx -t && docker exec ablage-nginx nginx -s reload
```

---

## Zertifikatsketten-Probleme

### Intermediate-Zertifikat fehlt

```bash
# Kette prüfen
echo | openssl s_client -servername localhost -connect localhost:443 2>&1 | \
  grep -E "Verify return|depth"

# Wenn "unable to verify": Intermediate fehlt
# Intermediate-Zertifikate herunterladen (je nach CA):
# - Let's Encrypt: https://letsencrypt.org/certificates/
# - DigiCert: https://www.digicert.com/kb/digicert-root-certificates.htm

# Kette zusammenfügen
cat server.crt intermediate.crt > fullchain.crt
```

### Root-CA nicht vertrauenswürdig

```bash
# System-CA-Bundle aktualisieren
update-ca-certificates

# Oder manuell Root-CA hinzufügen
cp custom-root-ca.crt /usr/local/share/ca-certificates/
update-ca-certificates
```

---

## Service-spezifische Erneuerung

### MinIO TLS

```bash
# MinIO verwendet eigene Zertifikate
docker exec ablage-minio mkdir -p /root/.minio/certs

# Zertifikate kopieren
docker cp /path/to/public.crt ablage-minio:/root/.minio/certs/public.crt
docker cp /path/to/private.key ablage-minio:/root/.minio/certs/private.key

# MinIO neustarten
docker-compose restart minio
```

### Redis TLS (falls aktiviert)

```bash
# Redis TLS-Konfiguration
docker exec ablage-redis cat /etc/redis/redis.conf | grep tls

# Zertifikate aktualisieren
docker cp /path/to/redis.crt ablage-redis:/etc/redis/certs/
docker cp /path/to/redis.key ablage-redis:/etc/redis/certs/

docker-compose restart redis
```

### PostgreSQL TLS (falls aktiviert)

```bash
# PostgreSQL SSL-Konfiguration prüfen
docker exec ablage-postgres cat /var/lib/postgresql/data/postgresql.conf | grep ssl

# Zertifikate aktualisieren
docker cp /path/to/server.crt ablage-postgres:/var/lib/postgresql/data/
docker cp /path/to/server.key ablage-postgres:/var/lib/postgresql/data/

docker-compose restart postgres
```

---

## Monitoring & Alerting

### Prometheus Alert Rules

```yaml
groups:
  - name: tls_alerts
    rules:
      - alert: TLSCertificateExpiringSoon
        expr: probe_ssl_earliest_cert_expiry - time() < 86400 * 7
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "TLS-Zertifikat läuft in weniger als 7 Tagen ab"
          description: "{{ $labels.instance }}: {{ $value | humanizeDuration }}"

      - alert: TLSCertificateCritical
        expr: probe_ssl_earliest_cert_expiry - time() < 86400
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "TLS-Zertifikat läuft in weniger als 24 Stunden ab"

      - alert: TLSCertificateExpired
        expr: probe_ssl_earliest_cert_expiry - time() < 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "TLS-Zertifikat ist abgelaufen!"
```

### Blackbox Exporter Konfiguration

```yaml
# /etc/prometheus/blackbox.yml
modules:
  https_check:
    prober: http
    timeout: 5s
    http:
      valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
      valid_status_codes: []
      method: GET
      tls_config:
        insecure_skip_verify: false
      fail_if_ssl: false
      fail_if_not_ssl: true
```

---

## Automatisierung

### Certbot Auto-Renewal Hook

```bash
# /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#!/bin/bash
docker exec ablage-nginx nginx -s reload

# Benachrichtigung senden
curl -X POST $SLACK_WEBHOOK \
  -H "Content-Type: application/json" \
  -d '{"text": "✅ TLS-Zertifikat erfolgreich erneuert"}'
```

### Cronjob für Monitoring

```bash
# /etc/cron.daily/check-tls-expiry
#!/bin/bash
DAYS_LEFT=$(echo | openssl s_client -servername localhost -connect localhost:443 2>/dev/null | \
  openssl x509 -noout -enddate | cut -d= -f2 | xargs -I {} date -d {} +%s | \
  xargs -I {} bash -c 'echo $(( ({} - $(date +%s)) / 86400 ))')

if [ $DAYS_LEFT -lt 14 ]; then
    curl -X POST $SLACK_WEBHOOK \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"⚠️ TLS-Zertifikat läuft in $DAYS_LEFT Tagen ab\"}"
fi
```

---

## Verifikation

```bash
# Zertifikat nach Erneuerung prüfen
echo | openssl s_client -servername localhost -connect localhost:443 2>/dev/null | \
  openssl x509 -noout -dates

# Vollständige Kette prüfen
echo | openssl s_client -servername localhost -connect localhost:443 2>&1 | \
  openssl x509 -noout -text | head -20

# HTTPS-Verbindung testen
curl -v https://localhost/api/v1/health 2>&1 | grep -E "SSL|TLS|certificate"

# Browser-Test (Chrome DevTools)
# F12 -> Security Tab -> View Certificate
```

---

## Troubleshooting

### "Certificate not trusted"

```bash
# Intermediate-Zertifikate prüfen
openssl s_client -servername localhost -connect localhost:443 -showcerts

# CA-Bundle aktualisieren
update-ca-certificates --fresh
```

### "Certificate name mismatch"

```bash
# Subject Alternative Names prüfen
openssl x509 -in server.crt -noout -text | grep -A1 "Subject Alternative Name"

# Common Name prüfen
openssl x509 -in server.crt -noout -subject
```

### "Private key does not match"

```bash
# Modulus vergleichen (muss identisch sein)
openssl x509 -noout -modulus -in server.crt | md5sum
openssl rsa -noout -modulus -in server.key | md5sum
```

---

## Eskalation

| Ablaufzeit | Aktion |
|------------|--------|
| > 14 Tage | Routine-Erneuerung planen |
| 7-14 Tage | On-Call: Erneuerung einleiten |
| 1-7 Tage | Sofortige Erneuerung |
| < 24 Stunden | Eskalation an Security-Team |
| Abgelaufen | Notfall-Zertifikat, alle Stakeholder informieren |

---

## Verwandte Runbooks

- [Security Hardening](../Security/Security-Hardening-Complete.md)
- [Nginx Configuration Recovery](nginx-configuration-recovery.md)
- [Incident Response](incident-response.md)
