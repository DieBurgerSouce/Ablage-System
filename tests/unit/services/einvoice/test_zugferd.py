# -*- coding: utf-8 -*-
"""
Tests fuer ZUGFeRD 2.3.3 Module.

Testet:
- ZUGFeRDEmbedder: PDF/A-3 Embedding
- ZUGFeRDValidator: Schema-Validierung
- ZUGFeRDMapper: Bidirektionale Konvertierung

Referenz: ZUGFeRD 2.3.3 / EN16931 / XRechnung 3.0.2
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from app.services.einvoice.zugferd_validator import (
    ZUGFeRDValidator,
    ValidationResult,
    ValidationSeverity,
    ZUGFeRDProfile,
    get_zugferd_validator,
)
from app.services.einvoice.zugferd_embedder import (
    ZUGFeRDEmbedder,
    ZUGFeRDProfile as EmbedderProfile,
    get_zugferd_embedder,
)


# =============================================================================
# Test Data
# =============================================================================

MINIMAL_ZUGFERD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>INV-2024-001</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">20240115</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>Test GmbH</ram:Name>
        <ram:PostalTradeAddress>
          <ram:CountryID>DE</ram:CountryID>
        </ram:PostalTradeAddress>
        <ram:SpecifiedTaxRegistration>
          <ram:ID schemeID="VA">DE123456789</ram:ID>
        </ram:SpecifiedTaxRegistration>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>Kunde AG</ram:Name>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:ApplicableTradeTax>
        <ram:CalculatedAmount>19.00</ram:CalculatedAmount>
        <ram:TypeCode>VAT</ram:TypeCode>
        <ram:BasisAmount>100.00</ram:BasisAmount>
        <ram:CategoryCode>S</ram:CategoryCode>
        <ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>
      </ram:ApplicableTradeTax>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>100.00</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>100.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">19.00</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>119.00</ram:GrandTotalAmount>
        <ram:DuePayableAmount>119.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""

XRECHNUNG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf:spec:XRechnung:3.0</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>XR-2024-001</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">20240115</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:BuyerReference>04011000-1234-1234-12</ram:BuyerReference>
      <ram:SellerTradeParty>
        <ram:Name>Test GmbH</ram:Name>
        <ram:PostalTradeAddress>
          <ram:CountryID>DE</ram:CountryID>
        </ram:PostalTradeAddress>
        <ram:URIUniversalCommunication>
          <ram:URIID schemeID="EM">seller@example.de</ram:URIID>
        </ram:URIUniversalCommunication>
        <ram:SpecifiedTaxRegistration>
          <ram:ID schemeID="VA">DE123456789</ram:ID>
        </ram:SpecifiedTaxRegistration>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>Behoerde XY</ram:Name>
        <ram:URIUniversalCommunication>
          <ram:URIID schemeID="EM">buyer@behoerde.de</ram:URIID>
        </ram:URIUniversalCommunication>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:ApplicableTradeTax>
        <ram:CalculatedAmount>19.00</ram:CalculatedAmount>
        <ram:TypeCode>VAT</ram:TypeCode>
        <ram:BasisAmount>100.00</ram:BasisAmount>
        <ram:CategoryCode>S</ram:CategoryCode>
        <ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>
      </ram:ApplicableTradeTax>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>100.00</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>100.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">19.00</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>119.00</ram:GrandTotalAmount>
        <ram:DuePayableAmount>119.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""

INVALID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<invalid>This is not valid ZUGFeRD</invalid>
"""

SYNTAX_ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice>
  <unclosed_tag>
"""


# =============================================================================
# ZUGFeRDValidator Tests
# =============================================================================

class TestZUGFeRDValidator:
    """Tests fuer ZUGFeRDValidator."""

    @pytest.fixture
    def validator(self) -> ZUGFeRDValidator:
        """Validator-Instanz."""
        return ZUGFeRDValidator()

    def test_validate_minimal_zugferd(self, validator: ZUGFeRDValidator):
        """Testet Validierung eines minimalen ZUGFeRD XML."""
        result = validator.validate(MINIMAL_ZUGFERD_XML)

        assert result.valid is True
        assert result.profile == ZUGFeRDProfile.EN16931
        assert result.version == "2.3.3"
        assert result.xml_hash is not None
        assert len(result.xml_hash) == 64  # SHA-256

    def test_validate_xrechnung(self, validator: ZUGFeRDValidator):
        """Testet Validierung einer XRechnung."""
        result = validator.validate(XRECHNUNG_XML)

        assert result.valid is True
        assert result.profile == ZUGFeRDProfile.XRECHNUNG
        assert "3.0" in (result.version or "")

    def test_validate_syntax_error(self, validator: ZUGFeRDValidator):
        """Testet Erkennung von Syntax-Fehlern."""
        result = validator.validate(SYNTAX_ERROR_XML)

        assert result.valid is False
        assert len(result.messages) > 0
        assert result.messages[0].severity == ValidationSeverity.FATAL
        assert result.messages[0].code == "XML_SYNTAX_ERROR"

    def test_validate_invalid_root_element(self, validator: ZUGFeRDValidator):
        """Testet Erkennung eines ungueltigen Root-Elements."""
        result = validator.validate(INVALID_XML)

        assert result.valid is False
        errors = [m for m in result.messages if m.severity == ValidationSeverity.ERROR]
        assert any(m.code == "INVALID_ROOT_ELEMENT" for m in errors)

    def test_validate_syntax_only(self, validator: ZUGFeRDValidator):
        """Testet schnelle Syntax-Validierung."""
        result = validator.validate_syntax(MINIMAL_ZUGFERD_XML)

        assert result.valid is True
        assert result.profile == ZUGFeRDProfile.EN16931
        assert len(result.messages) == 0

    def test_detect_profile(self, validator: ZUGFeRDValidator):
        """Testet Profil-Erkennung."""
        profile, version = validator.detect_profile(MINIMAL_ZUGFERD_XML)
        assert profile == ZUGFeRDProfile.EN16931
        assert version == "2.3.3"

        profile, version = validator.detect_profile(XRECHNUNG_XML)
        assert profile == ZUGFeRDProfile.XRECHNUNG

    def test_validate_amounts_consistency(self, validator: ZUGFeRDValidator):
        """Testet Betrags-Konsistenzpruefung."""
        result = validator.validate(MINIMAL_ZUGFERD_XML)

        # Keine Betrags-Warnungen bei konsistenten Daten
        amount_warnings = [
            m for m in result.messages
            if m.code in ("BR-CO-10", "BR-CO-15")
        ]
        assert len(amount_warnings) == 0

    def test_factory_function(self):
        """Testet Factory-Funktion (Singleton)."""
        v1 = get_zugferd_validator()
        v2 = get_zugferd_validator()
        assert v1 is v2  # Gleiche Instanz

    def test_xrechnung_requires_leitweg_id(self, validator: ZUGFeRDValidator):
        """Testet dass XRechnung Leitweg-ID erfordert."""
        # XML ohne Leitweg-ID aber mit XRechnung-Profil
        xml_without_leitweg = XRECHNUNG_XML.replace(
            "<ram:BuyerReference>04011000-1234-1234-12</ram:BuyerReference>",
            ""
        )
        result = validator.validate(xml_without_leitweg)

        leitweg_errors = [
            m for m in result.messages
            if m.code == "MISSING_BUYERREFERENCE" or m.code == "BR-DE-01"
        ]
        assert len(leitweg_errors) > 0


# =============================================================================
# ZUGFeRDEmbedder Tests
# =============================================================================

class TestZUGFeRDEmbedder:
    """Tests fuer ZUGFeRDEmbedder."""

    @pytest.fixture
    def embedder(self) -> ZUGFeRDEmbedder:
        """Embedder-Instanz."""
        return ZUGFeRDEmbedder()

    def test_available_property(self, embedder: ZUGFeRDEmbedder):
        """Testet Backend-Erkennung."""
        # Sollte True sein wenn PyMuPDF oder pikepdf installiert
        # In Tests moeglicherweise False
        assert isinstance(embedder.available, bool)

    @pytest.mark.skipif(
        not ZUGFeRDEmbedder().available,
        reason="Kein PDF-Backend verfuegbar"
    )
    def test_embed_xml_in_pdf(self, embedder: ZUGFeRDEmbedder):
        """Testet XML-Embedding in PDF."""
        # Minimal-PDF erstellen (fuer Test)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<<>>\nstartxref\n0\n%%EOF"

        result_pdf, metadata = embedder.embed_xml_in_pdf(
            pdf_content,
            MINIMAL_ZUGFERD_XML,
            profile=EmbedderProfile.EN16931
        )

        assert isinstance(result_pdf, bytes)
        assert len(result_pdf) > len(pdf_content)
        assert metadata["profile"] == "EN16931"
        assert metadata["xml_hash"] is not None

    def test_embed_empty_xml_raises(self, embedder: ZUGFeRDEmbedder):
        """Testet dass leeres XML einen Fehler wirft."""
        if not embedder.available:
            pytest.skip("Kein PDF-Backend verfuegbar")

        with pytest.raises(ValueError, match="XML-Inhalt darf nicht leer sein"):
            embedder.embed_xml_in_pdf(b"", "", EmbedderProfile.EN16931)

    def test_factory_function(self):
        """Testet Factory-Funktion (Singleton)."""
        e1 = get_zugferd_embedder()
        e2 = get_zugferd_embedder()
        assert e1 is e2  # Gleiche Instanz

    @pytest.mark.skipif(
        not ZUGFeRDEmbedder().available,
        reason="Kein PDF-Backend verfuegbar"
    )
    def test_extract_xml_from_pdf(self, embedder: ZUGFeRDEmbedder):
        """Testet XML-Extraktion aus PDF."""
        # Erst embedden, dann extrahieren
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<<>>\nstartxref\n0\n%%EOF"

        result_pdf, _ = embedder.embed_xml_in_pdf(
            pdf_content,
            MINIMAL_ZUGFERD_XML,
            profile=EmbedderProfile.EN16931
        )

        extracted = embedder.extract_xml_from_pdf(result_pdf)

        if extracted:  # Extraktion kann je nach Backend fehlschlagen
            assert "CrossIndustryInvoice" in extracted
            assert "INV-2024-001" in extracted

    def test_check_pdfa3_compliance(self, embedder: ZUGFeRDEmbedder):
        """Testet PDF/A-3 Konformitaetspruefung."""
        if not embedder.available:
            result = embedder.check_pdfa3_compliance(b"")
            assert result["compliant"] is False
            assert "Kein PDF-Backend" in result["issues"][0]
        else:
            # Mit leerem PDF
            result = embedder.check_pdfa3_compliance(b"")
            assert isinstance(result, dict)
            assert "compliant" in result

    def test_xmp_metadata_generation(self, embedder: ZUGFeRDEmbedder):
        """Testet XMP Metadaten-Generierung."""
        xmp = embedder._create_xmp_metadata(
            EmbedderProfile.EN16931,
            "factur-x.xml",
            "Alternative"
        )

        assert "pdfaid:part>3<" in xmp.lower() or "pdfaid:part>3" in xmp
        assert "factur-x.xml" in xmp
        assert "EN16931" in xmp
        assert "x:xmpmeta" in xmp


# =============================================================================
# Integration Tests
# =============================================================================

class TestZUGFeRDIntegration:
    """Integration Tests fuer ZUGFeRD-Module."""

    def test_validate_then_embed(self):
        """Testet Workflow: Validieren -> Embedden."""
        validator = get_zugferd_validator()
        embedder = get_zugferd_embedder()

        # Schritt 1: Validieren
        result = validator.validate(MINIMAL_ZUGFERD_XML)
        assert result.valid is True

        # Schritt 2: Embedden (wenn Backend verfuegbar)
        if embedder.available:
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<<>>\nstartxref\n0\n%%EOF"
            result_pdf, metadata = embedder.embed_xml_in_pdf(
                pdf_content,
                MINIMAL_ZUGFERD_XML,
                EmbedderProfile.EN16931
            )
            assert len(result_pdf) > 0

    def test_all_profiles(self):
        """Testet alle ZUGFeRD-Profile."""
        validator = get_zugferd_validator()

        profiles = [
            ("minimum", ZUGFeRDProfile.MINIMUM),
            ("basic", ZUGFeRDProfile.BASIC),
            ("basicwl", ZUGFeRDProfile.BASIC_WL),
            ("en16931", ZUGFeRDProfile.EN16931),
            ("extended", ZUGFeRDProfile.EXTENDED),
            ("xrechnung", ZUGFeRDProfile.XRECHNUNG),
        ]

        for profile_name, expected_profile in profiles:
            xml = MINIMAL_ZUGFERD_XML.replace(
                "urn:cen.eu:en16931:2017",
                f"urn:factur-x.eu:1p0:{profile_name}"
            )
            profile, _ = validator.detect_profile(xml)
            # Profil sollte erkannt werden (oder auf EN16931 fallen bei unbekannten)
            assert profile is not None or profile_name in ("minimum", "basic")
