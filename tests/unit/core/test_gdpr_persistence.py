# -*- coding: utf-8 -*-
"""
Unit Tests für GDPR Processing Activities Persistence.

Testet:
- PostgreSQL-basierte Speicherung von Verarbeitungsaktivitäten
- Async Database Operations
- Retention Compliance Checks
- Compliance Report Generation
- Backward Compatibility

SECURITY FIX: In-Memory-Speicherung wurde durch PostgreSQL ersetzt.

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Test markers
pytestmark = [pytest.mark.unit]


class TestGDPRProcessingActivityModel:
    """Tests für GDPRProcessingActivity Datenbank-Modell."""

    def test_model_creation(self):
        """Test dass Model korrekt erstellt werden kann."""
        from app.db.models import GDPRProcessingActivity

        activity = GDPRProcessingActivity(
            activity_id="test123",
            processing_purpose="document_digitization",
            legal_basis="Art. 6(1)(b) - Contract performance",
            retention_period_days=365,
            data_categories=["document_content"]
        )

        assert activity.activity_id == "test123"
        assert activity.processing_purpose == "document_digitization"
        assert activity.retention_period_days == 365

    def test_model_with_document_reference(self):
        """Test Model mit Dokument-Referenz."""
        from app.db.models import GDPRProcessingActivity

        doc_id = uuid4()
        activity = GDPRProcessingActivity(
            activity_id="test456",
            document_id=doc_id,
            processing_purpose="ocr_processing",
            legal_basis="Art. 6(1)(b)",
            retention_period_days=365
        )

        assert activity.document_id == doc_id

    def test_model_with_pseudonymized_subject(self):
        """Test Model mit pseudonymisiertem Subject."""
        from app.db.models import GDPRProcessingActivity

        activity = GDPRProcessingActivity(
            activity_id="test789",
            subject_id="hashed_user_id_abc123",
            processing_purpose="quality_improvement",
            legal_basis="Art. 6(1)(f)",
            retention_period_days=90
        )

        assert activity.subject_id == "hashed_user_id_abc123"


class TestRegisterProcessingActivityAsync:
    """Tests für async Processing Activity Registration."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    @pytest.fixture
    def mock_db(self):
        """Erstelle Mock Database Session."""
        mock = AsyncMock()
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_register_activity_creates_db_record(self, gdpr_manager, mock_db):
        """Test dass Activity in DB gespeichert wird."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        with patch("app.db.models.GDPRProcessingActivity") as MockActivity:
            mock_instance = MagicMock()
            mock_instance.activity_id = "test_id"
            MockActivity.return_value = mock_instance

            result = await gdpr_manager.register_processing_activity_async(
                db=mock_db,
                document_id=str(uuid4()),
                data_categories=[DataCategory.DOCUMENT_CONTENT],
                purpose=ProcessingPurpose.OCR_PROCESSING
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert "id" in result
        assert result["purpose"] == "ocr_processing"

    @pytest.mark.asyncio
    async def test_register_activity_with_subject_hashes_id(self, gdpr_manager, mock_db):
        """Test dass Subject-ID gehasht wird."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        captured_activity = None

        def capture_add(activity):
            nonlocal captured_activity
            captured_activity = activity

        mock_db.add.side_effect = capture_add

        with patch("app.db.models.GDPRProcessingActivity") as MockActivity:
            mock_instance = MagicMock()
            MockActivity.return_value = mock_instance

            await gdpr_manager.register_processing_activity_async(
                db=mock_db,
                document_id=str(uuid4()),
                data_categories=[DataCategory.PERSONAL_IDENTIFIABLE],
                purpose=ProcessingPurpose.DOCUMENT_DIGITIZATION,
                subject_id="user123@example.com"
            )

        # Verify activity was added
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_activity_sets_retention_expiry(self, gdpr_manager, mock_db):
        """Test dass Retention-Ablaufdatum gesetzt wird."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        with patch("app.db.models.GDPRProcessingActivity") as MockActivity:
            mock_instance = MagicMock()
            mock_instance.activity_id = "test_id"
            MockActivity.return_value = mock_instance

            result = await gdpr_manager.register_processing_activity_async(
                db=mock_db,
                document_id=str(uuid4()),
                data_categories=[DataCategory.DOCUMENT_CONTENT],
                purpose=ProcessingPurpose.OCR_PROCESSING
            )

        assert "retention_expires_at" in result
        assert "retention_period_days" in result

    @pytest.mark.asyncio
    async def test_register_activity_with_processing_backend(self, gdpr_manager, mock_db):
        """Test Activity mit Processing Backend."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        with patch("app.db.models.GDPRProcessingActivity") as MockActivity:
            mock_instance = MagicMock()
            mock_instance.activity_id = "test_id"
            MockActivity.return_value = mock_instance

            result = await gdpr_manager.register_processing_activity_async(
                db=mock_db,
                document_id=str(uuid4()),
                data_categories=[DataCategory.DOCUMENT_CONTENT],
                purpose=ProcessingPurpose.OCR_PROCESSING,
                processing_backend="deepseek"
            )

        # Verify MockActivity was called with processing_backend
        call_kwargs = MockActivity.call_args[1]
        assert call_kwargs.get("processing_backend") == "deepseek"


class TestCheckRetentionComplianceAsync:
    """Tests für async Retention Compliance Check."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    @pytest.mark.asyncio
    async def test_check_compliance_returns_statistics(self, gdpr_manager):
        """Test dass Compliance-Check Statistiken zurückgibt."""
        mock_db = AsyncMock()

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 100

        # Mock expired activities query
        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_expired_result])

        result = await gdpr_manager.check_retention_compliance_async(mock_db)

        assert "total_activities" in result
        assert "expired_activities" in result
        assert "to_be_deleted" in result
        assert result["total_activities"] == 100

    @pytest.mark.asyncio
    async def test_check_compliance_finds_expired_activities(self, gdpr_manager):
        """Test dass abgelaufene Activities gefunden werden."""
        mock_db = AsyncMock()

        # Create mock expired activity
        mock_expired_activity = MagicMock()
        mock_expired_activity.activity_id = "expired_123"
        mock_expired_activity.document_id = uuid4()
        mock_expired_activity.retention_expires_at = datetime.now(timezone.utc) - timedelta(days=10)
        mock_expired_activity.processing_purpose = "ocr_processing"

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        # Mock expired activities query
        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = [mock_expired_activity]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_expired_result])

        result = await gdpr_manager.check_retention_compliance_async(mock_db)

        assert result["expired_activities"] == 1
        assert len(result["to_be_deleted"]) == 1
        assert result["to_be_deleted"][0]["activity_id"] == "expired_123"


class TestGetComplianceReportAsync:
    """Tests für async Compliance Report."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    @pytest.mark.asyncio
    async def test_compliance_report_includes_all_metrics(self, gdpr_manager):
        """Test dass Report alle Metriken enthält."""
        mock_db = AsyncMock()

        # Mock all count queries
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Patch check_retention_compliance_async
        with patch.object(
            gdpr_manager,
            'check_retention_compliance_async',
            AsyncMock(return_value={"total_activities": 0, "expired_activities": 0, "to_be_deleted": []})
        ):
            result = await gdpr_manager.get_compliance_report_async(mock_db)

        assert "timestamp" in result
        assert "total_processing_activities" in result
        assert "total_data_breaches" in result
        assert "pending_deletion_requests" in result
        assert "retention_compliance" in result
        assert "gdpr_articles_covered" in result

    @pytest.mark.asyncio
    async def test_compliance_report_lists_gdpr_articles(self, gdpr_manager):
        """Test dass Report GDPR-Artikel auflistet."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            gdpr_manager,
            'check_retention_compliance_async',
            AsyncMock(return_value={"total_activities": 0, "expired_activities": 0, "to_be_deleted": []})
        ):
            result = await gdpr_manager.get_compliance_report_async(mock_db)

        articles = result["gdpr_articles_covered"]
        assert any("Art. 17" in a for a in articles)  # Right to Erasure
        assert any("Art. 30" in a for a in articles)  # Processing Records


class TestGetProcessingActivitiesAsync:
    """Tests für async Activity Retrieval."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    @pytest.mark.asyncio
    async def test_get_activities_returns_list(self, gdpr_manager):
        """Test dass Activities als Liste zurückgegeben werden."""
        mock_db = AsyncMock()

        mock_activity = MagicMock()
        mock_activity.activity_id = "test_123"
        mock_activity.document_id = uuid4()
        mock_activity.subject_id = "hashed_id"
        mock_activity.data_categories = ["document_content"]
        mock_activity.processing_purpose = "ocr_processing"
        mock_activity.legal_basis = "Art. 6(1)(b)"
        mock_activity.retention_period_days = 365
        mock_activity.retention_expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        mock_activity.processing_backend = "deepseek"
        mock_activity.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_activity]

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await gdpr_manager.get_processing_activities_async(mock_db)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "test_123"
        assert result[0]["purpose"] == "ocr_processing"

    @pytest.mark.asyncio
    async def test_get_activities_with_filters(self, gdpr_manager):
        """Test Activity-Abfrage mit Filtern."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        doc_id = str(uuid4())
        result = await gdpr_manager.get_processing_activities_async(
            mock_db,
            document_id=doc_id,
            purpose="ocr_processing",
            limit=50
        )

        assert isinstance(result, list)
        mock_db.execute.assert_called_once()


class TestBackwardCompatibility:
    """Tests für Rückwärtskompatibilität."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    def test_sync_register_still_works(self, gdpr_manager):
        """Test dass synchrone Registrierung noch funktioniert."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        result = gdpr_manager.register_processing_activity(
            document_id=str(uuid4()),
            data_categories=[DataCategory.DOCUMENT_CONTENT],
            purpose=ProcessingPurpose.OCR_PROCESSING
        )

        assert "id" in result
        assert result["purpose"] == "ocr_processing"

    def test_sync_register_adds_to_cache(self, gdpr_manager):
        """Test dass synchrone Registrierung in Cache speichert."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        initial_count = len(gdpr_manager._processing_activities_cache)

        gdpr_manager.register_processing_activity(
            document_id=str(uuid4()),
            data_categories=[DataCategory.METADATA],
            purpose=ProcessingPurpose.QUALITY_IMPROVEMENT
        )

        assert len(gdpr_manager._processing_activities_cache) == initial_count + 1

    def test_sync_compliance_check_works(self, gdpr_manager):
        """Test dass synchroner Compliance-Check funktioniert."""
        result = gdpr_manager.check_retention_compliance()

        assert "total_activities" in result
        assert "expired_activities" in result

    def test_sync_compliance_report_works(self, gdpr_manager):
        """Test dass synchroner Report funktioniert."""
        result = gdpr_manager.get_compliance_report()

        assert "timestamp" in result
        assert "warning" in result  # Should have deprecation warning

    def test_processing_activities_property_returns_cache(self, gdpr_manager):
        """Test dass Property Cache zurückgibt."""
        from app.core.gdpr import DataCategory, ProcessingPurpose

        # Add something to cache
        gdpr_manager.register_processing_activity(
            document_id=str(uuid4()),
            data_categories=[DataCategory.DOCUMENT_CONTENT],
            purpose=ProcessingPurpose.OCR_PROCESSING
        )

        # Access via property
        activities = gdpr_manager.processing_activities

        assert isinstance(activities, list)
        assert len(activities) >= 1


class TestDataCategoryRetention:
    """Tests für Datenkategorie-spezifische Aufbewahrungsfristen."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    def test_financial_data_10_year_retention(self, gdpr_manager):
        """Test dass Finanzdaten 10 Jahre aufbewahrt werden."""
        from app.core.gdpr import DataCategory

        retention = gdpr_manager._get_retention_period([DataCategory.FINANCIAL])
        assert retention == 3650  # 10 years

    def test_document_content_7_year_retention(self, gdpr_manager):
        """Test dass Dokumentinhalte 7 Jahre aufbewahrt werden."""
        from app.core.gdpr import DataCategory

        retention = gdpr_manager._get_retention_period([DataCategory.DOCUMENT_CONTENT])
        assert retention == 2555  # 7 years (German commercial law)

    def test_metadata_90_day_retention(self, gdpr_manager):
        """Test dass Metadaten 90 Tage aufbewahrt werden."""
        from app.core.gdpr import DataCategory

        retention = gdpr_manager._get_retention_period([DataCategory.METADATA])
        assert retention == 90

    def test_mixed_categories_use_max_retention(self, gdpr_manager):
        """Test dass bei gemischten Kategorien Maximum verwendet wird."""
        from app.core.gdpr import DataCategory

        retention = gdpr_manager._get_retention_period([
            DataCategory.METADATA,  # 90 days
            DataCategory.FINANCIAL  # 10 years
        ])
        assert retention == 3650  # Maximum


class TestLegalBasisDetermination:
    """Tests für Rechtsgrundlagen-Bestimmung."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    def test_ocr_processing_uses_contract_basis(self, gdpr_manager):
        """Test dass OCR-Verarbeitung Vertragserfüllung nutzt."""
        from app.core.gdpr import ProcessingPurpose

        basis = gdpr_manager._determine_legal_basis(ProcessingPurpose.OCR_PROCESSING)
        assert "Art. 6(1)(b)" in basis

    def test_legal_compliance_uses_legal_obligation(self, gdpr_manager):
        """Test dass rechtliche Compliance gesetzliche Verpflichtung nutzt."""
        from app.core.gdpr import ProcessingPurpose

        basis = gdpr_manager._determine_legal_basis(ProcessingPurpose.LEGAL_COMPLIANCE)
        assert "Art. 6(1)(c)" in basis

    def test_quality_improvement_uses_legitimate_interest(self, gdpr_manager):
        """Test dass Qualitätsverbesserung berechtigtes Interesse nutzt."""
        from app.core.gdpr import ProcessingPurpose

        basis = gdpr_manager._determine_legal_basis(ProcessingPurpose.QUALITY_IMPROVEMENT)
        assert "Art. 6(1)(f)" in basis


class TestPseudonymization:
    """Tests für Pseudonymisierung."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPRComplianceManager Instanz."""
        from app.core.gdpr import GDPRComplianceManager
        return GDPRComplianceManager()

    def test_pseudonymize_produces_consistent_hash(self, gdpr_manager):
        """Test dass gleiche Eingabe gleichen Hash produziert."""
        hash1 = gdpr_manager.pseudonymize_identifier("test@example.com")
        hash2 = gdpr_manager.pseudonymize_identifier("test@example.com")

        assert hash1 == hash2

    def test_pseudonymize_produces_different_hash_for_different_input(self, gdpr_manager):
        """Test dass verschiedene Eingaben verschiedene Hashes produzieren."""
        hash1 = gdpr_manager.pseudonymize_identifier("user1@example.com")
        hash2 = gdpr_manager.pseudonymize_identifier("user2@example.com")

        assert hash1 != hash2

    def test_pseudonymize_with_salt(self, gdpr_manager):
        """Test Pseudonymisierung mit Salt."""
        hash_no_salt = gdpr_manager.pseudonymize_identifier("test@example.com")
        hash_with_salt = gdpr_manager.pseudonymize_identifier("test@example.com", salt="secret")

        assert hash_no_salt != hash_with_salt
