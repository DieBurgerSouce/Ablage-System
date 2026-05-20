# Audit-Checkliste

> **Ablage-System - Compliance & Security Audit Guide**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Diese Checkliste dient zur Durchführung von internen und externen Audits des Ablage-Systems. Sie deckt alle relevanten Bereiche für Datenschutz, IT-Sicherheit und Compliance ab.

---

## Inhaltsverzeichnis

1. [Audit-Vorbereitung](#audit-vorbereitung)
2. [Datenschutz (DSGVO)](#datenschutz-dsgvo)
3. [IT-Sicherheit](#it-sicherheit)
4. [Zugangskontrolle](#zugangskontrolle)
5. [Datensicherung](#datensicherung)
6. [Protokollierung](#protokollierung)
7. [Infrastruktur](#infrastruktur)
8. [Dokumentenmanagement](#dokumentenmanagement)
9. [Notfall-Management](#notfall-management)
10. [Audit-Abschluss](#audit-abschluss)

---

## Audit-Vorbereitung

### Vor dem Audit

| Nr. | Prüfpunkt | Status | Anmerkungen |
|-----|-----------|--------|-------------|
| 1.1 | Audit-Scope definiert | ☐ | |
| 1.2 | Audit-Team benannt | ☐ | |
| 1.3 | Zeitplan erstellt | ☐ | |
| 1.4 | Dokumentation bereitgestellt | ☐ | |
| 1.5 | Ansprechpartner informiert | ☐ | |
| 1.6 | Testzugänge vorbereitet | ☐ | |
| 1.7 | Vorherige Audit-Berichte gesichtet | ☐ | |

### Benötigte Dokumentation

```
Bereitstellen:
├── Systemarchitektur-Diagramme
├── Netzwerkplan
├── Benutzer- und Rollenübersicht
├── Datenschutz-Folgenabschätzung (DSFA)
├── Verfahrensverzeichnis
├── Backup-Konzept
├── Notfallplan
├── Letzte Penetrationstest-Berichte
└── Vorherige Audit-Ergebnisse
```

---

## Datenschutz (DSGVO)

### Art. 5 - Grundsätze der Verarbeitung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.1 | **Rechtmäßigkeit**: Rechtsgrundlage für alle Verarbeitungen dokumentiert | ☐ | |
| 2.2 | **Zweckbindung**: Verarbeitungszwecke definiert und eingehalten | ☐ | |
| 2.3 | **Datenminimierung**: Nur notwendige Daten werden erhoben | ☐ | |
| 2.4 | **Richtigkeit**: Prozess zur Datenaktualisierung vorhanden | ☐ | |
| 2.5 | **Speicherbegrenzung**: Löschfristen definiert und automatisiert | ☐ | |
| 2.6 | **Integrität**: Technische Schutzmaßnahmen implementiert | ☐ | |
| 2.7 | **Vertraulichkeit**: Zugriffsbeschränkungen aktiv | ☐ | |

### Art. 13/14 - Informationspflichten

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.8 | Datenschutzerklärung vorhanden und aktuell | ☐ | |
| 2.9 | Kontaktdaten des Verantwortlichen angegeben | ☐ | |
| 2.10 | Kontaktdaten des DSB angegeben (falls vorhanden) | ☐ | |
| 2.11 | Verarbeitungszwecke transparent dargestellt | ☐ | |
| 2.12 | Speicherdauer kommuniziert | ☐ | |
| 2.13 | Betroffenenrechte erläutert | ☐ | |

### Art. 15-22 - Betroffenenrechte

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.14 | **Auskunft (Art. 15)**: Export-Funktion implementiert | ☐ | |
| 2.15 | **Berichtigung (Art. 16)**: Korrektur-Workflow vorhanden | ☐ | |
| 2.16 | **Löschung (Art. 17)**: Löschfunktion mit Bestätigung | ☐ | |
| 2.17 | **Einschränkung (Art. 18)**: Verarbeitung pausierbar | ☐ | |
| 2.18 | **Datenübertragbarkeit (Art. 20)**: Maschinenlesbarer Export | ☐ | |
| 2.19 | **Widerspruch (Art. 21)**: Widerspruchsprozess definiert | ☐ | |
| 2.20 | Bearbeitungsfristen (30 Tage) eingehalten | ☐ | |

### Art. 28 - Auftragsverarbeitung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.21 | AVV mit allen Dienstleistern abgeschlossen | ☐ | |
| 2.22 | Subunternehmer dokumentiert | ☐ | |
| 2.23 | Weisungsrecht vertraglich gesichert | ☐ | |
| 2.24 | Audits bei Auftragsverarbeitern durchführbar | ☐ | |

### Art. 30 - Verzeichnis der Verarbeitungstätigkeiten

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.25 | Verfahrensverzeichnis vollständig | ☐ | |
| 2.26 | Kategorien personenbezogener Daten dokumentiert | ☐ | |
| 2.27 | Empfänger(-kategorien) dokumentiert | ☐ | |
| 2.28 | Löschfristen dokumentiert | ☐ | |
| 2.29 | TOM-Übersicht vorhanden | ☐ | |

### Art. 32 - Technische und organisatorische Maßnahmen

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.30 | Pseudonymisierung wo möglich angewendet | ☐ | |
| 2.31 | Verschlüsselung bei Übertragung (TLS 1.3) | ☐ | |
| 2.32 | Verschlüsselung bei Speicherung | ☐ | |
| 2.33 | Wiederherstellbarkeit der Daten | ☐ | |
| 2.34 | Regelmäßige Überprüfung der TOM | ☐ | |

### Art. 33/34 - Datenschutzverletzungen

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 2.35 | Meldeprozess definiert (72h an Behörde) | ☐ | |
| 2.36 | Betroffenen-Benachrichtigungsprozess vorhanden | ☐ | |
| 2.37 | Incident-Response-Team benannt | ☐ | |
| 2.38 | Dokumentationsvorlage für Vorfälle | ☐ | |

---

## IT-Sicherheit

### Netzwerksicherheit

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 3.1 | Firewall aktiv und konfiguriert | ☐ | |
| 3.2 | Netzwerksegmentierung implementiert | ☐ | |
| 3.3 | VPN für Remote-Zugriff | ☐ | |
| 3.4 | IDS/IPS aktiv | ☐ | |
| 3.5 | Ports minimiert (nur benötigte offen) | ☐ | |
| 3.6 | DDoS-Schutz vorhanden | ☐ | |

**Prüfbefehl:**
```bash
# Offene Ports prüfen
nmap -sT localhost

# Firewall-Regeln anzeigen
iptables -L -n -v
# oder
ufw status verbose
```

### Verschlüsselung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 3.7 | TLS 1.3 für HTTPS | ☐ | |
| 3.8 | Gültige SSL-Zertifikate | ☐ | |
| 3.9 | Datenbank-Verbindungen verschlüsselt | ☐ | |
| 3.10 | Redis-Verbindung verschlüsselt (TLS) | ☐ | |
| 3.11 | MinIO-Verschlüsselung aktiv | ☐ | |

**Prüfbefehl:**
```bash
# TLS-Version prüfen
openssl s_client -connect localhost:443 -tls1_3

# Zertifikat-Gültigkeit
openssl s_client -connect localhost:443 2>/dev/null | openssl x509 -dates -noout
```

### Schwachstellen-Management

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 3.12 | Regelmäßige Vulnerability-Scans | ☐ | |
| 3.13 | Patch-Management-Prozess definiert | ☐ | |
| 3.14 | Sicherheitsupdates zeitnah eingespielt | ☐ | |
| 3.15 | Abhängigkeiten auf Schwachstellen geprüft | ☐ | |

**Prüfbefehl:**
```bash
# Python-Abhängigkeiten prüfen
pip-audit

# npm-Abhängigkeiten prüfen
npm audit

# Docker-Images scannen
trivy image ablage-backend:latest
```

### Anwendungssicherheit

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 3.16 | SQL-Injection-Schutz (ORM) | ☐ | |
| 3.17 | XSS-Schutz (Content-Security-Policy) | ☐ | |
| 3.18 | CSRF-Schutz implementiert | ☐ | |
| 3.19 | Input-Validierung durchgängig | ☐ | |
| 3.20 | Rate-Limiting aktiv | ☐ | |
| 3.21 | Security-Header gesetzt | ☐ | |

**Prüfbefehl:**
```bash
# Security-Header prüfen
curl -I https://localhost | grep -E "(X-Frame|X-XSS|Content-Security|Strict-Transport)"

# Rate-Limiting testen
for i in {1..20}; do curl -s -o /dev/null -w "%{http_code}\n" https://localhost/api/v1/auth/login; done
```

---

## Zugangskontrolle

### Authentifizierung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 4.1 | Starke Passwortrichtlinien (Min. 12 Zeichen) | ☐ | |
| 4.2 | Passwort-Hashing (bcrypt, cost 12) | ☐ | |
| 4.3 | MFA optional/verpflichtend | ☐ | |
| 4.4 | Account-Sperrung nach Fehlversuchen | ☐ | |
| 4.5 | Session-Timeout konfiguriert | ☐ | |
| 4.6 | JWT-Tokens sicher (httpOnly, Secure) | ☐ | |

**Prüfbefehl:**
```bash
# Passwort-Policy prüfen (API)
curl https://localhost/api/v1/auth/password-policy

# Session-Cookie-Attribute prüfen
curl -I https://localhost/api/v1/auth/login -c - | grep -i set-cookie
```

### Autorisierung (RBAC)

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 4.7 | Rollen definiert und dokumentiert | ☐ | |
| 4.8 | Minimalprinzip (Least Privilege) | ☐ | |
| 4.9 | Rollenzuweisung nachvollziehbar | ☐ | |
| 4.10 | Regelmäßige Berechtigungsüberprüfung | ☐ | |
| 4.11 | Admin-Accounts separat und gesichert | ☐ | |

**Rollenübersicht prüfen:**
```sql
-- PostgreSQL: Benutzer und Rollen
SELECT u.email, r.name as role, r.permissions
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id;
```

### Benutzerverwaltung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 4.12 | Onboarding-Prozess dokumentiert | ☐ | |
| 4.13 | Offboarding-Prozess (zeitnahe Deaktivierung) | ☐ | |
| 4.14 | Inaktive Accounts deaktiviert (90 Tage) | ☐ | |
| 4.15 | Service-Accounts dokumentiert | ☐ | |

---

## Datensicherung

### Backup-Strategie

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 5.1 | Backup-Konzept dokumentiert | ☐ | |
| 5.2 | Automatisierte Backups aktiv | ☐ | |
| 5.3 | 3-2-1-Regel eingehalten | ☐ | |
| 5.4 | Offsite-Backup vorhanden | ☐ | |
| 5.5 | Backup-Verschlüsselung | ☐ | |

**Prüfbefehl:**
```bash
# Backup-Status prüfen
curl http://localhost:8000/api/v1/backup/status

# Letzte Backups auflisten
curl http://localhost:8000/api/v1/backup/list
```

### Backup-Komponenten

| Nr. | Komponente | Backup-Typ | Intervall | Aufbewahrung | Status |
|-----|------------|------------|-----------|--------------|--------|
| 5.6 | PostgreSQL | pg_dump | Täglich | 30 Tage | ☐ |
| 5.7 | Redis | RDB Snapshot | Täglich | 7 Tage | ☐ |
| 5.8 | MinIO | mc mirror | Täglich | 90 Tage | ☐ |
| 5.9 | Konfiguration | tar.gz | Wöchentlich | 90 Tage | ☐ |

### Wiederherstellung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 5.10 | Restore-Prozedur dokumentiert | ☐ | |
| 5.11 | Regelmäßige Restore-Tests (quartalsweise) | ☐ | |
| 5.12 | RTO definiert (< 4 Stunden) | ☐ | |
| 5.13 | RPO definiert (< 24 Stunden) | ☐ | |
| 5.14 | Letzter erfolgreicher Restore-Test | ☐ | Datum: _______ |

---

## Protokollierung

### Log-Management

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 6.1 | Zentrale Log-Aggregation (Loki) | ☐ | |
| 6.2 | Strukturierte Logs (JSON) | ☐ | |
| 6.3 | Log-Retention definiert | ☐ | |
| 6.4 | Log-Integrität geschützt | ☐ | |
| 6.5 | Keine sensiblen Daten in Logs | ☐ | |

### Audit-Logging

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 6.6 | Login-Versuche protokolliert | ☐ | |
| 6.7 | Berechtigungsänderungen protokolliert | ☐ | |
| 6.8 | Dokumentenzugriffe protokolliert | ☐ | |
| 6.9 | Admin-Aktionen protokolliert | ☐ | |
| 6.10 | Löschvorgänge protokolliert | ☐ | |

**Prüfbefehl:**
```bash
# Audit-Logs abfragen (Beispiel: Login-Events)
curl "http://localhost:8000/api/v1/audit/logs?action=auth.login&limit=100"

# Loki-Query für Security-Events
logcli query '{app="ablage-backend"} |= "security"' --limit=50
```

### Log-Aufbewahrung

| Log-Typ | Aufbewahrung | Status |
|---------|--------------|--------|
| Anwendungslogs | 90 Tage | ☐ |
| Sicherheitslogs | 365 Tage | ☐ |
| Audit-Logs | 7 Jahre | ☐ |
| Fehler-Logs | 90 Tage | ☐ |

---

## Infrastruktur

### Server-Sicherheit

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 7.1 | OS gehärtet (CIS Benchmark) | ☐ | |
| 7.2 | Automatische Updates aktiv | ☐ | |
| 7.3 | SSH nur mit Key-Auth | ☐ | |
| 7.4 | Root-Login deaktiviert | ☐ | |
| 7.5 | Fail2ban aktiv | ☐ | |
| 7.6 | Antivirensoftware (optional) | ☐ | |

**Prüfbefehl:**
```bash
# SSH-Konfiguration prüfen
grep -E "^PermitRootLogin|^PasswordAuthentication" /etc/ssh/sshd_config

# Fail2ban-Status
fail2ban-client status sshd

# Offene Ports
ss -tulpn
```

### Docker-Sicherheit

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 7.7 | Aktuelle Docker-Version | ☐ | |
| 7.8 | Container als non-root | ☐ | |
| 7.9 | Ressourcen-Limits gesetzt | ☐ | |
| 7.10 | Keine privilegierten Container | ☐ | |
| 7.11 | Read-only Filesystems wo möglich | ☐ | |
| 7.12 | Secrets nicht in Images | ☐ | |

**Prüfbefehl:**
```bash
# Container-Sicherheit prüfen
docker inspect --format='{{.HostConfig.Privileged}}' $(docker ps -q)

# Ressourcen-Limits
docker stats --no-stream

# Image-Vulnerabilities
trivy image ablage-backend:latest
```

### GPU-Infrastruktur

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 7.13 | GPU-Treiber aktuell | ☐ | |
| 7.14 | CUDA-Version kompatibel | ☐ | |
| 7.15 | GPU-Isolation zwischen Containern | ☐ | |
| 7.16 | VRAM-Monitoring aktiv | ☐ | |

**Prüfbefehl:**
```bash
# GPU-Status
nvidia-smi

# CUDA-Version
nvcc --version

# GPU-Nutzung in Docker
docker exec ablage-worker nvidia-smi
```

---

## Dokumentenmanagement

### Dokumentensicherheit

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 8.1 | Zugriffskontrolle auf Dokumentebene | ☐ | |
| 8.2 | Dokumenten-Verschlüsselung | ☐ | |
| 8.3 | Virus-Scanning bei Upload | ☐ | |
| 8.4 | Erlaubte Dateitypen begrenzt | ☐ | |
| 8.5 | Maximale Dateigröße konfiguriert | ☐ | |

### OCR-Verarbeitung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 8.6 | OCR-Daten sicher gespeichert | ☐ | |
| 8.7 | Keine Weitergabe an externe Dienste | ☐ | |
| 8.8 | Temporäre Dateien gelöscht | ☐ | |
| 8.9 | GPU-Speicher nach Verarbeitung freigegeben | ☐ | |

### Datenklassifizierung

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 8.10 | Dokumenttypen klassifiziert | ☐ | |
| 8.11 | Sensible Dokumente markiert | ☐ | |
| 8.12 | Aufbewahrungsfristen definiert | ☐ | |
| 8.13 | Automatische Löschung nach Frist | ☐ | |

---

## Notfall-Management

### Business Continuity

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 9.1 | Notfallplan dokumentiert | ☐ | |
| 9.2 | Verantwortlichkeiten definiert | ☐ | |
| 9.3 | Kontaktliste aktuell | ☐ | |
| 9.4 | Eskalationspfade definiert | ☐ | |
| 9.5 | Regelmäßige Notfallübungen | ☐ | |

### Incident Response

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 9.6 | Incident-Response-Plan vorhanden | ☐ | |
| 9.7 | Incident-Response-Team benannt | ☐ | |
| 9.8 | Kommunikationsplan (intern/extern) | ☐ | |
| 9.9 | Forensik-Prozess definiert | ☐ | |
| 9.10 | Post-Incident-Review-Prozess | ☐ | |

### Disaster Recovery

| Nr. | Prüfpunkt | Erfüllt | Nachweis |
|-----|-----------|---------|----------|
| 9.11 | DR-Plan dokumentiert | ☐ | |
| 9.12 | Failover-Standort (falls vorhanden) | ☐ | |
| 9.13 | RTO: < 4 Stunden | ☐ | |
| 9.14 | RPO: < 24 Stunden | ☐ | |
| 9.15 | Jährlicher DR-Test durchgeführt | ☐ | Datum: _______ |

---

## Audit-Abschluss

### Zusammenfassung

| Bereich | Geprüft | Bestanden | Abweichungen |
|---------|---------|-----------|--------------|
| Datenschutz (DSGVO) | ☐ | ☐ | |
| IT-Sicherheit | ☐ | ☐ | |
| Zugangskontrolle | ☐ | ☐ | |
| Datensicherung | ☐ | ☐ | |
| Protokollierung | ☐ | ☐ | |
| Infrastruktur | ☐ | ☐ | |
| Dokumentenmanagement | ☐ | ☐ | |
| Notfall-Management | ☐ | ☐ | |

### Feststellungen

#### Kritisch (Sofortmaßnahmen erforderlich)

| Nr. | Feststellung | Maßnahme | Verantwortlich | Frist |
|----|--------------|----------|----------------|-------|
| K1 | | | | |
| K2 | | | | |

#### Hoch (Maßnahmen innerhalb 30 Tage)

| Nr. | Feststellung | Maßnahme | Verantwortlich | Frist |
|----|--------------|----------|----------------|-------|
| H1 | | | | |
| H2 | | | | |

#### Mittel (Maßnahmen innerhalb 90 Tage)

| Nr. | Feststellung | Maßnahme | Verantwortlich | Frist |
|----|--------------|----------|----------------|-------|
| M1 | | | | |
| M2 | | | | |

#### Niedrig (Empfehlungen)

| Nr. | Feststellung | Empfehlung |
|----|--------------|------------|
| N1 | | |
| N2 | | |

### Audit-Abschluss

| Feld | Wert |
|------|------|
| Audit-Zeitraum | ___ bis ___ |
| Auditor(en) | |
| Audit-Typ | ☐ Intern ☐ Extern |
| Gesamt-Ergebnis | ☐ Bestanden ☐ Bestanden mit Auflagen ☐ Nicht bestanden |
| Nächstes Audit | |

### Unterschriften

| Rolle | Name | Unterschrift | Datum |
|-------|------|--------------|-------|
| Auditor | | | |
| IT-Leitung | | | |
| Datenschutzbeauftragter | | | |
| Geschäftsführung | | | |

---

## Anhänge

### A. Automatisierte Prüfbefehle

Für eine schnelle Überprüfung können folgende Befehle ausgeführt werden:

```bash
#!/bin/bash
# audit-check.sh - Automatisierte Audit-Prüfungen

echo "=== Ablage-System Audit-Check ==="
echo "Datum: $(date)"
echo ""

# System-Status
echo "--- System-Status ---"
docker-compose ps
echo ""

# Sicherheits-Header
echo "--- Security Headers ---"
curl -sI https://localhost | grep -E "(X-Frame|X-XSS|Content-Security|Strict-Transport)"
echo ""

# SSL-Zertifikat
echo "--- SSL-Zertifikat ---"
openssl s_client -connect localhost:443 2>/dev/null | openssl x509 -dates -noout
echo ""

# Backup-Status
echo "--- Backup-Status ---"
curl -s http://localhost:8000/api/v1/backup/status | jq
echo ""

# GPU-Status
echo "--- GPU-Status ---"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv
echo ""

# Container-Sicherheit
echo "--- Container-Sicherheit ---"
echo "Privilegierte Container:"
docker inspect --format='{{.Name}}: {{.HostConfig.Privileged}}' $(docker ps -q)
echo ""

# Offene Ports
echo "--- Offene Ports ---"
ss -tulpn | grep LISTEN
echo ""

echo "=== Audit-Check abgeschlossen ==="
```

### B. Compliance-Matrix

| Anforderung | DSGVO | ISO 27001 | BSI Grundschutz |
|-------------|-------|-----------|-----------------|
| Zugangskontrolle | Art. 32 | A.9 | ORP.4 |
| Verschlüsselung | Art. 32 | A.10 | CON.1 |
| Protokollierung | Art. 30 | A.12.4 | OPS.1.1.5 |
| Backup | Art. 32 | A.12.3 | CON.3 |
| Incident Response | Art. 33/34 | A.16 | DER.2.1 |

### C. Glossar

| Begriff | Erklärung |
|---------|-----------|
| AVV | Auftragsverarbeitungsvertrag |
| DSFA | Datenschutz-Folgenabschätzung |
| DSB | Datenschutzbeauftragter |
| RTO | Recovery Time Objective |
| RPO | Recovery Point Objective |
| TOM | Technische und organisatorische Maßnahmen |
| MFA | Multi-Faktor-Authentifizierung |
| RBAC | Role-Based Access Control |

---

*Letzte Aktualisierung: Januar 2025*
