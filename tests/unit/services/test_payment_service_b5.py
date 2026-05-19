# -*- coding: utf-8 -*-
"""Unit-Tests fuer Banking Payment Service (B5).

Money-Movement-Logik mit IBAN-Validierung (PII) - sicherheitskritisch.
Tests fokussieren auf:
- IBAN-Validierung (Pattern + MOD-97 Pruefziffer)
- BIC-Validierung
- TAN-Format-Validierung
- Betrags-Grenzen (positiv, MAX_SINGLE_PAYMENT)
- Empfaengername-Grenzen (2-70 Zeichen, SEPA Limit)
- Verwendungszweck-Limit (140 Zeichen, SEPA Limit)
- Ausfuehrungsdatum (nicht in Vergangenheit)

Quelle: GOAL_PHASE_B.md B5, MASTER_REVIEW_2026-05-19.md test_gaps.md
"High Priority: payment_service.py - Banking Money-Movement, IBAN-PII".

Hinweis: test_payment_service_b5.py um Konflikt mit moeglich existierendem
test_payment_service.py zu vermeiden - falls beide existieren werden beide
ausgefuehrt.
"""

import pytest
from unittest.mock import Mock
from datetime import date, timedelta


pytestmark = [pytest.mark.unit, pytest.mark.banking]


# =================== Fixtures ===================


@pytest.fixture
def service():
    from app.services.banking.payment_service import PaymentService
    # PaymentService nimmt db als erstes Argument
    return PaymentService()


def _make_payment_data(
    iban="DE89370400440532013000",
    bic="COBADEFFXXX",
    name="Max Mustermann",
    amount=100.00,
    reference="Test Zahlung",
    execution_date=None,
):
    """Erzeuge ein PaymentOrderCreate-aehnliches Mock-Object."""
    pd = Mock()
    pd.beneficiary_iban = iban
    pd.beneficiary_bic = bic
    pd.beneficiary_name = name
    pd.amount = amount
    pd.reference = reference
    pd.execution_date = execution_date
    pd.creditor_iban = None
    pd.creditor_bic = None
    pd.creditor_name = None
    return pd


# =================== IBAN Validation ===================


class TestIBANValidation:
    def test_valid_german_iban_passes(self, service):
        """Standard valide deutsche IBAN."""
        data = _make_payment_data(iban="DE89370400440532013000")
        result = service._validate_payment(data)
        assert "Ungültige IBAN" not in result.errors
        assert "IBAN-Prüfziffer ungültig" not in result.errors

    def test_missing_iban_fails(self, service):
        data = _make_payment_data(iban=None)
        result = service._validate_payment(data)
        assert "IBAN fehlt" in result.errors

    def test_invalid_iban_format_fails(self, service):
        data = _make_payment_data(iban="XYZ123")
        result = service._validate_payment(data)
        # Either pattern or checksum fails
        assert any("IBAN" in e for e in result.errors)

    def test_iban_normalization_handles_spaces(self, service):
        """IBAN mit Leerzeichen wird normalisiert."""
        normalized = service._normalize_iban("DE89 3704 0044 0532 0130 00")
        assert normalized == "DE89370400440532013000"

    def test_iban_normalization_uppercases(self, service):
        normalized = service._normalize_iban("de89370400440532013000")
        assert normalized == "DE89370400440532013000"

    def test_iban_checksum_valid_german(self, service):
        assert service._validate_iban_checksum("DE89370400440532013000") is True

    def test_iban_checksum_invalid_returns_false(self, service):
        # Modify last digit -> Pruefziffer falsch
        assert service._validate_iban_checksum("DE89370400440532013009") is False

    def test_iban_checksum_garbage_returns_false(self, service):
        assert service._validate_iban_checksum("INVALID!!") is False

    def test_iban_checksum_empty_returns_false(self, service):
        assert service._validate_iban_checksum("") is False


# =================== BIC Validation ===================


class TestBICValidation:
    def test_valid_bic_passes(self, service):
        data = _make_payment_data(bic="DEUTDEFFXXX")
        result = service._validate_payment(data)
        assert "Ungültige BIC" not in result.errors

    def test_invalid_bic_fails(self, service):
        data = _make_payment_data(bic="NOT_A_BIC")
        result = service._validate_payment(data)
        assert "Ungültige BIC" in result.errors

    def test_bic_lowercase_accepted(self, service):
        """BIC wird vor Pattern-Match upper-cased."""
        data = _make_payment_data(bic="deutdeffxxx")
        result = service._validate_payment(data)
        assert "Ungültige BIC" not in result.errors

    def test_no_bic_is_ok(self, service):
        """BIC ist optional (SEPA-Inland)."""
        data = _make_payment_data(bic=None)
        result = service._validate_payment(data)
        assert not any("BIC" in e for e in result.errors)


# =================== Amount Validation ===================


class TestAmountValidation:
    def test_positive_amount_passes(self, service):
        data = _make_payment_data(amount=100.00)
        result = service._validate_payment(data)
        assert "Betrag muss positiv sein" not in result.errors

    def test_zero_amount_fails(self, service):
        data = _make_payment_data(amount=0)
        result = service._validate_payment(data)
        assert "Betrag muss positiv sein" in result.errors

    def test_negative_amount_fails(self, service):
        data = _make_payment_data(amount=-50.00)
        result = service._validate_payment(data)
        assert "Betrag muss positiv sein" in result.errors

    def test_exceeds_max_single_payment_warning(self, service):
        """Ueberschreiten von MAX_SINGLE_PAYMENT -> Warnung, kein Error."""
        max_amount = service.MAX_SINGLE_PAYMENT
        data = _make_payment_data(amount=max_amount + 1000)
        result = service._validate_payment(data)
        assert any("überschreitet" in w for w in result.warnings)


# =================== Empfaengername (SEPA 70-Zeichen-Limit) ===================


class TestBeneficiaryName:
    def test_normal_name_passes(self, service):
        data = _make_payment_data(name="Max Mustermann")
        result = service._validate_payment(data)
        assert not any("Empfängername" in e for e in result.errors)

    def test_missing_name_fails(self, service):
        data = _make_payment_data(name=None)
        result = service._validate_payment(data)
        assert any("Empfängername fehlt" in e for e in result.errors)

    def test_too_short_name_fails(self, service):
        data = _make_payment_data(name="X")  # 1 Zeichen
        result = service._validate_payment(data)
        assert any("Empfängername" in e for e in result.errors)

    def test_too_long_name_fails(self, service):
        """SEPA-Limit: 70 Zeichen."""
        data = _make_payment_data(name="X" * 71)
        result = service._validate_payment(data)
        assert any("zu lang" in e for e in result.errors)


# =================== Verwendungszweck (SEPA 140-Zeichen-Limit) ===================


class TestReferenceLimit:
    def test_normal_reference_passes(self, service):
        data = _make_payment_data(reference="Rechnung 2026-001")
        result = service._validate_payment(data)
        assert not any("Verwendungszweck" in e for e in result.errors)

    def test_140_char_reference_passes(self, service):
        data = _make_payment_data(reference="X" * 140)
        result = service._validate_payment(data)
        assert not any("Verwendungszweck" in e for e in result.errors)

    def test_over_140_char_reference_fails(self, service):
        data = _make_payment_data(reference="X" * 141)
        result = service._validate_payment(data)
        assert any("Verwendungszweck" in e for e in result.errors)


# =================== Execution Date ===================


class TestExecutionDate:
    def test_today_passes(self, service):
        data = _make_payment_data(execution_date=date.today())
        result = service._validate_payment(data)
        assert not any("Vergangenheit" in e for e in result.errors)

    def test_past_date_fails(self, service):
        past = date.today() - timedelta(days=1)
        data = _make_payment_data(execution_date=past)
        result = service._validate_payment(data)
        assert any("Vergangenheit" in e for e in result.errors)

    def test_future_within_year_passes(self, service):
        future = date.today() + timedelta(days=30)
        data = _make_payment_data(execution_date=future)
        result = service._validate_payment(data)
        assert not any("Vergangenheit" in e or "Zukunft" in e for e in result.errors)

    def test_far_future_warning(self, service):
        far = date.today() + timedelta(days=400)
        data = _make_payment_data(execution_date=far)
        result = service._validate_payment(data)
        assert any("Zukunft" in w for w in result.warnings)


# =================== TAN Validation ===================


class TestTANValidation:
    def test_valid_6_digit_tan(self, service):
        assert service._validate_tan("123456") is True

    def test_short_tan_fails(self, service):
        assert service._validate_tan("12345") is False

    def test_long_tan_fails(self, service):
        assert service._validate_tan("1234567") is False

    def test_non_numeric_tan_fails(self, service):
        assert service._validate_tan("12345A") is False

    def test_empty_tan_fails(self, service):
        assert service._validate_tan("") is False


# =================== Full Valid Payment ===================


class TestValidPayment:
    def test_complete_valid_payment_has_no_errors(self, service):
        data = _make_payment_data(
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            name="Max Mustermann GmbH",
            amount=1500.00,
            reference="Rechnung 2026-001 Zahlung",
            execution_date=date.today() + timedelta(days=2),
        )
        result = service._validate_payment(data)
        assert result.valid is True
        assert result.errors == []
