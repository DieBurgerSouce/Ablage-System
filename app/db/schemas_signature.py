# -*- coding: utf-8 -*-
"""
Pydantic Schemas fuer QES/eIDAS Signaturen.

Validierung und Serialisierung fuer:
- Signaturanfragen (Create, Response, List)
- Signatureintraege (Sign, Reject, Response)
- Verifikation und Audit-Trail
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Enums (Pydantic-kompatibel)
# ============================================================================


class SignatureLevelEnum(str, Enum):
    """Signaturniveau nach eIDAS."""
    SIMPLE = "simple"
    ADVANCED = "advanced"
    QUALIFIED = "qualified"


class SignatureStatusEnum(str, Enum):
    """Status einer Signatur."""
    PENDING = "pending"
    REQUESTED = "requested"
    SIGNED = "signed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SignatureProviderEnum(str, Enum):
    """Signaturanbieter."""
    D_TRUST = "d_trust"
    SIGN_ME = "sign_me"
    SWISSCOM_AIS = "swisscom_ais"
    INTERNAL = "internal"


# ============================================================================
# Request Schemas
# ============================================================================


class SignerCreate(BaseModel):
    """Schema zum Anlegen eines Unterzeichners."""
    email: str = Field(..., description="E-Mail des Unterzeichners")
    name: str = Field(..., description="Name des Unterzeichners")
    user_id: Optional[UUID] = Field(
        None, description="Interne User-ID (optional)"
    )
    signing_order: int = Field(
        1, description="Reihenfolge bei sequentiellem Signieren"
    )


class SignatureRequestCreate(BaseModel):
    """Schema zum Erstellen einer Signaturanfrage."""
    document_id: UUID
    title: str = Field(
        ..., max_length=255, description="Titel der Signaturanfrage"
    )
    description: Optional[str] = None
    signature_level: SignatureLevelEnum = SignatureLevelEnum.ADVANCED
    provider: SignatureProviderEnum = SignatureProviderEnum.INTERNAL
    signers: List[SignerCreate] = Field(..., min_length=1)
    signing_order_required: bool = False
    expires_in_days: int = Field(30, ge=1, le=365)


class SignEntryRequest(BaseModel):
    """Schema zum Signieren eines Dokuments."""
    certificate_issuer: Optional[str] = None
    certificate_serial: Optional[str] = None


class RejectSignatureRequest(BaseModel):
    """Schema zum Ablehnen einer Signatur."""
    reason: str = Field(
        ..., min_length=1, description="Ablehnungsgrund"
    )


# ============================================================================
# Response Schemas
# ============================================================================


class SignatureEntryResponse(BaseModel):
    """Response-Schema fuer einen Signatureintrag."""
    id: UUID
    signer_email: str
    signer_name: str
    signing_order: int
    status: SignatureStatusEnum
    signed_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    certificate_issuer: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SignatureRequestResponse(BaseModel):
    """Response-Schema fuer eine Signaturanfrage."""
    id: UUID
    document_id: UUID
    title: str
    description: Optional[str] = None
    signature_level: SignatureLevelEnum
    provider: SignatureProviderEnum
    status: SignatureStatusEnum
    requested_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    signing_order_required: bool
    entries: List[SignatureEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SignatureRequestListResponse(BaseModel):
    """Paginierte Liste von Signaturanfragen."""
    items: List[SignatureRequestResponse]
    total: int
    page: int
    per_page: int


class SignatureVerificationResponse(BaseModel):
    """Ergebnis der Signaturverifikation."""
    document_id: UUID
    is_fully_signed: bool
    total_signatures: int
    completed_signatures: int
    pending_signatures: int
    rejected_signatures: int
    message: str


class SignatureAuditResponse(BaseModel):
    """Response-Schema fuer einen Audit-Eintrag."""
    id: UUID
    action: str
    performed_at: datetime
    ip_address: Optional[str] = None
    details_json: Optional[Dict[str, object]] = None

    model_config = ConfigDict(from_attributes=True)
