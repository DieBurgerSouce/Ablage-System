"""
Executive Reporting API Schemas

Pydantic Schemas für Geschäftsführung Dashboard und Reporting.
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# KPI Response Schema
# =============================================================================

class KPIResponse(BaseModel):
    """Key Performance Indicators für Dashboard."""

    documents_this_month: int = Field(
        ...,
        description="Anzahl Dokumente im aktuellen Monat"
    )
    documents_last_month: int = Field(
        ...,
        description="Anzahl Dokumente im letzten Monat"
    )
    documents_trend_percent: float = Field(
        ...,
        description="Trend in Prozent (positiv = Anstieg)"
    )
    avg_processing_time_ms: float = Field(
        ...,
        description="Durchschnittliche Verarbeitungszeit in Millisekunden"
    )
    processing_time_trend_percent: float = Field(
        ...,
        description="Trend der Verarbeitungszeit in Prozent"
    )
    ocr_accuracy: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Durchschnittliche OCR-Genauigkeit (0-1)"
    )
    ocr_accuracy_trend: float = Field(
        ...,
        description="Trend der OCR-Genauigkeit in Prozent"
    )
    cost_per_document: float = Field(
        ...,
        description="Geschätzte Kosten pro Dokument basierend auf Verarbeitungszeit"
    )
    active_users_count: int = Field(
        ...,
        description="Anzahl aktiver Benutzer im aktuellen Monat"
    )
    pending_reviews: int = Field(
        ...,
        description="Anzahl ausstehender Prüfungen"
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Department Breakdown Schema
# =============================================================================

class DepartmentBreakdown(BaseModel):
    """Abteilungs-/Bereichsstatistiken."""

    department: str = Field(
        ...,
        description="Name der Abteilung/des Bereichs"
    )
    document_count: int = Field(
        ...,
        description="Anzahl Dokumente"
    )
    avg_processing_time_ms: float = Field(
        ...,
        description="Durchschnittliche Verarbeitungszeit in Millisekunden"
    )
    accuracy: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Durchschnittliche OCR-Genauigkeit"
    )
    pending_count: int = Field(
        ...,
        description="Anzahl ausstehender Dokumente"
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Trend Data Schemas
# =============================================================================

class TrendDataPoint(BaseModel):
    """Einzelner Datenpunkt in einer Zeitreihe."""

    date: str = Field(
        ...,
        description="Datum im ISO-Format (YYYY-MM-DD)"
    )
    value: float = Field(
        ...,
        description="Wert an diesem Datum"
    )

    model_config = ConfigDict(from_attributes=True)


class TrendResponse(BaseModel):
    """Zeitreihen-Daten für Trendanalyse."""

    metric: str = Field(
        ...,
        description="Name der Metrik (documents, processing_time, accuracy)"
    )
    data: List[TrendDataPoint] = Field(
        ...,
        description="Zeitreihen-Datenpunkte"
    )
    period_days: int = Field(
        ...,
        description="Anzahl Tage im Zeitraum"
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Executive Summary Schema
# =============================================================================

class ExecutiveSummaryResponse(BaseModel):
    """Gesamtübersicht für Geschäftsführung."""

    kpis: KPIResponse = Field(
        ...,
        description="Key Performance Indicators"
    )
    departments: List[DepartmentBreakdown] = Field(
        ...,
        description="Statistiken nach Abteilungen/Bereichen"
    )
    document_trend: TrendResponse = Field(
        ...,
        description="Trend der Dokumentenanzahl"
    )
    processing_trend: TrendResponse = Field(
        ...,
        description="Trend der Verarbeitungszeit"
    )
    generated_at: str = Field(
        ...,
        description="Zeitpunkt der Generierung (ISO-Format)"
    )

    model_config = ConfigDict(from_attributes=True)
