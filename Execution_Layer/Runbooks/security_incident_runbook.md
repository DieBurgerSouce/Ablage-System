# Security Incident Response Runbook
**Ablage-System - Sicherheitsvorf all-Reaktion**

Version: 1.0
Last Updated: 2025-01-23
Owner: Security Team
Classification: CONFIDENTIAL
Severity: CRITICAL

---

## ⚠️ EMERGENCY CONTACTS

| Role | Name | Contact | Availability |
|------|------|---------|--------------|
| Security Lead | [TBD] | security@company.com | 24/7 |
| DPO (Data Protection Officer) | [TBD] | dpo@company.com | Business hours + on-call |
| CTO | [TBD] | cto@company.com | 24/7 |
| Legal Counsel | [TBD] | legal@company.com | Business hours |
| External IR Firm | [TBD] | [TBD] | 24/7 (retainer) |

**Emergency Hotline:** +49 [TBD]

---

## Quick Reference

| Incident Type | Severity | Initial Response Time | Page |
|---------------|----------|-----------------------|------|
| Unauthorized access | CRITICAL | <15 min | [§1](#1-unauthorized-access-detection) |
| Data breach | CRITICAL | <15 min | [§2](#2-data-breach-response) |
| Ransomware | CRITICAL | <5 min | [§3](#3-ransomware-attack) |
| DDoS attack | HIGH | <30 min | [§4](#4-ddos-attack) |
| SQL injection | HIGH | <30 min | [§5](#5-injection-attacks) |
| Brute force | MEDIUM | <1 hour | [§6](#6-brute-force-attacks) |
| Suspicious activity | LOW | <4 hours | [§7](#7-suspicious-activity) |

---

## General Incident Response Process

### Phase 1: Detection & Assessment (0-15 minutes)
1. **Identify:** What is happening?
2. **Classify:** Severity level (Critical/High/Medium/Low)
3. **Contain:** Immediate actions to limit damage
4. **Notify:** Alert appropriate personnel

### Phase 2: Containment (15-60 minutes)
1. **Isolate:** Affected systems
2. **Preserve:** Evidence for investigation
3. **Assess:** Scope and impact
4. **Communicate:** Stakeholders

### Phase 3: Eradication (1-24 hours)
1. **Identify:** Root cause
2. **Remove:** Threat from environment
3. **Patch:** Vulnerabilities
4. **Verify:** Clean system state

### Phase 4: Recovery (1-7 days)
1. **Restore:** Systems from clean backups
2. **Monitor:** For recurrence
3. **Test:** Full functionality
4. **Resume:** Normal operations

### Phase 5: Post-Incident (1-4 weeks)
1. **Document:** Full incident report
2. **Review:** Response effectiveness
3. **Improve:** Security controls
4. **Train:** Team on lessons learned

---

## 1. Unauthorized Access Detection

### Symptoms
- Unfamiliar login from unusual location/IP
- Access to admin panel from non-admin account
- API requests with elevated privileges
- Database queries from unknown source

### Immediate Response (0-5 minutes)

**Step 1: Verify Legitimacy**
```bash
# Check recent logins
docker-compose logs backend | grep 'login.*success' | tail -50

# Identify suspicious login
# Look for:
# - Unfamiliar IP addresses
# - Unusual times (2-5 AM)
# - Failed attempts followed by success (credential stuffing)
# - Multiple accounts from same IP
```

**Step 2: If Confirmed Unauthorized - LOCK ACCOUNT**
```bash
# Disable user account immediately
docker exec ablage-backend python -c "
from app.services.user_service import UserService
service = UserService()
service.disable_user('SUSPICIOUS_USER_ID', reason='Security incident')
"

# Revoke all active sessions
docker exec ablage-redis redis-cli --scan --pattern 'session:SUSPICIOUS_USER_ID:*' | \
  xargs docker exec ablage-redis redis-cli DEL
```

**Step 3: Block IP Address**
```bash
# Add to firewall blacklist
sudo ufw deny from SUSPICIOUS_IP to any
sudo ufw reload

# Or via fail2ban
sudo fail2ban-client set sshd banip SUSPICIOUS_IP
```

**⏱️ Time to Execute:** <5 minutes
**🔒 Impact:** Suspected account locked, IP blocked

---

### Investigation (5-30 minutes)

**Analyze Attack Vector:**
```sql
-- Check authentication logs
SELECT
  timestamp,
  user_id,
  ip_address,
  user_agent,
  success,
  failure_reason
FROM auth_logs
WHERE user_id = 'SUSPICIOUS_USER_ID'
  OR ip_address = 'SUSPICIOUS_IP'
ORDER BY timestamp DESC
LIMIT 100;

-- Look for patterns:
-- 1. Credential stuffing: Many failures, then success
-- 2. Session hijacking: Valid session, different IP
-- 3. Privilege escalation: Normal user accessing admin endpoints
```

**Check What Was Accessed:**
```sql
-- Review API access logs
SELECT
  timestamp,
  endpoint,
  method,
  status_code,
  response_time_ms
FROM api_logs
WHERE user_id = 'SUSPICIOUS_USER_ID'
  AND timestamp > 'BREACH_START_TIME'
ORDER BY timestamp;

-- Identify sensitive endpoints:
-- /api/v1/admin/*
-- /api/v1/users/*/documents
-- /api/v1/documents/*/download
```

**Assess Data Exposure:**
```sql
-- Check document access
SELECT
  d.id,
  d.filename,
  d.owner_id,
  d.contains_pii,
  da.accessed_at,
  da.action
FROM documents d
JOIN document_access_log da ON d.id = da.document_id
WHERE da.user_id = 'SUSPICIOUS_USER_ID'
  AND da.accessed_at > 'BREACH_START_TIME';

-- Count sensitive documents accessed
SELECT COUNT(*) as sensitive_docs_accessed
FROM documents d
JOIN document_access_log da ON d.id = da.document_id
WHERE da.user_id = 'SUSPICIOUS_USER_ID'
  AND d.contains_pii = true;
```

---

### Containment Actions

**Reset Credentials:**
```bash
# Force password reset for affected user
docker exec ablage-backend python -c "
from app.services.user_service import UserService
service = UserService()
service.force_password_reset('AFFECTED_USER_ID')
"

# Revoke all API keys
docker exec ablage-backend python -c "
from app.services.api_key_service import APIKeyService
service = APIKeyService()
service.revoke_all_keys('AFFECTED_USER_ID', reason='Security incident')
"
```

**Enable Enhanced Monitoring:**
```bash
# Increase auth logging verbosity
docker exec ablage-backend sed -i 's/LOG_LEVEL=INFO/LOG_LEVEL=DEBUG/' /app/.env
docker-compose restart backend

# Enable audit logging for affected user (if they're re-enabled)
```

---

### GDPR Compliance (if PII accessed)

**Notification Requirements (GDPR Art. 33-34):**
- **To Authority (Art. 33):** Within 72 hours if "likely to result in risk"
- **To Data Subject (Art. 34):** Without undue delay if "high risk"

**Assessment Checklist:**
```markdown
- [ ] Was personal data accessed? (Yes/No)
- [ ] Type of data: (Basic/Special categories/Criminal convictions)
- [ ] Number of data subjects affected: ____
- [ ] Risk level: (Low/Medium/High)
- [ ] Likelihood of harm: (Unlikely/Possible/Likely)
- [ ] Measures to mitigate: _________________
- [ ] Need to notify authority? (Yes/No)
- [ ] Need to notify data subjects? (Yes/No)
```

**If Notification Required:**
```bash
# Generate breach report
docker exec ablage-backend python /opt/ablage/scripts/generate_breach_report.py \
  --incident-id INCIDENT_001 \
  --start-time "2025-01-23 02:15:00" \
  --end-time "2025-01-23 02:45:00" \
  --affected-users SUSPICIOUS_USER_ID \
  --output /var/log/ablage/breach_report_INCIDENT_001.pdf

# Send to DPO for review
```

**⏱️ Notification Deadline:** 72 hours from discovery

---

## 2. Data Breach Response

### Symptoms
- Data exfiltration detected (large downloads)
- Unauthorized database export
- Documents downloaded in bulk
- Sensitive data appears in unexpected location

### CRITICAL: Immediate Actions (0-10 minutes)

**Step 1: STOP THE BLEEDING**
```bash
# Disconnect affected service from internet
docker network disconnect ablage_network ablage-backend

# Or block all egress traffic
sudo iptables -A OUTPUT -j DROP
sudo iptables -A OUTPUT -d 127.0.0.1 -j ACCEPT  # Keep localhost
```

**Step 2: Preserve Evidence**
```bash
# Create forensic snapshot
timestamp=$(date +%Y%m%d_%H%M%S)

# Snapshot logs (CRITICAL - do this first)
docker-compose logs > /mnt/forensics/incident_logs_${timestamp}.txt

# Snapshot database
docker exec ablage-postgres pg_dump -U postgres ablage > \
  /mnt/forensics/db_snapshot_${timestamp}.sql

# Snapshot MinIO data listing
docker exec ablage-minio mc ls --recursive local/documents/ > \
  /mnt/forensics/minio_listing_${timestamp}.txt

# Copy entire Docker volumes (in background)
sudo rsync -a /var/lib/docker/volumes/ /mnt/forensics/volumes_${timestamp}/ &
```

**Step 3: Notify Leadership (IMMEDIATELY)**
```bash
# Send emergency alert
/opt/ablage/scripts/send_security_alert.sh \
  --severity CRITICAL \
  --type "Data Breach" \
  --message "Unauthorized data access detected. System isolated." \
  --recipients "security@company.com,cto@company.com,dpo@company.com"
```

**⏱️ Time to Execute:** <10 minutes
**🔒 Impact:** System offline, evidence preserved

---

### Investigation (10-60 minutes)

**Identify Exfiltration Method:**
```sql
-- Large downloads
SELECT
  user_id,
  document_id,
  action,
  timestamp,
  file_size_mb
FROM document_access_log
WHERE action = 'download'
  AND timestamp > NOW() - INTERVAL '24 hours'
  AND file_size_mb > 10
ORDER BY timestamp DESC;

-- Bulk API requests
SELECT
  user_id,
  endpoint,
  COUNT(*) as request_count,
  SUM(response_size_bytes) as total_bytes
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY user_id, endpoint
HAVING COUNT(*) > 100
ORDER BY total_bytes DESC;
```

**Determine Scope:**
```sql
-- Total data accessed by attacker
SELECT
  COUNT(DISTINCT document_id) as documents_accessed,
  SUM(file_size_mb) as total_mb_accessed,
  COUNT(DISTINCT owner_id) as users_affected,
  MIN(timestamp) as first_access,
  MAX(timestamp) as last_access
FROM document_access_log
WHERE user_id = 'ATTACKER_ID';

-- Breakdown by data sensitivity
SELECT
  d.sensitivity_level,
  COUNT(*) as count,
  SUM(d.file_size_mb) as total_mb
FROM documents d
JOIN document_access_log dal ON d.id = dal.document_id
WHERE dal.user_id = 'ATTACKER_ID'
GROUP BY d.sensitivity_level;
```

---

### GDPR Data Breach Notification

**⚠️ MANDATORY if high risk to data subjects**

**Notification Template (Art. 33):**
```markdown
# Data Breach Notification to Supervisory Authority

## Incident Details
- **Date/Time of Breach:** 2025-01-23, 02:15 UTC
- **Date/Time of Discovery:** 2025-01-23, 02:45 UTC
- **Nature of Breach:** Unauthorized access and data exfiltration

## Categories of Data Subjects
- **Number Affected:** [X] individuals
- **Categories:** Customers, employees, business partners

## Categories of Personal Data
- [X] Name, email, contact information
- [X] Identification documents (scanned invoices, contracts)
- [ ] Special categories (health, biometric, etc.)
- [ ] Criminal convictions data

## Likely Consequences
- Potential identity theft
- Unauthorized disclosure of business information
- Reputational damage

## Measures Taken or Proposed
- Immediate system isolation (02:45 UTC)
- Affected accounts disabled (02:50 UTC)
- Forensic investigation initiated (03:00 UTC)
- Enhanced monitoring deployed (03:15 UTC)
- Affected users to be notified (within 72h)

## DPO Contact
- Name: [DPO Name]
- Email: dpo@company.com
- Phone: +49 [TBD]

Submitted by: [Security Team]
Date: 2025-01-23
```

**Submit to:**
- **Germany:** Bundesbeauftragter für den Datenschutz und die Informationsfreiheit (BfDI)
- **Portal:** https://www.bfdi.bund.de/DE/Service/Meldungen/Datenpannen/Datenpannen_node.html

---

### Data Subject Notification (Art. 34)

**When Required:** High risk to rights and freedoms

**Notification Template:**
```markdown
Betreff: Wichtige Sicherheitsbenachrichtigung - Datenschutzvorfall

Sehr geehrte/r [Name],

wir informieren Sie über einen Sicherheitsvorfall, der möglicherweise Ihre
personenbezogenen Daten betrifft.

**Was ist passiert?**
Am 23. Januar 2025 haben wir unbefugten Zugriff auf unser System festgestellt.
Der Angreifer konnte auf [X] Dokumente zugreifen.

**Welche Daten sind betroffen?**
- Name und E-Mail-Adresse
- Hochgeladene Dokumente vom [Zeitraum]
- [Weitere betroffene Daten]

**Was haben wir unternommen?**
- Sofortige Isolation des betroffenen Systems
- Sperrung der Angreifer-Zugänge
- Benachrichtigung der Datenschutzbehörde
- Verstärkung der Sicherheitsmaßnahmen

**Was sollten Sie tun?**
1. Ändern Sie Ihr Passwort (erzwungen bei nächstem Login)
2. Aktivieren Sie Zwei-Faktor-Authentifizierung
3. Überprüfen Sie Ihre Kontoaktivitäten
4. Seien Sie wachsam bei verdächtigen E-Mails

**Weitere Informationen:**
Kontakt: security@company.com
Telefon: +49 [TBD]

Mit freundlichen Grüßen,
[Company Name]
Datenschutzteam
```

---

## 3. Ransomware Attack

### Symptoms
- Files encrypted with unusual extensions (.encrypted, .locked)
- Ransom note (README.txt) appears
- Cannot access documents in MinIO
- System performance degradation

### ⚠️ CRITICAL: DO NOT PAY RANSOM ⚠️

### Immediate Response (0-5 minutes)

**Step 1: ISOLATE IMMEDIATELY**
```bash
# Disconnect ALL systems from network
docker network disconnect ablage_network ablage-backend
docker network disconnect ablage_network ablage-worker
docker network disconnect ablage_network ablage-postgres
docker network disconnect ablage_network ablage-minio

# Shutdown affected containers
docker-compose stop
```

**Step 2: Identify Ransomware Variant**
```bash
# Check ransom note
cat /var/lib/docker/volumes/ablage_minio/_data/README.txt

# Check file extensions
find /var/lib/docker/volumes/ablage_minio/_data/ -name "*.encrypted" -o -name "*.locked" | head -20

# Search online: https://www.nomoreransom.org/en/decryption-tools.html
```

**Step 3: Assess Damage**
```bash
# Count encrypted files
find /var/lib/docker/volumes/ablage_minio/_data/ -name "*.encrypted" | wc -l

# Check if database encrypted
docker exec ablage-postgres psql -U postgres -l

# Check if backups accessible
ls -lh /mnt/backups/ | tail -10
```

**⏱️ Time to Execute:** <5 minutes
**🔒 Impact:** Complete system shutdown

---

### Recovery (1-48 hours)

**Option 1: Restore from Backup (PREFERRED)**
```bash
# Verify backup integrity
tar -tzf /mnt/backups/ablage_backup_latest.tar.gz | head -20

# Restore database
docker exec ablage-postgres pg_restore -U postgres -d ablage \
  /mnt/backups/postgres_backup_latest.dump

# Restore MinIO data
docker exec ablage-minio mc mirror /mnt/backups/minio_latest/ local/documents/

# Verify restoration
docker exec ablage-backend python /opt/ablage/scripts/verify_restore.py
```

**Option 2: Decryption Tool (if available)**
```bash
# Download decryption tool from https://www.nomoreransom.org
wget https://www.nomoreransom.org/tools/[VARIANT]_decryptor.exe

# Run decryption (example)
wine [VARIANT]_decryptor.exe /var/lib/docker/volumes/ablage_minio/_data/

# Verify decryption
md5sum /var/lib/docker/volumes/ablage_minio/_data/test_file.pdf
```

**Option 3: Contact Law Enforcement & Specialists**
- **Germany:** Bundeskriminalamt (BKA) Cybercrime Unit
- **Phone:** +49 611 55-0
- **Email:** cybercrime@bka.bund.de

---

### Prevention Measures

**Post-Incident Hardening:**
```bash
# Implement strict file upload validation
docker exec ablage-backend vi /app/api/v1/documents.py
# Add: file type whitelist, size limits, virus scanning

# Deploy endpoint protection
sudo apt install clamav clamav-daemon
sudo systemctl start clamav-daemon

# Scan on upload
clamscan --infected --remove /tmp/upload/*

# Immutable backups (cannot be encrypted)
aws s3api put-object-lock-configuration --bucket ablage-backups \
  --object-lock-configuration 'ObjectLockEnabled=Enabled,Rule={DefaultRetention={Mode=COMPLIANCE,Days=30}}'
```

---

## 4. DDoS Attack

### Symptoms
- API response times >5 seconds
- Connection timeouts
- CPU at 100% (handling requests)
- Thousands of requests from same IPs

### Immediate Response (0-10 minutes)

**Step 1: Confirm DDoS**
```bash
# Check request rate
docker-compose logs backend | grep "POST\|GET" | awk '{print $1}' | uniq -c | sort -rn | head -20

# Identify attacking IPs
docker-compose logs backend | awk '{print $NF}' | sort | uniq -c | sort -rn | head -50

# Typical pattern: 100+ requests/second from few IPs
```

**Step 2: Rate Limiting (Immediate)**
```bash
# Enable aggressive rate limiting
docker exec ablage-backend python -c "
from app.core.config import settings
settings.RATE_LIMIT_PER_MINUTE = 10  # Reduce from 100
settings.RATE_LIMIT_BURST = 5
" && docker-compose restart backend

# Block top offending IPs
for ip in $(docker-compose logs backend | awk '{print $NF}' | sort | uniq -c | sort -rn | head -10 | awk '{print $2}'); do
  sudo ufw deny from $ip
done
```

**Step 3: Enable CloudFlare (if available)**
```bash
# Point DNS to CloudFlare
# Enable "Under Attack Mode" in CF dashboard
# This adds JavaScript challenge to all visitors
```

**⏱️ Time to Execute:** <10 minutes
**🔒 Impact:** Legitimate users may experience delays

---

### Investigation

**Attack Characteristics:**
```bash
# Request distribution
docker-compose logs backend | awk '{print $5}' | sort | uniq -c | sort -rn

# Geographic distribution (if using GeoIP)
docker exec ablage-backend python /opt/ablage/scripts/analyze_attack_geoip.py

# Attack type:
# - HTTP Flood: High request rate, random URLs
# - Slowloris: Many slow connections
# - Amplification: Small requests, large responses
```

---

## 5. Injection Attacks

### Symptoms
- SQL errors in logs
- Unexpected database queries
- XSS payloads in input fields
- Command execution attempts

### SQL Injection Response

**Detection:**
```sql
-- Check for suspicious queries in logs
SELECT query FROM pg_stat_statements
WHERE query LIKE '%UNION SELECT%'
   OR query LIKE '%1=1%'
   OR query LIKE '%SLEEP(%'
   OR query LIKE '%information_schema%'
ORDER BY calls DESC;
```

**Immediate Fix:**
```bash
# Ensure parameterized queries everywhere
docker exec ablage-backend python /opt/ablage/scripts/audit_sql_queries.py

# Add WAF rule
sudo vi /etc/nginx/waf_rules.conf
# Add: block SQL injection patterns
```

---

## 6. Brute Force Attacks

### Symptoms
- High rate of authentication failures
- Dictionary attack patterns
- Credential stuffing (leaked passwords)

### Response

**Enable Account Lockout:**
```python
# Update app/services/auth_service.py
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

async def check_lockout(user_id: str) -> bool:
    """Check if account locked due to failed attempts."""
    attempts = await redis.get(f"failed_auth:{user_id}")
    return int(attempts or 0) >= MAX_FAILED_ATTEMPTS
```

**Deploy Fail2Ban:**
```bash
# Install fail2ban
sudo apt install fail2ban

# Configure for Docker logs
sudo vi /etc/fail2ban/jail.local
# [ablage-auth]
# enabled = true
# filter = ablage-auth
# logpath = /var/lib/docker/containers/*/*.log
# maxretry = 5
# bantime = 3600

sudo systemctl restart fail2ban
```

---

## 7. Suspicious Activity

### Investigation Procedure

**Collect Evidence:**
```bash
# Full log export
/opt/ablage/scripts/export_logs.sh --start "2025-01-23 00:00" --end "2025-01-23 23:59"

# User activity timeline
docker exec ablage-backend python /opt/ablage/scripts/user_activity_report.py \
  --user SUSPICIOUS_USER_ID --output /tmp/activity_report.pdf
```

---

## Post-Incident Report Template

```markdown
# Security Incident Report

**Incident ID:** SEC-2025-001
**Date:** 2025-01-23
**Severity:** Critical
**Status:** Resolved

## Executive Summary
Brief description of incident and impact.

## Timeline
- 02:15 UTC: Attack began
- 02:45 UTC: Detected by monitoring
- 02:50 UTC: Containment actions initiated
- 03:30 UTC: Threat neutralized
- 05:00 UTC: Systems restored

## Attack Vector
How the attacker gained access.

## Impact Assessment
- Data accessed: [X] documents
- Users affected: [Y]
- Downtime: 2.5 hours
- Financial impact: €[Z]

## Root Cause
Why this happened.

## Remediation
- Immediate fixes applied
- Long-term improvements planned

## Lessons Learned
- What worked well
- What needs improvement

## Recommendations
1. Implement MFA (2-4 weeks)
2. Deploy SIEM (1-3 months)
3. Security awareness training (ongoing)

**Prepared by:** Security Team
**Reviewed by:** CTO, DPO
**Date:** 2025-01-30
```

---

## Related Documents
- [GDPR Compliance Checker](../../Dynamic_Knowledge/Compliance/gdpr_compliance_implementation.md)
- [Security Architecture](../../Static_Knowledge/Technical_Details/security_architecture.md)
- [Incident Response Playbook](../incident_response_playbook.md)
- [Daily Operations Checklist](daily_operations_checklist.md)

---

## Revision History

| Version | Date       | Author        | Changes                              |
|---------|------------|---------------|--------------------------------------|
| 1.0     | 2025-01-23 | Security Team | Initial security incident runbook    |
