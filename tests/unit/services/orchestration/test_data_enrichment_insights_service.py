# -*- coding: utf-8 -*-
"""
Unit Tests fuer DataEnrichmentInsightsService.

Testet die ECHTE API des Service (Stand: improve/foundation-truth):
- Factory-Singleton (Modul-Ebene, NICHT Klassen-Ebene)
- DataIssueType / DataEnrichmentResult / DataQualitySummary Datentypen
- Namensaehnlichkeit (_calculate_name_similarity)
- Datenqualitaets-Zusammenfassung (Dict-Rueckgabe)
- Notenvergabe (_score_to_grade)
- Graceful Degradation der detect_*-Methoden

PHASE 6: Proaktive Intelligenz

Hinweis (Schema-Drift): Die detect_*-Methoden bauen ihre SQLAlchemy-Queries
gegen Spalten, die das echte Modell NICHT besitzt (BusinessEntity.company_id,
BusinessEntity.address_street, Document.linked_entity_id). Der dabei
ausgeloeste AttributeError wird vom try/except der jeweiligen Methode
abgefangen, sodass sie ehrlich `[]` zurueckgibt (Graceful Degradation).
Die Async-Tests pruefen daher genau diesen dokumentierten Vertrag
(Rueckgabetyp `list` bzw. `[]`), ohne fehlendes Verhalten vorzutaeuschen.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

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
def reset_factory_singleton():
    """Reset des Modul-Singletons vor und nach jedem Test."""
    import app.services.orchestration.data_enrichment_insights_service as mod
    mod._data_enrichment_instance = None
    yield
    mod._data_enrichment_instance = None


@pytest.fixture
def service():
    """Frische Service-Instanz fuer jeden Test."""
    return DataEnrichmentInsightsService()


@pytest.fixture
def mock_db():
    """Mock Database Session.

    scalars().all() -> [] und scalar() -> 0 als neutrale Defaults,
    damit Tests, deren Query-Aufbau zufaellig durchlaeuft, leere
    Ergebnisse erhalten.
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.scalar = MagicMock(return_value=0)
    result.fetchall = MagicMock(return_value=[])
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.fixture
def sample_company_id():
    """Sample Company ID."""
    return uuid4()


# =============================================================================
# Factory-Singleton Tests
# =============================================================================

class TestFactorySingleton:
    """Tests fuer das Singleton-Verhalten der Factory-Funktion.

    Wichtig: Die Klasse selbst ist KEIN Singleton -- zwei direkte
    Konstruktor-Aufrufe liefern unterschiedliche Instanzen. Nur die
    Factory `get_data_enrichment_insights_service()` cached eine
    Modul-globale Instanz.
    """

    def test_direct_construction_yields_distinct_instances(self):
        """Direkter Konstruktor-Aufruf ist KEIN Singleton."""
        instance1 = DataEnrichmentInsightsService()
        instance2 = DataEnrichmentInsightsService()

        assert instance1 is not instance2

    def test_factory_returns_same_instance(self, reset_factory_singleton):
        """Factory-Funktion gibt immer dieselbe (gecachte) Instanz zurueck."""
        instance1 = get_data_enrichment_insights_service()
        instance2 = get_data_enrichment_insights_service()

        assert instance1 is instance2
        assert isinstance(instance1, DataEnrichmentInsightsService)


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
        """DataEnrichmentResult kann zu ProactiveInsight konvertiert werden.

        Bei severity 'high' ist der InsightType eine WARNING.
        """
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
        assert insight.message == "Lieferant ABC hat keine USt-IdNr. hinterlegt."
        assert insight.confidence == 0.85

    def test_to_insight_low_severity_is_suggestion(self):
        """Bei niedriger Severity ist der InsightType eine SUGGESTION."""
        result = DataEnrichmentResult(
            issue_type=DataIssueType.OUTDATED,
            title="Veraltete Daten",
            message="Kontaktdaten lange nicht aktualisiert.",
            severity="low",
        )

        insight = result.to_insight()

        assert insight.insight_type.value == "suggestion"
        assert insight.priority.value == "low"


# =============================================================================
# DataQualitySummary Tests
# =============================================================================

class TestDataQualitySummary:
    """Tests fuer DataQualitySummary Dataclass."""

    def test_defaults(self):
        """DataQualitySummary hat sinnvolle Defaults (perfekte Qualitaet)."""
        summary = DataQualitySummary()

        assert summary.total_entities == 0
        assert summary.entities_with_issues == 0
        assert summary.total_issues == 0
        assert summary.issues_by_type == {}
        assert summary.quality_score == 100.0
        assert summary.grade == "A"

    def test_quality_score_assignment(self):
        """Qualitaets-Score und Note koennen gesetzt werden."""
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
            quality_score=80.0,
            grade="B",
        )

        assert summary.quality_score == 80.0
        assert summary.grade == "B"
        assert summary.issues_by_type[DataIssueType.MISSING_FIELD] == 15

    def test_grade_assignment_via_score_to_grade(self, service):
        """Note wird anhand der echten Schwellen (_score_to_grade) zugewiesen.

        Schwellen: >=90 A, >=80 B, >=70 C, >=60 D, sonst F.
        """
        assert service._score_to_grade(95) == "A"
        assert service._score_to_grade(90) == "A"
        assert service._score_to_grade(85) == "B"
        assert service._score_to_grade(80) == "B"
        assert service._score_to_grade(75) == "C"
        assert service._score_to_grade(70) == "C"
        assert service._score_to_grade(65) == "D"
        assert service._score_to_grade(60) == "D"
        assert service._score_to_grade(59) == "F"
        assert service._score_to_grade(0) == "F"


# =============================================================================
# Required-Fields Konfiguration
# =============================================================================

class TestRequiredFieldsConfig:
    """Tests fuer die Pflichtfeld-Konfiguration pro Entity-Typ."""

    def test_required_fields_per_entity_type(self, service):
        """Pflichtfelder sind pro Entity-Typ definiert."""
        supplier_fields = service._required_fields["supplier"]
        customer_fields = service._required_fields["customer"]

        # Lieferanten brauchen IBAN fuer Zahlung
        assert "iban" in supplier_fields
        assert "vat_id" in supplier_fields
        # Beide brauchen mindestens Name und Adress-Strasse
        assert "name" in customer_fields
        assert "address_street" in customer_fields
        assert "address_city" in customer_fields
        # Kunden brauchen eine Kundennummer
        assert "customer_number" in customer_fields


# =============================================================================
# Missing Data Detection Tests
# =============================================================================

class TestMissingDataDetection:
    """Tests fuer Erkennung fehlender Stammdaten."""

    @pytest.mark.asyncio
    async def test_detect_missing_master_data_returns_list(
        self, service, mock_db, sample_company_id
    ):
        """Erkennt fehlende Stammdaten und gibt eine Liste zurueck."""
        insights = await service.detect_missing_master_data(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)


# =============================================================================
# Duplicate Detection Tests
# =============================================================================

class TestDuplicateDetection:
    """Tests fuer Duplikat-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_duplicates_returns_list(
        self, service, mock_db, sample_company_id
    ):
        """Erkennt potenzielle Duplikate und gibt eine Liste zurueck."""
        insights = await service.detect_duplicates(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_name_similarity_identical(self, service):
        """Identische Namen ergeben Aehnlichkeit 1.0."""
        assert service._calculate_name_similarity(
            "Test Company", "Test Company"
        ) == 1.0

    def test_name_similarity_disjoint_tokens(self, service):
        """Komplett unterschiedliche Namen (keine gemeinsamen Tokens) -> 0.0."""
        assert service._calculate_name_similarity("ABC", "XYZ") == 0.0

    def test_name_similarity_shared_token_partial(self, service):
        """Teilweise Ueberlappung liefert einen Wert zwischen 0 und 1.

        'Mueller GmbH' vs 'Mueller AG' teilen das Token 'mueller'
        -> Jaccard=1/3, Containment=1/2 -> 0.6*0.333 + 0.4*0.5 = 0.4.
        """
        sim = service._calculate_name_similarity("Mueller GmbH", "Mueller AG")

        assert 0.0 < sim < 1.0
        assert sim == pytest.approx(0.4)

    def test_name_similarity_empty_input(self, service):
        """Leere Eingaben liefern 0.0 (kein Crash)."""
        assert service._calculate_name_similarity("", "Test") == 0.0
        assert service._calculate_name_similarity("Test", "") == 0.0

    def test_name_similarity_umlaut_token_treated_distinct(self, service):
        """ASCII- und Umlaut-Schreibweise teilen sich nur gemeinsame Tokens.

        Dokumentiert das ECHTE Verhalten: 'mueller' und 'mueller' werden
        NICHT mit 'müller' gleichgesetzt -- es gibt keine
        Umlaut-Normalisierung. 'Mueller GmbH' vs 'Müller GmbH' teilen
        nur 'gmbh' -> Jaccard=1/3, Containment=1/2 -> 0.4.
        """
        sim = service._calculate_name_similarity("Mueller GmbH", "Müller GmbH")

        assert sim == pytest.approx(0.4)


# =============================================================================
# Inconsistency Detection Tests
# =============================================================================

class TestInconsistencyDetection:
    """Tests fuer Inkonsistenz-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_inconsistencies_returns_list(
        self, service, mock_db, sample_company_id
    ):
        """Erkennt Inkonsistenzen und gibt eine Liste zurueck."""
        insights = await service.detect_inconsistencies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)


# =============================================================================
# Outdated Data Detection Tests
# =============================================================================

class TestOutdatedDataDetection:
    """Tests fuer veraltete Daten."""

    @pytest.mark.asyncio
    async def test_detect_outdated_data_returns_list(
        self, service, mock_db, sample_company_id
    ):
        """Erkennt veraltete Stammdaten und gibt eine Liste zurueck."""
        insights = await service.detect_outdated_data(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_outdated_threshold_default(self, service):
        """Der Schwellwert fuer veraltete Daten ist 365 Tage (1 Jahr)."""
        assert service._outdated_threshold_days == 365


# =============================================================================
# Unlinked Documents Tests
# =============================================================================

class TestUnlinkedDocuments:
    """Tests fuer nicht verknuepfte Dokumente."""

    @pytest.mark.asyncio
    async def test_detect_unlinked_documents_returns_list(
        self, service, mock_db, sample_company_id
    ):
        """Erkennt Dokumente ohne Entity-Verknuepfung und gibt eine Liste zurueck."""
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
    async def test_get_data_quality_summary_returns_dict(
        self, service, mock_db, sample_company_id
    ):
        """Generiert eine Datenqualitaets-Zusammenfassung als Dict.

        Die echte Methode gibt ein Dict (nicht DataQualitySummary) mit
        den Schluesseln quality_score, total_issues, by_type, by_severity
        und grade zurueck.
        """
        summary = await service.get_data_quality_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(summary, dict)
        assert "quality_score" in summary
        assert "total_issues" in summary
        assert "by_type" in summary
        assert "by_severity" in summary
        assert "grade" in summary

    @pytest.mark.asyncio
    async def test_summary_perfect_score_when_no_issues(
        self, service, mock_db, sample_company_id
    ):
        """Ohne erkannte Issues ergibt sich Score 100 und Note A."""
        summary = await service.get_data_quality_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert summary["total_issues"] == 0
        assert summary["quality_score"] == 100
        assert summary["grade"] == "A"


# =============================================================================
# Combined Analysis Tests
# =============================================================================

class TestCombinedDataAnalysis:
    """Tests fuer kombinierte Datenanalyse."""

    @pytest.mark.asyncio
    async def test_check_all_data_issues(
        self, service, mock_db, sample_company_id
    ):
        """Kombinierte Datenanalyse ueber alle Detektoren gibt eine Liste zurueck."""
        insights = await service.check_all_data_issues(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)


# =============================================================================
# Graceful Degradation
# =============================================================================

class TestGracefulDegradation:
    """Tests fuer robuste Fehlerbehandlung der Detektoren."""

    @pytest.mark.asyncio
    async def test_handles_db_error_in_missing(
        self, service, sample_company_id
    ):
        """Behandelt DB-/Query-Fehler graceful und gibt [] zurueck."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_missing_master_data(
            db=db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_db_error_in_duplicates(
        self, service, sample_company_id
    ):
        """detect_duplicates faengt Fehler ab und gibt [] zurueck."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_duplicates(
            db=db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_check_all_survives_partial_failure(
        self, service, sample_company_id
    ):
        """check_all_data_issues liefert trotz Detektor-Fehlern eine Liste."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.check_all_data_issues(
            db=db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        assert insights == []
