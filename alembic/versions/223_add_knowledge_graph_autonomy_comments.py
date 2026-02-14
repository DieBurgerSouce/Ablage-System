"""Add knowledge graph, learning autonomy, and comment enhancement tables.

Phase 2+3 Erweiterungen:
- knowledge_graph_relations: Explizite Beziehungen
- entity_resolutions: Entity-Matching
- knowledge_graph_snapshots: Graph-Metriken
- user_action_autonomy: Lernende Autonomie pro User/Aktion
- autonomy_decision_logs: Entscheidungs-Protokoll
- autonomy_level_history: Level-Aenderungs-Historie
- comment_anchors: PDF-Positionierung
- comment_threads: Thread-Verwaltung
- comment_suggestions: Aenderungsvorschlaege

Revision ID: 223_add_knowledge_graph_autonomy_comments
Revises: 222_add_folder_hierarchy
Create Date: 2026-02-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "223_add_knowledge_graph_autonomy_comments"
down_revision: Union[str, Sequence[str]] = "222_add_folder_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ================================================================
    # Phase 2.1: Knowledge Graph Relations
    # ================================================================
    op.create_table(
        "knowledge_graph_relations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("relation_label", sa.String(255), nullable=True),
        sa.Column("strength", sa.Float, server_default="1.0"),
        sa.Column("confidence", sa.Float, server_default="1.0"),
        sa.Column("is_auto_extracted", sa.Boolean, server_default="false"),
        sa.Column("extraction_source", sa.String(100), nullable=True),
        sa.Column("source_document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("relation_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kg_relations_company_id", "knowledge_graph_relations", ["company_id"])
    op.create_index("ix_kg_relations_source", "knowledge_graph_relations", ["source_id", "source_type"])
    op.create_index("ix_kg_relations_target", "knowledge_graph_relations", ["target_id", "target_type"])
    op.create_index("ix_kg_relations_type", "knowledge_graph_relations", ["relation_type"])
    op.create_index("ix_kg_relations_confidence", "knowledge_graph_relations", ["confidence"])
    op.create_index("ix_kg_relations_deleted_at", "knowledge_graph_relations", ["deleted_at"])
    op.create_index("ix_kg_relations_pair", "knowledge_graph_relations",
                     ["source_id", "target_id", "relation_type"])

    # Entity Resolution
    op.create_table(
        "entity_resolutions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_a_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("business_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_b_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("business_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("similarity_score", sa.Float, nullable=False),
        sa.Column("match_status", sa.String(30), server_default="vorgeschlagen", nullable=False),
        sa.Column("canonical_entity_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_reasons", postgresql.JSONB, server_default="[]"),
        sa.Column("match_method", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_unique_constraint("uq_entity_resolution_pair", "entity_resolutions",
                                 ["entity_a_id", "entity_b_id"])
    op.create_index("ix_entity_resolutions_company_id", "entity_resolutions", ["company_id"])
    op.create_index("ix_entity_resolutions_status", "entity_resolutions", ["match_status"])
    op.create_index("ix_entity_resolutions_score", "entity_resolutions", ["similarity_score"])

    # Graph Snapshots
    op.create_table(
        "knowledge_graph_snapshots",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("total_nodes", sa.Integer, server_default="0"),
        sa.Column("total_edges", sa.Integer, server_default="0"),
        sa.Column("total_entities", sa.Integer, server_default="0"),
        sa.Column("total_documents", sa.Integer, server_default="0"),
        sa.Column("relation_counts", postgresql.JSONB, server_default="{}"),
        sa.Column("community_count", sa.Integer, server_default="0"),
        sa.Column("largest_community_size", sa.Integer, server_default="0"),
        sa.Column("avg_community_size", sa.Float, server_default="0.0"),
        sa.Column("avg_confidence", sa.Float, server_default="0.0"),
        sa.Column("auto_extracted_ratio", sa.Float, server_default="0.0"),
        sa.Column("unresolved_entities", sa.Integer, server_default="0"),
    )
    op.create_index("ix_kg_snapshots_company_id", "knowledge_graph_snapshots", ["company_id"])
    op.create_index("ix_kg_snapshots_snapshot_at", "knowledge_graph_snapshots", ["snapshot_at"])

    # ================================================================
    # Phase 2.2: Learning Autonomy
    # ================================================================
    op.create_table(
        "user_action_autonomy",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("current_level", sa.String(30), server_default="suggest", nullable=False),
        sa.Column("is_manually_set", sa.Boolean, server_default="false"),
        sa.Column("total_suggestions", sa.Integer, server_default="0"),
        sa.Column("total_confirmations", sa.Integer, server_default="0"),
        sa.Column("total_rejections", sa.Integer, server_default="0"),
        sa.Column("total_corrections", sa.Integer, server_default="0"),
        sa.Column("total_auto_executed", sa.Integer, server_default="0"),
        sa.Column("total_undone", sa.Integer, server_default="0"),
        sa.Column("current_streak", sa.Integer, server_default="0"),
        sa.Column("best_streak", sa.Integer, server_default="0"),
        sa.Column("confirmations_for_auto_undo", sa.Integer, server_default="10"),
        sa.Column("confirmations_for_full_auto", sa.Integer, server_default="50"),
        sa.Column("avg_confidence", sa.Float, server_default="0.0"),
        sa.Column("last_confidence", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_user_action_autonomy", "user_action_autonomy",
                                 ["user_id", "action_type", "company_id"])
    op.create_index("ix_user_action_autonomy_user_id", "user_action_autonomy", ["user_id"])
    op.create_index("ix_user_action_autonomy_company_id", "user_action_autonomy", ["company_id"])
    op.create_index("ix_user_action_autonomy_action_type", "user_action_autonomy", ["action_type"])
    op.create_index("ix_user_action_autonomy_level", "user_action_autonomy", ["current_level"])

    op.create_table(
        "autonomy_decision_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("autonomy_level_at_time", sa.String(30), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("context_data", postgresql.JSONB, server_default="{}"),
        sa.Column("suggested_value", sa.Text, nullable=True),
        sa.Column("suggested_confidence", sa.Float, nullable=True),
        sa.Column("user_action", sa.String(30), nullable=False),
        sa.Column("corrected_value", sa.Text, nullable=True),
        sa.Column("suggestion_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_duration_ms", sa.Integer, nullable=True),
    )
    op.create_index("ix_autonomy_decision_user", "autonomy_decision_logs", ["user_id", "action_type"])
    op.create_index("ix_autonomy_decision_company", "autonomy_decision_logs", ["company_id"])
    op.create_index("ix_autonomy_decision_document", "autonomy_decision_logs", ["document_id"])
    op.create_index("ix_autonomy_decision_action", "autonomy_decision_logs", ["user_action"])
    op.create_index("ix_autonomy_decision_time", "autonomy_decision_logs", ["suggestion_at"])

    op.create_table(
        "autonomy_level_history",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_action_autonomy_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("user_action_autonomy.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_level", sa.String(30), nullable=False),
        sa.Column("new_level", sa.String(30), nullable=False),
        sa.Column("change_reason", sa.String(50), nullable=False),
        sa.Column("confirmations_at_change", sa.Integer, server_default="0"),
        sa.Column("streak_at_change", sa.Integer, server_default="0"),
        sa.Column("avg_confidence_at_change", sa.Float, server_default="0.0"),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_autonomy_level_history_uaa", "autonomy_level_history", ["user_action_autonomy_id"])
    op.create_index("ix_autonomy_level_history_time", "autonomy_level_history", ["changed_at"])

    # ================================================================
    # Phase 3.1: Comment Enhancements
    # ================================================================
    op.create_table(
        "comment_anchors",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("comment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("document_comments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("x", sa.Float, nullable=False),
        sa.Column("y", sa.Float, nullable=False),
        sa.Column("width", sa.Float, nullable=True),
        sa.Column("height", sa.Float, nullable=True),
        sa.Column("anchor_type", sa.String(30), server_default="pin", nullable=False),
        sa.Column("highlighted_text", sa.Text, nullable=True),
        sa.Column("text_start_offset", sa.Integer, nullable=True),
        sa.Column("text_end_offset", sa.Integer, nullable=True),
        sa.Column("freeform_path", sa.Text, nullable=True),
        sa.Column("color", sa.String(7), server_default="#FBBF24"),
    )
    op.create_index("ix_comment_anchors_comment_id", "comment_anchors", ["comment_id"])
    op.create_index("ix_comment_anchors_page", "comment_anchors", ["page_number"])

    op.create_table(
        "comment_threads",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), server_default="offen", nullable=False),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("reply_count", sa.Integer, server_default="0"),
        sa.Column("root_comment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("document_comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_comment_threads_document_id", "comment_threads", ["document_id"])
    op.create_index("ix_comment_threads_company_id", "comment_threads", ["company_id"])
    op.create_index("ix_comment_threads_status", "comment_threads", ["status"])

    op.create_table(
        "comment_suggestions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("comment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("document_comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("original_value", sa.Text, nullable=True),
        sa.Column("suggested_value", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), server_default="offen", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_comment_suggestions_comment_id", "comment_suggestions", ["comment_id"])
    op.create_index("ix_comment_suggestions_document_id", "comment_suggestions", ["document_id"])
    op.create_index("ix_comment_suggestions_status", "comment_suggestions", ["status"])


def downgrade() -> None:
    op.drop_table("comment_suggestions")
    op.drop_table("comment_threads")
    op.drop_table("comment_anchors")
    op.drop_table("autonomy_level_history")
    op.drop_table("autonomy_decision_logs")
    op.drop_table("user_action_autonomy")
    op.drop_table("knowledge_graph_snapshots")
    op.drop_table("entity_resolutions")
    op.drop_table("knowledge_graph_relations")
