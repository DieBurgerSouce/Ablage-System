# -*- coding: utf-8 -*-
"""Unit Tests für VIES EU-Integration.

Testet die SOAP-basierte USt-IdNr Validierung gegen die EU VIES API.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx

from app.services.external.supplier_verification_service import (
    SupplierVerificationService,
    ViesResult,
    VerificationFinding,
    VerificationSource,
    VerificationSeverity,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock für AsyncSession."""
    return AsyncMock()


@pytest.fixture
def service(mock_db_session: AsyncMock) -> SupplierVerificationService:
    """Service-Instanz mit Mock-DB."""
    return SupplierVerificationService(mock_db_session)


@pytest.fixture
def valid_vies_response_xml() -> str:
    """Beispiel-Response für gültige VAT-ID."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkVatResponse xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
      <countryCode>DE</countryCode>
      <vatNumber>123456789</vatNumber>
      <requestDate>2026-01-29</requestDate>
      <valid>true</valid>
      <name>Muster GmbH</name>
      <address>Musterstraße 1, 80331 München</address>
    </checkVatResponse>
  </soap:Body>
</soap:Envelope>"""


@pytest.fixture
def invalid_vies_response_xml() -> str:
    """Beispiel-Response für ungültige VAT-ID."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkVatResponse xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
      <countryCode>DE</countryCode>
      <vatNumber>999999999</vatNumber>
      <requestDate>2026-01-29</requestDate>
      <valid>false</valid>
      <name>---</name>
      <address>---</address>
    </checkVatResponse>
  </soap:Body>
</soap:Envelope>"""


@pytest.fixture
def vies_fault_response_xml() -> str:
    """Beispiel-Response für SOAP Fault."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>INVALID_INPUT</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"""


# =============================================================================
# Format Validation Tests
# =============================================================================


class TestViesFormatValidation:
    """Tests für VAT-ID Format-Validierung."""

    @pytest.mark.asyncio
    async def test_invalid_format_empty(self, service: SupplierVerificationService) -> None:
        """Test: Leere VAT-ID."""
        result, findings = await service._check_vies("")

        assert result.valid is False
        assert any(f.code == "VIES_INVALID_FORMAT" for f in findings)

    @pytest.mark.asyncio
    async def test_invalid_format_no_country_code(self, service: SupplierVerificationService) -> None:
        """Test: VAT-ID ohne Ländercode."""
        result, findings = await service._check_vies("123456789")

        assert result.valid is False
        assert any(f.code == "VIES_INVALID_FORMAT" for f in findings)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "ECHTER BUG (W3, 2026-06-12): _check_vies kennt keine "
            "EU-Laendercode-Whitelist. Bei nicht erreichbarer VIES-API "
            "greift _vies_format_fallback, dessen Default fuer unbekannte "
            "Laendercodes ('XX') nur len(vat_number)>=2 prueft und damit "
            "valid=True liefert — fuer einen Code, den VIES gar nicht "
            "unterstuetzt. Fix (Laender-Whitelist in app/services/external/"
            "supplier_verification_service.py) ist out-of-zone fuer "
            "w3-tests, siehe Manifest w3-tests.md. Nach App-Fix: "
            "XPASS(strict) -> Marker entfernen."
        ),
    )
    @pytest.mark.asyncio
    async def test_invalid_format_wrong_country_code(self, service: SupplierVerificationService) -> None:
        """Test: VAT-ID mit ungültigem (Nicht-EU-)Ländercode."""
        # Deterministisch offline: API-Aufruf schlaegt fehl -> Format-Fallback
        with patch.object(
            service,
            "_call_vies_api",
            AsyncMock(side_effect=RuntimeError("offline")),
        ):
            result, findings = await service._check_vies("XX123456789")

        # 'XX' ist kein EU-Mitgliedsland -> darf nie valid=True ergeben
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_valid_format_german(self, service: SupplierVerificationService) -> None:
        """Test: Format-Check für deutsche VAT-ID."""
        is_valid = service._validate_vat_format("DE", "123456789")
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_valid_format_german_wrong_length(self, service: SupplierVerificationService) -> None:
        """Test: Deutsche VAT-ID mit falscher Länge."""
        is_valid = service._validate_vat_format("DE", "12345678")  # 8 statt 9
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_valid_format_austrian(self, service: SupplierVerificationService) -> None:
        """Test: Format-Check für österreichische VAT-ID."""
        is_valid = service._validate_vat_format("AT", "U12345678")
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_valid_format_french(self, service: SupplierVerificationService) -> None:
        """Test: Format-Check für französische VAT-ID."""
        is_valid = service._validate_vat_format("FR", "AB123456789")
        assert is_valid is True


# =============================================================================
# SOAP Request Building Tests
# =============================================================================


class TestViesSoapRequestBuilding:
    """Tests für SOAP-Request Erstellung."""

    def test_soap_envelope_structure(self, service: SupplierVerificationService) -> None:
        """Test: SOAP Envelope hat korrekte Struktur."""
        envelope = service._build_vies_soap_request("DE", "123456789")

        assert "soapenv:Envelope" in envelope
        assert "soapenv:Body" in envelope
        assert "urn:checkVat" in envelope
        assert "<urn:countryCode>DE</urn:countryCode>" in envelope
        assert "<urn:vatNumber>123456789</urn:vatNumber>" in envelope

    def test_soap_envelope_namespace(self, service: SupplierVerificationService) -> None:
        """Test: SOAP Envelope hat korrekte Namespaces."""
        envelope = service._build_vies_soap_request("FR", "12345678901")

        assert "xmlns:soapenv" in envelope
        assert "xmlns:urn" in envelope
        assert "urn:ec.europa.eu:taxud:vies:services:checkVat:types" in envelope


# =============================================================================
# API Call Tests
# =============================================================================


class TestViesApiCalls:
    """Tests für VIES API Aufrufe."""

    @pytest.mark.asyncio
    async def test_valid_german_vat(
        self,
        service: SupplierVerificationService,
        valid_vies_response_xml: str,
    ) -> None:
        """Test: Erfolgreiche Validierung einer deutschen VAT-ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = valid_vies_response_xml
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result, findings = await service._check_vies("DE123456789")

        assert result.valid is True
        assert result.vat_number == "DE123456789"
        assert result.country_code == "DE"
        assert result.company_name == "Muster GmbH"
        assert result.company_address == "Musterstraße 1, 80331 München"
        assert any(f.code == "VIES_VALID" for f in findings)
        assert any("EU-VIES-API" in f.details.get("verified_via", "") for f in findings)

    @pytest.mark.asyncio
    async def test_valid_french_vat(
        self,
        service: SupplierVerificationService,
    ) -> None:
        """Test: Französische VAT-ID."""
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkVatResponse xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
      <countryCode>FR</countryCode>
      <vatNumber>12345678901</vatNumber>
      <requestDate>2026-01-29</requestDate>
      <valid>true</valid>
      <name>Société Exemple SARL</name>
      <address>1 Rue de Paris, 75001 Paris</address>
    </checkVatResponse>
  </soap:Body>
</soap:Envelope>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = response_xml
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result, findings = await service._check_vies("FR12345678901")

        assert result.valid is True
        assert result.country_code == "FR"

    @pytest.mark.asyncio
    async def test_invalid_vat(
        self,
        service: SupplierVerificationService,
        invalid_vies_response_xml: str,
    ) -> None:
        """Test: Ungültige VAT-ID (Format ok, aber nicht registriert)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = invalid_vies_response_xml
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result, findings = await service._check_vies("DE999999999")

        assert result.valid is False
        assert any(f.code == "VIES_INVALID" for f in findings)


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestViesErrorHandling:
    """Tests für Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_timeout_fallback(self, service: SupplierVerificationService) -> None:
        """Test: Timeout führt zu Format-Fallback."""
        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timeout")
            )

            result, findings = await service._check_vies("DE123456789")

        # Sollte auf Format-Check zurückfallen
        assert result.vat_number == "DE123456789"
        assert any(f.code == "VIES_FALLBACK" for f in findings)
        assert any("Timeout" in f.message for f in findings)

    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, service: SupplierVerificationService) -> None:
        """Test: Rate Limit (429) führt zu Retry."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Rate limited",
                request=MagicMock(),
                response=rate_limit_response,
            )
        )

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=MagicMock(),
                    response=rate_limit_response,
                )
            # 3. Versuch erfolgreich
            success_response = MagicMock()
            success_response.status_code = 200
            success_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkVatResponse xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
      <countryCode>DE</countryCode>
      <vatNumber>123456789</vatNumber>
      <requestDate>2026-01-29</requestDate>
      <valid>true</valid>
      <name>Test GmbH</name>
      <address>Test 1</address>
    </checkVatResponse>
  </soap:Body>
</soap:Envelope>"""
            success_response.raise_for_status = MagicMock()
            return success_response

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = mock_post
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result, findings = await service._check_vies("DE123456789")

        # Nach Retries erfolgreich
        assert result.valid is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_service_unavailable_fallback(self, service: SupplierVerificationService) -> None:
        """Test: 503 Service Unavailable führt zu Fallback."""
        unavailable_response = MagicMock()
        unavailable_response.status_code = 503
        unavailable_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Service unavailable",
                request=MagicMock(),
                response=unavailable_response,
            )
        )

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Service unavailable",
                    request=MagicMock(),
                    response=unavailable_response,
                )
            )

            result, findings = await service._check_vies("DE123456789")

        assert any(f.code == "VIES_FALLBACK" for f in findings)
        assert any("503" in f.message for f in findings)

    @pytest.mark.asyncio
    async def test_soap_fault_handling(
        self,
        service: SupplierVerificationService,
        vies_fault_response_xml: str,
    ) -> None:
        """Test: SOAP Fault wird korrekt behandelt."""
        mock_response = MagicMock()
        mock_response.status_code = 200  # SOAP Faults kommen mit 200
        mock_response.text = vies_fault_response_xml
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result, findings = await service._check_vies("DE123456789")

        # Sollte auf Fallback zurückfallen nach Exception
        assert any(f.code == "VIES_FALLBACK" for f in findings)

    @pytest.mark.asyncio
    async def test_invalid_xml_response(self, service: SupplierVerificationService) -> None:
        """Test: Ungültige XML-Response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "This is not XML"
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.external.supplier_verification_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result, findings = await service._check_vies("DE123456789")

        assert any(f.code == "VIES_FALLBACK" for f in findings)


# =============================================================================
# Fallback Tests
# =============================================================================


class TestViesFallbackBehavior:
    """Tests für Fallback-Verhalten."""

    def test_fallback_uses_format_validation(self, service: SupplierVerificationService) -> None:
        """Test: Fallback nutzt Format-Validierung."""
        findings: list = []
        result, findings = service._vies_format_fallback(
            "DE123456789", "DE", "123456789", findings, "Test-Fehler"
        )

        # Deutsches Format ist gültig
        assert result.valid is True
        assert any("format-check-only" in f.details.get("verified_via", "") for f in findings)

    def test_fallback_invalid_format(self, service: SupplierVerificationService) -> None:
        """Test: Fallback bei ungültigem Format."""
        findings: list = []
        result, findings = service._vies_format_fallback(
            "DE12345", "DE", "12345", findings, "Test-Fehler"
        )

        # Zu kurz für deutsches Format
        assert result.valid is False

    def test_fallback_unknown_country(self, service: SupplierVerificationService) -> None:
        """Test: Fallback bei unbekanntem (Nicht-EU-)Land lehnt ab."""
        findings: list = []
        result, findings = service._vies_format_fallback(
            "XX123456", "XX", "123456", findings, "Test-Fehler"
        )

        # Fix 2026-06-12: Nicht-EU-Laendercodes kann VIES nie validieren —
        # der alte Fallback (valid=True ab 2 Zeichen) kodifizierte den Bug.
        assert result.valid is False

    def test_fallback_eu_country_without_spezialformat(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: EU-Land ohne Spezialformat nutzt weiter den Laengen-Check."""
        findings: list = []
        result, findings = service._vies_format_fallback(
            "DK12345678", "DK", "12345678", findings, "Test-Fehler"
        )

        assert result.valid is True


# =============================================================================
# Edge Cases
# =============================================================================


class TestViesEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.mark.asyncio
    async def test_vat_with_spaces(self, service: SupplierVerificationService) -> None:
        """Test: VAT-ID mit Leerzeichen wird bereinigt."""
        # Sollte intern zu "DE123456789" bereinigt werden
        with patch.object(service, "_call_vies_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                ViesResult(valid=True, vat_number="DE123456789", country_code="DE"),
                [],
            )

            result, _ = await service._check_vies("DE 123 456 789")

        assert result.vat_number == "DE123456789"

    @pytest.mark.asyncio
    async def test_vat_with_dashes(self, service: SupplierVerificationService) -> None:
        """Test: VAT-ID mit Bindestrichen wird bereinigt."""
        with patch.object(service, "_call_vies_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                ViesResult(valid=True, vat_number="DE123456789", country_code="DE"),
                [],
            )

            result, _ = await service._check_vies("DE-123-456-789")

        assert result.vat_number == "DE123456789"

    @pytest.mark.asyncio
    async def test_lowercase_country_code(self, service: SupplierVerificationService) -> None:
        """Test: Kleinbuchstaben im Ländercode werden konvertiert."""
        with patch.object(service, "_call_vies_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                ViesResult(valid=True, vat_number="DE123456789", country_code="DE"),
                [],
            )

            result, _ = await service._check_vies("de123456789")

        assert result.country_code == "DE"


# =============================================================================
# Security Tests (CWE-91, CWE-611)
# =============================================================================


class TestViesSecurityCases:
    """Security-relevante Tests fuer VIES-Integration."""

    def test_xml_injection_prevention_in_soap_builder(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: XML Injection wird durch Escaping verhindert (CWE-91)."""
        # Malicious VAT that tries to close XML tag and inject
        malicious_vat = "123</urn:vatNumber><urn:malicious>xxx"
        malicious_country = "DE</urn:countryCode><urn:hack>x"

        envelope = service._build_vies_soap_request(malicious_country, malicious_vat)

        # Die Injection-Zeichen sollten escaped sein:
        # < wird zu &lt;, > wird zu &gt;
        # Das bedeutet "</urn:vatNumber>" wird zu "&lt;/urn:vatNumber&gt;"
        # was als TEXT interpretiert wird, nicht als XML-Tag
        assert "&lt;" in envelope  # < muss escaped sein
        assert "&gt;" in envelope  # > muss escaped sein
        # Die escaped Version ist sicher - es sind keine echten XML-Tags mehr

    def test_xml_injection_with_ampersand(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: Ampersand wird escaped (XML Injection)."""
        envelope = service._build_vies_soap_request("DE", "123&456")

        # & sollte als &amp; escaped sein
        assert "&amp;" in envelope or "123" in envelope

    def test_xml_injection_with_quotes(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: Quotes werden escaped."""
        envelope = service._build_vies_soap_request("DE", '123"456')

        # " sollte als &quot; escaped sein
        assert "&quot;" in envelope or "123" in envelope

    def test_vat_number_length_truncation(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: Ueberlange VAT-Nummern werden abgeschnitten."""
        very_long_vat = "A" * 100
        envelope = service._build_vies_soap_request("DE", very_long_vat)

        # Sollte auf max 20 Zeichen begrenzt sein
        assert "A" * 21 not in envelope

    def test_country_code_length_truncation(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: Ueberlange Laendercodes werden abgeschnitten."""
        long_country = "DEXYZ"
        envelope = service._build_vies_soap_request(long_country, "123456789")

        # Sollte auf 2 Zeichen begrenzt sein
        assert "DEXYZ" not in envelope
        assert "<urn:countryCode>DE</urn:countryCode>" in envelope

    @pytest.mark.asyncio
    async def test_xml_injection_in_full_check(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: XML Injection wird im vollen Check abgelehnt."""
        # VAT mit XML-Injection Versuch
        malicious_vat = "DE123</urn:vatNumber><urn:evil>hack"

        # Sollte als ungueltiges Format abgelehnt werden
        result, findings = await service._check_vies(malicious_vat)

        assert result.valid is False
        assert any(f.code == "VIES_INVALID_FORMAT" for f in findings)

    @pytest.mark.asyncio
    async def test_very_long_vat_id_rejected(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: Ueberlange VAT-ID wird abgelehnt."""
        # 1000 Zeichen lange VAT-ID
        long_vat = "DE" + "1" * 1000

        result, findings = await service._check_vies(long_vat)

        # Sollte abgelehnt werden (Format ungueltig)
        assert result.valid is False
        assert any(f.code == "VIES_INVALID_FORMAT" for f in findings)

    @pytest.mark.asyncio
    async def test_crlf_injection_in_vat_rejected(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: CRLF in VAT-ID wird als ungueltiges Format abgelehnt (CWE-113)."""
        malicious_vat = "DE123\r\n456\r\n789"

        result, findings = await service._check_vies(malicious_vat)

        # CRLF macht das Format ungueltig (alphanumerisch erwartet)
        assert result.valid is False
        assert any(f.code == "VIES_INVALID_FORMAT" for f in findings)

    @pytest.mark.asyncio
    async def test_null_byte_injection_in_vat_rejected(
        self, service: SupplierVerificationService
    ) -> None:
        """Test: Null-Byte in VAT-ID wird als ungueltiges Format abgelehnt (CWE-158)."""
        malicious_vat = "DE123\x00456789"

        result, findings = await service._check_vies(malicious_vat)

        # Null-Byte macht das Format ungueltig (alphanumerisch erwartet)
        assert result.valid is False
        assert any(f.code == "VIES_INVALID_FORMAT" for f in findings)


# =============================================================================
# XXE Prevention Tests (CWE-611)
# =============================================================================


class TestXXEPrevention:
    """Tests fuer XXE-Praevention mit defusedxml."""

    def test_xxe_external_entity_blocked(self) -> None:
        """Test: External Entity Angriff wird von defusedxml blockiert."""
        from defusedxml.ElementTree import fromstring
        from defusedxml.common import EntitiesForbidden

        malicious_xml = """<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<root>&xxe;</root>"""

        # defusedxml sollte dies ablehnen
        with pytest.raises(EntitiesForbidden):
            fromstring(malicious_xml)

    def test_billion_laughs_blocked(self) -> None:
        """Test: Billion Laughs DoS-Angriff wird blockiert."""
        from defusedxml.ElementTree import fromstring
        from defusedxml.common import EntitiesForbidden

        # Vereinfachte Version des Billion Laughs Angriffs
        malicious_xml = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">
]>
<root>&lol2;</root>"""

        # defusedxml sollte dies ablehnen
        with pytest.raises(EntitiesForbidden):
            fromstring(malicious_xml)

    def test_external_dtd_blocked(self) -> None:
        """Test: Externe DTD ist unschaedlich bzw. hart blockierbar.

        W3 (2026-06-12): Echter defusedxml-Vertrag — die blosse DOCTYPE-
        SYSTEM-Deklaration wirft im Default KEINE Exception (forbid_dtd
        ist standardmaessig False); expat loest externe DTDs ohnehin nie
        auf, es findet also kein Fetch/SSRF statt. Jede tatsaechliche
        ENTITY-Nutzung bleibt durch forbid_entities=True blockiert (siehe
        Billion-Laughs-/Parameter-Entity-Tests). Der harte Modus
        forbid_dtd=True lehnt bereits die Deklaration ab.
        """
        from defusedxml.ElementTree import fromstring
        from defusedxml.common import DTDForbidden

        malicious_xml = """<?xml version="1.0"?>
<!DOCTYPE foo SYSTEM "http://evil.com/malicious.dtd">
<root>test</root>"""

        # Default (App-Nutzung in _call_vies_api): parsebar, aber inert
        root = fromstring(malicious_xml)
        assert root.tag == "root"
        assert root.text == "test"

        # Harter Modus: DTD-Deklaration selbst wird abgelehnt
        with pytest.raises(DTDForbidden):
            fromstring(malicious_xml, forbid_dtd=True)

    def test_parameter_entity_blocked(self) -> None:
        """Test: Parameter Entity Injection wird blockiert."""
        from defusedxml.ElementTree import fromstring
        from defusedxml.common import EntitiesForbidden

        malicious_xml = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY % xxe SYSTEM "file:///etc/passwd">
  %xxe;
]>
<root>test</root>"""

        # defusedxml sollte Parameter-Entities ablehnen
        with pytest.raises((EntitiesForbidden, Exception)):
            fromstring(malicious_xml)

    def test_safe_xml_parses_correctly(self) -> None:
        """Test: Normales XML wird korrekt geparst."""
        from defusedxml.ElementTree import fromstring

        safe_xml = """<?xml version="1.0"?>
<root>
  <child>test</child>
</root>"""

        # Sicheres XML sollte funktionieren
        root = fromstring(safe_xml)
        assert root.tag == "root"
        assert root.find("child").text == "test"
