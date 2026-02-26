# -*- coding: utf-8 -*-
"""
Autonomy Framework database models for Ablage-System.

Ermöglicht Persistierung von:
- Action-Queue (Genehmigungs-Warteschlange)
- Autonomie-Einstellungen pro Company/User
- Autonomie-Entscheidungs-Logs
- Confidence-Routing History

Vision 2.0 Phase 3 - Autonomie-Framework

Feinpoliert und durchdacht - Deutsche Präzision.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# ENUMS
# =============================================================================


class AutonomyLevelEnum(str, Enum):
    """Autonomie-Stufen für das System."""
    CONSERVATIVE = "conservative"      # Level 1: Immer Bestätigung
    SMART_HYBRID = "smart_hybrid"      # Level 2: 95%+ auto
    PROGRESSIVE = "progressive"        # Level 3: Routine auto
    ZERO_TOUCH = "zero_touch"          # Level 4: Alles auto


class ActionCategoryEnum(str, Enum):
    """Kategorien von Aktionen mit unterschiedlichen Risikoprofilen."""
    ROUTINE = "routine"                # Niedrigstes Risiko
    READ_ONLY = "read_only"            # Nur lesend
    MODIFICATION = "modification"      # Datenmodifikation
    NOTIFICATION = "notification"      # Benachrichtigungen
    FINANCIAL = "financial"            # Finanzielle Aktionen
    DELETION = "deletion"              # Löschungen
    EXTERNAL = "external"              # Externe Systeme
    LEGAL = "legal"                    # Rechtlich relevant
    COMPLIANCE = "compliance"          # Hoechstes Risiko


class PendingActionStatus(str, Enum):
    """Status einer ausstehenden Aktion."""
    PENDING = "pending"                # Wartet auf Genehmigung
    APPROVED = "approved"              # Genehmigt
    REJECTED = "rejected"              # Abgelehnt
    EXPIRED = "expired"                # Zeitlich abgelaufen
    AUTO_APPROVED = "auto_approved"    # Automatisch genehmigt
    CANCELLED = "cancelled"            # Abgebrochen


class RoutingDecision(str, Enum):
    """Routing-Entscheidung basierend auf Confidence."""
    AUTO_EXECUTE = "auto_execute"      # Direkt ausführen
    SUGGEST_AND_CONFIRM = "suggest_and_confirm"  # Vorschlagen + Bestätigung
    MANUAL_REVIEW = "manual_review"    # Manuelle Prüfung


# =============================================================================
# AUTONOMY SETTINGS
# =============================================================================


class AutonomySettings(Base):
    """
    Autonomie-Einstellungen pro Company.

    Definiert das Autonomie-Level und Kategorie-spezifische
    Einstellungen für die automatische Aktionsausführung.
    """
    __tablename__ = "autonomy_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Globales Autonomie-Level
    autonomy_level = Column(
        String(30),
        nullable=False,
        default=AutonomyLevelEnum.CONSERVATIVE.value
    )

    # Kategorie-spezifische Einstellungen
    category_overrides = Column(
        CrossDBJSON,
        nullable=True,
        comment="Kategorie-spezifische Autonomie-Level"
    )

    # Confidence-Schwellenwerte
    low_confidence_threshold = Column(
        Float,
        nullable=False,
        default=0.80,
        comment="Unter diesem Wert: Immer manuell"
    )
    high_confidence_threshold = Column(
        Float,
        nullable=False,
        default=0.95,
        comment="Über diesem Wert: Auto-Execute (wenn erlaubt)"
    )

    # Timeout-Einstellungen
    default_timeout_hours = Column(
        Integer,
        nullable=False,
        default=24,
        comment="Standard-Timeout für ausstehende Aktionen"
    )
    auto_approve_on_timeout = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Automatisch genehmigen bei Timeout"
    )

    # Benachrichtigungen
    notify_on_auto_execute = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Benachrichtigung bei Auto-Execute"
    )
    notify_channels = Column(
        CrossDBJSON,
        nullable=True,
        comment="Benachrichtigungskanaele (email, slack, etc.)"
    )

    # Audit-Einstellungen
    require_dual_approval = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Vier-Augen-Prinzip für kritische Aktionen"
    )
    dual_approval_categories = Column(
        CrossDBJSON,
        nullable=True,
        comment="Kategorien die Dual-Approval benötigen"
    )

    # Limits
    daily_auto_execute_limit = Column(
        Integer,
        nullable=True,
        comment="Max. Auto-Executes pro Tag (null = unbegrenzt)"
    )
    max_single_action_value = Column(
        Float,
        nullable=True,
        comment="Max. Wert für Auto-Execute (Finanzaktionen)"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", backref="autonomy_settings")
    updated_by = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "autonomy_level IN ('conservative', 'smart_hybrid', 'progressive', 'zero_touch')",
            name="ck_autonomy_level"
        ),
        CheckConstraint(
            "low_confidence_threshold >= 0.0 AND low_confidence_threshold <= 1.0",
            name="ck_low_threshold_range"
        ),
        CheckConstraint(
            "high_confidence_threshold >= 0.0 AND high_confidence_threshold <= 1.0",
            name="ck_high_threshold_range"
        ),
        CheckConstraint(
            "low_confidence_threshold < high_confidence_threshold",
            name="ck_threshold_order"
        ),
        {"comment": "Autonomie-Einstellungen pro Company"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "autonomy_level": self.autonomy_level,
            "category_overrides": self.category_overrides,
            "low_confidence_threshold": self.low_confidence_threshold,
            "high_confidence_threshold": self.high_confidence_threshold,
            "default_timeout_hours": self.default_timeout_hours,
            "auto_approve_on_timeout": self.auto_approve_on_timeout,
            "notify_on_auto_execute": self.notify_on_auto_execute,
            "require_dual_approval": self.require_dual_approval,
            "daily_auto_execute_limit": self.daily_auto_execute_limit,
            "max_single_action_value": self.max_single_action_value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# PENDING ACTIONS
# =============================================================================


class PendingAction(Base):
    """
    Ausstehende Aktion in der Genehmigungs-Warteschlange.

    Speichert Aktionen die auf Benutzer-Genehmigung
    oder automatische Freigabe warten.
    """
    __tablename__ = "pending_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Typ der Aktion (z.B. send_dunning, approve_payment)"
    )
    action_category = Column(
        String(30),
        nullable=False,
        index=True
    )
    description = Column(Text, nullable=False)
    detailed_description = Column(
        Text,
        nullable=True,
        comment="Ausführliche Beschreibung für Review"
    )

    # Status
    status = Column(
        String(30),
        nullable=False,
        default=PendingActionStatus.PENDING.value,
        index=True
    )

    # Confidence und Routing
    confidence = Column(
        Float,
        nullable=False,
        comment="Konfidenz-Score (0.0-1.0)"
    )
    routing_decision = Column(
        String(30),
        nullable=False,
        comment="Urspruengliche Routing-Entscheidung"
    )
    reason = Column(
        Text,
        nullable=True,
        comment="Begruendung für die Routing-Entscheidung"
    )

    # Aktionsdetails
    parameters = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="Aktionsparameter"
    )
    affected_entities = Column(
        CrossDBJSON,
        nullable=True,
        comment="Betroffene Entitäten (Dokumente, Kunden, etc.)"
    )
    estimated_impact = Column(
        CrossDBJSON,
        nullable=True,
        comment="Geschätzte Auswirkungen der Aktion"
    )

    # Quell-Information
    source_type = Column(
        String(50),
        nullable=True,
        comment="Quelle der Aktion (ai_assistant, workflow, batch)"
    )
    source_id = Column(
        String(100),
        nullable=True,
        comment="ID der Quelle (Conversation ID, Workflow ID)"
    )

    # Genehmigung
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Dual-Approval
    requires_dual_approval = Column(Boolean, nullable=False, default=False)
    second_approver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    second_approved_at = Column(DateTime(timezone=True), nullable=True)

    # Ausführung
    executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_result = Column(
        CrossDBJSON,
        nullable=True,
        comment="Ergebnis der Ausführung"
    )
    execution_error = Column(Text, nullable=True)

    # Timeout
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Ablaufzeitpunkt"
    )

    # Priorität
    priority = Column(
        Integer,
        nullable=False,
        default=50,
        comment="Priorität (0=niedrig, 100=hoch)"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", backref="pending_actions")
    approved_by = relationship(
        "User",
        foreign_keys=[approved_by_id],
        backref="approved_actions"
    )
    second_approver = relationship(
        "User",
        foreign_keys=[second_approver_id]
    )

    __table_args__ = (
        Index("ix_pending_company_status", "company_id", "status"),
        Index("ix_pending_expires", "expires_at"),
        Index("ix_pending_priority", "priority"),
        Index("ix_pending_category", "action_category"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'auto_approved', 'cancelled')",
            name="ck_pending_action_status"
        ),
        CheckConstraint(
            "action_category IN ('routine', 'read_only', 'modification', 'notification', 'financial', 'deletion', 'external', 'legal', 'compliance')",
            name="ck_pending_action_category"
        ),
        CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name="ck_pending_priority_range"
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_pending_confidence_range"
        ),
        {"comment": "Ausstehende Aktionen für Genehmigung"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "action_type": self.action_type,
            "action_category": self.action_category,
            "description": self.description,
            "detailed_description": self.detailed_description,
            "status": self.status,
            "confidence": self.confidence,
            "routing_decision": self.routing_decision,
            "reason": self.reason,
            "parameters": self.parameters,
            "affected_entities": self.affected_entities,
            "estimated_impact": self.estimated_impact,
            "requires_dual_approval": self.requires_dual_approval,
            "priority": self.priority,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


# =============================================================================
# AUTONOMY DECISION LOG
# =============================================================================


class AutonomyDecisionLog(Base):
    """
    Protokoll von Autonomie-Entscheidungen.

    Speichert alle Routing-Entscheidungen für
    Audit, Analyse und ML-Training.
    """
    __tablename__ = "autonomy_decision_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action_type = Column(String(100), nullable=False, index=True)
    action_category = Column(String(30), nullable=False)
    action_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="ID der zugehoerigen PendingAction"
    )

    # Entscheidung
    routing_decision = Column(String(30), nullable=False)
    was_auto_executed = Column(Boolean, nullable=False, default=False)

    # Eingabedaten
    confidence_score = Column(Float, nullable=False)
    autonomy_level = Column(String(30), nullable=False)
    category_override_applied = Column(Boolean, nullable=False, default=False)

    # Schwellenwerte zum Zeitpunkt der Entscheidung
    low_threshold_used = Column(Float, nullable=False)
    high_threshold_used = Column(Float, nullable=False)

    # Begeuendung
    decision_reason = Column(Text, nullable=True)
    decision_factors = Column(
        CrossDBJSON,
        nullable=True,
        comment="Einflussfaktoren auf die Entscheidung"
    )

    # Ergebnis (wenn bereits bekannt)
    outcome = Column(
        String(30),
        nullable=True,
        comment="approved, rejected, expired, executed, failed"
    )
    outcome_at = Column(DateTime(timezone=True), nullable=True)
    user_feedback = Column(
        String(30),
        nullable=True,
        comment="positive, negative, neutral"
    )

    # Performance-Metriken
    decision_time_ms = Column(
        Integer,
        nullable=True,
        comment="Zeit für Routing-Entscheidung in ms"
    )
    execution_time_ms = Column(
        Integer,
        nullable=True,
        comment="Zeit für Ausführung in ms (wenn auto)"
    )

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="autonomy_decision_logs")

    __table_args__ = (
        Index("ix_decision_log_company_date", "company_id", "created_at"),
        Index("ix_decision_log_action_type", "action_type", "created_at"),
        Index("ix_decision_log_routing", "routing_decision", "created_at"),
        Index("ix_decision_log_outcome", "outcome"),
        CheckConstraint(
            "routing_decision IN ('auto_execute', 'suggest_and_confirm', 'manual_review')",
            name="ck_decision_routing"
        ),
        {"comment": "Protokoll der Autonomie-Entscheidungen"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "action_type": self.action_type,
            "action_category": self.action_category,
            "action_id": str(self.action_id) if self.action_id else None,
            "routing_decision": self.routing_decision,
            "was_auto_executed": self.was_auto_executed,
            "confidence_score": self.confidence_score,
            "autonomy_level": self.autonomy_level,
            "decision_reason": self.decision_reason,
            "outcome": self.outcome,
            "user_feedback": self.user_feedback,
            "decision_time_ms": self.decision_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# AUTONOMY METRICS (AGGREGATED)
# =============================================================================


class AutonomyMetrics(Base):
    """
    Aggregierte Metriken für Autonomie-Performance.

    Speichert tägliche Zusammenfassungen für
    Dashboard und Trend-Analyse.
    """
    __tablename__ = "autonomy_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zeitraum
    date = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Datum der Metrik"
    )

    # Volumen
    total_actions = Column(Integer, nullable=False, default=0)
    auto_executed_count = Column(Integer, nullable=False, default=0)
    suggested_count = Column(Integer, nullable=False, default=0)
    manual_review_count = Column(Integer, nullable=False, default=0)

    # Genehmigungen
    approved_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    expired_count = Column(Integer, nullable=False, default=0)

    # Performance
    avg_confidence = Column(Float, nullable=True)
    avg_decision_time_ms = Column(Float, nullable=True)
    avg_approval_time_min = Column(
        Float,
        nullable=True,
        comment="Durchschnittliche Zeit bis Genehmigung"
    )

    # Qualitaet
    auto_execute_success_rate = Column(
        Float,
        nullable=True,
        comment="Erfolgsrate der Auto-Executes"
    )
    false_positive_rate = Column(
        Float,
        nullable=True,
        comment="Rate der überfluessigen Reviews"
    )

    # Kategorien-Aufschluesselung
    by_category = Column(
        CrossDBJSON,
        nullable=True,
        comment="Metriken nach Aktionskategorie"
    )
    by_action_type = Column(
        CrossDBJSON,
        nullable=True,
        comment="Metriken nach Aktionstyp"
    )

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", backref="autonomy_metrics")

    __table_args__ = (
        Index(
            "ix_autonomy_metrics_company_date",
            "company_id",
            "date",
            unique=True
        ),
        {"comment": "Aggregierte Autonomie-Metriken"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "date": self.date.isoformat() if self.date else None,
            "total_actions": self.total_actions,
            "auto_executed_count": self.auto_executed_count,
            "suggested_count": self.suggested_count,
            "manual_review_count": self.manual_review_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "expired_count": self.expired_count,
            "avg_confidence": self.avg_confidence,
            "avg_decision_time_ms": self.avg_decision_time_ms,
            "avg_approval_time_min": self.avg_approval_time_min,
            "auto_execute_success_rate": self.auto_execute_success_rate,
            "by_category": self.by_category,
        }


# =============================================================================
# PROACTIVE ACTION STATE
# =============================================================================


class ProactiveActionState(Base):
    """
    Persistierter Zustand für proaktive Aufgaben.

    Speichert ob eine proaktive Aufgabe erledigt oder verschoben wurde.
    Aufgaben werden über eine zusammengesetzte action_id identifiziert
    (Format: '{action_type}:{source_id}').
    """
    __tablename__ = "proactive_action_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Aufgaben-Identifikation
    action_id = Column(
        String(300),
        nullable=False,
        index=True,
        comment="Zusammengesetzte ID: '{action_type}:{source_id}'"
    )

    # Status
    is_completed = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Aufgabe wurde als erledigt markiert"
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Erledigung"
    )

    # Snooze
    snoozed_until = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Aufgabe bis zu diesem Zeitpunkt unterdrücken"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="proactive_action_states")

    __table_args__ = (
        Index(
            "ix_proactive_state_company_action",
            "company_id",
            "action_id",
            unique=True,
        ),
        Index("ix_proactive_state_snoozed", "snoozed_until"),
        {"comment": "Zustand proaktiver Aufgaben (erledigt/verschoben)"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "action_id": self.action_id,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "snoozed_until": self.snoozed_until.isoformat() if self.snoozed_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
