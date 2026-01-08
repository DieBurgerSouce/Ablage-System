"""Add validation queue system.

Revision ID: 064_add_validation_queue_system
Revises: 063_fix_privat_metadata_column
Create Date: 2024-12-30

Enterprise-Grade Validierungssystem mit:
- ValidationQueueItem: Warteschlangen-Eintraege
- ValidationFieldReview: Feld-Reviews pro Item
- ValidationRule: Regelbasierte Stichproben
- ValidationSampleConfig: Prozent-basierte Konfiguration
- validation_analytics: Aggregierte Statistiken
- Neue Permissions: validation:write, validation:manage
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =============================================================================
    # ENUM TYPES
    # =============================================================================

    # ValidationStatus Enum
    validation_status_enum = postgresql.ENUM(
        'pending', 'in_progress', 'approved', 'rejected', 'skipped',
        name='validation_status',
        create_type=False
    )
    validation_status_enum.create(op.get_bind(), checkfirst=True)

    # SampleSource Enum
    sample_source_enum = postgresql.ENUM(
        'automatic', 'rule_based', 'manual', 'low_confidence',
        name='sample_source',
        create_type=False
    )
    sample_source_enum.create(op.get_bind(), checkfirst=True)

    # ValidationRuleType Enum
    rule_type_enum = postgresql.ENUM(
        'confidence_threshold', 'field_pattern', 'document_type',
        'first_occurrence', 'error_pattern',
        name='validation_rule_type',
        create_type=False
    )
    rule_type_enum.create(op.get_bind(), checkfirst=True)

    # =============================================================================
    # VALIDATION SAMPLE CONFIG (%-basierte Stichproben)
    # =============================================================================
    op.create_table(
        'validation_sample_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Konfiguration
        sa.Column('name', sa.String(100), nullable=False, server_default='Standard'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('sample_percentage', sa.Integer, nullable=False, server_default='10'),
        sa.Column('stratify_by_document_type', sa.Boolean, server_default='true'),
        sa.Column('stratify_by_ocr_backend', sa.Boolean, server_default='false'),
        sa.Column('min_confidence_threshold', sa.Float, server_default='0.85',
                  comment='Dokumente unter diesem Wert werden immer validiert'),

        # Zeitraum
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),

        # Statistik
        sa.Column('documents_sampled', sa.Integer, server_default='0'),
        sa.Column('last_sample_at', sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Constraints
        sa.CheckConstraint('sample_percentage >= 0 AND sample_percentage <= 100',
                          name='ck_sample_percentage_range'),
        sa.CheckConstraint('min_confidence_threshold >= 0 AND min_confidence_threshold <= 1',
                          name='ck_confidence_threshold_range'),
    )

    # =============================================================================
    # VALIDATION RULES (Regelbasierte Stichproben)
    # =============================================================================
    op.create_table(
        'validation_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Regel-Identifikation
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),

        # Regel-Definition
        sa.Column('rule_type', sa.String(50), nullable=False),
        sa.Column('conditions', postgresql.JSONB, nullable=False, server_default='{}',
                  comment='z.B. {"confidence_below": 0.85, "fields": ["iban"]}'),

        # Prioritaet und Status
        sa.Column('priority', sa.Integer, nullable=False, server_default='5',
                  comment='1 = hoechste Prioritaet, wird an Queue-Items vererbt'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('is_system', sa.Boolean, server_default='false',
                  comment='System-Regeln koennen nicht geloescht werden'),

        # Statistik
        sa.Column('documents_matched', sa.Integer, server_default='0'),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    op.create_index('ix_validation_rules_active', 'validation_rules', ['is_active'])
    op.create_index('ix_validation_rules_type', 'validation_rules', ['rule_type'])
    op.create_index('ix_validation_rules_priority', 'validation_rules', ['priority'])

    # =============================================================================
    # VALIDATION QUEUE ITEMS (Haupttabelle)
    # =============================================================================
    op.create_table(
        'validation_queue_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Dokument-Referenz
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),

        # Status und Zuweisung
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer, nullable=False, server_default='5',
                  comment='1 = hoechste Prioritaet'),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),

        # Stichproben-Quelle
        sa.Column('sample_source', sa.String(50), nullable=False, server_default='automatic'),
        sa.Column('sample_rule_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('validation_rules.id', ondelete='SET NULL'), nullable=True),

        # Confidence Metriken (kopiert bei Erstellung fuer historische Analyse)
        sa.Column('overall_confidence', sa.Float, nullable=True),
        sa.Column('min_field_confidence', sa.Float, nullable=True),
        sa.Column('fields_below_threshold', sa.Integer, server_default='0',
                  comment='Anzahl Felder mit Confidence unter Schwellenwert'),
        sa.Column('total_fields', sa.Integer, server_default='0'),

        # Dokumenttyp (kopiert fuer Filterung ohne Join)
        sa.Column('document_type', sa.String(50), nullable=True),
        sa.Column('document_name', sa.String(255), nullable=True),

        # Validierungsergebnis
        sa.Column('validation_notes', sa.Text, nullable=True,
                  comment='Notizen vom Validator'),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('rejection_category', sa.String(50), nullable=True,
                  comment='z.B. ocr_error, missing_data, wrong_format'),
        sa.Column('validated_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),

        # Zeit-Tracking fuer Analytics
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Wann wurde mit der Validierung begonnen'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_duration_seconds', sa.Integer, nullable=True),

        # Korrekturen-Zaehler
        sa.Column('corrections_made', sa.Integer, server_default='0'),
        sa.Column('umlaut_corrections', sa.Integer, server_default='0'),
        sa.Column('format_corrections', sa.Integer, server_default='0'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Unique Constraint: Ein Dokument kann nur einmal in der Queue sein
        sa.UniqueConstraint('document_id', 'status', name='uq_document_queue_status',
                           comment='Verhindert doppelte Eintraege fuer pending/in_progress'),
    )

    # Indexes fuer haeufige Queries
    op.create_index('ix_vqi_status', 'validation_queue_items', ['status'])
    op.create_index('ix_vqi_priority', 'validation_queue_items', ['priority'])
    op.create_index('ix_vqi_assigned_to', 'validation_queue_items', ['assigned_to_id'])
    op.create_index('ix_vqi_document', 'validation_queue_items', ['document_id'])
    op.create_index('ix_vqi_confidence', 'validation_queue_items', ['overall_confidence'])
    op.create_index('ix_vqi_sample_source', 'validation_queue_items', ['sample_source'])
    op.create_index('ix_vqi_created_at', 'validation_queue_items', ['created_at'])
    op.create_index('ix_vqi_document_type', 'validation_queue_items', ['document_type'])

    # Compound Indexes fuer Dashboard-Queries
    op.create_index('ix_vqi_status_priority', 'validation_queue_items',
                    ['status', 'priority', 'created_at'])
    op.create_index('ix_vqi_assigned_status', 'validation_queue_items',
                    ['assigned_to_id', 'status'])
    op.create_index('ix_vqi_validated_date', 'validation_queue_items',
                    ['validated_at', 'validated_by_id'])

    # =============================================================================
    # VALIDATION FIELD REVIEWS (Feld-Details)
    # =============================================================================
    op.create_table(
        'validation_field_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Queue-Item Referenz
        sa.Column('queue_item_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('validation_queue_items.id', ondelete='CASCADE'), nullable=False),

        # Feld-Identifikation
        sa.Column('field_key', sa.String(100), nullable=False,
                  comment='z.B. invoice_number, iban, total_amount'),
        sa.Column('field_label', sa.String(255), nullable=False,
                  comment='Deutscher Anzeigename'),
        sa.Column('field_type', sa.String(50), nullable=True,
                  comment='z.B. text, number, date, currency, iban'),

        # Werte
        sa.Column('original_value', sa.Text, nullable=True),
        sa.Column('corrected_value', sa.Text, nullable=True),
        sa.Column('was_corrected', sa.Boolean, server_default='false'),

        # Confidence
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('confidence_threshold', sa.Float, server_default='0.85'),
        sa.Column('is_below_threshold', sa.Boolean, server_default='false'),

        # Validierung
        sa.Column('validation_status', sa.String(50), server_default='pending',
                  comment='pending, validated, error, skipped'),
        sa.Column('validation_errors', postgresql.JSONB, server_default='[]',
                  comment='Liste von Validierungsfehlern'),
        sa.Column('umlaut_issues', postgresql.JSONB, server_default='[]',
                  comment='Umlaut-spezifische Probleme'),
        sa.Column('format_issues', postgresql.JSONB, server_default='[]',
                  comment='Format-spezifische Probleme'),

        # OCR-Metadaten fuer PDF-Highlighting
        sa.Column('bounding_box', postgresql.JSONB, nullable=True,
                  comment='{"x": 0, "y": 0, "width": 100, "height": 20, "page": 1}'),
        sa.Column('ocr_backend', sa.String(50), nullable=True),

        # Audit
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_vfr_queue_item', 'validation_field_reviews', ['queue_item_id'])
    op.create_index('ix_vfr_field_key', 'validation_field_reviews', ['field_key'])
    op.create_index('ix_vfr_below_threshold', 'validation_field_reviews', ['is_below_threshold'])
    op.create_index('ix_vfr_was_corrected', 'validation_field_reviews', ['was_corrected'])

    # Unique: Ein Feld pro Queue-Item
    op.create_unique_constraint('uq_field_per_queue_item', 'validation_field_reviews',
                                ['queue_item_id', 'field_key'])

    # =============================================================================
    # VALIDATION ANALYTICS (Aggregierte Statistiken)
    # =============================================================================
    op.create_table(
        'validation_analytics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Zeitraum
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('hour', sa.Integer, nullable=True,
                  comment='Stunde (0-23) fuer stuendliche Granularitaet, NULL fuer taeglich'),

        # Editor (NULL = Gesamtstatistik)
        sa.Column('editor_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),

        # Dokumenttyp (NULL = Alle Typen)
        sa.Column('document_type', sa.String(50), nullable=True),

        # Metriken: Anzahl
        sa.Column('items_validated', sa.Integer, server_default='0'),
        sa.Column('items_approved', sa.Integer, server_default='0'),
        sa.Column('items_rejected', sa.Integer, server_default='0'),
        sa.Column('items_skipped', sa.Integer, server_default='0'),

        # Metriken: Zeit
        sa.Column('avg_validation_time_seconds', sa.Integer, nullable=True),
        sa.Column('min_validation_time_seconds', sa.Integer, nullable=True),
        sa.Column('max_validation_time_seconds', sa.Integer, nullable=True),
        sa.Column('total_validation_time_seconds', sa.Integer, server_default='0'),

        # Metriken: Korrekturen
        sa.Column('corrections_made', sa.Integer, server_default='0'),
        sa.Column('umlaut_corrections', sa.Integer, server_default='0'),
        sa.Column('format_corrections', sa.Integer, server_default='0'),
        sa.Column('fields_reviewed', sa.Integer, server_default='0'),

        # Metriken: Confidence
        sa.Column('avg_confidence_before', sa.Float, nullable=True),
        sa.Column('avg_confidence_after', sa.Float, nullable=True),
        sa.Column('confidence_improvement', sa.Float, nullable=True,
                  comment='avg_after - avg_before'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Unique Constraint fuer Aggregation
    op.create_unique_constraint('uq_analytics_period', 'validation_analytics',
                                ['date', 'hour', 'editor_id', 'document_type'])

    op.create_index('ix_va_date', 'validation_analytics', ['date'])
    op.create_index('ix_va_editor', 'validation_analytics', ['editor_id'])
    op.create_index('ix_va_document_type', 'validation_analytics', ['document_type'])
    op.create_index('ix_va_date_editor', 'validation_analytics', ['date', 'editor_id'])

    # =============================================================================
    # PERMISSIONS hinzufuegen
    # NOTE: permissions Tabelle hat kein updated_at - nur created_at
    # =============================================================================
    op.execute("""
        INSERT INTO permissions (id, name, description, resource_type, action, is_system, created_at)
        VALUES
            (gen_random_uuid(), 'validation:write', 'Dokumente validieren und bearbeiten', 'validation', 'write', true, NOW()),
            (gen_random_uuid(), 'validation:manage', 'Validierungsregeln und -konfiguration verwalten', 'validation', 'manage', true, NOW()),
            (gen_random_uuid(), 'validation:read', 'Validierungsstatus und Statistiken einsehen', 'validation', 'read', true, NOW())
        ON CONFLICT (name) DO NOTHING;
    """)

    # Editor-Rolle um validation:write erweitern (falls Editor-Rolle existiert)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'editor'
          AND p.name IN ('validation:write', 'validation:read')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          );
    """)

    # Admin-Rolle um alle validation Permissions erweitern
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'admin'
          AND p.name IN ('validation:write', 'validation:manage', 'validation:read')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          );
    """)

    # =============================================================================
    # STANDARD-REGELN erstellen
    # =============================================================================
    op.execute("""
        INSERT INTO validation_rules (id, name, description, rule_type, conditions, priority, is_active, is_system)
        VALUES
            (
                gen_random_uuid(),
                'Niedrige Konfidenz',
                'Dokumente mit Overall-Confidence unter 85% automatisch zur Validierung',
                'confidence_threshold',
                '{"confidence_below": 0.85}'::jsonb,
                2,
                true,
                true
            ),
            (
                gen_random_uuid(),
                'Fehlende IBAN bei Rechnungen',
                'Rechnungen ohne erkannte IBAN zur manuellen Pruefung',
                'field_pattern',
                '{"document_type": "invoice", "field": "iban", "pattern": "empty_or_invalid"}'::jsonb,
                3,
                true,
                true
            ),
            (
                gen_random_uuid(),
                'Kritisch niedrige Feldkonfidenz',
                'Dokumente mit mindestens einem Feld unter 50% Konfidenz',
                'confidence_threshold',
                '{"min_field_confidence_below": 0.50}'::jsonb,
                1,
                true,
                true
            ),
            (
                gen_random_uuid(),
                'Umlaut-Fehler erkannt',
                'Dokumente bei denen Umlaut-Probleme erkannt wurden',
                'error_pattern',
                '{"error_type": "umlaut_error"}'::jsonb,
                2,
                true,
                true
            )
        ON CONFLICT (name) DO NOTHING;
    """)

    # =============================================================================
    # STANDARD-KONFIGURATION erstellen
    # =============================================================================
    op.execute("""
        INSERT INTO validation_sample_configs (id, name, description, sample_percentage,
                                               stratify_by_document_type, min_confidence_threshold, is_active)
        VALUES (
            gen_random_uuid(),
            'Standard',
            'Standard-Stichprobenkonfiguration: 10% aller Dokumente',
            10,
            true,
            0.85,
            true
        )
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Tabellen loeschen (in umgekehrter Reihenfolge)
    op.drop_table('validation_analytics')
    op.drop_table('validation_field_reviews')
    op.drop_table('validation_queue_items')
    op.drop_table('validation_rules')
    op.drop_table('validation_sample_configs')

    # Permissions entfernen
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE name LIKE 'validation:%'
        );
    """)
    op.execute("DELETE FROM permissions WHERE name LIKE 'validation:%';")

    # ENUMs entfernen
    op.execute("DROP TYPE IF EXISTS validation_status CASCADE;")
    op.execute("DROP TYPE IF EXISTS sample_source CASCADE;")
    op.execute("DROP TYPE IF EXISTS validation_rule_type CASCADE;")
