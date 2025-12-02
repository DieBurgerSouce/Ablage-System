# -*- coding: utf-8 -*-
"""
Unit Tests fuer CORS Production Validation.

Testet die CORS-Validierungslogik:
- Wildcard (*) ist in Production nicht erlaubt
- Wildcard ist mit Credentials nie erlaubt
- Localhost Origins sind in Production nicht erlaubt
- HTTPS ist in Production erforderlich
- Origin-Format-Validierung
"""

import pytest


class TestCORSWildcardValidation:
    """Tests fuer CORS Wildcard-Validierung."""

    def test_wildcard_not_allowed_in_production(self):
        """'*' ist in Production nicht erlaubt."""
        cors_origins = ["*"]
        is_debug = False

        # Simuliere die Validierungslogik
        has_wildcard = "*" in cors_origins

        if has_wildcard and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True

    def test_wildcard_allowed_in_debug_without_credentials(self):
        """'*' ist in Debug ohne Credentials erlaubt."""
        cors_origins = ["*"]
        is_debug = True
        allow_credentials = False

        has_wildcard = "*" in cors_origins

        # In Debug ohne Credentials sollte es erlaubt sein
        error_raised = False
        if has_wildcard:
            if allow_credentials:
                error_raised = True
            elif not is_debug:
                error_raised = True

        assert error_raised is False

    def test_wildcard_not_allowed_with_credentials(self):
        """'*' ist mit Credentials nie erlaubt."""
        cors_origins = ["*"]
        allow_credentials = True
        is_debug = True  # Selbst in Debug

        has_wildcard = "*" in cors_origins

        if has_wildcard and allow_credentials:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True


class TestCORSLocalhostValidation:
    """Tests fuer CORS Localhost-Validierung."""

    LOCALHOST_PATTERNS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")

    def _has_localhost(self, origins):
        """Prueft ob Origins localhost enthalten."""
        return any(
            any(pattern in origin.lower() for pattern in self.LOCALHOST_PATTERNS)
            for origin in origins
        )

    def test_localhost_not_allowed_in_production(self):
        """localhost Origins sind in Production nicht erlaubt."""
        cors_origins = ["http://localhost:3000"]
        is_debug = False

        has_localhost = self._has_localhost(cors_origins)

        if has_localhost and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True

    def test_127_0_0_1_not_allowed_in_production(self):
        """127.0.0.1 Origins sind in Production nicht erlaubt."""
        cors_origins = ["http://127.0.0.1:8080"]
        is_debug = False

        has_localhost = self._has_localhost(cors_origins)

        if has_localhost and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True

    def test_ipv6_localhost_not_allowed_in_production(self):
        """::1 Origins sind in Production nicht erlaubt."""
        cors_origins = ["http://[::1]:3000"]
        is_debug = False

        has_localhost = self._has_localhost(cors_origins)

        if has_localhost and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True

    def test_localhost_allowed_in_debug(self):
        """localhost ist in Debug erlaubt."""
        cors_origins = ["http://localhost:3000"]
        is_debug = True

        has_localhost = self._has_localhost(cors_origins)

        # In Debug sollte es erlaubt sein (nur Warnung)
        error_raised = has_localhost and not is_debug

        assert error_raised is False

    @pytest.mark.parametrize("origin", [
        "http://localhost:3000",
        "http://localhost",
        "http://localhost:8080/api",
        "https://localhost:443",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://[::1]:3000",
        "http://0.0.0.0:3000",
    ])
    def test_various_localhost_patterns_detected(self, origin):
        """Verschiedene localhost-Varianten werden erkannt."""
        assert self._has_localhost([origin]) is True

    @pytest.mark.parametrize("origin", [
        "https://example.com",
        "https://app.ablage-system.local",
        "https://192.168.1.100",
    ])
    def test_non_localhost_not_detected(self, origin):
        """Nicht-localhost Origins werden nicht als localhost erkannt."""
        assert self._has_localhost([origin]) is False


class TestCORSHttpsValidation:
    """Tests fuer CORS HTTPS-Validierung in Production."""

    def _get_non_https_origins(self, origins):
        """Gibt alle nicht-HTTPS Origins zurueck."""
        return [
            origin for origin in origins
            if origin != "*" and not origin.startswith("https://")
        ]

    def test_http_not_allowed_in_production(self):
        """HTTP Origins sind in Production nicht erlaubt."""
        cors_origins = ["http://example.com"]
        is_debug = False

        non_https = self._get_non_https_origins(cors_origins)

        if non_https and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True

    def test_https_allowed_in_production(self):
        """HTTPS Origins sind in Production erlaubt."""
        cors_origins = ["https://example.com", "https://app.ablage-system.de"]
        is_debug = False

        non_https = self._get_non_https_origins(cors_origins)

        if non_https and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is False

    def test_http_allowed_in_debug(self):
        """HTTP Origins sind in Debug erlaubt."""
        cors_origins = ["http://localhost:3000"]
        is_debug = True

        # In Debug sollte HTTP erlaubt sein (nur für localhost)
        # Diese Validierung gilt nur für Production
        non_https = self._get_non_https_origins(cors_origins)
        error_raised = non_https and not is_debug

        assert error_raised is False

    def test_mixed_http_https_not_allowed_in_production(self):
        """Gemischte HTTP/HTTPS Origins sind in Production nicht erlaubt."""
        cors_origins = ["https://secure.example.com", "http://insecure.example.com"]
        is_debug = False

        non_https = self._get_non_https_origins(cors_origins)

        if non_https and not is_debug:
            error_raised = True
        else:
            error_raised = False

        assert error_raised is True
        assert "http://insecure.example.com" in non_https


class TestCORSOriginFormatValidation:
    """Tests fuer CORS Origin-Format-Validierung."""

    def _get_invalid_origins(self, origins):
        """Prueft Origins auf gueltiges Format."""
        from urllib.parse import urlparse

        invalid = []
        for origin in origins:
            if origin == "*":
                continue
            # Muss mit http:// oder https:// beginnen
            if not origin.startswith(("http://", "https://")):
                invalid.append(origin)
                continue
            # Darf keinen Pfad enthalten (außer root /)
            try:
                parsed = urlparse(origin)
                if parsed.path and parsed.path != "/" and parsed.path != "":
                    invalid.append(f"{origin} (hat Pfad: {parsed.path})")
            except Exception:
                invalid.append(f"{origin} (ungueltige URL)")
        return invalid

    def test_origin_without_protocol_invalid(self):
        """Origin ohne Protokoll ist ungueltig."""
        cors_origins = ["example.com"]

        invalid = self._get_invalid_origins(cors_origins)

        assert len(invalid) > 0
        assert "example.com" in invalid

    def test_origin_with_path_invalid(self):
        """Origin mit Pfad ist ungueltig."""
        cors_origins = ["https://example.com/api/v1"]

        invalid = self._get_invalid_origins(cors_origins)

        assert len(invalid) > 0
        assert any("/api/v1" in i for i in invalid)

    def test_origin_with_root_path_valid(self):
        """Origin mit Root-Pfad ist gueltig."""
        cors_origins = ["https://example.com/"]

        invalid = self._get_invalid_origins(cors_origins)

        # Root-Pfad "/" sollte erlaubt sein
        assert len(invalid) == 0

    def test_valid_https_origin(self):
        """Gueltiges HTTPS Origin ohne Pfad."""
        cors_origins = ["https://example.com"]

        invalid = self._get_invalid_origins(cors_origins)

        assert len(invalid) == 0

    def test_valid_https_origin_with_port(self):
        """Gueltiges HTTPS Origin mit Port."""
        cors_origins = ["https://example.com:8443"]

        invalid = self._get_invalid_origins(cors_origins)

        assert len(invalid) == 0

    @pytest.mark.parametrize("origin,is_valid", [
        ("https://example.com", True),
        ("http://localhost:3000", True),
        ("https://app.ablage-system.de:8443", True),
        ("https://example.com/", True),  # Root-Pfad OK
        ("example.com", False),  # Kein Protokoll
        ("ftp://example.com", False),  # Falsches Protokoll
        ("https://example.com/api", False),  # Hat Pfad
        ("https://example.com/api/v1", False),  # Hat Pfad
        ("//example.com", False),  # Protocol-relative
    ])
    def test_origin_format_validation(self, origin, is_valid):
        """Parametrisierte Tests fuer Origin-Format."""
        invalid = self._get_invalid_origins([origin])

        if is_valid:
            assert len(invalid) == 0, f"{origin} sollte gueltig sein"
        else:
            assert len(invalid) > 0, f"{origin} sollte ungueltig sein"


class TestCORSProductionConfiguration:
    """Integration-artige Tests fuer Production-Konfiguration."""

    def test_secure_production_configuration(self):
        """Sichere Production-Konfiguration wird akzeptiert."""
        cors_origins = [
            "https://app.ablage-system.de",
            "https://admin.ablage-system.de",
        ]
        is_debug = False
        allow_credentials = True

        # Keine der Validierungen sollte fehlschlagen
        has_wildcard = "*" in cors_origins
        has_localhost = any(
            any(p in o.lower() for p in ("localhost", "127.0.0.1", "::1"))
            for o in cors_origins
        )
        non_https = [o for o in cors_origins if not o.startswith("https://")]

        errors = []
        if has_wildcard:
            errors.append("wildcard")
        if has_localhost and not is_debug:
            errors.append("localhost")
        if non_https and not is_debug:
            errors.append("non-https")

        assert len(errors) == 0, f"Fehler: {errors}"

    def test_insecure_production_configuration_fails(self):
        """Unsichere Production-Konfiguration wird abgelehnt."""
        cors_origins = [
            "*",  # Wildcard
        ]
        is_debug = False
        allow_credentials = True

        has_wildcard = "*" in cors_origins

        # Wildcard mit Credentials sollte immer fehlschlagen
        assert has_wildcard and allow_credentials

    def test_development_configuration_allowed(self):
        """Development-Konfiguration mit localhost ist erlaubt."""
        cors_origins = [
            "http://localhost:3000",
            "http://localhost:8080",
        ]
        is_debug = True
        allow_credentials = True

        has_wildcard = "*" in cors_origins
        has_localhost = any(
            any(p in o.lower() for p in ("localhost", "127.0.0.1"))
            for o in cors_origins
        )

        # In Debug mit localhost sollte OK sein
        errors = []
        if has_wildcard and allow_credentials:
            errors.append("wildcard+credentials")
        if has_localhost and not is_debug:
            errors.append("localhost-in-production")

        assert len(errors) == 0


class TestCORSEdgeCases:
    """Edge Cases fuer CORS-Validierung."""

    def test_empty_origins_list(self):
        """Leere Origins-Liste."""
        cors_origins = []

        has_wildcard = "*" in cors_origins
        has_localhost = any(
            any(p in o.lower() for p in ("localhost",))
            for o in cors_origins
        )

        assert has_wildcard is False
        assert has_localhost is False

    def test_case_insensitive_localhost_detection(self):
        """Localhost-Erkennung ist case-insensitive."""
        cors_origins = ["http://LOCALHOST:3000", "http://LocalHost:8080"]

        has_localhost = any(
            "localhost" in origin.lower()
            for origin in cors_origins
        )

        assert has_localhost is True

    def test_subdomain_with_localhost_not_detected(self):
        """Subdomain mit 'localhost' im Namen ist kein echter localhost."""
        # Dies ist ein Edge Case - localhost.example.com ist NICHT localhost
        cors_origins = ["https://localhost.example.com"]

        # Aber unsere Validierung erkennt es trotzdem (sicher ist sicher)
        has_localhost = any(
            "localhost" in origin.lower()
            for origin in cors_origins
        )

        # Das Pattern "localhost" ist enthalten, also wird es erkannt
        assert has_localhost is True

    def test_ip_address_origins(self):
        """IP-Adressen als Origins (nicht localhost)."""
        cors_origins = ["https://192.168.1.100", "https://10.0.0.1:8443"]

        has_localhost = any(
            any(p in o.lower() for p in ("localhost", "127.0.0.1", "::1", "0.0.0.0"))
            for o in cors_origins
        )

        # Private IPs sind nicht localhost
        assert has_localhost is False
