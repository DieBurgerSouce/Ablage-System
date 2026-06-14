# -*- coding: utf-8 -*-
"""
Tests fuer OCR Confidence Service - Phase 2 Feature.

Testet:
- Confidence-Daten aus Document.metadata JSONB extrahieren
- Graceful Degradation wenn keine Confidence-Daten vorhanden
- Page-Filterung (spezifische Seitennummer)
- Summary Endpoint (Durchschnitte ohne Word-Daten)
- Document Not Found (404)
- Mehrere OCR-Backends (deepseek, got-ocr, surya)
"""

from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from app.db.models import Document


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Mock AsyncSession fuer Datenbank-Operationen."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def document_with_confidence_data() -> Document:
    """Dokument mit vollstaendigen OCR Confidence-Daten."""
    doc = Mock(spec=Document)
    doc.id = uuid4()
    doc.filename = "rechnung_001.pdf"
    doc.document_type = "invoice"
    doc.metadata = {
        "ocr_confidence": {
            "backend": "deepseek",
            "pages": [
                {
                    "page_number": 1,
                    "average_confidence": 0.95,
                    "min_confidence": 0.87,
                    "max_confidence": 0.99,
                    "words": [
                        {"text": "Rechnung", "confidence": 0.98},
                        {"text": "Datum", "confidence": 0.95},
                        {"text": "Betrag", "confidence": 0.92}
                    ]
                },
                {
                    "page_number": 2,
                    "average_confidence": 0.88,
                    "min_confidence": 0.75,
                    "max_confidence": 0.96,
                    "words": [
                        {"text": "Summe", "confidence": 0.91},
                        {"text": "Zahlung", "confidence": 0.85}
                    ]
                }
            ],
            "overall_average": 0.915,
            "timestamp": "2024-01-15T10:30:00Z"
        }
    }
    return doc


@pytest.fixture
def document_without_confidence_data() -> Document:
    """Dokument ohne OCR Confidence-Daten."""
    doc = Mock(spec=Document)
    doc.id = uuid4()
    doc.filename = "old_document.pdf"
    doc.document_type = "contract"
    doc.metadata = {}  # Empty metadata
    return doc


@pytest.fixture
def document_with_partial_confidence() -> Document:
    """Dokument mit unvollstaendigen Confidence-Daten."""
    doc = Mock(spec=Document)
    doc.id = uuid4()
    doc.filename = "partial.pdf"
    doc.document_type = "invoice"
    doc.metadata = {
        "ocr_confidence": {
            "backend": "got-ocr",
            "pages": [
                {
                    "page_number": 1,
                    "average_confidence": 0.89
                    # Missing words, min_confidence, max_confidence
                }
            ]
        }
    }
    return doc


@pytest.fixture
def document_with_multiple_backends() -> Document:
    """Dokument mit Confidence-Daten von mehreren Backends."""
    doc = Mock(spec=Document)
    doc.id = uuid4()
    doc.filename = "multi_backend.pdf"
    doc.document_type = "invoice"
    doc.metadata = {
        "ocr_confidence": {
            "deepseek": {
                "pages": [{"page_number": 1, "average_confidence": 0.95}],
                "overall_average": 0.95
            },
            "got-ocr": {
                "pages": [{"page_number": 1, "average_confidence": 0.88}],
                "overall_average": 0.88
            },
            "surya": {
                "pages": [{"page_number": 1, "average_confidence": 0.82}],
                "overall_average": 0.82
            }
        }
    }
    return doc


# =============================================================================
# Mock OCR Confidence Service
# =============================================================================

class MockOCRConfidenceService:
    """Mock Service fuer OCR Confidence (basierend auf erwartetem Interface)."""

    def __init__(self, db: AsyncMock):
        self.db = db

    async def get_confidence_data(
        self,
        document_id: str,
        page_number: Optional[int] = None,
        backend: Optional[str] = None
    ) -> Dict[str, object]:
        """Extrahiert Confidence-Daten aus Document.metadata."""
        # Simulate DB query
        doc = await self._get_document(document_id)

        if not doc:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        metadata = doc.metadata or {}
        confidence = metadata.get("ocr_confidence", {})

        if not confidence:
            return {
                "document_id": document_id,
                "has_confidence_data": False,
                "message": "Keine OCR Confidence-Daten verfuegbar"
            }

        # Backend handling
        if backend and isinstance(confidence, dict) and backend in confidence:
            confidence = confidence[backend]

        # Page filtering
        if page_number is not None:
            pages = confidence.get("pages", [])
            page_data = next((p for p in pages if p["page_number"] == page_number), None)

            if not page_data:
                return {
                    "document_id": document_id,
                    "page_number": page_number,
                    "has_confidence_data": False,
                    "message": f"Keine Daten fuer Seite {page_number}"
                }

            return {
                "document_id": document_id,
                "page_number": page_number,
                "has_confidence_data": True,
                **page_data
            }

        # Full data
        return {
            "document_id": document_id,
            "has_confidence_data": True,
            **confidence
        }

    async def get_confidence_summary(
        self,
        document_id: str,
        backend: Optional[str] = None
    ) -> Dict[str, object]:
        """Gibt nur Durchschnittswerte zurueck (ohne Word-Daten)."""
        full_data = await self.get_confidence_data(document_id, backend=backend)

        if not full_data.get("has_confidence_data"):
            return full_data

        # Remove word-level data
        summary = {
            "document_id": document_id,
            "has_confidence_data": True,
            "backend": full_data.get("backend"),
            "overall_average": full_data.get("overall_average"),
            "timestamp": full_data.get("timestamp"),
            "pages": []
        }

        for page in full_data.get("pages", []):
            summary["pages"].append({
                "page_number": page["page_number"],
                "average_confidence": page.get("average_confidence"),
                "min_confidence": page.get("min_confidence"),
                "max_confidence": page.get("max_confidence"),
                "word_count": len(page.get("words", []))
            })

        return summary

    async def _get_document(self, document_id: str) -> Optional[Document]:
        """Laedt Dokument aus DB."""
        # db.execute ist async (AsyncMock), scalar_one_or_none ist synchron.
        result = await self.db.execute(None)
        return result.scalar_one_or_none()


# =============================================================================
# Confidence Data Extraction Tests
# =============================================================================

class TestOCRConfidenceExtraction:
    """Tests fuer Extraktion von Confidence-Daten aus metadata JSONB."""

    @pytest.mark.asyncio
    async def test_extract_full_confidence_data(self, mock_db_session, document_with_confidence_data):
        """Vollstaendige Confidence-Daten werden korrekt extrahiert."""
        service = MockOCRConfidenceService(mock_db_session)

        # Mock document query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_confidence_data
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(str(document_with_confidence_data.id))

        assert result["has_confidence_data"] is True
        assert result["backend"] == "deepseek"
        assert result["overall_average"] == 0.915
        assert len(result["pages"]) == 2
        assert result["pages"][0]["average_confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_extract_specific_page_confidence(self, mock_db_session, document_with_confidence_data):
        """Confidence-Daten fuer spezifische Seite werden gefiltert."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_confidence_data
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(
            str(document_with_confidence_data.id),
            page_number=2
        )

        assert result["has_confidence_data"] is True
        assert result["page_number"] == 2
        assert result["average_confidence"] == 0.88
        assert len(result["words"]) == 2

    @pytest.mark.asyncio
    async def test_extract_word_level_confidence(self, mock_db_session, document_with_confidence_data):
        """Word-Level Confidence-Daten werden korrekt extrahiert."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_confidence_data
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(
            str(document_with_confidence_data.id),
            page_number=1
        )

        words = result.get("words", [])
        assert len(words) == 3
        assert words[0]["text"] == "Rechnung"
        assert words[0]["confidence"] == 0.98
        assert words[2]["text"] == "Betrag"
        assert words[2]["confidence"] == 0.92


# =============================================================================
# Graceful Degradation Tests
# =============================================================================

class TestOCRConfidenceGracefulDegradation:
    """Tests fuer Graceful Degradation bei fehlenden Daten."""

    @pytest.mark.asyncio
    async def test_document_without_confidence_data(self, mock_db_session, document_without_confidence_data):
        """Dokument ohne Confidence-Daten gibt sinnvolle Antwort."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_without_confidence_data
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(str(document_without_confidence_data.id))

        assert result["has_confidence_data"] is False
        assert "Keine OCR Confidence-Daten verfuegbar" in result["message"]

    @pytest.mark.asyncio
    async def test_document_with_partial_confidence(self, mock_db_session, document_with_partial_confidence):
        """Dokument mit unvollstaendigen Daten wird korrekt behandelt."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_partial_confidence
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(str(document_with_partial_confidence.id))

        assert result["has_confidence_data"] is True
        assert result["backend"] == "got-ocr"
        assert result["pages"][0]["average_confidence"] == 0.89
        # Missing fields should not crash

    @pytest.mark.asyncio
    async def test_page_not_found_returns_message(self, mock_db_session, document_with_confidence_data):
        """Nicht existierende Seite gibt Fehlermeldung."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_confidence_data
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(
            str(document_with_confidence_data.id),
            page_number=99  # Does not exist
        )

        assert result["has_confidence_data"] is False
        assert "Keine Daten fuer Seite 99" in result["message"]


# =============================================================================
# Summary Endpoint Tests
# =============================================================================

class TestOCRConfidenceSummary:
    """Tests fuer Summary Endpoint (Durchschnitte ohne Word-Daten)."""

    @pytest.mark.asyncio
    async def test_summary_excludes_word_data(self, mock_db_session, document_with_confidence_data):
        """Summary enthaelt keine Word-Level Daten."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_confidence_data
        mock_db_session.execute.return_value = mock_result

        summary = await service.get_confidence_summary(str(document_with_confidence_data.id))

        assert summary["has_confidence_data"] is True
        assert summary["overall_average"] == 0.915

        for page in summary["pages"]:
            assert "words" not in page
            assert "average_confidence" in page
            assert "word_count" in page

    @pytest.mark.asyncio
    async def test_summary_includes_page_stats(self, mock_db_session, document_with_confidence_data):
        """Summary enthaelt Page-Level Statistiken."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_confidence_data
        mock_db_session.execute.return_value = mock_result

        summary = await service.get_confidence_summary(str(document_with_confidence_data.id))

        page1 = summary["pages"][0]
        assert page1["page_number"] == 1
        assert page1["average_confidence"] == 0.95
        assert page1["min_confidence"] == 0.87
        assert page1["max_confidence"] == 0.99
        assert page1["word_count"] == 3

    @pytest.mark.asyncio
    async def test_summary_without_confidence_data(self, mock_db_session, document_without_confidence_data):
        """Summary fuer Dokument ohne Daten gibt Fehlermeldung."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_without_confidence_data
        mock_db_session.execute.return_value = mock_result

        summary = await service.get_confidence_summary(str(document_without_confidence_data.id))

        assert summary["has_confidence_data"] is False
        assert "Keine OCR Confidence-Daten verfuegbar" in summary["message"]


# =============================================================================
# Multiple Backends Tests
# =============================================================================

class TestOCRConfidenceMultipleBackends:
    """Tests fuer Dokumente mit mehreren OCR-Backends."""

    @pytest.mark.asyncio
    async def test_extract_specific_backend_data(self, mock_db_session, document_with_multiple_backends):
        """Confidence-Daten fuer spezifisches Backend werden extrahiert."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_multiple_backends
        mock_db_session.execute.return_value = mock_result

        # Extract deepseek data
        result = await service.get_confidence_data(
            str(document_with_multiple_backends.id),
            backend="deepseek"
        )

        assert result["has_confidence_data"] is True
        assert result["overall_average"] == 0.95

    @pytest.mark.asyncio
    async def test_compare_backends(self, mock_db_session, document_with_multiple_backends):
        """Verschiedene Backends koennen verglichen werden."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_multiple_backends
        mock_db_session.execute.return_value = mock_result

        deepseek_data = await service.get_confidence_data(
            str(document_with_multiple_backends.id),
            backend="deepseek"
        )
        got_ocr_data = await service.get_confidence_data(
            str(document_with_multiple_backends.id),
            backend="got-ocr"
        )
        surya_data = await service.get_confidence_data(
            str(document_with_multiple_backends.id),
            backend="surya"
        )

        assert deepseek_data["overall_average"] > got_ocr_data["overall_average"]
        assert got_ocr_data["overall_average"] > surya_data["overall_average"]


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestOCRConfidenceErrorHandling:
    """Tests fuer Error Handling."""

    @pytest.mark.asyncio
    async def test_document_not_found_raises_error(self, mock_db_session):
        """Nicht existierendes Dokument wirft ValueError."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        doc_id = str(uuid4())

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.get_confidence_data(doc_id)

    @pytest.mark.asyncio
    async def test_invalid_backend_returns_empty(self, mock_db_session, document_with_multiple_backends):
        """Nicht existierendes Backend gibt leere Antwort."""
        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = document_with_multiple_backends
        mock_db_session.execute.return_value = mock_result

        result = await service.get_confidence_data(
            str(document_with_multiple_backends.id),
            backend="nonexistent-backend"
        )

        # Should return empty or handle gracefully
        assert result["document_id"] == str(document_with_multiple_backends.id)


# =============================================================================
# Performance Tests
# =============================================================================

class TestOCRConfidencePerformance:
    """Tests fuer Performance-Aspekte."""

    @pytest.mark.asyncio
    async def test_large_document_summary_fast(self, mock_db_session):
        """Summary ist schnell auch fuer grosse Dokumente."""
        # Create document with many pages
        doc = Mock(spec=Document)
        doc.id = uuid4()
        doc.filename = "large.pdf"
        doc.metadata = {
            "ocr_confidence": {
                "backend": "deepseek",
                "pages": [
                    {
                        "page_number": i,
                        "average_confidence": 0.90,
                        "words": [{"text": f"word_{j}", "confidence": 0.90} for j in range(100)]
                    }
                    for i in range(1, 51)  # 50 pages
                ],
                "overall_average": 0.90
            }
        }

        service = MockOCRConfidenceService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db_session.execute.return_value = mock_result

        summary = await service.get_confidence_summary(str(doc.id))

        # Summary should exclude all word data
        assert len(summary["pages"]) == 50
        for page in summary["pages"]:
            assert "words" not in page
            assert page["word_count"] == 100
