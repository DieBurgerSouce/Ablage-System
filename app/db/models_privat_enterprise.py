"""Privat Enterprise Modelle (KPI, Goals, Approvals) - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime, date
from enum import Enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Index, Date, func, UniqueConstraint, Numeric, CheckConstraint, text, Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship, backref
from app.db.models_base import Base, CrossDBJSON


# =============================================================================
# ENTERPRISE INTELLIGENCE SYSTEM
# Phase 4: LLM Cache, Event Log, Recurring Payments, Coverage Gaps
# =============================================================================

class RecurringPaymentFrequency(str, Enum):
    """Häufigkeit wiederkehrender Zahlungen."""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    YEARLY = "yearly"


class RecurringPaymentCategory(str, Enum):
    """Kategorie wiederkehrender Zahlungen."""
    SUBSCRIPTION = "subscription"
    UTILITY = "utility"
    RENT = "rent"
    INSURANCE = "insurance"
    LOAN = "loan"
    SAVINGS = "savings"
    SALARY = "salary"
    OTHER = "other"


class CoverageGapType(str, Enum):
    """Typ der Versicherungslücke."""
    MISSING = "missing"
    UNDERCOVERED = "undercovered"
    EXPIRED = "expired"
    OVERLAPPING = "overlapping"


class CoverageGapSeverity(str, Enum):
    """Schweregrad der Versicherungslücke."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LLMCache(Base):
    """Semantisches Caching für LLM-Antworten.

    Reduziert LLM-Aufrufe durch Wiederverwendung ähnlicher Antworten.
    Nutzt Embedding-basierte Ähnlichkeitssuche.
    """

    __tablename__ = "llm_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_hash = Column(String(64), nullable=False, unique=True, index=True,
                         comment="SHA-256 Hash des normalisierten Prompts")
    prompt_text = Column(Text, nullable=False, comment="Originaler Prompt-Text")
    prompt_embedding = Column(CrossDBJSON, nullable=True,
                              comment="Embedding-Vektor für semantische Suche")
    response = Column(Text, nullable=False, comment="LLM-Antwort")
    model = Column(String(50), nullable=False, index=True,
                   comment="Verwendetes Modell")
    model_version = Column(String(50), nullable=True, comment="Modell-Version")
    temperature = Column(Numeric(3, 2), nullable=True, comment="Verwendete Temperature")
    hit_count = Column(Integer, nullable=False, default=0, comment="Anzahl Cache-Hits")
    last_hit_at = Column(DateTime(timezone=True), nullable=True,
                         comment="Zeitpunkt des letzten Hits")
    token_count_prompt = Column(Integer, nullable=True, comment="Token-Anzahl im Prompt")
    token_count_response = Column(Integer, nullable=True,
                                  comment="Token-Anzahl in der Antwort")
    latency_ms = Column(Integer, nullable=True,
                        comment="Original-Antwortzeit in Millisekunden")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Ablaufzeitpunkt")
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusätzliche Metadaten")

    __table_args__ = (
        Index("ix_llm_cache_created_at", "created_at"),
        Index("ix_llm_cache_expires_at", "expires_at"),
        Index("ix_llm_cache_hit_count", "hit_count"),
        {"comment": "Semantisches LLM-Antwort-Caching"}
    )


class EventLog(Base):
    """Event Log für Event Bus Historie.

    Persistiert alle Events für Audit, Replay und Debugging.
    """

    __tablename__ = "event_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True,
                      comment="Eindeutige Event-ID")
    event_type = Column(String(100), nullable=False, index=True,
                        comment="Event-Typ")
    source = Column(String(100), nullable=False, index=True,
                    comment="Quelle des Events")
    correlation_id = Column(UUID(as_uuid=True), nullable=True,
                            comment="Korrelations-ID")
    user_id = Column(UUID(as_uuid=True), nullable=True,
                     comment="Benutzer-ID")
    space_id = Column(UUID(as_uuid=True), nullable=True,
                      comment="Privat-Space-ID")
    payload = Column(CrossDBJSON, nullable=False, comment="Event-Payload")
    processed = Column(Boolean, nullable=False, default=False,
                       comment="Wurde verarbeitet?")
    processed_at = Column(DateTime(timezone=True), nullable=True,
                          comment="Verarbeitungszeitpunkt")
    handler_count = Column(Integer, nullable=False, default=0,
                           comment="Anzahl Handler")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_event_log_correlation_id", "correlation_id"),
        Index("ix_event_log_user_id", "user_id"),
        Index("ix_event_log_space_id", "space_id"),
        Index("ix_event_log_created_at", "created_at"),
        Index("ix_event_log_unprocessed", "event_type", "created_at",
              postgresql_where=text("processed = false")),
        {"comment": "Event Bus Historie für Audit und Replay"}
    )


class PrivatRecurringPayment(Base):
    """Erkannte wiederkehrende Zahlungen.

    Automatisch erkannte oder manuell definierte regelmäßige Zahlungen
    für Cashflow-Prognosen und Anomalie-Erkennung.
    """

    __tablename__ = "privat_recurring_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    name = Column(String(255), nullable=False, comment="Name der Zahlung")
    payee = Column(String(255), nullable=True, comment="Zahlungsempfänger")
    expected_amount = Column(Numeric(10, 2), nullable=False,
                             comment="Erwarteter Betrag")
    amount_variance = Column(Numeric(10, 2), nullable=True,
                             comment="Tolerierte Abweichung")
    frequency = Column(String(20), nullable=False, index=True,
                       comment="Häufigkeit")
    expected_day = Column(Integer, nullable=True,
                          comment="Erwarteter Tag im Zyklus")
    category = Column(String(50), nullable=True, index=True,
                      comment="Kategorie")
    last_occurrence = Column(Date, nullable=True, comment="Letztes Auftreten")
    next_expected = Column(Date, nullable=True, comment="Nächstes erwartetes Datum")
    occurrence_count = Column(Integer, nullable=False, default=0,
                              comment="Anzahl Vorkommen")
    confidence = Column(Numeric(3, 2), nullable=False, default=0.0,
                        comment="Erkennungs-Konfidenz")
    is_active = Column(Boolean, nullable=False, default=True,
                       comment="Ist aktiv?")
    is_income = Column(Boolean, nullable=False, default=False,
                       comment="Ist Einnahme?")
    linked_account_id = Column(UUID(as_uuid=True), nullable=True,
                               comment="Verknüpftes Bankkonto")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusätzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="recurring_payments")

    __table_args__ = (
        Index("ix_recurring_payments_next_expected", "next_expected"),
        Index("ix_recurring_payments_confidence", "confidence"),
        {"comment": "Erkannte wiederkehrende Zahlungen"}
    )


class PrivatCoverageGap(Base):
    """Versicherungslücken-Analyse.

    Identifizierte Deckungslücken mit Empfehlungen.
    """

    __tablename__ = "privat_coverage_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    insurance_id = Column(UUID(as_uuid=True),
                          ForeignKey("privat_insurances.id", ondelete="SET NULL"),
                          nullable=True, comment="Referenz auf Versicherung")
    insurance_type = Column(String(50), nullable=False, index=True,
                            comment="Versicherungstyp")
    gap_type = Column(String(50), nullable=False,
                      comment="Lückentyp")
    recommended_coverage = Column(Numeric(15, 2), nullable=True,
                                  comment="Empfohlene Deckungssumme")
    current_coverage = Column(Numeric(15, 2), nullable=True,
                              comment="Aktuelle Deckungssumme")
    gap_amount = Column(Numeric(15, 2), nullable=True,
                        comment="Differenz zur Empfehlung")
    severity = Column(String(20), nullable=False, index=True,
                      comment="Schweregrad")
    risk_description = Column(Text, nullable=True,
                              comment="Risikobeschreibung")
    recommendation = Column(Text, nullable=True,
                            comment="Handlungsempfehlung")
    estimated_monthly_cost = Column(Numeric(10, 2), nullable=True,
                                    comment="Geschätzte Monatskosten")
    priority_score = Column(Integer, nullable=True,
                            comment="Prioritäts-Score 1-100")
    is_resolved = Column(Boolean, nullable=False, default=False,
                         comment="Behoben?")
    resolved_at = Column(DateTime(timezone=True), nullable=True,
                         comment="Behebungszeitpunkt")
    last_analysis_at = Column(DateTime(timezone=True), server_default=func.now(),
                              nullable=False, comment="Letzte Analyse")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusätzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="coverage_gaps")
    insurance = relationship("PrivatInsurance", back_populates="coverage_gaps")

    __table_args__ = (
        Index("ix_coverage_gaps_unresolved", "space_id", "severity",
              postgresql_where=text("is_resolved = false")),
        Index("ix_coverage_gaps_priority", "priority_score"),
        {"comment": "Versicherungslücken-Analyse"}
    )


# =============================================================================
# PREDICTIVE INTELLIGENCE: KPI History, Projections, Early Warnings
# =============================================================================


class KPIUnit(str, Enum):
    """Einheit für KPIs."""
    PERCENT = "percent"
    CURRENCY = "currency"
    RATIO = "ratio"
    SCORE = "score"
    MONTHS = "months"
    COUNT = "count"
    NUMBER = "number"
    DAYS = "days"
    YEARS = "years"


class ProjectionMethod(str, Enum):
    """Methode für KPI-Projektionen."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    SEASONAL = "seasonal"
    ENSEMBLE = "ensemble"


class TrendDirection(str, Enum):
    """Trendrichtung."""
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    VOLATILE = "volatile"


class WarningSeverity(str, Enum):
    """Schweregrad von Early Warnings."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class WarningType(str, Enum):
    """Typ der Early Warning."""
    THRESHOLD_BREACH = "threshold_breach"
    TREND_REVERSAL = "trend_reversal"
    VOLATILITY_SPIKE = "volatility_spike"
    SEASONAL_ANOMALY = "seasonal_anomaly"
    GOAL_AT_RISK = "goal_at_risk"


class ProfessionType(str, Enum):
    """Berufstypen für personalisierte Schwellenwerte."""
    EMPLOYEE = "employee"
    CIVIL_SERVANT = "civil_servant"
    FREELANCER = "freelancer"
    ENTREPRENEUR = "entrepreneur"
    RETIREE = "retiree"


class RiskProfile(str, Enum):
    """Risikoprofil des Users."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class PrivatKPIHistory(Base):
    """KPI History - Tägliche Snapshots aller KPIs für Trend-Analyse.

    Ermöglicht die Projektion von KPIs in die Zukunft basierend auf
    historischen Trends. Ein Eintrag pro KPI pro Space pro Tag.
    """

    __tablename__ = "privat_kpi_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    kpi_name = Column(String(100), nullable=False, index=True,
                      comment="Name des KPI (z.B. dti, financial_health_score)")
    kpi_value = Column(Numeric(15, 4), nullable=False, comment="Numerischer Wert")
    kpi_unit = Column(String(20), nullable=True,
                      comment="Einheit: percent, currency, ratio, score")
    components = Column(CrossDBJSON, nullable=True,
                        comment="Aufschluesselung in Komponenten")
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False,
                         comment="Zeitpunkt der Aufzeichnung")
    source = Column(String(50), nullable=False, default="automated",
                    comment="Quelle: automated, manual, recalculated")
    extra_data = Column(CrossDBJSON, nullable=True,
                        comment="Zusätzliche Kontextdaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="kpi_history")

    __table_args__ = (
        Index("ix_kpi_history_space_kpi", "space_id", "kpi_name", "recorded_at"),
        Index("ix_kpi_history_recorded_at", "recorded_at"),
        # Note: UniqueConstraint auf space_id + kpi_name + recorded_at (Tag-Ebene wird in Migration gehandhabt)
        UniqueConstraint("space_id", "kpi_name", "recorded_at",
                         name="uq_kpi_history_space_kpi_date"),
        {"comment": "Tägliche KPI-Snapshots für Trend-Analyse"}
    )


class PrivatProjection(Base):
    """KPI Projections Cache - Vorausberechnete Prognosen.

    Gecachte Projektionen für 3/6/12 Monate in die Zukunft.
    Werden täglich neu berechnet und invalidiert.
    """

    __tablename__ = "privat_projections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    kpi_name = Column(String(100), nullable=False, index=True,
                      comment="Name des projizierten KPI")
    projection_months = Column(Integer, nullable=False,
                               comment="Projektionszeitraum in Monaten (3, 6, 12)")
    projection_method = Column(String(50), nullable=False, default=ProjectionMethod.LINEAR.value,
                               comment="Methode: linear, exponential, seasonal, ensemble")
    current_value = Column(Numeric(15, 4), nullable=False,
                           comment="Aktueller Wert zum Berechnungszeitpunkt")
    projected_values = Column(CrossDBJSON, nullable=False,
                              comment="Monatliche Projektionen: [{month, value, confidence}]")
    threshold_breaches = Column(CrossDBJSON, nullable=True,
                                comment="Erkannte zukuenftige Schwellenwertbrueche")
    trend_direction = Column(String(20), nullable=False,
                             comment="Trendrichtung: rising, falling, stable, volatile")
    trend_strength = Column(Numeric(5, 4), nullable=True,
                            comment="Trendstärke 0-1 (R-squared)")
    seasonality_detected = Column(Boolean, nullable=False, default=False,
                                  comment="Wurde Saisonalitaet erkannt?")
    confidence_overall = Column(Numeric(3, 2), nullable=False,
                                comment="Gesamt-Konfidenz 0-1")
    data_points_used = Column(Integer, nullable=False,
                              comment="Anzahl historischer Datenpunkte")
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False,
                           comment="Zeitpunkt der Berechnung")
    valid_until = Column(DateTime(timezone=True), nullable=False,
                         comment="Gültig bis")
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusätzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="projections")
    early_warnings = relationship("PrivatEarlyWarning", back_populates="projection",
                                  cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("space_id", "kpi_name", "projection_months",
                         name="uq_projections_space_kpi_months"),
        Index("ix_projections_valid_until", "valid_until"),
        Index("ix_projections_with_breaches", "space_id",
              postgresql_where=text("threshold_breaches IS NOT NULL")),
        {"comment": "Vorausberechnete KPI-Projektionen"}
    )

    @property
    def is_valid(self) -> bool:
        """Prüft ob Projektion noch gültig ist."""
        from datetime import datetime, timezone
        return self.valid_until > datetime.now(timezone.utc)


class PrivatEarlyWarning(Base):
    """Early Warnings - Proaktive Warnungen bei zukuenftigen Problemen.

    Speichert erkannte zukuenftige Schwellenwert-Verletzungen mit
    Empfehlungen und Zeitrahmen. Kern des PROAKTIVEN Systems.
    """

    __tablename__ = "privat_early_warnings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    projection_id = Column(UUID(as_uuid=True),
                           ForeignKey("privat_projections.id", ondelete="SET NULL"),
                           nullable=True, comment="Zugrundeliegende Projektion")
    kpi_name = Column(String(100), nullable=False, index=True,
                      comment="Betroffener KPI")
    warning_type = Column(String(50), nullable=False,
                          comment="Typ: threshold_breach, trend_reversal, etc.")
    severity = Column(String(20), nullable=False, index=True,
                      comment="Schweregrad: info, warning, critical")
    current_value = Column(Numeric(15, 4), nullable=False,
                           comment="Aktueller Wert")
    projected_value = Column(Numeric(15, 4), nullable=False,
                             comment="Projizierter Wert zum Breach-Zeitpunkt")
    threshold_value = Column(Numeric(15, 4), nullable=True,
                             comment="Schwellenwert der überschritten wird")
    threshold_name = Column(String(100), nullable=True,
                            comment="Name des Schwellenwerts")
    breach_date = Column(Date, nullable=False, index=True,
                         comment="Prognostiziertes Datum der Verletzung")
    days_until_breach = Column(Integer, nullable=False,
                               comment="Tage bis zur Verletzung")
    title = Column(String(255), nullable=False,
                   comment="Titel der Warnung (deutsch)")
    description = Column(Text, nullable=True,
                         comment="Detaillierte Beschreibung")
    recommendation = Column(Text, nullable=True,
                            comment="Handlungsempfehlung")
    potential_impact = Column(Numeric(15, 2), nullable=True,
                              comment="Geschätzter finanzieller Impact")
    action_url = Column(String(255), nullable=True,
                        comment="Link zur entsprechenden Aktion")
    confidence = Column(Numeric(3, 2), nullable=False,
                        comment="Konfidenz der Warnung 0-1")
    is_dismissed = Column(Boolean, nullable=False, default=False,
                          comment="Wurde die Warnung verworfen?")
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_reason = Column(Text, nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False,
                         comment="Wurde das Problem behoben?")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Warnung verfaellt")
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusätzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="early_warnings")
    projection = relationship("PrivatProjection", back_populates="early_warnings")

    __table_args__ = (
        Index("ix_early_warnings_active", "space_id", "severity", "breach_date",
              postgresql_where=text("is_dismissed = false AND is_resolved = false")),
        Index("ix_early_warnings_days_until", "days_until_breach",
              postgresql_where=text("is_dismissed = false AND is_resolved = false")),
        {"comment": "Proaktive Warnungen bei zukuenftigen Problemen"}
    )

    @property
    def is_active(self) -> bool:
        """Prüft ob die Warnung aktiv ist."""
        return not self.is_dismissed and not self.is_resolved


class PrivatTask(Base):
    """Orchestrator-Tasks - Aufgaben aus der Cross-Module-Orchestrierung.

    Generische Tasks die vom CrossModuleOrchestrator erstellt werden,
    wenn automatische Aktionen Benutzereingriff erfordern oder
    manuelle Follow-Ups notwendig sind.
    """

    __tablename__ = "privat_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True, comment="Zugewiesener Benutzer")

    # Task-Identifikation
    task_type = Column(String(50), nullable=False, index=True,
                       comment="Typ: review, action, follow_up, reminder, approval")
    title = Column(String(255), nullable=False,
                   comment="Kurzer Titel der Aufgabe")
    description = Column(Text, nullable=True,
                         comment="Ausführliche Beschreibung")
    category = Column(String(50), nullable=True, index=True,
                      comment="Kategorie: financial, insurance, property, loan, general")

    # Priorität und Dringlichkeit
    priority = Column(String(20), nullable=False, default="medium",
                      comment="Priorität: low, medium, high, critical")
    due_date = Column(DateTime(timezone=True), nullable=True,
                      comment="Fälligkeitsdatum")

    # Herkunft aus Orchestration
    source_action_id = Column(UUID(as_uuid=True), nullable=True,
                              comment="ID der ausloesenden OrchestrationAction")
    source_reason = Column(Text, nullable=True,
                           comment="Grund für Task-Erstellung")
    source_module = Column(String(50), nullable=True,
                           comment="Ausloesendes Modul: financial_health, insurance, loan, etc.")

    # Status-Tracking
    status = Column(String(30), nullable=False, default="pending",
                    comment="Status: pending, in_progress, completed, cancelled, snoozed")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_reason = Column(Text, nullable=True)

    # Snooze-Funktion (wie bei MahnTask)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    snooze_count = Column(Integer, default=0)
    snooze_reason = Column(String(255), nullable=True)

    # Ergebnis
    result_notes = Column(Text, nullable=True,
                          comment="Notizen nach Abschluss")
    result_action_taken = Column(String(100), nullable=True,
                                 comment="Getroffene Massnahme")

    # Verknüpfte Entitäten
    related_entity_type = Column(String(50), nullable=True,
                                 comment="Typ der verknüpften Entität: property, loan, insurance")
    related_entity_id = Column(UUID(as_uuid=True), nullable=True,
                               comment="ID der verknüpften Entität")

    # Metadaten
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    extra_data = Column(CrossDBJSON, nullable=True,
                        comment="Zusätzliche Metadaten vom Orchestrator")

    # Relationships
    space = relationship("PrivatSpace", back_populates="tasks")
    user = relationship("User", backref="privat_tasks")

    __table_args__ = (
        Index("ix_privat_tasks_pending", "user_id", "status", "priority",
              postgresql_where=text("status IN ('pending', 'in_progress')")),
        Index("ix_privat_tasks_due", "due_date",
              postgresql_where=text("status = 'pending'")),
        Index("ix_privat_tasks_source", "source_action_id"),
        CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'cancelled', 'snoozed')",
                        name="chk_privat_task_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')",
                        name="chk_privat_task_priority"),
        {"comment": "Orchestrator-generierte Tasks für Benutzeraktionen"}
    )

    @property
    def is_overdue(self) -> bool:
        """Prüft ob Task überfällig ist."""
        from datetime import datetime, timezone
        if self.due_date and self.status in ("pending", "in_progress"):
            return self.due_date < datetime.now(timezone.utc)
        return False

    @property
    def is_snoozed(self) -> bool:
        """Prüft ob Task zur Zeit snoozt."""
        from datetime import datetime, timezone
        if self.snoozed_until and self.status == "snoozed":
            return self.snoozed_until > datetime.now(timezone.utc)
        return False


# =============================================================================
# PORTFOLIO SNAPSHOT MODEL (Enterprise Feature)
# =============================================================================

class PortfolioSnapshot(Base):
    """Monatlicher Snapshot der Vermögensübersicht.

    Speichert aggregierte Vermögensstaende zu bestimmten Zeitpunkten
    für historische Analyse und Reporting.
    """
    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False, index=True, comment="Datum des Snapshots")

    # Vermögenswerte (Assets)
    total_real_estate = Column(Numeric(14, 2), nullable=False, default=0,
                               comment="Gesamtwert Immobilien")
    total_vehicles = Column(Numeric(14, 2), nullable=False, default=0,
                            comment="Gesamtwert Fahrzeuge")
    total_investments = Column(Numeric(14, 2), nullable=False, default=0,
                               comment="Gesamtwert Investments (Aktien, ETFs, Fonds)")
    total_cash = Column(Numeric(14, 2), nullable=False, default=0,
                        comment="Barvermoegen und Bankguthaben")
    total_other_assets = Column(Numeric(14, 2), nullable=False, default=0,
                                comment="Sonstige Vermögenswerte")

    # Verbindlichkeiten (Liabilities)
    total_mortgages = Column(Numeric(14, 2), nullable=False, default=0,
                             comment="Hypotheken und Immobilienkredite")
    total_loans = Column(Numeric(14, 2), nullable=False, default=0,
                         comment="Sonstige Kredite (Auto, Konsum)")
    total_other_liabilities = Column(Numeric(14, 2), nullable=False, default=0,
                                     comment="Sonstige Verbindlichkeiten")

    # Aggregierte Werte
    total_assets = Column(Numeric(14, 2), nullable=False, default=0,
                          comment="Summe aller Vermögenswerte")
    total_liabilities = Column(Numeric(14, 2), nullable=False, default=0,
                               comment="Summe aller Verbindlichkeiten")
    net_worth = Column(Numeric(14, 2), nullable=False, default=0,
                       comment="Nettovermoegen (Assets - Liabilities)")

    # Veränderungen zum Vormonat
    net_worth_change_absolute = Column(Numeric(14, 2), nullable=True,
                                       comment="Absolute Änderung zum Vormonat in EUR")
    net_worth_change_percent = Column(Numeric(8, 4), nullable=True,
                                      comment="Prozentuale Änderung zum Vormonat")

    # Kennzahlen
    debt_to_assets_ratio = Column(Numeric(8, 4), nullable=False, default=0,
                                  comment="Verschuldungsgrad (Liabilities/Assets)")
    liquidity_ratio = Column(Numeric(8, 4), nullable=False, default=0,
                             comment="Liquiditaetsquote (Cash/Liabilities)")

    # Asset Allocation als JSON
    asset_allocation = Column(CrossDBJSON, nullable=True,
                              comment="Vermögensverteilung als JSON (z.B. {'real_estate': 45, 'investments': 30, ...})")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    space = relationship("PrivatSpace", back_populates="portfolio_snapshots")

    __table_args__ = (
        Index("ix_portfolio_snapshots_space_date", "space_id", "snapshot_date"),
        UniqueConstraint("space_id", "snapshot_date", name="uq_portfolio_snapshot_space_date"),
        {"comment": "Monatliche Vermögenssnapshots für historische Analyse"}
    )

    @property
    def total_equity(self) -> float:
        """Eigenkapitalquote berechnen."""
        if self.total_assets and self.total_assets > 0:
            return float(self.net_worth / self.total_assets)
        return 0.0


# =============================================================================
# FINANCIAL GOAL MODEL (Enterprise Feature)
# =============================================================================

class FinancialGoalType(str, Enum):
    """Typ der finanziellen Ziele."""
    RETIREMENT = "retirement"           # Altersvorsorge
    EDUCATION = "education"             # Ausbildung/Studium
    PROPERTY_PURCHASE = "property"      # Immobilienkauf
    DEBT_FREE = "debt_free"             # Schuldenfreiheit
    EMERGENCY_FUND = "emergency_fund"   # Notgroschen
    TRAVEL = "travel"                   # Reisen
    VEHICLE = "vehicle"                 # Fahrzeugkauf
    RENOVATION = "renovation"           # Renovierung
    INVESTMENT = "investment"           # Investment-Ziel
    CUSTOM = "custom"                   # Benutzerdefiniert


class FinancialGoalStatus(str, Enum):
    """Status der finanziellen Ziele."""
    ACTIVE = "active"           # Aktiv - wird verfolgt
    PAUSED = "paused"           # Pausiert
    COMPLETED = "completed"     # Erreicht
    CANCELLED = "cancelled"     # Abgebrochen


class FinancialGoal(Base):
    """Finanzielle Ziele mit Progress-Tracking.

    Ermöglicht das Setzen von Sparzielen mit automatischer
    Fortschrittsverfolgung und Prognosen.
    """
    __tablename__ = "financial_goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)

    # Ziel-Definition
    name = Column(String(200), nullable=False, comment="Name des Ziels")
    description = Column(Text, nullable=True, comment="Beschreibung")
    goal_type = Column(String(50), nullable=False, default=FinancialGoalType.CUSTOM.value,
                       comment="Typ des Ziels")
    icon = Column(String(50), nullable=True, default="Target", comment="Icon für UI")
    color = Column(String(7), nullable=True, default="#10B981", comment="Farbe für UI")

    # Zielwerte
    target_value = Column(Numeric(14, 2), nullable=False, comment="Zielbetrag in EUR")
    target_date = Column(Date, nullable=False, comment="Zieldatum")

    # Tracking
    current_value = Column(Numeric(14, 2), nullable=False, default=0,
                           comment="Aktueller Betrag")
    progress_percent = Column(Numeric(8, 4), nullable=False, default=0,
                              comment="Fortschritt in Prozent (0-100)")

    # Berechnete/Prognostizierte Werte
    monthly_savings_required = Column(Numeric(12, 2), nullable=True,
                                      comment="Erforderliche monatliche Sparrate")
    months_remaining = Column(Integer, nullable=True,
                              comment="Verbleibende Monate bis Zieldatum")
    is_on_track = Column(Boolean, nullable=False, default=True,
                         comment="Liegt das Ziel im Plan?")
    projected_completion_date = Column(Date, nullable=True,
                                       comment="Prognostiziertes Erreichen basierend auf aktuellem Tempo")

    # Verknüpfte Assets (optional)
    linked_assets = Column(CrossDBJSON, nullable=True,
                           comment="Verknüpfte Assets als JSON (z.B. [{'type': 'investment', 'id': '...'}])")

    # Status und Priorität
    status = Column(String(20), nullable=False, default=FinancialGoalStatus.ACTIVE.value)
    priority = Column(Integer, nullable=False, default=1, comment="Priorität (1=hoechste)")

    # Automatische Aktualisierung
    auto_update_enabled = Column(Boolean, nullable=False, default=True,
                                 comment="Automatische Fortschrittsaktualisierung?")
    last_auto_update = Column(DateTime(timezone=True), nullable=True,
                              comment="Letzte automatische Aktualisierung")

    # Benachrichtigungen
    notify_on_milestone = Column(Boolean, nullable=False, default=True,
                                 comment="Benachrichtigung bei Meilensteinen?")
    notify_on_delay = Column(Boolean, nullable=False, default=True,
                             comment="Benachrichtigung bei Verzögerung?")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="Zeitpunkt der Zielerreichung")

    # Relationships
    space = relationship("PrivatSpace", back_populates="financial_goals")
    contributions = relationship("FinancialGoalContribution", back_populates="goal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_financial_goals_space", "space_id"),
        Index("ix_financial_goals_status", "status"),
        Index("ix_financial_goals_target_date", "target_date"),
        Index("ix_financial_goals_on_track", "is_on_track",
              postgresql_where=text("status = 'active'")),
        {"comment": "Finanzielle Ziele mit Progress-Tracking"}
    )

    @property
    def is_completed(self) -> bool:
        """Prüft ob Ziel erreicht wurde."""
        return self.status == FinancialGoalStatus.COMPLETED.value or \
               (self.current_value >= self.target_value if self.target_value else False)

    @property
    def is_overdue(self) -> bool:
        """Prüft ob Zieldatum überschritten."""
        from datetime import date
        return date.today() > self.target_date and not self.is_completed

    @property
    def remaining_amount(self) -> float:
        """Verbleibender Betrag bis zum Ziel."""
        return float(max(self.target_value - self.current_value, 0))


class FinancialGoalContribution(Base):
    """Beitraege/Einzahlungen zu einem Finanzziel.

    Trackt individuelle Beitraege zum Fortschritt eines Ziels.
    """
    __tablename__ = "financial_goal_contributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("financial_goals.id", ondelete="CASCADE"), nullable=False)

    # Beitrag
    amount = Column(Numeric(14, 2), nullable=False, comment="Beitragsbetrag in EUR")
    contribution_date = Column(Date, nullable=False, server_default=func.current_date(),
                               comment="Datum des Beitrags")

    # Quelle
    source_type = Column(String(50), nullable=True, comment="Quelle (manual, automatic, transfer)")
    source_description = Column(String(255), nullable=True, comment="Beschreibung der Quelle")

    # Verknüpfte Transaktion (optional)
    linked_transaction_id = Column(UUID(as_uuid=True), nullable=True,
                                   comment="Verknüpfte Transaktion falls automatisch")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Notes
    note = Column(Text, nullable=True, comment="Optionale Notiz")

    # Relationships
    goal = relationship("FinancialGoal", back_populates="contributions")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_goal_contributions_goal", "goal_id"),
        Index("ix_goal_contributions_date", "contribution_date"),
        {"comment": "Beitraege zu finanziellen Zielen"}
    )


# =============================================================================
# Approval System - Enterprise Genehmigungssystem
# =============================================================================

class ApprovalRuleType(str, Enum):
    """Typen von Approval-Regeln."""
    AMOUNT_THRESHOLD = "amount_threshold"  # Betragsschwelle
    CATEGORY = "category"  # Nach Kategorie
    SUPPLIER = "supplier"  # Nach Lieferant
    COST_CENTER = "cost_center"  # Nach Kostenstelle
    DOCUMENT_TYPE = "document_type"  # Nach Dokumenttyp
    RISK_LEVEL = "risk_level"  # Nach Risikostufe
    CUSTOM = "custom"  # Benutzerdefiniert


class ApprovalStatus(str, Enum):
    """Status einer Genehmigungsanfrage."""
    PENDING = "pending"  # Ausstehend
    APPROVED = "approved"  # Genehmigt
    REJECTED = "rejected"  # Abgelehnt
    ESCALATED = "escalated"  # Eskaliert
    EXPIRED = "expired"  # Abgelaufen
    CANCELLED = "cancelled"  # Storniert


class ApprovalPriority(str, Enum):
    """Priorität einer Genehmigung."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ApprovalRule(Base):
    """Regeln für automatisches Approval-Routing.

    Enterprise Feature: Definiert wann und wer genehmigen muss basierend auf:
    - Betragsschwellen
    - Kategorien/Kostenstellon
    - Lieferanten
    - Risikostufen
    """
    __tablename__ = "approval_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Regel-Definition
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(SQLAlchemyEnum(ApprovalRuleType), nullable=False, index=True)

    # Entitäts-Typen, auf die Regel angewendet wird
    entity_types = Column(CrossDBJSON, nullable=False, default=list)
    # z.B.: ["invoice", "expense", "purchase_order", "document"]

    # Bedingungen (JSON)
    conditions = Column(CrossDBJSON, nullable=False, default=dict)
    # Beispiele:
    # {"amount_greater_than": 5000, "amount_less_than": 50000}
    # {"category_in": ["IT", "Marketing"]}
    # {"supplier_risk_level": "high"}
    # {"cost_center_id": "uuid..."}

    # Genehmiger-Chain (JSON Array)
    approval_chain = Column(CrossDBJSON, nullable=False, default=list)
    # Beispiel: [
    #   {"step": 1, "type": "role", "value": "manager", "required": true},
    #   {"step": 2, "type": "user", "value": "uuid...", "required": true},
    #   {"step": 3, "type": "role", "value": "cfo", "required": false, "threshold": 10000}
    # ]

    # Eskalation
    escalation_after_hours = Column(Integer, nullable=True)
    escalation_to_role = Column(String(50), nullable=True)

    # SLA
    sla_hours = Column(Integer, nullable=True, default=48)  # Max. Bearbeitungszeit

    # Priorität und Reihenfolge
    priority = Column(Integer, default=100, nullable=False)  # Niedrig = Höhere Priorität
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", backref="approval_rules")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approval_requests = relationship("ApprovalRequest", back_populates="triggered_by_rule")

    __table_args__ = (
        Index("ix_approval_rules_company_active", "company_id", "is_active"),
        Index("ix_approval_rules_priority", "priority"),
        {"comment": "Regeln für automatisches Approval-Routing"}
    )


class ApprovalRequest(Base):
    """Genehmigungsanfrage mit Multi-Step Approval Chain.

    Enterprise Feature: Trackt den kompletten Genehmigungsprozess mit:
    - Multi-Level Genehmigungen
    - Eskalation bei Zeitüberschreitung
    - Vollständiger Audit Trail
    - Integration mit Workflows
    """
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Entität, die genehmigt werden soll
    entity_type = Column(String(50), nullable=False, index=True)
    # z.B.: "invoice", "expense", "document", "purchase_order", "contract"
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Optionale Workflow-Verknüpfung
    workflow_execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True)

    # Regel, die diese Anfrage ausgeloest hat
    triggered_by_rule_id = Column(UUID(as_uuid=True), ForeignKey("approval_rules.id", ondelete="SET NULL"), nullable=True)

    # Anfrage-Details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(14, 2), nullable=True)  # Betrag falls relevant
    currency = Column(String(3), default="EUR", nullable=False)

    # Status
    status = Column(SQLAlchemyEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False, index=True)
    priority = Column(SQLAlchemyEnum(ApprovalPriority), default=ApprovalPriority.NORMAL, nullable=False, index=True)

    # Approval Chain Fortschritt
    current_step = Column(Integer, default=1, nullable=False)
    total_steps = Column(Integer, nullable=False)
    approval_chain = Column(CrossDBJSON, nullable=False, default=list)
    # Kopie der Chain zum Zeitpunkt der Erstellung

    # SLA und Timing
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    escalation_date = Column(DateTime(timezone=True), nullable=True)
    is_escalated = Column(Boolean, default=False, nullable=False)

    # Ergebnis
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Wer hat die Anfrage erstellt
    requested_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Zusätzliche Daten
    request_metadata = Column(CrossDBJSON, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="approval_requests")
    workflow_execution = relationship("WorkflowExecution", backref="approval_requests")
    triggered_by_rule = relationship("ApprovalRule", back_populates="approval_requests")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approval_steps = relationship("ApprovalStep", back_populates="approval_request", cascade="all, delete-orphan", order_by="ApprovalStep.step_number")

    __table_args__ = (
        Index("ix_approval_requests_entity", "entity_type", "entity_id"),
        Index("ix_approval_requests_status", "company_id", "status"),
        Index("ix_approval_requests_due", "due_date"),
        {"comment": "Genehmigungsanfragen mit Multi-Step Chain"}
    )


class ApprovalStep(Base):
    """Einzelner Schritt im Genehmigungsprozess.

    Trackt jeden Genehmiger und seine Entscheidung.
    """
    __tablename__ = "approval_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_request_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)

    # Schritt-Nummer
    step_number = Column(Integer, nullable=False)

    # Genehmiger
    approver_type = Column(String(20), nullable=False)  # "user", "role", "group"
    approver_value = Column(String(255), nullable=False)  # User-ID, Rollenname, etc.
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Status dieses Schritts
    status = Column(SQLAlchemyEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False, index=True)
    is_required = Column(Boolean, default=True, nullable=False)

    # Entscheidung
    decision = Column(String(20), nullable=True)  # "approved", "rejected"
    decision_date = Column(DateTime(timezone=True), nullable=True)
    decision_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_notes = Column(Text, nullable=True)

    # Delegation
    delegated_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    delegated_at = Column(DateTime(timezone=True), nullable=True)
    delegation_reason = Column(Text, nullable=True)

    # Erinnerungen
    reminder_sent_count = Column(Integer, default=0, nullable=False)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    approval_request = relationship("ApprovalRequest", back_populates="approval_steps")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    decision_by = relationship("User", foreign_keys=[decision_by_id])
    delegated_to = relationship("User", foreign_keys=[delegated_to_id])

    __table_args__ = (
        Index("ix_approval_steps_request_number", "approval_request_id", "step_number"),
        Index("ix_approval_steps_assigned", "assigned_user_id", "status"),
        {"comment": "Einzelne Schritte im Genehmigungsprozess"}
    )


class ApprovalDelegation(Base):
    """Genehmigungsdelegation / Stellvertretung.

    Ermöglicht es Benutzern, ihre Genehmigungsrechte
    temporaer an Stellvertreter zu delegieren.
    """
    __tablename__ = "approval_delegations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Delegierender Benutzer
    delegator_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Stellvertreter
    delegate_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Zeitraum
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    reason = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    delegator = relationship("User", foreign_keys=[delegator_user_id])
    delegate = relationship("User", foreign_keys=[delegate_user_id])
    company = relationship("Company", backref="approval_delegations")

    __table_args__ = (
        Index("ix_approval_delegations_delegator_active", "delegator_user_id", "is_active"),
        {"comment": "Genehmigungsdelegation / Stellvertretung"}
    )


# =============================================================================
# Privat-Modul: Personalized Thresholds (Phase 0 Critical Fix)
# =============================================================================

class PrivatUserProfile(Base):
    """User-Profil für personalisierte Schwellenwert-Berechnung.

    Speichert Berufsprofil, Risikotoleranz und Praeferenzen
    für die automatische Anpassung von Schwellenwerten.
    """
    __tablename__ = "privat_user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Profession and Risk
    profession_type = Column(String(50), nullable=False, default="employee")
    risk_tolerance = Column(String(50), nullable=False, default="moderate")
    income_stability = Column(Numeric(3, 2), nullable=False, default=0.7)  # 0-1

    # Demographics
    age_group = Column(String(20), nullable=True)  # "18-30", "31-45", etc.
    household_size = Column(Integer, nullable=False, default=2)

    # Financial Situation
    has_dependents = Column(Boolean, nullable=False, default=False)
    is_homeowner = Column(Boolean, nullable=False, default=False)
    has_pension_plan = Column(Boolean, nullable=False, default=True)

    # Preferences
    prefers_aggressive_alerts = Column(Boolean, nullable=False, default=False)
    prefers_conservative_targets = Column(Boolean, nullable=False, default=True)

    # Learning data
    feedback_history = Column(CrossDBJSON, nullable=True, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref=backref("privat_profile", uselist=False))
    thresholds = relationship("PrivatUserThreshold", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "User-Profile für personalisierte Schwellenwerte (Privat-Modul)"}
    )


class PrivatUserThreshold(Base):
    """Personalisierter Schwellenwert für einen User.

    Speichert sowohl Default- als auch aktuellen Wert,
    sowie Tracking-Daten für Effektivitaetsmessung.
    """
    __tablename__ = "privat_user_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("privat_user_profiles.id", ondelete="CASCADE"), nullable=True, index=True)

    # Threshold identification
    threshold_type = Column(String(50), nullable=False)  # e.g., "dti_warning", "emergency_fund_min"

    # Values
    default_value = Column(Numeric(10, 4), nullable=False)
    current_value = Column(Numeric(10, 4), nullable=False)

    # Adjustment tracking
    adjustment_source = Column(String(50), nullable=False)  # system_default, user_preference, learned_behavior
    adjustment_reason = Column(Text, nullable=True)

    # Confidence and Effectiveness
    confidence = Column(Numeric(3, 2), nullable=False, default=0.7)  # 0-1
    times_triggered = Column(Integer, nullable=False, default=0)
    times_acted_on = Column(Integer, nullable=False, default=0)
    effectiveness_score = Column(Numeric(3, 2), nullable=False, default=1.0)  # 0-1

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    profile = relationship("PrivatUserProfile", back_populates="thresholds")

    __table_args__ = (
        UniqueConstraint("user_id", "threshold_type", name="uq_user_threshold_type"),
        Index("ix_user_thresholds_type", "threshold_type"),
        Index("ix_user_thresholds_user_type", "user_id", "threshold_type"),
        {"comment": "Personalisierte Schwellenwerte pro User (Privat-Modul)"}
    )


class PrivatThresholdAdjustment(Base):
    """Audit-Log für Schwellenwert-Anpassungen.

    Trackt alle Änderungen an Schwellenwerten mit Rollback-Support.
    """
    __tablename__ = "privat_threshold_adjustments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    threshold_type = Column(String(50), nullable=False, index=True)

    # Values
    previous_value = Column(Numeric(10, 4), nullable=False)
    new_value = Column(Numeric(10, 4), nullable=False)

    # Adjustment details
    adjustment_source = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=False, default=0.7)

    # Rollback support
    can_rollback = Column(Boolean, nullable=False, default=True)
    rolled_back = Column(Boolean, nullable=False, default=False)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rolled_back_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamp
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_threshold_adjustments_user_type", "user_id", "threshold_type"),
        {"comment": "Audit-Log für Schwellenwert-Änderungen (Privat-Modul)"}
    )


class PrivatThresholdRecommendation(Base):
    """AI-generierte Empfehlung für Schwellenwert-Anpassung.

    Empfehlungen haben ein Ablaufdatum und können akzeptiert
    oder abgelehnt werden.
    """
    __tablename__ = "privat_threshold_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    threshold_type = Column(String(50), nullable=False)

    # Values
    current_value = Column(Numeric(10, 4), nullable=False)
    recommended_value = Column(Numeric(10, 4), nullable=False)

    # Recommendation details
    reason = Column(Text, nullable=False)
    confidence = Column(Numeric(3, 2), nullable=False, default=0.7)
    potential_impact = Column(Text, nullable=True)

    # Status
    accepted = Column(Boolean, nullable=True)  # null = pending
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Validity
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_threshold_recommendations_pending", "user_id", "accepted", postgresql_where=text("accepted IS NULL")),
        {"comment": "AI-Empfehlungen für Schwellenwert-Anpassungen (Privat-Modul)"}
    )
