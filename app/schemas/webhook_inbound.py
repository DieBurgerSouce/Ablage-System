# -*- coding: utf-8 -*-
"""
Inbound Webhook Schemas.

Pydantic-Modelle für den generischen Inbound-Webhook-Empfänger.
Validierung, Serialisierung und Response-Modelle.

Feinpoliert und durchdacht - Type-safe Webhook Processing.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InboundWebhookProvider(str, Enum):
    """Unterstützte Inbound-Webhook-Provider."""
    DATEV = "datev"
    DHL = "dhl"
    DPD = "dpd"
    UPS = "ups"
    GLS = "gls"


class InboundWebhookAction(str, Enum):
    """Mögliche Webhook-Aktionen."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    STATUS_CHANGE = "status_change"


class InboundWebhookStatus(str, Enum):
    """Verarbeitungsstatus eines Inbound-Webhook-Events."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    IGNORED = "ignored"


class InboundWebhookPayload(BaseModel):
    """Eingehendes Webhook-Payload (generisch für alle Provider)."""
    event_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Eindeutige Event-ID vom Provider (Idempotenz)"
    )
    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Provider-spezifischer Event-Typ"
    )
    action: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Aktion: create, update, delete, status_change"
    )
    timestamp: Optional[datetime] = Field(
        None,
        description="Zeitstempel des Events beim Provider"
    )
    data: Dict[str, object] = Field(
        default_factory=dict,
        description="Provider-spezifische Event-Daten"
    )
    external_ref: Optional[str] = Field(
        None,
        max_length=255,
        description="Externe Referenz (Tracking-Nr, Rechnungs-Nr, etc.)"
    )

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        """Validiert Event-ID: Nur sichere Zeichen erlaubt."""
        if not re.match(r"^[A-Za-z0-9._\-:]+$", v):
            raise ValueError("Event-ID enthält ungültige Zeichen")
        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Validiert Aktion gegen erlaubte Werte."""
        allowed = {"create", "update", "delete", "status_change"}
        if v not in allowed:
            raise ValueError(f"Ungültige Aktion: {v}. Erlaubt: {', '.join(sorted(allowed))}")
        return v


class InboundWebhookResponse(BaseModel):
    """Antwort nach Webhook-Empfang."""
    success: bool
    event_id: str
    message: str
    task_id: Optional[str] = None


class InboundWebhookEventSummary(BaseModel):
    """Zusammenfassung eines gespeicherten Webhook-Events."""
    id: UUID
    provider: str
    event_id: str
    event_type: str
    action: str
    status: str
    external_ref: Optional[str] = None
    internal_event_type: Optional[str] = None
    received_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    attempts: int = 0
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class InboundWebhookEventList(BaseModel):
    """Liste von Inbound-Webhook-Events."""
    events: List[InboundWebhookEventSummary]
    total: int
