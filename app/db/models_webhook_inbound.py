# -*- coding: utf-8 -*-
"""
Inbound Webhook Event satellite model.

Speichert empfangene Webhooks von externen Providern (DATEV, DHL, DPD, UPS, GLS)
fuer idempotente Verarbeitung, Retry-Logik und Audit-Trail.

Feinpoliert und durchdacht - Enterprise-grade Inbound Webhook Tracking.
"""

import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class InboundWebhookEvent(Base):
    """Inbound Webhook Events fuer idempotente Verarbeitung.

    Speichert empfangene Webhooks von externen Providern fuer:
    - Idempotenz-Pruefung (doppelte Events ignorieren)
    - Retry-Logik bei Fehlern
    - Audit-Trail
    - Provider-uebergreifende Event-Normalisierung
    """
    __tablename__ = "inbound_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, comment="datev, dhl, dpd, ups, gls")
    config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ERP-Verbindung (fuer DATEV), nullable fuer Carrier-Provider"
    )

    # Event-Identifikation (fuer Idempotenz)
    event_id = Column(String(255), nullable=False, comment="Externe Event-ID (Idempotenz)")
    event_type = Column(String(100), nullable=False, comment="Provider-spezifischer Event-Typ")
    action = Column(String(50), nullable=False, comment="create, update, delete, status_change")

    # Payload-Tracking
    payload_hash = Column(String(64), nullable=False, comment="SHA-256 Hash des Payloads")
    payload_preview = Column(CrossDBJSON, nullable=True, comment="Sanitized Preview (keine PII)")
    external_ref = Column(String(255), nullable=True, index=True, comment="Tracking-Nr, Rechnungs-Nr, etc.")

    # Verarbeitungsstatus
    status = Column(String(30), nullable=False, default="pending", index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Task-Tracking
    task_id = Column(String(100), nullable=True, comment="Celery Task-ID")

    # Internal Event Mapping
    internal_event_type = Column(String(100), nullable=True, comment="EventType-Wert nach Mapping")

    # Zeitstempel
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    connection = relationship("ERPConnection", backref="inbound_webhook_events")

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_inbound_webhook_provider_event_id"),
        Index("ix_inbound_webhook_provider_status", "provider", "status"),
        {"comment": "Inbound webhook events from external providers (DATEV, carriers)"}
    )

    def __repr__(self) -> str:
        return f"<InboundWebhookEvent {self.provider}/{self.event_type} status={self.status}>"
