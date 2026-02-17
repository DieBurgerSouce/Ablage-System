# -*- coding: utf-8 -*-
"""
Pydantic Schemas fuer Duplikat-Erkennungs-API.

Definiert Request- und Response-Modelle fuer die Duplikat-Erkennung.

Feinpoliert und durchdacht - Typisierte API-Schemas.
"""

from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DuplicateCheckRequest(BaseModel):
    """Anfrage zur Duplikat-Pruefung eines Dokuments."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID = Field(..., description="ID des zu pruefenden Dokuments")
    company_id: Optional[UUID] = Field(
        None,
        description="Optional: Company-Filter fuer mandantenspezifische Pruefung",
    )
    include_near: bool = Field(
        True,
        description="Ob Near-Duplicate-Check (Text-Aehnlichkeit) durchgefuehrt werden soll",
    )


class DuplicateMatch(BaseModel):
    """Ein gefundenes Duplikat."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID = Field(..., description="ID des Duplikat-Dokuments")
    duplicate_type: str = Field(
        ...,
        description="Typ des Duplikats (exact, near, semantic, number_match, visual)",
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aehnlichkeits-Score (0.0 = komplett anders, 1.0 = identisch)",
    )
    matched_fields: List[str] = Field(
        default_factory=list,
        description="Liste der uebereinstimmenden Felder",
    )
    details: Optional[Dict[str, str]] = Field(
        None,
        description="Optionale Details zum Match (z.B. Hash, Dateiname)",
    )


class DuplicateCheckResponse(BaseModel):
    """Ergebnis der Duplikat-Pruefung."""

    model_config = ConfigDict(from_attributes=True)

    has_duplicates: bool = Field(
        ...,
        description="Ob Duplikate gefunden wurden",
    )
    candidates: List[DuplicateMatch] = Field(
        default_factory=list,
        description="Liste aller gefundenen Duplikat-Kandidaten",
    )
    best_match: Optional[DuplicateMatch] = Field(
        None,
        description="Bester Treffer (hoechster Aehnlichkeits-Score)",
    )
    processing_time_ms: int = Field(
        ...,
        ge=0,
        description="Verarbeitungsdauer in Millisekunden",
    )


class BatchScanRequest(BaseModel):
    """Anfrage fuer einen Batch-Duplikat-Scan."""

    model_config = ConfigDict(from_attributes=True)

    company_id: UUID = Field(
        ...,
        description="Company-ID fuer den Batch-Scan (alle Dokumente dieser Firma)",
    )


class BatchScanResponse(BaseModel):
    """Antwort auf einen gestarteten Batch-Duplikat-Scan."""

    model_config = ConfigDict(from_attributes=True)

    task_id: str = Field(..., description="Celery Task-ID fuer den asynchronen Scan")
    message: str = Field(..., description="Status-Nachricht")


class DuplicateStatsResponse(BaseModel):
    """Statistiken zur Duplikat-Erkennung."""

    model_config = ConfigDict(from_attributes=True)

    total_documents: int = Field(
        ...,
        ge=0,
        description="Gesamtanzahl der Dokumente",
    )
    total_duplicates_found: int = Field(
        ...,
        ge=0,
        description="Anzahl als Duplikat markierter Dokumente",
    )
    by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Aufschluesselung nach Duplikat-Typ",
    )
    avg_similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Durchschnittlicher Aehnlichkeits-Score aller Duplikate",
    )


class DuplicateConfigUpdate(BaseModel):
    """Aktualisierung der Duplikat-Erkennungs-Konfiguration."""

    model_config = ConfigDict(from_attributes=True)

    min_similarity_near: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimale Aehnlichkeit fuer Near-Duplicates (Standard: 0.85)",
    )
    min_similarity_semantic: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimale Aehnlichkeit fuer semantische Duplikate (Standard: 0.70)",
    )
    max_candidates: Optional[int] = Field(
        None,
        ge=1,
        le=500,
        description="Maximale Anzahl von Kandidaten pro Pruefung (Standard: 50)",
    )
    max_text_length: Optional[int] = Field(
        None,
        ge=100,
        le=100000,
        description="Maximale Textlaenge fuer Vergleich in Zeichen (Standard: 10000)",
    )


class DuplicateConfigResponse(BaseModel):
    """Aktuelle Konfiguration der Duplikat-Erkennung."""

    model_config = ConfigDict(from_attributes=True)

    min_similarity_near: float = Field(
        ...,
        description="Minimale Aehnlichkeit fuer Near-Duplicates",
    )
    min_similarity_semantic: float = Field(
        ...,
        description="Minimale Aehnlichkeit fuer semantische Duplikate",
    )
    max_candidates: int = Field(
        ...,
        description="Maximale Anzahl von Kandidaten pro Pruefung",
    )
    max_text_length: int = Field(
        ...,
        description="Maximale Textlaenge fuer Vergleich in Zeichen",
    )
