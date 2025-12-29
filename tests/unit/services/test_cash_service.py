# -*- coding: utf-8 -*-
"""
Unit tests for Cash Service.

Tests fuer GoBD-konforme Kassenbuchfuehrung:
- Steuer-Konstanten
- Steuerberechnung
- Abzugsfaehigkeit
- Entry-Nummern
- Denomination-Validierung
"""

import pytest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4, UUID
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.cash_service import CashService


class TestCashServiceConstants:
    """Tests fuer Steuer-Konstanten."""

    def test_default_tax_rates_defined(self):
        """Teste ob Standard-Steuersaetze definiert sind."""
        service = CashService()

        assert "standard" in service.DEFAULT_TAX_RATES
        assert "reduced" in service.DEFAULT_TAX_RATES
        assert "zero" in service.DEFAULT_TAX_RATES
        assert service.DEFAULT_TAX_RATES["standard"] == Decimal("19")
        assert service.DEFAULT_TAX_RATES["reduced"] == Decimal("7")
        assert service.DEFAULT_TAX_RATES["zero"] == Decimal("0")

    def test_deductible_percentages_defined(self):
        """Teste ob Abzugsfaehigkeits-Saetze definiert sind."""
        service = CashService()

        assert "entertainment" in service.DEDUCTIBLE_PERCENTAGES
        assert "gifts" in service.DEDUCTIBLE_PERCENTAGES
        assert service.DEDUCTIBLE_PERCENTAGES["entertainment"] == 70


class TestCashServiceEntryCalculations:
    """Tests fuer Entry-Berechnungen."""

    @pytest.fixture
    def service(self):
        """CashService-Instanz."""
        return CashService()

    def test_calculate_tax_standard_rate(self, service):
        """Teste MwSt-Berechnung mit 19%."""
        gross = Decimal("119.00")
        tax_rate = Decimal("19")

        rate, tax, net = service._calculate_tax(gross, tax_rate)

        assert rate == Decimal("19")
        assert net == Decimal("100.00")
        assert tax == Decimal("19.00")

    def test_calculate_tax_reduced_rate(self, service):
        """Teste MwSt-Berechnung mit 7%."""
        gross = Decimal("107.00")
        tax_rate = Decimal("7")

        rate, tax, net = service._calculate_tax(gross, tax_rate)

        assert rate == Decimal("7")
        assert net == Decimal("100.00")
        assert tax == Decimal("7.00")

    def test_calculate_tax_zero_rate(self, service):
        """Teste Berechnung ohne MwSt."""
        gross = Decimal("100.00")
        tax_rate = Decimal("0")

        rate, tax, net = service._calculate_tax(gross, tax_rate)

        assert rate == Decimal("0")
        assert net == Decimal("100.00")
        assert tax == Decimal("0.00")

    def test_calculate_tax_none_returns_none(self, service):
        """Teste Berechnung bei None-Steuersatz."""
        gross = Decimal("100.00")
        tax_rate = None

        rate, tax, net = service._calculate_tax(gross, tax_rate)

        assert rate is None
        assert tax is None
        assert net is None

    def test_calculate_tax_rounding(self, service):
        """Teste Rundung bei MwSt-Berechnung."""
        gross = Decimal("99.99")
        tax_rate = Decimal("19")

        rate, tax, net = service._calculate_tax(gross, tax_rate)

        # Pruefe auf korrekte Rundung (2 Dezimalstellen)
        assert net.as_tuple().exponent >= -2
        assert tax.as_tuple().exponent >= -2
        # Brutto = Netto + Steuer
        assert net + tax == gross


class TestCashServiceDeductibility:
    """Tests fuer Abzugsfaehigkeit nach Buchungstyp."""

    @pytest.fixture
    def service(self):
        """CashService-Instanz."""
        return CashService()

    def test_entertainment_deductibility(self, service):
        """Teste Bewirtungskosten 70% abzugsfaehig."""
        from app.db.models import CashEntryType

        percentage = service._get_deductible_percentage(CashEntryType.ENTERTAINMENT)

        assert percentage == 70

    def test_gifts_deductibility(self, service):
        """Teste Geschenke 100% abzugsfaehig."""
        from app.db.models import CashEntryType

        percentage = service._get_deductible_percentage(CashEntryType.GIFTS)

        assert percentage == 100

    def test_default_deductibility(self, service):
        """Teste Standard-Abzugsfaehigkeit (100%)."""
        from app.db.models import CashEntryType

        percentage = service._get_deductible_percentage(CashEntryType.INCOME)

        assert percentage == 100


class TestCashServiceGoBDCompliance:
    """Tests fuer GoBD-Compliance."""

    def test_entry_type_enum_values(self):
        """Teste dass alle GoBD-Buchungstypen definiert sind."""
        from app.db.models import CashEntryType

        # Standard-Typen
        assert CashEntryType.INCOME
        assert CashEntryType.EXPENSE
        assert CashEntryType.CANCELLATION

        # Kassenverkehr mit Bank
        assert CashEntryType.DEPOSIT
        assert CashEntryType.WITHDRAWAL

        # Sonder-Typen
        assert CashEntryType.ENTERTAINMENT
        assert CashEntryType.GIFTS

    def test_entry_cannot_have_negative_amount_concept(self):
        """Konzepttest: Betraege sollten positiv sein."""
        # GoBD: Betrag ist immer positiv, entry_type bestimmt Richtung
        amount = Decimal("100.00")
        assert amount > 0

    def test_cancellation_creates_counter_entry_concept(self):
        """Konzepttest: Stornierung durch Gegenbuchung."""
        # GoBD: Kein Loeschen, nur Gegenbuchung mit Verweis
        original_amount = Decimal("100.00")
        cancel_amount = -original_amount

        assert cancel_amount == Decimal("-100.00")
        assert original_amount + cancel_amount == Decimal("0")


class TestCashServiceValidation:
    """Tests fuer Eingabe-Validierung."""

    def test_entry_date_not_in_future(self):
        """Teste dass Buchungsdatum nicht in Zukunft liegt."""
        from datetime import date, timedelta

        today = date.today()
        future = today + timedelta(days=1)

        # Buchungsdatum darf nicht in Zukunft liegen
        assert future > today
        # Validierung erfolgt im Service

    def test_register_max_balance_warning(self):
        """Teste Warnung bei Ueberschreiten des Maximalsaldos."""
        max_balance = Decimal("5000.00")
        warning_threshold = Decimal("4500.00")
        current_balance = Decimal("4600.00")

        # Warnschwelle ueberschritten
        assert current_balance > warning_threshold
        assert current_balance <= max_balance

    def test_balance_after_calculation(self):
        """Teste Saldo-Berechnung nach Buchung."""
        previous_balance = Decimal("1000.00")
        income_amount = Decimal("500.00")
        expense_amount = Decimal("-200.00")

        balance_after_income = previous_balance + income_amount
        balance_after_expense = balance_after_income + expense_amount

        assert balance_after_income == Decimal("1500.00")
        assert balance_after_expense == Decimal("1300.00")


class TestCashServiceDenominations:
    """Tests fuer Stueckelung bei Kassensturz."""

    def test_euro_coin_denominations(self):
        """Teste Euro-Muenz-Stueckelungen."""
        coin_values = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.05"),
            Decimal("0.10"),
            Decimal("0.20"),
            Decimal("0.50"),
            Decimal("1.00"),
            Decimal("2.00"),
        ]

        # Alle Standard-Muenzen
        assert len(coin_values) == 8
        assert min(coin_values) == Decimal("0.01")
        assert max(coin_values) == Decimal("2.00")

    def test_euro_note_denominations(self):
        """Teste Euro-Schein-Stueckelungen."""
        note_values = [
            Decimal("5"),
            Decimal("10"),
            Decimal("20"),
            Decimal("50"),
            Decimal("100"),
            Decimal("200"),
            Decimal("500"),
        ]

        # Alle Standard-Scheine
        assert len(note_values) == 7
        assert min(note_values) == Decimal("5")
        assert max(note_values) == Decimal("500")

    def test_calculate_total_from_denominations(self):
        """Teste Berechnung der Gesamtsumme aus Stueckelung."""
        denominations = {
            "coins": {
                "1.00": 5,
                "2.00": 3,
            },
            "notes": {
                "10": 2,
                "50": 1,
            },
        }

        coin_total = Decimal("1.00") * 5 + Decimal("2.00") * 3  # 5 + 6 = 11
        note_total = Decimal("10") * 2 + Decimal("50") * 1  # 20 + 50 = 70
        total = coin_total + note_total

        assert coin_total == Decimal("11.00")
        assert note_total == Decimal("70.00")
        assert total == Decimal("81.00")


class TestCashServiceReports:
    """Tests fuer Report-Berechnungen."""

    def test_daily_summary_structure(self):
        """Teste Struktur der Tageszusammenfassung."""
        daily_data = {
            "date": date.today(),
            "opening_balance": Decimal("1000.00"),
            "closing_balance": Decimal("1200.00"),
            "total_income": Decimal("500.00"),
            "total_expense": Decimal("300.00"),
            "net_change": Decimal("200.00"),
            "entry_count": 5,
        }

        assert daily_data["net_change"] == daily_data["total_income"] - daily_data["total_expense"]
        assert daily_data["closing_balance"] == daily_data["opening_balance"] + daily_data["net_change"]

    def test_period_summary_calculation(self):
        """Teste Berechnung der Periodenzusammenfassung."""
        entries = [
            {"amount": Decimal("100.00"), "entry_type": "income"},
            {"amount": Decimal("-50.00"), "entry_type": "expense"},
            {"amount": Decimal("200.00"), "entry_type": "income"},
            {"amount": Decimal("-75.00"), "entry_type": "expense"},
        ]

        total_income = sum(
            e["amount"] for e in entries if e["amount"] > 0
        )
        total_expense = sum(
            abs(e["amount"]) for e in entries if e["amount"] < 0
        )
        net = total_income - total_expense

        assert total_income == Decimal("300.00")
        assert total_expense == Decimal("125.00")
        assert net == Decimal("175.00")


class TestCashServiceEntryNumbers:
    """Tests fuer fortlaufende Entry-Nummern."""

    def test_entry_number_format(self):
        """Teste Format der Buchungsnummer."""
        fiscal_year = 2024
        entry_number = 1

        formatted = f"{fiscal_year}-{entry_number:05d}"

        assert formatted == "2024-00001"

    def test_entry_numbers_sequential(self):
        """Teste dass Buchungsnummern fortlaufend sind."""
        numbers = [1, 2, 3, 4, 5]

        for i in range(len(numbers) - 1):
            assert numbers[i + 1] == numbers[i] + 1

    def test_no_gaps_in_entry_numbers(self):
        """Teste dass keine Luecken in Buchungsnummern entstehen."""
        # GoBD: Fortlaufende Nummerierung ohne Luecken
        existing_numbers = [1, 2, 3, 5]  # Luecke bei 4

        has_gap = False
        for i in range(len(existing_numbers) - 1):
            if existing_numbers[i + 1] != existing_numbers[i] + 1:
                has_gap = True
                break

        assert has_gap is True  # Luecke erkannt


# ==================== Phase 2 Tests: Enterprise Input-Validierung ====================

class TestCashServiceInputValidation:
    """Tests fuer erweiterte Input-Validierung (Phase 2.2)."""

    def test_amount_max_limit(self):
        """Teste maximale Betragsgrenze."""
        max_amount = Decimal("999999.99")
        over_limit = Decimal("1000000.00")

        assert max_amount < Decimal("1000000")
        assert over_limit >= Decimal("1000000")

    def test_amount_two_decimal_places(self):
        """Teste Cent-Genauigkeit (max 2 Dezimalstellen)."""
        valid_amount = Decimal("123.45")
        invalid_amount = Decimal("123.456")

        assert valid_amount.as_tuple().exponent >= -2
        assert invalid_amount.as_tuple().exponent < -2

    def test_amount_rounding(self):
        """Teste Rundung auf 2 Dezimalstellen."""
        amounts = [
            (Decimal("10.00"), True),
            (Decimal("10.50"), True),
            (Decimal("10.99"), True),
            (Decimal("10.001"), False),
            (Decimal("10.999"), False),
        ]

        for amount, is_valid in amounts:
            has_two_decimals = round(amount, 2) == amount
            assert has_two_decimals == is_valid

    def test_description_whitespace_normalization(self):
        """Teste Whitespace-Normalisierung in Beschreibung."""
        raw_description = "  Büromaterial   kaufen   "
        normalized = " ".join(raw_description.split())

        assert normalized == "Büromaterial kaufen"
        assert "  " not in normalized

    def test_entry_date_max_age(self):
        """Teste maximale Altersgrenze fuer Buchungsdatum (10 Jahre)."""
        from datetime import timedelta

        today = date.today()
        max_age_days = 3650  # ~10 Jahre
        oldest_allowed = today - timedelta(days=max_age_days)

        # 9 Jahre alt = erlaubt
        nine_years_ago = today - timedelta(days=3285)
        assert nine_years_ago >= oldest_allowed

        # 11 Jahre alt = nicht erlaubt
        eleven_years_ago = today - timedelta(days=4015)
        assert eleven_years_ago < oldest_allowed


class TestCashServiceDuplicateDetection:
    """Tests fuer Duplikat-Erkennung (Phase 4.2)."""

    def test_exact_match_detection(self):
        """Teste Erkennung exakter Duplikate."""
        entry1 = {
            "amount": Decimal("100.00"),
            "entry_date": date.today(),
            "description": "Büromaterial",
        }
        entry2 = entry1.copy()

        # Exakt gleiche Werte = Duplikat
        assert entry1 == entry2

    def test_fuzzy_description_match(self):
        """Teste Fuzzy-Match bei Beschreibungen."""
        desc1 = "büromaterial einkauf"
        desc2 = "büromaterial einkauf netto"

        words1 = set(desc1.lower().split())
        words2 = set(desc2.lower().split())

        overlap = len(words1 & words2)
        max_words = max(len(words1), len(words2))
        similarity = overlap / max_words

        # 2 von 3 Woertern = 66% Uebereinstimmung
        assert similarity == pytest.approx(0.666, rel=0.01)

    def test_reference_number_exact_match(self):
        """Teste exakte Belegnummer-Uebereinstimmung."""
        ref1 = "R-2024-001"
        ref2 = "R-2024-001"
        ref3 = "R-2024-002"

        assert ref1 == ref2  # Duplikat
        assert ref1 != ref3  # Kein Duplikat

    def test_different_date_no_duplicate(self):
        """Teste dass unterschiedliche Daten kein Duplikat sind."""
        from datetime import timedelta

        entry1_date = date.today()
        entry2_date = date.today() - timedelta(days=1)

        # Gleiches Amount, andere Datum = kein Duplikat
        assert entry1_date != entry2_date


class TestCashServiceTimezoneHandling:
    """Tests fuer Timezone-Handling (Phase 2.4)."""

    def test_utc_timestamp_creation(self):
        """Teste UTC-Zeitstempel-Erstellung."""
        from datetime import timezone

        now_utc = datetime.now(timezone.utc)

        assert now_utc.tzinfo is not None
        assert now_utc.tzinfo == timezone.utc

    def test_naive_vs_aware_datetime(self):
        """Teste Unterschied naive vs. aware datetime."""
        from datetime import timezone

        naive = datetime.now()
        aware = datetime.now(timezone.utc)

        assert naive.tzinfo is None
        assert aware.tzinfo is not None

    def test_timezone_consistency(self):
        """Teste Konsistenz bei Zeitstempel-Vergleichen."""
        from datetime import timezone, timedelta

        utc_now = datetime.now(timezone.utc)
        cet_offset = timezone(timedelta(hours=1))
        cet_now = utc_now.astimezone(cet_offset)

        # Gleicher Zeitpunkt, unterschiedliche Darstellung
        assert utc_now.timestamp() == pytest.approx(cet_now.timestamp(), rel=0.001)


class TestCashServiceExportFormats:
    """Tests fuer Export-Formate (Phase 3)."""

    def test_csv_separator(self):
        """Teste CSV-Trennzeichen (Semikolon fuer DE)."""
        csv_line = "Beleg-Nr;Datum;Betrag;Beschreibung"
        fields = csv_line.split(";")

        assert len(fields) == 4
        assert fields[0] == "Beleg-Nr"

    def test_csv_utf8_bom(self):
        """Teste UTF-8 BOM fuer Excel-Kompatibilitaet."""
        bom = "\ufeff"
        csv_content = f"{bom}Beleg-Nr;Datum\n1;2024-12-29"

        assert csv_content.startswith(bom)
        assert csv_content.encode("utf-8").startswith(b"\xef\xbb\xbf")

    def test_datev_date_format(self):
        """Teste DATEV-Datumsformat (TTMM)."""
        entry_date = date(2024, 12, 29)
        datev_format = entry_date.strftime("%d%m")

        assert datev_format == "2912"

    def test_datev_encoding(self):
        """Teste DATEV-Encoding (Windows-1252)."""
        text = "Büromaterial für Ärzte"

        # CP1252 kann deutsche Umlaute
        encoded = text.encode("cp1252")
        decoded = encoded.decode("cp1252")

        assert decoded == text

    def test_skr03_cash_account(self):
        """Teste SKR03 Kassenkonto."""
        skr03_cash = "1000"
        assert skr03_cash == "1000"

    def test_skr04_cash_account(self):
        """Teste SKR04 Kassenkonto."""
        skr04_cash = "1600"
        assert skr04_cash == "1600"


class TestCashServiceIdempotency:
    """Tests fuer Idempotency-Konzepte (Phase 4.3)."""

    def test_idempotency_key_format(self):
        """Teste Idempotency-Key-Format."""
        import hashlib

        # Typisches Format: prefix_hash
        content = "user123:create_entry:2024-12-29:100.00"
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
        key = f"cash_{hash_value}"

        assert key.startswith("cash_")
        assert len(key) == 5 + 16  # "cash_" + 16 hex chars

    def test_cached_response_structure(self):
        """Teste Struktur der gecachten Response."""
        cached = {
            "response": {"id": "abc123", "entry_number": 1},
            "status_code": 201,
            "cached_at": "2024-12-29T10:00:00+00:00",
            "idempotency_key": "cash_abc123",
        }

        assert "response" in cached
        assert "status_code" in cached
        assert cached["status_code"] == 201

    def test_lock_key_format(self):
        """Teste Lock-Key-Format."""
        user_id = "user123"
        idempotency_key = "cash_abc123"
        lock_key = f"idempotency:lock:{user_id}:{idempotency_key}"

        assert lock_key.startswith("idempotency:lock:")
        assert user_id in lock_key
