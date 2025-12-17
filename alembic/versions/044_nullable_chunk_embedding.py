"""Make RAG chunk embedding nullable

Revision ID: 044_nullable_chunk_embedding
Revises: 043_add_vector_ab_testing
Create Date: 2025-12-16

Die Chunks werden zuerst erstellt, dann asynchron mit Embeddings versehen.
Daher muss die embedding Spalte nullable sein.
"""
from alembic import op
import sqlalchemy as sa


revision = '044_nullable_chunk_embedding'
down_revision = '043_add_vector_ab_testing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('rag_document_chunks', 'embedding',
                    existing_type=sa.LargeBinary(),
                    nullable=True)


def downgrade() -> None:
    # Nur wenn alle Chunks Embeddings haben
    op.alter_column('rag_document_chunks', 'embedding',
                    existing_type=sa.LargeBinary(),
                    nullable=False)
