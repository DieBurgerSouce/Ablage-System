# SOP-004: Security Incident Response

**Version**: 1.0
**Last Updated**: 2025-11-22
**Owner**: Security Team
**Status**: Production

## Purpose

This SOP defines the procedures for responding to security incidents in the Ablage-System, ensuring rapid containment, proper investigation, and GDPR-compliant handling of data breaches.

## Scope

This SOP applies to all security incidents including:
- Unauthorized access attempts
- Data breaches (actual or suspected)
- Malware detection
- DDoS attacks
- System vulnerabilities
- GDPR compliance violations

## Roles and Responsibilities

| Role | Responsibility |
|------|----------------|
| **Incident Commander** | Overall incident coordination, decision-making |
| **Security Analyst** | Investigation, evidence collection, analysis |
| **System Administrator** | System containment, remediation, recovery |
| **DPO (Data Protection Officer)** | GDPR compliance, authority notification |
| **Communications Lead** | Internal/external communication, user notification |

## Incident Severity Levels

### Critical (P1)
- Active data breach with personal data exfiltration
- Ransomware infection
- Complete system compromise
- Response Time: **Immediate (< 15 minutes)**

### High (P2)
- Suspected data breach
- Successful unauthorized access (no data exfiltration confirmed)
- Critical vulnerability exploitation
- Response Time: **< 1 hour**

### Medium (P3)
- Failed unauthorized access attempts (multiple)
- Non-critical vulnerability discovered
- Malware detected in uploaded documents
- Response Time: **< 4 hours**

### Low (P4)
- Single failed login attempt
- Security policy violation (non-critical)
- Minor configuration issue
- Response Time: **< 24 hours**

## Incident Response Workflow

### Phase 1: Detection & Assessment (0-15 minutes)

#### Step 1.1: Incident Detection

**Triggered by**:
- Monitoring alerts (Prometheus, Grafana)
- Security audit log anomalies
- User reports
- Automated security scans

**Immediate Actions**:
```bash
# Check recent security events
tail -n 100 Dynamic_Knowledge/Logs/security_audit_log.jsonl

# Check system health
curl http://localhost:8000/health

# Check for active threats
docker-compose logs | grep -i "error\|security\|unauthorized"
```

#### Step 1.2: Initial Assessment

**Determine**:
1. What happened? (type of incident)
2. When did it happen? (timeline)
3. What systems are affected?
4. Is personal data involved?
5. Is the threat active?

**Document** in incident tracking system:
- Incident ID: `INC-{YYYY}{MM}{DD}-{NUMBER}`
- Detection time
- Detection method
- Initial severity assessment

#### Step 1.3: Severity Classification

Use decision tree: [Relations/Decision_Trees/security_incident_response_tree.yaml](../../Relations/Decision_Trees/security_incident_response_tree.yaml)

**Critical Indicators**:
- [ ] Personal data accessed/exfiltrated
- [ ] Ransomware/malware execution
- [ ] Database compromise
- [ ] Multiple system compromise

**Escalation**:
- P1/P2: Activate Incident Commander immediately
- P3: Notify security team
- P4: Log and monitor

### Phase 2: Containment (15-60 minutes)

#### Step 2.1: Immediate Containment

**For Unauthorized Access**:
```bash
# 1. Lock affected user accounts
psql -c "UPDATE users SET is_active = false WHERE id = '{user_id}';"

# 2. Terminate all sessions
redis-cli KEYS "session:*" | xargs redis-cli DEL

# 3. Disable compromised API keys
psql -c "UPDATE api_keys SET is_active = false WHERE id = '{key_id}';"

# 4. Block attacking IP
iptables -A INPUT -s {IP_ADDRESS} -j DROP
```

**For Data Breach**:
```bash
# 1. Isolate affected systems
docker-compose stop {affected_service}

# 2. Create forensic backup
docker commit {container_id} forensic_backup_{timestamp}

# 3. Preserve logs
docker logs {container_id} > logs/incident_{inc_id}.log

# 4. Stop data exfiltration
# Check network connections
netstat -anp | grep ESTABLISHED
# Block suspicious connections
iptables -A OUTPUT -d {suspicious_ip} -j DROP
```

**For Malware**:
```bash
# 1. Quarantine infected file
mv /uploads/{filename} /quarantine/{filename}

# 2. Update virus definitions
freshclam

# 3. Full system scan
clamscan -r --infected --remove /uploads/
```

#### Step 2.2: Evidence Preservation

**Critical**: Do NOT delete or modify evidence!

```bash
# Create evidence directory
mkdir -p /evidence/INC-{incident_id}

# Collect system state
docker ps -a > /evidence/INC-{incident_id}/containers.txt
docker logs {container} > /evidence/INC-{incident_id}/{container}.log
netstat -anp > /evidence/INC-{incident_id}/network.txt
ps aux > /evidence/INC-{incident_id}/processes.txt

# Collect application logs
cp Dynamic_Knowledge/Logs/*.jsonl /evidence/INC-{incident_id}/

# Collect database state
pg_dump -Fc ablage_system > /evidence/INC-{incident_id}/db_backup.dump

# Calculate checksums
cd /evidence/INC-{incident_id}
sha256sum * > checksums.txt
```

### Phase 3: Investigation (1-4 hours)

#### Step 3.1: Forensic Analysis

**Timeline Reconstruction**:
1. When did the incident start?
2. What was the attack vector?
3. What actions did the attacker take?
4. What data was accessed?
5. When was it detected?

**Analysis Tools**:
```bash
# Analyze security audit log
cat Dynamic_Knowledge/Logs/security_audit_log.jsonl | \
  jq 'select(.timestamp >= "2025-01-20T10:00:00Z")' | \
  jq -s 'sort_by(.timestamp)'

# Find all actions by suspicious IP
grep "{suspicious_ip}" Dynamic_Knowledge/Logs/*.jsonl

# Check for lateral movement
docker logs backend | grep -i "ssh\|rdp\|smb"

# Analyze database access
psql -c "SELECT * FROM audit_logs WHERE
  timestamp >= '2025-01-20 10:00:00'
  ORDER BY timestamp;"
```

#### Step 3.2: Impact Assessment

**Determine**:
- [ ] Number of affected users
- [ ] Types of data accessed
- [ ] Duration of unauthorized access
- [ ] Extent of system compromise

**For Personal Data Breach**:
```sql
-- Count affected users
SELECT COUNT(DISTINCT user_id)
FROM documents
WHERE id IN (
  SELECT document_id
  FROM access_logs
  WHERE user_id = '{attacker_id}'
);

-- Identify data types accessed
SELECT DISTINCT document_type, COUNT(*)
FROM documents
WHERE id IN (
  SELECT document_id
  FROM access_logs
  WHERE user_id = '{attacker_id}'
)
GROUP BY document_type;
```

### Phase 4: GDPR Compliance (If Personal Data Affected)

#### Step 4.1: Breach Notification Decision

**Must notify if**:
- Personal data breach occurred
- Risk to rights and freedoms of individuals

**Timeline**:
- Supervisory authority: **72 hours** from awareness
- Affected individuals: **Without undue delay** if high risk

#### Step 4.2: Supervisory Authority Notification

**Required Information** (GDPR Art. 33):
1. Nature of the breach
2. Categories and approximate number of:
   - Affected data subjects
   - Personal data records concerned
3. Contact point (DPO)
4. Likely consequences
5. Measures taken or proposed

**Template**:
```
To: data-protection-authority@example.de
Subject: Personal Data Breach Notification - INC-{incident_id}

Dear Sir/Madam,

We hereby notify you of a personal data breach in accordance with
Article 33 of the GDPR.

1. Nature of Breach:
   [Unauthorized access to user documents via compromised API key]

2. Data Subjects Affected:
   - Approximate number: [XX users]
   - Categories: [Customers who uploaded invoices between DATE1 and DATE2]

3. Personal Data Records:
   - Approximate number: [XX documents]
   - Categories: [Invoices containing names, addresses, tax IDs]

4. Contact Point:
   Data Protection Officer
   Email: dpo@company.de
   Phone: +49-XXX-XXXXXXX

5. Likely Consequences:
   [Risk of identity theft, financial fraud]

6. Measures Taken:
   - [Immediate: Disabled compromised API key, locked accounts]
   - [Short-term: Password reset for all affected users]
   - [Long-term: Enhanced API key security, MFA implementation]

Date of breach awareness: [YYYY-MM-DD HH:MM]
Date of this notification: [YYYY-MM-DD HH:MM]

Sincerely,
[Name], Data Protection Officer
```

#### Step 4.3: Individual Notification (If High Risk)

**Template** (German):
```
Betreff: Wichtige Sicherheitsmitteilung zu Ihren Daten

Sehr geehrte/r [Name],

wir informieren Sie über einen Sicherheitsvorfall, der Ihre
personenbezogenen Daten betrifft.

Was ist passiert?
[Am DD.MM.YYYY kam es zu einem unbefugten Zugriff auf unser System...]

Welche Daten sind betroffen?
[Ihre hochgeladenen Dokumente vom Zeitraum XX.XX.XXXX bis XX.XX.XXXX,
die folgende Informationen enthalten können: Name, Adresse, ...]

Welche Maßnahmen haben wir ergriffen?
- [Sofortige Sperrung des betroffenen Systems]
- [Zurücksetzen aller Passwörter]
- [Verstärkte Sicherheitsmaßnahmen]

Was sollten Sie tun?
1. [Ändern Sie Ihr Passwort unter: https://...]
2. [Überprüfen Sie Ihre Kontobewegungen]
3. [Kontaktieren Sie uns bei Fragen: security@company.de]

Weitere Informationen:
[Link zu FAQ, Kontaktdaten für Rückfragen]

Mit freundlichen Grüßen,
[Ihr Security Team]
```

### Phase 5: Eradication & Recovery (4-24 hours)

#### Step 5.1: Remove Threat

**For Compromised Credentials**:
```bash
# Force password reset for all users
psql -c "UPDATE users SET password_reset_required = true;"

# Rotate all API keys
python scripts/rotate_api_keys.py

# Rotate database credentials
python scripts/rotate_db_credentials.py
```

**For Malware**:
```bash
# Remove infected files
rm -rf /uploads/{infected_path}

# Update antivirus signatures
freshclam && clamscan -r --infected --remove /

# Scan all uploads
clamscan -r /uploads/
```

**For Vulnerabilities**:
```bash
# Apply security patches
apt-get update && apt-get upgrade -y

# Update application dependencies
pip install --upgrade -r requirements.txt

# Rebuild containers with patches
docker-compose build --no-cache
```

#### Step 5.2: System Hardening

**Immediate**:
- [ ] Change all passwords and keys
- [ ] Review and tighten firewall rules
- [ ] Update all software components
- [ ] Enable additional logging
- [ ] Increase monitoring sensitivity

**Configuration Changes**:
```bash
# Enable MFA for all users
psql -c "UPDATE users SET mfa_required = true;"

# Reduce session timeout
# In .env: SESSION_TIMEOUT=900  # 15 minutes

# Strengthen rate limiting
# In app/config.py: RATE_LIMIT_PER_HOUR = 5  # From 10
```

#### Step 5.3: Service Restoration

**Staged Approach**:
1. Restore in staging environment first
2. Run full test suite
3. Security scan
4. Gradual production rollout

```bash
# 1. Staging restore
docker-compose -f docker-compose.staging.yml up -d

# 2. Run tests
pytest tests/ -v --cov=app

# 3. Security scan
bandit -r app/ -f json
safety check

# 4. Production restore (blue-green)
ansible-playbook -i inventory/production playbooks/deploy_green.yml
```

### Phase 6: Post-Incident Activities (24-72 hours)

#### Step 6.1: Post-Incident Review

**Schedule**: Within 7 days of incident closure

**Participants**:
- Incident Commander
- All team members involved
- Management (if P1/P2)

**Agenda**:
1. Timeline review
2. Response effectiveness
3. Gaps identified
4. Lessons learned
5. Action items

**Template**:
```markdown
# Post-Incident Review: INC-{incident_id}

## Incident Summary
- Type: [Data breach / Unauthorized access / ...]
- Severity: [P1 / P2 / P3 / P4]
- Detection: [YYYY-MM-DD HH:MM]
- Resolution: [YYYY-MM-DD HH:MM]
- Duration: [XX hours XX minutes]

## What Happened?
[Detailed chronological description]

## What Went Well?
- [Quick detection via monitoring alert]
- [Effective containment procedure]
- [...]

## What Could Be Improved?
- [Delayed escalation (15 min vs 5 min target)]
- [Missing runbook for this scenario]
- [...]

## Root Cause
[Primary cause of incident]

## Action Items
1. [Update firewall rules] - Owner: SysAdmin - Due: 2025-02-01
2. [Implement MFA] - Owner: Security Lead - Due: 2025-02-15
3. [Conduct security training] - Owner: HR - Due: 2025-03-01

## Preventive Measures
[Long-term changes to prevent recurrence]
```

#### Step 6.2: Update Documentation

- [ ] Update incident response procedures
- [ ] Add to known issues / FAQs
- [ ] Update security documentation
- [ ] Share lessons learned with team

#### Step 6.3: Implement Improvements

**Track Action Items**:
```yaml
# Add to Relations/Workflows/security_improvements.yaml
action_items:
  - id: "AI-001"
    description: "Implement MFA for all users"
    priority: "critical"
    owner: "security_team"
    due_date: "2025-02-15"
    status: "in_progress"
```

## Communication Templates

### Internal Alert (Slack)

```
🚨 SECURITY INCIDENT ALERT

Incident ID: INC-{incident_id}
Severity: {P1 / P2 / P3 / P4}
Type: {brief description}
Detection: {timestamp}
Status: {Investigating / Contained / Resolved}

Incident Commander: @{name}

Action Required:
{any immediate actions needed from team}

Next Update: {timestamp}
```

### Status Update

```
📊 Incident Status Update - INC-{incident_id}

Current Status: {Investigating / Containing / Recovering / Resolved}

Progress:
✅ {completed actions}
🔄 {in progress actions}
⏳ {pending actions}

Timeline:
- Detection: {timestamp}
- Containment: {timestamp}
- Resolution ETA: {timestamp}

Next Update: {timestamp}
```

## Appendix

### A. Quick Reference Commands

```bash
# Lock user account
psql -c "UPDATE users SET is_active = false WHERE email = '{email}';"

# Clear all sessions
redis-cli FLUSHDB

# Block IP address
iptables -A INPUT -s {IP} -j DROP

# Check recent logins
psql -c "SELECT * FROM audit_logs WHERE event_type = 'login' ORDER BY timestamp DESC LIMIT 20;"

# Export incident evidence
tar -czf incident_{id}_evidence.tar.gz /evidence/INC-{id}/
```

### B. Contact List

| Role | Contact | Phone | Available |
|------|---------|-------|-----------|
| Security Lead | security-lead@company.de | +49-XXX-XXX | 24/7 |
| DPO | dpo@company.de | +49-XXX-XXX | Business hours |
| On-Call Engineer | oncall@company.de | PagerDuty | 24/7 |
| Management | management@company.de | +49-XXX-XXX | Business hours |

### C. External Contacts

- **Supervisory Authority**: data-protection-authority@example.de
- **Law Enforcement**: 110 (emergency), local cybercrime unit
- **Security Vendor**: security-vendor@example.de

## Related Documents

- [Relations/Decision_Trees/security_incident_response_tree.yaml](../../Relations/Decision_Trees/security_incident_response_tree.yaml)
- [Meta_Layer/MOCs/SECURITY_MOC.md](../../Meta_Layer/MOCs/SECURITY_MOC.md)
- [Dynamic_Knowledge/Logs/security_audit_log.jsonl](../../Dynamic_Knowledge/Logs/security_audit_log.jsonl)
- [Static_Knowledge/Snippets/gdpr_logging_patterns.py](../../Static_Knowledge/Snippets/gdpr_logging_patterns.py)

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-22 | Security Team | Initial version |

---

**CONFIDENTIAL**: This document contains sensitive security procedures. Distribute on need-to-know basis only.
