# Nginx Reverse Proxy Configuration - Ablage-System OCR

Production-grade Nginx reverse proxy with security hardening, rate limiting, and SSL/TLS support.

## 📋 Features

- **Security Hardening**: Security headers, rate limiting, HSTS
- **SSL/TLS**: TLS 1.2/1.3, strong ciphers, OCSP stapling
- **Rate Limiting**: Separate limits for API, uploads, and authentication
- **WebSocket Support**: Real-time communication
- **Compression**: Gzip compression for text assets
- **Caching**: Static asset caching with proper headers
- **Monitoring**: Health checks, detailed logging
- **Multi-Domain**: Main app + Grafana + Prometheus subdomains

## 🚀 Quick Start

### 1. Build and Start Nginx

```bash
cd infrastructure/nginx
docker-compose -f docker-compose.nginx.yml up -d
```

### 2. Verify Configuration

```bash
# Test nginx configuration
docker exec ablage-nginx nginx -t

# View logs
docker logs ablage-nginx

# Check health
curl http://localhost/health
```

### 3. Setup SSL/TLS (See SSL Setup section below)

```bash
# Initial certificate request
./ssl-setup.sh init ablage-system.local

# Or use the main SSL script
cd ../../
./scripts/ssl-setup.sh
```

## 📁 Directory Structure

```
infrastructure/nginx/
├── nginx.conf                    # Main Nginx configuration
├── conf.d/
│   └── ablage-system.conf        # Site-specific configuration
├── snippets/
│   ├── security-headers.conf     # Security headers
│   └── ssl.conf                  # SSL configuration
├── Dockerfile                    # Nginx container
├── docker-compose.nginx.yml      # Docker Compose for Nginx + Certbot
├── .htpasswd                     # Basic auth credentials (create manually)
└── README.md                     # This file
```

## ⚙️ Configuration

### Main Configuration (`nginx.conf`)

Key settings:
- **Worker processes**: Auto-detected based on CPU cores
- **Worker connections**: 4096 per worker
- **Client max body size**: 50MB (for document uploads)
- **SSL protocols**: TLS 1.2 and 1.3 only
- **Gzip compression**: Enabled for text files

### Site Configuration (`conf.d/ablage-system.conf`)

Includes:
- **HTTP to HTTPS redirect**: All traffic redirected to HTTPS
- **API reverse proxy**: Proxies to backend:8000
- **Rate limiting**:
  - API endpoints: 100 req/min
  - Upload endpoint: 10 req/min
  - Auth endpoints: 5 req/min
- **WebSocket support**: `/ws/` endpoint
- **Grafana**: grafana.ablage-system.local
- **Prometheus**: prometheus.ablage-system.local (with basic auth)

## 🔒 Security Features

### Security Headers

```nginx
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000
Content-Security-Policy: ...
Permissions-Policy: ...
```

### Rate Limiting

| Endpoint | Limit | Burst |
|----------|-------|-------|
| API endpoints | 100 req/min | 20 |
| Document upload | 10 req/min | 5 |
| Authentication | 5 req/min | 3 |

### SSL/TLS

- **Protocols**: TLS 1.2, TLS 1.3
- **Ciphers**: Strong ciphers only (ECDHE-ECDSA, ECDHE-RSA)
- **HSTS**: Enabled with 1-year max-age
- **OCSP Stapling**: Enabled
- **Session tickets**: Disabled (for forward secrecy)

## 🔐 Basic Authentication Setup (htpasswd)

Prometheus und andere Admin-Interfaces sind mit Basic Auth geschuetzt.
Die `.htpasswd`-Datei muss **vor dem Docker-Build** erstellt werden.

### Option 1: Interaktiv mit setup-nginx.sh (Empfohlen)

```bash
cd infrastructure/nginx
./setup-nginx.sh
# Folge den Prompts fuer Username und Passwort
```

### Option 2: Mit Docker (keine lokale Installation noetig)

```bash
# Einzelner Benutzer erstellen
docker run --rm httpd:alpine htpasswd -nb prometheus_user sicheres_passwort > infrastructure/nginx/.htpasswd

# Weiteren Benutzer hinzufuegen
docker run --rm httpd:alpine htpasswd -nb user2 passwort2 >> infrastructure/nginx/.htpasswd
```

### Option 3: Mit apache2-utils (Linux)

```bash
# Installation (Ubuntu/Debian)
apt-get install apache2-utils

# Datei erstellen mit erstem Benutzer
htpasswd -bc infrastructure/nginx/.htpasswd prometheus_admin sicheres_passwort

# Weiteren Benutzer hinzufuegen
htpasswd -b infrastructure/nginx/.htpasswd user2 passwort2
```

### Option 4: Manuell generieren

```bash
# Passwort-Hash mit Python generieren
python3 -c "import crypt; print('user:' + crypt.crypt('password', crypt.mksalt(crypt.METHOD_SHA512)))"
# Ausgabe in .htpasswd speichern
```

### Wichtig

- Die `.htpasswd`-Datei sollte NICHT ins Git-Repository committed werden!
- Fuer CI/CD: Generiere die Datei im Build-Prozess oder als Secret
- Falls keine `.htpasswd` existiert, erstellt der Docker-Build einen Platzhalter (UNSICHER!)

## 🔒 DH-Parameter (Diffie-Hellman)

Fuer Perfect Forward Secrecy werden DH-Parameter benoetigt.
Diese werden **automatisch beim Docker-Build generiert**.

### Standard (2048-bit, schneller Build)

```bash
docker build -t ablage-nginx infrastructure/nginx/
# Generiert 2048-bit DH-Parameter (~30 Sekunden)
```

### Produktion (4096-bit, empfohlen)

```bash
# Option 1: Via Build-Argument
docker build --build-arg DH_PARAM_BITS=4096 -t ablage-nginx infrastructure/nginx/
# Dauert ca. 5-10 Minuten

# Option 2: Vorab generieren (fuer CI/CD empfohlen)
openssl dhparam -out infrastructure/nginx/dhparam.pem 4096
# Dann in Dockerfile die Zeile RUN openssl dhparam... durch COPY ersetzen
```

### Mit setup-nginx.sh

```bash
cd infrastructure/nginx
./setup-nginx.sh
# Generiert DH-Parameter automatisch (4096-bit)
```

## 📊 Monitoring Subdomains

### Grafana

**URL**: https://grafana.ablage-system.local

Configuration in `conf.d/ablage-system.conf`:
- Reverse proxy to grafana:3000
- WebSocket support for Grafana Live
- SSL/TLS enabled

### Prometheus

**URL**: https://prometheus.ablage-system.local

Configuration:
- Reverse proxy to prometheus:9090
- Basic authentication required
- SSL/TLS enabled

## 🌐 Domain Configuration

### Hosts File (Development)

Add to `/etc/hosts`:

```
127.0.0.1 ablage-system.local
127.0.0.1 grafana.ablage-system.local
127.0.0.1 prometheus.ablage-system.local
```

### DNS Records (Production)

```dns
ablage-system.local.       A      YOUR_SERVER_IP
grafana.ablage-system.local.  A   YOUR_SERVER_IP
prometheus.ablage-system.local. A YOUR_SERVER_IP
```

## 📝 Logs

### Log Locations

```bash
# Access logs
docker exec ablage-nginx tail -f /var/log/nginx/ablage-system-access.log

# Error logs
docker exec ablage-nginx tail -f /var/log/nginx/ablage-system-error.log

# Grafana logs
docker exec ablage-nginx tail -f /var/log/nginx/grafana-access.log

# Prometheus logs
docker exec ablage-nginx tail -f /var/log/nginx/prometheus-access.log
```

### Log Format

**Main log format**:
```
$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent"
```

**Detailed log format**:
```
$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" rt=$request_time uct="$upstream_connect_time" uht="$upstream_header_time" urt="$upstream_response_time"
```

## 🔧 Maintenance

### Reload Configuration

```bash
# Test configuration
docker exec ablage-nginx nginx -t

# Reload without downtime
docker exec ablage-nginx nginx -s reload
```

### View Current Configuration

```bash
# View main config
docker exec ablage-nginx cat /etc/nginx/nginx.conf

# View site config
docker exec ablage-nginx cat /etc/nginx/conf.d/ablage-system.conf
```

### Update Configuration

1. Edit configuration files locally
2. Test configuration:
   ```bash
   docker exec ablage-nginx nginx -t
   ```
3. Reload if test passes:
   ```bash
   docker exec ablage-nginx nginx -s reload
   ```

### Check Upstream Status

```bash
# Check if backend is accessible
docker exec ablage-nginx curl -f http://backend:8000/health
```

## 🐛 Troubleshooting

### Nginx Won't Start

```bash
# Check logs
docker logs ablage-nginx

# Test configuration
docker exec ablage-nginx nginx -t

# Check port conflicts
netstat -tuln | grep -E ':80|:443'
```

### 502 Bad Gateway

```bash
# Check if backend is running
docker ps | grep backend

# Check backend health
curl http://localhost:8000/health

# Check nginx error logs
docker exec ablage-nginx tail -50 /var/log/nginx/error.log
```

### Rate Limiting Issues

```bash
# Check rate limit zones
docker exec ablage-nginx cat /etc/nginx/nginx.conf | grep limit_req_zone

# Temporarily disable rate limiting for testing:
# Comment out limit_req lines in conf.d/ablage-system.conf
```

### SSL Certificate Issues

```bash
# Check certificate validity
docker exec ablage-nginx openssl x509 -in /etc/letsencrypt/live/ablage-system.local/fullchain.pem -noout -dates

# Renew certificate manually
docker exec ablage-certbot certbot renew --dry-run

# Force renewal
docker exec ablage-certbot certbot renew --force-renewal
```

## 🎯 Performance Tuning

### Worker Processes

Default: `auto` (matches CPU cores)

Adjust in `nginx.conf` if needed:
```nginx
worker_processes 4;
```

### Worker Connections

Default: 4096

Increase for high-traffic:
```nginx
worker_connections 8192;
```

### Buffer Sizes

Adjust for large uploads in `nginx.conf`:
```nginx
client_body_buffer_size 256k;
client_max_body_size 100m;
```

### Cache Configuration

Static assets cached for 1 year:
```nginx
expires 1y;
add_header Cache-Control "public, immutable";
```

## 🔄 Integration with Main Stack

### Docker Compose Integration

Add to main `docker-compose.yml`:

```yaml
services:
  nginx:
    build: ./infrastructure/nginx
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
      - grafana
      - prometheus
    volumes:
      - ./frontend/dist:/var/www/ablage-system:ro
      - certbot_conf:/etc/letsencrypt
      - certbot_www:/var/www/certbot
```

### Environment Variables

```bash
# .env file
NGINX_PORT_HTTP=80
NGINX_PORT_HTTPS=443
DOMAIN=ablage-system.local
```

## 📚 References

- [Nginx Documentation](https://nginx.org/en/docs/)
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [Security Headers](https://securityheaders.com/)
- [Let's Encrypt](https://letsencrypt.org/)

## 🆘 Support

For issues or questions:
- Check logs: `docker logs ablage-nginx`
- Test config: `docker exec ablage-nginx nginx -t`
- Review [Nginx docs](https://nginx.org/en/docs/)
- Open issue on GitHub

---

**Last Updated**: 2025-01-24
**Maintainer**: Ablage-System Team
