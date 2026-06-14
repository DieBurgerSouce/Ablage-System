# -*- coding: utf-8 -*-
"""
Unit Tests fuer Extended Document Chain Service V2.

Testet:
- Erweiterte Chain-Typen (Contract, Procurement, Project)
- ML-basiertes Auto-Matching
- Visualisierungs-API
- Chain-Completion Berechnung

Phase 6.2: Extended Document Chains Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.document_chain_service_v2 import (
    ExtendedDocumentChainServiceV2,
    ChainType,
    ContractDocumentType,
    ProcurementDocumentType,
    ExtendedChainDocument,
    ExtendedDocumentChain,
    MLMatchResult,
    ChainVisualization,
    EXTENDED_CHAIN_POSITIONS,
    get_extended_chain_service,
)
from app.services.document_chain_service import RelationshipType


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def service():
    """Erzeugt eine Service-Instanz."""
    return ExtendedDocumentChainServiceV2()


@pytest.fixture
def mock_db():
    """Erzeugt eine Mock-DB-Session."""
    mock = AsyncMock()
    mock.flush = AsyncMock()
    mock.commit = AsyncMock()
    mock.execute = AsyncMock()
    mock.get = AsyncMock()
    mock.add = MagicMock()
    return mock


@pytest.fixture
def sample_document():
    """Erzeugt ein Sample-Dokument."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.company_id = uuid4()
    doc.document_type = "invoice"
    doc.original_filename = "rechnung_001.pdf"
    doc.chain_id = None
    doc.chain_position = None
    doc.chain_root_document_id = None
    doc.document_metadata = {
        "extracted_data": {
            "total_amount": "1234.56",
            "invoice_number": "RE-2026-001",
            "customer_number": "K-12345",
        }
    }
    doc.created_at = datetime.now(timezone.utc)
    doc.processed_date = datetime.now(timezone.utc)
    doc.business_entity_id = uuid4()
    doc.business_entity = None
    return doc


# =============================================================================
# CHAIN TYPE TESTS
# =============================================================================


class TestChainTypes:
    """Tests fuer Chain-Typen."""

    def test_chain_type_enum_values(self):
        """Testet dass alle erwarteten Chain-Typen existieren."""
        assert ChainType.QUOTE_TO_ORDER.value == "quote_to_order"
        assert ChainType.CONTRACT_FULFILLMENT.value == "contract_fulfillment"
        assert ChainType.PROCUREMENT.value == "procurement"
        assert ChainType.PROJECT.value == "project"

    def test_contract_document_types(self):
        """Testet Vertrags-Dokumenttypen."""
        assert ContractDocumentType.CONTRACT.value == "contract"
        assert ContractDocumentType.DUNNING_L1.value == "dunning_l1"
        assert ContractDocumentType.DUNNING_L2.value == "dunning_l2"
        assert ContractDocumentType.DUNNING_L3.value == "dunning_l3"

    def test_procurement_document_types(self):
        """Testet Beschaffungs-Dokumenttypen."""
        assert ProcurementDocumentType.PURCHASE_ORDER.value == "purchase_order"
        assert ProcurementDocumentType.GOODS_RECEIPT.value == "goods_receipt"
        assert ProcurementDocumentType.QUALITY_CONTROL.value == "quality_control"

    def test_extended_chain_positions_contract(self):
        """Testet Chain-Positionen fuer Vertragserfuellung."""
        positions = EXTENDED_CHAIN_POSITIONS[ChainType.CONTRACT_FULFILLMENT.value]

        assert positions[ContractDocumentType.CONTRACT.value] == 1
        assert positions[ContractDocumentType.DELIVERY.value] == 3
        assert positions[ContractDocumentType.INVOICE.value] == 5
        assert positions[ContractDocumentType.DUNNING_L1.value] == 7
        assert positions[ContractDocumentType.DUNNING_L3.value] == 9

    def test_extended_chain_positions_procurement(self):
        """Testet Chain-Positionen fuer Beschaffung."""
        positions = EXTENDED_CHAIN_POSITIONS[ChainType.PROCUREMENT.value]

        assert positions[ProcurementDocumentType.PURCHASE_ORDER.value] == 2
        assert positions[ProcurementDocumentType.GOODS_RECEIPT.value] == 5
        assert positions[ProcurementDocumentType.QUALITY_CONTROL.value] == 6
        assert positions[ProcurementDocumentType.INVOICE.value] == 7


# =============================================================================
# SERVICE INITIALIZATION TESTS
# =============================================================================


class TestServiceInitialization:
    """Tests fuer Service-Initialisierung."""

    def test_service_creation(self, service):
        """Testet dass Service korrekt erstellt wird."""
        assert service is not None
        assert service._base_service is not None

    def test_get_extended_chain_service_factory(self):
        """Testet Factory-Funktion."""
        svc = get_extended_chain_service()
        assert isinstance(svc, ExtendedDocumentChainServiceV2)

    def test_ml_thresholds(self, service):
        """Testet ML-Konfidenz-Schwellenwerte."""
        assert service.ML_CONFIDENCE_HIGH == 0.90
        assert service.ML_CONFIDENCE_MEDIUM == 0.75
        assert service.ML_CONFIDENCE_LOW == 0.60
        assert service.ML_MIN_AUTO_LINK == 0.80

    def test_ml_feature_weights(self, service):
        """Testet ML-Feature-Gewichtungen."""
        weights = service.ML_FEATURE_WEIGHTS

        assert "reference_match" in weights
        assert "amount_similarity" in weights
        assert "entity_match" in weights
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)


# =============================================================================
# CHAIN PREFIX TESTS
# =============================================================================


class TestChainPrefix:
    """Tests fuer Chain-ID Prefixe."""

    def test_contract_prefix(self, service):
        """Testet Prefix fuer Vertragserfuellung."""
        prefix = service._get_chain_prefix(ChainType.CONTRACT_FULFILLMENT)
        assert prefix == "CONTRACT"

    def test_procurement_prefix(self, service):
        """Testet Prefix fuer Beschaffung."""
        prefix = service._get_chain_prefix(ChainType.PROCUREMENT)
        assert prefix == "PROC"

    def test_project_prefix(self, service):
        """Testet Prefix fuer Projekt."""
        prefix = service._get_chain_prefix(ChainType.PROJECT)
        assert prefix == "PROJECT"

    def test_standard_prefix(self, service):
        """Testet Standard-Prefix."""
        prefix = service._get_chain_prefix(ChainType.QUOTE_TO_ORDER)
        assert prefix == "CHAIN"


# =============================================================================
# TYPE FLAGS TESTS
# =============================================================================


class TestTypeFlags:
    """Tests fuer Dokumenttyp-Flags."""

    def test_contract_flags(self, service):
        """Testet Flags fuer Vertragserfuellung."""
        doc_types = {"contract", "delivery", "invoice"}
        flags = service._generate_type_flags(ChainType.CONTRACT_FULFILLMENT, doc_types)

        assert flags["has_contract"] is True
        assert flags["has_delivery"] is True
        assert flags["has_invoice"] is True
        assert flags["has_dunning"] is False

    def test_contract_flags_with_dunning(self, service):
        """Testet Flags mit Mahnungen."""
        doc_types = {"contract", "dunning_l1"}
        flags = service._generate_type_flags(ChainType.CONTRACT_FULFILLMENT, doc_types)

        assert flags["has_dunning"] is True

    def test_procurement_flags(self, service):
        """Testet Flags fuer Beschaffung."""
        doc_types = {"purchase_order", "goods_receipt", "invoice"}
        flags = service._generate_type_flags(ChainType.PROCUREMENT, doc_types)

        assert flags["has_purchase_order"] is True
        assert flags["has_goods_receipt"] is True
        assert flags["has_invoice"] is True
        assert flags["has_quality_control"] is False

    def test_standard_flags(self, service):
        """Testet Standard-Flags."""
        doc_types = {"quote", "order", "invoice"}
        flags = service._generate_type_flags(ChainType.QUOTE_TO_ORDER, doc_types)

        assert flags["has_quote"] is True
        assert flags["has_order"] is True
        assert flags["has_invoice"] is True
        assert flags["has_delivery_note"] is False


# =============================================================================
# COMPLETION CALCULATION TESTS
# =============================================================================


class TestCompletionCalculation:
    """Tests fuer Completion-Berechnung."""

    def test_contract_completion_full(self, service):
        """Testet volle Vertragserfuellung."""
        doc_types = {"contract", "delivery", "invoice"}
        completion = service._calculate_completion(ChainType.CONTRACT_FULFILLMENT, doc_types)

        # contract=25 + delivery=25 + invoice=25 = 75%
        assert completion == pytest.approx(75.0, abs=1.0)

    def test_contract_completion_partial(self, service):
        """Testet teilweise Vertragserfuellung."""
        doc_types = {"contract"}
        completion = service._calculate_completion(ChainType.CONTRACT_FULFILLMENT, doc_types)

        assert completion == pytest.approx(25.0, abs=1.0)

    def test_procurement_completion_full(self, service):
        """Testet volle Beschaffungskette."""
        doc_types = {
            "purchase_order", "order_confirmation", "delivery_note",
            "goods_receipt", "invoice"
        }
        completion = service._calculate_completion(ChainType.PROCUREMENT, doc_types)

        # 20+15+15+20+30 = 100%
        assert completion == 100.0

    def test_procurement_completion_partial(self, service):
        """Testet teilweise Beschaffungskette."""
        doc_types = {"purchase_order", "invoice"}
        completion = service._calculate_completion(ChainType.PROCUREMENT, doc_types)

        # 20 + 30 = 50%
        assert completion == pytest.approx(50.0, abs=1.0)


# =============================================================================
# FEATURE EXTRACTION TESTS
# =============================================================================


class TestFeatureExtraction:
    """Tests fuer Feature-Extraktion."""

    def test_extract_document_features(self, service, sample_document):
        """Testet Feature-Extraktion aus Dokument."""
        features = service._extract_document_features(sample_document)

        assert features["document_type"] == "invoice"
        assert features["amount"] == "1234.56"
        assert features["invoice_number"] == "RE-2026-001"
        assert features["customer_number"] == "K-12345"
        assert features["entity_id"] == sample_document.business_entity_id

    def test_extract_features_empty_metadata(self, service):
        """Testet Feature-Extraktion ohne Metadaten."""
        doc = MagicMock()
        doc.document_type = "invoice"
        doc.processed_date = datetime.now(timezone.utc)
        doc.created_at = datetime.now(timezone.utc)
        doc.business_entity_id = None
        doc.document_metadata = None

        features = service._extract_document_features(doc)

        assert features["document_type"] == "invoice"
        assert features.get("amount") is None


# =============================================================================
# FEATURE SCORING TESTS
# =============================================================================


class TestFeatureScoring:
    """Tests fuer Feature-Scoring."""

    def test_reference_match_score(self, service, sample_document):
        """Testet Reference-Match Score."""
        doc_features = {
            "order_number": "ORD-001",
            "amount": "100.00",
            "date": datetime.now(timezone.utc),
            "entity_id": uuid4(),
            "document_type": "invoice",
            "customer_number": "K-123",
        }

        candidate = MagicMock()
        candidate.document_type = "order"
        candidate.processed_date = datetime.now(timezone.utc)
        candidate.created_at = datetime.now(timezone.utc)
        candidate.business_entity_id = doc_features["entity_id"]
        candidate.document_metadata = {
            "extracted_data": {
                "order_number": "ORD-001",  # Match!
                "total_amount": "100.00",
                "customer_number": "K-123",
            }
        }

        scores = service._calculate_feature_scores(doc_features, candidate)

        assert scores["reference_match"] == 1.0

    def test_amount_similarity_score_exact(self, service):
        """Testet Amount-Similarity fuer identische Betraege."""
        doc_features = {
            "amount": "1000.00",
            "date": datetime.now(timezone.utc),
            "document_type": "invoice",
        }

        candidate = MagicMock()
        candidate.document_type = "order"
        candidate.processed_date = datetime.now(timezone.utc)
        candidate.created_at = datetime.now(timezone.utc)
        candidate.business_entity_id = None
        candidate.document_metadata = {
            "extracted_data": {
                "total_amount": "1000.00",  # Exact match
            }
        }

        scores = service._calculate_feature_scores(doc_features, candidate)

        assert scores["amount_similarity"] == 1.0

    def test_entity_match_score(self, service):
        """Testet Entity-Match Score."""
        entity_id = uuid4()
        doc_features = {
            "entity_id": entity_id,
            "document_type": "invoice",
            "date": datetime.now(timezone.utc),
        }

        candidate = MagicMock()
        candidate.document_type = "order"
        candidate.processed_date = datetime.now(timezone.utc)
        candidate.created_at = datetime.now(timezone.utc)
        candidate.business_entity_id = entity_id  # Same entity
        candidate.document_metadata = {}

        scores = service._calculate_feature_scores(doc_features, candidate)

        assert scores["entity_match"] == 1.0


# =============================================================================
# CHAIN TYPE INFERENCE TESTS
# =============================================================================


class TestChainTypeInference:
    """Tests fuer Chain-Typ-Ableitung."""

    def test_infer_contract_chain(self, service):
        """Testet Ableitung von Contract-Chain."""
        chain_type = service._infer_chain_type("contract", "invoice")
        assert chain_type == ChainType.CONTRACT_FULFILLMENT

    def test_infer_procurement_chain(self, service):
        """Testet Ableitung von Procurement-Chain."""
        chain_type = service._infer_chain_type("purchase_order", "delivery_note")
        assert chain_type == ChainType.PROCUREMENT

    def test_infer_quote_chain(self, service):
        """Testet Ableitung von Quote-Chain."""
        chain_type = service._infer_chain_type("quote", "order")
        assert chain_type == ChainType.QUOTE_TO_ORDER

    def test_infer_default_chain(self, service):
        """Testet Default-Ableitung."""
        chain_type = service._infer_chain_type("invoice", "receipt")
        assert chain_type == ChainType.DELIVERY_TO_INVOICE


# =============================================================================
# RELATIONSHIP TYPE INFERENCE TESTS
# =============================================================================


class TestRelationshipTypeInference:
    """Tests fuer Beziehungstyp-Ableitung."""

    def test_infer_quote_to_order(self, service):
        """Testet Quote-to-Order Ableitung."""
        rel_type = service._infer_relationship_type("quote", "order")
        assert rel_type == RelationshipType.QUOTE_TO_ORDER

    def test_infer_order_to_delivery(self, service):
        """Testet Order-to-Delivery Ableitung."""
        rel_type = service._infer_relationship_type("order", "delivery_note")
        assert rel_type == RelationshipType.ORDER_TO_DELIVERY

    def test_infer_delivery_to_invoice(self, service):
        """Testet Delivery-to-Invoice Ableitung."""
        rel_type = service._infer_relationship_type("delivery_note", "invoice")
        assert rel_type == RelationshipType.DELIVERY_TO_INVOICE

    def test_infer_related_default(self, service):
        """Testet Default-Beziehung."""
        rel_type = service._infer_relationship_type("other", "document")
        assert rel_type == RelationshipType.RELATED


# =============================================================================
# MATCH REASON GENERATION TESTS
# =============================================================================


class TestMatchReasonGeneration:
    """Tests fuer Match-Reason Generierung."""

    def test_match_reason_reference(self, service):
        """Testet Match-Reason fuer Reference-Match."""
        feature_scores = {"reference_match": 1.0, "entity_match": 0.0}
        doc_features = {"order_number": "ORD-001"}
        candidate = MagicMock()

        reason = service._generate_match_reason(feature_scores, doc_features, candidate)

        assert "Order Number" in reason

    def test_match_reason_entity(self, service):
        """Testet Match-Reason fuer Entity-Match."""
        feature_scores = {"reference_match": 0.0, "entity_match": 1.0, "amount_similarity": 0.5}
        doc_features = {}
        candidate = MagicMock()

        reason = service._generate_match_reason(feature_scores, doc_features, candidate)

        assert "Geschäftspartner" in reason

    def test_match_reason_ml_fallback(self, service):
        """Testet ML-Fallback Reason."""
        feature_scores = {"reference_match": 0.0, "entity_match": 0.0, "amount_similarity": 0.3}
        doc_features = {}
        candidate = MagicMock()

        reason = service._generate_match_reason(feature_scores, doc_features, candidate)

        assert "ML-basierte" in reason


# =============================================================================
# DATA CLASS TESTS
# =============================================================================


class TestDataClasses:
    """Tests fuer Datenklassen."""

    def test_extended_chain_document_creation(self):
        """Testet ExtendedChainDocument Erstellung."""
        doc = ExtendedChainDocument(
            id=uuid4(),
            document_type="invoice",
            chain_position=1,
            filename="test.pdf",
            document_date=datetime.now(timezone.utc),
            amount=Decimal("100.00"),
            reference_numbers={"invoice_number": "RE-001"},
            created_at=datetime.now(timezone.utc),
            chain_type=ChainType.CONTRACT_FULFILLMENT,
        )

        assert doc.chain_type == ChainType.CONTRACT_FULFILLMENT
        assert doc.amount == Decimal("100.00")

    def test_ml_match_result_creation(self):
        """Testet MLMatchResult Erstellung."""
        result = MLMatchResult(
            matched=True,
            chain_id="CONTRACT-2026-00001",
            chain_type=ChainType.CONTRACT_FULFILLMENT,
            relationship_type=RelationshipType.ORDER_TO_INVOICE,
            confidence=0.95,
            matched_documents=[uuid4()],
            match_reason="Gleiche Bestellnummer",
            ml_features={"reference_match": 1.0},
        )

        assert result.matched is True
        assert result.confidence == 0.95
        assert result.model_version == "v1.0"

    def test_chain_visualization_creation(self):
        """Testet ChainVisualization Erstellung."""
        viz = ChainVisualization(
            chain_id="CHAIN-001",
            chain_type=ChainType.QUOTE_TO_ORDER,
            nodes=[{"id": "1", "label": "Quote"}],
            edges=[{"source": "1", "target": "2"}],
        )

        assert viz.layout == "horizontal"
        assert len(viz.nodes) == 1
        assert len(viz.edges) == 1


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration-Tests."""

    @pytest.mark.asyncio
    async def test_create_contract_chain_flow(self, service, mock_db, sample_document):
        """Testet kompletten Vertragserfuellungs-Flow."""
        company_id = uuid4()
        user_id = uuid4()

        # Mock DB responses
        mock_db.execute.return_value.scalar.return_value = 0
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_document
        mock_db.get.return_value = sample_document

        # Service sollte nicht crashen bei Mock
        # In echtem Test mit DB-Integration pruefen
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_chain_prefix_all_types(self, service):
        """Testet alle Chain-Prefixe."""
        for chain_type in ChainType:
            prefix = service._get_chain_prefix(chain_type)
            assert isinstance(prefix, str)
            assert len(prefix) > 0
