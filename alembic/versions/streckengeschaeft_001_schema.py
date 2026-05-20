"""
Streckengeschäft Detection - Database Schema
Alembic Migration for Drop Shipment / Triangular Transaction Detection

Revision ID: streckengeschaeft_001
Create Date: 2024-12-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'streckengeschaeft_001'
down_revision = '058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # ENUM TYPES (with IF NOT EXISTS logic for PostgreSQL)
    # ==========================================================================

    # Transaction type classification
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_type AS ENUM (
                'standard',
                'drop_shipment',
                'triangular_eu',
                'chain_transaction',
                'unknown'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Role of German company in transaction
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE company_role AS ENUM (
                'first_supplier',
                'intermediate',
                'final_buyer',
                'not_applicable'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Moving delivery assignment
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moving_delivery AS ENUM (
                'to_intermediate',
                'from_intermediate',
                'undetermined'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Classification confidence level
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE confidence_level AS ENUM (
                'definitive',
                'high',
                'medium',
                'low',
                'manual_required'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # VAT treatment category
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE vat_category AS ENUM (
                'standard_de',
                'intra_community',
                'reverse_charge',
                'export',
                'triangular_middle',
                'triangular_final'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ==========================================================================
    # CORE TABLES
    # ==========================================================================

    # Define ENUM types using postgresql.ENUM with create_type=False
    transaction_type_enum = postgresql.ENUM(
        'standard', 'drop_shipment', 'triangular_eu', 'chain_transaction', 'unknown',
        name='transaction_type', create_type=False)
    company_role_enum = postgresql.ENUM(
        'first_supplier', 'intermediate', 'final_buyer', 'not_applicable',
        name='company_role', create_type=False)
    moving_delivery_enum = postgresql.ENUM(
        'to_intermediate', 'from_intermediate', 'undetermined',
        name='moving_delivery', create_type=False)
    vat_category_enum = postgresql.ENUM(
        'standard_de', 'intra_community', 'reverse_charge', 'export',
        'triangular_middle', 'triangular_final',
        name='vat_category', create_type=False)
    confidence_level_enum = postgresql.ENUM(
        'definitive', 'high', 'medium', 'low', 'manual_required',
        name='confidence_level', create_type=False)

    # Drop shipment classification at document level
    op.create_table(
        'drop_shipment_classifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Classification results (use existing ENUMs)
        sa.Column('transaction_type', transaction_type_enum, nullable=False, default='unknown'),
        sa.Column('company_role', company_role_enum, nullable=False, default='not_applicable'),
        sa.Column('moving_delivery', moving_delivery_enum, default='undetermined'),
        sa.Column('vat_category', vat_category_enum, nullable=False),

        # Confidence and validation
        sa.Column('confidence_level', confidence_level_enum, nullable=False, default='manual_required'),
        sa.Column('confidence_score', sa.Integer(), nullable=False, default=0),
        sa.Column('is_validated', sa.Boolean(), default=False),
        sa.Column('validated_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        
        # Indicators that triggered classification
        sa.Column('indicators', postgresql.JSONB(), nullable=False, 
                  server_default='[]'),
        sa.Column('conflicts', postgresql.JSONB(), nullable=True),
        
        # EU parties involved (for triangular transactions)
        sa.Column('party_count', sa.Integer(), default=2),
        sa.Column('eu_countries_involved', postgresql.ARRAY(sa.String(2)), 
                  nullable=True),
        
        # DATEV integration
        sa.Column('datev_account_debit', sa.String(10), nullable=True),
        sa.Column('datev_account_credit', sa.String(10), nullable=True),
        sa.Column('datev_tax_code', sa.String(5), nullable=True),
        sa.Column('zm_relevant', sa.Boolean(), default=False),
        sa.Column('zm_marker', sa.String(1), nullable=True),  # '1' for triangular
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), 
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        
        # Constraints
        sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 100',
                          name='valid_confidence_score'),
        sa.CheckConstraint('party_count >= 2 AND party_count <= 10',
                          name='valid_party_count'),
    )
    
    # Position-level classification for mixed invoices (Mischbestellungen)
    op.create_table(
        'drop_shipment_positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('classification_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('drop_shipment_classifications.id', 
                               ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False),
        
        # Position identification
        sa.Column('position_number', sa.Integer(), nullable=False),
        sa.Column('article_number', sa.String(100), nullable=True),
        sa.Column('article_description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=True),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('line_total', sa.Numeric(12, 2), nullable=True),
        
        # Position-level classification
        sa.Column('is_drop_shipment', sa.Boolean(), nullable=False, default=False),
        sa.Column('warehouse_code', sa.String(20), nullable=True),
        sa.Column('erp_position_type', sa.String(10), nullable=True),  # TAS, TAN, etc.
        
        # VAT treatment for this position
        sa.Column('vat_category', vat_category_enum, nullable=True),
        sa.Column('vat_rate', sa.Numeric(5, 2), nullable=True),
        
        # DATEV account for this position
        sa.Column('datev_revenue_account', sa.String(10), nullable=True),
        sa.Column('datev_expense_account', sa.String(10), nullable=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        
        # Unique constraint: one entry per position per document
        sa.UniqueConstraint('document_id', 'position_number', 
                           name='uq_position_per_document'),
    )
    
    # VAT ID registry for party identification
    op.create_table(
        'vat_id_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('vat_id', sa.String(20), nullable=False, unique=True),
        sa.Column('country_code', sa.String(2), nullable=False),
        sa.Column('company_name', sa.String(255), nullable=True),
        
        # Validation status (VIES check)
        sa.Column('is_valid', sa.Boolean(), nullable=True),
        sa.Column('last_validated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_response', postgresql.JSONB(), nullable=True),
        
        # Internal reference (links to business_entities table)
        sa.Column('business_entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('business_entities.id'), nullable=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        
        sa.Index('ix_vat_id_country', 'country_code'),
    )
    
    # Party information extracted from documents
    op.create_table(
        'transaction_parties',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('classification_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('drop_shipment_classifications.id',
                               ondelete='CASCADE'),
                  nullable=False, index=True),
        
        # Party role in the chain
        sa.Column('party_role', sa.String(30), nullable=False),  
        # 'seller', 'buyer', 'ship_to', 'bill_to', 'carrier'
        sa.Column('sequence_number', sa.Integer(), nullable=False),  
        # Position in chain: 1=first, 2=middle, 3=last
        
        # Party identification
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('vat_id', sa.String(20), nullable=True),
        sa.Column('country_code', sa.String(2), nullable=True),
        
        # Address
        sa.Column('street', sa.String(255), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('country', sa.String(100), nullable=True),
        
        # Source of extraction
        sa.Column('source_field', sa.String(50), nullable=True),
        # 'invoice_address', 'delivery_address', 'cmr_consignee', etc.
        
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
    )
    
    # Document evidence chain for proof archive
    op.create_table(
        'proof_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('classification_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('drop_shipment_classifications.id',
                               ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'),
                  nullable=True),
        
        # Proof type
        sa.Column('proof_type', sa.String(50), nullable=False),
        # 'invoice', 'delivery_note', 'cmr', 'gelangensbestaetigung', 
        # 'speditionsauftrag', 'vat_id_proof'
        
        sa.Column('is_present', sa.Boolean(), default=False),
        sa.Column('is_complete', sa.Boolean(), default=False),
        sa.Column('missing_fields', postgresql.ARRAY(sa.String(50)), nullable=True),
        
        # For CMR: Field 24 extraction
        sa.Column('cmr_field_24_signed', sa.Boolean(), nullable=True),
        sa.Column('cmr_field_24_date', sa.Date(), nullable=True),
        
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
    )
    
    # Classification audit log (immutable)
    op.create_table(
        'classification_audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('classification_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('drop_shipment_classifications.id',
                               ondelete='CASCADE'),
                  nullable=False, index=True),
        
        sa.Column('action', sa.String(50), nullable=False),
        # 'created', 'auto_classified', 'manually_validated', 
        # 'overridden', 'exported_datev', 'zm_reported'
        
        sa.Column('previous_value', postgresql.JSONB(), nullable=True),
        sa.Column('new_value', postgresql.JSONB(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        
        sa.Column('performed_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('performed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        
        # System info for audit
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
    )
    
    # ==========================================================================
    # CONFIGURATION TABLES
    # ==========================================================================
    
    # DATEV account mapping configuration
    op.create_table(
        'datev_streckengeschaeft_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        
        sa.Column('kontenrahmen', sa.String(5), nullable=False),  # 'SKR03', 'SKR04'
        sa.Column('company_role', company_role_enum, nullable=False),
        sa.Column('transaction_type', transaction_type_enum, nullable=False),
        
        # Account numbers
        sa.Column('revenue_account', sa.String(10), nullable=True),
        sa.Column('expense_account', sa.String(10), nullable=True),
        sa.Column('tax_code', sa.String(5), nullable=True),
        
        # UStVA mapping
        sa.Column('ustva_kennzahl', sa.String(5), nullable=True),
        sa.Column('zm_kennzeichen', sa.String(1), nullable=True),
        
        sa.Column('description_de', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        
        sa.UniqueConstraint('kontenrahmen', 'company_role', 'transaction_type',
                           name='uq_datev_account_mapping'),
    )
    
    # Classification indicator weights
    op.create_table(
        'classification_indicators',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        
        sa.Column('indicator_code', sa.String(50), nullable=False, unique=True),
        sa.Column('indicator_name_de', sa.String(100), nullable=False),
        sa.Column('indicator_name_en', sa.String(100), nullable=True),
        
        sa.Column('weight', sa.Integer(), nullable=False, default=50),
        sa.Column('is_definitive', sa.Boolean(), default=False),
        sa.Column('applies_to_incoming', sa.Boolean(), default=True),
        sa.Column('applies_to_outgoing', sa.Boolean(), default=True),
        
        sa.Column('detection_pattern', sa.Text(), nullable=True),  # Regex
        sa.Column('detection_field', sa.String(50), nullable=True),
        
        sa.Column('is_active', sa.Boolean(), default=True),
        
        sa.CheckConstraint('weight >= 0 AND weight <= 100', name='valid_weight'),
    )
    
    # ==========================================================================
    # INDEXES FOR PERFORMANCE
    # ==========================================================================
    
    op.create_index('ix_classification_type', 'drop_shipment_classifications',
                    ['transaction_type'])
    op.create_index('ix_classification_confidence', 'drop_shipment_classifications',
                    ['confidence_level', 'is_validated'])
    op.create_index('ix_classification_zm', 'drop_shipment_classifications',
                    ['zm_relevant', 'created_at'])
    op.create_index('ix_positions_drop_ship', 'drop_shipment_positions',
                    ['is_drop_shipment'])
    
    # ==========================================================================
    # SEED DEFAULT DATA
    # ==========================================================================
    
    # Default DATEV account mappings
    op.execute("""
        INSERT INTO datev_streckengeschaeft_accounts 
        (kontenrahmen, company_role, transaction_type, revenue_account, 
         expense_account, tax_code, ustva_kennzahl, zm_kennzeichen, description_de)
        VALUES
        -- SKR03 mappings
        ('SKR03', 'intermediate', 'triangular_eu', '8130', NULL, NULL, '42', '1',
         'Dreiecksgeschäft Zwischenhändler - Erlöse'),
        ('SKR03', 'final_buyer', 'triangular_eu', NULL, '3553', '731', '66', NULL,
         'Dreiecksgeschäft Endabnehmer - Aufwand'),
        ('SKR03', 'first_supplier', 'triangular_eu', '8125', NULL, NULL, '41', NULL,
         'Dreiecksgeschäft Erstlieferer - steuerfreie igl. Lieferung'),
        ('SKR03', 'not_applicable', 'drop_shipment', '8400', '3400', NULL, NULL, NULL,
         'Streckengeschäft Standard'),
        
        -- SKR04 mappings  
        ('SKR04', 'intermediate', 'triangular_eu', '4130', NULL, NULL, '42', '1',
         'Dreiecksgeschäft Zwischenhändler - Erlöse'),
        ('SKR04', 'final_buyer', 'triangular_eu', NULL, '5553', '731', '66', NULL,
         'Dreiecksgeschäft Endabnehmer - Aufwand'),
        ('SKR04', 'first_supplier', 'triangular_eu', '4125', NULL, NULL, '41', NULL,
         'Dreiecksgeschäft Erstlieferer - steuerfreie igl. Lieferung'),
        ('SKR04', 'not_applicable', 'drop_shipment', '4400', '5400', NULL, NULL, NULL,
         'Streckengeschäft Standard');
    """)
    
    # Default classification indicators
    op.execute("""
        INSERT INTO classification_indicators
        (indicator_code, indicator_name_de, weight, is_definitive, 
         detection_pattern, detection_field)
        VALUES
        ('ERP_TAS', 'SAP Positionstyp TAS', 100, true, 'TAS', 'erp_position_type'),
        ('ERP_DROPSHIP', 'ERP Streckengeschäft-Flag', 100, true, 
         'Externes Streckengeschäft|Drop.?Ship', 'procurement_type'),
        ('LEGAL_25B', '§25b UStG Hinweis', 100, true, 
         '§\\s*25\\s*b|Dreiecksgeschäft', 'full_text'),
        ('ADDR_MISMATCH', 'Abweichende Liefer-/Rechnungsadresse', 90, false, 
         NULL, 'address_comparison'),
        ('THREE_EU_VATID', 'Drei EU-USt-IdNrn.', 95, false, 
         NULL, 'vat_id_analysis'),
        ('EMPTY_WAREHOUSE', 'Leeres Lagerort-Feld', 85, false, 
         NULL, 'warehouse_field'),
        ('CMR_THIRD_PARTY', 'CMR mit Drittempfänger', 80, false, 
         NULL, 'cmr_analysis'),
        ('NO_VAT_REVERSE', 'Keine USt + Reverse Charge', 85, false,
         'Reverse.?Charge|Steuerschuldnerschaft', 'vat_analysis');
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('classification_indicators')
    op.drop_table('datev_streckengeschaeft_accounts')
    op.drop_table('classification_audit_log')
    op.drop_table('proof_documents')
    op.drop_table('transaction_parties')
    op.drop_table('vat_id_registry')
    op.drop_table('drop_shipment_positions')
    op.drop_table('drop_shipment_classifications')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS vat_category')
    op.execute('DROP TYPE IF EXISTS confidence_level')
    op.execute('DROP TYPE IF EXISTS moving_delivery')
    op.execute('DROP TYPE IF EXISTS company_role')
    op.execute('DROP TYPE IF EXISTS transaction_type')
