"""AI/ML Intelligence Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Index, Date, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON


# =============================================================================
# AI Autonomy Models (Feature 07)
# =============================================================================

class AIConfidenceThreshold(Base):
    """Admin-konfigurierbare Konfidenz-Schwellenwerte.

    Definiert pro Entscheidungstyp ab welcher Konfidenz automatisch
    angewendet wird (auto), nur vorgeschlagen (suggest) oder
    manuell geprüft werden muss (manual).
    """
    __tablename__ = "ai_confidence_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Decision Type (unique per company)
    decision_type = Column(String(50), nullable=False, index=True)
    # Types: categorization, accounting, matching, anomaly, prediction, duplicate

    # Schwellenwerte (0.0 - 1.0)
    auto_threshold = Column(Float, default=0.95)  # Ab hier automatisch
    suggest_threshold = Column(Float, default=0.80)  # Ab hier vorschlagen
    # Unter suggest_threshold = manuelle Review

    # Feature-Toggle
    is_enabled = Column(Boolean, default=True)
    allow_auto_apply = Column(Boolean, default=True)

    # Beschreibung für Admin-UI
    display_name = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    # Audit
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="ai_thresholds")
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        UniqueConstraint("company_id", "decision_type", name="uq_ai_threshold_company_type"),
        {"comment": "Admin-konfigurierbare KI-Konfidenz-Schwellenwerte"}
    )

    def __repr__(self) -> str:
        return f"<AIConfidenceThreshold {self.decision_type} auto={self.auto_threshold}>"


class AIDecision(Base):
    """KI-Entscheidung mit vollständigem Audit-Trail.

    Speichert jede KI-Entscheidung mit Konfidenz, Erklärung und
    Review-Status für GoBD-Compliance und Self-Learning.
    """
    __tablename__ = "ai_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    # Decision Type
    decision_type = Column(String(50), nullable=False, index=True)
    # Types: categorization, accounting, matching, anomaly, prediction, duplicate

    # Entscheidungs-Details
    decision_value = Column(CrossDBJSON, nullable=False)
    # Beispiel categorization: {"category": "invoice_incoming", "subcategory": "supplier_invoice"}
    # Beispiel accounting: {"debit_account": "4000", "credit_account": "1600", "tax_code": "VSt19"}
    # Beispiel matching: {"matched_document_id": "...", "match_type": "invoice_delivery"}

    # Confidence
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0
    calibrated_confidence = Column(Float, nullable=True)  # Nach Kalibrierung
    confidence_level = Column(String(20), nullable=False, index=True)  # auto, suggest, manual

    # Explainable AI
    explanation = Column(CrossDBJSON, nullable=True)
    # Beispiel: {"reasons": ["Keyword 'Rechnung' gefunden", "Lieferant bekannt"], "features": {...}}
    features_used = Column(CrossDBJSON, nullable=True)  # Welche Features verwendet
    model_version = Column(String(50), nullable=True)  # Modell-Version für Reproduzierbarkeit

    # Autonomie-Status
    auto_applied = Column(Boolean, default=False)  # Automatisch angewendet?
    requires_review = Column(Boolean, default=True, index=True)  # Muss geprüft werden?
    is_final = Column(Boolean, default=False)  # Wurde final entschieden?

    # Review-Informationen
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_action = Column(String(20), nullable=True)  # approved, rejected, modified
    review_comment = Column(Text, nullable=True)

    # Bei Modifikation: Was wurde geändert?
    modified_value = Column(CrossDBJSON, nullable=True)

    # Timing
    processing_time_ms = Column(Integer, nullable=True)

    # Audit/Compliance
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="ai_decisions")
    document = relationship("Document", backref="ai_decisions")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    feedback = relationship("AILearningFeedback", back_populates="ai_decision", uselist=False)

    __table_args__ = (
        Index("ix_ai_decisions_pending_review", "decision_type", "requires_review", "is_final"),
        {"comment": "KI-Entscheidungen mit vollständigem Audit-Trail"}
    )

    def __repr__(self) -> str:
        return f"<AIDecision {self.decision_type} conf={self.confidence:.2f} level={self.confidence_level}>"


class AILearningFeedback(Base):
    """Self-Learning Feedback aus User-Korrekturen.

    Speichert Korrekturen und Ablehnungen um die KI-Modelle
    kontinuierlich zu verbessern.
    """
    __tablename__ = "ai_learning_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_decision_id = Column(UUID(as_uuid=True), ForeignKey("ai_decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Feedback-Typ
    feedback_type = Column(String(20), nullable=False, index=True)
    # Types: approved, corrected, rejected

    # Original vs. Korrigiert
    original_value = Column(CrossDBJSON, nullable=False)
    corrected_value = Column(CrossDBJSON, nullable=True)  # Nur bei 'corrected'

    # Korrektur-Details
    correction_reason = Column(Text, nullable=True)
    correction_category = Column(String(50), nullable=True)  # z.B. "wrong_category", "missing_info"

    # Wer hat korrigiert
    corrector_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Learning-Status
    processed_for_learning = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    learning_batch_id = Column(String(50), nullable=True)

    # Gewichtung für Learning
    learning_weight = Column(Float, default=1.0)  # Höher = wichtiger

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    ai_decision = relationship("AIDecision", back_populates="feedback")
    company = relationship("Company", backref="ai_learning_feedback")
    corrector = relationship("User", foreign_keys=[corrector_id])

    __table_args__ = (
        {"comment": "Self-Learning Feedback aus User-Korrekturen"}
    )

    def __repr__(self) -> str:
        return f"<AILearningFeedback {self.feedback_type} processed={self.processed_for_learning}>"


class DocumentMatch(Base):
    """Smart Matching zwischen zusammengehoerenden Dokumenten.

    Speichert KI-erkannte Verbindungen zwischen Dokumenten,
    z.B. Rechnung <-> Lieferschein <-> Bestellung.
    """
    __tablename__ = "document_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Quell- und Ziel-Dokument
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    target_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Match-Typ
    match_type = Column(String(50), nullable=False, index=True)
    # Types: invoice_delivery, invoice_order, delivery_order, invoice_contract, etc.

    # Match-Qualitaet
    match_confidence = Column(Float, nullable=False)
    match_score = Column(Float, nullable=True)  # Detaillierter Score
    match_features = Column(CrossDBJSON, nullable=True)
    # Beispiel: {"order_number": 0.95, "customer": 0.90, "amount": 0.85, "date": 0.70}

    # Verknüpfungs-Status
    auto_linked = Column(Boolean, default=False)
    is_confirmed = Column(Boolean, default=False, index=True)
    is_rejected = Column(Boolean, default=False)

    # Wer hat verknüpft/bestätigt
    linked_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Referenz zur AI-Entscheidung
    ai_decision_id = Column(UUID(as_uuid=True), ForeignKey("ai_decisions.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="document_matches")
    source_document = relationship("Document", foreign_keys=[source_document_id], backref="matches_as_source")
    target_document = relationship("Document", foreign_keys=[target_document_id], backref="matches_as_target")
    linked_by = relationship("User", foreign_keys=[linked_by_id])
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])
    ai_decision = relationship("AIDecision", backref="document_match")

    __table_args__ = (
        UniqueConstraint("source_document_id", "target_document_id", name="uq_document_match_pair"),
        {"comment": "Smart Matching zwischen Dokumenten"}
    )

    def __repr__(self) -> str:
        return f"<DocumentMatch {self.match_type} conf={self.match_confidence:.2f}>"


class PaymentPrediction(Base):
    """Zahlungsvorhersagen für Rechnungen.

    Prognostiziert basierend auf Historie wann eine Rechnung
    bezahlt wird für Cashflow-Planung.
    """
    __tablename__ = "payment_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True, index=True)

    # Vorhersage
    predicted_payment_date = Column(Date, nullable=False, index=True)
    predicted_days = Column(Integer, nullable=False)  # Tage ab Rechnungsdatum
    confidence = Column(Float, nullable=False)

    # Vorhersage-Details
    prediction_features = Column(CrossDBJSON, nullable=True)
    # Beispiel: {"historical_avg_days": 25, "invoice_amount": 5000, "payment_terms": "net30"}

    # Modell-Info
    model_version = Column(String(50), nullable=True)
    prediction_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Tatsaechliche Zahlung (für Learning)
    actual_payment_date = Column(Date, nullable=True)
    actual_days = Column(Integer, nullable=True)
    prediction_error_days = Column(Integer, nullable=True)  # Differenz

    # Status
    is_paid = Column(Boolean, default=False, index=True)
    is_overdue = Column(Boolean, default=False)

    # Referenz zur AI-Entscheidung
    ai_decision_id = Column(UUID(as_uuid=True), ForeignKey("ai_decisions.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="payment_predictions")
    document = relationship("Document", backref="payment_predictions")
    business_entity = relationship("BusinessEntity", backref="payment_predictions")
    ai_decision = relationship("AIDecision", backref="payment_prediction")

    __table_args__ = (
        {"comment": "Zahlungsvorhersagen für Cashflow-Planung"}
    )

    def __repr__(self) -> str:
        return f"<PaymentPrediction predicted={self.predicted_payment_date} conf={self.confidence:.2f}>"


# =============================================================================
# AUTONOMOUS TRUST SYSTEM MODELS (Phase 2.1)
# Multi-Level Trust für autonome KI-Aktionen
# =============================================================================


class AutonomousTrustConfig(Base):
    """Trust-Level Konfiguration pro Company.

    Speichert das aktuelle Trust-Level und Konfiguration für
    autonome KI-Aktionen. Kann global oder pro Dokumenttyp sein.

    Trust-Level:
    - LEVEL_1_ASSISTANCE: Alle Aktionen erfordern Bestätigung
    - LEVEL_2_AUTO_ACCEPT: >90% Confidence, 24h Auto-Accept
    - LEVEL_3_CONFIDENCE: >95% sofort, 80-95% verzögert (4h)
    - LEVEL_4_AUTONOMOUS: Volle Autonomie, nur Exceptions
    """
    __tablename__ = "autonomous_trust_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Trust Level
    trust_level = Column(
        String(50),
        nullable=False,
        default="assistance",
        comment="Trust-Level: assistance, auto_accept, confidence, autonomous"
    )

    # Optional: Spezifisch für Dokumenttyp
    document_type = Column(
        String(50),
        nullable=True,
        comment="Optional: Spezifisches Level für diesen Dokumenttyp"
    )

    # Konfiguration
    is_enabled = Column(Boolean, default=True)

    # Schwellenwerte (Override der Defaults)
    immediate_threshold = Column(
        Float,
        nullable=True,
        comment="Ab hier sofortige Aktion (Override)"
    )
    delayed_threshold = Column(
        Float,
        nullable=True,
        comment="Ab hier verzögerte Aktion (Override)"
    )
    delay_hours = Column(
        Integer,
        nullable=True,
        comment="Wartezeit in Stunden (Override)"
    )

    # Metriken-Snapshot (wird periodisch aktualisiert)
    metrics_snapshot = Column(
        CrossDBJSON,
        nullable=True,
        comment="Letzter Metriken-Snapshot (total_decisions, approval_rate, etc.)"
    )
    metrics_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Trust-Level Änderungshistorie
    level_changed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der letzten Level-Änderung"
    )
    change_reason = Column(
        Text,
        nullable=True,
        comment="Grund für letzte Level-Änderung"
    )

    # Audit
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="autonomous_trust_configs")
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        UniqueConstraint("company_id", "document_type", name="uq_trust_config_company_doctype"),
        {"comment": "Trust-Level Konfiguration für autonome KI-Aktionen"}
    )

    def __repr__(self) -> str:
        return f"<AutonomousTrustConfig company={self.company_id} level={self.trust_level} doc_type={self.document_type}>"


class AutonomousProposalQueue(Base):
    """Queue für verzögerte Auto-Akzeptanz.

    Speichert Vorschläge, die nicht sofort ausgeführt werden:
    - Level 2: 24h Wartezeit bei >90% Confidence
    - Level 3: 4h Wartezeit bei 80-95% Confidence

    Features:
    - Timeout-Handling mit automatischer Ausführung
    - User-Intervention (vorzeitige Genehmigung/Ablehnung)
    - Rollback-Fähigkeit für 7 Tage
    """
    __tablename__ = "autonomous_proposal_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Proposal Details
    proposal_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Typ: file_document, approve_payment, send_dunning, update_master_data, assign_entity, classify_document"
    )
    target_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="ID des Ziel-Objekts (Document, Invoice, Entity, etc.)"
    )
    proposed_value = Column(
        CrossDBJSON,
        nullable=False,
        comment="Vorgeschlagener Wert als JSON"
    )

    # Confidence und Timing
    confidence = Column(Float, nullable=False)
    delay_hours = Column(
        Integer,
        nullable=False,
        comment="Urspruengliche Verzögerung in Stunden"
    )
    scheduled_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Geplante Ausführungszeit"
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="pending, approved, rejected, auto_accepted, expired, rolled_back, cancelled"
    )

    # Ausführung
    executed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Ausführung"
    )
    executed_by = Column(
        String(100),
        nullable=True,
        comment="User-ID oder 'system' bei Auto-Accept"
    )

    # Rollback
    rollback_until = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Bis wann Rollback möglich ist"
    )

    # Referenzen
    ai_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_decisions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Referenz zur urspruenglichen AI-Decision"
    )
    reasoning = Column(
        Text,
        nullable=True,
        comment="Begruendung des Vorschlags"
    )
    proposal_metadata = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusätzliche Metadaten"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="autonomous_proposals")
    ai_decision = relationship("AIDecision", backref="proposal_queue_items")

    __table_args__ = (
        {"comment": "Queue für verzögerte Auto-Akzeptanz mit Rollback"}
    )

    def __repr__(self) -> str:
        return f"<AutonomousProposalQueue {self.proposal_type} status={self.status} conf={self.confidence:.2f}>"
