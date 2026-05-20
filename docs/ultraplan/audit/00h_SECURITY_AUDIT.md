# 00h - Security Audit (Pilot-Reality-Check)

**Datum**: 2026-05-03
**Branch**: feature/ocr-performance
**Methode**: Angreifer-Perspektive, Code-Inspektion (kein Live-Pentest)
**Scope**: Backend (FastAPI), Frontend (React), Infra (Nginx), DB (Postgres + RLS)

---

## OWASP Top 10 (2021) - Status

| ID | Risiko | Status | Evidenz |
|----|--------|--------|---------|
| A01 | Broken Access Control | **PARTIAL** | RLS aktiv (`alembic/versions/025_add_rls_policies.py:69`), Tenant-Filter in Queries vorhanden (`access_analytics_service.py:213`); aber kein zentralisierter Authorization-Decorator - jedes Service muss `company_id` selbst filtern. Risiko: Vergessene Filter in 200+ Services. |
| A02 | Cryptographic Failures | **OK** | bcrypt cost=12 (`security_auth.py:363`), JWT mit `secrets.token_urlsafe(32)` jti, SECRET_KEY als `SecretStr` (`security_auth.py:402`), TOTP-Secrets verschluesselt (`core/totp.py:44-48`). Algorithm via Config (HS256 default - **KEIN RS256/ES256**, Symmetric Key Risiko bei Multi-Service). |
| A03 | Injection | **PARTIAL** | Hauptsaechlich SQLAlchemy ORM. **6 Stellen mit f-string SQL** in `field_encryption_service.py:102/131/228/239/266/390` (mit `# noqa: S608`), `backup_restore_test_service.py:649`, `adhoc_report_service.py:721`, `training_migration_service.py:223`. Alle haben Whitelist-Validierung (`_validate_field`), aber `training_migration_service.py:223` nutzt **rohes `conn.execute(f"SELECT * FROM {table_name}")` ohne `text()`** - Tabellenname-Validation pruefen! NLQ hat dedizierten Sanitizer (`ai/nlq/sql_sanitizer.py`). |
| A04 | Insecure Design | **PARTIAL** | Hash-Chain fuer AuditLog + DomainEvents (Genesis -> SHA-256 verkettet, `event_store.py:507`), aber `previous_hash` und `chain_hash` sind **nullable** (`models.py:889-893`). Kein DB-Trigger gegen UPDATE/DELETE im Code sichtbar (Kommentar verweist auf Migration 017 - nicht verifiziert). |
| A05 | Security Misconfiguration | **OK** | Security-Headers in `infrastructure/nginx/snippets/security-headers.conf:5-25` (X-Frame-Options=SAMEORIGIN, HSTS 1y+preload, CSP). **CSP enthaelt `unsafe-inline` fuer script-src + style-src** - schwaecht XSS-Schutz erheblich. |
| A06 | Vulnerable Components | **PARTIAL** | `python-jose==3.3.0` (CVE-2024-33664 algorithm confusion - **AUSWECHSELN**), `passlib==1.7.4` (unmaintained, letzter Release 2020), `fastapi==0.110.0` (alt, aktuell ist 0.115+), `sqlalchemy==2.0.25` (ok). Keine `pip-audit`/`safety`-Run sichtbar. |
| A07 | Auth Failures | **PARTIAL** | 2FA TOTP+Backup-Codes (`mfa_service.py`, `core/totp.py`), Login-Rate-Limit `10/minute` per IP (`auth.py:93`) - **schwach** (BSI empfiehlt 5/15min + Account-Lockout). Registration `5/hour` ok. Password-Reset `3/hour` (RateLimitTier.PASSWORD_RESET). JWT-Tokens werden im Response-Body als Bearer zurueckgegeben (`auth.py:166`), **NICHT als httpOnly-Cookie** trotz Doku-Behauptung in `api/v1/README.md:13` (Inkonsistenz - XSS-Token-Diebstahl moeglich, falls Frontend `localStorage` nutzt). |
| A08 | Data Integrity Failures | **OK** | Hash-Chain DomainEvents (SHA-256, Genesis-Pattern), GoBD-Modell mit CHECK-Constraint (`gobd.py:181`), Optimistic Locking via Mixin. CSRF Double-Submit-Cookie aktiv (`csrf.py`). |
| A09 | Logging/Monitoring | **OK** | `structlog`, AuditLog mit IP/UA/method/path, `safe_error_log` zur PII-Maskierung, Prometheus-Metriken vorhanden, Redaktion in `safe_errors.py`. |
| A10 | SSRF | **NOT_AUDITED** | Nicht explizit gesucht; Email-Import + Slack/Teams-Integrationen sind potenzielle Vektoren - separat pruefen. |

---

## Auth-Flow Detail

| Aspekt | Befund | Datei:Zeile |
|--------|--------|-------------|
| JWT-Erzeugung | HS256 (`settings.ALGORITHM`), 32-byte jti, exp+iat | `core/security_auth.py:370-409` |
| Access-Token TTL | **15 Minuten** (gut) | `core/config.py:94` |
| Refresh-Token TTL | **7 Tage** | `core/config.py:95` |
| Cookie-Setting | CSRF-Token: `httponly=False` (notwendig fuer JS-Read), `samesite=strict`, generiert via Double-Submit-Pattern | `middleware/csrf.py:88, 111, 281` |
| Access-Token-Cookie | **Nicht implementiert** - Token kommt als JSON-Body | `api/v1/auth.py:166` |
| Portal-Auth (separat) | TTL 30min/7d, eigene Konstanten | `services/portal/portal_auth_service.py:29-30` (**Inkonsistenz** mit Haupt-Auth) |
| 2FA | TOTP RFC 6238, 6 Digits, 30s Interval, 8 Backup-Codes (SHA-256), QR-Code-Setup | `core/totp.py:53-59` |

---

## Kritische Findings

### Top-3 Staerken

1. **Hash-Chain fuer Audit/Domain-Events** (`event_store.py:507-513`): Saubere SHA-256 Verkettung mit Genesis-Hash, kanonisches JSON (`sort_keys=True, separators=(",", ":")`), GoBD-konform via DB-CHECK-Constraint.
2. **PostgreSQL Row-Level Security aktiviert** (`alembic/025_add_rls_policies.py`): Defense-in-Depth fuer Multi-Tenancy via `SET app.current_company_id` (`db/session.py:217`). Auch bei Application-Bypass greift DB-Layer.
3. **Field-Encryption mit AAD** (`field_encryption_service.py:85-87`): Whitelist-Validierung gegen SQL-Injection bei JSONB-Spaltennamen, AAD pro Feld - verhindert Cross-Field-Substitution.

### Top-5 Luecken (PILOT-BLOCKER & schwerwiegend)

1. **JWT in Response-Body statt httpOnly-Cookie** (`api/v1/auth.py:166`)
   - Doku in `api/v1/README.md:13` behauptet "JWT Bearer Token (httpOnly Cookie)" - **Code widerlegt das**.
   - Wenn Frontend in `localStorage` ablegt: jeder XSS = sofortiger Token-Diebstahl. Mit 15min Access-Token zwar limitiert, aber Refresh-Token ueber 7 Tage extrahierbar.
   - **Fix**: `response.set_cookie("access_token", ..., httponly=True, secure=True, samesite="strict")` im Login-Endpoint. Pflicht vor Pilot.

2. **CSP enthaelt `unsafe-inline`** (`nginx/snippets/security-headers.conf:19`)
   - `script-src 'self' 'unsafe-inline'` macht CSP gegen XSS weitgehend wirkungslos.
   - 8 Stellen mit `dangerouslySetInnerHTML` (alle DOMPurify-gewrappt - gut), aber bei `unsafe-inline` reicht ein vergessener Sanitize.
   - **Fix**: Nonce-/Hash-basierte CSP, Inline-Scripts ausbauen.

3. **`python-jose==3.3.0` vulnerable** (`requirements.txt`)
   - CVE-2024-33664 (algorithm confusion bei JWE), Library wird nicht mehr aktiv gepflegt.
   - **Fix**: Migration zu `pyjwt[crypto]` (bereits dependency `PyJWT>=2.8.0` vorhanden) oder `authlib`. Pflicht.

4. **Login-Rate-Limit zu schwach** (`api/v1/auth.py:93`: `10/minute`)
   - 10 Versuche/Minute = 14400/Tag pro IP. Credential-Stuffing trivial.
   - Kein Account-Lockout-Code sichtbar (nur `login_blocked_session_limit` als Audit-Action - das ist Session-Concurrency, nicht Brute-Force-Lockout).
   - **Fix**: 5/15min IP + 5/Stunde pro Username + Exponential Backoff + Captcha nach 3 Fehlversuchen.

5. **`training_migration_service.py:223` rohes f-string SQL ohne `text()`**
   - `cursor = conn.execute(f"SELECT * FROM {table_name}")` - der Kommentar in Zeile 222 sagt "gleiche Sicherheit" wie `text(f"...")`, das ist faktisch falsch ohne Whitelist. `table_name` Quelle pruefen. Bei User-Input = SQLi. Tabellenname-Whitelist ergaenzen.
   - Dazu: 6 weitere `f"... {column_name} ..."` in `field_encryption_service.py` haben zwar Whitelist (`_validate_field`), aber falls dort jemals neuer Spaltentyp ohne Validierung ergaenzt wird = SQLi.

### Weitere bemerkenswerte Punkte

- **Multi-Tenancy**: 100+ Stellen mit `company_id ==` Filter pro Service. Risiko durch Vergessen sehr hoch. Empfehlung: SQLAlchemy-Event `before_compile` mit Auto-Filter, oder striktes Repository-Pattern. RLS fangt es ab - aber nur wenn `app.current_company_id` korrekt gesetzt ist (Middleware `company_context.py:399`).
- **Portal-Auth-Konstanten**: `portal_auth_service.py:29-30` definiert eigene 30min/7d - sollte `settings.ACCESS_TOKEN_EXPIRE_MINUTES` referenzieren.
- **YARA-Rules**: 1 Datei (`security/yara_rules/document_malware.yar`) - sehr duenn. ClamAV ist Hauptverteidigung, ok.
- **AuditLog Immutability**: Felder `sequence_number`, `integrity_hash`, `previous_hash` sind alle **nullable** (`models.py:889-893`). DB-Trigger gegen UPDATE/DELETE im Code nicht sichtbar - Migration 017 referenziert, aber Existenz im Repo nicht verifiziert.
- **Secrets-History**: `git log -S"password="` zeigt nur Code-Refactor-Commits ("feat(all): wire batches", etc.), keine sichtbaren Plain-Text-Secrets. Stichprobe ok, kein systematisches `truffleHog`/`gitleaks` gelaufen.
- **CSRF-Exempt-Paths**: Liste in `csrf.py:45` pruefen - Login muss exempt sein, ansonsten kein Problem.
- **HSTS**: `max-age=31536000; includeSubDomains; preload` - ok, aber zwei nginx-configs (Snippet vs `ablage-system.conf:253`) haben **abweichende Werte** (snippets hat preload, conf.d nicht). Konsolidieren.

---

## Bewertung: Security Pilot-Readiness

**Note: 6 / 10**

Begruendung: Solides Fundament (RLS, Hash-Chain, 2FA, CSRF, ClamAV, bcrypt cost=12, Field-Encryption mit AAD), aber **drei Pilot-Blocker**: JWT-Bearer-im-Body, vulnerable `python-jose`, CSP mit `unsafe-inline`. Plus zu schwacher Login-Rate-Limit. Die Architektur ist Enterprise-tauglich gedacht, die Umsetzung weist aber inkonsistente Stellen auf, die ein gezielter Angreifer in <1 Tag findet (Doku/Code-Drift, Auth-Inkonsistenzen Portal vs Haupt, JSONB-SQL-f-strings).

Mit 1-2 Wochen fokussiertem Hardening (Top-5 Luecken) realistisch auf 8/10.

---

## Empfehlung Pentest vor Pilot

**JA - extern, mind. Web-App-Pentest (5 PT) + Code-Review-Walkthrough (2 PT).**

Begruendung:
- Multi-Tenant-Isolation (200+ manuelle `company_id`-Filter) braucht Black-Box-Validierung. Keine Code-Inspektion findet alle vergessenen Filter.
- DSGVO-relevante Daten + Lexware-PII (Kundennummern, IBANs) - Haftungsrisiko bei Tenant-Bleed.
- `python-jose` CVE muss vor Pentest gefixt sein (sonst trivialer Finding).
- AuditLog-Immutability (DB-Trigger) muss vor Pentest verifiziert sein - sonst GoBD-Compliance unklar.

**Vor-Pentest-Checkliste**:
1. JWT auf httpOnly-Cookie umstellen, `localStorage`-Nutzung im Frontend pruefen.
2. `python-jose` -> `pyjwt` migrieren, `passlib` evaluieren.
3. CSP ohne `unsafe-inline`, Inline-Scripts in Frontend ausbauen.
4. Login-Rate-Limit verschaerfen + Account-Lockout implementieren.
5. AuditLog-DB-Trigger gegen UPDATE/DELETE in einer Migration explizit verifizieren.
6. `pip-audit` + `bandit` + `gitleaks` in CI verankern.
7. Portal-Auth-Konstanten konsolidieren mit Haupt-Auth.
8. `training_migration_service.py:223` Tabellenname-Whitelist ergaenzen.

Erst dann externer Pentest. Pilot-Start nach Pentest-Fix-Run.

---

**Wortzahl**: ca. 1380.
