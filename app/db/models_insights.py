# -*- coding: utf-8 -*-
"""
Financial Insights database models for Ablage-System.

Ermöglicht Persistierung von:
- Cashflow-Prognosen
- Betrugs-Warnungen
- Skonto-Empfehlungen
- Proaktive Insights

Vision 2.0 Phase 2 - KI-Intelligenz

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
    Date,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# ENUMS
# =============================================================================


class InsightCategory(str, Enum):
    """Kategorie der Insight."""
    CASHFLOW = "cashflow"              # Liquiditaetsprognose
    FRAUD = "fraud"                    # Betrugserkennung
    SKONTO = "skonto"                  # Skonto-Optimierung
    RISK = "risk"                      # Risiko-Intelligence
    PAYMENT = "payment"                # Zahlungsverhalten
    SUPPLIER = "supplier"              # Lieferanten-Analyse
    SEASONAL = "seasonal"              # Saisonale Muster


class InsightSeverity(str, Enum):
    """Schweregrad der Insight."""
    INFO = "info"              # Informativ
    LOW = "low"                # Niedriger Handlungsbedarf
    MEDIUM = "medium"          # Mittlerer Handlungsbedarf
    HIGH = "high"              # Hoher Handlungsbedarf
    CRITICAL = "critical"      # Sofortige Aktion erforderlich


class InsightStatus(str, Enum):
    """Bearbeitungsstatus der Insight."""
    NEW = "new"                    # Neu
    ACKNOWLEDGED = "acknowledged"  # Zur Kenntnis genommen
    ACTED_UPON = "acted_upon"      # Aktion durchgeführt
    DISMISSED = "dismissed"        # Verworfen
    EXPIRED = "expired"            # Abgelaufen


class CashflowScenarioType(str, Enum):
    """Typ des Cashflow-Szenarios."""
    BASELINE = "baseline"          # Basisszenario
    OPTIMISTIC = "optimistic"      # Optimistisches Szenario
    PESSIMISTIC = "pessimistic"    # Pessimistisches Szenario
    CUSTOM = "custom"              # Benutzerdefiniert


class FraudAlertType(str, Enum):
    """Typ der Betrugswarnung."""
    DUPLICATE_INVOICE = "duplicate_invoice"      # Doppelte Rechnung
    PRICE_ANOMALY = "price_anomaly"              # Preisanomalie
    PHANTOM_SUPPLIER = "phantom_supplier"        # Fiktiver Lieferant
    UNUSUAL_PATTERN = "unusual_pattern"          # Ungewoehnliches Muster
    TIMING_ANOMALY = "timing_anomaly"            # Timing-Anomalie
    AMOUNT_DEVIATION = "amount_deviation"        # Betragsabweichung


class FraudAlertStatus(str, Enum):
    """Status der Betrugswarnung."""
    OPEN = "open"                  # Offen
    INVESTIGATING = "investigating"  # In Untersuchung
    CONFIRMED = "confirmed"        # Bestätigt (Betrug)
    FALSE_POSITIVE = "false_positive"  # Fehlalarm
    RESOLVED = "resolved"          # Geloest


# =============================================================================
# CASHFLOW MODELS
# =============================================================================


class CashflowPrediction(Base):
    """
    Cashflow-Prognose für einen bestimmten Zeitraum.

    Speichert die täglichen Prognosen für Liquiditaetsplanung
    mit verschiedenen Szenarien und Konfidenzintervallen.
    """
    __tablename__ = "cashflow_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Prognose-Identifikation
    prediction_date = Column(
        Date,
        nullable=False,
        comment="Datum für das die Prognose gilt"
    )
    scenario_type = Column(
        String(30),
        nullable=False,
        default=CashflowScenarioType.BASELINE.value
    )

    # Prognosewerte
    predicted_inflow = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Erwartete Einzahlungen"
    )
    predicted_outflow = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Erwartete Auszahlungen"
    )
    predicted_balance = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Erwarteter Saldo am Ende des Tages"
    )

    # Konfidenzintervall
    confidence_low = Column(
        Float,
        nullable=True,
        comment="Untere Konfidenzgrenze"
    )
    confidence_high = Column(
        Float,
        nullable=True,
        comment="Obere Konfidenzgrenze"
    )
    confidence_level = Column(
        Float,
        nullable=True,
        default=0.95,
        comment="Konfidenzniveau (z.B. 0.95 für 95%)"
    )

    # Modell-Metadaten
    model_version = Column(
        String(50),
        nullable=True,
        comment="Version des Prognosemodells"
    )
    features_used = Column(
        CrossDBJSON,
        nullable=True,
        comment="Verwendete Features/Faktoren"
    )
    accuracy_metrics = Column(
        CrossDBJSON,
        nullable=True,
        comment="Genauigkeitsmetriken des Modells"
    )

    # Detailaufschluesselung
    inflow_breakdown = Column(
        CrossDBJSON,
        nullable=True,
        comment="Aufschluesselung der Einzahlungen nach Kategorie"
    )
    outflow_breakdown = Column(
        CrossDBJSON,
        nullable=True,
        comment="Aufschluesselung der Auszahlungen nach Kategorie"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", backref="cashflow_predictions")

    __table_args__ = (
        Index(
            "ix_cashflow_pred_company_date",
            "company_id",
            "prediction_date",
            "scenario_type",
            unique=True
        ),
        Index("ix_cashflow_pred_date_range", "prediction_date"),
        CheckConstraint(
            "scenario_type IN ('baseline', 'optimistic', 'pessimistic', 'custom')",
            name="ck_cashflow_scenario_type"
        ),
        {"comment": "Cashflow-Prognosen für Liquiditaetsplanung"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "prediction_date": self.prediction_date.isoformat() if self.prediction_date else None,
            "scenario_type": self.scenario_type,
            "predicted_inflow": self.predicted_inflow,
            "predicted_outflow": self.predicted_outflow,
            "predicted_balance": self.predicted_balance,
            "confidence_low": self.confidence_low,
            "confidence_high": self.confidence_high,
            "confidence_level": self.confidence_level,
            "model_version": self.model_version,
            "inflow_breakdown": self.inflow_breakdown,
            "outflow_breakdown": self.outflow_breakdown,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# FRAUD DETECTION MODELS
# =============================================================================


class FraudAlert(Base):
    """
    Betrugs-Warnung aus der Anomalieerkennung.

    Speichert erkannte Auffälligkeiten mit Details
    zur Untersuchung und Nachverfolgung.
    """
    __tablename__ = "fraud_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Alert-Klassifikation
    alert_type = Column(
        String(50),
        nullable=False,
        index=True
    )
    severity = Column(
        String(20),
        nullable=False,
        default=InsightSeverity.MEDIUM.value
    )
    status = Column(
        String(30),
        nullable=False,
        default=FraudAlertStatus.OPEN.value
    )

    # Alert-Details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    risk_score = Column(
        Float,
        nullable=True,
        comment="Risiko-Score (0.0-1.0)"
    )
    confidence = Column(
        Float,
        nullable=True,
        comment="Konfidenz der Erkennung (0.0-1.0)"
    )

    # Betroffene Entitäten
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    invoice_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="ID der betroffenen Rechnung"
    )

    # Evidenz und Kontext
    evidence = Column(
        CrossDBJSON,
        nullable=True,
        comment="Beweismaterial (Dokumente, Transaktionen)"
    )
    anomaly_details = Column(
        CrossDBJSON,
        nullable=True,
        comment="Details zur erkannten Anomalie"
    )
    similar_cases = Column(
        CrossDBJSON,
        nullable=True,
        comment="Referenzen zu ähnlichen Faellen"
    )
    recommended_actions = Column(
        CrossDBJSON,
        nullable=True,
        comment="Empfohlene Aktionen"
    )

    # Bearbeitung
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    investigation_notes = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Timestamps
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", backref="fraud_alerts")
    document = relationship("Document", backref="fraud_alerts")
    assigned_to = relationship(
        "User",
        foreign_keys=[assigned_to_id],
        backref="assigned_fraud_alerts"
    )
    resolved_by = relationship(
        "User",
        foreign_keys=[resolved_by_id]
    )

    __table_args__ = (
        Index("ix_fraud_alert_company_status", "company_id", "status"),
        Index("ix_fraud_alert_type_severity", "alert_type", "severity"),
        Index("ix_fraud_alert_detected", "detected_at"),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_fraud_alert_severity"
        ),
        CheckConstraint(
            "status IN ('open', 'investigating', 'confirmed', 'false_positive', 'resolved')",
            name="ck_fraud_alert_status"
        ),
        {"comment": "Betrugs-Warnungen aus Anomalieerkennung"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "alert_type": self.alert_type,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "document_id": str(self.document_id) if self.document_id else None,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "evidence": self.evidence,
            "anomaly_details": self.anomaly_details,
            "recommended_actions": self.recommended_actions,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


# =============================================================================
# SKONTO RECOMMENDATION MODELS
# =============================================================================


class SkontoRecommendation(Base):
    """
    Skonto-Empfehlung basierend auf Analyse.

    Speichert Empfehlungen zur optimalen Skonto-Nutzung
    mit ROI-Berechnung und Liquiditaetsauswirkung.
    """
    __tablename__ = "skonto_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Betroffene Rechnung
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="ID des InvoiceTracking-Eintrags"
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Empfehlungsdetails
    recommendation = Column(
        String(50),
        nullable=False,
        comment="use_skonto, skip_skonto, partial_payment"
    )
    priority = Column(
        String(20),
        nullable=False,
        default="medium",
        comment="Priorität: high, medium, low"
    )

    # Finanzielle Details
    invoice_amount = Column(Float, nullable=False)
    skonto_percentage = Column(Float, nullable=False)
    skonto_amount = Column(
        Float,
        nullable=False,
        comment="Einsparung durch Skonto"
    )
    skonto_deadline = Column(Date, nullable=False)
    days_until_deadline = Column(Integer, nullable=False)

    # ROI-Berechnung
    annualized_return = Column(
        Float,
        nullable=True,
        comment="Annualisierte Rendite des Skontos"
    )
    opportunity_cost = Column(
        Float,
        nullable=True,
        comment="Opportunitaetskosten bei Nicht-Nutzung"
    )

    # Liquiditaetsauswirkung
    liquidity_impact = Column(
        Float,
        nullable=True,
        comment="Auswirkung auf verfügbare Liquiditaet"
    )
    cash_available = Column(
        Float,
        nullable=True,
        comment="Verfügbare Liquiditaet zum Zeitpunkt"
    )
    liquidity_buffer_after = Column(
        Float,
        nullable=True,
        comment="Liquiditaetspuffer nach Zahlung"
    )

    # Begruendung
    reasoning = Column(
        Text,
        nullable=True,
        comment="Ausführliche Begruendung der Empfehlung"
    )
    factors = Column(
        CrossDBJSON,
        nullable=True,
        comment="Einflussfaktoren der Entscheidung"
    )

    # Status
    status = Column(
        String(30),
        nullable=False,
        default=InsightStatus.NEW.value
    )
    acted_upon = Column(Boolean, nullable=False, default=False)
    action_taken = Column(
        String(50),
        nullable=True,
        comment="Tatsaechlich durchgeführte Aktion"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Gültig bis (= Skonto-Deadline)"
    )
    acted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", backref="skonto_recommendations")

    __table_args__ = (
        Index("ix_skonto_rec_company_status", "company_id", "status"),
        Index("ix_skonto_rec_deadline", "skonto_deadline"),
        Index("ix_skonto_rec_priority", "priority"),
        Index("ix_skonto_rec_invoice", "invoice_tracking_id"),
        CheckConstraint(
            "status IN ('new', 'acknowledged', 'acted_upon', 'dismissed', 'expired')",
            name="ck_skonto_rec_status"
        ),
        CheckConstraint(
            "priority IN ('high', 'medium', 'low')",
            name="ck_skonto_rec_priority"
        ),
        {"comment": "Skonto-Optimierungsempfehlungen"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "invoice_tracking_id": str(self.invoice_tracking_id),
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "recommendation": self.recommendation,
            "priority": self.priority,
            "invoice_amount": self.invoice_amount,
            "skonto_percentage": self.skonto_percentage,
            "skonto_amount": self.skonto_amount,
            "skonto_deadline": self.skonto_deadline.isoformat() if self.skonto_deadline else None,
            "days_until_deadline": self.days_until_deadline,
            "annualized_return": self.annualized_return,
            "opportunity_cost": self.opportunity_cost,
            "liquidity_impact": self.liquidity_impact,
            "reasoning": self.reasoning,
            "factors": self.factors,
            "status": self.status,
            "acted_upon": self.acted_upon,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


# =============================================================================
# PROACTIVE INSIGHTS MODEL
# =============================================================================


class ProactiveInsight(Base):
    """
    Generische proaktive Insight.

    Speichert verschiedene Arten von Insights die
    dem Benutzer proaktiv angezeigt werden sollen.
    """
    __tablename__ = "proactive_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Für benutzer-spezifische Insights"
    )

    # Insight-Klassifikation
    category = Column(
        String(30),
        nullable=False,
        index=True
    )
    insight_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Spezifischer Insight-Typ"
    )
    severity = Column(
        String(20),
        nullable=False,
        default=InsightSeverity.INFO.value
    )
    status = Column(
        String(30),
        nullable=False,
        default=InsightStatus.NEW.value
    )

    # Inhalt
    title = Column(String(255), nullable=False)
    summary = Column(String(500), nullable=False)
    details = Column(Text, nullable=True)
    icon = Column(
        String(50),
        nullable=True,
        comment="Icon-Name für UI"
    )

    # Kontextdaten
    context_data = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusätzliche Daten für Rendering"
    )
    related_entities = Column(
        CrossDBJSON,
        nullable=True,
        comment="Betroffene Entitäten (Dokumente, Kunden, etc.)"
    )
    metrics = Column(
        CrossDBJSON,
        nullable=True,
        comment="Quantitative Metriken"
    )

    # Aktionen
    suggested_actions = Column(
        CrossDBJSON,
        nullable=True,
        comment="Vorgeschlagene Aktionen"
    )
    action_url = Column(
        String(255),
        nullable=True,
        comment="URL zur direkten Aktion"
    )

    # Zeitbezug
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Gültig bis (null = unbegrenzt)"
    )
    recurrence_key = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Schluessel für wiederkehrende Insights"
    )

    # Interaktion
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    acted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", backref="proactive_insights")
    user = relationship("User", backref="proactive_insights")

    __table_args__ = (
        Index("ix_insight_company_status", "company_id", "status"),
        Index("ix_insight_category_type", "category", "insight_type"),
        Index("ix_insight_valid_range", "valid_from", "valid_until"),
        Index("ix_insight_recurrence", "recurrence_key"),
        CheckConstraint(
            "category IN ('cashflow', 'fraud', 'skonto', 'risk', 'payment', 'supplier', 'seasonal')",
            name="ck_insight_category"
        ),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_insight_severity"
        ),
        CheckConstraint(
            "status IN ('new', 'acknowledged', 'acted_upon', 'dismissed', 'expired')",
            name="ck_insight_status"
        ),
        {"comment": "Proaktive Insights für Benutzer"}
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "category": self.category,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "icon": self.icon,
            "context_data": self.context_data,
            "related_entities": self.related_entities,
            "metrics": self.metrics,
            "suggested_actions": self.suggested_actions,
            "action_url": self.action_url,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
