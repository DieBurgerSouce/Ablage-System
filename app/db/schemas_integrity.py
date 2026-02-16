# -*- coding: utf-8 -*-
"""
Pydantic Schemas für Dokument-Integrität (Hash-Chain).

Request- und Response-Modelle für die Integritäts-API.
"""

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VerificationStatusEnum(str, Enum):
    """Verifizierungsstatus eines Dokuments."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    TAMPERED = "tampered"


class IntegrityStatusResponse(BaseModel):
    """Antwort mit dem Integritätsstatus eines Dokuments."""

    document_id: UUID
    file_hash: str
    hash_algorithm: str
    file_size_bytes: int
    computed_at: datetime
    verified_at: Optional[datetime] = None
    verification_status: VerificationStatusEnum

    model_config = ConfigDict(from_attributes=True)


class IntegrityVerifyResponse(BaseModel):
    """Antwort nach Verifizierung eines Dokuments."""

    document_id: UUID
    is_valid: bool
    message: str  # Deutsche Meldung
    stored_hash: str
    computed_hash: str
    verified_at: datetime


class MerkleBuildRequest(BaseModel):
    """Anfrage zum Erstellen eines täglichen Merkle-Baums."""

    tree_date: date = Field(..., description="Datum für den Merkle-Baum")


class MerkleBuildResponse(BaseModel):
    """Antwort nach Erstellung eines Merkle-Baums."""

    tree_date: date
    merkle_root: str
    document_count: int
    message: str


class MerkleProofResponse(BaseModel):
    """Antwort mit Merkle-Beweis für ein Dokument."""

    document_id: UUID
    is_included: bool
    proof_path: List[str]
    merkle_root: str
    tree_date: date
    message: str


class IntegrityReportRequest(BaseModel):
    """Anfrage zur Erstellung eines Integritätsberichts."""

    report_date: Optional[date] = Field(
        None,
        description="Berichtsdatum (Standard: heute)",
    )


class IntegrityReportResponse(BaseModel):
    """Antwort mit einem Integritätsbericht."""

    id: UUID
    report_date: date
    total_documents: int
    verified_count: int
    tampered_count: int
    unverified_count: int
    merkle_root: str
    generated_at: datetime
    report_data: Dict[str, object]

    model_config = ConfigDict(from_attributes=True)
