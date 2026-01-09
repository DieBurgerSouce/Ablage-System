# Security Testing Guide

> **Enterprise Document Processing Platform - Security Testing Strategie**
> Version: 1.0
> Status: Production-Ready
> Letzte Aktualisierung: Januar 2026

---

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [Security Testing Kategorien](#security-testing-kategorien)
3. [OWASP Top 10 Coverage](#owasp-top-10-coverage)
4. [Authentication Testing](#authentication-testing)
5. [Authorization Testing (RBAC)](#authorization-testing-rbac)
6. [Input Validation Testing](#input-validation-testing)
7. [Security Headers Testing](#security-headers-testing)
8. [CSRF Protection Testing](#csrf-protection-testing)
9. [Rate Limiting Testing](#rate-limiting-testing)
10. [Test-Fixtures und Utilities](#test-fixtures-und-utilities)
11. [CI/CD Integration](#cicd-integration)
12. [Security Test Checkliste](#security-test-checkliste)

---

## Übersicht

Das Ablage-System implementiert eine umfassende Security-Testing-Strategie, die alle kritischen Sicherheitsaspekte abdeckt. Dieser Guide beschreibt die Test-Kategorien, Best Practices und konkrete Implementierungsbeispiele.

### Test-Infrastruktur

```
tests/
├── unit/
│   ├── core/
│   │   ├── test_security.py              # JWT, Passwort-Hashing, Blacklist
│   │   ├── test_input_sanitization.py    # XSS, SQL-Injection, Path Traversal
│   │   ├── test_rate_limiting.py         # Rate Limit Tiers, Redis Storage
│   │   └── test_credential_redaction.py  # PII-Filterung in Logs
│   ├── middleware/
│   │   ├── test_csrf.py                  # Double-Submit-Cookie Pattern
│   │   ├── test_security_headers.py      # CSP, HSTS, X-Frame-Options
│   │   └── test_security_headers_extended.py
│   └── api/
│       ├── test_auth.py                  # Login, Logout, Token-Refresh
│       ├── test_auth_2fa.py              # TOTP, Recovery Codes
│       └── test_input_validation_extended.py
├── security/
│   └── test_datev_authorization.py       # RBAC, Authorization Bypass
├── integration/
│   ├── test_rate_limit_e2e.py            # End-to-End Rate Limiting
│   └── test_personal_api_security.py     # Personal-Daten Schutz
└── load/
    └── k6/scenarios/auth_flow.js         # Load-Test für Auth-Endpoints
```

### Verwendete Marker

```python
# pytest.ini oder pyproject.toml
markers =
    security: Security-relevante Tests
    owasp: OWASP Top 10 Tests
    auth: Authentication Tests
    authz: Authorization Tests
    injection: Injection-Attack Tests
    xss: Cross-Site Scripting Tests
    csrf: CSRF Protection Tests
```

---

## Security Testing Kategorien

### Kategorie-Matrix

| Kategorie | Dateien | Tests | Kritikalität |
|-----------|---------|-------|--------------|
| Authentication | 6 | ~80 | KRITISCH |
| Authorization | 4 | ~45 | KRITISCH |
| Input Validation | 3 | ~120 | HOCH |
| Security Headers | 2 | ~35 | MITTEL |
| CSRF Protection | 1 | ~50 | HOCH |
| Rate Limiting | 2 | ~40 | HOCH |
| **Gesamt** | **18** | **~370** | - |

### Test-Befehle

```bash
# Alle Security-Tests ausführen
pytest -m security -v

# OWASP-spezifische Tests
pytest -m owasp -v

# Authentication Tests
pytest tests/unit/core/test_security.py tests/unit/api/test_auth*.py -v

# Nur Authorization Tests
pytest -m authz -v

# Input Validation Tests
pytest tests/unit/core/test_input_sanitization.py -v
```

---

## OWASP Top 10 Coverage

### A01:2021 – Broken Access Control

**Test-Datei:** `tests/security/test_datev_authorization.py`

```python
@pytest.mark.asyncio
@pytest.mark.security
@pytest.mark.owasp
async def test_cannot_delete_other_users_vendor_mapping(
    self, mock_user_a, mock_user_b, mock_config_for_user_a, mock_vendor_mapping
):
    """
    SECURITY TEST: User B darf Vendor-Mapping von User A NICHT loeschen.

    OWASP A01:2021 - Broken Access Control
    Vor dem Fix konnte jeder authentifizierte User beliebige Vendor-Mappings
    loeschen, wenn er die UUIDs kannte/erriet.
    """
    from app.api.v1.datev import delete_vendor_mapping
    from fastapi import HTTPException

    mock_db = AsyncMock(spec=AsyncSession)

    # Config-Query: Gibt None zurueck, weil User B nicht der Besitzer ist
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = config_result

    # User B versucht Mapping von User A zu loeschen
    with pytest.raises(HTTPException) as exc_info:
        await delete_vendor_mapping(
            config_id=mock_config_for_user_a.id,
            mapping_id=mock_vendor_mapping.id,
            db=mock_db,
            current_user=mock_user_b,  # ANGREIFER
        )

    # Erwartung: 404 (nicht 403, um keine Information preiszugeben)
    assert exc_info.value.status_code == 404
    assert "Konfiguration nicht gefunden" in exc_info.value.detail

    # WICHTIG: delete() sollte NICHT aufgerufen worden sein
    mock_db.delete.assert_not_called()
```

### A02:2021 – Cryptographic Failures

**Test-Datei:** `tests/unit/core/test_security.py`

```python
class TestPasswordValidation:
    """Tests für Passwort-Validierung (OWASP A02)."""

    def test_password_too_short(self):
        """Passwort unter 8 Zeichen muss fehlschlagen."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("Short1!")
        assert is_valid is False
        assert "8" in error or "Zeichen" in error

    def test_password_missing_complexity(self):
        """Passwort muss Komplexitätsanforderungen erfüllen."""
        is_valid, error = validate_password_strength("lowercase1!")
        assert is_valid is False
        assert "Großbuchstaben" in error

    def test_bcrypt_cost_factor(self):
        """Bcrypt muss mit Cost Factor 12 hashen."""
        from app.core.security import get_password_hash, BCRYPT_COST_FACTOR

        assert BCRYPT_COST_FACTOR >= 12

        hash_result = get_password_hash("TestPassword123!")
        # Bcrypt-Hash-Format: $2b$12$...
        assert "$2b$12$" in hash_result or "$2a$12$" in hash_result
```

### A03:2021 – Injection

**Test-Datei:** `tests/unit/core/test_input_sanitization.py`

```python
class TestSQLInjectionCheck:
    """Tests für SQL-Injection-Erkennung (OWASP A03)."""

    def test_union_select_detected(self):
        """UNION SELECT wird erkannt."""
        is_safe, pattern = check_sql_injection_patterns("1 UNION SELECT * FROM users")
        assert not is_safe
        assert "UNION" in pattern or "SELECT" in pattern

    def test_drop_table_detected(self):
        """DROP TABLE wird erkannt."""
        is_safe, pattern = check_sql_injection_patterns("1; DROP TABLE users")
        assert not is_safe

    def test_exec_injection_detected(self):
        """SQL-EXEC-Injection wird erkannt."""
        is_safe, pattern = check_sql_injection_patterns("EXEC sp_executesql")
        assert not is_safe


class TestEnforceSQLSafe:
    """Defense-in-Depth SQL-Schutz."""

    def test_union_injection_blocked(self):
        """UNION Injection wird blockiert."""
        with pytest.raises(SQLInjectionError) as exc_info:
            enforce_sql_safe("1 UNION SELECT * FROM users")
        assert exc_info.value.detected_pattern == "UNION"

    def test_german_umlauts_allowed(self):
        """Deutsche Umlaute werden erlaubt."""
        result = enforce_sql_safe("Rechnungsübersicht für März")
        assert "ü" in result
        assert "ä" in result
```

### A05:2021 – Security Misconfiguration

**Test-Datei:** `tests/unit/core/test_security.py`

```python
class TestSecretKeyValidation:
    """Tests für SECRET_KEY Validierung (OWASP A05)."""

    def test_empty_secret_key_in_production_raises_error(self):
        """Leerer SECRET_KEY in Production muss ValueError auslösen."""
        with patch.dict(os.environ, {"SECRET_KEY": "", "DEBUG": "false"}):
            with pytest.raises((ValueError, ValidationError)):
                # Settings ohne .env für Isolation
                class IsolatedSettings(BaseSettings):
                    SECRET_KEY: str = ""
                    DEBUG: bool = False

                    @model_validator(mode='after')
                    def validate_settings(self):
                        if not self.SECRET_KEY and not self.DEBUG:
                            raise ValueError(
                                "SECRET_KEY ist nicht gesetzt! "
                                "In Production muss SECRET_KEY via Umgebungsvariable definiert werden."
                            )
                        return self

                IsolatedSettings(_env_file=None)


class TestCorsValidation:
    """Tests für CORS Origins Validierung."""

    def test_wildcard_in_production_raises_error(self):
        """CORS_ORIGINS='*' in Production muss fehlschlagen."""
        def validate_cors_origins(origins, allow_credentials, debug_mode):
            has_wildcard = "*" in origins
            if has_wildcard and allow_credentials:
                raise ValueError("CORS_ORIGINS='*' nicht erlaubt mit Credentials!")
            if has_wildcard and not debug_mode:
                raise ValueError("CORS_ORIGINS='*' in Production nicht erlaubt!")

        with pytest.raises(ValueError):
            validate_cors_origins(origins=["*"], allow_credentials=False, debug_mode=False)

    def test_localhost_in_production_raises_error(self):
        """localhost in CORS_ORIGINS in Production muss fehlschlagen."""
        localhost_origins = ["http://localhost:3000"]

        def validate_localhost(origins, debug_mode):
            localhost_patterns = ("localhost", "127.0.0.1", "::1")
            has_localhost = any(
                any(p in o.lower() for p in localhost_patterns) for o in origins
            )
            if has_localhost and not debug_mode:
                raise ValueError(f"localhost in Production nicht erlaubt!")

        with pytest.raises(ValueError):
            validate_localhost(localhost_origins, debug_mode=False)
```

### A07:2021 – Identification and Authentication Failures

**Test-Datei:** `tests/unit/core/test_security.py`

```python
class TestTokenCreation:
    """Tests für Token-Erstellung (OWASP A07)."""

    def test_access_token_contains_jti(self):
        """Access Token muss JTI (unique ID) für Blacklisting enthalten."""
        from app.core.security import create_access_token
        from jose import jwt

        token = create_access_token({"sub": "user123"})
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_token_type_prevents_misuse(self):
        """Token-Typ verhindert Refresh-Token-Missbrauch."""
        from app.core.security import create_access_token, create_refresh_token

        access = create_access_token({"sub": "user123"})
        refresh = create_refresh_token({"sub": "user123"})

        access_payload = jwt.decode(access, secret_key, algorithms=[settings.ALGORITHM])
        refresh_payload = jwt.decode(refresh, secret_key, algorithms=[settings.ALGORITHM])

        assert access_payload["type"] == "access"
        assert refresh_payload["type"] == "refresh"


class TestTokenBlacklisting:
    """Tests für Token-Blacklisting (Fail-Closed Mode)."""

    @pytest.mark.asyncio
    async def test_blacklist_token_fails_closed_on_redis_unavailable(self):
        """Token-Blacklisting gibt HTTPException im fail-closed Modus."""
        from app.core import security as security_module
        from fastapi import HTTPException

        # Simuliere Redis-Ausfall
        security_module._redis_available = False
        security_module._redis_client = None

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        jti = "test-jti-" + secrets.token_hex(8)

        # Im fail-closed Modus: HTTPException 503
        with pytest.raises(HTTPException) as exc_info:
            await security_module.blacklist_token(jti, expires)

        assert exc_info.value.status_code == 503
        # Deutsche Fehlermeldung
        assert "sicherheit" in exc_info.value.detail.lower() or "verfügbar" in exc_info.value.detail.lower()
```

---

## Authentication Testing

### JWT Token Tests

```python
# tests/unit/api/test_auth.py

class TestJWTAuthentication:
    """Tests für JWT-basierte Authentifizierung."""

    @pytest.mark.asyncio
    async def test_login_returns_token_pair(self, test_client, test_user):
        """Login gibt Access- und Refresh-Token zurück."""
        response = await test_client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "ValidPassword123!"
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_access_token_expires(self, test_client, test_user_token):
        """Access-Token läuft nach konfigurierter Zeit ab."""
        # Manipuliere Token-Ablaufzeit
        from jose import jwt
        from datetime import datetime, timezone, timedelta

        expired_payload = {
            "sub": test_user.id,
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "type": "access",
            "jti": secrets.token_urlsafe(32)
        }
        expired_token = jwt.encode(expired_payload, settings.SECRET_KEY.get_secret_value())

        response = await test_client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
        assert "abgelaufen" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token_issues_new_access_token(self, test_client, test_user_tokens):
        """Refresh-Token gibt neuen Access-Token zurück."""
        response = await test_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": test_user_tokens["refresh_token"]}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        # Neuer Token ist anders als alter
        assert data["access_token"] != test_user_tokens["access_token"]
```

### 2FA/TOTP Testing

```python
# tests/unit/api/test_auth_2fa.py

class TestTOTPAuthentication:
    """Tests für TOTP-basierte 2FA."""

    @pytest.mark.asyncio
    async def test_2fa_setup_returns_secret_and_qr(self, test_client, authenticated_user):
        """2FA-Setup gibt Secret und QR-Code zurück."""
        response = await test_client.post(
            "/api/v1/auth/2fa/setup",
            headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_code" in data  # Base64-encoded
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10

    @pytest.mark.asyncio
    async def test_2fa_replay_protection(self, test_client, user_with_2fa):
        """TOTP-Code kann nur einmal verwendet werden."""
        import pyotp

        totp = pyotp.TOTP(user_with_2fa["totp_secret"])
        code = totp.now()

        # Erste Verwendung erfolgreich
        response1 = await test_client.post("/api/v1/auth/2fa/verify", json={
            "temp_token": user_with_2fa["temp_token"],
            "code": code
        })
        assert response1.status_code == 200

        # Zweite Verwendung fehlgeschlagen (Replay-Schutz)
        response2 = await test_client.post("/api/v1/auth/2fa/verify", json={
            "temp_token": user_with_2fa["temp_token"],
            "code": code
        })
        assert response2.status_code == 401
        assert "bereits verwendet" in response2.json()["detail"].lower()
```

---

## Authorization Testing (RBAC)

### Resource Ownership Tests

```python
# tests/security/test_datev_authorization.py

class TestResourceOwnership:
    """Tests für Resource-Ownership-basierte Authorization."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_cannot_access_other_users_config(
        self, mock_user_a, mock_user_b, mock_config_for_user_a
    ):
        """User B darf Config von User A NICHT laden."""
        from app.services.datev.export_service import DATEVExportService

        service = DATEVExportService()
        mock_db = AsyncMock(spec=AsyncSession)

        # Query gibt None zurück, weil user_id nicht matcht
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        config = await service._get_config(
            db=mock_db,
            config_id=mock_config_for_user_a.id,
            user_id=mock_user_b.id,  # ANGREIFER
        )

        assert config is None

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_uuid_collision_does_not_bypass_auth(self, mock_user_a, mock_user_b):
        """UUID-Kollision umgeht Authorization nicht."""
        service = DATEVExportService()

        # Beide User haben "zufällig" gleiche config_id
        shared_config_id = uuid.uuid4()

        mock_db = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        # Query prüft BEIDE: config_id UND user_id
        config = await service._get_config(
            db=mock_db,
            config_id=shared_config_id,
            user_id=mock_user_b.id,
        )

        assert config is None
```

### Role-Based Access Control

```python
class TestRBACPermissions:
    """Tests für rollenbasierte Berechtigungen."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_admin_can_access_admin_endpoints(self, admin_user, test_client):
        """Admin kann Admin-Endpoints aufrufen."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers=admin_user["headers"]
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_regular_user_cannot_access_admin_endpoints(self, regular_user, test_client):
        """Normaler User kann Admin-Endpoints NICHT aufrufen."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers=regular_user["headers"]
        )
        assert response.status_code == 403
        assert "Berechtigung" in response.json()["detail"]
```

---

## Input Validation Testing

### XSS Prevention

```python
# tests/unit/core/test_input_sanitization.py

class TestXSSPrevention:
    """Tests für XSS-Prävention."""

    def test_script_tags_removed(self):
        """XSS Script-Tags werden entfernt."""
        query = '<script>alert("xss")</script>Test'
        result, warnings = sanitize_search_query(query)

        assert "<script>" not in result
        assert "</script>" not in result
        assert any("HTML" in w for w in warnings)

    def test_javascript_injection_blocked(self):
        """JavaScript-Injection wird blockiert."""
        query = "javascript:alert(1)"
        result, warnings = sanitize_search_query(query)

        assert "javascript:" not in result.lower()

    def test_event_handler_blocked(self):
        """Event-Handler-Attribute werden blockiert."""
        query = 'onclick="alert(1)" Rechnung'
        result, warnings = sanitize_search_query(query)

        assert "onclick" not in result.lower()

    def test_html_content_sanitization(self):
        """HTML-Content wird sicher bereinigt."""
        html = "<p>Test</p><script>alert('xss')</script>"
        result = sanitize_html_content(html)

        assert "<script>" not in result
        assert "alert" not in result
```

### Path Traversal Prevention

```python
class TestPathTraversal:
    """Tests für Path-Traversal-Prävention."""

    def test_path_traversal_blocked(self):
        """Path-Traversal wird blockiert."""
        filename = "../../../etc/passwd"
        result = sanitize_filename(filename)

        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_null_byte_removed(self):
        """Null-Bytes werden entfernt."""
        filename = "file\x00.pdf"
        result = sanitize_filename(filename)

        assert "\x00" not in result

    def test_windows_forbidden_chars_replaced(self):
        """Windows-verbotene Zeichen werden ersetzt."""
        filename = 'file<>:"|?*.pdf'
        result = sanitize_filename(filename)

        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
```

### SSRF Protection

```python
class TestSSRFProtection:
    """Tests für SSRF-Schutz."""

    def test_localhost_blocked(self):
        """localhost URLs werden blockiert."""
        from app.core.security import validate_url_for_ssrf

        is_valid, error = validate_url_for_ssrf("http://localhost:8080/internal")
        assert not is_valid
        assert "nicht erlaubt" in error

    def test_internal_ip_blocked(self):
        """Interne IP-Bereiche werden blockiert."""
        internal_ips = [
            "http://10.0.0.1/admin",
            "http://172.16.0.1/secrets",
            "http://192.168.1.1/config",
            "http://169.254.169.254/latest/meta-data/",  # AWS Metadata!
        ]

        for url in internal_ips:
            is_valid, error = validate_url_for_ssrf(url)
            assert not is_valid, f"URL sollte blockiert sein: {url}"

    def test_external_url_allowed(self):
        """Externe URLs werden erlaubt."""
        is_valid, error = validate_url_for_ssrf("https://api.example.com/webhook")
        assert is_valid
```

---

## Security Headers Testing

### Header Validierung

```python
# tests/unit/middleware/test_security_headers.py

class TestSecurityHeadersMiddleware:
    """Tests für Security Headers Middleware."""

    def test_x_content_type_options_header(self, client):
        """Response sollte X-Content-Type-Options: nosniff haben."""
        response = client.get("/test")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_header(self, client):
        """Response sollte X-Frame-Options: DENY haben (Clickjacking-Schutz)."""
        response = client.get("/test")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection_header(self, client):
        """Response sollte X-XSS-Protection Header haben."""
        response = client.get("/test")
        xss_header = response.headers.get("X-XSS-Protection")

        assert xss_header is not None
        assert "1" in xss_header
        assert "mode=block" in xss_header

    def test_content_security_policy_header(self, client):
        """Response sollte CSP Header haben."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert csp is not None
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "frame-ancestors 'none'" in csp  # Clickjacking-Schutz

    def test_permissions_policy_header(self, client):
        """Response sollte Permissions-Policy Header haben."""
        response = client.get("/test")
        permissions = response.headers.get("Permissions-Policy")

        assert permissions is not None
        assert "camera=()" in permissions
        assert "microphone=()" in permissions
        assert "geolocation=()" in permissions


class TestHSTSConfiguration:
    """Tests für HSTS Header Konfiguration."""

    def test_hsts_disabled_in_debug(self):
        """HSTS sollte in Debug-Modus deaktiviert sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = True

            response = client.get("/test")
            hsts = response.headers.get("Strict-Transport-Security")

            assert hsts is None

    def test_hsts_enabled_in_production(self):
        """HSTS sollte in Production aktiviert sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            response = client.get("/test")
            hsts = response.headers.get("Strict-Transport-Security")

            assert hsts is not None
            assert "max-age=" in hsts
            assert "includeSubDomains" in hsts
```

---

## CSRF Protection Testing

### Double-Submit-Cookie Pattern

```python
# tests/unit/middleware/test_csrf.py

class TestCSRFMiddleware:
    """Tests für CSRF Middleware."""

    def test_get_request_sets_csrf_cookie(self, client):
        """GET-Request setzt CSRF-Cookie."""
        response = client.get("/test")

        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies
        assert len(response.cookies.get(CSRF_COOKIE_NAME)) == 64  # 32 bytes hex

    def test_post_request_fails_without_csrf_token(self, client):
        """POST ohne CSRF-Token schlägt fehl."""
        response = client.post("/test")

        assert response.status_code == 403
        assert "CSRF" in response.json()["nachricht"]

    def test_post_request_succeeds_with_valid_csrf_token(self, client):
        """POST mit gültigem CSRF-Token erfolgreich."""
        # Erst GET um Cookie zu bekommen
        get_response = client.get("/test")
        csrf_token = get_response.cookies.get(CSRF_COOKIE_NAME)

        # POST mit korrektem Token im Header
        response = client.post("/test", headers={CSRF_HEADER_NAME: csrf_token})

        assert response.status_code == 200

    def test_post_succeeds_with_bearer_token_no_csrf(self, client):
        """POST mit Bearer-Token benötigt kein CSRF-Token (API-Clients)."""
        response = client.post(
            "/test",
            headers={"Authorization": "Bearer some_jwt_token"}
        )

        assert response.status_code == 200


class TestCSRFTokenRotation:
    """Tests für CSRF-Token-Rotation."""

    def test_token_rotates_after_successful_post(self, client):
        """Token rotiert nach erfolgreichem POST."""
        get_response = client.get("/test")
        initial_token = get_response.cookies.get(CSRF_COOKIE_NAME)

        post_response = client.post("/test", headers={CSRF_HEADER_NAME: initial_token})
        new_cookie_token = post_response.cookies.get(CSRF_COOKIE_NAME)

        assert post_response.status_code == 200
        assert new_cookie_token != initial_token

    def test_old_token_invalid_after_rotation(self, client):
        """Altes Token nach Rotation ungültig."""
        get_response = client.get("/test")
        initial_token = get_response.cookies.get(CSRF_COOKIE_NAME)

        # Erster POST rotiert Token
        post_response = client.post("/test", headers={CSRF_HEADER_NAME: initial_token})

        # Zweiter POST mit altem Token schlägt fehl
        second_response = client.post(
            "/test",
            headers={CSRF_HEADER_NAME: initial_token},
            cookies={CSRF_COOKIE_NAME: post_response.cookies.get(CSRF_COOKIE_NAME)}
        )

        assert second_response.status_code == 403
```

---

## Rate Limiting Testing

### Rate Limit Tiers

```python
# tests/unit/core/test_rate_limiting.py

class TestRateLimitTier:
    """Tests für Rate Limit Tier-Konfigurationen."""

    def test_login_rate_limit(self):
        """Login hat strenge Rate Limits (Brute-Force-Schutz)."""
        from app.core.rate_limiting import RateLimitTier
        assert RateLimitTier.LOGIN == "5/15minutes"

    def test_register_rate_limit(self):
        """Registration hat strenge Rate Limits."""
        from app.core.rate_limiting import RateLimitTier
        assert RateLimitTier.REGISTER == "3/hour"

    def test_ocr_tier_differentiation(self):
        """OCR hat verschiedene Limits für Free/Premium."""
        from app.core.rate_limiting import RateLimitTier

        # Free Tier
        assert RateLimitTier.OCR_FREE_HOURLY == "10/hour"
        assert RateLimitTier.OCR_FREE_DAILY == "50/day"

        # Premium Tier (10x höher)
        assert RateLimitTier.OCR_PREMIUM_HOURLY == "100/hour"
        assert RateLimitTier.OCR_PREMIUM_DAILY == "1000/day"


class TestIPWhitelist:
    """Tests für IP-Whitelist-Management."""

    def test_localhost_whitelisted_by_default(self, whitelist):
        """localhost ist standardmäßig whitelisted."""
        assert whitelist.is_whitelisted("127.0.0.1") is True
        assert whitelist.is_whitelisted("::1") is True

    def test_unknown_ip_not_whitelisted(self, whitelist):
        """Unbekannte IPs sind nicht whitelisted."""
        assert whitelist.is_whitelisted("8.8.8.8") is False


class TestGermanErrorMessages:
    """Tests für deutsche Rate-Limit-Fehlermeldungen."""

    def test_german_error_response(self, mock_request):
        """Rate-Limit-Fehler sind auf Deutsch."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german

        response = rate_limit_exceeded_handler_german(mock_request, exc)

        assert response.status_code == 429
        # Deutsche Fehlermeldung
        data = response.json()
        assert any(word in str(data).lower() for word in ["anfragen", "limit", "überschritten"])
```

---

## Test-Fixtures und Utilities

### Conftest.py Fixtures

```python
# tests/conftest.py

import pytest
import secrets
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

@pytest.fixture
def mock_user_a():
    """Mock User A (Ressourcen-Besitzer)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user_a@test.de"
    user.is_active = True
    user.role = "user"
    return user

@pytest.fixture
def mock_user_b():
    """Mock User B (potenzieller Angreifer)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user_b@test.de"
    user.is_active = True
    user.role = "user"
    return user

@pytest.fixture
def admin_user():
    """Mock Admin User."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@test.de"
    user.is_active = True
    user.role = "admin"
    return user

@pytest.fixture
def mock_db():
    """Mock AsyncSession für Tests."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.delete = AsyncMock()
    return db

@pytest.fixture
def app_with_security():
    """FastAPI-App mit allen Security-Middlewares."""
    app = FastAPI()

    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=False, enable_csp=True)
    app.add_middleware(CSRFMiddleware, enabled=True, cookie_secure=False)

    @app.get("/test")
    async def test_get():
        return {"message": "ok"}

    @app.post("/test")
    async def test_post():
        return {"message": "created"}

    return app

@pytest.fixture
def security_client(app_with_security):
    """Test-Client mit Security-Middlewares."""
    return TestClient(app_with_security)
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/security-tests.yml
name: Security Tests

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  security-tests:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7
        ports:
          - 6379:6379
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run Security Tests
        run: |
          pytest -m security --tb=short -v
        env:
          SECRET_KEY: ${{ secrets.TEST_SECRET_KEY }}
          REDIS_URL: redis://localhost:6379

      - name: Run OWASP Tests
        run: |
          pytest -m owasp --tb=short -v

      - name: Upload Coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: security
```

---

## Security Test Checkliste

### Pre-Commit Checkliste

- [ ] Alle Security-Tests bestanden (`pytest -m security`)
- [ ] Keine hartkodierten Secrets im Code
- [ ] Input-Validierung für alle User-Inputs
- [ ] Authorization für alle geschützten Endpoints
- [ ] Rate-Limiting für sensitive Endpoints
- [ ] CSRF-Schutz für state-changing Endpoints

### PR-Review Checkliste

- [ ] OWASP Top 10 Vulnerabilities geprüft
- [ ] Neue Endpoints haben Authorization-Tests
- [ ] Neue Input-Felder haben Sanitization-Tests
- [ ] Error-Messages geben keine sensiblen Infos preis
- [ ] Logging enthält keine PII/Credentials

### Release Checkliste

- [ ] Security-Test-Coverage > 90%
- [ ] Keine kritischen Security-Findings
- [ ] HSTS aktiviert (Production)
- [ ] CSP konfiguriert
- [ ] Rate-Limits für alle Tiers definiert
- [ ] Token-Blacklist Redis-basiert

---

## Referenzen

- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [ASVS 4.0](https://owasp.org/www-project-application-security-verification-standard/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

---

*Dokumentation generiert für Ablage-System Enterprise Platform*
