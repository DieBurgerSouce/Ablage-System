# -*- coding: utf-8 -*-
"""
Outbound Webhook Event Platform - Satellite Models.

Implementiert das vollstaendige Outbound-Webhook-System:
- WebhookEndpoint: Registrierte Empfaenger-URLs mit HMAC-Signierung
- WebhookDelivery: Zustellungsprotokoll mit Retry-Tracking und DLQ
- WebhookEventLog: Event-Journal fuer Replay-Funktionalitaet

Satellite-Modell - importiert Base und CrossDBJSON aus app.db.models.
Feinpoliert und durchdacht - Enterprise-grade Outbound Webhook Tracking.
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class WebhookEndpoint(Base):
    """Registrierter Webhook-Empfaenger eines Mandanten.

    Speichert die Konfiguration fuer Outbound-Webhook-Zustellungen:
    - Ziel-URL und benutzerdefinierte Header
    - Abonnierte Event-Typen (leer = alle Events)
    - HMAC-SHA256 Secret als sicherer Hash (nie im Klartext)
    - Retry-Richtlinien und Aktivierungsstatus

    Sicherheit:
    - Das Webhook-Secret wird NIEMALS im Klartext gespeichert oder geloggt
    - Die URL wird vor der Zustellung auf SSRF validiert
    """

    __tablename__ = "webhook_endpoints"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutiger Endpoint-Bezeichner",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandant (Multi-Tenancy)",
    )

    # Zielkonfiguration
    url = Column(
        String(2000),
        nullable=False,
        comment="Ziel-URL fuer Webhook-Zustellungen (max 2000 Zeichen)",
    )
    description = Column(
        Text,
        nullable=True,
        comment="Optionale Beschreibung des Endpoints",
    )

    # Sicherheit - Secret wird als HMAC-Hash gespeichert, NIE im Klartext
    secret_hash = Column(
        String(256),
        nullable=False,
        comment="HMAC-SHA256 Hash des Webhook-Secrets (nie Klartext)",
    )

    # Event-Filter
    event_types = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Abonnierte Event-Typen, z.B. [\"document.created\"]. Leer = alle Events.",
    )

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Aktiv/Inaktiv-Schalter fuer Soft-Delete",
    )

    # Benutzerdefinierte HTTP-Header
    headers = Column(
        CrossDBJSON,
        nullable=True,
        comment="Optionale benutzerdefinierte HTTP-Header fuer Zustellungen",
    )

    # Retry-Konfiguration
    retry_policy = Column(
        CrossDBJSON,
        nullable=False,
        default=lambda: {
            "max_retries": 3,
            "backoff_factor": 2,
            "timeout_seconds": 30,
        },
        comment="Retry-Richtlinie: {max_retries, backoff_factor, timeout_seconds}",
    )

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Beziehungen
    company = relationship("Company", backref="webhook_endpoints")
    deliveries = relationship(
        "WebhookDelivery",
        back_populates="endpoint",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    __table_args__ = (
        Index("ix_webhook_endpoints_company_active", "company_id", "is_active"),
        {"comment": "Registrierte Outbound-Webhook-Endpoints pro Mandant"},
    )

    def __repr__(self) -> str:
        return (
            f"<WebhookEndpoint id={str(self.id)[:8]} "
            f"company={str(self.company_id)[:8]} "
            f"active={self.is_active}>"
        )


class WebhookDelivery(Base):
    """Zustellungsprotokoll fuer einen einzelnen Webhook-Aufruf.

    Verfolgt jeden Zustellversuch von der Erstellung bis zur
    Bestaetigung oder zum Eintrag in die Dead Letter Queue.

    Status-Lebenszyklus:
        pending -> delivered (HTTP 2xx empfangen)
        pending -> failed (alle Versuche erschoepft, kein DLQ)
        pending -> dlq (max_attempts erreicht -> Dead Letter Queue)

    Sicherheit:
    - response_body wird auf 1000 Zeichen gekuerzt
    - Secrets werden NIEMALS im Payload oder Logs gespeichert
    """

    __tablename__ = "webhook_deliveries"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutiger Zustellungs-Bezeichner",
    )
    endpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Zugehoerige Endpoint-Konfiguration",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandant fuer Multi-Tenancy-Isolation",
    )

    # Event-Referenz
    event_type = Column(
        String(100),
        nullable=False,
        comment="Event-Typ, z.B. document.created",
    )
    event_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Referenz auf den Quell-Event (WebhookEventLog.id)",
    )

    # Payload
    payload = Column(
        CrossDBJSON,
        nullable=False,
        comment="Vollstaendiges Event-Payload (wird signiert und zugestellt)",
    )

    # Zustellstatus
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Zustellstatus: pending, delivered, failed, dlq",
    )

    # Versuchszaehler
    attempts = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl durchgefuehrter Zustellversuche",
    )
    max_attempts = Column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximale Anzahl Versuche bevor DLQ",
    )

    # HTTP-Antwort (gesanitized)
    response_status_code = Column(
        Integer,
        nullable=True,
        comment="HTTP-Statuscode der letzten Antwort",
    )
    response_body = Column(
        Text,
        nullable=True,
        comment="Gekuerzte HTTP-Antwort (max 1000 Zeichen, keine Secrets)",
    )

    # Timing
    last_attempt_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitstempel des letzten Zustellversuchs",
    )
    next_retry_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Geplanter Zeitpunkt fuer den naechsten Retry",
    )
    delivered_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitstempel der erfolgreichen Zustellung",
    )

    # Erstellungszeitpunkt
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Beziehungen
    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")
    company = relationship("Company", backref="webhook_deliveries")

    __table_args__ = (
        Index("ix_webhook_deliveries_endpoint_status", "endpoint_id", "status"),
        Index(
            "ix_webhook_deliveries_retry",
            "status",
            "next_retry_at",
            postgresql_where=text(
                "status IN ('pending', 'failed') AND next_retry_at IS NOT NULL"
            ),
        ),
        Index("ix_webhook_deliveries_company_event", "company_id", "event_type"),
        {"comment": "Zustellungsprotokoll fuer Outbound-Webhook-Events"},
    )

    def __repr__(self) -> str:
        return (
            f"<WebhookDelivery id={str(self.id)[:8]} "
            f"event={self.event_type} "
            f"status={self.status} "
            f"attempts={self.attempts}>"
        )


class WebhookEventLog(Base):
    """Event-Journal fuer Replay-Funktionalitaet.

    Speichert alle publizierten Events mandantengetrennt als
    unveraenderliches Protokoll. Ermoeglicht:
    - Gezielten Replay einzelner Events
    - Bulk-Replay nach Event-Typ und Zeitraum
    - Audit-Trail fuer alle Webhook-Events

    Dieses Modell ist append-only - keine Updates nach der Erstellung.
    """

    __tablename__ = "webhook_event_log"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutiger Event-Bezeichner",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandant fuer Multi-Tenancy-Isolation",
    )

    # Event-Klassifikation
    event_type = Column(
        String(100),
        nullable=False,
        comment="Event-Typ, z.B. document.created, invoice.updated",
    )

    # Quell-Referenz
    source_table = Column(
        String(100),
        nullable=False,
        comment="Quell-Tabelle des Events, z.B. documents, invoices",
    )
    source_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Primaerschluessel des ausloesenden Datensatzes",
    )

    # Event-Payload (vollstaendig, fuer Replay)
    payload = Column(
        CrossDBJSON,
        nullable=False,
        comment="Vollstaendiges Event-Payload fuer spaetere Replay-Zustellungen",
    )

    # Zeitstempel (append-only, kein updated_at)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Beziehungen
    company = relationship("Company", backref="webhook_event_log")

    __table_args__ = (
        Index(
            "ix_webhook_event_log_company_type",
            "company_id",
            "event_type",
            "created_at",
        ),
        Index(
            "ix_webhook_event_log_source",
            "company_id",
            "source_table",
            "source_id",
        ),
        {"comment": "Unveraenderbares Event-Journal fuer Webhook-Replay"},
    )

    def __repr__(self) -> str:
        return (
            f"<WebhookEventLog id={str(self.id)[:8]} "
            f"event={self.event_type} "
            f"source={self.source_table}/{str(self.source_id)[:8]}>"
        )
