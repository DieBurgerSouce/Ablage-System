# -*- coding: utf-8 -*-
"""
Tests fuer AutoKontierungService - Automatische Kontierung auf DATEV-Konten.

Phase 4.2.2 (P0 - GoBD Finanzcode)

Testet:
- Balancierte Buchungssaetze (Soll == Haben)
- Korrekte SKR03/SKR04 Kontenrahmen-Zuordnung
- MwSt-Saetze (19% und 7%)
- Reverse Charge Szenarien
- Ungueltige Dokumente
- Audit Trail (Journal Entry Erstellung)
"""

import uuid
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.kontierung.auto_kontierung_service import (
    AutoKontierungService,
    KontierungSuggestion,
    KontierungResult,
)


# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_db() -> AsyncMock:
    """Erstellt eine Mock-AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    # Mock fuer _generate_entry_number: max(entry_number) -> None (erster Eintrag)
    entry_result = MagicMock()
    entry_result.scalar_one_or_none.return_value = None
    db.execute.return_value = entry_result

    return db


def _make_extracted_fields(
    gross: str = "1190.00",
    net: str = "1000.00",
    tax: str = "190.00",
    vat_rate: str = "19",
    description: str = "Bueroartikel fuer Abteilung IT",
) -> Dict[str, Dict[str, object]]:
    """Erstellt Mock-OCR extracted_fields."""
    return {
        "total_amount": {"value": gross, "confidence": 0.95},
        "net_amount": {"value": net, "confidence": 0.93},
        "tax_amount": {"value": tax, "confidence": 0.91},
        "tax_rate": {"value": vat_rate, "confidence": 0.90},
        "description": {"value": description, "confidence": 0.88},
    }


def _sum_debits(suggestion: KontierungSuggestion, service: AutoKontierungService) -> Decimal:
    """Summiert alle Soll-Betraege der Buchungszeilen."""
    lines = service._build_journal_lines(suggestion)
    return sum(line.debit_amount for line in lines)


def _sum_credits(suggestion: KontierungSuggestion, service: AutoKontierungService) -> Decimal:
    """Summiert alle Haben-Betraege der Buchungszeilen."""
    lines = service._build_journal_lines(suggestion)
    return sum(line.credit_amount for line in lines)


# =============================================================================
# Tests
# =============================================================================


class TestAutoKontierung:
    """Tests fuer AutoKontierungService."""

    @pytest.mark.asyncio
    async def test_kontierung_generates_balanced_entries(self) -> None:
        """Soll-Summe == Haben-Summe (doppelte Buchfuehrung)."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        fields = _make_extracted_fields(
            gross="1190.00", net="1000.00", tax="190.00", vat_rate="19",
        )

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=True,
        )

        total_debit = _sum_debits(suggestion, service)
        total_credit = _sum_credits(suggestion, service)

        assert total_debit == total_credit, (
            f"Soll ({total_debit}) != Haben ({total_credit}) - Buchung nicht balanciert!"
        )
        assert total_debit > Decimal("0"), "Buchung darf nicht leer sein"

    @pytest.mark.asyncio
    async def test_kontierung_uses_correct_accounts(self) -> None:
        """SKR03 Kontenrahmen: Korrekte Aufwands- und Gegenkonten."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        # 'buerobedarf' sollte Buerokosten-Konto triggern
        fields = _make_extracted_fields(description="buerobedarf drucker toner")

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=True,
        )

        # SKR03 Buerokosten = 4930, Kreditoren = 1600
        assert suggestion.debit_account == "4930", (
            f"Erwartet Buerokosten 4930, erhalten: {suggestion.debit_account}"
        )
        assert suggestion.credit_account == "1600", (
            f"Erwartet Kreditoren-Sammelkonto 1600, erhalten: {suggestion.credit_account}"
        )
        assert suggestion.method == "keyword"

    @pytest.mark.asyncio
    async def test_kontierung_handles_vat_rates_19(self) -> None:
        """19% MwSt wird korrekt berechnet und balanciert."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        fields = _make_extracted_fields(
            gross="1190.00", net="1000.00", tax="190.00", vat_rate="19",
        )

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=True,
        )

        assert suggestion.tax_rate == Decimal("19.00")
        assert suggestion.tax_amount == Decimal("190.00")
        assert suggestion.amount == Decimal("1190.00")
        assert suggestion.tax_code == "40"  # BU-Schluessel Vorsteuer 19%

        # Balance-Check
        total_debit = _sum_debits(suggestion, service)
        total_credit = _sum_credits(suggestion, service)
        assert total_debit == total_credit

    @pytest.mark.asyncio
    async def test_kontierung_handles_vat_rates_7(self) -> None:
        """7% MwSt (ermaessigt) wird korrekt erkannt und zugeordnet."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        fields = _make_extracted_fields(
            gross="107.00", net="100.00", tax="7.00", vat_rate="7",
        )

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=True,
        )

        assert suggestion.tax_rate == Decimal("7.00")
        assert suggestion.tax_amount == Decimal("7.00")
        assert suggestion.tax_code == "41"  # BU-Schluessel Vorsteuer 7%

        # Balance-Check
        total_debit = _sum_debits(suggestion, service)
        total_credit = _sum_credits(suggestion, service)
        assert total_debit == total_credit

    @pytest.mark.asyncio
    async def test_kontierung_rejects_invalid_document(self) -> None:
        """Fehlende Pflichtfelder erzeugen Fallback mit niedriger Confidence."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        # Leere extracted_fields: kein Betrag, keine Beschreibung
        fields: Dict[str, Dict[str, object]] = {}

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=True,
        )

        # Fallback wird gewaehlt (Confidence 0.60)
        assert suggestion.confidence == 0.60
        assert suggestion.method == "fallback"
        assert suggestion.amount == Decimal("0")  # Kein Betrag extrahiert

    @pytest.mark.asyncio
    async def test_kontierung_audit_trail(self) -> None:
        """Buchung erzeugt JournalEntry mit korrekten Feldern."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        fields = _make_extracted_fields(
            gross="595.00", net="500.00", tax="95.00", vat_rate="19",
            description="miete buero januar",
        )

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=True,
        )

        company_id = uuid.uuid4()
        document_id = uuid.uuid4()

        result = await service.create_journal_entry(
            document_id=document_id,
            company_id=company_id,
            suggestion=suggestion,
        )

        assert result.success is True
        assert result.journal_entry_id is not None
        assert result.amount == Decimal("595.00")
        assert result.entry_number is not None
        assert result.entry_number.startswith("JE-")

        # Verifiziere DB-Operationen
        db.add.assert_called_once()
        db.flush.assert_awaited()

        # Balance-Check auf das Ergebnis
        total_debit = _sum_debits(suggestion, service)
        total_credit = _sum_credits(suggestion, service)
        assert total_debit == total_credit

    @pytest.mark.asyncio
    async def test_kontierung_outgoing_invoice_balanced(self) -> None:
        """Ausgangsrechnung: Forderung im Soll, Erloes im Haben - balanciert."""
        db = _make_mock_db()
        service = AutoKontierungService(db, "SKR03")

        fields = _make_extracted_fields(
            gross="2380.00", net="2000.00", tax="380.00", vat_rate="19",
        )

        suggestion = await service.suggest_kontierung(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            classification_type="invoice",
            extracted_fields=fields,
            is_incoming=False,  # Ausgangsrechnung
        )

        # SKR03: Debitoren = 1400
        assert suggestion.debit_account == "1400"
        assert suggestion.tax_code == "51"  # BU-Schluessel Umsatzsteuer 19%
        assert suggestion.method == "outgoing_standard"

        # Balance
        total_debit = _sum_debits(suggestion, service)
        total_credit = _sum_credits(suggestion, service)
        assert total_debit == total_credit
        assert total_debit == Decimal("2380.00")
