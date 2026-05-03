# 06 - Security-Perspektive (Pilot-Reality-Check)

**Rolle**: Security Architect / Angreifer
**Datum**: 2026-05-03
**Methode**: Synthese aus Audits 00h (Security), 00f (Infrastructure), 00d (API Inventory) plus gezielte Code-Verifikation
**Mindset**: Defense-in-Depth ist gut, aber ich suche die Stelle, wo ein Junior-Pentester nach 3 Stunden ein PoC hat.

---

## TL;DR (1 Satz)

**Die Security-Architektur ist enterprise-tauglich konzipiert (RLS, Hash-Chain, 2FA, Field-Encryption mit AAD), aber die Umsetzung enthaelt drei Pilot-Blocker - JWT-im-Body statt httpOnly, `python-jose` mit aktiver CVE, CSP mit `unsafe-inline` - die ein gezielter Angreifer in unter einem Tag findet.**

---

## OWASP Top 10 (2021) - Status-Tabelle

| ID | Kategorie | Status | Begruendung (1-Zeiler) |
|----|-----------|--------|------------------------|
| **A01** | Broken Access Control | **PARTIAL** | RLS aktiv (Migration 025) + Middleware setzt `app.current_company_id`. Aber 200+ Services filtern `company_id` manuell - eine vergessene Stelle = Tenant-Bleed. (CWE-285, CWE-639) |
| **A02** | Cryptographic Failures | **OK** | bcrypt cost=12, `secrets.token_urlsafe(32)` jti, `SecretStr` fuer Keys, TOTP-Secrets verschluesselt. Schwaeche: HS256 statt RS256/ES256 (Symmetric Key Risiko bei Multi-Service). |
| **A03** | Injection | **PARTIAL** | SQLAlchemy ORM dominant. ABER 6+ Stellen mit f-string SQL (`field_encryption_service`, `training_migration_service:223` ohne `text()`-Wrapper). Whitelist-Schutz da, aber fragil. (CWE-89) |
| **A04** | Insecure Design | **PARTIAL** | Hash-Chain fuer AuditLog/DomainEvents korrekt designed. Aber `previous_hash`/`chain_hash`/`sequence_number` in `models.py:889-893` sind **nullable** - DB-Trigger gegen UPDATE/DELETE laut Kommentar in Migration 017, aber Repo-Verifikation steht aus. (CWE-471) |
| **A05** | Security Misconfiguration | **PARTIAL** | Nginx-Headers vollstaendig (HSTS preload, XFO, XCTO). **Aber CSP enthaelt `unsafe-inline`** fuer script-src + style-src -> XSS-Schutz schwach. Zwei Nginx-Configs mit abweichenden HSTS-Werten. (CWE-1021) |
| **A06** | Vulnerable Components | **CRITICAL** | `python-jose==3.3.0` mit CVE-2024-33664 (algorithm confusion), `passlib==1.7.4` (unmaintained seit 2020), `fastapi==0.110.0` (alt). Kein `pip-audit` in CI. (CWE-1104) |
| **A07** | Auth Failures | **PARTIAL** | 2FA TOTP+Backup-Codes ok. Login-Rate-Limit `10/minute` per IP **zu schwach** (BSI: 5/15min + Lockout). JWT-Token im Response-Body statt httpOnly-Cookie - Doku/Code-Drift. (CWE-307, CWE-522) |
| **A08** | Data Integrity | **OK** | Hash-Chain DomainEvents (SHA-256 Genesis), GoBD CHECK-Constraint, CSRF Double-Submit-Cookie, Optimistic Locking. |
| **A09** | Logging/Monitoring | **OK** | structlog durchgaengig (89 Files migriert), AuditLog mit IP/UA/method/path, `safe_error_log` fuer PII-Maskierung, Prometheus-Metriken, Loki+Promtail+Jaeger. **Aber**: Out-of-Hours-Notification ist tot (Slack-Receiver auskommentiert, SMTP zeigt auf `localhost:587`). |
| **A10** | SSRF | **NOT_AUDITED** | Email-Import + Slack/Teams + URL-Fetcher in OCR/Folder-Import sind potentielle Vektoren. Kein dedizierter Allowlist-Code geprueft. (CWE-918) |

---

## Antworten auf die Pflichtfragen

**1. Auth-Flow (JWT/Refresh/TTL)**: Access-Token 15min, Refresh-Token 7 Tage (gut). **ABER**: Token kommt als JSON-Body (`api/v1/auth.py:166`), nicht als httpOnly-Cookie - obwohl `api/v1/README.md:13` das behauptet. Klassische Doku-Code-Drift. Portal-Auth definiert eigene 30min/7d-Konstanten (`portal_auth_service.py:29-30`) - inkonsistent.

**2. 2FA Backup-Codes**: Ja, 8 Backup-Codes, SHA-256-gehashed (`core/totp.py`, `mfa_service.py`). Recovery-Flow existiert. Solide.

**3. SQL-Injection**: ORM ueberwiegend. 6+ Raw-SQL-f-strings mit Whitelist-Validierung, plus `training_migration_service.py:223` mit `conn.execute(f"SELECT * FROM {table_name}")` ohne `text()` - falls `table_name` aus User-Input kaeme, waere das CWE-89. Aktuell intern aufgerufen, aber Codepfad fragil.

**4. XSS / `dangerouslySetInnerHTML`**: 8 Treffer im Frontend, alle mit DOMPurify gewrappt. **Aber**: bei `unsafe-inline` in CSP reicht ein einziges vergessenes Sanitize - die CSP ist kein Sicherheitsnetz mehr.

**5. CSRF**: Double-Submit-Cookie aktiv (`middleware/csrf.py`), `samesite=strict`, `httponly=False` fuer JS-Read (notwendig fuer Pattern). Login als Exempt-Path - korrekt. Solide.

**6. Rate-Limiting**: 554 Vorkommen / 3012 Endpoints = **18% Coverage**. Login `10/min` zu schwach. Kein User-Level-Lockout sichtbar (nur Session-Concurrency). Globales nginx-RL als Sicherheitsnetz, aber bei 100 parallelen Pilot-Usern haut das nicht hin.

**7. File-Upload**: ClamAV als Hauptverteidigung im Compose. YARA-Rules in `security/yara_rules/document_malware.yar` - **nur 1 Datei, sehr duenn**. Magic-Number-Validierung steht aus (Audit hat keinen expliziten Fund). Risiko: Polyglot-Files (PDF mit JS-Payload) bei OCR-Pipeline.

**8. Secrets-History**: `git log -S"password="` zeigt Code-Refactor, keine sichtbaren Plain-Text-Secrets im Repo (Stichprobe). `.env.example` mit 99 Variablen. Vault gestartet aber nicht integriert - Secrets liegen weiterhin als Disk-Files. Kein systematisches `gitleaks`/`trufflehog` in CI.

**9. Audit-Log Hash-Chain**: SHA-256 Genesis-Pattern korrekt designed (`event_store.py:507`). **Aber**: `previous_hash`, `integrity_hash`, `sequence_number` als `nullable=True` in `models.py:889-893`. DB-Trigger gegen UPDATE/DELETE laut Kommentar in Migration 017 - Existenz im Repo nicht verifiziert. Luecken-Recovery: theoretisch ueber Genesis-Replay moeglich, praktisch nicht getestet.

**10. Multi-Tenant-Isolation**: RLS-Policies ab Migration 025, Middleware `company_context.py:399` setzt `SET app.current_company_id`. Defense-in-Depth ist da. **Aber**: 200+ Services mit manuellen `company_id ==` Filtern. Stichprobe `access_analytics_service.py:213` zeigt korrekten Filter. Risiko: bei 797 Service-Files reicht eine vergessene Stelle. Mai-2026-Backfill (Migration 257-261) zeigt: Multi-Tenancy ist gerade in der Hardening-Phase, nicht abgeschlossen.

---

## Top-3 Staerken

1. **Hash-Chain fuer DomainEvents (SHA-256, Genesis-Pattern)** - kanonisches JSON (`sort_keys=True, separators=(",", ":")`), DB-CHECK-Constraint fuer GoBD-Compliance. Architektonisch sauber.
2. **PostgreSQL Row-Level Security als Defense-in-Depth** - selbst wenn Application-Layer einen Tenant-Filter vergisst, blockt der DB-Layer. Migration 025 + Session-Hook (`db/session.py:217`).
3. **Field-Encryption mit AAD** (`field_encryption_service.py:85-87`) - Whitelist-Validierung gegen JSONB-SQL-Injection, AAD pro Feld verhindert Cross-Field-Substitution. Krypto-Hygiene auf hohem Niveau.

---

## Top-5 Luecken (mit CWE-IDs)

1. **JWT in Response-Body statt httpOnly-Cookie** (`api/v1/auth.py:166`) - **CWE-522** (Insufficiently Protected Credentials) + **CWE-79** (XSS-Token-Diebstahl). Doku/Code-Drift. Refresh-Token 7 Tage = grosses Zeitfenster fuer Token-Theft. Pilot-Blocker.

2. **`python-jose==3.3.0` mit CVE-2024-33664** (algorithm confusion) - **CWE-1104** (Vulnerable Components). Library nicht mehr gepflegt. Pilot-Blocker, weil ein automatisierter SCA-Scan das in 5 Sekunden findet. Migration zu `pyjwt[crypto]` (bereits Dependency) ist 1 Tag Arbeit.

3. **CSP enthaelt `unsafe-inline`** (`nginx/snippets/security-headers.conf:19`) - **CWE-1021** (Improper Restriction of Rendered UI Layers). Ein vergessenes DOMPurify reicht fuer Stored XSS - und damit fuer Diebstahl der JWT, die im localStorage liegt (siehe Punkt 1). Kombinations-Risiko.

4. **Login-Rate-Limit zu schwach (10/min IP, kein Account-Lockout)** - **CWE-307** (Improper Restriction of Excessive Authentication Attempts). 14400 Versuche/Tag pro IP = Credential-Stuffing trivial. BSI-Empfehlung: 5/15min + Account-Lockout + Captcha nach 3 Fehlversuchen + User-Level-Lockout (5/h pro Username).

5. **Multi-Tenant-Filter manuell in 200+ Services** - **CWE-639** (Authorization Bypass Through User-Controlled Key). RLS faengt es ab, **wenn** `app.current_company_id` korrekt gesetzt ist. Bei 797 Services und Mai-2026-Backfill noch in Arbeit (Migration 257-261) ist die Wahrscheinlichkeit einer vergessenen Stelle hoch. Empfehlung: SQLAlchemy `before_compile`-Event mit Auto-Filter ODER striktes Repository-Pattern.

**Bonus-Findings (nicht Top-5 aber nennenswert)**:
- AuditLog-Felder nullable - **CWE-471** (Modification of Assumed-Immutable Data). DB-Trigger-Verifikation fehlt.
- 33% der Endpoints ohne explizite Auth-Dep auf Route-Level (`ml.py` mit 5/15) - **CWE-862** (Missing Authorization). Globales Router-Default + `@public`-Whitelist-Pattern noetig.
- Out-of-Hours-Notification tot (Slack-Receiver auskommentiert, SMTP `localhost:587`) - **CWE-778** (Insufficient Logging). Security-Incidents werden nicht eskaliert.

---

## Note: Security Pilot-Readiness

**6 / 10**

| Dimension | Wert | Kommentar |
|-----------|------|-----------|
| Krypto-Hygiene | 8/10 | bcrypt cost=12, AAD, TOTP-Encryption |
| Auth-Architektur | 5/10 | 2FA gut, JWT-Body schlecht, Rate-Limit schwach |
| Injection-Schutz | 7/10 | ORM-dominant, Whitelist-Patterns, aber fragil |
| Multi-Tenancy | 6/10 | RLS gut, 200+ manuelle Filter riskant |
| Secrets-Mgmt | 5/10 | Vault bereit, aber unintegriert (.env-basiert) |
| Component-Hygiene | 3/10 | Aktive CVE, kein SCA in CI |
| Logging/Audit | 7/10 | structlog + Hash-Chain stark, Notification-Mile tot |
| File-Upload-Security | 6/10 | ClamAV gut, YARA duenn, Magic-Number unklar |

Mit 1-2 Wochen fokussiertem Hardening (Top-5 Luecken) realistisch auf **8/10**.

---

## Pentest-Empfehlung: JA - vor Pilot

**Externer Web-App-Pentest (5 PT) + Code-Review-Walkthrough (2 PT) BEVOR der erste echte Pilot-Kunde Daten eingibt.**

**Begruendung**:
- Multi-Tenant-Isolation mit 200+ manuellen Filtern braucht Black-Box-Validierung. Statische Code-Inspektion findet nicht alle vergessenen Filter.
- DSGVO-relevante Daten + Lexware-PII (Kundennummern, IBANs, USt-IDs) - Haftungsrisiko bei Tenant-Bleed.
- `python-jose` CVE waere bei Pentest ein triviler Finding und verbrennt PT.
- AuditLog-Immutability (DB-Trigger) muss vor Pentest verifiziert sein - sonst GoBD-Compliance unklar.

**Pre-Pentest-Checkliste (in dieser Reihenfolge)**:
1. JWT auf httpOnly-Cookie umstellen, Frontend-`localStorage`-Nutzung pruefen.
2. `python-jose` -> `pyjwt[crypto]` migrieren.
3. CSP ohne `unsafe-inline` (Nonce-/Hash-basiert), Inline-Scripts in React ausbauen.
4. Login-Rate-Limit verschaerfen (5/15min IP + 5/h pro Username + Account-Lockout).
5. AuditLog-DB-Trigger gegen UPDATE/DELETE explizit in Migration verifizieren.
6. `pip-audit` + `bandit` + `gitleaks` in CI verankern.
7. Portal-Auth-Konstanten konsolidieren mit Haupt-Auth.
8. `training_migration_service.py:223` Tabellenname-Whitelist ergaenzen.

**Timing**: Pre-Pentest-Checkliste in 1-2 Wochen abarbeiten -> Pentest in Woche 3 -> Findings fixen in Woche 4 -> Pilot-Start ab Woche 5. Nach Pilot mit 5-10 Kunden: zweiter Pentest vor Skalierung auf 100+ Kunden (Multi-Tenant-Stress-Test).

---

## Drei sofort-Massnahmen (diese Woche, < 2 Tage Arbeit)

1. **`python-jose` ersetzen durch `pyjwt[crypto]`** (CVE-2024-33664 schliessen). PyJWT ist bereits Dependency, Migration in `core/security_auth.py` ist <1 Tag. Danach `pip-audit` in CI als GitHub-Action verankern - das verhindert, dass die naechste CVE 5 Monate ungefixt bleibt.

2. **JWT auf httpOnly-Cookie umstellen** in `api/v1/auth.py:166`: `response.set_cookie("access_token", token, httponly=True, secure=True, samesite="strict", max_age=900)`. Gleichzeitig Frontend pruefen - falls `localStorage` genutzt wird, auf `credentials: "include"` umstellen. Das schliesst die Doku/Code-Drift und das XSS-Token-Theft-Fenster.

3. **Slack-Webhook in Alertmanager aktivieren** (5 Minuten Arbeit, aber Sicherheits-relevant): Receiver `email-receiver` durch `slack-receiver` ersetzen, `SLACK_WEBHOOK_URL` in `.env` setzen. Ohne diesen Punkt sieht Ben einen 2-Uhr-nachts-Security-Incident erst um 9:30 Uhr morgens - das ist im Pilot inakzeptabel und im Markt fahrlaessig.

**Diese drei Massnahmen heben die Note von 6/10 auf ca. 7/10 in 2 Tagen.** Der Rest der Top-5 (CSP-Hardening, Login-Rate-Limit, Multi-Tenant-Auto-Filter) braucht 1-2 Wochen und Tests.

---

**Wortzahl**: ca. 1380.
