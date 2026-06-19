"""Entity, Business, Contract und Multi-Tenancy Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# ============================================================================
# NOTIFICATIONS + FEATURE FLAGS (core system models)
# ============================================================================

class NotificationType(str, Enum):
    """Benachrichtigungs-Typen."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    OCR_COMPLETE = "ocr_complete"
    BATCH_COMPLETE = "batch_complete"
    EXPORT_READY = "export_ready"
    SHARE_RECEIVED = "share_received"
    SYSTEM = "system"


class Notification(Base):
    """
    Benutzer-Benachrichtigungen.

    Speichert In-App und E-Mail Benachrichtigungen:
    - OCR-Verarbeitung abgeschlossen
    - Batch-Job fertig
    - Export bereit zum Download
    - Dokument wurde geteilt
    - System-Benachrichtigungen
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Empfänger
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Typ und Titel
    notification_type = Column(
        String(30),
        nullable=False,
        default=NotificationType.INFO.value
    )
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)

    # Optionale Referenz (z.B. Dokument-ID)
    reference_type = Column(String(50), nullable=True)  # "document", "batch_job", etc.
    reference_id = Column(UUID(as_uuid=True), nullable=True)

    # Status
    read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # E-Mail gesendet?
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Zusätzliche Daten
    data = Column(CrossDBJSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="system_notifications")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_expires", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        """Prüft ob Benachrichtigung abgelaufen ist."""
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        return self.expires_at < datetime.now(timezone.utc)


class FeatureFlag(Base):
    """
    Feature Flags für A/B Testing und Rollouts.

    Ermöglicht:
    - Graduelle Feature-Rollouts
    - A/B Tests mit Benutzergruppen
    - Kill-Switches für kritische Features
    - Benutzer-spezifische Overrides
    """
    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Feature-Identifikator (z.B. "new_ocr_pipeline", "dark_mode_v2")
    key = Column(String(100), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Aktivierungsstatus
    enabled = Column(Boolean, default=False)

    # Rollout-Prozent (0-100)
    rollout_percentage = Column(Integer, default=0)

    # Zielgruppen (JSON Array von User-Tiers oder User-IDs)
    target_tiers = Column(CrossDBJSON, default=list)  # ["premium", "enterprise"]
    target_users = Column(CrossDBJSON, default=list)  # Spezifische User-IDs

    # A/B Test Varianten
    variants = Column(CrossDBJSON, default=dict)  # {"control": 50, "variant_a": 25, "variant_b": 25}

    # Zeitliche Begrenzung
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    # Zusätzliche Konfiguration
    config = Column(CrossDBJSON, default=dict)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        Index("ix_feature_flags_key", "key"),
        Index("ix_feature_flags_enabled", "enabled"),
    )

    def is_active(self) -> bool:
        """Prüft ob Feature Flag aktiv ist (zeitlich)."""
        if not self.enabled:
            return False

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False

        return True

    def is_enabled_for_user(self, user_id: str, user_tier: Optional[str] = None) -> bool:
        """Prüft ob Feature für bestimmten Benutzer aktiviert ist."""
        if not self.is_active():
            return False

        # Spezifische User-IDs haben Vorrang
        if self.target_users and user_id in self.target_users:
            return True

        # Tier-basierte Aktivierung
        if self.target_tiers and user_tier and user_tier in self.target_tiers:
            return True

        # Rollout-Prozent (deterministisch basierend auf User-ID Hash)
        if self.rollout_percentage > 0:
            import hashlib
            hash_input = f"{self.key}:{user_id}".encode()
            # SECURITY FIX Phase 11.2: Use SHA256 instead of MD5 for security-critical hashing
            hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16) % 100
            return hash_value < self.rollout_percentage

        return False

    def get_variant_for_user(self, user_id: str) -> Optional[str]:
        """Ermittelt A/B Test Variante für Benutzer."""
        if not self.variants:
            return None

        import hashlib
        hash_input = f"{self.key}:variant:{user_id}".encode()
        # SECURITY FIX Phase 11.2: Use SHA256 instead of MD5 for security-critical hashing
        hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16) % 100

        cumulative = 0
        for variant_name, percentage in self.variants.items():
            cumulative += percentage
            if hash_value < cumulative:
                return variant_name

        return list(self.variants.keys())[0] if self.variants else None


# ============================================================================
# BUSINESS ENTITY MODELS (Kunden/Lieferanten)
# ============================================================================

class EntityType(str, Enum):
    """Geschäftspartner-Typ."""
    CUSTOMER = "customer"      # Kunde - erhaelt Dokumente VON uns
    SUPPLIER = "supplier"      # Lieferant - sendet Dokumente AN uns
    BOTH = "both"             # Kann beides sein
    INTERNAL = "internal"      # Interne Entität


class BusinessEntity(SoftDeleteMixin, Base):
    """
    Geschäftspartner (Kunde/Lieferant).

    Zentrale Entität für alle Geschäftsbeziehungen.
    Unterstützt automatische Erkennung aus OCR-Text mit 99%+ Präzision.
    """
    __tablename__ = "business_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant (Migration 268): Listen/Einzel-GET filtern nach company_id;
    # NULL = firmenuebergreifende (globale) Entity. Spalte fehlte in Modell UND
    # DB, obwohl Endpoints/Services sie bereits referenzierten (AttributeError).
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Entity identification
    entity_type = Column(String(20), nullable=False, default=EntityType.SUPPLIER.value)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255))
    short_name = Column(String(50))  # Kurzname für Anzeige

    # German business identifiers (für 99%+ Präzision)
    vat_id = Column(String(20), unique=True, nullable=True)  # USt-IdNr (DE123456789)
    tax_number = Column(String(30), nullable=True)  # Steuernummer
    trade_register = Column(String(50), nullable=True)  # HRB 12345

    # Banking information
    iban = Column(String(34), nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)

    # Contact information
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")
    phone = Column(String(30), nullable=True)
    fax = Column(String(30), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)

    # Matching patterns (für Auto-Detection)
    name_aliases = Column(CrossDBJSON, default=list)  # ["ACME GmbH", "ACME AG", "Acme"]
    address_patterns = Column(CrossDBJSON, default=list)  # Alternative Adressen
    email_domains = Column(CrossDBJSON, default=list)  # ["acme.de", "acme.com"]

    # Statistics (werden automatisch aktualisiert)
    document_count = Column(Integer, default=0)
    first_document_date = Column(DateTime(timezone=True), nullable=True)
    last_document_date = Column(DateTime(timezone=True), nullable=True)
    total_invoice_amount = Column(Float, default=0.0)
    currency = Column(String(3), default="EUR")

    # Status and confidence
    is_active = Column(Boolean, default=True)
    verified = Column(Boolean, default=False)  # Manuell verifiziert
    confidence_score = Column(Float, default=0.0)  # 0.0-1.0
    auto_detected = Column(Boolean, default=False)  # Automatisch erkannt

    # Lexware Integration
    lexware_ids = Column(
        CrossDBJSON,
        default=dict,
        comment="Lexware IDs per company: {folie: {kd_nr, matchcode, lief_nr}, messer: {...}}"
    )
    company_presence = Column(
        CrossDBJSON,
        default=list,
        comment="List of company short_names where entity exists: ['folie', 'messer']"
    )
    primary_customer_number = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Primary customer number for display (e.g., 12345)"
    )
    primary_supplier_number = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Primary supplier number for display"
    )

    # Risk Scoring (für Zahlungsverhalten-Analyse)
    risk_score = Column(
        Float,
        nullable=True,
        comment="Overall risk score 0-100 (100 = highest risk)"
    )
    risk_factors = Column(
        CrossDBJSON,
        default=dict,
        comment="Risk factor breakdown: {payment_delay, default_rate, ...}"
    )
    payment_behavior_score = Column(
        Float,
        nullable=True,
        comment="Payment behavior score 0-100 (100 = best payer)"
    )
    risk_calculated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last risk calculation"
    )

    # Auto-Filing Support (Phase 11.1)
    default_folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        comment="Default folder for auto-filing documents from this entity",
    )

    # Metadata & Audit
    notes = Column(Text, nullable=True)
    custom_fields = Column(CrossDBJSON, default=dict)  # Flexible Zusatzfelder
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    documents = relationship("Document", back_populates="business_entity")
    # default_folder relationship disabled - Folder model not implemented yet
    # default_folder = relationship("Folder", foreign_keys=[default_folder_id])

    # Indexes
    __table_args__ = (
        Index("ix_business_entities_name", "name"),
        Index("ix_business_entities_vat_id", "vat_id"),
        Index("ix_business_entities_iban", "iban"),
        Index("ix_business_entities_postal_code", "postal_code"),
        Index("ix_business_entities_entity_type", "entity_type"),
        Index("ix_business_entities_is_active", "is_active"),
        Index("ix_business_entities_deleted_at", "deleted_at"),
        Index("ix_business_entities_default_folder_id", "default_folder_id"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if entity is soft-deleted."""
        return self.deleted_at is not None

    @property
    def full_address(self) -> str:
        """Returns formatted full address."""
        parts = []
        if self.street:
            addr = self.street
            if self.street_number:
                addr += f" {self.street_number}"
            parts.append(addr)
        if self.postal_code and self.city:
            parts.append(f"{self.postal_code} {self.city}")
        elif self.city:
            parts.append(self.city)
        if self.country and self.country != "DE":
            parts.append(self.country)
        return ", ".join(parts)


# ============================================================================
# INVOICE TRACKING MODEL (Rechnungsverfolgung)
# ============================================================================

class InvoiceStatus(str, Enum):
    """Rechnungsstatus für Zahlungsverfolgung."""
    OPEN = "open"           # Neu erstellt, noch nicht versandt
    SENT = "sent"           # Versandt, noch nicht fällig
    PAID = "paid"           # Vollständig bezahlt
    OVERDUE = "overdue"     # Fällig und nicht bezahlt
    DUNNING = "dunning"     # Im Mahnverfahren
    CANCELLED = "cancelled" # Storniert
    PARTIAL = "partial"     # Teilweise bezahlt


class InvoiceTracking(SoftDeleteMixin, Base):
    """
    Rechnungsverfolgung für Risk Scoring, Skonto und Teilzahlungen.

    Verknüpft Dokumente (Rechnungen) mit Zahlungsinformationen
    für die Berechnung von Risiko-Scores.

    Enterprise Features (Januar 2026):
    - Skonto-Tracking mit Deadline-Alerts
    - Teilzahlungs-Verwaltung
    - Ausstehender Betrag Tracking
    """
    __tablename__ = "invoice_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Document reference
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Invoice identification
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    # Amount information
    amount = Column(Float, default=0.0)
    currency = Column(String(3), default="EUR")

    # Payment status
    status = Column(
        String(20),
        default=InvoiceStatus.OPEN.value,
        nullable=False
    )

    # Payment tracking
    paid_at = Column(DateTime(timezone=True), nullable=True)
    paid_amount = Column(Float, nullable=True)

    # ==========================================================================
    # SKONTO TRACKING (P0 Feature - Januar 2026)
    # ==========================================================================
    skonto_percentage = Column(
        Float,
        nullable=True,
        comment="Skonto-Prozentsatz (z.B. 2.0 für 2%)"
    )
    skonto_days = Column(
        Integer,
        nullable=True,
        comment="Tage für Skonto-Frist ab Rechnungsdatum"
    )
    skonto_deadline = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Berechnete Skonto-Frist (invoice_date + skonto_days)"
    )
    skonto_amount = Column(
        Float,
        nullable=True,
        comment="Berechneter Skonto-Betrag"
    )
    skonto_used = Column(
        Boolean,
        default=False,
        comment="True wenn Skonto genutzt wurde"
    )
    skonto_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Skonto-Nutzung"
    )
    net_days = Column(
        Integer,
        nullable=True,
        comment="Zahlungsziel netto (z.B. 30 Tage)"
    )

    # ==========================================================================
    # TEILZAHLUNGS-TRACKING (P0 Feature - Januar 2026)
    # ==========================================================================
    outstanding_amount = Column(
        Float,
        nullable=True,
        comment="Ausstehender Betrag (amount - paid_amount)"
    )
    is_partial_payment = Column(
        Boolean,
        default=False,
        comment="True wenn Teilzahlung(en) erfasst"
    )

    # Dunning tracking (Mahnwesen)
    dunning_level = Column(Integer, default=0)
    last_dunning_at = Column(DateTime(timezone=True), nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        comment="Mandanten-Zuordnung"
    )

    # Direkter Entity-Link (Migration 094) - F4 (2026-05-20):
    # DB-Spalte existiert seit Migration 094, Model deklarierte sie nicht.
    # 50+ Service-Stellen nutzen InvoiceTracking.entity_id - Drift-Pattern
    # analog zu Task B (Invoice.company_id). Nachgezogen analog zu F1/F2/F3.
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepfung mit BusinessEntity (Kunde/Lieferant), Migration 094"
    )

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship(
        "Document",
        backref=backref("invoice_tracking", uselist=False, cascade="all, delete-orphan")
    )
    company = relationship("Company", backref="invoice_trackings")
    entity = relationship("BusinessEntity", backref="invoice_trackings")
    payment_transactions = relationship(
        "PaymentTransaction",
        back_populates="invoice_tracking",
        cascade="all, delete-orphan",
        order_by="PaymentTransaction.transaction_date.asc()"
    )

    # Indexes
    __table_args__ = (
        Index("ix_invoice_tracking_document_id", "document_id"),
        Index("ix_invoice_tracking_status", "status"),
        Index("ix_invoice_tracking_due_date", "due_date"),
        Index("ix_invoice_tracking_invoice_number", "invoice_number"),
        Index("ix_invoice_tracking_skonto_deadline", "skonto_deadline"),
        Index("ix_invoice_tracking_company_id", "company_id"),
        Index("ix_invoice_tracking_entity_id", "entity_id"),
        Index("ix_invoice_tracking_partial", "is_partial_payment", "status"),
    )

    @property
    def is_overdue(self) -> bool:
        """Prüft ob Rechnung überfällig ist."""
        if self.status in (InvoiceStatus.PAID.value, InvoiceStatus.CANCELLED.value):
            return False
        if self.due_date:
            return datetime.now(self.due_date.tzinfo) > self.due_date
        return False

    @property
    def days_overdue(self) -> int:
        """Anzahl Tage überfällig (0 wenn nicht überfällig)."""
        if not self.is_overdue or not self.due_date:
            return 0
        delta = datetime.now(self.due_date.tzinfo) - self.due_date
        return max(0, delta.days)

    @property
    def skonto_still_valid(self) -> bool:
        """Prüft ob Skonto noch nutzbar ist."""
        if not self.skonto_deadline or self.skonto_used:
            return False
        return datetime.now(self.skonto_deadline.tzinfo) <= self.skonto_deadline

    @property
    def days_until_skonto_expires(self) -> Optional[int]:
        """Tage bis Skonto abläuft (None wenn kein Skonto oder abgelaufen)."""
        if not self.skonto_deadline or self.skonto_used:
            return None
        delta = self.skonto_deadline - datetime.now(self.skonto_deadline.tzinfo)
        return max(0, delta.days) if delta.days >= 0 else None


class PaymentTransaction(Base):
    """
    Teilzahlung für eine Rechnung.

    Ermöglicht mehrere Zahlungen pro Rechnung mit:
    - Skonto-Abzug Tracking
    - Bank-Reconciliation
    - Audit Trail
    """
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reference to invoice
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Payment details
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Float, nullable=False, comment="Gezahlter Betrag")
    payment_reference = Column(String(200), nullable=True, comment="Verwendungszweck/Referenz")
    payment_method = Column(
        String(30),
        default="bank_transfer",
        comment="Zahlungsmethode: bank_transfer, cash, credit_card, direct_debit"
    )

    # Skonto
    skonto_deducted = Column(
        Float,
        nullable=True,
        comment="Abgezogener Skonto-Betrag"
    )

    # Bank reconciliation
    bank_transaction_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Verknüpfte Bank-Transaktion ID"
    )
    reconciliation_status = Column(
        String(20),
        default="pending",
        comment="pending, matched, unmatched"
    )
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    reconciled_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Notes
    notes = Column(Text, nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    invoice_tracking = relationship(
        "InvoiceTracking",
        back_populates="payment_transactions"
    )
    company = relationship("Company", backref="payment_transactions")
    created_by = relationship("User", foreign_keys=[created_by_id])
    reconciled_by = relationship("User", foreign_keys=[reconciled_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_payment_transactions_invoice", "invoice_tracking_id"),
        Index("ix_payment_transactions_date", "transaction_date"),
        Index("ix_payment_transactions_bank", "bank_transaction_id"),
        Index("ix_payment_transactions_company", "company_id"),
        Index("ix_payment_transactions_reconciliation", "reconciliation_status"),
    )


class DocumentChainDiscrepancy(Base):
    """
    Abweichungen in Dokumentenketten.

    Erfasst Unterschiede zwischen verknüpften Dokumenten:
    - Betragsabweichungen (Angebot vs Rechnung)
    - Mengenabweichungen
    - Preisabweichungen
    """
    __tablename__ = "document_chain_discrepancies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Chain reference
    chain_id = Column(String(100), nullable=False, index=True)

    # Documents involved
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    target_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Discrepancy details
    discrepancy_type = Column(
        String(30),
        nullable=False,
        comment="amount, quantity, price, date, missing_item"
    )
    field_name = Column(String(100), nullable=True, comment="Betroffenes Feld")
    expected_value = Column(String(500), nullable=True)
    actual_value = Column(String(500), nullable=True)
    difference_amount = Column(Float, nullable=True, comment="Numerische Differenz")
    difference_percentage = Column(Float, nullable=True, comment="Prozentuale Differenz")

    # Severity
    severity = Column(
        String(20),
        default="warning",
        comment="info, warning, error, critical"
    )
    description = Column(Text, nullable=True)

    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    resolution_notes = Column(Text, nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source_document = relationship("Document", foreign_keys=[source_document_id])
    target_document = relationship("Document", foreign_keys=[target_document_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    company = relationship("Company", backref="chain_discrepancies")

    # Indexes
    __table_args__ = (
        Index("ix_chain_discrepancies_chain", "chain_id"),
        Index("ix_chain_discrepancies_type", "discrepancy_type"),
        Index("ix_chain_discrepancies_severity", "severity"),
        Index("ix_chain_discrepancies_resolved", "is_resolved"),
        Index("ix_chain_discrepancies_company", "company_id"),
    )


# ============================================================================
# DOCUMENT GROUP MODELS (Zusammengehoerige Dokumente)
# ============================================================================

class DocumentGroupType(str, Enum):
    """Dokumentgruppen-Typ."""
    STAPLED = "stapled"              # Physisch geheftet gewesen
    MULTI_PAGE = "multi_page"        # Mehrseitiger Scan (z.B. PDF mit mehreren Seiten)
    TRANSACTION = "transaction"      # Transaktionsbezogen (z.B. Rechnung + Lieferschein)
    CORRESPONDENCE = "correspondence" # Briefwechsel
    PROJECT = "project"              # Projektbezogen
    MANUAL = "manual"                # Manuell vom Benutzer erstellt


class DocumentGroup(SoftDeleteMixin, Base):
    """
    Dokumentgruppe für zusammengehoerige Dokumente.

    Gruppiert:
    - Physisch geheftete Seiten (waren mit Heftklammer zusammen)
    - Mehrseitige Scans
    - Logisch zusammengehoerige Dokumente (gleiche Transaktion)

    Erkennung mit 99%+ Präzision durch Mehrfach-Validierung.
    """
    __tablename__ = "document_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Group identification
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    group_type = Column(String(30), nullable=False, default=DocumentGroupType.STAPLED.value)

    # Primary document (erstes/wichtigstes Dokument der Gruppe)
    primary_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Detection metadata
    detection_method = Column(String(50), nullable=True)  # "filename_sequence", "timestamp", "content_similarity"
    detection_confidence = Column(Float, default=0.0)  # 0.0-1.0, muss >= 0.99 sein für Auto-Gruppierung
    detection_details = Column(CrossDBJSON, default=dict)  # Details zur Erkennung
    detection_signals = Column(CrossDBJSON, default=list)  # Alle Erkennungssignale

    # Content aggregation
    total_pages = Column(Integer, default=1)
    combined_text = Column(Text, nullable=True)  # Kombinierter OCR-Text aller Dokumente
    combined_text_hash = Column(String(64), nullable=True)  # SHA-256 für Deduplizierung

    # Business context
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)
    document_date = Column(DateTime(timezone=True), nullable=True)  # Hauptdatum der Gruppe
    reference_number = Column(String(100), nullable=True)  # Referenznummer (Rechnungsnr., etc.)

    # Extracted data (aggregiert aus allen Dokumenten)
    extracted_data = Column(CrossDBJSON, default=dict)

    # User interaction
    user_confirmed = Column(Boolean, default=False)  # Benutzer hat Gruppierung bestätigt
    user_split = Column(Boolean, default=False)  # Benutzer hat Gruppe aufgeteilt
    confirmation_date = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Validation queue
    needs_review = Column(Boolean, default=False)  # In Warteschlange für manuelle Prüfung
    review_priority = Column(Integer, default=5)  # 1=hoechste Priorität

    # Audit
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mandanten-Zuordnung fuer Multi-Company Isolation"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], backref="document_groups")
    company = relationship("Company", backref="document_groups")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])
    business_entity = relationship("BusinessEntity", backref="document_groups")
    documents = relationship("Document", back_populates="document_group", foreign_keys="Document.group_id")
    primary_document = relationship("Document", foreign_keys=[primary_document_id], post_update=True)

    # Indexes
    __table_args__ = (
        Index("ix_document_groups_group_type", "group_type"),
        Index("ix_document_groups_detection_confidence", "detection_confidence"),
        Index("ix_document_groups_business_entity_id", "business_entity_id"),
        Index("ix_document_groups_owner_id", "owner_id"),
        Index("ix_document_groups_company_id", "company_id"),
        Index("ix_document_groups_company_group_type", "company_id", "group_type"),
        Index("ix_document_groups_needs_review", "needs_review"),
        Index("ix_document_groups_user_confirmed", "user_confirmed"),
        Index("ix_document_groups_created_at", "created_at"),
        Index("ix_document_groups_deleted_at", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if group is soft-deleted."""
        return self.deleted_at is not None

    @property
    def is_auto_confirmed(self) -> bool:
        """Check if group was auto-confirmed (99%+ confidence)."""
        return self.detection_confidence >= 0.99 and not self.user_confirmed


# ============================================================================
# DOCUMENT RELATIONSHIP MODEL (Beziehungen zwischen Dokumenten)
# ============================================================================

class RelationshipType(str, Enum):
    """Beziehungstyp zwischen Dokumenten."""
    CHILD_OF = "child_of"           # Seite gehoert zu mehrseitigem Dokument
    REFERENCES = "references"        # Dokument verweist auf anderes (z.B. Rechnung -> Vertrag)
    REPLIES_TO = "replies_to"        # Antwort auf Dokument
    SUPPLEMENTS = "supplements"      # Ergaenzung/Anlage zu Dokument
    SUPERSEDES = "supersedes"        # Ersetzt/Annulliert anderes Dokument
    DUPLICATE_OF = "duplicate_of"    # Ist Duplikat von
    RELATED = "related"              # Allgemeine Beziehung


class DocumentRelationship(Base):
    """
    Beziehung zwischen zwei Dokumenten.

    Ermöglicht Tracking von:
    - Seitenreihenfolge in mehrseitigen Dokumenten
    - Verweise zwischen Dokumenten (Rechnung -> Vertrag)
    - Duplikat-Erkennung
    - Auftragsketten (Angebot -> Auftrag -> Lieferschein -> Rechnung)

    Bidirektionale Beziehungen werden als zwei separate Einträge gespeichert.
    """
    __tablename__ = "document_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationship endpoints
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    target_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Relationship details
    relationship_type = Column(String(30), nullable=False)
    confidence = Column(Float, default=1.0)  # 0.0-1.0 (legacy)
    confidence_score = Column(Float, nullable=True, comment="Konfidenz bei Auto-Detection (0.0-1.0)")

    # Chain reference (für Auftragsketten)
    chain_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Auftragsketten-ID (z.B. CHAIN-2026-00001)"
    )

    # Ordering (für CHILD_OF Beziehungen)
    sequence_number = Column(Integer, nullable=True)  # Seitennummer/Reihenfolge

    # Detection metadata
    detected_by = Column(String(50), nullable=True)  # "algorithm", "user", "ocr_reference"
    detection_details = Column(CrossDBJSON, default=dict)
    auto_detected = Column(
        Boolean,
        default=False,
        comment="True wenn automatisch erkannt (nicht manuell)"
    )

    # User interaction / Validation
    user_confirmed = Column(Boolean, default=False)
    user_rejected = Column(Boolean, default=False)
    validated = Column(
        Boolean,
        default=False,
        comment="True wenn manuell validiert oder manuell erstellt"
    )
    validated_at = Column(DateTime(timezone=True), nullable=True)
    validated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Wer hat validiert"
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Firmen-Zuordnung für Multi-Tenant"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    source_document = relationship(
        "Document",
        foreign_keys=[source_document_id],
        backref="outgoing_relationships"
    )
    target_document = relationship(
        "Document",
        foreign_keys=[target_document_id],
        backref="incoming_relationships"
    )
    created_by = relationship("User", foreign_keys=[created_by_id])
    validated_by = relationship("User", foreign_keys=[validated_by_id])
    company = relationship("Company", backref="document_relationships")

    # Indexes and constraints
    __table_args__ = (
        Index("ix_document_relationships_source", "source_document_id"),
        Index("ix_document_relationships_target", "target_document_id"),
        Index("ix_document_relationships_type", "relationship_type"),
        Index("ix_document_relationships_confidence", "confidence"),
        Index("ix_document_relationships_chain", "chain_id"),
        Index("ix_document_relationships_company", "company_id"),
        # Prevent duplicate relationships
        Index(
            "ix_document_relationships_unique",
            "source_document_id", "target_document_id", "relationship_type",
            unique=True
        ),
    )


# =============================================================================
# CONTRACTS (Business Contract Management)
# =============================================================================

class ContractType(str, Enum):
    """Types of business contracts."""
    SERVICE = "service"  # Dienstleistungsvertrag
    SUPPLY = "supply"  # Liefervertrag
    FRAMEWORK = "framework"  # Rahmenvertrag
    MAINTENANCE = "maintenance"  # Wartungsvertrag
    LICENSE = "license"  # Lizenzvertrag
    LEASE = "lease"  # Mietvertrag (Geschäftsräume)
    CONSULTING = "consulting"  # Beratungsvertrag
    COOPERATION = "cooperation"  # Kooperationsvertrag
    NDA = "nda"  # Geheimhaltungsvereinbarung
    PURCHASE = "purchase"  # Kaufvertrag
    OTHER = "other"


class ContractStatus(str, Enum):
    """Contract lifecycle status."""
    DRAFT = "draft"  # Entwurf
    PENDING_SIGNATURE = "pending_signature"  # Unterschrift ausstehend
    ACTIVE = "active"  # Aktiv
    SUSPENDED = "suspended"  # Ausgesetzt
    EXPIRING_SOON = "expiring_soon"  # Läuft bald ab
    EXPIRED = "expired"  # Abgelaufen
    TERMINATED = "terminated"  # Gekündigt
    RENEWED = "renewed"  # Verlängert


class RenewalOptionStatus(str, Enum):
    """Status of renewal options."""
    AVAILABLE = "available"  # Verfügbar
    PENDING = "pending"  # Entscheidung ausstehend
    EXERCISED = "exercised"  # Ausgeubt
    DECLINED = "declined"  # Abgelehnt
    EXPIRED = "expired"  # Abgelaufen


class MilestoneType(str, Enum):
    """Types of contract milestones."""
    CONTRACT_START = "contract_start"
    CONTRACT_END = "contract_end"
    RENEWAL_OPTION = "renewal_option"
    NOTICE_DEADLINE = "notice_deadline"
    PRICE_ADJUSTMENT = "price_adjustment"
    SERVICE_LEVEL_REVIEW = "service_level_review"
    DELIVERABLE_DUE = "deliverable_due"
    PAYMENT_DUE = "payment_due"
    AUDIT = "audit"
    CUSTOM = "custom"


class AmendmentStatus(str, Enum):
    """Status of contract amendments."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class BusinessContract(Base):
    """
    Business Contract entity for B2B contract management.

    Supports:
    - Contract lifecycle tracking
    - Automatic deadline calculations
    - Renewal options management
    - Multi-tenant operation
    """
    __tablename__ = "business_contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Contract identification
    contract_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    contract_type: Mapped[ContractType] = mapped_column(
        SQLAlchemyEnum(ContractType), default=ContractType.OTHER
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Contract parties
    party_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True
    )
    party_a_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_a_signatory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    party_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True
    )
    party_b_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_b_signatory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Contract timeline
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Termination and renewal
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30)
    notice_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    auto_renewal: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_period_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_renewals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_renewal_count: Mapped[int] = mapped_column(Integer, default=0)

    # Financial terms
    total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    monthly_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Price adjustments
    price_adjustment_clause: Mapped[bool] = mapped_column(Boolean, default=False)
    price_adjustment_index: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "VPI", "Verbraucherpreisindex"
    price_adjustment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    price_adjustment_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # Legal terms
    governing_law: Mapped[str] = mapped_column(String(100), default="Deutsches Recht")
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    arbitration_clause: Mapped[bool] = mapped_column(Boolean, default=False)

    # Document references
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )

    # Status and workflow
    status: Mapped[ContractStatus] = mapped_column(
        SQLAlchemyEnum(ContractStatus, values_callable=lambda e: [m.value for m in e]), default=ContractStatus.DRAFT
    )
    signed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    terminated_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notifications
    reminder_days: Mapped[List[int]] = mapped_column(
        JSONB, default=lambda: [90, 60, 30, 14, 7]
    )
    last_reminder_sent: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notification_emails: Mapped[List[str]] = mapped_column(
        JSONB, default=list
    )

    # Metadata
    tags: Mapped[List[str]] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    key_contacts: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    company = relationship("Company", foreign_keys=[company_id])
    party_a = relationship("BusinessEntity", foreign_keys=[party_a_id])
    party_b = relationship("BusinessEntity", foreign_keys=[party_b_id])
    document = relationship("Document", foreign_keys=[document_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    milestones = relationship(
        "ContractMilestone", back_populates="contract", cascade="all, delete-orphan"
    )
    amendments = relationship(
        "ContractAmendment", back_populates="contract", cascade="all, delete-orphan"
    )
    renewal_options = relationship(
        "ContractRenewalOption", back_populates="contract", cascade="all, delete-orphan"
    )

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("company_id", "contract_number", name="uq_contract_number"),
        Index("ix_contract_company", "company_id"),
        Index("ix_contract_status", "status"),
        Index("ix_contract_end_date", "end_date"),
        Index("ix_contract_notice_deadline", "notice_deadline"),
        Index("ix_contract_party_a", "party_a_id"),
        Index("ix_contract_party_b", "party_b_id"),
    )

    @hybrid_property
    def days_until_end(self) -> Optional[int]:
        """Calculate days until contract ends."""
        if not self.end_date:
            return None
        delta = self.end_date - date.today()
        return delta.days

    @hybrid_property
    def days_until_notice_deadline(self) -> Optional[int]:
        """Calculate days until notice deadline."""
        if not self.notice_deadline:
            return None
        delta = self.notice_deadline - date.today()
        return delta.days

    @hybrid_property
    def is_expiring_soon(self) -> bool:
        """Check if contract is expiring within 90 days."""
        if not self.end_date:
            return False
        return 0 < (self.end_date - date.today()).days <= 90

    @hybrid_property
    def is_notice_deadline_critical(self) -> bool:
        """Check if notice deadline is within 30 days."""
        if not self.notice_deadline:
            return False
        days = (self.notice_deadline - date.today()).days
        return 0 < days <= 30

    def calculate_notice_deadline(self) -> Optional[date]:
        """Calculate notice deadline based on end date and notice period."""
        if not self.end_date:
            return None
        return self.end_date - timedelta(days=self.notice_period_days)

    def update_notice_deadline(self) -> None:
        """Update the notice deadline field."""
        self.notice_deadline = self.calculate_notice_deadline()


class ContractMilestone(Base):
    """
    Contract milestones for tracking key dates and events.
    """
    __tablename__ = "contract_milestones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_contracts.id", ondelete="CASCADE"), nullable=False
    )

    milestone_type: Mapped[MilestoneType] = mapped_column(
        SQLAlchemyEnum(MilestoneType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Completion tracking
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completion_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notifications
    reminder_days_before: Mapped[List[int]] = mapped_column(
        JSONB, default=lambda: [14, 7, 1]
    )
    last_reminder_sent: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Linked task (optional)
    linked_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="milestones")

    __table_args__ = (
        Index("ix_milestone_contract", "contract_id"),
        Index("ix_milestone_scheduled", "scheduled_date"),
        Index("ix_milestone_type", "milestone_type"),
    )

    @hybrid_property
    def days_until_due(self) -> int:
        """Calculate days until milestone is due."""
        delta = self.scheduled_date - date.today()
        return delta.days

    @hybrid_property
    def is_overdue(self) -> bool:
        """Check if milestone is overdue and not completed."""
        return not self.is_completed and self.scheduled_date < date.today()


class ContractRenewalOption(Base):
    """
    Tracks available renewal options for a contract.
    """
    __tablename__ = "contract_renewal_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_contracts.id", ondelete="CASCADE"), nullable=False
    )

    # Option details
    option_number: Mapped[int] = mapped_column(Integer, nullable=False)
    renewal_duration_months: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pricing
    price_adjustment_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "fixed", "percentage", "index"
    price_adjustment_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    new_monthly_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )

    # Deadlines
    exercise_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    renewal_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    notice_required_days: Mapped[int] = mapped_column(Integer, default=30)

    # Status
    status: Mapped[RenewalOptionStatus] = mapped_column(
        SQLAlchemyEnum(RenewalOptionStatus), default=RenewalOptionStatus.AVAILABLE
    )
    exercised_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    exercised_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="renewal_options")
    exercised_by = relationship("User", foreign_keys=[exercised_by_id])

    __table_args__ = (
        UniqueConstraint(
            "contract_id", "option_number", name="uq_contract_renewal_option"
        ),
        Index("ix_renewal_contract", "contract_id"),
        Index("ix_renewal_deadline", "exercise_deadline"),
        Index("ix_renewal_status", "status"),
    )

    @hybrid_property
    def days_until_deadline(self) -> int:
        """Calculate days until exercise deadline."""
        delta = self.exercise_deadline - date.today()
        return delta.days

    @hybrid_property
    def is_deadline_critical(self) -> bool:
        """Check if deadline is within 30 days and option still available."""
        if self.status != RenewalOptionStatus.AVAILABLE:
            return False
        return 0 < self.days_until_deadline <= 30


class ContractAmendment(Base):
    """
    Tracks contract amendments and changes.
    """
    __tablename__ = "contract_amendments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_contracts.id", ondelete="CASCADE"), nullable=False
    )

    # Amendment identification
    amendment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amendment_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Changes
    changes_summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_clauses: Mapped[List[str]] = mapped_column(JSONB, default=list)
    changes_detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Financial impact
    value_change: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    new_total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )

    # Document
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )

    # Status
    status: Mapped[AmendmentStatus] = mapped_column(
        SQLAlchemyEnum(AmendmentStatus), default=AmendmentStatus.DRAFT
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="amendments")
    document = relationship("Document", foreign_keys=[document_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint(
            "contract_id", "amendment_number", name="uq_contract_amendment_number"
        ),
        Index("ix_amendment_contract", "contract_id"),
        Index("ix_amendment_status", "status"),
        Index("ix_amendment_effective", "effective_date"),
    )


# Event Listeners for BusinessContract
@event.listens_for(BusinessContract, 'before_insert')
@event.listens_for(BusinessContract, 'before_update')
def contract_before_save(mapper, connection, target: BusinessContract):
    """Auto-calculate notice deadline before saving."""
    if target.end_date and target.notice_period_days:
        target.notice_deadline = target.calculate_notice_deadline()

    # Auto-update status based on dates
    today = date.today()
    if target.status not in [ContractStatus.DRAFT, ContractStatus.TERMINATED]:
        if target.end_date:
            if target.end_date < today:
                target.status = ContractStatus.EXPIRED
            elif (target.end_date - today).days <= 90:
                target.status = ContractStatus.EXPIRING_SOON
            elif target.status == ContractStatus.EXPIRING_SOON:
                target.status = ContractStatus.ACTIVE


# =============================================================================
# MULTI-TENANT SUBSCRIPTION SYSTEM (Migration 104)
# =============================================================================


class SubscriptionTier(str, Enum):
    """Abonnement-Stufen für Multi-Tenant SaaS."""
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class TenantRateLimit(Base):
    """Tenant-spezifische Rate Limit Konfiguration.

    Ermöglicht individuelle Rate-Limits pro Mandant und Endpoint-Pattern.
    Wird durch SubscriptionTierDefaults mit Defaults befuellt.
    """
    __tablename__ = "tenant_rate_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Endpoint-spezifische Limits
    endpoint_pattern = Column(
        String(255),
        nullable=False,
        comment="Endpoint-Pattern (z.B. /api/v1/documents/*)"
    )
    requests_per_minute = Column(Integer, nullable=False, default=100)
    requests_per_hour = Column(Integer, nullable=False, default=1000)
    requests_per_day = Column(Integer, nullable=False, default=10000)

    # Burst-Limits
    burst_limit = Column(
        Integer,
        nullable=False,
        default=50,
        comment="Max Requests in 1 Sekunde"
    )

    # Spezielle Limits
    ocr_requests_per_hour = Column(Integer, nullable=True, comment="OCR-spezifisches Limit")
    batch_requests_per_hour = Column(Integer, nullable=True, comment="Batch-Operations Limit")
    export_requests_per_day = Column(Integer, nullable=True, comment="Export-Limit pro Tag")

    # Flags
    is_custom = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True wenn manuell angepasst"
    )
    is_active = Column(Boolean, nullable=False, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", back_populates="rate_limits")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint("company_id", "endpoint_pattern", name="uq_tenant_rate_limits_company_endpoint"),
        Index("ix_tenant_rate_limits_endpoint", "endpoint_pattern"),
    )

    def __repr__(self) -> str:
        return f"<TenantRateLimit {self.company_id}:{self.endpoint_pattern}>"


class TenantUsageMetrics(Base):
    """Aggregierte Nutzungsmetriken pro Tenant für Dashboard und Analytics.

    Wird automatisch durch Celery-Tasks befuellt (hourly, daily, monthly).
    """
    __tablename__ = "tenant_usage_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zeitraum
    period_type = Column(
        String(20),
        nullable=False,
        comment="hourly, daily, monthly"
    )
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # API Metriken
    total_requests = Column(BigInteger, nullable=False, default=0)
    rate_limited_requests = Column(BigInteger, nullable=False, default=0)
    failed_requests = Column(BigInteger, nullable=False, default=0)
    avg_response_time_ms = Column(Float, nullable=True)
    p95_response_time_ms = Column(Float, nullable=True)
    p99_response_time_ms = Column(Float, nullable=True)

    # OCR Metriken
    documents_processed = Column(Integer, nullable=False, default=0)
    pages_processed = Column(Integer, nullable=False, default=0)
    ocr_processing_time_ms = Column(BigInteger, nullable=False, default=0)

    # Storage Metriken
    storage_used_bytes = Column(BigInteger, nullable=False, default=0)
    documents_stored = Column(Integer, nullable=False, default=0)

    # User Metriken
    active_users = Column(Integer, nullable=False, default=0)
    unique_sessions = Column(Integer, nullable=False, default=0)

    # Endpoint-Breakdown
    endpoint_breakdown = Column(
        CrossDBJSON,
        nullable=True,
        comment="Requests pro Endpoint"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="usage_metrics")

    __table_args__ = (
        UniqueConstraint("company_id", "period_type", "period_start", name="uq_tenant_metrics_period"),
        Index("ix_tenant_metrics_period", "period_type", "period_start"),
        Index("ix_tenant_metrics_company_period", "company_id", "period_type", "period_start"),
    )

    def __repr__(self) -> str:
        return f"<TenantUsageMetrics {self.company_id}:{self.period_type}:{self.period_start}>"


class RateLimitViolation(Base):
    """Log für Rate-Limit-Verletzungen.

    Wird für Security-Monitoring und Abuse-Detection verwendet.
    """
    __tablename__ = "rate_limit_violations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Violation Details
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(500), nullable=True)

    # Limit Info
    limit_type = Column(
        String(50),
        nullable=False,
        comment="minute, hour, day, burst"
    )
    limit_value = Column(Integer, nullable=False)
    current_count = Column(Integer, nullable=False)
    retry_after_seconds = Column(Integer, nullable=True)

    # Timestamp
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="rate_limit_violations")
    user = relationship("User")

    __table_args__ = (
        Index("ix_rate_violations_time", "occurred_at"),
        Index("ix_rate_violations_endpoint", "endpoint"),
    )

    def __repr__(self) -> str:
        return f"<RateLimitViolation {self.endpoint}@{self.occurred_at}>"


class SubscriptionTierDefaults(Base):
    """Default-Konfiguration für Subscription Tiers.

    Definiert die Standard-Limits und Features pro Tier.
    Admin kann diese anpassen.
    """
    __tablename__ = "subscription_tier_defaults"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier = Column(String(50), nullable=False, unique=True)

    # Limits
    max_users = Column(Integer, nullable=False)
    max_documents_per_month = Column(Integer, nullable=False)
    max_storage_gb = Column(Integer, nullable=False)

    # Rate Limits
    requests_per_minute = Column(Integer, nullable=False)
    requests_per_hour = Column(Integer, nullable=False)
    requests_per_day = Column(Integer, nullable=False)
    ocr_requests_per_hour = Column(Integer, nullable=False)
    batch_requests_per_hour = Column(Integer, nullable=False)

    # Features
    features_enabled = Column(CrossDBJSON, nullable=False)

    # Pricing (für Billing-Vorbereitung)
    price_monthly_eur = Column(Numeric(10, 2), nullable=True)
    price_yearly_eur = Column(Numeric(10, 2), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<SubscriptionTierDefaults {self.tier}>"


# ==================== Business Contacts ====================


class ContactType(str, Enum):
    """Kontakttyp für BusinessContact."""
    CUSTOMER = "customer"      # Kunde
    SUPPLIER = "supplier"      # Lieferant
    PARTNER = "partner"        # Partner
    PROSPECT = "prospect"      # Interessent
    OTHER = "other"            # Sonstige


class ContactRole(str, Enum):
    """Rolle eines Kontakts bei einem Dokument."""
    SENDER = "sender"          # Absender
    RECIPIENT = "recipient"    # Empfänger
    MENTIONED = "mentioned"    # Erwaehnt
    CC = "cc"                  # CC


class DocumentContact(Base):
    """
    Verknüpfung zwischen Dokumenten und Geschäftskontakten.

    Ermöglicht:
    - Mehrere Kontakte pro Dokument (Sender, Empfänger, Erwaehnt)
    - Mehrere Dokumente pro Kontakt
    - Automatische Erkennung mit Confidence-Score
    """
    __tablename__ = "document_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Role and detection
    role = Column(String(20), nullable=False, default=ContactRole.MENTIONED.value)
    confidence = Column(Float, nullable=True)  # 0.0-1.0 für auto-detected
    is_auto_detected = Column(Boolean, default=False)

    # Metadata
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="contact_links")
    contact = relationship("BusinessContact", back_populates="document_links")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])

    __table_args__ = (
        UniqueConstraint("document_id", "contact_id", "role", name="uq_doc_contact_role"),
    )

    def __repr__(self) -> str:
        return f"<DocumentContact doc={self.document_id} contact={self.contact_id} role={self.role}>"


class BusinessContact(Base):
    """
    Geschäftskontakt mit automatischer Erkennung.

    Zentrales Model für alle Geschäftskontakte mit:
    - Automatischer Erkennung aus Dokumenten (OCR)
    - Deduplizierung und Zusammenführung
    - Umfangreichen Kontaktinformationen
    - Verknüpfung zu Dokumenten
    """
    __tablename__ = "business_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic identification
    name = Column(String(255), nullable=False, index=True)
    name_normalized = Column(String(255), nullable=True)  # Für Fuzzy-Matching
    contact_type = Column(String(20), nullable=False, default=ContactType.CUSTOMER.value)
    company_form = Column(String(50), nullable=True)  # GmbH, AG, etc.

    # Tax identifiers
    tax_id = Column(String(30), nullable=True)  # Steuernummer
    vat_id = Column(String(20), nullable=True, index=True)  # USt-IdNr
    registration_number = Column(String(50), nullable=True)  # HRB

    # Business numbers
    customer_number = Column(String(50), nullable=True, index=True)
    supplier_number = Column(String(50), nullable=True, index=True)

    # Address
    street = Column(String(255), nullable=True)
    house_number = Column(String(20), nullable=True)
    address_addition = Column(String(100), nullable=True)  # c/o, Gebaeude, etc.
    postal_code = Column(String(10), nullable=True, index=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), default="Deutschland")

    # Contact details
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(30), nullable=True)
    fax = Column(String(30), nullable=True)
    website = Column(String(255), nullable=True)

    # Banking
    bank_name = Column(String(100), nullable=True)
    iban = Column(String(34), nullable=True, index=True)
    bic = Column(String(11), nullable=True)

    # Additional data
    contact_persons = Column(CrossDBJSON, default=list)  # [{"name": "...", "role": "...", "email": "..."}]
    parent_company_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    tags = Column(CrossDBJSON, default=list)
    custom_fields = Column(CrossDBJSON, default=dict)

    # Ownership and source
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(String(50), default="manual")  # manual, ocr, import, api
    auto_detected = Column(Boolean, default=False)
    auto_detection_confidence = Column(Float, nullable=True)
    first_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    merged_into_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id", ondelete="SET NULL"), nullable=True)

    # Statistics (denormalized for performance)
    document_count = Column(Integer, default=0)
    total_invoice_amount = Column(Numeric(15, 2), default=0)
    last_document_date = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], backref="business_contacts")
    company = relationship("Company", backref="business_contacts")
    first_document = relationship("Document", foreign_keys=[first_document_id])
    parent_company = relationship("BusinessContact", remote_side=[id], foreign_keys=[parent_company_id])
    merged_into = relationship("BusinessContact", remote_side=[id], foreign_keys=[merged_into_id])
    document_links = relationship("DocumentContact", back_populates="contact", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_business_contacts_owner_active", "owner_id", "is_active"),
        Index("ix_business_contacts_company_active", "company_id", "is_active"),
        Index("ix_business_contacts_name_normalized", "name_normalized"),
    )

    @hybrid_property
    def formatted_address(self) -> Optional[str]:
        """Formatierte Adresse."""
        parts = []
        if self.street:
            street_full = self.street
            if self.house_number:
                street_full += f" {self.house_number}"
            parts.append(street_full)
        if self.address_addition:
            parts.append(self.address_addition)
        if self.postal_code or self.city:
            location = f"{self.postal_code or ''} {self.city or ''}".strip()
            parts.append(location)
        if self.country and self.country != "Deutschland":
            parts.append(self.country)
        return ", ".join(parts) if parts else None

    @hybrid_property
    def display_name(self) -> str:
        """Anzeigename mit optionaler Rechtsform."""
        if self.company_form and self.company_form not in self.name:
            return f"{self.name} {self.company_form}"
        return self.name

    def __repr__(self) -> str:
        return f"<BusinessContact {self.name} ({self.contact_type})>"


# =============================================================================
# DATA LOSS PREVENTION (DLP) MODELS
# Enterprise Security: Policies, Audit, Access Control
# =============================================================================

class DLPActionType(str, Enum):
    """Mögliche DLP-Aktionen."""
    ALLOW = "allow"
    BLOCK = "block"
    WATERMARK = "watermark"
    NOTIFY = "notify"
    AUDIT_ONLY = "audit_only"


class SensitiveDataTypeEnum(str, Enum):
    """Typen sensibler Daten für DLP-Erkennung."""
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    SSN = "ssn"
    EMAIL = "email"
    PHONE = "phone"
    TAX_ID = "tax_id"
    DATE_OF_BIRTH = "date_of_birth"
    HEALTH_DATA = "health_data"
    FINANCIAL_DATA = "financial_data"


class DLPPolicyModel(Base):
    """
    DLP Policy Datenbank-Modell.

    Persistiert DLP-Policies in der Datenbank statt nur im Memory.
    Ermöglicht Multi-Tenant Isolation und Audit-Trail.

    SECURITY:
    - Policies werden serverseitig validiert
    - company_id ist Pflichtfeld für Multi-Tenant Isolation
    - Alle Änderungen werden im Audit-Log protokolliert
    """
    __tablename__ = "dlp_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Policy Identification
    policy_id = Column(String(64), nullable=False, index=True,
                       comment="Human-readable Policy-ID (z.B. 'confidential-docs')")
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # Multi-Tenant (KRITISCH!)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung - PFLICHT für Isolation"
    )

    # Zugriffsbedingungen
    allowed_roles = Column(CrossDBJSON, default=["admin"],
                          comment="Rollen die Zugriff haben")
    blocked_roles = Column(CrossDBJSON, default=[],
                          comment="Rollen die explizit blockiert sind")

    # Zeit-basierte Einschränkungen
    time_restrictions = Column(CrossDBJSON, nullable=True,
                              comment="{'start': '09:00', 'end': '18:00', 'weekdays': [0-6]}")

    # Dokument-Filter
    document_types = Column(CrossDBJSON, default=["all"],
                           comment="Betroffene Dokumenttypen")
    tags_required = Column(CrossDBJSON, default=[],
                          comment="Dokument muss diese Tags haben")
    tags_blocked = Column(CrossDBJSON, default=[],
                         comment="Dokument darf diese Tags nicht haben")

    # Aktionen
    action = Column(String(20), default=DLPActionType.ALLOW.value, nullable=False)
    require_watermark = Column(Boolean, default=False, nullable=False)
    watermark_config = Column(CrossDBJSON, nullable=True,
                             comment="Wasserzeichen-Konfiguration")

    # Benachrichtigungen
    notify_admin = Column(Boolean, default=False, nullable=False)
    notify_user = Column(Boolean, default=False, nullable=False)
    log_access = Column(Boolean, default=True, nullable=False)

    # Priorität (niedrigere Zahl = höhere Priorität)
    priority = Column(Integer, default=100, nullable=False, index=True)

    # Audit
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="dlp_policies")
    created_by = relationship("User", backref="created_dlp_policies")

    __table_args__ = (
        UniqueConstraint("company_id", "policy_id", name="uq_dlp_policy_company_id"),
        Index("ix_dlp_policies_company_enabled", "company_id", "enabled"),
        Index("ix_dlp_policies_company_priority", "company_id", "priority"),
        {"comment": "DLP Policies für Enterprise Security"}
    )

    def __repr__(self) -> str:
        return f"<DLPPolicy {self.policy_id} ({self.action})>"


class DLPAuditLog(Base):
    """
    DLP-spezifisches Audit-Log.

    Protokolliert alle DLP-relevanten Events:
    - Zugriffsprüfungen (erlaubt/blockiert)
    - Policy-Änderungen
    - Wasserzeichen-Anwendung
    - Sensible Daten gefunden

    SECURITY:
    - Keine sensiblen Daten werden geloggt (nur Typen und Counts)
    - Immutable (nur INSERT erlaubt)
    - company_id für Multi-Tenant Isolation
    """
    __tablename__ = "dlp_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Event-Kontext
    event_type = Column(String(50), nullable=False, index=True,
                       comment="access_check, policy_change, watermark_applied, sensitive_data_found")
    action_type = Column(String(20), nullable=True,
                        comment="download, view, print, export")

    # Ergebnis
    result = Column(String(20), nullable=False,
                   comment="allowed, blocked, watermarked, notified")
    reason = Column(String(500), nullable=True)

    # Betroffene Entities
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("dlp_policies.id", ondelete="SET NULL"), nullable=True)

    # Multi-Tenant (KRITISCH!)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung - PFLICHT"
    )

    # Sensitive Data Info (NUR Typen und Counts, KEINE Werte!)
    sensitive_data_types = Column(CrossDBJSON, nullable=True,
                                  comment="{'credit_card': 2, 'iban': 1} - NUR Counts!")

    # Request-Kontext
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    # Metadata (HINWEIS: 'metadata' ist SQLAlchemy reserviert!)
    log_metadata = Column(CrossDBJSON, default=dict)

    # Timestamp (immutable)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="dlp_audit_logs")
    document = relationship("Document", backref="dlp_audit_logs")
    policy = relationship("DLPPolicyModel", backref="audit_logs")
    company = relationship("Company", backref="dlp_audit_logs")

    __table_args__ = (
        Index("ix_dlp_audit_company_created", "company_id", "created_at"),
        Index("ix_dlp_audit_company_event", "company_id", "event_type"),
        Index("ix_dlp_audit_user_created", "user_id", "created_at"),
        Index("ix_dlp_audit_document", "document_id"),
        {"comment": "DLP Audit-Log für Compliance und Forensik"}
    )

    def __repr__(self) -> str:
        return f"<DLPAuditLog {self.event_type} ({self.result}) at {self.created_at}>"


# =============================================================================
# BPMN Process Engine Models - Enums
# =============================================================================
# NOTE: The BPMN table models are in app/db/models/bpmn.py but due to Python
# module resolution (models.py takes precedence over models/), we define the
# enums here and the table models import Base from here.


class ProcessStatus(str, Enum):
    """Status eines BPMN Prozess-Instances."""
    CREATED = "created"          # Erstellt, noch nicht gestartet
    RUNNING = "running"          # Läuft aktuell
    SUSPENDED = "suspended"      # Pausiert (z.B. wegen Timer)
    COMPLETED = "completed"      # Erfolgreich abgeschlossen
    TERMINATED = "terminated"    # Manuell abgebrochen
    FAILED = "failed"            # Fehlgeschlagen


class BpmnTaskStatus(str, Enum):
    """Status eines BPMN Tasks (unterscheidet sich von TaskStatus)."""
    PENDING = "pending"          # Wartet auf Aktivierung
    ACTIVE = "active"            # Bereit zur Bearbeitung
    ASSIGNED = "assigned"        # Benutzer zugewiesen
    IN_PROGRESS = "in_progress"  # In Bearbeitung
    COMPLETED = "completed"      # Abgeschlossen
    FAILED = "failed"            # Fehlgeschlagen
    SKIPPED = "skipped"          # Übersprungen (z.B. Gateway)
    ESCALATED = "escalated"      # Eskaliert


class TaskType(str, Enum):
    """BPMN Task-Typen."""
    USER_TASK = "user_task"              # Manuelle Aufgabe
    SERVICE_TASK = "service_task"        # Automatische Aufgabe
    SCRIPT_TASK = "script_task"          # Script-Ausführung
    SEND_TASK = "send_task"              # Nachricht senden
    RECEIVE_TASK = "receive_task"        # Nachricht empfangen
    MANUAL_TASK = "manual_task"          # Reine manuelle Aufgabe
    BUSINESS_RULE_TASK = "business_rule" # DMN-Entscheidung
    CALL_ACTIVITY = "call_activity"      # Subprocess aufrufen


class GatewayType(str, Enum):
    """BPMN Gateway-Typen."""
    EXCLUSIVE = "exclusive"      # XOR - Nur ein Pfad
    PARALLEL = "parallel"        # AND - Alle Pfade
    INCLUSIVE = "inclusive"      # OR - Ein oder mehrere Pfade
    EVENT_BASED = "event_based"  # Basierend auf Events


class EventType(str, Enum):
    """BPMN Event-Typen."""
    START = "start"
    END = "end"
    INTERMEDIATE_CATCH = "intermediate_catch"
    INTERMEDIATE_THROW = "intermediate_throw"
    BOUNDARY = "boundary"


class EventTrigger(str, Enum):
    """BPMN Event-Trigger."""
    NONE = "none"
    TIMER = "timer"
    MESSAGE = "message"
    SIGNAL = "signal"
    ERROR = "error"
    ESCALATION = "escalation"
    CONDITIONAL = "conditional"
    COMPENSATION = "compensation"
