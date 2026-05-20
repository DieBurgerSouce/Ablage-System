# Infrastructure Hardening - Ablage-System OCR

Dokumentation der Sicherheitsverbesserungen fuer die Infrastruktur-Komponenten.

## Uebersicht

| Komponente | Massnahme | Status |
|------------|-----------|--------|
| Vault | Certificate Rotation Script | Implementiert |
| Grafana | IP-Whitelisting | Implementiert |
| Prometheus | IP-Whitelisting + Basic Auth | Implementiert |

---

## 1. Vault Certificate Rotation

### Beschreibung

Automatische Rotation der TLS-Zertifikate fuer HashiCorp Vault zur Gewaehrleistung
der verschluesselten Kommunikation.

### Dateien

- Script: `infrastructure/vault/scripts/cert-rotation.sh`
- Zertifikate: `infrastructure/vault/config/certs/`
- Logs: `infrastructure/vault/logs/cert-rotation.log`

### Verwendung

```bash
# Zertifikatsstatus pruefen
./infrastructure/vault/scripts/cert-rotation.sh --check

# Automatische Rotation (fuer Cronjob)
./infrastructure/vault/scripts/cert-rotation.sh --auto

# Interaktive Rotation mit Bestaetigung
./infrastructure/vault/scripts/cert-rotation.sh --manual

# PKI-basierte Rotation (Vault Enterprise)
./infrastructure/vault/scripts/cert-rotation.sh --pki
```

### Cronjob einrichten

```bash
# Monatliche Zertifikats-Rotation am 1. um 02:00 Uhr
0 2 1 * * /opt/ablage-system/infrastructure/vault/scripts/cert-rotation.sh --auto

# Woechentliche Pruefung ohne Rotation
0 8 * * 1 /opt/ablage-system/infrastructure/vault/scripts/cert-rotation.sh --check
```

### Zertifikats-Backup

Backups werden automatisch erstellt in:
```
infrastructure/vault/config/certs/backup/
```

Die letzten 10 Backups werden aufbewahrt.

### Warnschwellen

| Schwelle | Tage bis Ablauf | Aktion |
|----------|-----------------|--------|
| OK | > 30 Tage | Keine Rotation |
| Warnung | 7-30 Tage | Rotation empfohlen |
| Kritisch | < 7 Tage | Rotation erforderlich |
| Abgelaufen | 0 Tage | Sofortige Rotation |

---

## 2. Grafana IP-Whitelisting

### Beschreibung

IP-basierte Zugriffskontrolle fuer das Grafana Monitoring Dashboard.
Nur autorisierte Netzwerke koennen auf das Dashboard zugreifen.

### Konfiguration

Datei: `infrastructure/nginx/conf.d/ablage-system.conf`

```nginx
# IP-Whitelisting fuer Monitoring-Dienste
# Lokale Entwicklung
allow 127.0.0.0/8;
# Docker-Netzwerke
allow 172.16.0.0/12;
allow 172.28.0.0/16;
# Interne Netzwerke
allow 10.0.0.0/8;
allow 192.168.0.0/16;
# Alle anderen blockieren
deny all;
```

### Erlaubte Netzwerke

| Netzwerk | Beschreibung |
|----------|--------------|
| 127.0.0.0/8 | Localhost |
| 172.16.0.0/12 | Docker Bridge Networks |
| 172.28.0.0/16 | Ablage-System Docker Networks |
| 10.0.0.0/8 | Klasse A privat |
| 192.168.0.0/16 | Klasse C privat |

### Anpassungen fuer Produktion

Fuer Produktionsumgebungen sollten die IP-Bereiche eingeschraenkt werden:

```nginx
# Beispiel: Nur spezifische Admin-IPs
allow 192.168.1.100;    # Admin Workstation 1
allow 192.168.1.101;    # Admin Workstation 2
allow 10.10.0.0/24;     # VPN-Netzwerk
deny all;
```

### Zugriff

- URL: `https://grafana.ablage-system.local`
- Lokaler Port (Development): `127.0.0.1:3002`

---

## 3. Prometheus IP-Whitelisting

### Beschreibung

Doppelte Sicherheitsebene fuer Prometheus:
1. IP-Whitelisting (Netzwerkebene)
2. Basic Authentication (Benutzerebene)

### Konfiguration

Datei: `infrastructure/nginx/conf.d/ablage-system.conf`

```nginx
# IP-Whitelisting
allow 127.0.0.0/8;
allow 172.16.0.0/12;
allow 172.28.0.0/16;
allow 10.0.0.0/8;
allow 192.168.0.0/16;
deny all;

# Basic Auth (zusaetzliche Sicherheitsebene)
auth_basic "Prometheus Access - Authorisierte Benutzer";
auth_basic_user_file /etc/nginx/.htpasswd;
```

### htpasswd einrichten

```bash
# Option 1: Interaktiv mit setup-nginx.sh
./infrastructure/nginx/setup-nginx.sh

# Option 2: Manuell mit Docker
docker run --rm httpd:alpine htpasswd -nb prometheus_admin secure_password > infrastructure/nginx/.htpasswd

# Option 3: Mit apache2-utils
htpasswd -bc infrastructure/nginx/.htpasswd prometheus_admin secure_password
```

### Endpoint-spezifische Regeln

| Endpoint | Zugriff | Beschreibung |
|----------|---------|--------------|
| `/` | IP + Basic Auth | Web UI |
| `/metrics` | Nur Docker-intern | Prometheus Self-Scraping |
| `/api/` | IP + Basic Auth + Rate Limit | Query API |

### Zugriff

- URL: `https://prometheus.ablage-system.local`
- Lokaler Port (Development): `127.0.0.1:9090`

---

## IP-Whitelist Snippet

Fuer wiederverwendbare IP-Whitelist-Konfiguration:

Datei: `infrastructure/nginx/snippets/ip-whitelist-monitoring.conf`

### Verwendung in Server Blocks

```nginx
# In server block einbinden
include /etc/nginx/snippets/ip-whitelist-monitoring.conf;

# Dann mit geo-Variable pruefen
if ($monitoring_access = 0) {
    return 403;
}
```

---

## Sicherheits-Checkliste

### Vor dem Produktivbetrieb

- [ ] IP-Bereiche auf tatsaechliche Admin-Netzwerke einschraenken
- [ ] htpasswd-Datei mit sicheren Passwoertern erstellen
- [ ] SSL-Zertifikate von Let's Encrypt oder interner CA
- [ ] Vault Certificate Rotation Cronjob einrichten
- [ ] Monitoring fuer Zertifikatsablauf konfigurieren
- [ ] Backup-Strategie fuer Zertifikate pruefen

### Regelmaessige Pruefungen

- [ ] Woechentlich: Zertifikatsstatus pruefen (`cert-rotation.sh --check`)
- [ ] Monatlich: Nginx Access Logs auf unberechtigte Zugriffe pruefen
- [ ] Quartalsweise: htpasswd-Passwoerter rotieren
- [ ] Jaehrlich: IP-Whitelist-Bereiche ueberpruefen

---

## Fehlerbehebung

### Problem: Zugriff auf Grafana/Prometheus verweigert

1. Client-IP pruefen:
   ```bash
   curl ifconfig.me
   ```

2. Nginx Access Log pruefen:
   ```bash
   docker logs ablage-nginx | grep "403"
   ```

3. IP zur Whitelist hinzufuegen (falls berechtigt)

### Problem: Zertifikats-Rotation fehlgeschlagen

1. Logs pruefen:
   ```bash
   cat infrastructure/vault/logs/cert-rotation.log
   ```

2. Manuell pruefen:
   ```bash
   ./infrastructure/vault/scripts/cert-rotation.sh --check
   ```

3. Backup wiederherstellen:
   ```bash
   cp infrastructure/vault/config/certs/backup/TIMESTAMP/* infrastructure/vault/config/certs/
   docker restart ablage-vault
   ```

### Problem: Basic Auth funktioniert nicht

1. htpasswd-Datei pruefen:
   ```bash
   cat infrastructure/nginx/.htpasswd
   ```

2. Nginx Konfiguration testen:
   ```bash
   docker exec ablage-nginx nginx -t
   ```

3. htpasswd neu erstellen (siehe oben)

---

## Prometheus Alert Regeln

Fuer Zertifikats-Monitoring in `infrastructure/prometheus/rules/` hinzufuegen:

```yaml
# Datei: cert-alerts.yml
groups:
  - name: certificate_alerts
    rules:
      - alert: VaultCertificateExpiringSoon
        expr: (probe_ssl_earliest_cert_expiry{job="vault"} - time()) / 86400 < 30
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Vault Zertifikat laeuft bald ab"
          description: "Vault Zertifikat laeuft in {{ $value | printf \"%.0f\" }} Tagen ab"

      - alert: VaultCertificateCritical
        expr: (probe_ssl_earliest_cert_expiry{job="vault"} - time()) / 86400 < 7
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "Vault Zertifikat kritisch"
          description: "Vault Zertifikat laeuft in {{ $value | printf \"%.0f\" }} Tagen ab - sofortige Rotation erforderlich"
```

---

## Weitere Dokumentation

- Vault Setup: `infrastructure/vault/README.md`
- Nginx Setup: `infrastructure/nginx/README.md`
- SSL Setup: `infrastructure/nginx/SSL_SETUP.md`
- Monitoring: `infrastructure/grafana/README.md`

---

**Erstellt**: 2025-01-02
**Version**: 1.0
**Maintainer**: Ablage-System Team
