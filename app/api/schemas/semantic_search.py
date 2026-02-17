# -*- coding: utf-8 -*-
"""Pydantic-Schemas fuer die Semantische Suche.

Definiert Request/Response-Modelle fuer:
- Semantische Dokumentensuche (natuerlichsprachlich)
- Aehnliche Dokumente finden
- Embedding-Abdeckungsstatistiken
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Request Schemas
# ============================================================================


class SemanticSearchRequest(BaseModel):
    """Anfrage fuer semantische Suche."""
    query: str = Field(
        ...,
        min_length=2,
        max_length=2000,
        description="Natuerlichsprachliche Suchanfrage",
    )
    limit: int = Field(20, ge=1, le=100, description="Maximale Ergebnisanzahl")
    threshold: float = Field(
        0.5, ge=0.0, le=1.0, description="Minimaler Aehnlichkeitsscore"
    )
    document_type: Optional[str] = Field(
        None, description="Dokumenttyp-Filter (z.B. invoice, contract)"
    )
    date_from: Optional[datetime] = Field(
        None, description="Dokumente nach diesem Datum"
    )
    date_to: Optional[datetime] = Field(
        None, description="Dokumente vor diesem Datum"
    )


class SimilarDocumentsRequest(BaseModel):
    """Anfrage fuer aehnliche Dokumente."""
    limit: int = Field(10, ge=1, le=50, description="Maximale Ergebnisanzahl")
    threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Minimaler Aehnlichkeitsscore"
    )


class BatchEmbedRequest(BaseModel):
    """Anfrage fuer Batch-Embedding-Generierung."""
    batch_size: int = Field(
        100, ge=1, le=500, description="Batch-Groesse fuer Verarbeitung"
    )


# ============================================================================
# Response Schemas
# ============================================================================


class SemanticSearchResultItem(BaseModel):
    """Einzelnes Ergebnis der semantischen Suche."""
    document_id: uuid.UUID
    filename: str
    original_filename: Optional[str] = None
    document_type: Optional[str] = None
    similarity: float = Field(
        ..., ge=0.0, le=1.0, description="Kosinus-Aehnlichkeit"
    )
    created_at: Optional[datetime] = None
    text_preview: Optional[str] = Field(
        None, max_length=500, description="Vorschau des extrahierten Textes"
    )
    page_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SemanticSearchResponse(BaseModel):
    """Antwort der semantischen Suche."""
    query: str
    total: int = Field(..., description="Gesamtanzahl der Treffer")
    results: List[SemanticSearchResultItem]
    search_time_ms: float = Field(
        ..., description="Suchzeit in Millisekunden"
    )
    embedding_model: str = Field(
        ..., description="Verwendetes Embedding-Modell"
    )
    threshold_applied: float


class SimilarDocumentResultItem(BaseModel):
    """Aehnliches Dokument."""
    document_id: uuid.UUID
    filename: str
    document_type: Optional[str] = None
    similarity: float = Field(
        ..., ge=0.0, le=1.0, description="Kosinus-Aehnlichkeit"
    )
    created_at: Optional[datetime] = None
    text_preview: Optional[str] = Field(
        None, max_length=500, description="Vorschau des extrahierten Textes"
    )

    model_config = ConfigDict(from_attributes=True)


class SimilarDocumentsResponse(BaseModel):
    """Antwort fuer aehnliche Dokumente."""
    source_document_id: uuid.UUID
    total: int
    results: List[SimilarDocumentResultItem]
    search_time_ms: float


class EmbeddingCoverageStats(BaseModel):
    """Statistik zur Embedding-Abdeckung."""
    total_documents: int = Field(
        ..., description="Gesamtanzahl Dokumente"
    )
    documents_with_embedding: int = Field(
        ..., description="Dokumente mit Embedding"
    )
    documents_without_embedding: int = Field(
        ..., description="Dokumente ohne Embedding"
    )
    coverage_percent: float = Field(
        ..., ge=0.0, le=100.0, description="Abdeckung in Prozent"
    )
    embedding_model: str = Field(
        ..., description="Aktuelles Embedding-Modell"
    )
    oldest_embedding: Optional[datetime] = Field(
        None, description="Aeltestes Embedding-Datum"
    )
    newest_embedding: Optional[datetime] = Field(
        None, description="Neuestes Embedding-Datum"
    )


class BatchEmbedResponse(BaseModel):
    """Antwort fuer Batch-Embedding-Task."""
    task_id: str = Field(
        ..., description="Celery Task-ID fuer Statusabfrage"
    )
    message: str
