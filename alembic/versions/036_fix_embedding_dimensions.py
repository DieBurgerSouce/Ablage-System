"""Fix embedding column dimensions from 1536 to 1024.

The multilingual-e5-large model produces 1024-dimensional embeddings,
but the database columns were configured for 1536 dimensions.

This migration updates all embedding columns to use the correct 1024 dimensions.

Revision ID: 036_fix_embedding_dimensions
Revises: 035_add_ocr_training_sample_deleted_at
Create Date: 2025-12-11
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "036_fix_embedding_dimensions"
down_revision = "035_add_ocr_training_sample_deleted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change embedding columns from vector(1536) to vector(1024)."""

    # First, clear existing embeddings since dimensions are incompatible
    # They will be regenerated with the correct dimensions
    op.execute("""
        UPDATE documents
        SET embedding = NULL,
            embedding_updated_at = NULL,
            embedding_model = NULL
        WHERE embedding IS NOT NULL
    """)

    # Alter the documents.embedding column to vector(1024)
    op.execute("""
        ALTER TABLE documents
        ALTER COLUMN embedding TYPE vector(1024)
    """)

    # Check if rag_document_chunks table exists and fix it
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'rag_document_chunks') THEN
                UPDATE rag_document_chunks SET embedding = NULL WHERE embedding IS NOT NULL;
                ALTER TABLE rag_document_chunks ALTER COLUMN embedding TYPE vector(1024);
            END IF;
        END $$;
    """)

    # Check if rag_search_queries table exists and fix it
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'rag_search_queries') THEN
                UPDATE rag_search_queries SET query_embedding = NULL WHERE query_embedding IS NOT NULL;
                ALTER TABLE rag_search_queries ALTER COLUMN query_embedding TYPE vector(1024);
            END IF;
        END $$;
    """)

    # Check if tune_cards table exists and fix it
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tune_cards') THEN
                UPDATE tune_cards SET card_embedding = NULL WHERE card_embedding IS NOT NULL;
                ALTER TABLE tune_cards ALTER COLUMN card_embedding TYPE vector(1024);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert embedding columns back to vector(1536)."""

    # Clear embeddings first
    op.execute("""
        UPDATE documents
        SET embedding = NULL,
            embedding_updated_at = NULL,
            embedding_model = NULL
        WHERE embedding IS NOT NULL
    """)

    # Alter back to vector(1536)
    op.execute("""
        ALTER TABLE documents
        ALTER COLUMN embedding TYPE vector(1536)
    """)

    # Revert rag_document_chunks if exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'rag_document_chunks') THEN
                UPDATE rag_document_chunks SET embedding = NULL WHERE embedding IS NOT NULL;
                ALTER TABLE rag_document_chunks ALTER COLUMN embedding TYPE vector(1536);
            END IF;
        END $$;
    """)

    # Revert rag_search_queries if exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'rag_search_queries') THEN
                UPDATE rag_search_queries SET query_embedding = NULL WHERE query_embedding IS NOT NULL;
                ALTER TABLE rag_search_queries ALTER COLUMN query_embedding TYPE vector(1536);
            END IF;
        END $$;
    """)

    # Revert tune_cards if exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tune_cards') THEN
                UPDATE tune_cards SET card_embedding = NULL WHERE card_embedding IS NOT NULL;
                ALTER TABLE tune_cards ALTER COLUMN card_embedding TYPE vector(1536);
            END IF;
        END $$;
    """)
