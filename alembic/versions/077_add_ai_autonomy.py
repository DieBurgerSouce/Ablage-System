"""Add AI autonomy tables.

Revision ID: 077_add_ai_autonomy
Revises: 076_add_email_folder_import
Create Date: 2026-01-03

KI-Autonomie-Infrastruktur:
- ai_decisions: Alle KI-Entscheidungen mit Audit-Trail
- ai_confidence_thresholds: Admin-konfigurierbare Schwellenwerte
- ai_learning_feedback: Self-Learning Feedback
- document_matches: Smart Matching (Rechnung <-> Lieferschein)
- payment_predictions: Zahlungsvorhersagen
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add AI autonomy tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
        uuid_default = sa.text("gen_random_uuid()")
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON
        uuid_default = None

    # =========================================================================
    # 1. AI_CONFIDENCE_THRESHOLDS - Admin-konfigurierbare Schwellenwerte
    # =========================================================================
    op.create_table(
        "ai_confidence_thresholds",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=True),  # Optional: Pro-Mandant

        # Decision Type (unique per company)
        sa.Column("decision_type", sa.String(50), nullable=False),
        # Types: categorization, accounting, matching, anomaly, prediction, duplicate

        # Schwellenwerte (0.0 - 1.0)
        sa.Column("auto_threshold", sa.Float, server_default="0.95"),  # Ab hier automatisch
        sa.Column("suggest_threshold", sa.Float, server_default="0.80"),  # Ab hier vorschlagen
        # Unter suggest_threshold = manuelle Review

        # Feature-Toggle
        sa.Column("is_enabled", sa.Boolean, server_default=sa.text("true")),
        sa.Column("allow_auto_apply", sa.Boolean, server_default=sa.text("true")),

        # Beschreibung fuer Admin-UI
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),

        # Audit
        sa.Column("updated_by_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("company_id", "decision_type", name="uq_ai_threshold_company_type"),
    )

    op.create_index("ix_ai_thresholds_decision_type", "ai_confidence_thresholds", ["decision_type"])

    # =========================================================================
    # 2. AI_DECISIONS - Alle KI-Entscheidungen mit Audit-Trail
    # =========================================================================
    op.create_table(
        "ai_decisions",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=True),
        sa.Column("document_id", uuid_type, nullable=True),  # Optional: Bei manchen Entscheidungen ohne Dokument

        # Decision Type
        sa.Column("decision_type", sa.String(50), nullable=False),
        # Types: categorization, accounting, matching, anomaly, prediction, duplicate

        # Entscheidungs-Details
        sa.Column("decision_value", json_type, nullable=False),  # Strukturiertes Ergebnis
        # Beispiel categorization: {"category": "invoice_incoming", "subcategory": "supplier_invoice"}
        # Beispiel accounting: {"debit_account": "4000", "credit_account": "1600", "tax_code": "VSt19"}
        # Beispiel matching: {"matched_document_id": "...", "match_type": "invoice_delivery"}

        # Confidence
        sa.Column("confidence", sa.Float, nullable=False),  # 0.0 - 1.0
        sa.Column("calibrated_confidence", sa.Float, nullable=True),  # Nach Kalibrierung
        sa.Column("confidence_level", sa.String(20), nullable=False),  # auto, suggest, manual

        # Explainable AI
        sa.Column("explanation", json_type, nullable=True),
        # Beispiel: {"reasons": ["Keyword 'Rechnung' gefunden", "Lieferant bekannt"], "features": {...}}
        sa.Column("features_used", json_type, nullable=True),  # Welche Features verwendet
        sa.Column("model_version", sa.String(50), nullable=True),  # Modell-Version fuer Reproduzierbarkeit

        # Autonomie-Status
        sa.Column("auto_applied", sa.Boolean, server_default=sa.text("false")),  # Automatisch angewendet?
        sa.Column("requires_review", sa.Boolean, server_default=sa.text("true")),  # Muss geprueft werden?
        sa.Column("is_final", sa.Boolean, server_default=sa.text("false")),  # Wurde final entschieden?

        # Review-Informationen
        sa.Column("reviewed_by_id", uuid_type, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_action", sa.String(20), nullable=True),  # approved, rejected, modified
        sa.Column("review_comment", sa.Text, nullable=True),

        # Bei Modifikation: Was wurde geaendert?
        sa.Column("modified_value", json_type, nullable=True),

        # Timing
        sa.Column("processing_time_ms", sa.Integer, nullable=True),

        # Audit/Compliance
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Indizes fuer haeufige Abfragen
    op.create_index("ix_ai_decisions_document_id", "ai_decisions", ["document_id"])
    op.create_index("ix_ai_decisions_decision_type", "ai_decisions", ["decision_type"])
    op.create_index("ix_ai_decisions_requires_review", "ai_decisions", ["requires_review"])
    op.create_index("ix_ai_decisions_confidence_level", "ai_decisions", ["confidence_level"])
    op.create_index("ix_ai_decisions_created_at", "ai_decisions", ["created_at"])
    op.create_index(
        "ix_ai_decisions_pending_review",
        "ai_decisions",
        ["decision_type", "requires_review", "is_final"],
        postgresql_where=sa.text("requires_review = true AND is_final = false") if is_postgres else None,
    )

    # =========================================================================
    # 3. AI_LEARNING_FEEDBACK - Self-Learning Feedback
    # =========================================================================
    op.create_table(
        "ai_learning_feedback",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("ai_decision_id", uuid_type, nullable=False),
        sa.Column("company_id", uuid_type, nullable=True),

        # Feedback-Typ
        sa.Column("feedback_type", sa.String(20), nullable=False),
        # Types: approved, corrected, rejected

        # Original vs. Korrigiert
        sa.Column("original_value", json_type, nullable=False),
        sa.Column("corrected_value", json_type, nullable=True),  # Nur bei 'corrected'

        # Korrektur-Details
        sa.Column("correction_reason", sa.Text, nullable=True),
        sa.Column("correction_category", sa.String(50), nullable=True),  # z.B. "wrong_category", "missing_info"

        # Wer hat korrigiert
        sa.Column("corrector_id", uuid_type, nullable=False),

        # Learning-Status
        sa.Column("processed_for_learning", sa.Boolean, server_default=sa.text("false")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("learning_batch_id", sa.String(50), nullable=True),

        # Gewichtung fuer Learning
        sa.Column("learning_weight", sa.Float, server_default="1.0"),  # Hoeher = wichtiger

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["ai_decision_id"], ["ai_decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["corrector_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_ai_feedback_decision_id", "ai_learning_feedback", ["ai_decision_id"])
    op.create_index("ix_ai_feedback_processed", "ai_learning_feedback", ["processed_for_learning"])
    op.create_index("ix_ai_feedback_type", "ai_learning_feedback", ["feedback_type"])

    # =========================================================================
    # 4. DOCUMENT_MATCHES - Smart Matching
    # =========================================================================
    op.create_table(
        "document_matches",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=True),

        # Quell- und Ziel-Dokument
        sa.Column("source_document_id", uuid_type, nullable=False),
        sa.Column("target_document_id", uuid_type, nullable=False),

        # Match-Typ
        sa.Column("match_type", sa.String(50), nullable=False),
        # Types: invoice_delivery, invoice_order, delivery_order, invoice_contract, etc.

        # Match-Qualitaet
        sa.Column("match_confidence", sa.Float, nullable=False),
        sa.Column("match_score", sa.Float, nullable=True),  # Detaillierter Score
        sa.Column("match_features", json_type, nullable=True),
        # Beispiel: {"order_number": 0.95, "customer": 0.90, "amount": 0.85, "date": 0.70}

        # Verknuepfungs-Status
        sa.Column("auto_linked", sa.Boolean, server_default=sa.text("false")),
        sa.Column("is_confirmed", sa.Boolean, server_default=sa.text("false")),
        sa.Column("is_rejected", sa.Boolean, server_default=sa.text("false")),

        # Wer hat verknuepft/bestaetigt
        sa.Column("linked_by_id", uuid_type, nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_id", uuid_type, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),

        # Referenz zur AI-Entscheidung
        sa.Column("ai_decision_id", uuid_type, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_decision_id"], ["ai_decisions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_document_id", "target_document_id", name="uq_document_match_pair"),
    )

    op.create_index("ix_document_matches_source", "document_matches", ["source_document_id"])
    op.create_index("ix_document_matches_target", "document_matches", ["target_document_id"])
    op.create_index("ix_document_matches_type", "document_matches", ["match_type"])
    op.create_index("ix_document_matches_confirmed", "document_matches", ["is_confirmed"])

    # =========================================================================
    # 5. PAYMENT_PREDICTIONS - Zahlungsvorhersagen
    # =========================================================================
    op.create_table(
        "payment_predictions",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=True),
        sa.Column("document_id", uuid_type, nullable=False),  # Rechnung
        sa.Column("business_entity_id", uuid_type, nullable=True),  # Kunde/Lieferant

        # Vorhersage
        sa.Column("predicted_payment_date", sa.Date, nullable=False),
        sa.Column("predicted_days", sa.Integer, nullable=False),  # Tage ab Rechnungsdatum
        sa.Column("confidence", sa.Float, nullable=False),

        # Vorhersage-Details
        sa.Column("prediction_features", json_type, nullable=True),
        # Beispiel: {"historical_avg_days": 25, "invoice_amount": 5000, "payment_terms": "net30"}

        # Modell-Info
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("prediction_date", sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Tatsaechliche Zahlung (fuer Learning)
        sa.Column("actual_payment_date", sa.Date, nullable=True),
        sa.Column("actual_days", sa.Integer, nullable=True),
        sa.Column("prediction_error_days", sa.Integer, nullable=True),  # Differenz

        # Status
        sa.Column("is_paid", sa.Boolean, server_default=sa.text("false")),
        sa.Column("is_overdue", sa.Boolean, server_default=sa.text("false")),

        # Referenz zur AI-Entscheidung
        sa.Column("ai_decision_id", uuid_type, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_decision_id"], ["ai_decisions.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_payment_predictions_document", "payment_predictions", ["document_id"])
    op.create_index("ix_payment_predictions_entity", "payment_predictions", ["business_entity_id"])
    op.create_index("ix_payment_predictions_date", "payment_predictions", ["predicted_payment_date"])
    op.create_index("ix_payment_predictions_is_paid", "payment_predictions", ["is_paid"])

    # =========================================================================
    # 6. DEFAULT THRESHOLDS - Standard-Schwellenwerte einfuegen
    # =========================================================================
    if is_postgres:
        op.execute("""
            INSERT INTO ai_confidence_thresholds (id, decision_type, auto_threshold, suggest_threshold, display_name, description, is_enabled, allow_auto_apply)
            VALUES
                (gen_random_uuid(), 'categorization', 0.95, 0.80, 'Auto-Kategorisierung', 'Dokument-Typ automatisch erkennen (Rechnung, Vertrag, etc.)', true, true),
                (gen_random_uuid(), 'accounting', 0.90, 0.75, 'Auto-Kontierung', 'Buchungskonten automatisch vorschlagen', true, false),
                (gen_random_uuid(), 'matching', 0.95, 0.85, 'Smart Matching', 'Zusammengehoerige Dokumente automatisch verbinden', true, true),
                (gen_random_uuid(), 'anomaly', 0.85, 0.70, 'Anomalie-Erkennung', 'Ungewoehnliche Betraege oder Muster erkennen', true, false),
                (gen_random_uuid(), 'prediction', 0.80, 0.60, 'Zahlungs-Vorhersage', 'Erwartetes Zahlungsdatum prognostizieren', true, false),
                (gen_random_uuid(), 'duplicate', 0.90, 0.75, 'Duplikat-Erkennung', 'Aehnliche oder doppelte Dokumente finden', true, true)
            ON CONFLICT DO NOTHING;
        """)


def downgrade() -> None:
    """Remove AI autonomy tables."""
    op.drop_table("payment_predictions")
    op.drop_table("document_matches")
    op.drop_table("ai_learning_feedback")
    op.drop_table("ai_decisions")
    op.drop_table("ai_confidence_thresholds")
