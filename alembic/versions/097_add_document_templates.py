"""Add document templates tables

Revision ID: 097_add_document_templates
Revises: 096_add_business_contracts
Create Date: 2026-01-17

Document Template System:
- document_templates: Vorlagen mit Jinja2-Syntax
- generated_documents: Aus Vorlagen erstellte Dokumente
- template_snippets: Wiederverwendbare Textbausteine
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '097_add_document_templates'
down_revision = '096_add_business_contracts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create template category enum
    template_category_enum = postgresql.ENUM(
        'invoice', 'offer', 'contract', 'letter', 'reminder',
        'dunning', 'confirmation', 'report', 'certificate', 'other',
        name='templatecategory',
        create_type=False
    )
    template_category_enum.create(op.get_bind(), checkfirst=True)

    # Create template output format enum
    output_format_enum = postgresql.ENUM(
        'pdf', 'docx', 'html', 'markdown',
        name='templateoutputformat',
        create_type=False
    )
    output_format_enum.create(op.get_bind(), checkfirst=True)

    # Create document_templates table
    op.create_table(
        'document_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),

        # Identification
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),  # e.g., "INV-STANDARD"
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('category', postgresql.ENUM(
            'invoice', 'offer', 'contract', 'letter', 'reminder',
            'dunning', 'confirmation', 'report', 'certificate', 'other',
            name='templatecategory', create_type=False
        ), default='other'),

        # Template content
        sa.Column('content', sa.Text, nullable=False),  # Jinja2 Template
        sa.Column('header_content', sa.Text, nullable=True),
        sa.Column('footer_content', sa.Text, nullable=True),

        # Styling
        sa.Column('css_styles', sa.Text, nullable=True),
        sa.Column('page_size', sa.String(20), default='A4'),
        sa.Column('orientation', sa.String(20), default='portrait'),
        sa.Column('margins', postgresql.JSONB, default={"top": 20, "right": 15, "bottom": 20, "left": 15}),

        # Output format
        sa.Column('output_format', postgresql.ENUM(
            'pdf', 'docx', 'html', 'markdown',
            name='templateoutputformat', create_type=False
        ), default='pdf'),

        # Variables schema
        sa.Column('variables', postgresql.JSONB, default=[]),

        # Versioning
        sa.Column('version', sa.Integer, default=1),
        sa.Column('is_latest', sa.Boolean, default=True),
        sa.Column('parent_template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('document_templates.id'), nullable=True),

        # Status
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_default', sa.Boolean, default=False),

        # Usage statistics
        sa.Column('usage_count', sa.Integer, default=0),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),

        # Metadata
        sa.Column('tags', postgresql.JSONB, default=[]),
        sa.Column('metadata', postgresql.JSONB, default={}),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )

    # Create unique constraint on company + code + version
    op.create_unique_constraint(
        'uq_template_code_version',
        'document_templates',
        ['company_id', 'code', 'version']
    )

    # Create indexes for document_templates
    op.create_index('ix_template_company', 'document_templates', ['company_id'])
    op.create_index('ix_template_category', 'document_templates', ['category'])
    op.create_index('ix_template_code', 'document_templates', ['code'])
    op.create_index('ix_template_is_active', 'document_templates', ['is_active'])
    op.create_index('ix_template_is_default', 'document_templates', ['is_default'])

    # Create generated_documents table
    op.create_table(
        'generated_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('document_templates.id'), nullable=False),

        # Generated file
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=True),
        sa.Column('file_size', sa.Integer, nullable=True),

        # Variable values used
        sa.Column('variable_values', postgresql.JSONB, default={}),

        # Template version at generation time
        sa.Column('template_version', sa.Integer, nullable=False),
        sa.Column('template_snapshot', postgresql.JSONB, nullable=True),

        # References
        sa.Column('linked_entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('linked_document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),

        # Status
        sa.Column('is_finalized', sa.Boolean, default=False),
        sa.Column('is_sent', sa.Boolean, default=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_to', postgresql.JSONB, default=[]),

        # Metadata
        sa.Column('metadata', postgresql.JSONB, default={}),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )

    # Create indexes for generated_documents
    op.create_index('ix_generated_company', 'generated_documents', ['company_id'])
    op.create_index('ix_generated_template', 'generated_documents', ['template_id'])
    op.create_index('ix_generated_entity', 'generated_documents', ['linked_entity_id'])
    op.create_index('ix_generated_document', 'generated_documents', ['linked_document_id'])
    op.create_index('ix_generated_created', 'generated_documents', ['created_at'])

    # Create template_snippets table
    op.create_table(
        'template_snippets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),

        # Identification
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),  # e.g., "AGB-FOOTER"
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('category', sa.String(100), default='general'),

        # Content
        sa.Column('content', sa.Text, nullable=False),

        # Status
        sa.Column('is_active', sa.Boolean, default=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Create unique constraint on company + code
    op.create_unique_constraint(
        'uq_snippet_code',
        'template_snippets',
        ['company_id', 'code']
    )

    # Create indexes for template_snippets
    op.create_index('ix_snippet_company', 'template_snippets', ['company_id'])
    op.create_index('ix_snippet_category', 'template_snippets', ['category'])
    op.create_index('ix_snippet_is_active', 'template_snippets', ['is_active'])

    # Add relationship to Company model (back_populates)
    # This is handled by SQLAlchemy relationship definitions


def downgrade() -> None:
    # Drop tables in reverse order (due to foreign keys)
    op.drop_table('template_snippets')
    op.drop_table('generated_documents')
    op.drop_table('document_templates')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS templateoutputformat')
    op.execute('DROP TYPE IF EXISTS templatecategory')
