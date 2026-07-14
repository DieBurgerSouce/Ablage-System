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


class ProofVerdictEnum(str, Enum):
    """Gesamturteil einer Dokument-Beweisführung."""

    VERIFIED = "verified"
    TAMPERED = "tampered"
    NO_BASELINE = "no_baseline"


class ChainProofInfo(BaseModel):
    """Ergebnis der Beweisketten-Prüfung (Audit-Chain) für ein Dokument."""

    entries_total: int
    entries_verified: int
    valid: Optional[bool] = Field(
        None, description="None = keine Ketten-Einträge für dieses Dokument"
    )
    broken_at_sequence: Optional[int] = None
    first_entry_at: Optional[datetime] = None
    last_entry_at: Optional[datetime] = None
    message: str  # Deutsche Meldung


class TsaProofInfo(BaseModel):
    """Ergebnis der RFC-3161-Zeitstempel-Prüfung."""

    present: bool
    valid: Optional[bool] = Field(
        None, description="None = nicht prüfbar (kein Token oder Prüf-Fehler)"
    )
    message: str  # Deutsche Meldung


class DocumentProofResponse(BaseModel):
    """Antwort der Live-Beweisführung für ein Dokument.

    Bewusst differenziert statt eines Pauschal-Booleans: Datei-Hash,
    Beweiskette und Zeitstempel werden einzeln ausgewiesen.
    """

    document_id: UUID
    verdict: ProofVerdictEnum
    file_hash_matches: Optional[bool] = Field(
        None, description="None = keine Baseline vorhanden"
    )
    baseline_source: Optional[str] = Field(
        None, description='"archiv" | "integritaets_hash" | None'
    )
    stored_hash: Optional[str] = None
    computed_hash: Optional[str] = None
    hash_algorithm: str = "sha256"
    archived_at: Optional[datetime] = None
    archive_id: Optional[UUID] = None
    chain: ChainProofInfo
    tsa: TsaProofInfo
    verified_at: datetime
    message_de: str


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
