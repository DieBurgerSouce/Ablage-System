# -*- coding: utf-8 -*-
"""
Pydantic Schemas fuer Barcode/QR Pipeline API.

Definiert Request- und Response-Modelle fuer die Barcode-Erkennung.

Feinpoliert und durchdacht - Typisierte API-Schemas.
"""

from datetime import datetime
from typing import Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class BarcodeDetectionResponse(BaseModel):
    """Einzelne Barcode-Erkennung."""

    id: UUID
    document_id: UUID
    code_type: str = Field(..., description="Typ des erkannten Codes (z.B. sepa_qr, ean_13)")
    category: str = Field(..., description="Kategorie (payment, product, logistics, document, url, other)")
    raw_value: str = Field(..., description="Rohdaten des erkannten Codes")
    parsed_data: Dict[str, Union[str, float, bool, None]] = Field(
        default_factory=dict,
        description="Geparste/strukturierte Daten",
    )
    position_x: int
    position_y: int
    position_width: int
    position_height: int
    page_number: int = Field(..., ge=1, description="Seitennummer (1-basiert)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Erkennungs-Konfidenz")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BarcodeListResponse(BaseModel):
    """Liste von Barcode-Erkennungen fuer ein Dokument."""

    document_id: UUID
    erkennungen: List[BarcodeDetectionResponse] = Field(
        ..., description="Liste erkannter Codes"
    )
    gesamt: int = Field(..., description="Gesamtanzahl erkannter Codes")
    hat_zahlungscodes: bool = Field(
        False, description="Ob Zahlungs-relevante Codes gefunden wurden"
    )
    hat_produktcodes: bool = Field(
        False, description="Ob Produkt-Codes gefunden wurden"
    )


class BarcodeRedetectRequest(BaseModel):
    """Anfrage zur erneuten Barcode-Erkennung."""

    grund: Optional[str] = Field(
        None,
        max_length=500,
        description="Optionaler Grund fuer die erneute Erkennung",
    )


class BarcodeRedetectResponse(BaseModel):
    """Antwort auf erneute Barcode-Erkennung."""

    document_id: UUID
    nachricht: str = Field(..., description="Status-Nachricht")
    task_id: Optional[str] = Field(
        None, description="Celery Task-ID fuer asynchrone Verarbeitung"
    )
