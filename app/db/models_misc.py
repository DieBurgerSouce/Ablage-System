"""Diverse System-Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime, date
from enum import Enum
from typing import Dict, Any
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, Float, ForeignKey, Index, Date, Numeric, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON, CrossDBVector


# =============================================================================
# COMPANY SETTINGS
# =============================================================================

class CompanySettings(Base):
    """
    Singleton-Tabelle für Firmendetails.

    Wird verwendet um zu bestimmen, ob eine hochgeladene Rechnung
    eine Eingangsrechnung (an uns) oder Ausgangsrechnung (von uns) ist.

    Diese Tabelle sollte nur einen einzigen Datensatz haben.
    """
    __tablename__ = "company_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firmenidentifikation
    company_name = Column(String(255), nullable=False, comment="Offizieller Firmenname")
    alternative_names = Column(
        CrossDBJSON,
        default=[],
        comment="Alternative Schreibweisen für Dokumentenerkennung"
    )

    # Adresse
    street = Column(String(255), nullable=True, comment="Strasse mit Hausnummer")
    postal_code = Column(String(20), nullable=True, comment="PLZ")
    city = Column(String(100), nullable=True, comment="Stadt")
    country = Column(String(100), default="Deutschland", comment="Land")

    # Steueridentifikation
    vat_id = Column(String(50), nullable=True, comment="USt-IdNr. (z.B. DE123456789)")
    tax_number = Column(String(50), nullable=True, comment="Steuernummer")

    # Bankverbindung
    iban = Column(String(34), nullable=True, comment="IBAN")
    bic = Column(String(11), nullable=True, comment="BIC/SWIFT")

    # Kontaktdaten
    email = Column(String(255), nullable=True, comment="Zentrale E-Mail-Adresse")
    phone = Column(String(50), nullable=True, comment="Telefonnummer")
    website = Column(String(255), nullable=True, comment="Webseite")

    # Handelsregister
    commercial_register = Column(String(100), nullable=True, comment="Handelsregister-Nr.")
    court = Column(String(100), nullable=True, comment="Registergericht")

    # Kalender-Sync (Phase 6D)
    calendar_sync = Column(CrossDBJSON, nullable=True, comment="Sync-Konfiguration (Provider, URL, Kategorien)")
    calendar_oauth_tokens = Column(CrossDBJSON, nullable=True, comment="Verschluesselte OAuth-Tokens nach Provider")
    calendar_sync_state = Column(CrossDBJSON, nullable=True, comment="Sync-State Mapping {uid: external_event_id}")

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_company_settings_updated", "updated_at"),
    )


# =============================================================================
# SAVED FILTERS & APP CONFIG
# =============================================================================

class SavedFilter(Base):
    """Gespeicherte Filter für Server-seitige Persistenz mit Sharing.

    Ersetzt die LocalStorage-basierte Implementierung durch eine
    persistente Loesung mit Multi-Tenant-Isolation und Sharing-Option.

    Features:
    - Pro Feature (documents, invoices, entities, transactions)
    - Sharing innerhalb einer Company
    - Default-Filter pro User
    - Usage-Tracking für Sortierung nach Häufigkeit

    Usage:
        # Eigene Filter
        filters = db.query(SavedFilter).filter(
            SavedFilter.user_id == current_user.id,
            SavedFilter.feature == "documents"
        ).all()

        # Geteilte Filter der Company
        shared = db.query(SavedFilter).filter(
            SavedFilter.company_id == current_user.company_id,
            SavedFilter.is_shared == True,
            SavedFilter.feature == "documents"
        ).all()
    """
    __tablename__ = "saved_filters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner and tenant
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Feature this filter applies to
    feature = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Feature scope: documents, invoices, entities, transactions, etc."
    )

    # Filter configuration as JSONB
    filter_config = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="Flexible filter config: {status: [], tags: [], dateRange: {}, search: ''}"
    )

    # Sharing and default settings
    is_shared = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="If true, visible to all users in the same company"
    )
    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="If true, auto-applied when opening the feature"
    )

    # Usage tracking for sorting by popularity/recency
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="saved_filters")
    company = relationship("Company", backref="saved_filters")

    __table_args__ = (
        Index("ix_saved_filters_user_feature", "user_id", "feature", "deleted_at"),
        Index("ix_saved_filters_company_shared", "company_id", "feature", "is_shared", "deleted_at"),
        {"comment": "Server-side saved filters with sharing support"}
    )

    def __repr__(self) -> str:
        return f"<SavedFilter {self.name} ({self.feature})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "feature": self.feature,
            "filter_config": self.filter_config,
            "is_shared": self.is_shared,
            "is_default": self.is_default,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_own": True,  # Will be set by service
        }


# ============================================================================
# APP CONFIG - Key-Value Store for Application Configuration
# Used by MLOps, OCR Self-Learning, and other system-wide settings
# ============================================================================

class AppConfig(Base):
    """System-weite Konfigurationsspeicherung als Key-Value Store.

    Flexibler JSONB-basierter Speicher für:
    - MLOps Model Registry
    - OCR Confidence Adjustments
    - Feature Flags
    - System-weite Einstellungen

    Usage:
        # Speichern
        config = AppConfig(
            key="mlops_model_registry",
            value={"deepseek": [...], "got_ocr": [...]},
            description="MLOps Model Versioning"
        )
        db.add(config)

        # Laden
        config = await db.execute(
            select(AppConfig).where(AppConfig.key == "mlops_model_registry")
        )
        registry = config.scalar_one_or_none()
    """
    __tablename__ = "app_config"

    key = Column(
        String(255),
        primary_key=True,
        nullable=False,
        comment="Eindeutiger Schluessel für die Konfiguration"
    )
    value = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="JSONB-Wert der Konfiguration"
    )
    description = Column(
        Text,
        nullable=True,
        comment="Beschreibung der Konfiguration"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        {"comment": "System-weite Konfiguration als Key-Value Store"}
    )

    def __repr__(self) -> str:
        return f"<AppConfig key={self.key}>"


# =============================================================================
# ZERO-TOUCH OCR
# =============================================================================

class ZeroTouchResult(Base):
    """Zero-Touch OCR Ergebnis - Automatische Dokumentverarbeitung."""
    __tablename__ = "zero_touch_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Confidence scores
    ocr_confidence = Column(Float, nullable=True)
    classification_type = Column(String(50), nullable=True)
    classification_confidence = Column(Float, default=0.0)
    extraction_confidence = Column(Float, default=0.0)
    extracted_fields = Column(CrossDBJSON, default=dict)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True
    )
    entity_confidence = Column(Float, nullable=True)
    overall_confidence = Column(Float, default=0.0)

    # Processing flags
    auto_processed = Column(Boolean, default=False)
    requires_review = Column(Boolean, default=True)
    review_completed = Column(Boolean, default=False)
    reviewed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Business object
    business_object_type = Column(String(50), nullable=True)
    business_object_id = Column(UUID(as_uuid=True), nullable=True)

    # Performance
    total_processing_ms = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="zero_touch_result")
    company = relationship("Company", backref="zero_touch_results")
    entity = relationship("BusinessEntity", backref="zero_touch_results")
    reviewed_by = relationship("User", backref="zero_touch_reviews")

    __table_args__ = (
        Index("ix_zero_touch_company_created", "company_id", "created_at"),
        Index(
            "ix_zero_touch_auto_processed",
            "company_id", "auto_processed",
            postgresql_where=text("auto_processed = true"),
        ),
        Index(
            "ix_zero_touch_requires_review",
            "company_id", "requires_review",
            postgresql_where=text("requires_review = true AND review_completed = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ZeroTouchResult {self.id} confidence={self.overall_confidence} auto={self.auto_processed}>"


# ============================================================================
# NLQ 2.0 MODELS (Feature 2 - Phase 1)
# ============================================================================

class NLQQueryLog(Base):
    """Natural Language Query Log - Protokollierung von NLQ-Abfragen."""
    __tablename__ = "nlq_query_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Query data
    natural_query = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    sanitized_sql = Column(Text, nullable=True)
    query_intent = Column(String(100), nullable=True)

    # Execution
    execution_time_ms = Column(Integer, default=0)
    result_count = Column(Integer, default=0)
    was_cached = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)

    # Visualization
    visualization_type = Column(String(50), nullable=True)  # bar, line, pie, table, kpi
    visualization_config = Column(CrossDBJSON, default=dict)

    # Feedback
    feedback_rating = Column(Integer, nullable=True)  # 1-5
    feedback_comment = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="nlq_queries")
    company = relationship("Company", backref="nlq_queries")

    __table_args__ = (
        Index("ix_nlq_queries_company_created", "company_id", "created_at"),
        Index("ix_nlq_queries_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<NLQQueryLog {self.id} intent={self.query_intent}>"


# ============================================================================
# SMART INBOX MODELS (Feature 3 - Phase 1)
# ============================================================================

class SmartInboxItemSource(str, Enum):
    """Quelle eines Smart Inbox Items."""
    VALIDATION_QUEUE = "validation_queue"
    ALERT = "alert"
    DEADLINE = "deadline"
    OCR_RESULT = "ocr_result"
    TASK = "task"
    APPROVAL = "approval"
    INVOICE = "invoice"
    WORKFLOW = "workflow"


class SmartInboxItemStatus(str, Enum):
    """Status eines Smart Inbox Items."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class SmartInboxItem(Base):
    """Smart Inbox Item - KI-priorisierte Aufgabe."""
    __tablename__ = "smart_inbox_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source
    source_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)

    # Priority
    raw_priority = Column(Float, default=50.0)
    ml_priority = Column(Float, default=50.0)
    urgency_score = Column(Float, default=0.0)
    importance_score = Column(Float, default=0.0)

    # Status
    status = Column(String(20), default=SmartInboxItemStatus.PENDING)
    deadline = Column(DateTime(timezone=True), nullable=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)

    # Actions
    recommended_actions = Column(CrossDBJSON, default=list)
    completed_action = Column(String(100), nullable=True)

    # Context
    context_data = Column(CrossDBJSON, default=dict)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="smart_inbox_items")
    company = relationship("Company", backref="smart_inbox_items")
    document = relationship("Document", backref="smart_inbox_items")
    entity = relationship("BusinessEntity", backref="smart_inbox_items")

    __table_args__ = (
        Index("ix_smart_inbox_user_status", "user_id", "status"),
        Index("ix_smart_inbox_company_created", "company_id", "created_at"),
        Index(
            "ix_smart_inbox_pending_priority",
            "user_id", "ml_priority",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_smart_inbox_snoozed",
            "user_id", "snoozed_until",
            postgresql_where=text("status = 'snoozed'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<SmartInboxItem {self.id} priority={self.ml_priority} status={self.status}>"


class UserBehaviorLog(Base):
    """User Behavior Log - Lerndaten für ML-Priorisierung."""
    __tablename__ = "user_behavior_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Reference
    inbox_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("smart_inbox_items.id", ondelete="CASCADE"),
        nullable=True
    )

    # Behavior
    action = Column(String(50), nullable=False)  # viewed, clicked, dismissed, completed, snoozed
    source_type = Column(String(50), nullable=True)
    time_spent_ms = Column(Integer, default=0)
    context_page = Column(String(200), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="behavior_logs")
    company = relationship("Company", backref="behavior_logs")
    inbox_item = relationship("SmartInboxItem", backref="behavior_logs")

    __table_args__ = (
        Index("ix_behavior_logs_user_created", "user_id", "created_at"),
        Index("ix_behavior_logs_company_created", "company_id", "created_at"),
        Index("ix_behavior_logs_item", "inbox_item_id"),
    )

    def __repr__(self) -> str:
        return f"<UserBehaviorLog {self.id} action={self.action}>"


# ============================================================================
# CEO DASHBOARD MODELS (Feature 4 - Phase 2)
# ============================================================================

class CompanyHealthSnapshot(Base):
    """Täglicher Gesundheits-Snapshot eines Unternehmens."""
    __tablename__ = "company_health_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    snapshot_date = Column(Date, nullable=False)

    # Health scores (0-100)
    health_score_overall = Column(Float, default=0.0)
    health_score_financial = Column(Float, default=0.0)
    health_score_operations = Column(Float, default=0.0)
    health_score_risk = Column(Float, default=0.0)
    health_score_compliance = Column(Float, default=0.0)

    # KPIs
    documents_count = Column(Integer, default=0)
    invoices_pending = Column(Integer, default=0)
    invoices_overdue = Column(Integer, default=0)
    pending_amount = Column(Numeric(12, 2), default=0)
    overdue_amount = Column(Numeric(12, 2), default=0)
    auto_process_rate = Column(Float, default=0.0)
    active_alerts = Column(Integer, default=0)
    critical_alerts = Column(Integer, default=0)

    # Additional metrics
    metrics_data = Column(CrossDBJSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="health_snapshots")

    __table_args__ = (
        UniqueConstraint("company_id", "snapshot_date", name="uq_health_snapshot_company_date"),
        Index("ix_health_snapshot_company_date", "company_id", "snapshot_date"),
    )

    def __repr__(self) -> str:
        return f"<CompanyHealthSnapshot {self.snapshot_date} score={self.health_score_overall}>"


# ============================================================================
# KNOWLEDGE GRAPH MODELS (Feature 5 - Phase 2)
# ============================================================================

class GraphEdge(Base):
    """Knowledge Graph Kante - Beziehung zwischen Entitäten."""
    __tablename__ = "graph_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source node
    source_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)

    # Target node
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)

    # Edge metadata
    edge_type = Column(String(50), nullable=False)
    properties = Column(CrossDBJSON, default=dict)
    weight = Column(Float, default=1.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="graph_edges")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "source_type", "source_id",
            "target_type", "target_id", "edge_type",
            name="uq_graph_edge_unique"
        ),
        Index("ix_graph_edges_source", "company_id", "source_type", "source_id"),
        Index("ix_graph_edges_target", "company_id", "target_type", "target_id"),
        Index("ix_graph_edges_type", "company_id", "edge_type"),
    )

    def __repr__(self) -> str:
        return f"<GraphEdge {self.source_type}:{self.source_id} -[{self.edge_type}]-> {self.target_type}:{self.target_id}>"


# ============================================================================
# MERKLE TREE AUDIT MODELS (Feature 6 - Phase 2)
# ============================================================================

class MerkleTreeNode(Base):
    """Merkle Tree Knoten für kryptografischen Audit-Trail."""
    __tablename__ = "merkle_tree_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tree identification
    tree_id = Column(String(100), nullable=False)
    level = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)

    # Hash data
    hash_value = Column(String(64), nullable=False)
    left_child_hash = Column(String(64), nullable=True)
    right_child_hash = Column(String(64), nullable=True)

    # Statistics
    entry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="merkle_tree_nodes")

    __table_args__ = (
        UniqueConstraint("company_id", "tree_id", "level", "position", name="uq_merkle_node"),
        Index("ix_merkle_tree_id", "company_id", "tree_id", "level", "position"),
    )

    def __repr__(self) -> str:
        return f"<MerkleTreeNode tree={self.tree_id} level={self.level} pos={self.position}>"


# ============================================================================
# AI ETHICS MODELS (Feature 7 - Phase 2)
# ============================================================================

class AIEthicsAudit(Base):
    """KI-Ethik Audit - Protokollierung ethischer Prüfungen."""
    __tablename__ = "ai_ethics_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Audit details
    audit_type = Column(String(50), nullable=False)
    decision_type = Column(String(100), nullable=True)
    decision_id = Column(UUID(as_uuid=True), nullable=True)
    result = Column(String(20), nullable=False)  # passed, warning, failed
    fairness_score = Column(Float, nullable=True)
    details = Column(CrossDBJSON, default=dict)
    recommendations = Column(CrossDBJSON, default=list)

    # Creator
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="ai_ethics_audits")
    created_by = relationship("User", backref="ai_ethics_audits")

    __table_args__ = (
        Index("ix_ai_ethics_company_created", "company_id", "created_at"),
        Index("ix_ai_ethics_type", "company_id", "audit_type"),
    )

    def __repr__(self) -> str:
        return f"<AIEthicsAudit {self.id} type={self.audit_type} result={self.result}>"


class BiasReport(Base):
    """Bias-Bericht - Erkennungsergebnisse für Voreingenommenheit."""
    __tablename__ = "bias_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Report details
    report_type = Column(String(50), nullable=False)
    overall_fairness = Column(Float, nullable=False)
    dimensions = Column(CrossDBJSON, default=list)
    affected_entities = Column(Integer, default=0)
    recommendations = Column(CrossDBJSON, default=list)

    # Timestamps
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", backref="bias_reports")

    __table_args__ = (
        Index("ix_bias_reports_company_generated", "company_id", "generated_at"),
    )

    def __repr__(self) -> str:
        return f"<BiasReport {self.id} fairness={self.overall_fairness}>"


# ============================================================================
# EVENT SOURCING MODELS (Feature 8 - Phase 3)
# ============================================================================

class DomainEvent(Base):
    """Domain Event für Event-Sourcing (Hybrid-Ansatz)."""
    __tablename__ = "domain_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aggregate
    aggregate_type = Column(String(50), nullable=False)  # document, invoice, payment, entity
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_number = Column(BigInteger, nullable=False)

    # Event
    event_type = Column(String(100), nullable=False)
    event_data = Column(CrossDBJSON, nullable=False)
    event_metadata = Column(CrossDBJSON, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Causation
    correlation_id = Column(UUID(as_uuid=True), nullable=True)
    causation_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="domain_events")

    __table_args__ = (
        UniqueConstraint("aggregate_type", "aggregate_id", "sequence_number", name="uq_event_sequence"),
        Index("ix_domain_events_aggregate", "company_id", "aggregate_type", "aggregate_id", "sequence_number"),
        Index("ix_domain_events_type", "company_id", "event_type"),
        Index("ix_domain_events_correlation", "correlation_id"),
    )

    def __repr__(self) -> str:
        return f"<DomainEvent {self.event_type} seq={self.sequence_number}>"


class EventSnapshot(Base):
    """Snapshot des Aggregatzustands für Performance."""
    __tablename__ = "event_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aggregate
    aggregate_type = Column(String(50), nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_number = Column(BigInteger, nullable=False)

    # Snapshot data
    state = Column(CrossDBJSON, nullable=False)
    version = Column(Integer, default=1)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="event_snapshots")

    __table_args__ = (
        Index("ix_event_snapshots_aggregate", "company_id", "aggregate_type", "aggregate_id"),
    )

    def __repr__(self) -> str:
        return f"<EventSnapshot {self.aggregate_type}:{self.aggregate_id} seq={self.sequence_number}>"


# ============================================================================
# EXTERNAL ENRICHMENT MODELS (Feature 12 - Phase 4)
# ============================================================================

class ExternalEnrichmentResult(Base):
    """Externes Datenanreicherungsergebnis."""
    __tablename__ = "external_enrichment_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source
    source = Column(String(100), nullable=False)  # handelsregister, bundesanzeiger
    source_url = Column(String(500), nullable=True)
    raw_data = Column(CrossDBJSON, default=dict)
    enriched_data = Column(CrossDBJSON, default=dict)

    # Status
    status = Column(String(20), default="completed")  # pending, completed, failed
    confidence = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)

    # Cache
    cached_until = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="enrichment_results")
    entity = relationship("BusinessEntity", backref="enrichment_results")

    __table_args__ = (
        Index("ix_enrichment_entity_source", "entity_id", "source"),
        Index("ix_enrichment_company_created", "company_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ExternalEnrichmentResult {self.source} entity={self.entity_id}>"


# ============================================================================
# DOCUMENT ANNOTATIONS MODELS (Feature 14 - Phase 4)
# ============================================================================

class AnnotationType(str, Enum):
    """Typ einer Dokument-Annotation."""
    HIGHLIGHT = "highlight"
    COMMENT = "comment"
    DRAWING = "drawing"
    STAMP = "stamp"
    APPROVAL = "approval"
    REJECTION = "rejection"
    SIGNATURE = "signature"


class DocumentAnnotation(Base):
    """Dokument-Annotation - Markierungen, Kommentare, Zeichnungen."""
    __tablename__ = "document_annotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Annotation type and content
    annotation_type = Column(String(20), nullable=False)
    content = Column(Text, nullable=True)
    svg_data = Column(Text, nullable=True)

    # Position
    page = Column(Integer, nullable=False, default=1)
    position = Column(CrossDBJSON, default=dict)  # {x, y, width, height}
    color = Column(String(20), nullable=True)

    # Threading
    parent_annotation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_annotations.id", ondelete="CASCADE"),
        nullable=True
    )
    mentioned_user_ids = Column(CrossDBJSON, default=list)

    # Status
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="annotations")
    company = relationship("Company", backref="document_annotations")
    user = relationship("User", foreign_keys=[user_id], backref="annotations_created")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id], backref="annotations_resolved")
    parent = relationship("DocumentAnnotation", remote_side=[id], backref="replies")

    __table_args__ = (
        Index("ix_annotations_document_page", "document_id", "page"),
        Index("ix_annotations_company_created", "company_id", "created_at"),
        Index("ix_annotations_parent", "parent_annotation_id"),
    )

    def __repr__(self) -> str:
        return f"<DocumentAnnotation {self.id} type={self.annotation_type} page={self.page}>"


# ============================================================================
# LIFE EVENTS MODELS (Feature 16 - Phase 4)
# ============================================================================

class LifeEventType(str, Enum):
    """Typ eines Lebensereignisses."""
    UMZUG = "umzug"
    HEIRAT = "heirat"
    KIND = "kind"
    JOBWECHSEL = "jobwechsel"
    RUHESTAND = "ruhestand"
    TODESFALL = "todesfall"
    IMMOBILIENKAUF = "immobilienkauf"
    SCHEIDUNG = "scheidung"


class LifeEventStatus(str, Enum):
    """Status eines Lebensereignisses."""
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class LifeEvent(Base):
    """Lebensereignis - Proaktiver Lebensberater."""
    __tablename__ = "life_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Event details
    event_type = Column(String(30), nullable=False)
    status = Column(String(20), default=LifeEventStatus.DETECTED.value)
    detection_source = Column(String(100), nullable=True)  # document_analysis, user_input, pattern
    detection_confidence = Column(Float, default=0.0)

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(Date, nullable=True)

    # Checklist and recommendations
    checklist = Column(CrossDBJSON, default=list)  # [{id, task, completed, due_date}]
    recommendations = Column(CrossDBJSON, default=list)  # [{title, description, priority, url}]
    financial_impact = Column(CrossDBJSON, default=dict)  # {estimated_cost, savings_potential, tax_impact}

    # Related documents
    related_document_ids = Column(CrossDBJSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="life_events")
    company = relationship("Company", backref="life_events")

    __table_args__ = (
        Index("ix_life_events_user_status", "user_id", "status"),
        Index("ix_life_events_company_created", "company_id", "created_at"),
        Index("ix_life_events_type", "company_id", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<LifeEvent {self.event_type} status={self.status}>"


# ============================================================================
# VISION 2.0 SUPPLEMENTARY MODELS (Feature Gap Fixes)
# ============================================================================


class DocumentEntityLink(Base):
    """Verknüpfung zwischen Document und BusinessEntity.

    Ermöglicht M:N Beziehungen zwischen Dokumenten und Geschäftspartnern
    mit Typ-Klassifikation und Confidence-Score.

    Link Types:
    - invoice_sender: Entity hat Rechnung gesendet
    - invoice_recipient: Entity ist Rechnungsempfänger
    - mentioned: Entity wird im Dokument erwaehnt
    - extracted: Entity wurde aus OCR-Text extrahiert
    - manual: Manuell vom Benutzer verknüpft
    """
    __tablename__ = "document_entity_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Link metadata
    link_type = Column(String(50), nullable=True)
    confidence = Column(Float, default=1.0)
    link_metadata = Column(CrossDBJSON, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    document = relationship("Document", backref="entity_links")
    entity = relationship("BusinessEntity", backref="document_links")
    company = relationship("Company", backref="document_entity_links")
    created_by = relationship("User")

    __table_args__ = (
        Index("ix_doc_entity_links_company_type", "company_id", "link_type"),
        # Ein Document kann mit einem Entity nur einmal pro Link-Type verknüpft sein
        # Note: Constraint created in migration
    )

    def __repr__(self) -> str:
        return f"<DocumentEntityLink doc={self.document_id} entity={self.entity_id} type={self.link_type}>"


class RiskScoreHistory(Base):
    """Historische Risk-Scores für Geschäftspartner.

    Ermöglicht Trend-Analyse und Explainability für AI Ethics.
    Jeder Eintrag speichert den Score mit allen Faktoren.

    Triggers:
    - scheduled: Tägliche/woechentliche Berechnung
    - invoice_paid: Nach Zahlungseingang
    - dunning_increased: Nach Mahnstufe-Erhöhung
    - manual: Manuelle Neuberechnung
    """
    __tablename__ = "risk_score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Score data
    score = Column(Float, nullable=False)
    risk_level = Column(String(20), nullable=True)  # low, medium, high, critical
    factors = Column(CrossDBJSON, default=dict)  # {"payment_delay": 25, ...}

    # Context
    trigger_event = Column(String(100), nullable=True)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    entity = relationship("BusinessEntity", backref="risk_score_history")
    company = relationship("Company", backref="risk_score_history")

    __table_args__ = (
        Index("ix_risk_score_history_entity_date", "entity_id", "calculated_at"),
        Index("ix_risk_score_history_company_date", "company_id", "calculated_at"),
    )

    def __repr__(self) -> str:
        return f"<RiskScoreHistory entity={self.entity_id} score={self.score} level={self.risk_level}>"
