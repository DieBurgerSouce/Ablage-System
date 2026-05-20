# -*- coding: utf-8 -*-
"""Tests fuer SEPACreditTransferService.

Testet SEPA-Ueberweisungen im pain.001 Format:
- Transaktionsvalidierung (IBAN, BIC, Betrag)
- XML-Generierung
- Text-Bereinigung
- XML-Validierung
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, Mock, patch

from app.services.banking.sepa_credit_transfer_service import (
    SEPACreditTransferService,
    SEPACreditTransferTransaction,
    SEPACreditTransferBatch,
    SEPACreditTransferMessage,
    CreditTransferCreate,
    Pain001ExportResult,
    SEPA_ALLOWED_CHARS,
    MAX_NAME_LENGTH,
    MAX_REFERENCE_LENGTH,
)


class TestSEPATransactionValidation:
    """Tests fuer SEPA-Transaktionsvalidierung."""

    def test_valid_transaction(self) -> None:
        """Test: Gueltige Transaktion hat keine Fehler."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Mueller GmbH",
            creditor_iban="DE89370400440532013000",
            remittance_info="Rechnung 12345",
        )
        errors = tx.validate()
        assert len(errors) == 0

    def test_negative_amount(self) -> None:
        """Test: Negativer Betrag wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("-50.00"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
        )
        errors = tx.validate()
        assert any("positiv" in e for e in errors)

    def test_zero_amount(self) -> None:
        """Test: Betrag null wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("0"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
        )
        errors = tx.validate()
        assert any("positiv" in e for e in errors)

    def test_exceeds_max_amount(self) -> None:
        """Test: Ueberschreitung des Maximalbetrags wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("9999999999.99"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
        )
        errors = tx.validate()
        assert any("Maximum" in e for e in errors)

    def test_missing_iban(self) -> None:
        """Test: Fehlende IBAN wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Test GmbH",
            creditor_iban="",
        )
        errors = tx.validate()
        assert any("IBAN" in e for e in errors)

    def test_invalid_iban_format(self) -> None:
        """Test: Ungueltige IBAN wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Test GmbH",
            creditor_iban="INVALIDIBAN",
        )
        errors = tx.validate()
        assert any("IBAN" in e for e in errors)

    def test_valid_iban_mod97(self) -> None:
        """Test: Deutsche IBAN besteht MOD-97 Pruefung."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
        )
        assert tx._validate_iban("DE89370400440532013000") is True

    def test_invalid_bic(self) -> None:
        """Test: Ungueltige BIC wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic="XX",
        )
        errors = tx.validate()
        assert any("BIC" in e for e in errors)

    def test_valid_bic_8_chars(self) -> None:
        """Test: 8-stellige BIC ist gueltig."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
        )
        assert tx._validate_bic("COBADEFF") is True

    def test_valid_bic_11_chars(self) -> None:
        """Test: 11-stellige BIC ist gueltig."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
        )
        assert tx._validate_bic("COBADEFFXXX") is True

    def test_missing_creditor_name(self) -> None:
        """Test: Fehlender Empfaengername wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="",
            creditor_iban="DE89370400440532013000",
        )
        errors = tx.validate()
        assert any("Empfängername" in e or "Empfaengername" in e for e in errors)

    def test_name_too_long(self) -> None:
        """Test: Zu langer Name wird erkannt."""
        tx = SEPACreditTransferTransaction(
            payment_id="TRF-001",
            amount=Decimal("100.00"),
            creditor_name="A" * 71,
            creditor_iban="DE89370400440532013000",
        )
        errors = tx.validate()
        assert any("zu lang" in e for e in errors)


class TestSEPABatchProperties:
    """Tests fuer Batch-Berechnungen."""

    def test_total_amount(self) -> None:
        """Test: Gesamtsumme wird korrekt berechnet."""
        batch = SEPACreditTransferBatch(
            batch_id="BATCH-001",
            debtor_name="Test AG",
            debtor_iban="DE89370400440532013000",
            transactions=[
                SEPACreditTransferTransaction(payment_id="T1", amount=Decimal("100.00")),
                SEPACreditTransferTransaction(payment_id="T2", amount=Decimal("200.50")),
            ],
        )
        assert batch.total_amount == Decimal("300.50")

    def test_transaction_count(self) -> None:
        """Test: Transaktionsanzahl wird korrekt berechnet."""
        batch = SEPACreditTransferBatch(
            batch_id="BATCH-001",
            debtor_name="Test AG",
            debtor_iban="DE89370400440532013000",
            transactions=[
                SEPACreditTransferTransaction(payment_id="T1", amount=Decimal("100.00")),
                SEPACreditTransferTransaction(payment_id="T2", amount=Decimal("200.00")),
                SEPACreditTransferTransaction(payment_id="T3", amount=Decimal("300.00")),
            ],
        )
        assert batch.transaction_count == 3


class TestSEPAMessageProperties:
    """Tests fuer Message-Berechnungen."""

    def test_message_total_across_batches(self) -> None:
        """Test: Gesamtsumme ueber mehrere Batches."""
        msg = SEPACreditTransferMessage(
            message_id="MSG-001",
            created_at=datetime.now(timezone.utc),
            initiating_party_name="Test AG",
            batches=[
                SEPACreditTransferBatch(
                    batch_id="B1", debtor_name="A", debtor_iban="DE89370400440532013000",
                    transactions=[SEPACreditTransferTransaction(payment_id="T1", amount=Decimal("100.00"))],
                ),
                SEPACreditTransferBatch(
                    batch_id="B2", debtor_name="A", debtor_iban="DE89370400440532013000",
                    transactions=[SEPACreditTransferTransaction(payment_id="T2", amount=Decimal("250.00"))],
                ),
            ],
        )
        assert msg.total_amount == Decimal("350.00")
        assert msg.transaction_count == 2


class TestSanitizeText:
    """Tests fuer SEPA-Textbereinigung."""

    @pytest.fixture
    def service(self) -> SEPACreditTransferService:
        """Erstellt Service-Instanz."""
        return SEPACreditTransferService()

    def test_sanitize_umlauts(self, service: SEPACreditTransferService) -> None:
        """Test: Deutsche Umlaute werden korrekt ersetzt."""
        result = service._sanitize_text("Müller Größe Übung straße", 140)
        assert "ae" in result or "Mueller" in result
        assert "oe" in result or "Groesse" in result
        assert "ue" in result or "Uebung" in result
        assert "ss" in result or "strasse" in result

    def test_sanitize_special_chars(self, service: SEPACreditTransferService) -> None:
        """Test: Sonderzeichen werden durch Leerzeichen ersetzt."""
        result = service._sanitize_text("Test@Company#123", 140)
        assert "@" not in result
        assert "#" not in result

    def test_sanitize_truncation(self, service: SEPACreditTransferService) -> None:
        """Test: Zu langer Text wird abgeschnitten."""
        long_text = "A" * 200
        result = service._sanitize_text(long_text, 70)
        assert len(result) <= 70

    def test_sanitize_empty(self, service: SEPACreditTransferService) -> None:
        """Test: Leerer Text bleibt leer."""
        assert service._sanitize_text("", 140) == ""

    def test_sanitize_multiple_spaces(self, service: SEPACreditTransferService) -> None:
        """Test: Mehrfache Leerzeichen werden entfernt."""
        result = service._sanitize_text("Test    Company", 140)
        assert "  " not in result


class TestGenerateXML:
    """Tests fuer XML-Generierung."""

    @pytest.fixture
    def service(self) -> SEPACreditTransferService:
        """Erstellt Service-Instanz."""
        return SEPACreditTransferService()

    def test_xml_contains_declaration(self, service: SEPACreditTransferService) -> None:
        """Test: XML enthaelt Deklaration."""
        msg = SEPACreditTransferMessage(
            message_id="MSG-001",
            created_at=datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            initiating_party_name="Test AG",
            batches=[
                SEPACreditTransferBatch(
                    batch_id="B1",
                    debtor_name="Test AG",
                    debtor_iban="DE89370400440532013000",
                    transactions=[
                        SEPACreditTransferTransaction(
                            payment_id="TRF-001",
                            amount=Decimal("100.00"),
                            creditor_name="Mueller GmbH",
                            creditor_iban="DE89370400440532013000",
                            remittance_info="Rechnung 12345",
                        ),
                    ],
                ),
            ],
        )
        xml = service._generate_pain001_xml(msg)
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_xml_contains_namespace(self, service: SEPACreditTransferService) -> None:
        """Test: XML enthaelt pain.001 Namespace."""
        msg = SEPACreditTransferMessage(
            message_id="MSG-001",
            created_at=datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            initiating_party_name="Test AG",
            batches=[
                SEPACreditTransferBatch(
                    batch_id="B1",
                    debtor_name="Test AG",
                    debtor_iban="DE89370400440532013000",
                    transactions=[
                        SEPACreditTransferTransaction(
                            payment_id="TRF-001",
                            amount=Decimal("100.00"),
                            creditor_name="Mueller GmbH",
                            creditor_iban="DE89370400440532013000",
                        ),
                    ],
                ),
            ],
        )
        xml = service._generate_pain001_xml(msg)
        assert "pain.001" in xml

    def test_xml_contains_amount(self, service: SEPACreditTransferService) -> None:
        """Test: XML enthaelt den Betrag."""
        msg = SEPACreditTransferMessage(
            message_id="MSG-001",
            created_at=datetime.now(timezone.utc),
            initiating_party_name="Test AG",
            batches=[
                SEPACreditTransferBatch(
                    batch_id="B1",
                    debtor_name="Test AG",
                    debtor_iban="DE89370400440532013000",
                    transactions=[
                        SEPACreditTransferTransaction(
                            payment_id="TRF-001",
                            amount=Decimal("1234.56"),
                            creditor_name="Test GmbH",
                            creditor_iban="DE89370400440532013000",
                        ),
                    ],
                ),
            ],
        )
        xml = service._generate_pain001_xml(msg)
        assert "1234.56" in xml

    def test_xml_instant_payment(self, service: SEPACreditTransferService) -> None:
        """Test: SEPA Instant enthalt INST Instrument."""
        msg = SEPACreditTransferMessage(
            message_id="MSG-001",
            created_at=datetime.now(timezone.utc),
            initiating_party_name="Test AG",
            batches=[
                SEPACreditTransferBatch(
                    batch_id="B1",
                    debtor_name="Test AG",
                    debtor_iban="DE89370400440532013000",
                    transactions=[
                        SEPACreditTransferTransaction(
                            payment_id="TRF-001",
                            amount=Decimal("50.00"),
                            creditor_name="Test",
                            creditor_iban="DE89370400440532013000",
                        ),
                    ],
                ),
            ],
        )
        xml = service._generate_pain001_xml(msg, is_instant=True)
        assert "INST" in xml


class TestValidatePain001:
    """Tests fuer XML-Validierung."""

    @pytest.fixture
    def service(self) -> SEPACreditTransferService:
        """Erstellt Service-Instanz."""
        return SEPACreditTransferService()

    def test_validate_invalid_xml(self, service: SEPACreditTransferService) -> None:
        """Test: Ungueltiges XML wird erkannt."""
        errors = service.validate_pain001_xml("not valid xml <<<<")
        assert len(errors) > 0

    def test_validate_wrong_root_element(self, service: SEPACreditTransferService) -> None:
        """Test: Falsches Root-Element wird erkannt."""
        xml = '<?xml version="1.0"?><WrongRoot></WrongRoot>'
        errors = service.validate_pain001_xml(xml)
        assert len(errors) > 0
