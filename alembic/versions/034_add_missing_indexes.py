"""Add missing indexes for extracted_data and RAG performance.

Adds the following indexes for better query performance:

1. extracted_data JSON Indexes:
   - Invoice number for duplicate detection
   - Sender company for customer search
   - Gross amount for filtering

2. RAG Chunks Indexes:
   - HNSW Index for faster semantic search (alternative to IVFFlat)
   - Section + Document composite index for filtered searches

Revision ID: 034_add_missing_indexes
Revises: 033_add_rag_tables
Create Date: 2025-12-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "034_add_missing_indexes"
down_revision = "033_add_rag_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for extracted_data and RAG."""

    # 1. GIN Index for invoice number in extracted_data
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_extracted_invoice_number
        ON documents USING GIN ((extracted_data->'invoice'->'invoice_number'))
        WHERE extracted_data->'invoice'->'invoice_number' IS NOT NULL;
    """)

    # 2. GIN Index for sender company in extracted_data
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_extracted_sender_company
        ON documents USING GIN ((extracted_data->'invoice'->'sender'->'company'))
        WHERE extracted_data->'invoice'->'sender'->'company' IS NOT NULL;
    """)

    # 3. Functional index for gross_amount (for range queries)
    # Using BTREE on extracted numeric value
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_extracted_gross_amount
        ON documents (
            (CAST(extracted_data->'invoice'->>'gross_amount' AS NUMERIC))
        )
        WHERE extracted_data->'invoice'->>'gross_amount' IS NOT NULL;
    """)

    # 4. RAG Section + Document composite index for filtered searches
    # Only create if rag_document_chunks table exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'rag_document_chunks') THEN
                CREATE INDEX IF NOT EXISTS ix_rag_chunks_section_document
                ON rag_document_chunks (section_type, document_id);
            END IF;
        END $$;
    """)

    # 5. HNSW Index for RAG chunks (faster than IVFFlat for <100k vectors)
    # Note: Requires pgvector extension with HNSW support
    # This is optional - falls back gracefully if not available
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'rag_document_chunks')
               AND EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                -- Check if hnsw operator class exists (pgvector >= 0.5.0)
                IF EXISTS (SELECT 1 FROM pg_opclass WHERE opcname = 'vector_cosine_ops') THEN
                    -- Try HNSW first (pgvector >= 0.5.0)
                    BEGIN
                        CREATE INDEX IF NOT EXISTS ix_rag_chunks_embedding_hnsw
                        ON rag_document_chunks USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64);
                    EXCEPTION WHEN undefined_object THEN
                        -- HNSW not available, skip (IVFFlat index should exist from 033)
                        RAISE NOTICE 'HNSW index not available, using existing IVFFlat index';
                    END;
                END IF;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove performance indexes."""

    # Drop extracted_data indexes
    op.execute("DROP INDEX IF EXISTS ix_documents_extracted_invoice_number;")
    op.execute("DROP INDEX IF EXISTS ix_documents_extracted_sender_company;")
    op.execute("DROP INDEX IF EXISTS ix_documents_extracted_gross_amount;")

    # Drop RAG indexes
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_section_document;")
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_embedding_hnsw;")
