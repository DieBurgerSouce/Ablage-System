# -*- coding: utf-8 -*-
"""
Tests fuer DunningLetterService.

Testet:
- Briefdaten-Vorbereitung (prepare_letter_data)
- Verzugszinsen-Berechnung nach BGB §288
- HTML-Template-Rendering
- PDF-Generierung
- Deutsche Formatierung (Datum, Waehrung)
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.banking.dunning_letter_service import (
    DunningLetterService,
    DunningLetterData,
)


class TestDunningLevelConfig:
    """Tests fuer Mahnstufen-Konfiguration."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_all_levels_defined(self, service: DunningLetterService):
        """Sollte alle 4 Mahnstufen definiert haben."""
        config = service.DUNNING_LEVEL_CONFIG
        assert 1 in config
        assert 2 in config
        assert 3 in config
        assert 4 in config

    def test_level_1_config(self, service: DunningLetterService):
        """Sollte Level 1 (Zahlungserinnerung) korrekt konfiguriert haben."""
        config = service.DUNNING_LEVEL_CONFIG[1]

        assert config["name"] == "Zahlungserinnerung"
        assert config["template"] == "reminder_friendly.html"
        assert config["fee"] == Decimal("0.00")
        assert config["payment_days"] == 14

    def test_level_2_config(self, service: DunningLetterService):
        """Sollte Level 2 (1. Mahnung) korrekt konfiguriert haben."""
        config = service.DUNNING_LEVEL_CONFIG[2]

        assert config["name"] == "1. Mahnung"
        assert config["template"] == "mahnung_1.html"
        assert config["fee"] == Decimal("5.00")
        assert config["payment_days"] == 10

    def test_level_3_config(self, service: DunningLetterService):
        """Sollte Level 3 (2. Mahnung) korrekt konfiguriert haben."""
        config = service.DUNNING_LEVEL_CONFIG[3]

        assert config["name"] == "2. Mahnung"
        assert config["template"] == "mahnung_2.html"
        assert config["fee"] == Decimal("10.00")
        assert config["payment_days"] == 7

    def test_level_4_config(self, service: DunningLetterService):
        """Sollte Level 4 (Letzte Mahnung) korrekt konfiguriert haben."""
        config = service.DUNNING_LEVEL_CONFIG[4]

        assert config["name"] == "Letzte Mahnung"
        assert config["template"] == "mahnung_final.html"
        assert config["fee"] == Decimal("15.00")
        assert config["payment_days"] == 5

    def test_fees_increase_with_level(self, service: DunningLetterService):
        """Sollte aufsteigende Gebuehren haben."""
        config = service.DUNNING_LEVEL_CONFIG
        fees = [config[level]["fee"] for level in range(1, 5)]

        for i in range(len(fees) - 1):
            assert fees[i] <= fees[i + 1]

    def test_payment_days_decrease_with_level(self, service: DunningLetterService):
        """Sollte abnehmende Zahlungsfristen haben."""
        config = service.DUNNING_LEVEL_CONFIG
        days = [config[level]["payment_days"] for level in range(1, 5)]

        for i in range(len(days) - 1):
            assert days[i] >= days[i + 1]


class TestDunningLetterData:
    """Tests fuer DunningLetterData Dataclass."""

    def test_create_letter_data(self):
        """Sollte Briefdaten erstellen."""
        data = DunningLetterData(
            # Absender
            company_name="Muster AG",
            company_address="Musterweg 2",
            company_city="54321 Musterstadt",
            # Empfaenger
            recipient_name="Test GmbH",
            recipient_address="Teststrasse 1",
            recipient_city="12345 Teststadt",
            # Rechnung
            invoice_number="RE-2024-001",
            invoice_date=date(2024, 1, 15),
            invoice_amount=Decimal("1000.00"),
            due_date=date(2024, 2, 15),
            outstanding_amount=Decimal("1000.00"),
            # Mahnung
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=25,
            # Gebuehren
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10.50"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1015.50"),
            # Fristen
            payment_deadline=date(2024, 3, 1),
        )

        assert data.dunning_level == 2
        assert data.recipient_name == "Test GmbH"
        assert data.total_amount == Decimal("1015.50")
        assert data.days_overdue == 25

    def test_total_calculation(self):
        """Sollte Gesamtbetrag korrekt berechnen."""
        outstanding = Decimal("1000.00")
        interest = Decimal("10.00")
        fee = Decimal("5.00")
        total = outstanding + interest + fee

        data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="Kunde GmbH",
            recipient_address="Kunde",
            recipient_city="54321 Kunde",
            invoice_number="RE-001",
            invoice_date=date.today(),
            invoice_amount=outstanding,
            due_date=date.today() - timedelta(days=20),
            outstanding_amount=outstanding,
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=20,
            interest_rate=Decimal("12.62"),
            interest_amount=interest,
            dunning_fee=fee,
            total_amount=total,
            payment_deadline=date.today() + timedelta(days=10),
        )

        assert data.total_amount == Decimal("1015.00")

    def test_optional_fields(self):
        """Sollte optionale Felder korrekt handhaben."""
        data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="Kunde GmbH",
            recipient_address="Kunde",
            recipient_city="54321 Kunde",
            invoice_number="RE-001",
            invoice_date=date.today(),
            invoice_amount=Decimal("100.00"),
            due_date=date.today() - timedelta(days=10),
            outstanding_amount=Decimal("100.00"),
            dunning_level=1,
            dunning_date=date.today(),
            days_overdue=10,
            interest_rate=Decimal("8.62"),
            interest_amount=Decimal("1.00"),
            dunning_fee=Decimal("0.00"),
            total_amount=Decimal("101.00"),
            payment_deadline=date.today() + timedelta(days=14),
            # Optionale Felder
            company_iban="DE89370400440532013000",
            company_bic="COBADEFFXXX",
            company_bank_name="Musterbank",
            b2b_pauschale=Decimal("40.00"),
        )

        assert data.company_iban == "DE89370400440532013000"
        assert data.b2b_pauschale == Decimal("40.00")
        assert data.company_phone is None  # Nicht gesetzt


class TestDunningLetterService:
    """Tests fuer DunningLetterService."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_service_instantiation(self, service: DunningLetterService):
        """Sollte Service instanziieren."""
        assert service is not None

    def test_singleton_pattern(self):
        """Sollte Singleton-Pattern implementieren."""
        service1 = DunningLetterService()
        service2 = DunningLetterService()
        assert service1 is service2


class TestBaseInterestRate:
    """Tests fuer Basiszinssatz."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_get_base_interest_rate(self, service: DunningLetterService):
        """Sollte Basiszinssatz der Bundesbank liefern."""
        rate = service.get_base_interest_rate()

        # Aktueller Basiszinssatz (Stand Januar 2026)
        assert rate == Decimal("3.62")

    def test_b2b_interest_rate_calculation(self, service: DunningLetterService):
        """Sollte B2B-Zinssatz (Basiszins + 9%) berechnen."""
        rate = service.calculate_interest_rate(is_b2b=True)

        # B2B: Basiszins (3.62%) + 9% = 12.62%
        expected = Decimal("3.62") + Decimal("9.00")
        assert rate == expected

    def test_b2c_interest_rate_calculation(self, service: DunningLetterService):
        """Sollte B2C-Zinssatz (Basiszins + 5%) berechnen."""
        rate = service.calculate_interest_rate(is_b2b=False)

        # B2C: Basiszins (3.62%) + 5% = 8.62%
        expected = Decimal("3.62") + Decimal("5.00")
        assert rate == expected


class TestLateInterestCalculation:
    """Tests fuer Verzugszinsen-Berechnung nach BGB §288."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_no_interest_if_not_overdue(self, service: DunningLetterService):
        """Sollte keine Zinsen berechnen wenn nicht ueberfaellig."""
        interest = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=0,
            interest_rate=Decimal("12.62"),
        )

        assert interest == Decimal("0.00")

    def test_no_interest_for_negative_days(self, service: DunningLetterService):
        """Sollte keine Zinsen fuer negative Tage berechnen."""
        interest = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=-5,
            interest_rate=Decimal("12.62"),
        )

        assert interest == Decimal("0.00")

    def test_b2b_interest_one_year(self, service: DunningLetterService):
        """Sollte B2B-Zinsen fuer ein Jahr berechnen."""
        # B2B: Basiszins (3.62%) + 9% = 12.62% p.a.
        interest = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=365,
            interest_rate=Decimal("12.62"),
        )

        # 1000 * 0.1262 * (365/365) = 126.20
        assert interest == Decimal("126.20")

    def test_b2c_interest_one_year(self, service: DunningLetterService):
        """Sollte B2C-Zinsen fuer ein Jahr berechnen."""
        # B2C: Basiszins (3.62%) + 5% = 8.62% p.a.
        interest = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=365,
            interest_rate=Decimal("8.62"),
        )

        # 1000 * 0.0862 * (365/365) = 86.20
        assert interest == Decimal("86.20")

    def test_interest_scales_with_principal(self, service: DunningLetterService):
        """Sollte Zinsen proportional zum Betrag skalieren."""
        interest_1000 = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=60,
            interest_rate=Decimal("12.62"),
        )

        interest_2000 = service.calculate_interest(
            principal=Decimal("2000.00"),
            days_overdue=60,
            interest_rate=Decimal("12.62"),
        )

        # Doppelter Betrag = ca. doppelte Zinsen (Rundungsdifferenz max 1 Cent)
        expected = interest_1000 * 2
        assert abs(interest_2000 - expected) <= Decimal("0.01")

    def test_interest_scales_with_days(self, service: DunningLetterService):
        """Sollte Zinsen proportional zu Tagen skalieren."""
        interest_30d = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=30,
            interest_rate=Decimal("12.62"),
        )

        interest_60d = service.calculate_interest(
            principal=Decimal("1000.00"),
            days_overdue=60,
            interest_rate=Decimal("12.62"),
        )

        # Doppelte Zeit = ca. doppelte Zinsen (Rundungsdifferenz max 1 Cent)
        expected = interest_30d * 2
        assert abs(interest_60d - expected) <= Decimal("0.01")

    def test_interest_rounded_to_cents(self, service: DunningLetterService):
        """Sollte Zinsen auf 2 Dezimalstellen runden."""
        interest = service.calculate_interest(
            principal=Decimal("1234.56"),
            days_overdue=45,
            interest_rate=Decimal("12.62"),
        )

        # Sollte auf 2 Dezimalstellen gerundet sein
        assert interest == interest.quantize(Decimal("0.01"))


class TestSampleLetterData:
    """Tests fuer sample Letter Data Fixtures."""

    @pytest.fixture
    def sample_letter_data(self) -> DunningLetterData:
        """Erstellt Beispiel-Briefdaten fuer Tests."""
        return DunningLetterData(
            company_name="Muster AG",
            company_address="Musterweg 2",
            company_city="54321 Musterstadt",
            recipient_name="Test GmbH",
            recipient_address="Teststrasse 1",
            recipient_city="12345 Teststadt",
            invoice_number="RE-2024-001",
            invoice_date=date(2024, 1, 15),
            invoice_amount=Decimal("1000.00"),
            due_date=date(2024, 2, 15),
            outstanding_amount=Decimal("1000.00"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=25,
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10.50"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1015.50"),
            payment_deadline=date(2024, 3, 1),
            company_iban="DE89370400440532013000",
            company_bic="COBADEFFXXX",
            company_bank_name="Musterbank",
        )

    def test_fixture_creation(self, sample_letter_data: DunningLetterData):
        """Sollte Fixture korrekt erstellen."""
        assert sample_letter_data.company_name == "Muster AG"
        assert sample_letter_data.recipient_name == "Test GmbH"
        assert sample_letter_data.invoice_number == "RE-2024-001"


class TestRenderHtml:
    """Tests fuer HTML-Rendering."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    @pytest.fixture
    def sample_letter_data(self) -> DunningLetterData:
        return DunningLetterData(
            company_name="Muster AG",
            company_address="Musterweg 2",
            company_city="54321 Musterstadt",
            recipient_name="Test GmbH",
            recipient_address="Teststrasse 1",
            recipient_city="12345 Teststadt",
            invoice_number="RE-2024-001",
            invoice_date=date(2024, 1, 15),
            invoice_amount=Decimal("1000.00"),
            due_date=date(2024, 2, 15),
            outstanding_amount=Decimal("1000.00"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=25,
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10.50"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1015.50"),
            payment_deadline=date(2024, 3, 1),
            company_iban="DE89370400440532013000",
            company_bic="COBADEFFXXX",
        )

    def test_render_html_returns_string(
        self, service: DunningLetterService, sample_letter_data: DunningLetterData
    ):
        """Sollte HTML-String zurueckgeben."""
        html = service.render_html(sample_letter_data)

        assert isinstance(html, str)
        assert len(html) > 0

    def test_render_html_contains_recipient_info(
        self, service: DunningLetterService, sample_letter_data: DunningLetterData
    ):
        """Sollte Empfaenger-Informationen enthalten."""
        html = service.render_html(sample_letter_data)

        assert sample_letter_data.recipient_name in html

    def test_render_html_contains_invoice_info(
        self, service: DunningLetterService, sample_letter_data: DunningLetterData
    ):
        """Sollte Rechnungs-Informationen enthalten."""
        html = service.render_html(sample_letter_data)

        assert sample_letter_data.invoice_number in html


class TestRenderPdf:
    """Tests fuer PDF-Rendering."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    @pytest.fixture
    def sample_letter_data(self) -> DunningLetterData:
        return DunningLetterData(
            company_name="Muster AG",
            company_address="Musterweg 2",
            company_city="54321 Musterstadt",
            recipient_name="Test GmbH",
            recipient_address="Teststrasse 1",
            recipient_city="12345 Teststadt",
            invoice_number="RE-2024-001",
            invoice_date=date(2024, 1, 15),
            invoice_amount=Decimal("1000.00"),
            due_date=date(2024, 2, 15),
            outstanding_amount=Decimal("1000.00"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=25,
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10.50"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1015.50"),
            payment_deadline=date(2024, 3, 1),
            company_iban="DE89370400440532013000",
            company_bic="COBADEFFXXX",
        )

    def test_render_pdf_returns_bytes(
        self, service: DunningLetterService, sample_letter_data: DunningLetterData
    ):
        """Sollte PDF-Bytes zurueckgeben."""
        pdf_bytes = service.render_pdf(sample_letter_data)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    def test_render_pdf_is_valid_pdf(
        self, service: DunningLetterService, sample_letter_data: DunningLetterData
    ):
        """Sollte gueltige PDF-Datei erzeugen."""
        pdf_bytes = service.render_pdf(sample_letter_data)

        # PDF beginnt mit %PDF
        assert pdf_bytes.startswith(b"%PDF")

    def test_render_pdf_reasonable_size(
        self, service: DunningLetterService, sample_letter_data: DunningLetterData
    ):
        """Sollte PDF mit vernuenftiger Groesse erzeugen."""
        pdf_bytes = service.render_pdf(sample_letter_data)

        # PDF sollte zwischen 1KB und 1MB sein
        assert 1000 < len(pdf_bytes) < 1000000


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_very_small_amount(self, service: DunningLetterService):
        """Sollte sehr kleine Betraege verarbeiten."""
        letter_data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="Kunde",
            recipient_address="Kunde",
            recipient_city="54321 Kunde",
            invoice_number="RE-2024-001",
            invoice_date=date.today() - timedelta(days=60),
            invoice_amount=Decimal("1.00"),
            due_date=date.today() - timedelta(days=30),
            outstanding_amount=Decimal("1.00"),
            dunning_level=1,
            dunning_date=date.today(),
            days_overdue=30,
            interest_rate=Decimal("8.62"),
            interest_amount=Decimal("0.01"),
            dunning_fee=Decimal("0.00"),
            total_amount=Decimal("1.01"),
            payment_deadline=date.today() + timedelta(days=14),
        )

        html = service.render_html(letter_data)
        assert len(html) > 0

    def test_very_large_amount(self, service: DunningLetterService):
        """Sollte sehr grosse Betraege verarbeiten."""
        letter_data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="Kunde",
            recipient_address="Kunde",
            recipient_city="54321 Kunde",
            invoice_number="RE-2024-001",
            invoice_date=date.today() - timedelta(days=60),
            invoice_amount=Decimal("999999.99"),
            due_date=date.today() - timedelta(days=30),
            outstanding_amount=Decimal("999999.99"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=30,
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10000.00"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1010004.99"),
            payment_deadline=date.today() + timedelta(days=10),
        )

        html = service.render_html(letter_data)
        assert len(html) > 0

    def test_special_characters_in_names(self, service: DunningLetterService):
        """Sollte Sonderzeichen in Namen verarbeiten."""
        letter_data = DunningLetterData(
            company_name="Böhm-Schäfer AG",
            company_address="Überlandstraße 99",
            company_city="54321 Nürnberg",
            recipient_name="Müller & Söhne GmbH",
            recipient_address="Große Straße 1",
            recipient_city="12345 Köln",
            invoice_number="RE-2024-001",
            invoice_date=date.today() - timedelta(days=60),
            invoice_amount=Decimal("1000.00"),
            due_date=date.today() - timedelta(days=30),
            outstanding_amount=Decimal("1000.00"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=30,
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10.00"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1015.00"),
            payment_deadline=date.today() + timedelta(days=10),
        )

        html = service.render_html(letter_data)
        assert "Müller" in html or "Mueller" in html

    def test_zero_days_overdue(self, service: DunningLetterService):
        """Sollte Faelligkeitstag verarbeiten."""
        letter_data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="Kunde",
            recipient_address="Kunde",
            recipient_city="54321 Kunde",
            invoice_number="RE-2024-001",
            invoice_date=date.today() - timedelta(days=30),
            invoice_amount=Decimal("1000.00"),
            due_date=date.today(),  # Heute faellig
            outstanding_amount=Decimal("1000.00"),
            dunning_level=1,
            dunning_date=date.today(),
            days_overdue=0,
            interest_rate=Decimal("8.62"),
            interest_amount=Decimal("0.00"),
            dunning_fee=Decimal("0.00"),
            total_amount=Decimal("1000.00"),
            payment_deadline=date.today() + timedelta(days=14),
        )

        html = service.render_html(letter_data)
        assert len(html) > 0

    def test_all_dunning_levels(self, service: DunningLetterService):
        """Sollte alle Mahnstufen rendern koennen."""
        for level in range(1, 5):
            letter_data = DunningLetterData(
                company_name="Test AG",
                company_address="Test",
                company_city="12345 Test",
                recipient_name="Kunde",
                recipient_address="Kunde",
                recipient_city="54321 Kunde",
                invoice_number=f"RE-2024-{level:03d}",
                invoice_date=date.today() - timedelta(days=60),
                invoice_amount=Decimal("1000.00"),
                due_date=date.today() - timedelta(days=30),
                outstanding_amount=Decimal("1000.00"),
                dunning_level=level,
                dunning_date=date.today(),
                days_overdue=30,
                interest_rate=Decimal("12.62"),
                interest_amount=Decimal("10.00"),
                dunning_fee=service.DUNNING_LEVEL_CONFIG[level]["fee"],
                total_amount=Decimal("1010.00") + service.DUNNING_LEVEL_CONFIG[level]["fee"],
                payment_deadline=date.today() + timedelta(days=service.DUNNING_LEVEL_CONFIG[level]["payment_days"]),
            )

            html = service.render_html(letter_data)
            assert len(html) > 0
            assert f"RE-2024-{level:03d}" in html


class TestB2BPauschale:
    """Tests fuer B2B Pauschale nach §288 Abs. 5 BGB."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_b2b_pauschale_in_data(self):
        """Sollte B2B Pauschale in Briefdaten enthalten."""
        data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="B2B Kunde GmbH",
            recipient_address="Business Strasse 1",
            recipient_city="54321 B2B-Stadt",
            invoice_number="RE-B2B-001",
            invoice_date=date.today() - timedelta(days=60),
            invoice_amount=Decimal("1000.00"),
            due_date=date.today() - timedelta(days=30),
            outstanding_amount=Decimal("1000.00"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=30,
            interest_rate=Decimal("12.62"),
            interest_amount=Decimal("10.00"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("1055.00"),  # inkl. EUR 40 Pauschale
            payment_deadline=date.today() + timedelta(days=10),
            b2b_pauschale=Decimal("40.00"),  # EUR 40 nach §288 Abs. 5 BGB
        )

        assert data.b2b_pauschale == Decimal("40.00")

    def test_no_pauschale_for_b2c(self):
        """Sollte keine Pauschale fuer B2C haben."""
        data = DunningLetterData(
            company_name="Test AG",
            company_address="Test",
            company_city="12345 Test",
            recipient_name="Privatkunde",
            recipient_address="Privatstrasse 1",
            recipient_city="54321 Privatstadt",
            invoice_number="RE-B2C-001",
            invoice_date=date.today() - timedelta(days=60),
            invoice_amount=Decimal("100.00"),
            due_date=date.today() - timedelta(days=30),
            outstanding_amount=Decimal("100.00"),
            dunning_level=2,
            dunning_date=date.today(),
            days_overdue=30,
            interest_rate=Decimal("8.62"),
            interest_amount=Decimal("1.00"),
            dunning_fee=Decimal("5.00"),
            total_amount=Decimal("106.00"),  # Ohne Pauschale
            payment_deadline=date.today() + timedelta(days=10),
            # b2b_pauschale nicht gesetzt
        )

        assert data.b2b_pauschale is None


class TestJinja2Filters:
    """Tests fuer die Jinja2 Custom Filter."""

    @pytest.fixture
    def service(self) -> DunningLetterService:
        return DunningLetterService()

    def test_currency_filter_registered(self, service: DunningLetterService):
        """Sollte currency Filter registriert haben."""
        assert "currency" in service._jinja_env.filters

    def test_date_filter_registered(self, service: DunningLetterService):
        """Sollte date Filter registriert haben."""
        assert "date" in service._jinja_env.filters

    def test_percent_filter_registered(self, service: DunningLetterService):
        """Sollte percent Filter registriert haben."""
        assert "percent" in service._jinja_env.filters

    def test_currency_filter_output(self, service: DunningLetterService):
        """Sollte Waehrung korrekt formatieren."""
        currency_filter = service._jinja_env.filters["currency"]
        result = currency_filter(Decimal("1234.56"))

        # Deutsches Format
        assert "EUR" in result
        assert "1.234,56" in result

    def test_date_filter_output(self, service: DunningLetterService):
        """Sollte Datum korrekt formatieren."""
        date_filter = service._jinja_env.filters["date"]
        result = date_filter(date(2024, 3, 15))

        # Deutsches Format DD.MM.YYYY
        assert result == "15.03.2024"

    def test_percent_filter_output(self, service: DunningLetterService):
        """Sollte Prozentsatz korrekt formatieren."""
        percent_filter = service._jinja_env.filters["percent"]
        result = percent_filter(Decimal("12.62"))

        # Deutsches Format mit Komma
        assert "12,62" in result
        assert "%" in result

    def test_currency_filter_none(self, service: DunningLetterService):
        """Sollte None als 0,00 EUR formatieren."""
        currency_filter = service._jinja_env.filters["currency"]
        result = currency_filter(None)

        assert result == "0,00 EUR"

    def test_date_filter_none(self, service: DunningLetterService):
        """Sollte None als leeren String formatieren."""
        date_filter = service._jinja_env.filters["date"]
        result = date_filter(None)

        assert result == ""

    def test_percent_filter_none(self, service: DunningLetterService):
        """Sollte None als 0,00 % formatieren."""
        percent_filter = service._jinja_env.filters["percent"]
        result = percent_filter(None)

        assert result == "0,00 %"
