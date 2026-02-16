"""Document Filter Service - Query-Bau und Filterung.

Enthält Logik für:
- Filter-Bedingungen erstellen
- Sortier-Spalten ermitteln
- Komplexe Queries aufbauen
"""

from typing import List

from app.db.models import Document
from app.db.schemas import SearchFilters, SortField


class DocumentFilterService:
    """Service für Dokumentenfilterung und Query-Bau.

    Trennt die Query-Logik von der Datenbankzugriffs-Logik
    für bessere Testbarkeit und Wiederverwendung.
    """

    def build_filter_conditions(self, filters: SearchFilters) -> List:
        """SQLAlchemy-Filter-Bedingungen erstellen.

        Args:
            filters: SearchFilters-Objekt mit Filterkriterien

        Returns:
            Liste von SQLAlchemy-Bedingungen
        """
        conditions = []

        if filters.document_type:
            conditions.append(Document.document_type == filters.document_type.value)

        if filters.status:
            conditions.append(Document.status == filters.status.value)

        if filters.date_from:
            conditions.append(Document.created_at >= filters.date_from)

        if filters.date_to:
            conditions.append(Document.created_at <= filters.date_to)

        if filters.confidence_min is not None:
            conditions.append(Document.ocr_confidence >= filters.confidence_min)

        if filters.has_embedding is not None:
            if filters.has_embedding:
                conditions.append(Document.embedding.isnot(None))
            else:
                conditions.append(Document.embedding.is_(None))

        if filters.language:
            conditions.append(Document.detected_language == filters.language)

        return conditions

    def get_sort_column(self, sort_by: SortField):
        """Spalte für Sortierung ermitteln.

        Args:
            sort_by: SortField-Enum-Wert

        Returns:
            SQLAlchemy-Spalte für ORDER BY
        """
        sort_map = {
            SortField.CREATED_AT: Document.created_at,
            SortField.UPDATED_AT: Document.updated_at,
            SortField.FILENAME: Document.filename,
            SortField.FILE_SIZE: Document.file_size,
            SortField.OCR_CONFIDENCE: Document.ocr_confidence,
            SortField.RELEVANCE: Document.created_at  # Fallback
        }
        return sort_map.get(sort_by, Document.created_at)


# Singleton-Instanz
_filter_service_instance: DocumentFilterService = None


def get_filter_service() -> DocumentFilterService:
    """Filter-Service-Instanz abrufen (Singleton)."""
    global _filter_service_instance
    if _filter_service_instance is None:
        _filter_service_instance = DocumentFilterService()
    return _filter_service_instance
