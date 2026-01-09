# Brute Force Attack Response Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High Security)
> RTO: 10 Minuten | RPO: N/A

## Alert

```
PossibleBruteForceAttack - > 10 fehlgeschlagene Logins in 2 Minuten
AuthenticationFailureSpike - Ungewöhnlich viele Auth-Fehler
SuspiciousLoginPattern - Login-Versuche von unbekannten IPs
```

## Symptome

- Viele "401 Unauthorized" in den Logs
- Fehlgeschlagene Login-Versuche für bekannte Benutzer
- Ungewöhnliche geografische Login-Muster
- Account-Lockouts häufen sich

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Angriffsmuster identifizieren

```bash
# Fehlgeschlagene Logins (letzte 10 Minuten)
docker logs ablage-backend --since 10m 2>&1 | \
  grep -E "login.*failed|401|authentication" | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -20
```

### 2. Angreifer-IPs identifizieren

```bash
# IPs mit häufigen Auth-Fehlern
docker logs ablage-nginx --since 10m 2>&1 | \
  grep -E "POST.*/(auth|login)" | \
  grep " 401 " | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -10
```

### 3. Betroffene Accounts prüfen

```bash
# Accounts mit vielen fehlgeschlagenen Versuchen
docker exec ablage-backend python -c "
from app.services.auth_service import AuthService
from datetime import datetime, timedelta

svc = AuthService()
failed = svc.get_failed_login_attempts(
    since=datetime.utcnow() - timedelta(minutes=10)
)
for email, count in sorted(failed.items(), key=lambda x: -x[1])[:10]:
    print(f'{email}: {count} Fehlversuche')
"
```

---

## Gegenmaßnahmen

### Option A: IP-Block via Nginx

```bash
# IP-Adresse blockieren
echo "deny 192.168.1.100;" >> /tmp/blocked_ips.conf

# In Nginx-Container einfügen
docker cp /tmp/blocked_ips.conf ablage-nginx:/etc/nginx/conf.d/blocked.conf
docker exec ablage-nginx nginx -s reload

# Oder via API
curl -X POST http://localhost:8000/api/v1/admin/security/block-ip \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"ip": "192.168.1.100", "reason": "Brute force attack", "duration_hours": 24}'
```

### Option B: Rate Limiting verschärfen

```bash
# Temporäres Rate Limiting für Auth-Endpunkte
curl -X POST http://localhost:8000/api/v1/admin/rate-limits \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "endpoint": "/api/v1/auth/login",
    "requests_per_minute": 3,
    "block_duration_minutes": 15
  }'
```

### Option C: Accounts temporär sperren

```bash
# Betroffene Accounts sperren
docker exec ablage-backend python -c "
from app.services.user_service import UserService
from datetime import datetime, timedelta

svc = UserService()
# Accounts mit > 5 Fehlversuchen sperren
affected = svc.lock_accounts_with_failed_attempts(
    threshold=5,
    lock_duration=timedelta(hours=1)
)
print(f'{len(affected)} Accounts temporär gesperrt')
"
```

### Option D: CAPTCHA aktivieren

```bash
# CAPTCHA für Auth-Endpunkte aktivieren
curl -X POST http://localhost:8000/api/v1/admin/security/captcha \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true, "threshold_failed_attempts": 3}'
```

---

## Erweiterte Analyse

### 4. Geografische Analyse

```bash
# Login-Versuche nach Land/Region
docker exec ablage-backend python -c "
from app.services.security_analytics_service import SecurityAnalyticsService

svc = SecurityAnalyticsService()
geo_stats = svc.get_login_attempts_by_country(hours=1)
for country, count in sorted(geo_stats.items(), key=lambda x: -x[1])[:10]:
    print(f'{country}: {count}')
"
```

### 5. User-Agent-Analyse

```bash
# Verdächtige User-Agents
docker logs ablage-nginx --since 1h 2>&1 | \
  grep -E "POST.*/(auth|login)" | \
  awk -F'"' '{print $6}' | sort | uniq -c | sort -rn | head -10
```

### 6. Timing-Analyse

```bash
# Login-Versuche pro Minute
docker logs ablage-backend --since 1h 2>&1 | \
  grep "login" | \
  awk '{print substr($1,1,16)}' | uniq -c
```

---

## Account-Recovery

### Gesperrte Accounts entsperren

```bash
# Einzelnen Account entsperren
curl -X POST http://localhost:8000/api/v1/admin/users/{user_id}/unlock \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Alle gesperrten Accounts nach 1 Stunde entsperren
docker exec ablage-backend python -c "
from app.services.user_service import UserService
UserService().unlock_expired_lockouts()
"
```

### Passwort-Reset erzwingen

```bash
# Passwort-Reset für betroffene Accounts
curl -X POST http://localhost:8000/api/v1/admin/users/force-password-reset \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"emails": ["user1@example.de", "user2@example.de"]}'
```

---

## Langfristige Maßnahmen

### 1. Fail2Ban konfigurieren

```bash
# Fail2Ban für SSH und API
cat > /etc/fail2ban/jail.d/ablage.conf << 'EOF'
[ablage-auth]
enabled = true
port = 80,443,8000
filter = ablage-auth
logpath = /var/log/ablage/auth.log
maxretry = 5
bantime = 3600
findtime = 300
EOF
```

### 2. 2FA aktivieren

```bash
# 2FA für Admin-Accounts erzwingen
curl -X POST http://localhost:8000/api/v1/admin/security/2fa/enforce \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"roles": ["admin", "superuser"]}'
```

### 3. Login-Anomalie-Detection

```bash
# ML-basierte Anomalie-Detection aktivieren
curl -X POST http://localhost:8000/api/v1/admin/security/anomaly-detection \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true, "sensitivity": "high"}'
```

---

## Verifikation

```bash
# Blockierte IPs prüfen
curl -s http://localhost:8000/api/v1/admin/security/blocked-ips \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq

# Aktive Lockouts
curl -s http://localhost:8000/api/v1/admin/users?locked=true \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.total'

# Auth-Fehlerrate (sollte sinken)
watch -n 30 'curl -s http://localhost:8000/api/v1/metrics | grep auth_failures_total'
```

---

## Incident-Dokumentation

### Log-Export für Forensik

```bash
# Auth-Logs sichern
docker logs ablage-backend --since 24h 2>&1 | \
  grep -E "auth|login|password" > \
  /tmp/auth_incident_$(date +%Y%m%d_%H%M%S).log

# Nginx Access Logs
docker logs ablage-nginx --since 24h > \
  /tmp/nginx_incident_$(date +%Y%m%d_%H%M%S).log
```

### Incident-Report Template

```markdown
## Brute Force Incident Report

**Datum/Zeit**: $(date)
**Dauer**: X Minuten
**Betroffene Accounts**: X

### Angreifer-Informationen
- IP-Adressen: X.X.X.X, Y.Y.Y.Y
- Geografische Herkunft: Land
- User-Agents: ...

### Gegenmaßnahmen
1. IP-Block: Ja/Nein
2. Account-Lockouts: X Accounts
3. Rate Limiting: Aktiviert

### Auswirkungen
- Gesperrte legitime Benutzer: X
- Kompromittierte Accounts: 0

### Nachfolgeaktionen
- [ ] Passwort-Reset für betroffene Accounts
- [ ] 2FA-Aktivierung prüfen
- [ ] Firewall-Regeln aktualisieren
```

---

## Eskalation

| Schweregrad | Aktion |
|-------------|--------|
| < 50 Versuche | On-Call: IP-Block |
| 50-200 Versuche | Security-Team informieren |
| 200+ Versuche | Eskalation an CISO |
| Erfolgreicher Einbruch | Incident Response Team |

---

## Verwandte Runbooks

- [Incident Response](incident-response.md)
- [DDoS Attack Mitigation](ddos-attack-mitigation.md)
- [API Error Rate Spike](api-error-rate-spike.md)
