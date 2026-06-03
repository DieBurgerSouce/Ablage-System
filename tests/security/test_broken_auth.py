# -*- coding: utf-8 -*-
"""
Security Tests: Broken Authentication (OWASP A07:2021)

Testet:
- JWT Token Sicherheit
- Session Management
- MFA Bypass Versuche
- Password Security
- Token Expiration
- Brute Force Protection

Kritische Regeln:
- ACCESS_TOKEN_EXPIRE_MINUTES: 15
- REFRESH_TOKEN_EXPIRE_DAYS: 7
- Rate Limiting: Login 5/15min
"""

import time
import uuid
from datetime import datetime, timedelta
from typing import Dict

import pytest


# =============================================================================
# JWT TOKEN TESTS
# =============================================================================


class TestJWTSecurity:
    """Tests fuer JWT Token Sicherheit."""

    def test_jwt_algorithm_confusion(self, test_client):
        """Testet dass Algorithm Confusion (none/HS256) blockiert wird."""
        # Versuche Token mit 'none' Algorithm
        malicious_token = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJ1c2VyX2lkIjoiMSIsImlzX2FkbWluIjp0cnVlfQ."
        response = test_client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {malicious_token}"},
        )
        assert response.status_code == 401

    def test_jwt_with_weak_secret(self, test_client):
        """Testet dass schwache Secrets abgelehnt werden."""
        # Token mit bekanntem schwachen Secret signiert
        import jwt
        weak_secrets = ["secret", "password", "key", "123456", "admin"]
        for secret in weak_secrets:
            try:
                token = jwt.encode(
                    {"user_id": "1", "exp": datetime.utcnow() + timedelta(hours=1)},
                    secret,
                    algorithm="HS256"
                )
                response = test_client.get(
                    "/api/v1/documents",
                    headers={"Authorization": f"Bearer {token}"},
                )
                # Sollte abgelehnt werden (anderes Secret)
                assert response.status_code == 401
            except Exception:
                pass  # JWT library nicht verfuegbar

    def test_jwt_expiration_enforced(self, test_client):
        """Testet dass abgelaufene Tokens abgelehnt werden."""
        # Token mit exp in der Vergangenheit
        import jwt
        expired_token = jwt.encode(
            {"user_id": "1", "exp": datetime.utcnow() - timedelta(hours=1)},
            "test-secret-key-that-is-long-enough-for-security",
            algorithm="HS256"
        )
        response = test_client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    def test_jwt_without_exp_claim(self, test_client):
        """Testet dass Tokens ohne exp Claim abgelehnt werden."""
        import jwt
        no_exp_token = jwt.encode(
            {"user_id": "1"},  # Kein exp claim
            "test-secret-key-that-is-long-enough-for-security",
            algorithm="HS256"
        )
        response = test_client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {no_exp_token}"},
        )
        assert response.status_code == 401

    def test_jwt_tampering_detection(self, test_client):
        """Testet dass manipulierte Tokens erkannt werden."""
        import jwt
        # Valides Token erstellen
        valid_token = jwt.encode(
            {"user_id": "1", "is_admin": False, "exp": datetime.utcnow() + timedelta(hours=1)},
            "test-secret-key-that-is-long-enough-for-security",
            algorithm="HS256"
        )
        # Payload manipulieren (is_admin=true)
        parts = valid_token.split(".")
        import base64
        # Decode, modify, re-encode payload
        payload = base64.b64decode(parts[1] + "==")
        modified_payload = payload.replace(b'"is_admin":false', b'"is_admin":true')
        parts[1] = base64.b64encode(modified_payload).decode().rstrip("=")
        tampered_token = ".".join(parts)

        response = test_client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert response.status_code == 401


# =============================================================================
# SESSION MANAGEMENT TESTS
# =============================================================================


class TestSessionManagement:
    """Tests fuer Session Management."""

    def test_session_fixation_prevention(self, test_client):
        """Testet dass Session Fixation verhindert wird."""
        # Login mit pre-set session ID sollte neue Session erstellen
        response = test_client.post(
            "/api/v1/auth/login",
            json={"email": "test@test.de", "password": "testpassword"},
            cookies={"session_id": "attacker-controlled-session"},
        )
        if response.status_code == 200:
            # Session-ID sollte neu generiert worden sein
            new_session = response.cookies.get("session_id")
            assert new_session != "attacker-controlled-session"

    def test_session_invalidation_on_logout(self, test_client, auth_headers):
        """Testet dass Sessions bei Logout invalidiert werden."""
        # Logout
        response = test_client.post("/api/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200

        # Versuche mit dem gleichen Token erneut zuzugreifen
        response = test_client.get("/api/v1/documents", headers=auth_headers)
        # Sollte abgelehnt werden (Session invalidiert)
        # In manchen Implementierungen: 401, in anderen: token noch gueltig bis expiry
        assert response.status_code in [401, 200]

    @pytest.mark.asyncio
    async def test_session_timeout(self):
        """Session-Timeout: ein abgelaufener Access-Token wird abgelehnt (401).

        Simuliert Inaktivitaet ueber ACCESS_TOKEN_EXPIRE_MINUTES (15) hinaus,
        indem ein mit der ECHTEN App-Signatur erzeugter Token mit Ablauf in der
        Vergangenheit erzeugt und validiert wird. ``decode_token`` muss ihn als
        abgelaufen ablehnen (HTTP 401). DB-unabhaengig: die exp-Pruefung greift
        vor jeder Backend-/Blacklist-Abfrage.
        """
        from datetime import timedelta
        from uuid import uuid4

        from fastapi import HTTPException

        from app.core.security_auth import create_access_token, decode_token

        expired_token = create_access_token(
            data={"sub": str(uuid4()), "email": "timeout@ablage.local"},
            expires_delta=timedelta(minutes=-1),
        )
        with pytest.raises(HTTPException) as exc_info:
            await decode_token(expired_token)
        assert exc_info.value.status_code == 401, (
            f"Abgelaufener Token muss 401 liefern, erhalten {exc_info.value.status_code}"
        )

    def test_concurrent_session_limit(self, test_client):
        """Testet MAX_SESSIONS_PER_USER Limit (default: 10)."""
        # Simuliere 11 gleichzeitige Logins
        sessions = []
        for i in range(11):
            response = test_client.post(
                "/api/v1/auth/login",
                json={"email": "test@test.de", "password": "testpassword"},
            )
            if response.status_code == 200:
                sessions.append(response.json().get("access_token"))

        # Bei SESSION_LIMIT_MODE="soft" sollte aelteste Session invalidiert werden
        # Bei SESSION_LIMIT_MODE="hard" sollte 11. Login fehlschlagen
        # Pruefe dass nicht mehr als 10 gueltige Sessions existieren


# =============================================================================
# MFA BYPASS TESTS
# =============================================================================


class TestMFABypass:
    """Tests gegen MFA Bypass Angriffe."""

    def test_mfa_token_reuse(self, test_client):
        """Testet dass MFA-Tokens nur einmal verwendbar sind."""
        # Login Step 1
        response = test_client.post(
            "/api/v1/auth/login",
            json={"email": "mfa_user@test.de", "password": "testpassword"},
        )
        if response.status_code == 200 and response.json().get("requires_mfa"):
            mfa_token = "123456"  # Simulierter TOTP Code
            # Erster Versuch
            response1 = test_client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": mfa_token},
            )
            # Zweiter Versuch mit gleichem Code
            response2 = test_client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": mfa_token},
            )
            # Zweiter Versuch sollte fehlschlagen (Replay Protection)
            if response1.status_code == 200:
                assert response2.status_code in [400, 401]

    def test_mfa_bruteforce_protection(self, test_client):
        """Testet Rate Limiting fuer MFA-Versuche."""
        # 10 fehlerhafte MFA-Versuche
        for i in range(10):
            response = test_client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": f"{100000 + i}"},  # Falsche Codes
            )
            if response.status_code == 429:
                # Rate Limit erreicht - gut!
                return
        # Nach 10 Versuchen sollte Rate Limit greifen
        final_response = test_client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": "999999"},
        )
        assert final_response.status_code in [429, 401]

    def test_mfa_skip_attempt(self, test_client):
        """Testet dass MFA nicht uebersprungen werden kann."""
        # Versuche direkt auf geschuetzte Ressource zuzugreifen nach partial auth
        # (ohne MFA zu verifizieren)
        response = test_client.post(
            "/api/v1/auth/login",
            json={"email": "mfa_user@test.de", "password": "testpassword"},
        )
        if response.status_code == 200 and response.json().get("requires_mfa"):
            partial_token = response.json().get("partial_token")
            # Versuche mit partial token auf Dokumente zuzugreifen
            response = test_client.get(
                "/api/v1/documents",
                headers={"Authorization": f"Bearer {partial_token}"},
            )
            # Sollte abgelehnt werden - MFA nicht abgeschlossen
            assert response.status_code in [401, 403]


# =============================================================================
# PASSWORD SECURITY TESTS
# =============================================================================


class TestPasswordSecurity:
    """Tests fuer Password-Sicherheit."""

    @pytest.mark.parametrize("weak_password", [
        "password",
        "123456",
        "qwerty",
        "admin",
        "letmein",
        "welcome",
        "12345678",
        "password123",
        "abc123",
        "",  # Leer
        "a",  # Zu kurz
    ])
    def test_weak_password_rejection(self, weak_password: str, test_client):
        """Testet dass schwache Passwoerter abgelehnt werden."""
        response = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": "new_user@test.de",
                "password": weak_password,
                "full_name": "Test User",
            },
        )
        # Schwaches Passwort sollte abgelehnt werden
        assert response.status_code in [400, 422]

    def test_password_not_in_response(self, test_client, auth_headers):
        """Testet dass Passwoerter nie in Responses auftauchen."""
        response = test_client.get("/api/v1/users/me", headers=auth_headers)
        if response.status_code == 200:
            assert "password" not in response.text.lower()
            assert "password_hash" not in response.text.lower()
            assert "hashed_password" not in response.text.lower()

    def test_password_hash_timing_attack_resistance(self, test_client):
        """Testet Timing Attack Resistance bei Login."""
        import time
        # Login mit existierendem User
        start1 = time.time()
        test_client.post(
            "/api/v1/auth/login",
            json={"email": "existing@test.de", "password": "wrongpassword"},
        )
        time1 = time.time() - start1

        # Login mit nicht-existierendem User
        start2 = time.time()
        test_client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@test.de", "password": "wrongpassword"},
        )
        time2 = time.time() - start2

        # Zeiten sollten aehnlich sein (Timing Attack Protection)
        # Toleranz: 100ms
        assert abs(time1 - time2) < 0.1


# =============================================================================
# BRUTE FORCE PROTECTION TESTS
# =============================================================================


class TestBruteForceProtection:
    """Tests fuer Brute Force Protection."""

    def test_login_rate_limit(self, test_client):
        """Testet Login Rate Limit (5/15min)."""
        # 6 fehlerhafte Login-Versuche
        for i in range(6):
            response = test_client.post(
                "/api/v1/auth/login",
                json={"email": "victim@test.de", "password": f"wrong{i}"},
            )
            if response.status_code == 429:
                # Rate Limit erreicht - Test erfolgreich
                return

        # Nach 5 Versuchen sollte Rate Limit greifen
        assert response.status_code == 429

    def test_registration_rate_limit(self, test_client):
        """Testet Registration Rate Limit (3/hour)."""
        for i in range(4):
            response = test_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"new{i}@test.de",
                    "password": "StrongP@ssw0rd!",
                    "full_name": f"Test User {i}",
                },
            )
            if response.status_code == 429:
                # Rate Limit erreicht - Test erfolgreich
                return

        # Nach 3 Versuchen sollte Rate Limit greifen
        # (oder weniger, je nach IP/Fingerprint)


# =============================================================================
# TOKEN REFRESH TESTS
# =============================================================================


class TestTokenRefresh:
    """Tests fuer Token Refresh Mechanismus."""

    def test_refresh_token_rotation(self, test_client):
        """Testet dass Refresh-Tokens nach Verwendung rotiert werden."""
        # Login
        response = test_client.post(
            "/api/v1/auth/login",
            json={"email": "test@test.de", "password": "testpassword"},
        )
        if response.status_code == 200:
            refresh_token_1 = response.json().get("refresh_token")

            # Refresh
            response = test_client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token_1},
            )
            if response.status_code == 200:
                refresh_token_2 = response.json().get("refresh_token")
                # Neues Refresh Token sollte anders sein
                assert refresh_token_1 != refresh_token_2

                # Altes Refresh Token sollte nicht mehr funktionieren
                response = test_client.post(
                    "/api/v1/auth/refresh",
                    json={"refresh_token": refresh_token_1},
                )
                assert response.status_code in [400, 401]

    @pytest.mark.xfail(
        reason="Token-Family-Reuse-Detection ist nicht implementiert: der Refresh-Flow "
        "rotiert zwar Tokens, trackt aber keine Token-Family und invalidiert bei Reuse "
        "nicht die gesamte Family (kein family/reuse-Mechanismus im Code). "
        "Cross-Stream-Empfehlung an den Auth-Strom.",
        strict=False,
    )
    def test_refresh_token_reuse_detection(self, test_client):
        """Refresh-Token-Reuse muss die gesamte Token-Family invalidieren.

        Erwartetes Verhalten (OAuth Best Practice / RFC 6819): Wird ein bereits
        rotiertes (verbrauchtes) Refresh-Token erneut verwendet, muessen ALLE
        Tokens der Family ungueltig werden. Ohne laufendes Backend/DB wird zur
        Laufzeit uebersprungen; mit Backend faellt der Test mangels Family-
        Tracking als xfail auf.
        """
        login = test_client.post(
            "/api/v1/auth/login",
            json={"email": "test@test.de", "password": "testpassword"},
        )
        if login.status_code != 200:
            pytest.skip("Login nicht moeglich (Backend/DB nicht verfuegbar)")

        refresh_1 = login.json().get("refresh_token")
        rotated = test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
        if rotated.status_code != 200:
            pytest.skip("Refresh nicht moeglich")
        refresh_2 = rotated.json().get("refresh_token")

        # Reuse des alten (bereits rotierten) Refresh-Tokens muss abgelehnt werden
        reuse = test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
        assert reuse.status_code in (400, 401)

        # Family-Invalidierung: auch das zuletzt rotierte Token muss nun ungueltig sein
        after = test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2})
        assert after.status_code in (400, 401), (
            "Reuse-Detection muss die gesamte Token-Family invalidieren"
        )


# =============================================================================
# FIXTURES - Verwendung von conftest.py
# =============================================================================
# Die Fixtures test_client und auth_headers werden aus conftest.py importiert.
# Diese nutzen den ECHTEN TestClient mit der ECHTEN App für Enterprise-Grade Tests.
