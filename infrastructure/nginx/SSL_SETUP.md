# SSL/TLS Setup Guide - Ablage-System OCR

Automated SSL/TLS certificate provisioning using Let's Encrypt and Certbot.

## 🚀 Quick Start

### For Production Domains

```bash
# Set environment variables
export DOMAIN="ablage-system.com"
export LETSENCRYPT_EMAIL="admin@ablage-system.com"

# Run SSL setup
./scripts/ssl-setup.sh init
```

### For Local Development

```bash
# Generate self-signed certificate for local domains
export DOMAIN="ablage-system.local"
./scripts/ssl-setup.sh init
```

## 📋 Prerequisites

1. **Domain Name**: Must own a public domain (e.g., `ablage-system.com`)
2. **DNS Configuration**: Domain must point to your server's IP
3. **Port Access**: Ports 80 and 443 must be accessible from the internet
4. **Nginx Running**: Nginx container must be running

## 🔧 Configuration

### Environment Variables

```bash
# Required
DOMAIN="your-domain.com"               # Your domain name
LETSENCRYPT_EMAIL="admin@domain.com"   # Email for Let's Encrypt notifications

# Optional
STAGING="false"                        # Use staging server for testing (true/false)
```

### Nginx Configuration

The SSL setup script works with the existing Nginx configuration in `infrastructure/nginx/conf.d/ablage-system.conf`.

SSL-specific settings:
- **Protocols**: TLS 1.2, TLS 1.3
- **Ciphers**: Strong ciphers only
- **HSTS**: Enabled with 1-year max-age
- **OCSP Stapling**: Enabled
- **Session Tickets**: Disabled

## 📜 Commands

### Initial Setup

```bash
# Standard certificate (main domain + www + subdomains)
./scripts/ssl-setup.sh init

# Wildcard certificate (*.domain.com)
./scripts/ssl-setup.sh wildcard
```

### Maintenance

```bash
# Test renewal (dry-run)
./scripts/ssl-setup.sh test

# Force renewal
./scripts/ssl-setup.sh renew

# Show certificate info
./scripts/ssl-setup.sh info

# Revoke certificate
./scripts/ssl-setup.sh revoke
```

## 🌐 Supported Domains

The default setup creates certificates for:
- `ablage-system.com`
- `www.ablage-system.com`
- `grafana.ablage-system.com`
- `prometheus.ablage-system.com`

To add more subdomains, edit `scripts/ssl-setup.sh` line:
```bash
DOMAINS="$DOMAINS -d your-subdomain.$DOMAIN"
```

## 🔄 Automatic Renewal

Certificates are automatically renewed 30 days before expiry.

### How It Works

1. **Certbot Container**: Runs renewal check every 12 hours
2. **Docker Compose**: Configured in `docker-compose.nginx.yml`
3. **Nginx Reload**: Automatic after successful renewal

### Manual Renewal

```bash
# Test renewal (no changes made)
./scripts/ssl-setup.sh test

# Force immediate renewal
./scripts/ssl-setup.sh renew
```

### Monitoring Renewal

```bash
# Check renewal logs
docker logs ablage-certbot

# Check certificate expiry
openssl x509 -in /etc/letsencrypt/live/ablage-system.com/fullchain.pem -noout -dates
```

## 🔐 Self-Signed Certificates (Local Development)

For local development with `.local` domains:

```bash
# Generates self-signed certificate
export DOMAIN="ablage-system.local"
./scripts/ssl-setup.sh init
```

**Features**:
- 4096-bit RSA key
- Valid for 365 days
- Includes SAN for subdomains
- No browser warnings (after trusting)

**Trust Certificate**:

**Firefox**:
1. Visit `https://ablage-system.local`
2. Click "Advanced" → "Accept Risk and Continue"

**Chrome/Edge**:
1. Visit `https://ablage-system.local`
2. Click "Advanced" → "Proceed to ablage-system.local (unsafe)"

**System-wide (Linux)**:
```bash
sudo cp infrastructure/nginx/certs/ablage-system.local.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

**System-wide (macOS)**:
```bash
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain infrastructure/nginx/certs/ablage-system.local.crt
```

## 🚨 Troubleshooting

### Certificate Request Failed

**Error**: "Challenge failed"

**Solutions**:
1. Verify domain DNS points to server
2. Check ports 80 and 443 are accessible
3. Ensure Nginx is running: `docker ps | grep nginx`
4. Check firewall rules
5. Use staging server for testing: `STAGING=true ./scripts/ssl-setup.sh init`

### Rate Limiting

Let's Encrypt has rate limits:
- **50 certificates per domain per week**
- **5 duplicate certificates per week**

**Solution**: Use staging server for testing:
```bash
STAGING=true ./scripts/ssl-setup.sh init
```

### Nginx Configuration Invalid

**Error**: "nginx: configuration file /etc/nginx/nginx.conf test failed"

**Solutions**:
1. Test config: `docker exec ablage-nginx nginx -t`
2. Check certificate paths in `conf.d/ablage-system.conf`
3. Verify certificates exist: `docker exec ablage-nginx ls -la /etc/letsencrypt/live/`

### Certificate Not Trusted

**Error**: "NET::ERR_CERT_AUTHORITY_INVALID"

**For Production**:
- Check certificate issuer: Should be "Let's Encrypt"
- Verify fullchain.pem includes intermediate certificate
- Check system time is correct

**For Self-Signed**:
- Add certificate to system trust store (see above)
- Or use `--insecure` flag with curl

## 📊 SSL Testing

### Online Tools

- **SSL Labs**: https://www.ssllabs.com/ssltest/analyze.html?d=your-domain.com
- **SecurityHeaders**: https://securityheaders.com/?q=your-domain.com
- **HardenizeSSL**: https://www.hardenize.com/

### Command Line

```bash
# Test SSL connection
openssl s_client -connect ablage-system.com:443 -servername ablage-system.com

# Check certificate
curl -vI https://ablage-system.com

# Test specific TLS version
openssl s_client -connect ablage-system.com:443 -tls1_3
```

## 🔍 Certificate Details

### Certificate Files

Located in `/etc/letsencrypt/live/your-domain.com/`:

- `privkey.pem`: Private key (KEEP SECRET!)
- `fullchain.pem`: Certificate + intermediate chain
- `cert.pem`: Certificate only
- `chain.pem`: Intermediate certificates only

### Backup Certificates

```bash
# Backup all certificates
docker run --rm -v certbot_conf:/etc/letsencrypt -v $(pwd):/backup alpine \
  tar czf /backup/letsencrypt-backup-$(date +%Y%m%d).tar.gz /etc/letsencrypt
```

### Restore Certificates

```bash
# Restore from backup
docker run --rm -v certbot_conf:/etc/letsencrypt -v $(pwd):/backup alpine \
  tar xzf /backup/letsencrypt-backup-20250124.tar.gz -C /
```

## 🌍 DNS Providers (for Wildcard Certificates)

Wildcard certificates (`*.domain.com`) require DNS validation.

**Supported Plugins**:
- Cloudflare: `--dns-cloudflare`
- AWS Route53: `--dns-route53`
- DigitalOcean: `--dns-digitalocean`
- Google Cloud DNS: `--dns-google`

**Setup**:
```bash
# Export API credentials
export CLOUDFLARE_API_TOKEN="your-api-token"

# Request wildcard cert
./scripts/ssl-setup.sh wildcard
```

## 📞 Support

For issues:
1. Check logs: `docker logs ablage-certbot`
2. Test Nginx config: `docker exec ablage-nginx nginx -t`
3. Verify DNS: `nslookup your-domain.com`
4. Check Let's Encrypt status: https://letsencrypt.status.io/

---

**Last Updated**: 2025-01-24
**Let's Encrypt Docs**: https://letsencrypt.org/docs/
**Certbot Docs**: https://eff-certbot.readthedocs.io/
