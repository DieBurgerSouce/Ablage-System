# -*- coding: utf-8 -*-
"""
Document Lineage Services.

Tracking der Datenherkunft und Verarbeitungshistorie von Dokumenten.
"""

from app.services.lineage.document_lineage_service import (
    DocumentLineageService,
    get_lineage_service,
    LineageStats,
    TimelineEntry,
)
from app.services.lineage.integration import (
    LineageProcessingStep,
    record_document_import,
    record_ocr_result,
    record_classification,
    record_entity_linking,
    record_document_modification,
    record_document_export,
    track_lineage,
)

__all__ = [
    # Service
    "DocumentLineageService",
    "get_lineage_service",
    "LineageStats",
    "TimelineEntry",
    # Integration helpers
    "LineageProcessingStep",
    "record_document_import",
    "record_ocr_result",
    "record_classification",
    "record_entity_linking",
    "record_document_modification",
    "record_document_export",
    "track_lineage",
]
