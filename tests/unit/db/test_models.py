"""Unit tests for SQLAlchemy database models.

Tests model instantiation, enums, relationships, indexes, and defaults.
These tests do NOT require a database connection - they test model definitions.

For integration tests with actual database operations, see tests/integration/.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from app.db.models import (
    # Models
    Base,
    Document,
    User,
    ProcessingJob,
    OCRResult,
    OCRResultVersion,
    Tag,
    APIKey,
    AuditLog,
    SystemMetrics,
    SearchAnalytics,
    document_tags,
    # Enums
    ProcessingStatus,
    OCRBackend,
    DocumentType,
    UserTier,
    # Cross-DB Types
    CrossDBJSON,
    CrossDBTSVector,
    CrossDBVector,
)


class TestEnums:
    """Tests for database enums."""

    def test_processing_status_values(self):
        """ProcessingStatus sollte alle erwarteten Werte haben."""
        assert ProcessingStatus.PENDING.value == "pending"
        assert ProcessingStatus.QUEUED.value == "queued"
        assert ProcessingStatus.PROCESSING.value == "processing"
        assert ProcessingStatus.COMPLETED.value == "completed"
        assert ProcessingStatus.FAILED.value == "failed"
        assert ProcessingStatus.CANCELLED.value == "cancelled"

    def test_processing_status_count(self):
        """ProcessingStatus sollte genau 6 Werte haben."""
        assert len(ProcessingStatus) == 6

    def test_ocr_backend_values(self):
        """OCRBackend sollte alle erwarteten Backends haben."""
        assert OCRBackend.AUTO.value == "auto"
        assert OCRBackend.DEEPSEEK.value == "deepseek"
        assert OCRBackend.GOT_OCR.value == "got_ocr"
        assert OCRBackend.SURYA.value == "surya"
        assert OCRBackend.SURYA_GPU.value == "surya_gpu"

    def test_ocr_backend_count(self):
        """OCRBackend sollte genau 5 Backends haben."""
        assert len(OCRBackend) == 5

    def test_document_type_values(self):
        """DocumentType sollte alle Dokumenttypen haben."""
        expected_types = {
            "invoice", "order", "contract", "delivery_note",
            "receipt", "form", "letter", "report", "other", "unknown"
        }
        actual_types = {dt.value for dt in DocumentType}
        assert actual_types == expected_types

    def test_user_tier_values(self):
        """UserTier sollte free, premium und admin haben."""
        assert UserTier.FREE.value == "free"
        assert UserTier.PREMIUM.value == "premium"
        assert UserTier.ADMIN.value == "admin"


class TestDocumentModel:
    """Tests for Document model definition."""

    def test_document_tablename(self):
        """Document sollte 'documents' als Tabellenname haben."""
        assert Document.__tablename__ == "documents"

    def test_document_has_required_columns(self):
        """Document sollte alle erforderlichen Spalten haben."""
        columns = {c.name for c in Document.__table__.columns}
        required = {
            "id", "filename", "original_filename", "file_path", "file_size",
            "mime_type", "checksum", "document_type", "status", "page_count",
            "extracted_text", "ocr_backend_used", "ocr_confidence",
            "processing_duration_ms", "has_umlauts", "german_validation_score",
            "detected_language", "document_metadata", "upload_date",
            "processed_date", "created_at", "updated_at", "owner_id",
            "current_version_number", "total_versions",
            "search_vector", "embedding", "embedding_updated_at", "embedding_model"
        }
        assert required.issubset(columns), f"Fehlende Spalten: {required - columns}"

    def test_document_uuid_primary_key(self):
        """Document ID sollte UUID sein."""
        id_column = Document.__table__.columns["id"]
        assert id_column.primary_key is True

    def test_document_default_status(self):
        """Document sollte 'pending' als Default-Status haben."""
        status_column = Document.__table__.columns["status"]
        assert status_column.default.arg == ProcessingStatus.PENDING

    def test_document_indexes(self):
        """Document sollte Performance-Indizes haben."""
        index_names = {idx.name for idx in Document.__table__.indexes}
        expected_indexes = {
            "ix_documents_status",
            "ix_documents_upload_date",
            "ix_documents_owner_id",
            "ix_documents_checksum",
        }
        assert expected_indexes.issubset(index_names)

    def test_document_relationships(self):
        """Document sollte korrekte Relationships haben."""
        relationships = {r.key for r in Document.__mapper__.relationships}
        assert "owner" in relationships
        assert "tags" in relationships
        assert "processing_jobs" in relationships
        assert "ocr_results" in relationships
        assert "ocr_versions" in relationships


class TestUserModel:
    """Tests for User model definition."""

    def test_user_tablename(self):
        """User sollte 'users' als Tabellenname haben."""
        assert User.__tablename__ == "users"

    def test_user_unique_constraints(self):
        """User sollte unique constraints auf email und username haben."""
        email_col = User.__table__.columns["email"]
        username_col = User.__table__.columns["username"]
        assert email_col.unique is True
        assert username_col.unique is True

    def test_user_default_tier(self):
        """User sollte 'free' als Default-Tier haben."""
        tier_column = User.__table__.columns["tier"]
        assert tier_column.default.arg == UserTier.FREE

    def test_user_default_language(self):
        """User sollte 'de' als Default-Sprache haben."""
        lang_column = User.__table__.columns["preferred_language"]
        assert lang_column.default.arg == "de"

    def test_user_default_quota(self):
        """User sollte 100 als Default-Quote haben."""
        quota_column = User.__table__.columns["daily_quota"]
        assert quota_column.default.arg == 100

    def test_user_has_admin_fields(self):
        """User sollte Admin-Management-Felder haben."""
        columns = {c.name for c in User.__table__.columns}
        admin_fields = {
            "tier", "rate_limit_hourly", "rate_limit_daily",
            "last_activity_at", "password_reset_required",
            "deactivated_at", "deactivated_by_id", "notes"
        }
        assert admin_fields.issubset(columns)


class TestProcessingJobModel:
    """Tests for ProcessingJob model definition."""

    def test_processing_job_tablename(self):
        """ProcessingJob sollte 'processing_jobs' als Tabellenname haben."""
        assert ProcessingJob.__tablename__ == "processing_jobs"

    def test_processing_job_foreign_key(self):
        """ProcessingJob sollte Foreign Key zu Document haben."""
        doc_id_col = ProcessingJob.__table__.columns["document_id"]
        assert any(fk.column.table.name == "documents" for fk in doc_id_col.foreign_keys)

    def test_processing_job_default_priority(self):
        """ProcessingJob sollte 5 als Default-Prioritaet haben."""
        priority_col = ProcessingJob.__table__.columns["priority"]
        assert priority_col.default.arg == 5

    def test_processing_job_default_retries(self):
        """ProcessingJob sollte 3 als Max-Retries haben."""
        max_retries_col = ProcessingJob.__table__.columns["max_retries"]
        assert max_retries_col.default.arg == 3

    def test_processing_job_indexes(self):
        """ProcessingJob sollte Performance-Indizes haben."""
        index_names = {idx.name for idx in ProcessingJob.__table__.indexes}
        assert "ix_processing_jobs_status" in index_names
        assert "ix_processing_jobs_document_id" in index_names


class TestOCRResultModel:
    """Tests for OCRResult model definition."""

    def test_ocr_result_tablename(self):
        """OCRResult sollte 'ocr_results' als Tabellenname haben."""
        assert OCRResult.__tablename__ == "ocr_results"

    def test_ocr_result_has_german_fields(self):
        """OCRResult sollte deutsche Business-Felder haben."""
        columns = {c.name for c in OCRResult.__table__.columns}
        german_fields = {
            "detected_dates", "detected_amounts",
            "detected_ibans", "detected_vat_ids", "business_terms"
        }
        assert german_fields.issubset(columns)

    def test_ocr_result_has_layout_fields(self):
        """OCRResult sollte Layout-Analyse-Felder haben."""
        columns = {c.name for c in OCRResult.__table__.columns}
        assert "detected_layout" in columns
        assert "bounding_boxes" in columns
        assert "page_number" in columns


class TestOCRResultVersionModel:
    """Tests for OCRResultVersion model definition."""

    def test_ocr_version_tablename(self):
        """OCRResultVersion sollte 'ocr_result_versions' als Tabellenname haben."""
        assert OCRResultVersion.__tablename__ == "ocr_result_versions"

    def test_ocr_version_has_rollback_support(self):
        """OCRResultVersion sollte Rollback-Felder haben."""
        columns = {c.name for c in OCRResultVersion.__table__.columns}
        assert "is_rollback" in columns
        assert "rollback_from_version" in columns
        assert "is_current" in columns

    def test_ocr_version_indexes(self):
        """OCRResultVersion sollte optimierte Indizes haben."""
        index_names = {idx.name for idx in OCRResultVersion.__table__.indexes}
        assert "ix_ocr_versions_document_id" in index_names
        assert "ix_ocr_versions_is_current" in index_names


class TestTagModel:
    """Tests for Tag model definition."""

    def test_tag_tablename(self):
        """Tag sollte 'tags' als Tabellenname haben."""
        assert Tag.__tablename__ == "tags"

    def test_tag_unique_name(self):
        """Tag name sollte unique sein."""
        name_col = Tag.__table__.columns["name"]
        assert name_col.unique is True

    def test_tag_has_color(self):
        """Tag sollte Farb-Feld (Hex) haben."""
        columns = {c.name for c in Tag.__table__.columns}
        assert "color" in columns


class TestAPIKeyModel:
    """Tests for APIKey model definition."""

    def test_api_key_tablename(self):
        """APIKey sollte 'api_keys' als Tabellenname haben."""
        assert APIKey.__tablename__ == "api_keys"

    def test_api_key_hash_unique(self):
        """APIKey hash sollte unique sein."""
        hash_col = APIKey.__table__.columns["key_hash"]
        assert hash_col.unique is True

    def test_api_key_default_rate_limit(self):
        """APIKey sollte 1000 req/h als Default haben."""
        rate_col = APIKey.__table__.columns["rate_limit"]
        assert rate_col.default.arg == 1000


class TestAuditLogModel:
    """Tests for AuditLog model definition."""

    def test_audit_log_tablename(self):
        """AuditLog sollte 'audit_logs' als Tabellenname haben."""
        assert AuditLog.__tablename__ == "audit_logs"

    def test_audit_log_has_request_fields(self):
        """AuditLog sollte Request-Tracking-Felder haben."""
        columns = {c.name for c in AuditLog.__table__.columns}
        request_fields = {"ip_address", "user_agent", "request_method", "request_path"}
        assert request_fields.issubset(columns)

    def test_audit_log_indexes(self):
        """AuditLog sollte Indizes fuer schnelle Abfragen haben."""
        index_names = {idx.name for idx in AuditLog.__table__.indexes}
        assert "ix_audit_logs_user_id" in index_names
        assert "ix_audit_logs_created_at" in index_names
        assert "ix_audit_logs_action" in index_names


class TestSystemMetricsModel:
    """Tests for SystemMetrics model definition."""

    def test_system_metrics_tablename(self):
        """SystemMetrics sollte 'system_metrics' als Tabellenname haben."""
        assert SystemMetrics.__tablename__ == "system_metrics"

    def test_system_metrics_required_fields(self):
        """SystemMetrics sollte metric_type und metric_value als required haben."""
        type_col = SystemMetrics.__table__.columns["metric_type"]
        value_col = SystemMetrics.__table__.columns["metric_value"]
        assert type_col.nullable is False
        assert value_col.nullable is False


class TestSearchAnalyticsModel:
    """Tests for SearchAnalytics model definition."""

    def test_search_analytics_tablename(self):
        """SearchAnalytics sollte 'search_analytics' als Tabellenname haben."""
        assert SearchAnalytics.__tablename__ == "search_analytics"

    def test_search_analytics_has_filter_tracking(self):
        """SearchAnalytics sollte Filter-Tracking-Felder haben."""
        columns = {c.name for c in SearchAnalytics.__table__.columns}
        filter_fields = {
            "filters_used", "has_document_type_filter",
            "has_date_filter", "has_tag_filter", "has_status_filter"
        }
        assert filter_fields.issubset(columns)

    def test_search_analytics_has_performance_fields(self):
        """SearchAnalytics sollte Performance-Metriken haben."""
        columns = {c.name for c in SearchAnalytics.__table__.columns}
        perf_fields = {"execution_time_ms", "fts_time_ms", "semantic_time_ms"}
        assert perf_fields.issubset(columns)


class TestDocumentTagsAssociation:
    """Tests for document_tags association table."""

    def test_document_tags_exists(self):
        """document_tags Association Table sollte existieren."""
        assert document_tags is not None
        assert document_tags.name == "document_tags"

    def test_document_tags_has_foreign_keys(self):
        """document_tags sollte Foreign Keys haben."""
        fk_tables = {list(col.foreign_keys)[0].column.table.name
                     for col in document_tags.columns
                     if col.foreign_keys}
        assert "documents" in fk_tables
        assert "tags" in fk_tables

    def test_document_tags_has_indexes(self):
        """document_tags sollte Indizes auf beiden Spalten haben."""
        index_names = {idx.name for idx in document_tags.indexes}
        assert "ix_document_tags_document_id" in index_names
        assert "ix_document_tags_tag_id" in index_names


class TestCrossDBTypes:
    """Tests for cross-database type decorators."""

    def test_cross_db_json_exists(self):
        """CrossDBJSON TypeDecorator sollte existieren."""
        assert CrossDBJSON is not None
        assert CrossDBJSON.cache_ok is True

    def test_cross_db_tsvector_exists(self):
        """CrossDBTSVector TypeDecorator sollte existieren."""
        assert CrossDBTSVector is not None
        assert CrossDBTSVector.cache_ok is True

    def test_cross_db_vector_exists(self):
        """CrossDBVector TypeDecorator sollte existieren."""
        assert CrossDBVector is not None
        assert CrossDBVector.cache_ok is True

    def test_cross_db_vector_dimension(self):
        """CrossDBVector sollte konfigurierbare Dimension haben."""
        vector_type = CrossDBVector(dim=768)
        assert vector_type.dim == 768


class TestBaseModel:
    """Tests for SQLAlchemy Base."""

    def test_base_exists(self):
        """Base sollte existieren."""
        assert Base is not None

    def test_all_models_inherit_base(self):
        """Alle Models sollten von Base erben."""
        models = [Document, User, ProcessingJob, OCRResult, OCRResultVersion,
                  Tag, APIKey, AuditLog, SystemMetrics, SearchAnalytics]
        for model in models:
            assert issubclass(model, Base), f"{model.__name__} erbt nicht von Base"
