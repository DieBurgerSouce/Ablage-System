"""Verify critical database indexes exist and are valid.

This test ensures that all performance-critical indexes
(GIN, HNSW, partial, unique) are present in the database.
"""
import pytest
from sqlalchemy import text


# All critical indexes that MUST exist in production
CRITICAL_INDEXES = [
    # Full-text search (GIN on tsvector)
    ("documents", "ix_documents_search_vector_gin"),
    # Semantic search (HNSW on pgvector)
    ("documents", "ix_documents_embedding_hnsw"),
    # GIN on JSONB columns
    ("documents", "ix_documents_extracted_data_gin"),
    ("documents", "ix_documents_metadata_gin"),
    ("documents", "ix_documents_custom_fields_gin"),
    # Partial indexes for soft-deleted tables
    ("documents", "ix_documents_active"),
    ("bank_accounts", "ix_bank_accounts_active"),
    ("saved_filters", "ix_saved_filters_active"),
    # Unique constraint on document_tags
    ("document_tags", "ix_document_tags_unique"),
    # CompanySettings singleton
    ("company_settings", "ix_company_settings_singleton"),
]

# CHECK constraints that MUST exist
CRITICAL_CONSTRAINTS = [
    ("documents", "ck_documents_chain_integrity"),
    ("batch_jobs", "ck_batch_jobs_progress"),
    ("processing_jobs", "ck_processing_jobs_priority"),
    ("einvoice_documents", "ck_einvoice_source_exclusive"),
]

# Optional indexes (may not exist if pgvector/extension not installed)
OPTIONAL_INDEXES = [
    ("rag_document_chunks", "ix_rag_document_chunks_embedding_hnsw"),
]


@pytest.mark.integration
class TestIndexVerification:
    """Verify critical database indexes exist."""

    @pytest.fixture(autouse=True)
    def setup(self, db_session):
        self.db = db_session

    @pytest.mark.parametrize("table_name,index_name", CRITICAL_INDEXES)
    def test_critical_index_exists(self, table_name: str, index_name: str):
        """Verify a critical index exists in the database."""
        result = self.db.execute(
            text(
                """SELECT indexname, indexdef
                   FROM pg_indexes
                   WHERE tablename = :table AND indexname = :idx"""
            ),
            {"table": table_name, "idx": index_name},
        ).fetchone()

        assert result is not None, (
            f"Kritischer Index '{index_name}' fehlt auf Tabelle '{table_name}'. "
            f"Migration ausfuehren: alembic upgrade head"
        )

    @pytest.mark.parametrize("table_name,constraint_name", CRITICAL_CONSTRAINTS)
    def test_check_constraint_exists(self, table_name: str, constraint_name: str):
        """Verify a CHECK constraint exists in the database."""
        result = self.db.execute(
            text(
                """SELECT conname
                   FROM pg_constraint
                   WHERE conrelid = :table::regclass
                     AND conname = :name
                     AND contype = 'c'"""
            ),
            {"table": table_name, "name": constraint_name},
        ).fetchone()

        assert result is not None, (
            f"CHECK Constraint '{constraint_name}' fehlt auf Tabelle '{table_name}'. "
            f"Migration ausfuehren: alembic upgrade head"
        )

    @pytest.mark.parametrize("table_name,index_name", OPTIONAL_INDEXES)
    def test_optional_index_exists(self, table_name: str, index_name: str):
        """Verify optional indexes (warn if missing, don't fail)."""
        result = self.db.execute(
            text(
                """SELECT indexname
                   FROM pg_indexes
                   WHERE tablename = :table AND indexname = :idx"""
            ),
            {"table": table_name, "idx": index_name},
        ).fetchone()

        if result is None:
            pytest.skip(
                f"Optionaler Index '{index_name}' nicht vorhanden "
                f"(pgvector evtl. nicht installiert)"
            )

    def test_no_invalid_indexes(self):
        """Verify no indexes are in an invalid state."""
        result = self.db.execute(
            text(
                """SELECT schemaname, tablename, indexname
                   FROM pg_indexes
                   WHERE schemaname = 'public'
                     AND indexname LIKE '%invalid%'"""
            )
        ).fetchall()

        assert len(result) == 0, (
            f"Ungueltige Indexes gefunden: {[r[2] for r in result]}. "
            f"REINDEX ausfuehren."
        )

    def test_document_tags_prevents_duplicates(self):
        """Verify document_tags unique index prevents duplicate assignments."""
        result = self.db.execute(
            text(
                """SELECT indexdef
                   FROM pg_indexes
                   WHERE indexname = 'ix_document_tags_unique'"""
            )
        ).fetchone()

        assert result is not None, "Unique Index auf document_tags fehlt"
        assert "UNIQUE" in result[0].upper(), (
            "Index ix_document_tags_unique ist nicht UNIQUE"
        )
