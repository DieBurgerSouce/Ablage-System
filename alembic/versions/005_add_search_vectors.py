"""Add search vectors for FTS and semantic search

Revision ID: 005
Revises: 004
Create Date: 2025-11-27

Adds full-text search and semantic search capabilities:
- pgvector extension for semantic embeddings
- tsvector column for PostgreSQL full-text search
- HNSW index for efficient vector similarity search
- GIN index for fast full-text search
- Auto-update trigger for tsvector maintenance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== Enable pgvector extension ==========
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ========== Add search columns to documents table ==========

    # Full-text search vector (using existing german_text configuration)
    op.execute("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS search_vector tsvector;
    """)

    # Semantic embedding vector (1024 dimensions for multilingual-e5-large)
    op.execute("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS embedding vector(1024);
    """)

    # Embedding metadata columns
    op.add_column('documents',
        sa.Column('embedding_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents',
        sa.Column('embedding_model', sa.String(100), nullable=True))

    # ========== Create indexes for search performance ==========

    # GIN index for full-text search (very fast for @@ operator)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_search_vector
        ON documents USING GIN(search_vector);
    """)

    # HNSW index for vector similarity search (cosine distance)
    # Parameters: m=16 (max connections), ef_construction=64 (build quality)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_embedding
        ON documents USING hnsw(embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # Compound index for filtering with search (owner + status + has embedding)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_owner_status_embedding
        ON documents(owner_id, status)
        WHERE status = 'completed' AND embedding IS NOT NULL;
    """)

    # ========== Create auto-update function for tsvector ==========
    op.execute("""
        CREATE OR REPLACE FUNCTION documents_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            -- Combine multiple fields with different weights:
            -- A: Highest weight (filename, original_filename)
            -- B: Medium weight (extracted_text)
            -- C: Lower weight (document_type)
            NEW.search_vector :=
                setweight(to_tsvector('german_text', coalesce(NEW.filename, '')), 'A') ||
                setweight(to_tsvector('german_text', coalesce(NEW.original_filename, '')), 'A') ||
                setweight(to_tsvector('german_text', coalesce(NEW.extracted_text, '')), 'B') ||
                setweight(to_tsvector('german_text', coalesce(NEW.document_type, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ========== Create trigger for automatic tsvector updates ==========
    # WICHTIG: Separate op.execute() calls - PostgreSQL erlaubt keine multiple commands in prepared statements
    op.execute("DROP TRIGGER IF EXISTS documents_search_vector_trigger ON documents")
    op.execute("""
        CREATE TRIGGER documents_search_vector_trigger
            BEFORE INSERT OR UPDATE OF filename, original_filename, extracted_text, document_type
            ON documents
            FOR EACH ROW
            EXECUTE FUNCTION documents_search_vector_update()
    """)

    # ========== Populate search_vector for existing documents ==========
    op.execute("""
        UPDATE documents SET
            search_vector =
                setweight(to_tsvector('german_text', coalesce(filename, '')), 'A') ||
                setweight(to_tsvector('german_text', coalesce(original_filename, '')), 'A') ||
                setweight(to_tsvector('german_text', coalesce(extracted_text, '')), 'B') ||
                setweight(to_tsvector('german_text', coalesce(document_type, '')), 'C')
        WHERE search_vector IS NULL;
    """)

    # ========== Create helper function for hybrid search ranking ==========
    op.execute("""
        CREATE OR REPLACE FUNCTION hybrid_search_rank(
            fts_rank FLOAT,
            semantic_similarity FLOAT,
            fts_weight FLOAT DEFAULT 0.3,
            semantic_weight FLOAT DEFAULT 0.7
        ) RETURNS FLOAT AS $$
        BEGIN
            -- Reciprocal Rank Fusion style combination
            -- Normalize both scores to 0-1 range and combine with weights
            RETURN (fts_weight * LEAST(fts_rank, 1.0)) +
                   (semantic_weight * COALESCE(semantic_similarity, 0));
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)


def downgrade() -> None:
    # ========== Drop helper function ==========
    op.execute("DROP FUNCTION IF EXISTS hybrid_search_rank;")

    # ========== Drop trigger and function ==========
    op.execute("DROP TRIGGER IF EXISTS documents_search_vector_trigger ON documents;")
    op.execute("DROP FUNCTION IF EXISTS documents_search_vector_update;")

    # ========== Drop indexes ==========
    op.execute("DROP INDEX IF EXISTS ix_documents_owner_status_embedding;")
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding;")
    op.execute("DROP INDEX IF EXISTS ix_documents_search_vector;")

    # ========== Drop columns ==========
    op.drop_column('documents', 'embedding_model')
    op.drop_column('documents', 'embedding_updated_at')
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS embedding;")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_vector;")

    # Note: We don't drop the pgvector extension as it might be used elsewhere
