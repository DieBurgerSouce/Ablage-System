# -*- coding: utf-8 -*-
"""Tests fuer DocumentChainService.

Testet Auftragsketten-Tracking (Angebot -> Auftrag -> Lieferschein -> Rechnung).
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.document_chain_service import (
    DocumentChainService,
    ChainMatchResult,
    ChainDiscrepancy,
    DocumentChain,
    RelationshipType,
    DiscrepancyType,
    DiscrepancySeverity,
    CHAIN_POSITIONS,
)


class TestChainPositions:
    """Tests fuer Chain-Positionslogik."""

    def test_chain_positions_defined(self) -> None:
        """Test: Alle Dokumenttypen haben Positionen."""
        assert "quote" in CHAIN_POSITIONS
        assert "order" in CHAIN_POSITIONS
        assert "delivery_note" in CHAIN_POSITIONS
        assert "invoice" in CHAIN_POSITIONS
        assert "credit_note" in CHAIN_POSITIONS

    def test_chain_positions_ordering(self) -> None:
        """Test: Positionen sind korrekt geordnet."""
        assert CHAIN_POSITIONS["quote"] < CHAIN_POSITIONS["order"]
        assert CHAIN_POSITIONS["order"] < CHAIN_POSITIONS["delivery_note"]
        assert CHAIN_POSITIONS["delivery_note"] < CHAIN_POSITIONS["invoice"]
        assert CHAIN_POSITIONS["invoice"] < CHAIN_POSITIONS["credit_note"]


class TestCreateChain:
    """Tests fuer create_chain Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_chain_requires_documents(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Leere Dokumentenliste wird abgelehnt."""
        with pytest.raises(ValueError, match="Mindestens ein Dokument"):
            await service.create_chain(
                db=mock_db,
                documents=[],
                company_id=uuid4(),
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_create_chain_with_custom_id(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Kette mit vorgegebener ID erstellen."""
        company_id = uuid4()
        user_id = uuid4()
        doc_id = uuid4()
        custom_chain_id = "CHAIN-2026-00001"

        # Mock document
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.document_type = "invoice"
        mock_doc.chain_id = None
        mock_doc.chain_position = None

        # Mock db.execute for document lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_db.execute.return_value = mock_result

        chain_id = await service.create_chain(
            db=mock_db,
            documents=[doc_id],
            company_id=company_id,
            user_id=user_id,
            chain_id=custom_chain_id,
        )

        assert chain_id == custom_chain_id
        assert mock_doc.chain_id == custom_chain_id


class TestLinkDocuments:
    """Tests fuer link_documents Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_link_documents_not_found(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Nicht existierende Dokumente abgelehnt."""
        source_id = uuid4()
        target_id = uuid4()

        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.link_documents(
                db=mock_db,
                source_document_id=source_id,
                target_document_id=target_id,
                relationship_type=RelationshipType.QUOTE_TO_ORDER,
                company_id=uuid4(),
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_link_documents_different_company(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Dokumente verschiedener Firmen nicht verknuepfbar."""
        source_id = uuid4()
        target_id = uuid4()
        company_id = uuid4()

        # Mock source doc with different company
        mock_source = MagicMock()
        mock_source.id = source_id
        mock_source.company_id = uuid4()  # Different company

        mock_target = MagicMock()
        mock_target.id = target_id
        mock_target.company_id = company_id

        mock_db.get.side_effect = [mock_source, mock_target]

        with pytest.raises(ValueError, match="selben Firma"):
            await service.link_documents(
                db=mock_db,
                source_document_id=source_id,
                target_document_id=target_id,
                relationship_type=RelationshipType.QUOTE_TO_ORDER,
                company_id=company_id,
                user_id=uuid4(),
            )


class TestAutoMatching:
    """Tests fuer automatisches Matching."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_auto_match_document_not_found(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Nicht existierendes Dokument liefert leere Liste."""
        document_id = uuid4()
        company_id = uuid4()

        mock_db.get.return_value = None

        matches = await service.auto_match_documents(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert len(matches) == 0


class TestGetChain:
    """Tests fuer get_chain Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_chain_not_found(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Nicht existierende Kette liefert None."""
        chain_id = "CHAIN-2026-00001"
        company_id = uuid4()

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        chain = await service.get_chain(
            db=mock_db,
            chain_id=chain_id,
            company_id=company_id,
        )

        assert chain is None


class TestRelationshipTypes:
    """Tests fuer Beziehungstypen."""

    def test_all_relationship_types_exist(self) -> None:
        """Test: Alle Beziehungstypen definiert."""
        assert RelationshipType.QUOTE_TO_ORDER is not None
        assert RelationshipType.ORDER_TO_DELIVERY is not None
        assert RelationshipType.DELIVERY_TO_INVOICE is not None
        assert RelationshipType.INVOICE_TO_CREDIT is not None
        assert RelationshipType.ORDER_TO_INVOICE is not None
        assert RelationshipType.QUOTE_TO_INVOICE is not None
        assert RelationshipType.RELATED is not None

    def test_relationship_type_values(self) -> None:
        """Test: Beziehungstypen haben korrekte Werte."""
        assert RelationshipType.QUOTE_TO_ORDER.value == "quote_to_order"
        assert RelationshipType.ORDER_TO_DELIVERY.value == "order_to_delivery"
        assert RelationshipType.DELIVERY_TO_INVOICE.value == "delivery_to_invoice"


class TestDiscrepancyTypes:
    """Tests fuer Abweichungstypen."""

    def test_all_discrepancy_types_exist(self) -> None:
        """Test: Alle Abweichungstypen definiert."""
        assert DiscrepancyType.AMOUNT_MISMATCH is not None
        assert DiscrepancyType.QUANTITY_MISMATCH is not None
        assert DiscrepancyType.MISSING_POSITION is not None
        assert DiscrepancyType.EXTRA_POSITION is not None
        assert DiscrepancyType.DATE_INCONSISTENCY is not None
        assert DiscrepancyType.CUSTOMER_MISMATCH is not None
        assert DiscrepancyType.REFERENCE_MISMATCH is not None

    def test_severity_levels(self) -> None:
        """Test: Schweregrade definiert."""
        assert DiscrepancySeverity.INFO is not None
        assert DiscrepancySeverity.WARNING is not None
        assert DiscrepancySeverity.ERROR is not None
        assert DiscrepancySeverity.CRITICAL is not None


class TestGetDiscrepancies:
    """Tests fuer get_chain_discrepancies Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_discrepancies_empty(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Keine Abweichungen liefert leere Liste."""
        chain_id = "CHAIN-2026-00001"
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        discrepancies = await service.get_chain_discrepancies(
            db=mock_db,
            chain_id=chain_id,
            company_id=company_id,  # Multi-Tenant Security
            include_resolved=False,
        )

        assert len(discrepancies) == 0

    @pytest.mark.asyncio
    async def test_get_discrepancies_with_resolved(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Include resolved parameter wird beruecksichtigt."""
        chain_id = "CHAIN-2026-00001"
        company_id = uuid4()

        # Create mock discrepancy (using model field names)
        mock_disc = MagicMock()
        mock_disc.id = uuid4()
        mock_disc.chain_id = chain_id
        mock_disc.source_document_id = uuid4()
        mock_disc.target_document_id = uuid4()
        mock_disc.discrepancy_type = "amount_mismatch"
        mock_disc.field_name = "total_amount"
        mock_disc.expected_value = "1000.00"  # Model uses expected_value
        mock_disc.actual_value = "1100.00"    # Model uses actual_value
        mock_disc.difference_percentage = 10.0
        mock_disc.severity = "warning"
        mock_disc.is_resolved = True          # Model uses is_resolved
        mock_disc.created_at = datetime.now(timezone.utc)  # Model uses created_at

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_disc]
        mock_db.execute.return_value = mock_result

        discrepancies = await service.get_chain_discrepancies(
            db=mock_db,
            chain_id=chain_id,
            company_id=company_id,  # Multi-Tenant Security
            include_resolved=True,
        )

        assert len(discrepancies) == 1
        assert discrepancies[0].is_resolved is True


class TestResolveDiscrepancy:
    """Tests fuer resolve_discrepancy Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_resolve_discrepancy_not_found(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Nicht existierende Abweichung oder falsche Firma liefert False."""
        discrepancy_id = uuid4()
        company_id = uuid4()  # Multi-Tenant Security
        user_id = uuid4()

        # Mock: scalar_one_or_none liefert None (nicht gefunden oder falsche Firma)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success = await service.resolve_discrepancy(
            db=mock_db,
            discrepancy_id=discrepancy_id,
            company_id=company_id,  # Multi-Tenant Security
            user_id=user_id,
        )

        assert success is False

    @pytest.mark.asyncio
    async def test_resolve_discrepancy_success(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Abweichung erfolgreich loesen."""
        discrepancy_id = uuid4()
        company_id = uuid4()  # Multi-Tenant Security
        user_id = uuid4()

        mock_discrepancy = MagicMock()
        mock_discrepancy.id = discrepancy_id
        mock_discrepancy.company_id = company_id  # Must match
        mock_discrepancy.is_resolved = False  # Model uses is_resolved
        mock_discrepancy.chain_id = "CHAIN-2026-00001"

        # Mock: scalar_one_or_none liefert die Discrepancy
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_discrepancy
        mock_db.execute.return_value = mock_result

        success = await service.resolve_discrepancy(
            db=mock_db,
            discrepancy_id=discrepancy_id,
            company_id=company_id,  # Multi-Tenant Security
            user_id=user_id,
            resolution_notes="Preisanpassung genehmigt",
        )

        assert success is True
        assert mock_discrepancy.is_resolved is True  # Model uses is_resolved
        assert mock_discrepancy.resolved_by_id == user_id


class TestInferRelationship:
    """Tests fuer _infer_relationship Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    def test_infer_order_number(self, service: DocumentChainService) -> None:
        """Test: order_number -> ORDER_TO_INVOICE."""
        result = service._infer_relationship("order_number")
        assert result == RelationshipType.ORDER_TO_INVOICE

    def test_infer_quotation_number(self, service: DocumentChainService) -> None:
        """Test: quotation_number -> QUOTE_TO_ORDER."""
        result = service._infer_relationship("quotation_number")
        assert result == RelationshipType.QUOTE_TO_ORDER

    def test_infer_delivery_note_number(self, service: DocumentChainService) -> None:
        """Test: delivery_note_number -> DELIVERY_TO_INVOICE."""
        result = service._infer_relationship("delivery_note_number")
        assert result == RelationshipType.DELIVERY_TO_INVOICE

    def test_infer_unknown(self, service: DocumentChainService) -> None:
        """Test: Unbekannter Typ -> RELATED."""
        result = service._infer_relationship("unknown_field")
        assert result == RelationshipType.RELATED


class TestServiceConstants:
    """Tests fuer Service-Konstanten."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    def test_amount_tolerance(self, service: DocumentChainService) -> None:
        """Test: Betrags-Toleranz definiert."""
        assert service.AMOUNT_TOLERANCE_PERCENT == 1.0

    def test_min_confidence(self, service: DocumentChainService) -> None:
        """Test: Min-Konfidenz definiert."""
        assert service.MIN_CONFIDENCE_AUTO == 0.85


class TestChainMatchResult:
    """Tests fuer ChainMatchResult Dataclass."""

    def test_match_result_creation(self) -> None:
        """Test: MatchResult korrekt erstellen."""
        result = ChainMatchResult(
            matched=True,
            chain_id="CHAIN-2026-00001",
            relationship_type=RelationshipType.ORDER_TO_INVOICE,
            confidence=0.95,
            matched_documents=[uuid4()],
            match_reason="Gleiche Bestellnummer",
        )

        assert result.matched is True
        assert result.confidence == 0.95

    def test_match_result_no_match(self) -> None:
        """Test: MatchResult fuer keine Uebereinstimmung."""
        result = ChainMatchResult(
            matched=False,
            chain_id=None,
            relationship_type=None,
            confidence=0.0,
            matched_documents=[],
            match_reason="Keine Uebereinstimmung",
        )

        assert result.matched is False
        assert result.chain_id is None


class TestDocumentChain:
    """Tests fuer DocumentChain Dataclass."""

    def test_document_chain_creation(self) -> None:
        """Test: DocumentChain korrekt erstellen."""
        now = datetime.now(timezone.utc)
        company_id = uuid4()

        chain = DocumentChain(
            chain_id="CHAIN-2026-00001",
            company_id=company_id,
            documents=[],
            document_count=0,
            chain_started_at=now,
            chain_updated_at=now,
            has_quote=False,
            has_order=False,
            has_delivery_note=False,
            has_invoice=False,
            has_credit_note=False,
            open_discrepancies=0,
            is_complete=False,
        )

        assert chain.chain_id == "CHAIN-2026-00001"
        assert chain.company_id == company_id
        assert chain.is_complete is False


class TestGetDocumentChain:
    """Tests fuer get_document_chain Methode."""

    @pytest.fixture
    def service(self) -> DocumentChainService:
        """Erstellt DocumentChainService Instanz."""
        return DocumentChainService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_document_chain_no_chain(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Dokument ohne Kette liefert None."""
        document_id = uuid4()
        company_id = uuid4()

        mock_doc = MagicMock()
        mock_doc.chain_id = None
        mock_db.get.return_value = mock_doc

        chain = await service.get_document_chain(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert chain is None

    @pytest.mark.asyncio
    async def test_get_document_chain_not_found(
        self, service: DocumentChainService, mock_db: AsyncMock
    ) -> None:
        """Test: Nicht existierendes Dokument liefert None."""
        document_id = uuid4()
        company_id = uuid4()

        mock_db.get.return_value = None

        chain = await service.get_document_chain(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert chain is None
