# -*- coding: utf-8 -*-
"""
Tests fuer Absender/Empfaenger-Extraktion.

Diese Tests validieren die intelligente Zuordnung von Sender und Recipient
basierend auf:
1. Semantischen Labels (von/an, sender/recipient)
2. Laendercode-Heuristik (bei Reverse Charge)
3. Textposition-Fallback
"""

import pytest
from decimal import Decimal
from app.services.entity_extraction_service import (
    EntityExtractionService,
    GermanPatterns,
    ExtractedAddress,
    ExtractedCompanyName,
    EntityExtractionResult,
)


class TestPLZPatterns:
    """Tests fuer Multi-Land PLZ-Erkennung."""

    def test_german_plz(self):
        """Deutsche 5-stellige PLZ wird erkannt."""
        patterns = GermanPatterns()
        text = "42719 Solingen"
        match = patterns.PLZ_CITY.search(text)
        assert match is not None
        assert match.group(1) == "42719"
        assert match.group(2) == "Solingen"

    def test_dutch_plz(self):
        """Niederlaendische PLZ (4+2) wird erkannt."""
        patterns = GermanPatterns()
        text = "3600 AB Maarssen"
        match = patterns.PLZ_CITY_NL.search(text)
        assert match is not None
        assert match.group(1) == "3600 AB"
        assert match.group(2) == "Maarssen"

    def test_dutch_plz_without_space(self):
        """Niederlaendische PLZ ohne Leerzeichen."""
        patterns = GermanPatterns()
        text = "3600AB Maarssen"
        match = patterns.PLZ_CITY_NL.search(text)
        assert match is not None
        assert match.group(1) == "3600AB"

    def test_german_plz_not_matched_by_dutch(self):
        """Deutsche PLZ wird nicht vom NL-Pattern gematcht."""
        patterns = GermanPatterns()
        text = "42719 Solingen"
        match = patterns.PLZ_CITY_NL.search(text)
        # 42719 hat 5 Ziffern, NL erwartet 4
        assert match is None


class TestSenderRecipientLabels:
    """Tests fuer Label-Erkennung."""

    def test_sender_label_von(self):
        """'Von:' wird als Sender-Label erkannt."""
        patterns = GermanPatterns()
        assert patterns.SENDER_LABELS.search("Von: Firma GmbH") is not None

    def test_sender_label_from(self):
        """'From:' wird als Sender-Label erkannt."""
        patterns = GermanPatterns()
        assert patterns.SENDER_LABELS.search("From: Company Ltd.") is not None

    def test_sender_label_lieferant(self):
        """'Lieferant:' wird als Sender-Label erkannt."""
        patterns = GermanPatterns()
        assert patterns.SENDER_LABELS.search("Lieferant: Test GmbH") is not None

    def test_recipient_label_an(self):
        """'An:' wird als Recipient-Label erkannt."""
        patterns = GermanPatterns()
        assert patterns.RECIPIENT_LABELS.search("An: Kunde AG") is not None

    def test_recipient_label_rechnungsempfaenger(self):
        """'Rechnungsempfaenger:' wird erkannt."""
        patterns = GermanPatterns()
        assert patterns.RECIPIENT_LABELS.search("Rechnungsempfaenger:") is not None

    def test_recipient_label_bill_to(self):
        """'Bill to:' wird als Recipient-Label erkannt."""
        patterns = GermanPatterns()
        assert patterns.RECIPIENT_LABELS.search("Bill to: Customer Inc.") is not None


class TestCompanyNamePatterns:
    """Tests fuer Firmennamen-Erkennung mit EU-Rechtsformen."""

    def test_german_gmbh(self):
        """Deutsche GmbH wird erkannt."""
        patterns = GermanPatterns()
        match = patterns.COMPANY_NAME.search("Deutsche Firma GmbH")
        assert match is not None
        assert match.group(1).strip() == "Deutsche Firma"
        assert match.group(2) == "GmbH"

    def test_dutch_bv(self):
        """Niederlaendische B.V. wird erkannt."""
        patterns = GermanPatterns()
        match = patterns.COMPANY_NAME.search("ALPAC B.V.")
        assert match is not None
        assert match.group(1).strip() == "ALPAC"
        # Rechtsform kann B.V. oder B.V sein (mit/ohne abschliessenden Punkt)
        assert "B.V" in match.group(2)

    def test_british_ltd(self):
        """Britische Ltd. wird erkannt."""
        patterns = GermanPatterns()
        match = patterns.COMPANY_NAME.search("British Company Ltd.")
        assert match is not None
        assert match.group(1).strip() == "British Company"

    def test_spanish_sa(self):
        """Spanische S.A. wird erkannt."""
        patterns = GermanPatterns()
        match = patterns.COMPANY_NAME.search("Empresa Espanola S.A.")
        assert match is not None
        assert match.group(1).strip() == "Empresa Espanola"


class TestEntityExtractionService:
    """Tests fuer den Entity Extraction Service."""

    @pytest.fixture
    def service(self):
        """Erstellt eine Service-Instanz."""
        return EntityExtractionService()

    @pytest.mark.asyncio
    async def test_extract_dutch_and_german_addresses(self, service):
        """NL und DE Adressen werden erkannt und Rollen zugewiesen."""
        text = """Von: ALPAC B.V.
Landeweg 100
3600 AB Maarssen

Rechnungsempfaenger:
Deutsche Firma GmbH
Industriestr. 42
42719 Solingen"""

        result = await service.extract_entities(text)

        assert len(result.addresses) == 2

        # NL-Adresse - naechster zum "Von:" Label = sender
        nl_addr = next((a for a in result.addresses if a.country == "NL"), None)
        assert nl_addr is not None
        assert nl_addr.postal_code == "3600 AB"
        assert nl_addr.role == "sender"

        # DE-Adresse - naechster zum "Rechnungsempfaenger:" Label = recipient
        de_addr = next((a for a in result.addresses if a.country == "DE"), None)
        assert de_addr is not None
        assert de_addr.postal_code == "42719"
        assert de_addr.role == "recipient"

    @pytest.mark.asyncio
    async def test_extract_companies_with_eu_legal_forms(self, service):
        """Firmennamen mit EU-Rechtsformen werden erkannt."""
        text = """
        ALPAC B.V.
        Deutsche Firma GmbH
        British Company Ltd.
        """

        result = await service.extract_entities(text)

        # Mindestens ALPAC und Deutsche Firma sollten erkannt werden
        names = [c.name for c in result.company_names]
        assert any("ALPAC" in n for n in names)
        assert any("Deutsche Firma" in n for n in names)

    @pytest.mark.asyncio
    async def test_addresses_sorted_by_position(self, service):
        """Adressen werden nach Position sortiert."""
        text = """
        12345 Berlin
        54321 Hamburg
        """

        result = await service.extract_entities(text)

        assert len(result.addresses) == 2
        # Erste Adresse sollte Berlin sein (kommt zuerst im Text)
        assert result.addresses[0].city == "Berlin"
        assert result.addresses[1].city == "Hamburg"

    @pytest.mark.asyncio
    async def test_role_assignment_with_labels(self, service):
        """Rollen werden basierend auf Labels zugewiesen."""
        text = """Von: Lieferant GmbH
Musterstr. 1
12345 Berlin

An: Kunde AG
Testweg 2
54321 Hamburg"""

        result = await service.extract_entities(text)

        berlin_addr = next(
            (a for a in result.addresses if "Berlin" in a.city), None
        )
        hamburg_addr = next(
            (a for a in result.addresses if "Hamburg" in a.city), None
        )

        assert berlin_addr is not None
        assert berlin_addr.role == "sender"

        assert hamburg_addr is not None
        assert hamburg_addr.role == "recipient"


class TestReverseChargeScenario:
    """Tests fuer Reverse Charge Szenarien (EU-Rechnungen)."""

    @pytest.fixture
    def service(self):
        """Erstellt eine Service-Instanz."""
        return EntityExtractionService()

    @pytest.mark.asyncio
    async def test_alpac_invoice_real_layout(self, service):
        """
        ALPAC Invoice - echtes Layout wie im Dokument.

        Struktur des echten Dokuments:
        - LINKS: Empfaenger (Spargelmesser Firmenich, D-42719 Solingen)
        - RECHTS: Absender/Briefkopf (Alpac BV, 7418 HG Deventer, NL)

        OCR linearisiert das typischerweise so:
        1. Header (ALPAC Logo)
        2. Linke Spalte (Empfaenger)
        3. Rechte Spalte (Absender-Details)
        """
        # Simuliert OCR-Output eines zweispaltigen Layouts
        text = """
        ALPAC
        kunststof bakken en pallets

        Sales - Invoice

        Spargelmesser Firmenich
        Albertus-Magnus-Str. 11
        D-42719 Solingen
        Duitsland

        Alpac - kunststof bakken en pallets BV
        Van der Landeweg 6
        7418 HG Deventer

        Phone No. +31(0)570-627860
        VAT Reg. No. 820594829B01

        Invoice No. F-201401
        """

        result = await service.extract_entities(text)

        # Beide Adressen erkannt
        assert len(result.addresses) >= 2

        # NL-Adresse (Deventer) erkannt
        nl_addrs = [a for a in result.addresses if a.country == "NL"]
        assert len(nl_addrs) >= 1
        nl_addr = nl_addrs[0]
        assert "7418" in nl_addr.postal_code
        assert "Deventer" in nl_addr.city

        # DE-Adresse (Solingen) erkannt
        de_addrs = [a for a in result.addresses if a.country == "DE"]
        assert len(de_addrs) >= 1
        de_addr = de_addrs[0]
        assert de_addr.postal_code == "42719"
        assert "Solingen" in de_addr.city

        # Firmennamen erkannt
        company_names = [c.name for c in result.company_names]
        # "Alpac" sollte erkannt werden (mit BV-Rechtsform)
        assert any("Alpac" in n or "ALPAC" in n for n in company_names)

    @pytest.mark.asyncio
    async def test_reverse_charge_with_explicit_labels(self, service):
        """
        Reverse Charge mit expliziten Labels - eindeutige Zuordnung.
        """
        text = """
        RECHNUNG

        Von: ALPAC B.V.
        Landeweg 100
        3600 AB Maarssen
        Netherlands
        VAT: NL820594829B01

        Rechnungsempfaenger:
        Deutsche Firma GmbH
        Industriestr. 42
        42719 Solingen
        Germany
        VAT: DE200053646

        BTW verlegd / Reverse Charge

        Total EUR 1.305,60
        """

        result = await service.extract_entities(text)

        # Beide Adressen erkannt
        assert len(result.addresses) >= 2

        # NL-Adresse mit sender-Rolle (wegen "Von:" Label)
        nl_addrs = [a for a in result.addresses if a.country == "NL"]
        assert len(nl_addrs) >= 1
        nl_addr = nl_addrs[0]
        assert "3600" in nl_addr.postal_code
        assert nl_addr.role == "sender"  # "Von:" Label

        # DE-Adresse mit recipient-Rolle
        de_addrs = [a for a in result.addresses if a.country == "DE"]
        assert len(de_addrs) >= 1
        de_addr = de_addrs[0]
        assert de_addr.postal_code == "42719"
        assert de_addr.role == "recipient"  # "Rechnungsempfaenger" Label

        # Firmennamen erkannt
        company_names = [c.name for c in result.company_names]
        assert any("ALPAC" in n for n in company_names)
        assert any("Deutsche Firma" in n for n in company_names)


class TestCountryNameDetection:
    """Tests fuer mehrsprachige Laendernamen-Erkennung."""

    @pytest.fixture
    def service(self):
        """Erstellt eine Service-Instanz."""
        return EntityExtractionService()

    @pytest.mark.asyncio
    async def test_duitsland_recognized_as_germany(self, service):
        """'Duitsland' (NL) wird als DE erkannt."""
        text = """
        Spargelmesser Firmenich
        Albertus-Magnus-Str. 11
        D-42719 Solingen
        Duitsland
        """
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 1
        de_addr = result.addresses[0]
        assert de_addr.postal_code == "42719"
        assert de_addr.country == "DE"

    @pytest.mark.asyncio
    async def test_germany_recognized(self, service):
        """'Germany' (EN) wird als DE erkannt."""
        text = """
        Customer GmbH
        Teststr. 1
        12345 Berlin
        Germany
        """
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 1
        assert result.addresses[0].country == "DE"

    @pytest.mark.asyncio
    async def test_netherlands_recognized(self, service):
        """'Netherlands' (EN) wird als NL erkannt."""
        text = """
        ALPAC B.V.
        Landeweg 6
        7418 HG Deventer
        Netherlands
        """
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 1
        nl_addr = result.addresses[0]
        assert "7418" in nl_addr.postal_code
        assert nl_addr.country == "NL"

    @pytest.mark.asyncio
    async def test_d_prefix_recognized(self, service):
        """'D-42719' Prefix wird als DE erkannt."""
        text = """
        Firma GmbH
        Musterstr. 1
        D-42719 Solingen
        """
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 1
        assert result.addresses[0].country == "DE"

    @pytest.mark.asyncio
    async def test_combined_nl_and_de_countries(self, service):
        """NL und DE Adressen mit expliziten Laendernamen."""
        text = """
        ALPAC B.V.
        Landeweg 6
        7418 HG Deventer
        Netherlands

        Kunde GmbH
        Teststr. 1
        42719 Solingen
        Duitsland
        """
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 2

        nl_addr = next((a for a in result.addresses if "7418" in a.postal_code), None)
        de_addr = next((a for a in result.addresses if a.postal_code == "42719"), None)

        assert nl_addr is not None
        assert nl_addr.country == "NL"

        assert de_addr is not None
        assert de_addr.country == "DE"


class TestNormalGermanInvoice:
    """Regression-Tests fuer normale deutsche Rechnungen."""

    @pytest.fixture
    def service(self):
        """Erstellt eine Service-Instanz."""
        return EntityExtractionService()

    @pytest.mark.asyncio
    async def test_normal_german_invoice(self, service):
        """Normale deutsche Rechnung funktioniert weiterhin."""
        text = """Mustermann GmbH
Beispielstr. 1
12345 Berlin

Kunde AG
Teststr. 2
54321 Muenchen

Rechnungsnummer: RE-2024-001
Nettobetrag: 1.000,00 EUR"""

        result = await service.extract_entities(text)

        assert len(result.addresses) >= 2

        # Erste Adresse (Position) = Berlin
        assert result.addresses[0].postal_code == "12345"
        assert "Berlin" in result.addresses[0].city

        # Zweite Adresse (Position) = Muenchen
        assert result.addresses[1].postal_code == "54321"
        assert "nchen" in result.addresses[1].city  # Muenchen

        # Beide Firmennamen erkannt
        names = [c.name for c in result.company_names]
        assert any("Mustermann" in n for n in names)
        assert any("Kunde" in n for n in names)
