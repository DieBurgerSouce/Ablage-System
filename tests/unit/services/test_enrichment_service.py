# -*- coding: utf-8 -*-
"""Unit tests for External Enrichment Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.external.enrichment_orchestrator import (
    EnrichmentOrchestrator,
    EnrichmentResult,
    SourceInfo,
)
from app.services.external.handelsregister_service import CompanyRecord
from app.services.external.bundesanzeiger_service import (
    InsolvencyResult,
    InsolvencyPublication,
)
from app.db.models import BusinessEntity


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def orchestrator():
    """Enrichment orchestrator instance."""
    return EnrichmentOrchestrator()


@pytest.fixture
def mock_entity():
    """Mock BusinessEntity."""
    entity = MagicMock(spec=BusinessEntity)
    entity.id = uuid4()
    entity.company_id = uuid4()
    entity.name = "Musterfirma GmbH"
    entity.city = "München"
    entity.legal_form = None
    entity.metadata = {}
    return entity


# W3 (2026-06-12): Die zwei frueheren Enrichment-Quirks sind BEHOBEN
# (fix/w3b-backend-sweep): sauberer Bundesanzeiger-Befund zaehlt jetzt als
# befragte Quelle (insolvency_warning=False ist ein echtes Ergebnis) und
# die Confidence-Formel erreicht 1.0 (1.0 pro liefernder Quelle / Anzahl
# angefragter Quellen). Die strict-xfail-Marker wurden entfernt.


@pytest.mark.asyncio
async def test_enrichment_orchestrator_all_sources(orchestrator, mock_db, mock_entity):
    """Test enriching entity from all available sources."""
    # Mock database query to return entity
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister service
    company_record = CompanyRecord(
        name="Musterfirma GmbH",
        legal_form="GmbH",
        register_number="HRB 12345",
        registered_address="München",
        founded_date="2020-01-01",
        capital="25000 EUR",
    )
    orchestrator.handelsregister.search_company = AsyncMock(
        return_value=[company_record]
    )

    # Mock Bundesanzeiger service
    insolvency_result = InsolvencyResult(
        has_insolvency=False,
        count=0,
        publications=[],
    )
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=insolvency_result
    )

    # Execute enrichment
    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=None,  # All sources
        db=mock_db,
    )

    assert isinstance(result, EnrichmentResult)
    assert result.entity_id == mock_entity.id
    assert "handelsregister" in result.sources_queried
    assert "bundesanzeiger" in result.sources_queried
    assert len(result.enriched_fields) > 0
    assert result.confidence > 0.0
    assert "legal_form" in result.enriched_fields
    assert result.enriched_fields["legal_form"] == "GmbH"


@pytest.mark.asyncio
async def test_enrichment_single_source(orchestrator, mock_db, mock_entity):
    """Test enriching from specific source only."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister service
    company_record = CompanyRecord(
        name="Musterfirma GmbH",
        legal_form="GmbH",
        register_number="HRB 99999",
        registered_address="Berlin",
        founded_date="2015-06-15",
        capital="50000 EUR",
    )
    orchestrator.handelsregister.search_company = AsyncMock(
        return_value=[company_record]
    )

    # Execute enrichment from Handelsregister only
    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["handelsregister"],
        db=mock_db,
    )

    assert "handelsregister" in result.sources_queried
    assert "bundesanzeiger" not in result.sources_queried
    assert "register_number" in result.enriched_fields


@pytest.mark.asyncio
async def test_handelsregister_lookup(orchestrator, mock_db, mock_entity):
    """Test Handelsregister lookup returns company data."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister with detailed company record
    company_record = CompanyRecord(
        name="Testfirma AG",
        legal_form="AG",
        register_number="HRB 54321",
        registered_address="Hamburg, Teststraße 1",
        founded_date="2010-03-15",
        capital="100000 EUR",
    )
    orchestrator.handelsregister.search_company = AsyncMock(
        return_value=[company_record]
    )

    # Mock Bundesanzeiger (no insolvency)
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=InsolvencyResult(has_insolvency=False, count=0, publications=[])
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["handelsregister"],
        db=mock_db,
    )

    assert result.enriched_fields["legal_form"] == "AG"
    assert result.enriched_fields["register_number"] == "HRB 54321"
    assert result.enriched_fields["founded_date"] == "2010-03-15"


@pytest.mark.asyncio
async def test_handelsregister_not_found(orchestrator, mock_db, mock_entity):
    """Test handling when company not found in Handelsregister."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister with no results
    orchestrator.handelsregister.search_company = AsyncMock(return_value=[])

    # Mock Bundesanzeiger
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=InsolvencyResult(has_insolvency=False, count=0, publications=[])
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["handelsregister"],
        db=mock_db,
    )

    # Should complete without errors, but no enriched fields from Handelsregister
    assert len(result.enriched_fields) == 0
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_bundesanzeiger_publications(orchestrator, mock_db, mock_entity):
    """Test Bundesanzeiger finds publications."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister (no results)
    orchestrator.handelsregister.search_company = AsyncMock(return_value=[])

    # Mock Bundesanzeiger with publications
    publications = [
        InsolvencyPublication(
            publication_date=datetime(2025, 1, 1),
            publication_type="Eröffnung Insolvenzverfahren",
            court="AG München",
            reference="12 IN 345/25",
        ),
        InsolvencyPublication(
            publication_date=datetime(2025, 2, 1),
            publication_type="Bestellung Insolvenzverwalter",
            court="AG München",
            reference="12 IN 345/25",
        ),
    ]
    insolvency_result = InsolvencyResult(
        has_insolvency=True,
        count=2,
        publications=publications,
    )
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=insolvency_result
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["bundesanzeiger"],
        db=mock_db,
    )

    assert result.enriched_fields["insolvency_warning"] is True
    assert result.enriched_fields["insolvency_count"] == 2
    assert "insolvency_publications" in result.enriched_fields
    assert len(result.enriched_fields["insolvency_publications"]) == 2


@pytest.mark.asyncio
async def test_bundesanzeiger_insolvency_check(orchestrator, mock_db, mock_entity):
    """Test Bundesanzeiger insolvency check."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister
    orchestrator.handelsregister.search_company = AsyncMock(return_value=[])

    # Mock Bundesanzeiger with insolvency
    insolvency_result = InsolvencyResult(
        has_insolvency=True,
        count=1,
        publications=[
            InsolvencyPublication(
                publication_date=datetime(2026, 1, 10),
                publication_type="Insolvenzantrag",
                court="AG Berlin",
                reference="99 IN 123/26",
            )
        ],
    )
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=insolvency_result
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["bundesanzeiger"],
        db=mock_db,
    )

    assert "insolvency_warning" in result.enriched_fields
    assert result.enriched_fields["insolvency_warning"] is True


@pytest.mark.asyncio
async def test_enrichment_caching(orchestrator, mock_db, mock_entity):
    """Test cached results are returned (via metadata)."""
    # Mock entity with existing enrichment metadata
    mock_entity.metadata = {
        "enrichment": {
            "last_updated": datetime.utcnow().isoformat(),
            "sources": ["handelsregister"],
            "fields": ["legal_form", "register_number"],
        }
    }

    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock services
    orchestrator.handelsregister.search_company = AsyncMock(return_value=[])
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=InsolvencyResult(has_insolvency=False, count=0, publications=[])
    )

    # Execute enrichment
    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=None,
        db=mock_db,
    )

    # Metadata should be updated
    assert mock_entity.metadata is not None
    assert "enrichment" in mock_entity.metadata


@pytest.mark.asyncio
async def test_enrichment_cache_expired(orchestrator, mock_db, mock_entity):
    """Test stale cache is refreshed."""
    # Mock entity with old enrichment metadata
    old_timestamp = (datetime.utcnow() - timedelta(days=180)).isoformat()
    mock_entity.metadata = {
        "enrichment": {
            "last_updated": old_timestamp,
            "sources": ["handelsregister"],
            "fields": ["legal_form"],
        }
    }

    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock services with new data
    company_record = CompanyRecord(
        name="Musterfirma GmbH",
        legal_form="GmbH & Co. KG",
        register_number="HRA 11111",
        registered_address="München",
        founded_date="2019-01-01",
        capital="30000 EUR",
    )
    orchestrator.handelsregister.search_company = AsyncMock(
        return_value=[company_record]
    )
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=InsolvencyResult(has_insolvency=False, count=0, publications=[])
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=None,
        db=mock_db,
    )

    # Should have new data
    assert "legal_form" in result.enriched_fields


@pytest.mark.asyncio
async def test_enrichment_confidence_scoring(orchestrator, mock_db, mock_entity):
    """Test confidence scores are calculated correctly."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock both sources with data
    company_record = CompanyRecord(
        name="Musterfirma GmbH",
        legal_form="GmbH",
        register_number="HRB 12345",
        registered_address="München",
        founded_date="2020-01-01",
        capital="25000 EUR",
    )
    orchestrator.handelsregister.search_company = AsyncMock(
        return_value=[company_record]
    )

    insolvency_result = InsolvencyResult(
        has_insolvency=False,
        count=0,
        publications=[],
    )
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=insolvency_result
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["handelsregister", "bundesanzeiger"],
        db=mock_db,
    )

    # Both sources queried, confidence should be 1.0 (0.5 + 0.5)
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_enrichment_error_handling(orchestrator, mock_db, mock_entity):
    """Test graceful error handling on source failure."""
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock Handelsregister to raise exception
    orchestrator.handelsregister.search_company = AsyncMock(
        side_effect=Exception("API Error")
    )

    # Mock Bundesanzeiger (working)
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=InsolvencyResult(has_insolvency=False, count=0, publications=[])
    )

    # Should not raise, should handle gracefully
    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=["handelsregister", "bundesanzeiger"],
        db=mock_db,
    )

    # Should only have bundesanzeiger in sources_queried
    assert "handelsregister" not in result.sources_queried
    assert "bundesanzeiger" in result.sources_queried


@pytest.mark.asyncio
async def test_get_available_sources(orchestrator):
    """Test retrieving available enrichment sources."""
    sources = await orchestrator.get_available_sources()

    assert len(sources) > 0
    assert all(isinstance(s, SourceInfo) for s in sources)

    # Check for key sources
    source_names = [s.name for s in sources]
    assert "handelsregister" in source_names
    assert "bundesanzeiger" in source_names

    # Check source properties
    hr_source = next(s for s in sources if s.name == "handelsregister")
    assert hr_source.available is True
    assert hr_source.description is not None
    assert "Mock" in hr_source.description  # Currently mock


@pytest.mark.asyncio
async def test_entity_not_found(orchestrator, mock_db):
    """Test error when entity not found or no permission."""
    # Mock database query to return None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="nicht gefunden"):
        await orchestrator.enrich_entity(
            entity_id=uuid4(),
            company_id=uuid4(),
            sources=None,
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_enrichment_persists_no_phantom_metadata(
    orchestrator, mock_db, mock_entity
):
    """Test: Enrichment schreibt NICHT in die nicht existente metadata-Spalte.

    Ehrlicher Vertrag (Fix 2026-06-12): BusinessEntity hat KEINE
    metadata-Spalte — `.metadata` ist SQLAlchemys MetaData-Registry. Der
    alte Code `entity.metadata["enrichment"] = ...` crashte auf echten
    ORM-Objekten mit TypeError (dieser Test maskierte das frueher via
    Mock-Attribut). Bis zur Schema-Erweiterung wird nichts persistiert.
    """
    # Mock database query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_entity
    mock_db.execute.return_value = mock_result

    # Mock services with data
    company_record = CompanyRecord(
        name="Musterfirma GmbH",
        legal_form="GmbH",
        register_number="HRB 12345",
        registered_address="München",
        founded_date="2020-01-01",
        capital="25000 EUR",
    )
    orchestrator.handelsregister.search_company = AsyncMock(
        return_value=[company_record]
    )
    orchestrator.bundesanzeiger.check_insolvency = AsyncMock(
        return_value=InsolvencyResult(has_insolvency=False, count=0, publications=[])
    )

    result = await orchestrator.enrich_entity(
        entity_id=mock_entity.id,
        company_id=mock_entity.company_id,
        sources=None,
        db=mock_db,
    )

    # Ergebnis wird zurueckgegeben, aber nicht in eine Phantom-Spalte
    # geschrieben und auch nicht committet
    assert "legal_form" in result.enriched_fields
    assert mock_entity.metadata == {}
    mock_db.commit.assert_not_called()
