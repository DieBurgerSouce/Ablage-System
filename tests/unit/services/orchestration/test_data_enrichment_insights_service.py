# -*- coding: utf-8 -*-
"""
Unit Tests fuer DataEnrichmentInsightsService.

Testet:
- Fehlende Stammdaten-Erkennung
- Duplikat-Erkennung
- Inkonsistenz-Erkennung
- Datenqualitaets-Score

PHASE 6: Proaktive Intelligenz
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.data_enrichment_insights_service import (
    DataEnrichmentInsightsService,
    DataIssueType,
    DataEnrichmentResult,
    DataQualitySummary,
    get_data_enrichment_insights_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    DataEnrichmentInsightsService._instance = None
    yield
    DataEnrichmentInsightsService._instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return DataEnrichmentInsightsService()


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_company_id():
    """Sample Company ID."""
    return uuid4()


@pytest.fixture
def sample_entity_with_missing_data():
    """Sample Entity mit fehlenden Stammdaten."""
    return MagicMock(
        id=uuid4(),
        name="Lieferant ABC GmbH",
        entity_type="supplier",
        vat_id=None,  # Fehlend
        iban=None,  # Fehlend
        address="Musterstr. 1",
        city="Berlin",
        postal_code="10115",
        country="DE",
        email="kontakt@abc.de",
        phone=None,  # Fehlend
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
        updated_at=datetime.now(timezone.utc) - timedelta(days=30),
    )


@pytest.fixture
def sample_entity_complete():
    """Sample Entity mit vollstaendigen Daten."""
    return MagicMock(
        id=uuid4(),
        name="Lieferant XYZ AG",
        entity_type="supplier",
        vat_id="DE123456789",
        iban="DE89370400440532013000",
        address="Hauptstr. 10",
        city="Muenchen",
        postal_code="80331",
        country="DE",
        email="info@xyz.de",
        phone="+49 89 12345678",
        created_at=datetime.now(timezone.utc) - timedelta(days=90),
        updated_at=datetime.now(timezone.utc) - timedelta(days=5),
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = DataEnrichmentInsightsService()
        instance2 = DataEnrichmentInsightsService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_data_enrichment_insights_service()
        instance2 = get_data_enrichment_insights_service()

        assert instance1 is instance2


# =============================================================================
# DataIssueType Tests
# =============================================================================

class TestDataIssueType:
    """Tests fuer DataIssueType Enum."""

    def test_issue_types_defined(self):
        """Alle IssueTypes sind definiert."""
        assert DataIssueType.MISSING_FIELD.value == "missing_field"
        assert DataIssueType.DUPLICATE.value == "duplicate"
        assert DataIssueType.INCONSISTENT.value == "inconsistent"
        assert DataIssueType.OUTDATED.value == "outdated"
        assert DataIssueType.INVALID_FORMAT.value == "invalid_format"
        assert DataIssueType.UNLINKED.value == "unlinked"


# =============================================================================
# DataEnrichmentResult Tests
# =============================================================================

class TestDataEnrichmentResult:
    """Tests fuer DataEnrichmentResult Dataclass."""

    def test_defaults(self):
        """DataEnrichmentResult hat sinnvolle Defaults."""
        result = DataEnrichmentResult(
            issue_type=DataIssueType.MISSING_FIELD,
            title="Test Issue",
            message="Test Message",
        )

        assert result.severity == "medium"
        assert result.affected_field is None
        assert result.suggested_value is None
        assert result.entity_id is None
        assert result.confidence == 0.0

    def test_to_insight_conversion(self):
        """DataEnrichmentResult kann zu ProactiveInsight konvertiert werden."""
        result = DataEnrichmentResult(
            issue_type=DataIssueType.MISSING_FIELD,
            title="Fehlende USt-IdNr.",
            message="Lieferant ABC hat keine USt-IdNr. hinterlegt.",
            detail="Die USt-IdNr. wird fuer den Vorsteuerabzug benoetigt.",
            severity="high",
            affected_field="vat_id",
            suggested_value="DE123456789",
            entity_id=uuid4(),
            entity_name="Lieferant ABC",
            confidence=0.85,
        )

        insight = result.to_insight()

        assert insight.insight_type.value == "warning"
        assert insight.priority.value == "high"
        assert insight.title == "Fehlende USt-IdNr."


# =============================================================================
# DataQualitySummary Tests
# =============================================================================

class TestDataQualitySummary:
    """Tests fuer DataQualitySummary Dataclass."""

    def test_quality_score_calculation(self, service):
        """Qualitaets-Score wird korrekt berechnet."""
        summary = DataQualitySummary(
            total_entities=100,
            entities_with_issues=20,
            total_issues=35,
            issues_by_type={
                DataIssueType.MISSING_FIELD: 15,
                DataIssueType.DUPLICATE: 5,
                DataIssueType.INCONSISTENT: 10,
                DataIssueType.OUTDATED: 5,
            },
            quality_score=80.0,  # 100 - 20% mit Issues
            grade="B",
        )

        assert summary.quality_score == 80.0
        assert summary.grade == "B"

    def test_grade_assignment(self, service):
        """Note wird korrekt zugewiesen."""
        assert service._get_grade(95) == "A"
        assert service._get_grade(85) == "B"
        assert service._get_grade(75) == "C"
        assert service._get_grade(65) == "D"
        assert service._get_grade(50) == "F"


# =============================================================================
# Missing Data Detection Tests
# =============================================================================

class TestMissingDataDetection:
    """Tests fuer Erkennung fehlender Stammdaten."""

    @pytest.mark.asyncio
    async def test_detect_missing_master_data(
        self, service, mock_db, sample_company_id, sample_entity_with_missing_data
    ):
        """Erkennt fehlende Stammdaten."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[sample_entity_with_missing_data]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_missing_master_data(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_required_fields_per_entity_type(self, service):
        """Pflichtfelder sind pro Entity-Typ definiert."""
        supplier_fields = service._get_required_fields("supplier")
        customer_fields = service._get_required_fields("customer")

        # Lieferanten brauchen IBAN fuer Zahlung
        assert "iban" in supplier_fields
        # Kunden brauchen mindestens Name und Adresse
        assert "name" in customer_fields
        assert "address" in customer_fields

    def test_check_missing_fields(self, service, sample_entity_with_missing_data):
        """Prueft fehlende Felder korrekt."""
        required_fields = ["name", "vat_id", "iban", "address"]

        missing = service._check_missing_fields(
            sample_entity_with_missing_data,
            required_fields
        )

        assert "vat_id" in missing
        assert "iban" in missing
        assert "name" not in missing  # Vorhanden
        assert "address" not in missing  # Vorhanden


# =============================================================================
# Duplicate Detection Tests
# =============================================================================

class TestDuplicateDetection:
    """Tests fuer Duplikat-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_duplicates(self, service, mock_db, sample_company_id):
        """Erkennt potenzielle Duplikate."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_duplicates(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_name_similarity_calculation(self, service):
        """Berechnet Namensaehnlichkeit korrekt."""
        # Sehr aehnlich
        sim1 = service._calculate_name_similarity(
            "Mueller GmbH",
            "Müller GmbH"
        )
        assert sim1 > 0.8

        # Gleich
        sim2 = service._calculate_name_similarity(
            "Test Company",
            "Test Company"
        )
        assert sim2 == 1.0

        # Komplett unterschiedlich
        sim3 = service._calculate_name_similarity(
            "ABC",
            "XYZ"
        )
        assert sim3 < 0.5

    def test_jaccard_similarity(self, service):
        """Jaccard-Similarity funktioniert korrekt."""
        set1 = {"a", "b", "c"}
        set2 = {"b", "c", "d"}

        similarity = service._jaccard_similarity(set1, set2)

        # Schnitt: {b, c} = 2, Vereinigung: {a, b, c, d} = 4 -> 2/4 = 0.5
        assert similarity == 0.5

    def test_potential_duplicate_detection(self, service):
        """Erkennt potenzielle Duplikate anhand von Kriterien."""
        entity1 = MagicMock(
            id=uuid4(),
            name="Mueller GmbH",
            address="Musterstr. 1",
            postal_code="10115",
        )
        entity2 = MagicMock(
            id=uuid4(),
            name="Müller GmbH",  # Aehnlich
            address="Musterstr. 1",  # Gleich
            postal_code="10115",  # Gleich
        )

        is_duplicate = service._is_potential_duplicate(entity1, entity2)

        assert is_duplicate is True


# =============================================================================
# Inconsistency Detection Tests
# =============================================================================

class TestInconsistencyDetection:
    """Tests fuer Inkonsistenz-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_inconsistencies(self, service, mock_db, sample_company_id):
        """Erkennt Inkonsistenzen zwischen Stammdaten und Dokumenten."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_inconsistencies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_iban_mismatch_detected(self, service):
        """Erkennt IBAN-Unterschiede."""
        entity_iban = "DE89370400440532013000"
        document_iban = "DE89370400440532013999"  # Andere IBAN

        is_inconsistent = service._check_iban_consistency(entity_iban, document_iban)

        assert is_inconsistent is True

    def test_vat_id_mismatch_detected(self, service):
        """Erkennt USt-IdNr.-Unterschiede."""
        entity_vat = "DE123456789"
        document_vat = "DE987654321"

        is_inconsistent = service._check_vat_consistency(entity_vat, document_vat)

        assert is_inconsistent is True


# =============================================================================
# Outdated Data Detection Tests
# =============================================================================

class TestOutdatedDataDetection:
    """Tests fuer veraltete Daten."""

    @pytest.mark.asyncio
    async def test_detect_outdated_data(self, service, mock_db, sample_company_id):
        """Erkennt veraltete Stammdaten."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_outdated_data(
            db=mock_db,
            company_id=sample_company_id,
            outdated_days=365,
        )

        assert isinstance(insights, list)

    def test_is_outdated_check(self, service):
        """Prueft ob Daten als veraltet gelten."""
        old_date = datetime.now(timezone.utc) - timedelta(days=400)
        recent_date = datetime.now(timezone.utc) - timedelta(days=30)

        assert service._is_outdated(old_date, threshold_days=365) is True
        assert service._is_outdated(recent_date, threshold_days=365) is False


# =============================================================================
# Unlinked Documents Tests
# =============================================================================

class TestUnlinkedDocuments:
    """Tests fuer nicht verknuepfte Dokumente."""

    @pytest.mark.asyncio
    async def test_detect_unlinked_documents(self, service, mock_db, sample_company_id):
        """Erkennt Dokumente ohne Entity-Verknuepfung."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=15)  # 15 unverknuepfte Dokumente
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_unlinked_documents(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)


# =============================================================================
# Data Quality Summary Tests
# =============================================================================

class TestDataQualitySummaryGeneration:
    """Tests fuer Datenqualitaets-Zusammenfassung."""

    @pytest.mark.asyncio
    async def test_get_data_quality_summary(self, service, mock_db, sample_company_id):
        """Generiert Datenqualitaets-Zusammenfassung."""
        # Mock: 100 Entities, 20 mit Issues
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(side_effect=[100, 20])
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await service.get_data_quality_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(summary, DataQualitySummary)

    def test_calculate_quality_score(self, service):
        """Berechnet Qualitaets-Score korrekt."""
        # 80 von 100 Entities sind in Ordnung
        score = service._calculate_quality_score(
            total_entities=100,
            entities_with_issues=20
        )

        assert score == 80.0

    def test_calculate_quality_score_empty(self, service):
        """Qualitaets-Score bei 0 Entities."""
        score = service._calculate_quality_score(
            total_entities=0,
            entities_with_issues=0
        )

        assert score == 100.0  # Keine Entities = keine Issues


# =============================================================================
# Combined Analysis Tests
# =============================================================================

class TestCombinedDataAnalysis:
    """Tests fuer kombinierte Datenanalyse."""

    @pytest.mark.asyncio
    async def test_get_all_data_insights(self, service, mock_db, sample_company_id):
        """Kombinierte Datenanalyse."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_result.scalar = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.get_all_data_insights(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)


# =============================================================================
# Severity Determination Tests
# =============================================================================

class TestSeverityDetermination:
    """Tests fuer Schweregrad-Bestimmung."""

    def test_severity_for_missing_critical_field(self, service):
        """Kritische fehlende Felder haben hohe Prioritaet."""
        severity = service._get_severity_for_missing_field("iban", "supplier")

        assert severity in ["high", "critical"]

    def test_severity_for_missing_optional_field(self, service):
        """Optionale fehlende Felder haben niedrige Prioritaet."""
        severity = service._get_severity_for_missing_field("phone", "supplier")

        assert severity == "low"

    def test_severity_for_duplicate(self, service):
        """Duplikate haben mittlere Prioritaet."""
        severity = service._get_severity_for_issue(DataIssueType.DUPLICATE)

        assert severity == "medium"

    def test_severity_for_inconsistency(self, service):
        """Inkonsistenzen haben hohe Prioritaet."""
        severity = service._get_severity_for_issue(DataIssueType.INCONSISTENT)

        assert severity == "high"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_handles_empty_entities(self, service, mock_db, sample_company_id):
        """Behandelt leere Entity-Liste."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_missing_master_data(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_db_error(self, service, mock_db, sample_company_id):
        """Behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_duplicates(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    def test_handles_none_values(self, service):
        """Behandelt None-Werte korrekt."""
        entity = MagicMock(
            name=None,
            vat_id=None,
            iban=None,
        )

        missing = service._check_missing_fields(
            entity, ["name", "vat_id", "iban"]
        )

        assert "name" in missing
        assert "vat_id" in missing
        assert "iban" in missing

    def test_handles_empty_strings(self, service):
        """Behandelt leere Strings als fehlend."""
        entity = MagicMock(
            name="Valid Name",
            vat_id="",  # Leerer String
            iban="   ",  # Nur Whitespace
        )

        missing = service._check_missing_fields(
            entity, ["name", "vat_id", "iban"]
        )

        assert "vat_id" in missing
        assert "iban" in missing
        assert "name" not in missing
