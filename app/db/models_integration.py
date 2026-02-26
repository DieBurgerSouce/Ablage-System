"""Slack und Shipment Integration Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# ============================================================================
# SLACK INTEGRATION MODELS
# Slack-Kanal-Konfiguration und Benachrichtigungsverlauf
# ============================================================================


class SlackChannelType(str, Enum):
    """Typ des Slack-Kanals."""
    PUBLIC = "public"
    PRIVATE = "private"
    DM = "dm"  # Direct Message


class SlackChannel(Base):
    """
    Slack-Kanal-Konfiguration für Benachrichtigungen.

    Ermöglicht Multi-Kanal-Routing basierend auf:
    - Notification-Typ (document_processed, approval_required, etc.)
    - Firma (Multi-Tenant)
    - Priorität
    """

    __tablename__ = "slack_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kanal-Identifikation
    channel_id = Column(String(50), nullable=False, comment="Slack Channel ID (z.B. C01234567)")
    channel_name = Column(String(100), nullable=False, comment="Kanal-Name ohne #")
    channel_type = Column(
        String(20),
        default=SlackChannelType.PUBLIC.value,
        comment="Kanal-Typ: public, private, dm"
    )

    # Multi-Tenant Support
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        comment="Firmen-spezifischer Kanal (NULL = global)"
    )

    # Routing-Konfiguration
    notification_types = Column(
        CrossDBJSON,
        default=[],
        comment="Notification-Typen die an diesen Kanal gehen"
    )
    min_priority = Column(
        String(20),
        default="normal",
        comment="Mindest-Priorität: low, normal, high, urgent"
    )
    is_default = Column(Boolean, default=False, comment="Standard-Kanal für nicht-routbare Nachrichten")

    # Formatierung
    include_context = Column(Boolean, default=True, comment="Kontext-Details einschließen")
    mention_users = Column(
        CrossDBJSON,
        default=[],
        comment="Slack User-IDs die bei Nachrichten erwaehnt werden"
    )
    custom_icon = Column(String(100), nullable=True, comment="Custom Emoji als Icon")

    # Status
    is_active = Column(Boolean, default=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="slack_channels")
    created_by = relationship("User", foreign_keys=[created_by_id])
    messages = relationship("SlackMessageLog", back_populates="channel", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_slack_channels_company", "company_id"),
        Index("ix_slack_channels_active", "is_active"),
        Index("ix_slack_channels_channel_id", "channel_id"),
        UniqueConstraint("channel_id", "company_id", name="uq_slack_channels_channel_company"),
        {"comment": "Slack-Kanal-Konfiguration für Benachrichtigungen"}
    )

    def __repr__(self) -> str:
        return f"<SlackChannel #{self.channel_name} ({self.channel_id})>"


class SlackMessageStatus(str, Enum):
    """Status einer Slack-Nachricht."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


class SlackMessageLog(Base):
    """
    Log für gesendete Slack-Nachrichten.

    Ermöglicht:
    - Nachverfolgung von Benachrichtigungen
    - Rate Limit Monitoring
    - Fehleranalyse
    - Audit Trail
    """

    __tablename__ = "slack_message_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kanal-Referenz
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("slack_channels.id", ondelete="SET NULL"),
        nullable=True
    )
    slack_channel_id = Column(String(50), nullable=False, comment="Slack Channel ID als Backup")

    # Nachricht
    message_ts = Column(String(50), nullable=True, comment="Slack Message Timestamp/ID")
    thread_ts = Column(String(50), nullable=True, comment="Thread Timestamp wenn Antwort")
    notification_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message_preview = Column(String(500), nullable=True, comment="Erste 500 Zeichen")
    priority = Column(String(20), default="normal")

    # Status
    status = Column(
        String(20),
        default=SlackMessageStatus.PENDING.value,
    )
    error_message = Column(String(500), nullable=True)
    retry_count = Column(Integer, default=0)

    # Referenz zum Ausloesenden Objekt (polymorph)
    reference_type = Column(String(50), nullable=True, comment="document, approval, workflow, etc.")
    reference_id = Column(UUID(as_uuid=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    channel = relationship("SlackChannel", back_populates="messages")

    __table_args__ = (
        Index("ix_slack_messages_channel", "channel_id"),
        Index("ix_slack_messages_status", "status"),
        Index("ix_slack_messages_created", "created_at"),
        Index("ix_slack_messages_notification_type", "notification_type"),
        Index("ix_slack_messages_reference", "reference_type", "reference_id"),
        {"comment": "Log für gesendete Slack-Nachrichten"}
    )

    def __repr__(self) -> str:
        return f"<SlackMessageLog {self.notification_type} -> {self.slack_channel_id} ({self.status})>"


class SlackUserMapping(Base):
    """
    Mapping zwischen Ablage-System Benutzern und Slack User-IDs.

    Ermöglicht:
    - Direkte Benachrichtigungen an Benutzer
    - @mentions in Kanal-Nachrichten
    - Berechtigungs-Prüfung für Slack-Aktionen
    """

    __tablename__ = "slack_user_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User-Referenzen
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    slack_user_id = Column(String(50), nullable=False, comment="Slack User ID (z.B. U01234567)")
    slack_username = Column(String(100), nullable=True, comment="Slack Display Name")

    # Benachrichtigungs-Praeferenzen
    dm_enabled = Column(Boolean, default=False, comment="Direkte Nachrichten erlauben")
    dm_notification_types = Column(
        CrossDBJSON,
        default=[],
        comment="Notification-Typen die als DM gesendet werden"
    )
    mention_on_approval = Column(Boolean, default=True, comment="Bei Freigabe-Anfragen erwaehnen")
    quiet_hours_start = Column(String(5), nullable=True, comment="Ruhezeit Start (HH:MM)")
    quiet_hours_end = Column(String(5), nullable=True, comment="Ruhezeit Ende (HH:MM)")

    # Verifizierung
    is_verified = Column(Boolean, default=False, comment="Slack-Account verifiziert")
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="slack_mapping", uselist=False)

    __table_args__ = (
        Index("ix_slack_user_mappings_slack_user", "slack_user_id"),
        UniqueConstraint("slack_user_id", name="uq_slack_user_mappings_slack_user"),
        {"comment": "Mapping Ablage-System User <-> Slack User"}
    )

    def __repr__(self) -> str:
        return f"<SlackUserMapping User:{self.user_id} -> Slack:{self.slack_user_id}>"


# ==================== Shipping/Paketdienst Models ====================


class ShipmentCarrier(str, Enum):
    """Unterstützte Paketdienste."""
    DHL = "dhl"
    DPD = "dpd"
    HERMES = "hermes"
    UPS = "ups"
    GLS = "gls"
    FEDEX = "fedex"
    DEUTSCHE_POST = "deutsche_post"
    UNKNOWN = "unknown"


class ShipmentDirection(str, Enum):
    """Sendungsrichtung."""
    INBOUND = "inbound"    # Eingehend (Wareneingang)
    OUTBOUND = "outbound"  # Ausgehend (Versand an Kunden)
    RETURN = "return"      # Retoure


class ShipmentStatusEnum(str, Enum):
    """Standardisierte Sendungsstatus."""
    UNKNOWN = "unknown"
    LABEL_CREATED = "label_created"          # Label erstellt, noch nicht abgeholt
    PICKED_UP = "picked_up"                  # Vom Carrier abgeholt
    IN_TRANSIT = "in_transit"                # Unterwegs
    OUT_FOR_DELIVERY = "out_for_delivery"    # In Zustellung
    DELIVERED = "delivered"                  # Zugestellt
    DELIVERY_ATTEMPT = "delivery_attempt"    # Zustellversuch (nicht angetroffen)
    HELD_AT_LOCATION = "held_at_location"    # Liegt zur Abholung bereit
    RETURNED = "returned"                    # Zurück an Absender
    EXCEPTION = "exception"                  # Problem/Ausnahme
    CUSTOMS = "customs"                      # Im Zoll


class Shipment(SoftDeleteMixin, Base):
    """
    Sendungsverfolgung für Paketdienste.

    Features:
    - Multi-Carrier Support (DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post)
    - Automatische Carrier-Erkennung anhand Tracking-Nummer
    - Verknüpfung mit Business Entities und Dokumenten
    - Kosten-Tracking und Analyse

    Multi-Tenant: Alle Abfragen MUESSEN company_id filtern!
    """

    __tablename__ = "shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant: PFLICHT
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tracking-Daten
    tracking_number = Column(String(50), nullable=False)
    carrier = Column(String(20), nullable=False, default=ShipmentCarrier.UNKNOWN.value)
    direction = Column(String(20), nullable=False, default=ShipmentDirection.INBOUND.value)
    status = Column(String(30), nullable=False, default=ShipmentStatusEnum.UNKNOWN.value)
    status_description = Column(String(255), nullable=True)

    # Tracking URL (öffentlich)
    tracking_url = Column(String(500), nullable=True)

    # Zeitpunkte
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    actual_delivery = Column(DateTime(timezone=True), nullable=True)
    last_tracking_update = Column(DateTime(timezone=True), nullable=True)

    # Herkunft/Ziel
    origin = Column(String(100), nullable=True)
    destination = Column(String(100), nullable=True)

    # Details
    weight_kg = Column(Float, nullable=True)
    service_type = Column(String(100), nullable=True)  # z.B. "DHL Paket", "Express"
    reference = Column(String(100), nullable=True)  # z.B. Bestellnummer
    notes = Column(Text, nullable=True)

    # Kosten (optional)
    shipping_cost = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # Verknüpfungen
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknüpfter Kunde/Lieferant"
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknüpfter Lieferschein/Rechnung"
    )

    # Raw API Response (für Debugging)
    raw_tracking_data = Column(CrossDBJSON, default={})

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity", backref="shipments")
    document = relationship("Document", backref="shipments")
    events = relationship("ShipmentEvent", back_populates="shipment", order_by="desc(ShipmentEvent.timestamp)")
    creator = relationship("User")

    __table_args__ = (
        # Composite Index für Multi-Tenant
        Index("ix_shipments_company_status", "company_id", "status"),
        Index("ix_shipments_company_carrier", "company_id", "carrier"),
        Index("ix_shipments_company_direction", "company_id", "direction"),
        Index("ix_shipments_tracking", "tracking_number"),
        Index("ix_shipments_entity", "entity_id"),
        Index("ix_shipments_document", "document_id"),
        Index("ix_shipments_estimated_delivery", "estimated_delivery"),
        Index("ix_shipments_created", "created_at"),
        # Unique: Tracking-Nummer pro Company
        UniqueConstraint("company_id", "tracking_number", name="uq_shipments_company_tracking"),
        {"comment": "Sendungsverfolgung für Paketdienste"}
    )

    def __repr__(self) -> str:
        return f"<Shipment {self.carrier}:{self.tracking_number} ({self.status})>"


class ShipmentEvent(Base):
    """
    Einzelnes Tracking-Event für eine Sendung.

    Chronologischer Verlauf aller Status-Änderungen.
    """

    __tablename__ = "shipment_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Sendungs-Referenz
    shipment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False
    )

    # Event-Daten
    timestamp = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(30), nullable=False)
    description = Column(String(500), nullable=True)

    # Ort
    location = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country_code = Column(String(3), nullable=True)

    # Original-Status vom Carrier
    raw_status = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    shipment = relationship("Shipment", back_populates="events")

    __table_args__ = (
        Index("ix_shipment_events_shipment", "shipment_id"),
        Index("ix_shipment_events_timestamp", "timestamp"),
        Index("ix_shipment_events_status", "status"),
        # Unique: Ein Event pro Sendung und Zeitstempel
        UniqueConstraint("shipment_id", "timestamp", name="uq_shipment_events_shipment_timestamp"),
        {"comment": "Tracking-Events für Sendungen"}
    )
