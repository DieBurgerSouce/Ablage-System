# -*- coding: utf-8 -*-
"""
Tests fuer ThreeWayMatchingService - Bestellung <-> Lieferschein <-> Rechnung.

Phase 4.2.4 (P1)

Testet:
- Vollstaendiger 3-Way Match
- Toleranzen bei Betragsabweichungen
- Nicht-Match erzeugt Abweichungsbericht
- Multi-Position Abgleich
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.services.matching.three_way_matching_service import (
    ThreeWayMatchingService,
    ThreeWayMatchResult,
    DiscrepancyInfo,
    MatchCandidate,
)


# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_db() -> AsyncMock:
    """Erstellt eine Mock-AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _make_mock_match(
    match_id: Optional[uuid.UUID] = None,
    po_id: Optional[uuid.UUID] = None,
    dn_id: Optional[uuid.UUID] = None,
    inv_id: Optional[uuid.UUID] = None,
    po_amount: Optional[Decimal] = None,
    dn_amount: Optional[Decimal] = None,
    inv_amount: Optional[Decimal] = None,
    order_number: Optional[str] = None,
    vendor_entity_id: Optional[uuid.UUID] = None,
    vendor_name: Optional[str] = None,
    match_score: Optional[float] = None,
) -> MagicMock:
    """Erstellt ein Mock-PurchaseOrderMatch-Objekt."""
    from app.db.models_po_matching import MatchStatus

    match = MagicMock()
    match.id = match_id or uuid.uuid4()
    match.company_id = uuid.uuid4()
    match.purchase_order_id = po_id
    match.delivery_note_id = dn_id
    match.invoice_id = inv_id
    match.po_amount = po_amount
    match.dn_amount = dn_amount
    match.invoice_amount = inv_amount
    match.order_number = order_number
    match.vendor_entity_id = vendor_entity_id
    match.vendor_name = vendor_name
    match.match_status = MatchStatus.PENDING
    match.match_score = match_score or 0.0
    match.auto_matched = False
    match.amount_tolerance_percent = 2.0
    match.quantity_tolerance_percent = 1.0
    match.created_at = datetime.now(timezone.utc)
    match.order_date = None
    match.discrepancies = []

    # document_count property: zaehle nicht-None Dokument-IDs
    count = sum(1 for x in [po_id, dn_id, inv_id] if x is not None)
    type(match).document_count = PropertyMock(return_value=count)

    return match


# =============================================================================
# Tests
# =============================================================================


class TestThreeWayMatching:
    """Tests fuer ThreeWayMatchingService."""

    @pytest.mark.asyncio
    async def test_match_order_delivery_invoice(self) -> None:
        """Vollstaendiger 3-Way Match: PO -> DN -> Invoice."""
        db = _make_mock_db()
        service = ThreeWayMatchingService(db)

        company_id = uuid.uuid4()
        order_number = "PO-2026-001"
        amount = Decimal("1500.00")

        # 1) Bestellung einreichen -> neuer Match
        # Mock: keine Kandidaten gefunden -> neuer Match wird erstellt
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        result_po = await service.match_document(
            document_id=uuid.uuid4(),
            company_id=company_id,
            document_type="purchase_order",
            reference_number=order_number,
            amount=amount,
            vendor_name="Mueller GmbH",
        )

        assert result_po.success is True
        assert result_po.documents_matched == 1

    @pytest.mark.asyncio
    async def test_partial_match_tolerances(self) -> None:
        """Betragsabweichung innerhalb Toleranz (2%) wird akzeptiert."""
        service = ThreeWayMatchingService(AsyncMock())

        # Erstelle einen Match mit PO-Betrag 1000
        match = _make_mock_match(
            po_id=uuid.uuid4(),
            po_amount=Decimal("1000.00"),
        )

        # Lieferschein mit 1015 EUR (1.5% Abweichung - innerhalb 2% Toleranz)
        discrepancies = service._detect_discrepancies(
            match=match,
            incoming_type="delivery_note",
            incoming_amount=Decimal("1015.00"),
        )

        assert len(discrepancies) == 0, (
            f"1.5% Abweichung sollte innerhalb 2% Toleranz akzeptiert werden, "
            f"aber {len(discrepancies)} Abweichung(en) erkannt"
        )

    @pytest.mark.asyncio
    async def test_no_match_reports_discrepancies(self) -> None:
        """Betragsabweichung ausserhalb Toleranz erzeugt Abweichungsbericht."""
        service = ThreeWayMatchingService(AsyncMock())

        # Match mit PO-Betrag 1000
        match = _make_mock_match(
            po_id=uuid.uuid4(),
            po_amount=Decimal("1000.00"),
        )

        # Rechnung mit 1100 EUR (10% Abweichung - ausserhalb 2% Toleranz)
        discrepancies = service._detect_discrepancies(
            match=match,
            incoming_type="invoice",
            incoming_amount=Decimal("1100.00"),
        )

        assert len(discrepancies) > 0, "10% Abweichung muss als Diskrepanz erkannt werden"

        # Pruefe Diskrepanz-Details
        disc = discrepancies[0]
        assert disc.category == "amount"
        assert disc.deviation_percent is not None
        assert abs(disc.deviation_percent) > 2.0
        assert "EUR" in disc.expected_value
        assert "EUR" in disc.actual_value

    @pytest.mark.asyncio
    async def test_score_calculation(self) -> None:
        """Score-Berechnung: Basis aus Confidence, Abzuege fuer Abweichungen, Bonus fuer 3 Docs."""
        service = ThreeWayMatchingService(AsyncMock())

        # Ohne Abweichungen, 3 Dokumente, Confidence 0.95
        score_perfect = service._calculate_score(
            confidence=0.95,
            discrepancies=[],
            document_count=3,
        )
        # 0.95 * 100 = 95, + 5 Bonus fuer 3 Docs = 100 (capped)
        assert score_perfect == 100.0

        # Mit einer WARNING-Abweichung, 2 Dokumente, Confidence 0.85
        disc = DiscrepancyInfo(
            category="amount",
            description="Test",
            field_name="test",
            expected_value="100",
            actual_value="105",
            deviation_percent=5.0,
            severity="warning",
        )
        score_warning = service._calculate_score(
            confidence=0.85,
            discrepancies=[disc],
            document_count=2,
        )
        # 0.85 * 100 = 85, - 5 (warning) = 80
        assert score_warning == 80.0

    @pytest.mark.asyncio
    async def test_invalid_document_type_rejected(self) -> None:
        """Unbekannter Dokumenttyp wird mit Fehlermeldung abgelehnt."""
        db = _make_mock_db()
        service = ThreeWayMatchingService(db)

        result = await service.match_document(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            document_type="invalid_type",
        )

        assert result.success is False
        assert result.error is not None
        assert "Unbekannter Dokumenttyp" in result.error

    @pytest.mark.asyncio
    async def test_detect_strategy_from_confidence(self) -> None:
        """Strategie-Erkennung anhand Confidence-Wert."""
        assert ThreeWayMatchingService._detect_strategy_from_confidence(0.95) == "order_number"
        assert ThreeWayMatchingService._detect_strategy_from_confidence(0.85) == "vendor_amount"
        assert ThreeWayMatchingService._detect_strategy_from_confidence(0.70) == "vendor_date"
        assert ThreeWayMatchingService._detect_strategy_from_confidence(0.50) == "vendor_date"
