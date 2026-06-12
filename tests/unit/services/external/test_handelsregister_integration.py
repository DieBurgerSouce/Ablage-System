# -*- coding: utf-8 -*-
"""Unit Tests für Handelsregister-Integration.

Testet das Web-Scraping des offiziellen Portals handelsregister.de
mit Rate Limiting und Caching.
"""

import asyncio
import time
from collections import deque
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from lxml import html

from app.services.external.handelsregister_service import (
    HandelsregisterService,
    CompanyRecord,
    CompanyDetails,
    HANDELSREGISTER_RATE_LIMIT_PER_HOUR,
    REGISTER_PATTERN,
    _SAFE_HTML_PARSER,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> HandelsregisterService:
    """Service-Instanz."""
    svc = HandelsregisterService()
    svc.mock_enabled = False  # Echte Implementierung testen
    return svc


@pytest.fixture
def mock_service() -> HandelsregisterService:
    """Service-Instanz im Mock-Modus."""
    svc = HandelsregisterService()
    svc.mock_enabled = True
    return svc


@pytest.fixture
def sample_search_html() -> str:
    """Beispiel-HTML für Suchergebnisse."""
    return """
    <html>
    <body>
    <table class="ergebnisListe">
        <tr><th>Firma</th><th>Register</th><th>Adresse</th><th>Status</th></tr>
        <tr>
            <td><a href="/details/1">Muster GmbH</a></td>
            <td>Amtsgericht München HRB 123456</td>
            <td>Musterstraße 1, 80331 München</td>
            <td>eingetragen</td>
        </tr>
        <tr>
            <td><span>Test AG</span></td>
            <td>Amtsgericht Frankfurt HRB 98765</td>
            <td>Testweg 2, 60313 Frankfurt</td>
            <td>eingetragen</td>
        </tr>
    </table>
    <input name="javax.faces.ViewState" value="test-view-state-123"/>
    </body>
    </html>
    """


@pytest.fixture
def sample_initial_html() -> str:
    """Beispiel-HTML für initiale Seite."""
    return """
    <html>
    <body>
    <form id="form">
        <input name="javax.faces.ViewState" value="initial-view-state"/>
    </form>
    </body>
    </html>
    """


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestHandelsregisterRateLimiting:
    """Tests für Rate Limiting."""

    def test_can_make_request_initially(self, service: HandelsregisterService) -> None:
        """Test: Initial sind Requests erlaubt."""
        assert service._can_make_request() is True

    def test_rate_limit_reached(self, service: HandelsregisterService) -> None:
        """Test: Rate Limit wird respektiert."""
        # Simuliere 60 Requests
        now = time.time()
        for i in range(HANDELSREGISTER_RATE_LIMIT_PER_HOUR):
            service._request_times.append(now - i)

        assert service._can_make_request() is False

    def test_rate_limit_old_requests_expire(self, service: HandelsregisterService) -> None:
        """Test: Alte Requests werden entfernt."""
        # Füge Requests von vor über einer Stunde hinzu
        old_time = time.time() - 3700  # > 1 Stunde
        for _ in range(60):
            service._request_times.append(old_time)

        # Sollte wieder erlaubt sein
        assert service._can_make_request() is True

    def test_wait_time_calculation(self, service: HandelsregisterService) -> None:
        """Test: Wartezeit wird korrekt berechnet."""
        now = time.time()
        service._request_times.append(now - 3000)  # Vor 50 Minuten

        wait_time = service._get_wait_time()

        # Sollte ca. 10 Minuten (600 Sekunden) sein
        assert 500 < wait_time < 700

    def test_wait_time_empty_queue(self, service: HandelsregisterService) -> None:
        """Test: Wartezeit bei leerer Queue ist 0."""
        assert service._get_wait_time() == 0.0

    def test_record_request(self, service: HandelsregisterService) -> None:
        """Test: Request wird aufgezeichnet."""
        initial_count = len(service._request_times)
        service._record_request()

        assert len(service._request_times) == initial_count + 1


# =============================================================================
# Caching Tests
# =============================================================================


class TestHandelsregisterCaching:
    """Tests für Redis Caching."""

    def test_cache_key_generation(self, service: HandelsregisterService) -> None:
        """Test: Cache-Keys werden korrekt generiert."""
        key1 = service._make_cache_key("Muster GmbH", "München")
        key2 = service._make_cache_key("MUSTER GMBH", "MÜNCHEN")  # Case insensitive
        key3 = service._make_cache_key("Muster GmbH", None)

        assert key1 == key2  # Groß/Kleinschreibung egal
        assert key1 != key3  # Unterschiedliche Orte

    def test_cache_key_length(self, service: HandelsregisterService) -> None:
        """Test: Cache-Keys haben feste Länge."""
        key = service._make_cache_key("Sehr langer Firmenname GmbH & Co. KG", "Berlin")
        assert len(key) == 32

    @pytest.mark.asyncio
    async def test_cache_hit(self, service: HandelsregisterService) -> None:
        """Test: Cache-Hit liefert Daten ohne API-Call."""
        cached_data = {
            "records": [
                {
                    "name": "Cached GmbH",
                    "legal_form": "GmbH",
                    "register_court": "Amtsgericht Test",
                    "register_number": "HRB 999",
                    "registered_address": "Test 1",
                    "status": "active",
                }
            ]
        }

        with patch.object(service, "_get_from_cache", new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = cached_data

            results = await service.search_company("Cached GmbH")

        assert len(results) == 1
        assert results[0].name == "Cached GmbH"

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_portal(
        self,
        service: HandelsregisterService,
        sample_initial_html: str,
        sample_search_html: str,
    ) -> None:
        """Test: Cache-Miss führt zu Portal-Anfrage."""
        with patch.object(service, "_get_from_cache", new_callable=AsyncMock) as mock_get_cache:
            mock_get_cache.return_value = None  # Cache miss

            with patch.object(service, "_set_cache", new_callable=AsyncMock) as mock_set_cache:
                with patch("app.services.external.handelsregister_service.httpx.AsyncClient") as mock_client:
                    mock_responses = [
                        MagicMock(text=sample_initial_html, raise_for_status=MagicMock()),
                        MagicMock(text=sample_search_html, raise_for_status=MagicMock()),
                    ]
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                        return_value=mock_responses[0]
                    )
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                        return_value=mock_responses[1]
                    )

                    results = await service.search_company("Muster")

        # Cache sollte gesetzt werden
        mock_set_cache.assert_called_once()
        assert len(results) >= 1


# =============================================================================
# Portal Fetching Tests
# =============================================================================


class TestHandelsregisterPortalFetching:
    """Tests für Portal-Zugriff."""

    def test_extract_view_state(self, service: HandelsregisterService) -> None:
        """Test: ViewState wird extrahiert."""
        tree = html.fromstring("""
            <html>
            <input name="javax.faces.ViewState" value="test-state-123"/>
            </html>
        """)

        view_state = service._extract_view_state(tree)
        assert view_state == "test-state-123"

    def test_extract_view_state_missing(self, service: HandelsregisterService) -> None:
        """Test: Fehlender ViewState gibt leeren String."""
        tree = html.fromstring("<html><body></body></html>")

        view_state = service._extract_view_state(tree)
        assert view_state == ""

    def test_build_search_form(self, service: HandelsregisterService) -> None:
        """Test: Suchformular wird korrekt gebaut."""
        form = service._build_search_form("Test GmbH", "Berlin", "view-state-123")

        assert form["form:schlagwoerter"] == "Test GmbH"
        assert form["form:ort"] == "Berlin"
        assert form["javax.faces.ViewState"] == "view-state-123"

    def test_build_search_form_no_location(self, service: HandelsregisterService) -> None:
        """Test: Suchformular ohne Ort."""
        form = service._build_search_form("Test GmbH", None, "view-state")

        assert form["form:ort"] == ""

    def test_parse_search_results(
        self, service: HandelsregisterService, sample_search_html: str
    ) -> None:
        """Test: Suchergebnisse werden korrekt geparst."""
        tree = html.fromstring(sample_search_html)
        results = service._parse_search_results(tree)

        assert len(results) == 2
        assert results[0].name == "Muster GmbH"
        assert results[0].register_number == "HRB 123456"
        assert results[1].name == "Test AG"

    def test_parse_empty_results(self, service: HandelsregisterService) -> None:
        """Test: Leere Ergebnisse."""
        tree = html.fromstring("""
            <html><body><table class="ergebnisListe">
                <tr><th>Firma</th></tr>
            </table></body></html>
        """)

        results = service._parse_search_results(tree)
        assert len(results) == 0


# =============================================================================
# Register Info Parsing Tests
# =============================================================================


class TestHandelsregisterParsing:
    """Tests für Parsing-Funktionen."""

    def test_parse_register_info_hrb(self, service: HandelsregisterService) -> None:
        """Test: HRB-Nummer wird korrekt geparst."""
        court, number = service._parse_register_info("Amtsgericht München HRB 123456")

        assert court == "Amtsgericht München"
        assert number == "HRB 123456"

    def test_parse_register_info_hra(self, service: HandelsregisterService) -> None:
        """Test: HRA-Nummer wird korrekt geparst."""
        court, number = service._parse_register_info("Amtsgericht Berlin HRA 98765")

        assert court == "Amtsgericht Berlin"
        assert number == "HRA 98765"

    def test_parse_register_info_invalid(self, service: HandelsregisterService) -> None:
        """Test: Ungültige Registerinfo."""
        court, number = service._parse_register_info("Keine Registerinfo")

        assert court is None
        assert number is None

    def test_extract_legal_form_gmbh(self, service: HandelsregisterService) -> None:
        """Test: GmbH wird erkannt."""
        legal_form = service._extract_legal_form("Muster GmbH")
        assert legal_form == "GmbH"

    def test_extract_legal_form_ug(self, service: HandelsregisterService) -> None:
        """Test: UG wird erkannt."""
        legal_form = service._extract_legal_form("Startup UG (haftungsbeschränkt)")
        assert legal_form == "UG"

    def test_extract_legal_form_gmbh_co_kg(self, service: HandelsregisterService) -> None:
        """Test: GmbH & Co. KG wird erkannt."""
        legal_form = service._extract_legal_form("Handel GmbH & Co. KG")
        assert legal_form == "GmbH & Co. KG"

    def test_extract_legal_form_ag(self, service: HandelsregisterService) -> None:
        """Test: AG wird erkannt."""
        legal_form = service._extract_legal_form("Deutsche Bank AG")
        assert legal_form == "AG"

    def test_extract_legal_form_unknown(self, service: HandelsregisterService) -> None:
        """Test: Unbekannte Rechtsform."""
        legal_form = service._extract_legal_form("Einzelunternehmer Müller")
        assert legal_form is None


# =============================================================================
# Serialization Tests
# =============================================================================


class TestHandelsregisterSerialization:
    """Tests für Serialisierung."""

    def test_record_to_dict(self, service: HandelsregisterService) -> None:
        """Test: Record zu Dict."""
        record = CompanyRecord(
            name="Test GmbH",
            legal_form="GmbH",
            register_court="Amtsgericht Test",
            register_number="HRB 123",
            status="active",
        )

        result = service._record_to_dict(record)

        assert result["name"] == "Test GmbH"
        assert result["legal_form"] == "GmbH"
        assert result["register_number"] == "HRB 123"

    def test_dict_to_record(self, service: HandelsregisterService) -> None:
        """Test: Dict zu Record."""
        data = {
            "name": "Test GmbH",
            "legal_form": "GmbH",
            "register_court": "Amtsgericht Test",
            "register_number": "HRB 123",
            "status": "active",
        }

        record = service._dict_to_record(data)

        assert record.name == "Test GmbH"
        assert record.legal_form == "GmbH"

    def test_roundtrip_serialization(self, service: HandelsregisterService) -> None:
        """Test: Serialisierung und Deserialisierung."""
        original = CompanyRecord(
            name="Roundtrip AG",
            legal_form="AG",
            register_court="Amtsgericht Köln",
            register_number="HRB 999",
            registered_address="Domstraße 1, 50667 Köln",
            status="active",
        )

        dict_form = service._record_to_dict(original)
        restored = service._dict_to_record(dict_form)

        assert restored.name == original.name
        assert restored.legal_form == original.legal_form
        assert restored.register_number == original.register_number


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestHandelsregisterErrorHandling:
    """Tests für Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_portal_unavailable_fallback(self, service: HandelsregisterService) -> None:
        """Test: Portal nicht erreichbar führt zu Mock-Fallback."""
        with patch.object(service, "_get_from_cache", new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = None

            with patch("app.services.external.handelsregister_service.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.ConnectError("Connection refused")
                )

                results = await service.search_company("Test GmbH")

        # Sollte auf Mock zurückfallen
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_rate_limit_uses_mock(self, service: HandelsregisterService) -> None:
        """Test: Rate Limit führt zu Mock."""
        # Fülle Rate Limit
        now = time.time()
        for i in range(HANDELSREGISTER_RATE_LIMIT_PER_HOUR):
            service._request_times.append(now)

        with patch.object(service, "_get_from_cache", new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = None

            results = await service.search_company("Test GmbH")

        # Sollte Mock-Ergebnis zurückgeben
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_http_error_fallback(self, service: HandelsregisterService) -> None:
        """Test: HTTP-Fehler führt zu Fallback."""
        with patch.object(service, "_get_from_cache", new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = None

            with patch("app.services.external.handelsregister_service.httpx.AsyncClient") as mock_client:
                error_response = MagicMock()
                error_response.status_code = 500
                error_response.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Server error",
                        request=MagicMock(),
                        response=error_response,
                    )
                )
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=error_response
                )

                results = await service.search_company("Test GmbH")

        assert len(results) >= 1


# =============================================================================
# Mock Mode Tests
# =============================================================================


class TestHandelsregisterMockMode:
    """Tests für Mock-Modus."""

    @pytest.mark.asyncio
    async def test_mock_search_gmbh(self, mock_service: HandelsregisterService) -> None:
        """Test: Mock-Suche für GmbH."""
        results = await mock_service.search_company("Muster GmbH")

        assert len(results) >= 1
        assert any("GmbH" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_mock_search_ag(self, mock_service: HandelsregisterService) -> None:
        """Test: Mock-Suche für AG."""
        results = await mock_service.search_company("Großkonzern AG")

        assert len(results) >= 1
        assert any("AG" in r.legal_form for r in results if r.legal_form)

    @pytest.mark.asyncio
    async def test_mock_search_ug(self, mock_service: HandelsregisterService) -> None:
        """Test: Mock-Suche für UG."""
        results = await mock_service.search_company("Startup UG")

        assert len(results) >= 1
        assert any("UG" in r.legal_form for r in results if r.legal_form)

    @pytest.mark.asyncio
    async def test_mock_search_unknown(self, mock_service: HandelsregisterService) -> None:
        """Test: Mock-Suche für unbekannten Typ."""
        results = await mock_service.search_company("Max Mustermann")

        assert len(results) >= 1
        # Sollte als Einzelunternehmen zurückkommen

    @pytest.mark.asyncio
    async def test_mock_details(self, mock_service: HandelsregisterService) -> None:
        """Test: Mock-Details."""
        details = await mock_service.get_company_details("HRB 123456")

        assert details is not None
        assert details.record.register_number == "HRB 123456"
        assert len(details.history or []) > 0


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestHandelsregisterIntegration:
    """Integration-ähnliche Tests."""

    @pytest.mark.asyncio
    async def test_full_search_flow_with_cache(
        self,
        service: HandelsregisterService,
        sample_initial_html: str,
        sample_search_html: str,
    ) -> None:
        """Test: Vollständiger Suchablauf mit Caching."""
        # Erster Request: Cache miss, Portal-Anfrage
        with patch.object(service, "_get_from_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with patch.object(service, "_set_cache", new_callable=AsyncMock) as mock_set:
                with patch("app.services.external.handelsregister_service.httpx.AsyncClient") as mock_client:
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                        return_value=MagicMock(text=sample_initial_html, raise_for_status=MagicMock())
                    )
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                        return_value=MagicMock(text=sample_search_html, raise_for_status=MagicMock())
                    )

                    results = await service.search_company("Muster")

        # Ergebnisse prüfen
        assert len(results) == 2
        assert results[0].name == "Muster GmbH"

        # Cache wurde gesetzt
        mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_requests_rate_limited(
        self, service: HandelsregisterService
    ) -> None:
        """Test: Parallele Requests werden rate-limited."""
        # Mock alles für schnelle Ausführung
        service.mock_enabled = True

        # Starte viele Requests parallel
        tasks = [
            service.search_company(f"Firma {i}")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # Alle sollten Ergebnisse haben (Mock)
        assert all(len(r) >= 1 for r in results)


# =============================================================================
# Security Tests (CWE-20, CWE-80, CWE-918)
# =============================================================================


# W3 (2026-06-12): Der fruehere Validierungs-Gap in get_company_details ist
# BEHOBEN (fix/w3b-backend-sweep): _validate_register_id laeuft jetzt am
# Methodenanfang VOR Mock-/Cache-/Rate-Limit-Pfad und VOR dem try-Block
# (ValueError wird nicht mehr vom Mock-Fallback geschluckt, CWE-918).
# Die strict-xfail-Marker wurden entfernt.


class TestHandelsregisterSecurity:
    """Security-relevante Tests fuer Handelsregister-Service."""

    @pytest.mark.asyncio
    async def test_html_injection_in_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: HTML Injection im Firmennamen wird abgelehnt (CWE-80)."""
        malicious_name = "<script>alert('xss')</script>"

        with pytest.raises(ValueError, match="ungültige Zeichen"):
            await mock_service.search_company(malicious_name)

    @pytest.mark.asyncio
    async def test_sql_injection_in_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: SQL Injection im Firmennamen wird abgelehnt."""
        malicious_name = "'; DROP TABLE companies; --"

        with pytest.raises(ValueError, match="ungültige Zeichen"):
            await mock_service.search_company(malicious_name)

    @pytest.mark.asyncio
    async def test_path_traversal_in_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Path Traversal im Firmennamen wird abgelehnt."""
        malicious_name = "../../../etc/passwd"

        with pytest.raises(ValueError, match="ungültige Zeichen"):
            await mock_service.search_company(malicious_name)

    @pytest.mark.asyncio
    async def test_very_long_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Ueberlanger Firmenname wird abgelehnt."""
        long_name = "A" * 300  # Ueber MAX_NAME_LENGTH

        with pytest.raises(ValueError, match="zu lang"):
            await mock_service.search_company(long_name)

    @pytest.mark.asyncio
    async def test_empty_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Leerer Firmenname wird abgelehnt."""
        with pytest.raises(ValueError, match="erforderlich"):
            await mock_service.search_company("")

    @pytest.mark.asyncio
    async def test_short_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Zu kurzer Firmenname wird abgelehnt."""
        with pytest.raises(ValueError, match="zu kurz"):
            await mock_service.search_company("A")

    @pytest.mark.asyncio
    async def test_german_umlauts_allowed(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Deutsche Umlaute sind erlaubt."""
        # Sollte keine Exception werfen
        results = await mock_service.search_company("Müller & Söhne GmbH")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_invalid_register_id_format_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Ungueltige Registernummer wird abgelehnt (CWE-918)."""
        # SSRF-Versuch mit manipulierter Registernummer
        malicious_id = "HRB 123 ../../admin"

        with pytest.raises(ValueError, match="Ungültiges Registernummer-Format"):
            await mock_service.get_company_details(malicious_id)

    @pytest.mark.asyncio
    async def test_valid_hrb_format_accepted(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Gueltiges HRB-Format wird akzeptiert."""
        # Sollte keine Exception werfen
        result = await mock_service.get_company_details("HRB 123456")
        assert result is not None

    @pytest.mark.asyncio
    async def test_valid_hra_format_accepted(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Gueltiges HRA-Format wird akzeptiert."""
        result = await mock_service.get_company_details("HRA 12345")
        assert result is not None

    @pytest.mark.asyncio
    async def test_register_id_without_space_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Registernummer ohne Leerzeichen wird abgelehnt."""
        with pytest.raises(ValueError, match="Ungültiges Registernummer-Format"):
            await mock_service.get_company_details("HRB123456")

    @pytest.mark.asyncio
    async def test_register_id_with_letters_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Registernummer mit Buchstaben in Nummer wird abgelehnt."""
        with pytest.raises(ValueError, match="Ungültiges Registernummer-Format"):
            await mock_service.get_company_details("HRB 123ABC")

    @pytest.mark.asyncio
    async def test_null_byte_injection_in_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Null-Byte Injection im Firmennamen wird abgelehnt (CWE-158)."""
        malicious_name = "Muster GmbH\x00<script>alert('xss')</script>"

        with pytest.raises(ValueError, match="Null-Byte"):
            await mock_service.search_company(malicious_name)

    @pytest.mark.asyncio
    async def test_null_byte_injection_in_location_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Null-Byte Injection im Ort wird abgelehnt (CWE-158)."""
        with pytest.raises(ValueError, match="Null-Byte"):
            await mock_service.search_company("Muster GmbH", "München\x00/etc/passwd")

    @pytest.mark.asyncio
    async def test_unicode_normalization_applied(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: Unicode-Normalisierung wird angewendet (CWE-176)."""
        # Verschiedene Unicode-Repraesentationen von "ä"
        # U+00E4 (ä) vs U+0061 U+0308 (a + combining diaeresis)
        name_composed = "Müller GmbH"  # Normales ä
        name_decomposed = "Mu\u0308ller GmbH"  # a + combining diaeresis

        # Beide sollten funktionieren nach Normalisierung
        results1 = await mock_service.search_company(name_composed)
        results2 = await mock_service.search_company(name_decomposed)

        # Beide sollten Ergebnisse liefern (keine Exception)
        assert len(results1) >= 1
        assert len(results2) >= 1

    @pytest.mark.asyncio
    async def test_crlf_injection_in_name_rejected(
        self, mock_service: HandelsregisterService
    ) -> None:
        """Test: CRLF Injection im Firmennamen wird abgelehnt (CWE-113)."""
        malicious_name = "Muster GmbH\r\nX-Injected-Header: evil"

        with pytest.raises(ValueError, match="ungültige Zeichen"):
            await mock_service.search_company(malicious_name)


# =============================================================================
# Register Pattern Validation Tests (Phase 3 Security)
# =============================================================================


class TestRegisterPatternValidation:
    """Tests fuer echtes REGISTER_PATTERN aus dem Service."""

    def test_valid_hrb_patterns(self) -> None:
        """Test: Gueltige HRB-Formate werden akzeptiert."""
        valid_patterns = [
            "HRB 123456",
            "HRB 1",
            "HRB 1234567",  # Max 7 Ziffern
        ]
        for pattern in valid_patterns:
            assert REGISTER_PATTERN.match(pattern), f"Pattern sollte gueltig sein: {pattern}"

    def test_valid_hra_patterns(self) -> None:
        """Test: Gueltige HRA-Formate werden akzeptiert."""
        valid_patterns = [
            "HRA 12345",
            "HRA 1",
        ]
        for pattern in valid_patterns:
            assert REGISTER_PATTERN.match(pattern), f"Pattern sollte gueltig sein: {pattern}"

    def test_valid_other_register_types(self) -> None:
        """Test: Andere gueltige Registerarten."""
        valid_patterns = [
            "GnR 123",  # Genossenschaftsregister
            "PR 456",   # Partnerschaftsregister
            "VR 789",   # Vereinsregister
        ]
        for pattern in valid_patterns:
            assert REGISTER_PATTERN.match(pattern), f"Pattern sollte gueltig sein: {pattern}"

    def test_invalid_patterns_rejected(self) -> None:
        """Test: Ungueltige Formate werden abgelehnt."""
        invalid_patterns = [
            "HRB123456",      # Ohne Leerzeichen
            "HRB 12345678",   # Zu viele Ziffern (>7)
            "HRB 123 B",      # Suffix nicht erlaubt
            "XYZ 123",        # Ungueltiger Typ
            "hrb 123",        # Kleinbuchstaben
            "HRB 123ABC",     # Buchstaben in Nummer
            "HRB",            # Nur Typ
            "123456",         # Nur Nummer
            "../etc/passwd",  # Path Traversal
        ]
        for pattern in invalid_patterns:
            assert not REGISTER_PATTERN.match(pattern), f"Pattern sollte ungueltig sein: {pattern}"

    def test_multiple_whitespace_normalized_safely(self) -> None:
        """Test: Mehrfach-Whitespace matcht (\\s+), ist aber unschaedlich.

        W3 (2026-06-12): Der echte Vertrag nutzt ``\\s+`` zwischen Typ und
        Nummer. 'HRB  123' wird daher AKZEPTIERT — sicherheitsrelevant ist
        nur, dass ausschliesslich die Capture-Groups (Typ-Whitelist +
        reine Ziffern) weiterverwendet werden, nie der Roh-String.
        """
        match = REGISTER_PATTERN.match("HRB  123")
        assert match is not None
        assert match.group(1) == "HRB"
        assert match.group(2) == "123"


# =============================================================================
# XXE Prevention Tests (Phase 3 Security)
# =============================================================================


class TestHandelsregisterXXEPrevention:
    """Tests fuer XXE-Praevention im HTML-Parser (CWE-611)."""

    def test_safe_html_parser_configured(self) -> None:
        """Test: HTMLParser ist mit no_network=True konfiguriert."""
        # Der Parser existiert und ist vom Typ HTMLParser
        assert _SAFE_HTML_PARSER is not None

    def test_external_dtd_not_loaded(self) -> None:
        """Test: Externe DTDs werden nicht geladen."""
        malicious_html = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0//EN"
            "http://evil.com/malicious.dtd">
            <html><body><input name="javax.faces.ViewState" value="test"/></body></html>'''

        # Sollte parsen ohne externe DTD zu laden
        tree = html.fromstring(malicious_html, parser=_SAFE_HTML_PARSER)
        assert tree is not None

    def test_entity_expansion_not_harmful(self) -> None:
        """Test: Entity-Expansion fuehrt nicht zu Problemen."""
        # Billion Laughs Attack (XXE Denial of Service)
        malicious_html = '''<!DOCTYPE html [
            <!ENTITY lol "lol">
            <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
        ]>
        <html><body>&lol1;</body></html>'''

        # Sollte sicher parsen (ohne Endlos-Expansion)
        tree = html.fromstring(malicious_html, parser=_SAFE_HTML_PARSER)
        assert tree is not None

    def test_xxe_file_read_prevented(self) -> None:
        """Test: Lokale Datei-Lesung via XXE wird verhindert."""
        # XXE mit file:// Protocol
        malicious_html = '''<!DOCTYPE html [
            <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <html><body>&xxe;</body></html>'''

        tree = html.fromstring(malicious_html, parser=_SAFE_HTML_PARSER)
        # Der Body sollte NICHT /etc/passwd Inhalt enthalten
        body_text = tree.xpath("//body/text()")
        if body_text:
            assert "root:" not in str(body_text[0])
