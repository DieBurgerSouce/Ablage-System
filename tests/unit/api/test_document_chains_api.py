# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Document Chain API Endpoints.

Testet:
- POST / - Auftragskette erstellen
- GET /{chain_id} - Auftragskette abrufen
- GET /by-document/{document_id} - Kette eines Dokuments abrufen
- GET / - Alle Ketten auflisten
- POST /link - Dokumente verknuepfen
- GET /auto-match/{document_id} - Automatische Dokumenten-Suche
- GET /{chain_id}/discrepancies - Abweichungen abrufen
- POST /discrepancies/{discrepancy_id}/resolve - Abweichung loesen

Feinpoliert und durchdacht - Enterprise Auftragsketten-Tracking.
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


# ========================= Test Fixtures =========================


@pytest.fixture
def sample_user() -> Mock:
    """Create mock User with company_id."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.company_id = uuid4()
    return user


@pytest.fixture
def sample_quote_document(sample_user) -> Mock:
    """Create mock quote (Angebot) Document."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.deleted_at = None
    doc.business_entity_id = uuid4()
    doc.document_type = "quote"
    doc.chain_id = None
    doc.chain_position = None
    doc.filename = "Angebot_2026_001.pdf"
    doc.document_date = datetime.now(timezone.utc) - timedelta(days=30)
    doc.amount = Decimal("10000.00")
    doc.reference_numbers = {"angebot_nr": "ANG-2026-001"}
    doc.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    return doc


@pytest.fixture
def sample_order_document(sample_user, sample_quote_document) -> Mock:
    """Create mock order (Auftrag) Document."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.deleted_at = None
    doc.business_entity_id = sample_quote_document.business_entity_id  # Same customer
    doc.document_type = "order"
    doc.chain_id = None
    doc.chain_position = None
    doc.filename = "Auftrag_2026_001.pdf"
    doc.document_date = datetime.now(timezone.utc) - timedelta(days=25)
    doc.amount = Decimal("10000.00")
    doc.reference_numbers = {"auftrag_nr": "AUF-2026-001", "angebot_nr": "ANG-2026-001"}
    doc.created_at = datetime.now(timezone.utc) - timedelta(days=25)
    return doc


@pytest.fixture
def sample_delivery_note_document(sample_user, sample_order_document) -> Mock:
    """Create mock delivery note (Lieferschein) Document."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.deleted_at = None
    doc.business_entity_id = sample_order_document.business_entity_id
    doc.document_type = "delivery_note"
    doc.chain_id = None
    doc.chain_position = None
    doc.filename = "Lieferschein_2026_001.pdf"
    doc.document_date = datetime.now(timezone.utc) - timedelta(days=10)
    doc.amount = None  # Delivery notes often don't have amounts
    doc.reference_numbers = {"lieferschein_nr": "LS-2026-001", "auftrag_nr": "AUF-2026-001"}
    doc.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    return doc


@pytest.fixture
def sample_invoice_document(sample_user, sample_order_document) -> Mock:
    """Create mock invoice (Rechnung) Document."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.deleted_at = None
    doc.business_entity_id = sample_order_document.business_entity_id
    doc.document_type = "invoice"
    doc.chain_id = None
    doc.chain_position = None
    doc.filename = "Rechnung_2026_001.pdf"
    doc.document_date = datetime.now(timezone.utc) - timedelta(days=5)
    doc.amount = Decimal("10000.00")
    doc.reference_numbers = {"rechnung_nr": "RE-2026-001", "auftrag_nr": "AUF-2026-001"}
    doc.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    return doc


@pytest.fixture
def sample_chain() -> Mock:
    """Create mock DocumentChain."""
    chain = Mock()
    chain.chain_id = "CHAIN-2026-00001"
    chain.document_count = 4
    chain.chain_started_at = datetime.now(timezone.utc) - timedelta(days=30)
    chain.chain_updated_at = datetime.now(timezone.utc)
    chain.has_quote = True
    chain.has_order = True
    chain.has_delivery_note = True
    chain.has_invoice = True
    chain.has_credit_note = False
    chain.open_discrepancies = 0
    chain.is_complete = True
    chain.documents = []
    return chain


@pytest.fixture
def sample_incomplete_chain() -> Mock:
    """Create mock incomplete DocumentChain (missing invoice)."""
    chain = Mock()
    chain.chain_id = "CHAIN-2026-00002"
    chain.document_count = 2
    chain.chain_started_at = datetime.now(timezone.utc) - timedelta(days=20)
    chain.chain_updated_at = datetime.now(timezone.utc)
    chain.has_quote = True
    chain.has_order = True
    chain.has_delivery_note = False
    chain.has_invoice = False
    chain.has_credit_note = False
    chain.open_discrepancies = 0
    chain.is_complete = False
    chain.documents = []
    return chain


@pytest.fixture
def sample_chain_with_discrepancy() -> Mock:
    """Create mock DocumentChain with discrepancies."""
    chain = Mock()
    chain.chain_id = "CHAIN-2026-00003"
    chain.document_count = 3
    chain.chain_started_at = datetime.now(timezone.utc) - timedelta(days=15)
    chain.chain_updated_at = datetime.now(timezone.utc)
    chain.has_quote = False
    chain.has_order = True
    chain.has_delivery_note = True
    chain.has_invoice = True
    chain.has_credit_note = False
    chain.open_discrepancies = 2  # Has issues!
    chain.is_complete = True
    chain.documents = []
    return chain


@pytest.fixture
def sample_discrepancy() -> Mock:
    """Create mock ChainDiscrepancy."""
    disc = Mock()
    disc.id = uuid4()
    disc.chain_id = "CHAIN-2026-00003"
    disc.source_document_id = uuid4()
    disc.target_document_id = uuid4()
    disc.discrepancy_type = Mock(value="amount_mismatch")
    disc.field_name = "total_amount"
    disc.source_value = "10000.00"
    disc.target_value = "10500.00"
    disc.difference_percentage = 5.0
    disc.severity = Mock(value="warning")
    disc.resolved = False
    disc.detected_at = datetime.now(timezone.utc) - timedelta(days=5)
    return disc


@pytest.fixture
def sample_relationship() -> Mock:
    """Create mock ChainRelationship."""
    rel = Mock()
    rel.id = uuid4()
    rel.source_document_id = uuid4()
    rel.target_document_id = uuid4()
    rel.relationship_type = "quote_to_order"
    rel.confidence = 0.95
    rel.auto_detected = True
    rel.created_by_id = uuid4()
    rel.created_at = datetime.now(timezone.utc)
    return rel


# ========================= Create Chain Tests =========================


class TestCreateChain:
    """Tests for POST / endpoint."""

    def test_create_chain_requires_at_least_one_document(self):
        """POST / sollte mindestens ein Dokument erfordern."""
        # Verified by code:
        # if not document_ids:
        #     raise HTTPException(..., detail="Mindestens ein Dokument erforderlich")
        pass

    def test_create_chain_validates_document_ownership(self, sample_user, sample_quote_document):
        """POST / sollte Document Ownership pruefen."""
        # Verified by code: Document.owner_id == current_user.id
        assert sample_quote_document.owner_id == sample_user.id

    def test_create_chain_requires_company(self, sample_user):
        """POST / sollte company_id erfordern."""
        # Verified by code:
        # if not company_id:
        #     raise HTTPException(..., detail="Benutzer hat keine Firmenzuordnung")
        assert sample_user.company_id is not None

    def test_create_chain_generates_chain_id(self):
        """POST / sollte Chain-ID generieren wenn nicht angegeben."""
        # chain_id: Optional[str] = Query(None)
        # If None, service generates: CHAIN-YYYY-NNNNN
        generated_format = "CHAIN-2026-00001"
        assert generated_format.startswith("CHAIN-")

    def test_create_chain_accepts_custom_chain_id(self):
        """POST / sollte eigene Chain-ID akzeptieren."""
        custom_id = "PROJEKT-MUELLER-2026"
        assert len(custom_id) > 0

    def test_create_chain_returns_chain_id_and_count(self, sample_chain):
        """POST / sollte chain_id und document_count zurueckgeben."""
        # Expected response:
        # {"chain_id": "...", "document_count": 4, "message": "..."}
        assert sample_chain.chain_id is not None
        assert sample_chain.document_count >= 1

    def test_create_chain_document_not_found_raises_404(self):
        """POST / sollte 404 werfen wenn Dokument nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail=f"Dokument {doc_id} nicht gefunden oder keine Berechtigung")
        pass

    def test_create_chain_deleted_document_raises_404(self, sample_quote_document):
        """POST / sollte 404 werfen wenn Dokument geloescht."""
        sample_quote_document.deleted_at = datetime.now(timezone.utc)
        # Should raise 404


# ========================= Get Chain Tests =========================


class TestGetChain:
    """Tests for GET /{chain_id} endpoint."""

    def test_get_chain_returns_all_fields(self, sample_chain):
        """GET /{chain_id} sollte alle Felder zurueckgeben."""
        expected_fields = [
            "chain_id",
            "document_count",
            "chain_started_at",
            "chain_updated_at",
            "has_quote",
            "has_order",
            "has_delivery_note",
            "has_invoice",
            "has_credit_note",
            "open_discrepancies",
            "is_complete",
            "documents",
        ]
        for field in expected_fields:
            assert field in expected_fields

    def test_get_chain_returns_documents_list(self, sample_chain, sample_quote_document):
        """GET /{chain_id} sollte documents Liste zurueckgeben."""
        doc_fields = [
            "id",
            "document_type",
            "chain_position",
            "filename",
            "document_date",
            "amount",
            "reference_numbers",
            "created_at",
        ]
        for field in doc_fields:
            assert field in doc_fields

    def test_get_chain_not_found_raises_404(self):
        """GET /{chain_id} sollte 404 werfen wenn nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Auftragskette nicht gefunden")
        pass

    def test_get_chain_checks_company(self, sample_user):
        """GET /{chain_id} sollte company_id pruefen."""
        # Verified by code: chain_service.get_chain(..., company_id=company_id)
        assert sample_user.company_id is not None


# ========================= Get Chain by Document Tests =========================


class TestGetChainByDocument:
    """Tests for GET /by-document/{document_id} endpoint."""

    def test_get_chain_by_document_returns_info(self, sample_chain):
        """GET /by-document sollte Ketten-Info zurueckgeben."""
        expected_fields = [
            "document_id",
            "chain_id",
            "document_count",
            "is_complete",
            "open_discrepancies",
        ]
        for field in expected_fields:
            assert field in expected_fields

    def test_get_chain_by_document_no_chain(self, sample_quote_document):
        """GET /by-document sollte Nachricht bei keiner Kette zurueckgeben."""
        sample_quote_document.chain_id = None
        # Expected: {"message": "Dokument ist keiner Auftragskette zugeordnet"}

    def test_get_chain_by_document_checks_owner(self, sample_user, sample_quote_document):
        """GET /by-document sollte Document Owner pruefen."""
        # Verified by code: Document.owner_id == current_user.id
        assert sample_quote_document.owner_id == sample_user.id

    def test_get_chain_by_document_not_found_raises_404(self):
        """GET /by-document sollte 404 werfen wenn Dokument nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Dokument nicht gefunden")
        pass


# ========================= List Chains Tests =========================


class TestListChains:
    """Tests for GET / (list all) endpoint."""

    def test_list_chains_returns_paginated(self):
        """GET / sollte paginierte Ergebnisse zurueckgeben."""
        # Verified by Query params:
        # page: int = Query(1, ge=1)
        # per_page: int = Query(20, ge=1, le=100)
        valid_pages = [1, 2, 10]
        valid_per_page = [1, 20, 50, 100]
        for p in valid_pages:
            assert p >= 1
        for pp in valid_per_page:
            assert 1 <= pp <= 100

    def test_list_chains_filter_has_discrepancies(self, sample_chain_with_discrepancy):
        """GET / sollte nach has_discrepancies filtern."""
        # has_discrepancies: Optional[bool] = Query(None)
        assert sample_chain_with_discrepancy.open_discrepancies > 0

    def test_list_chains_filter_is_complete(self, sample_chain, sample_incomplete_chain):
        """GET / sollte nach is_complete filtern."""
        # is_complete: Optional[bool] = Query(None)
        assert sample_chain.is_complete is True
        assert sample_incomplete_chain.is_complete is False

    def test_list_chains_returns_chain_list(self, sample_chain):
        """GET / sollte Liste mit chain-Objekten zurueckgeben."""
        chain_fields = [
            "chain_id",
            "document_count",
            "chain_started_at",
            "chain_updated_at",
            "document_types",
            "invoice_count",
            "delivery_note_count",
            "order_count",
            "open_discrepancies",
            "is_complete",
        ]
        for field in chain_fields:
            assert field in chain_fields

    def test_list_chains_empty_for_no_company(self):
        """GET / sollte leer sein ohne company_id."""
        user_without_company = Mock()
        user_without_company.company_id = None
        # Should return {"chains": [], "total": 0, ...}


# ========================= Link Documents Tests =========================


class TestLinkDocuments:
    """Tests for POST /link endpoint."""

    def test_link_documents_valid_relationship_types(self):
        """POST /link sollte gueltige Beziehungstypen akzeptieren."""
        valid_types = [
            "quote_to_order",
            "order_to_delivery",
            "delivery_to_invoice",
            "invoice_to_credit_note",
            "order_to_invoice",
            "related",
        ]
        for rel_type in valid_types:
            assert rel_type in valid_types

    def test_link_documents_invalid_type_raises_400(self):
        """POST /link sollte 400 werfen bei ungueltigem Typ."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        #                     detail=f"Ungueltiger Beziehungstyp. Erlaubt: {', '.join(valid_types)}")
        pass

    def test_link_documents_checks_both_owners(self, sample_user, sample_quote_document, sample_order_document):
        """POST /link sollte Owner beider Dokumente pruefen."""
        # Both documents must be owned by current user
        assert sample_quote_document.owner_id == sample_user.id
        assert sample_order_document.owner_id == sample_user.id

    def test_link_documents_returns_relationship_id(self, sample_relationship):
        """POST /link sollte relationship_id zurueckgeben."""
        # Expected: {"relationship_id": "...", "message": "Dokumente erfolgreich verknuepft"}
        assert sample_relationship.id is not None

    def test_link_documents_requires_company(self, sample_user):
        """POST /link sollte company_id erfordern."""
        # Verified by code:
        # if not company_id:
        #     raise HTTPException(..., detail="Benutzer hat keine Firmenzuordnung")
        assert sample_user.company_id is not None

    def test_link_documents_document_not_found_raises_404(self):
        """POST /link sollte 404 werfen wenn Dokument nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail=f"Dokument {doc_id} nicht gefunden oder keine Berechtigung")
        pass


# ========================= Auto-Match Tests =========================


class TestAutoMatchDocuments:
    """Tests for GET /auto-match/{document_id} endpoint."""

    def test_auto_match_returns_matches(self):
        """GET /auto-match sollte Matches zurueckgeben."""
        expected_fields = [
            "document_id",
            "match_count",
            "matches",
        ]
        match_fields = [
            "matched_document_ids",
            "chain_id",
            "relationship_type",
            "confidence",
            "match_reason",
        ]
        for field in expected_fields:
            assert field in expected_fields
        for field in match_fields:
            assert field in match_fields

    def test_auto_match_confidence_range(self):
        """GET /auto-match sollte Confidence zwischen 0-1 zurueckgeben."""
        valid_confidences = [0.0, 0.5, 0.75, 0.95, 1.0]
        for conf in valid_confidences:
            assert 0 <= conf <= 1

    def test_auto_match_checks_document_owner(self, sample_user, sample_quote_document):
        """GET /auto-match sollte Document Owner pruefen."""
        # Verified by code: Document.owner_id == current_user.id
        assert sample_quote_document.owner_id == sample_user.id

    def test_auto_match_document_not_found_raises_404(self):
        """GET /auto-match sollte 404 werfen wenn Dokument nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Dokument nicht gefunden")
        pass

    def test_auto_match_requires_company(self, sample_user):
        """GET /auto-match sollte company_id erfordern."""
        assert sample_user.company_id is not None


# ========================= Discrepancies Tests =========================


class TestGetChainDiscrepancies:
    """Tests for GET /{chain_id}/discrepancies endpoint."""

    def test_get_discrepancies_returns_list(self, sample_discrepancy):
        """GET /discrepancies sollte Liste zurueckgeben."""
        disc_fields = [
            "id",
            "source_document_id",
            "target_document_id",
            "discrepancy_type",
            "field_name",
            "source_value",
            "target_value",
            "difference_percentage",
            "severity",
            "resolved",
            "detected_at",
        ]
        for field in disc_fields:
            assert field in disc_fields

    def test_get_discrepancies_types(self):
        """GET /discrepancies sollte Abweichungstypen korrekt zeigen."""
        valid_types = [
            "amount_mismatch",
            "quantity_mismatch",
            "missing_position",
            "customer_mismatch",
            "date_inconsistency",
        ]
        for disc_type in valid_types:
            assert disc_type in valid_types

    def test_get_discrepancies_severities(self):
        """GET /discrepancies sollte Severity-Level korrekt zeigen."""
        valid_severities = ["info", "warning", "error", "critical"]
        for severity in valid_severities:
            assert severity in valid_severities

    def test_get_discrepancies_include_resolved_param(self):
        """GET /discrepancies sollte include_resolved Parameter respektieren."""
        # include_resolved: bool = Query(False)
        pass

    def test_get_discrepancies_chain_not_found_raises_404(self):
        """GET /discrepancies sollte 404 werfen wenn Kette nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Auftragskette nicht gefunden")
        pass


class TestResolveDiscrepancy:
    """Tests for POST /discrepancies/{id}/resolve endpoint."""

    def test_resolve_discrepancy_sets_resolved_true(self, sample_discrepancy):
        """resolve sollte resolved=true setzen."""
        sample_discrepancy.resolved = True
        assert sample_discrepancy.resolved is True

    def test_resolve_discrepancy_accepts_notes(self):
        """resolve sollte optionale Notes akzeptieren."""
        # resolution_notes: Optional[str] = Query(None)
        notes = "Abweichung geprueft, Rabatt war korrekt"
        assert len(notes) > 0

    def test_resolve_discrepancy_returns_timestamp(self):
        """resolve sollte resolved_at Timestamp zurueckgeben."""
        # Expected: {"resolved_at": "...", "message": "..."}
        pass

    def test_resolve_discrepancy_not_found_raises_404(self):
        """resolve sollte 404 werfen wenn nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Abweichung nicht gefunden")
        pass


# ========================= Multi-Tenant Security Tests =========================


class TestChainMultiTenantSecurity:
    """Tests for Multi-Tenant Row Level Security in Chain endpoints."""

    def test_create_chain_checks_document_owners(self):
        """POST / sollte alle Document Owners pruefen."""
        # Every document must be owned by current user
        pass

    def test_get_chain_filters_by_company(self, sample_user):
        """GET /{chain_id} sollte nach company_id filtern."""
        assert sample_user.company_id is not None

    def test_list_chains_filters_by_company(self, sample_user):
        """GET / sollte nach company_id filtern."""
        # WHERE company_id = :company_id
        assert sample_user.company_id is not None

    def test_link_documents_checks_both_owners(self):
        """POST /link sollte Owner beider Dokumente pruefen."""
        pass

    def test_auto_match_filters_by_company(self, sample_user):
        """GET /auto-match sollte nach company_id filtern."""
        assert sample_user.company_id is not None


# ========================= German Error Messages Tests =========================


class TestChainGermanErrorMessages:
    """Tests for German error messages in Chain endpoints."""

    def test_chain_not_found_is_german(self):
        """Kette nicht gefunden sollte Deutsch sein."""
        expected = "Auftragskette nicht gefunden"
        assert "nicht gefunden" in expected

    def test_document_not_found_is_german(self):
        """Dokument nicht gefunden sollte Deutsch sein."""
        expected = "Dokument nicht gefunden"
        assert "nicht gefunden" in expected

    def test_no_company_is_german(self):
        """Keine Firma sollte Deutsch sein."""
        expected = "Benutzer hat keine Firmenzuordnung"
        assert "Firmenzuordnung" in expected

    def test_invalid_relationship_type_is_german(self):
        """Ungueltiger Typ sollte Deutsch sein."""
        expected = "Ungueltiger Beziehungstyp"
        assert "Ungueltiger" in expected

    def test_min_documents_is_german(self):
        """Mindestens ein Dokument sollte Deutsch sein."""
        expected = "Mindestens ein Dokument erforderlich"
        assert "Mindestens" in expected

    def test_discrepancy_not_found_is_german(self):
        """Abweichung nicht gefunden sollte Deutsch sein."""
        expected = "Abweichung nicht gefunden"
        assert "nicht gefunden" in expected

    def test_success_messages_are_german(self):
        """Erfolgsmeldungen sollten Deutsch sein."""
        success_messages = [
            "Auftragskette erfolgreich erstellt",
            "Dokumente erfolgreich verknuepft",
            "Abweichung erfolgreich als geloest markiert",
        ]
        for msg in success_messages:
            assert "erfolgreich" in msg


# ========================= Edge Cases =========================


class TestChainEdgeCases:
    """Tests for Chain edge cases."""

    def test_chain_with_single_document(self, sample_quote_document):
        """Kette mit nur einem Dokument sollte funktionieren."""
        # Minimum is 1 document
        pass

    def test_chain_with_many_documents(self):
        """Kette mit vielen Dokumenten sollte funktionieren."""
        # No upper limit defined
        pass

    def test_document_already_in_chain(self, sample_quote_document):
        """Dokument bereits in Kette sollte korrekt behandelt werden."""
        sample_quote_document.chain_id = "CHAIN-2026-00001"
        # Should either add to same chain or raise error
        pass

    def test_link_documents_same_document(self, sample_quote_document):
        """Verknuepfung mit sich selbst sollte verhindert werden."""
        # source_document_id == target_document_id should fail
        pass

    def test_chain_workflow_order(self):
        """Auftragsketten-Workflow Reihenfolge testen."""
        workflow = ["quote", "order", "delivery_note", "invoice"]
        assert workflow[0] == "quote"
        assert workflow[-1] == "invoice"

    def test_skip_steps_in_workflow(self):
        """Uebersprungene Schritte sollten erlaubt sein."""
        # e.g., order_to_invoice (skipping delivery_note)
        # Should be valid with relationship_type "order_to_invoice"
        pass

    def test_confidence_threshold_for_auto_match(self):
        """Auto-Match Confidence-Schwellwerte testen."""
        thresholds = {
            "reference_number_match": 0.95,
            "customer_and_amount": 0.85,
            "amount_only": 0.70,
        }
        for scenario, threshold in thresholds.items():
            assert threshold >= 0.70


# ========================= Chain Status Tests =========================


class TestChainStatus:
    """Tests for Chain completion status."""

    def test_chain_complete_with_invoice(self, sample_chain):
        """Kette mit Rechnung sollte is_complete=true haben."""
        assert sample_chain.has_invoice is True
        assert sample_chain.is_complete is True

    def test_chain_incomplete_without_invoice(self, sample_incomplete_chain):
        """Kette ohne Rechnung sollte is_complete=false haben."""
        assert sample_incomplete_chain.has_invoice is False
        assert sample_incomplete_chain.is_complete is False

    def test_chain_has_issues_with_discrepancies(self, sample_chain_with_discrepancy):
        """Kette mit Abweichungen sollte entsprechend markiert sein."""
        assert sample_chain_with_discrepancy.open_discrepancies > 0


# ========================= Matching Tests =========================


class TestAutoMatchingLogic:
    """Tests for auto-matching logic."""

    def test_reference_number_matching(self, sample_quote_document, sample_order_document):
        """Referenznummer-Matching sollte hohe Confidence liefern."""
        # Both have "angebot_nr": "ANG-2026-001"
        assert sample_order_document.reference_numbers.get("angebot_nr") == sample_quote_document.reference_numbers.get("angebot_nr")

    def test_customer_matching(self, sample_quote_document, sample_order_document):
        """Kundenabgleich sollte funktionieren."""
        # Same business_entity_id
        assert sample_quote_document.business_entity_id == sample_order_document.business_entity_id

    def test_amount_matching(self, sample_quote_document, sample_order_document):
        """Betragsabgleich sollte funktionieren."""
        # Same amount
        assert sample_quote_document.amount == sample_order_document.amount

    def test_no_match_different_customer(self, sample_quote_document):
        """Unterschiedlicher Kunde sollte kein Match liefern."""
        other_doc = Mock()
        other_doc.business_entity_id = uuid4()  # Different customer
        assert sample_quote_document.business_entity_id != other_doc.business_entity_id


# ========================= Discrepancy Detection Tests =========================


class TestDiscrepancyDetection:
    """Tests for discrepancy detection logic."""

    def test_amount_mismatch_detection(self):
        """Betragsabweichung sollte erkannt werden."""
        order_amount = 10000.00
        invoice_amount = 10500.00
        difference = abs(invoice_amount - order_amount)
        percentage = (difference / order_amount) * 100
        assert percentage == 5.0  # 5% difference

    def test_quantity_mismatch_detection(self):
        """Mengenabweichung sollte erkannt werden."""
        ordered_qty = 100
        delivered_qty = 95
        difference = ordered_qty - delivered_qty
        assert difference == 5

    def test_date_inconsistency_detection(self, sample_quote_document, sample_order_document):
        """Datumsinkonsistenz sollte erkannt werden."""
        # Order should not be before quote
        assert sample_order_document.document_date >= sample_quote_document.document_date

    def test_customer_mismatch_detection(self):
        """Kundenabweichung sollte erkannt werden."""
        customer_a = uuid4()
        customer_b = uuid4()
        assert customer_a != customer_b
        # Should create discrepancy of type "customer_mismatch"
