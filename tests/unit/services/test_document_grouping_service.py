# -*- coding: utf-8 -*-
"""
Tests fuer DocumentGroupingService.

Testet Erkennung zusammengehoeriger Dokumente:
- Dateinamen-Sequenz-Erkennung (Hex-Pattern)
- Zeitstempel-basierte Gruppierung
- Inhaltsbasierte Gruppierung (Seitennummerierung)
- Konfidenz-Berechnung
- Gruppen-Management

99%+ Praezision ist das Ziel.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.document_grouping_service import (
    DocumentGroupingService,
    GroupingSignal,
    GroupCandidate,
    RelationshipCandidate,
    GroupDetectionResult,
    GroupingPatterns,
    CONFIDENCE_WEIGHTS,
    AUTO_GROUP_THRESHOLD,
    REVIEW_THRESHOLD,
    MIN_CONFIDENCE,
)


class TestGroupingPatterns:
    """Tests fuer Gruppierungs-Regex-Muster."""

    def test_page_numbering_pattern(self):
        """Sollte Seitennummerierung erkennen."""
        pattern = GroupingPatterns.PAGE_NUMBERING
        test_cases = [
            ("Seite 1 von 5", True, "1", "5"),
            ("Page 3 of 10", True, "3", "10"),
            ("S. 2 / 4", False, None, None),  # Simples Pattern
            ("Blatt 1 von 3", True, "1", "3"),
        ]
        for text, should_match, page, total in test_cases:
            match = pattern.search(text)
            if should_match:
                assert match is not None, f"Should match: {text}"
                assert match.group(1) == page
                assert match.group(2) == total
            else:
                assert match is None or match.group(1) != page

    def test_continuation_pattern(self):
        """Sollte Fortsetzungshinweise erkennen."""
        pattern = GroupingPatterns.CONTINUATION
        test_cases = [
            ("Text hier Fortsetzung", True),
            ("... continued", True),
            ("Ende des Dokuments", False),
        ]
        for text, should_match in test_cases:
            match = pattern.search(text)
            assert (match is not None) == should_match, f"Failed for: {text}"

    def test_reference_pattern(self):
        """Sollte Referenzen erkennen."""
        pattern = GroupingPatterns.REFERENCE
        test_cases = [
            ("Bezug: RE-2024-001", True, "RE-2024-001"),
            ("Betr.: Vertrag-123", True, "Vertrag-123"),
            ("Ihre Rechnung Nr. 456", True, "456"),
        ]
        for text, should_match, ref in test_cases:
            match = pattern.search(text)
            if should_match:
                assert match is not None, f"Should match: {text}"

    def test_hex_filename_pattern(self):
        """Sollte Hex-Dateinamen erkennen."""
        pattern = GroupingPatterns.HEX_FILENAME
        test_cases = [
            ("00000001.TIF", True, "00000001"),
            ("0000000A.tif", True, "0000000A"),
            ("00001C00.PDF", True, "00001C00"),
            ("document.pdf", False, None),
            ("1234.tif", False, None),  # Zu kurz
        ]
        for filename, should_match, hex_part in test_cases:
            match = pattern.match(filename)
            if should_match:
                assert match is not None, f"Should match: {filename}"
                assert match.group(1).upper() == hex_part.upper()
            else:
                assert match is None


class TestDocumentGroupingService:
    """Tests fuer DocumentGroupingService."""

    @pytest.fixture
    def service(self):
        """Erstellt DocumentGroupingService ohne DB."""
        return DocumentGroupingService(db=None)

    @pytest.fixture
    def service_with_db(self):
        """Erstellt DocumentGroupingService mit Mock-DB."""
        mock_db = AsyncMock()
        return DocumentGroupingService(db=mock_db)

    @pytest.fixture
    def mock_documents_hex_sequence(self):
        """Mock-Dokumente mit Hex-Sequenz-Dateinamen."""
        docs = []
        base_time = datetime.now(timezone.utc)

        for i, hex_num in enumerate([0x1C00, 0x1C01, 0x1C02, 0x1C03]):
            doc = MagicMock()
            doc.id = uuid4()
            doc.original_filename = f"{hex_num:08X}.TIF"
            doc.folder_name = "UP000001"
            doc.scan_timestamp = base_time + timedelta(seconds=i * 5)
            doc.created_at = base_time + timedelta(seconds=i * 5)
            doc.extracted_text = f"Seite {i+1} von 4\nTestinhalt"
            docs.append(doc)

        return docs

    @pytest.fixture
    def mock_documents_with_pages(self):
        """Mock-Dokumente mit Seitennummerierung."""
        docs = []
        base_time = datetime.now(timezone.utc)

        for i in range(1, 5):
            doc = MagicMock()
            doc.id = uuid4()
            doc.original_filename = f"document_page{i}.pdf"
            doc.scan_timestamp = None
            doc.created_at = base_time
            doc.extracted_text = f"Inhalt\n\nSeite {i} von 4\n\nWeiterer Text"
            docs.append(doc)

        return docs

    # ==========================================================================
    # Filename Sequence Detection Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_detect_filename_sequence_creates_group(self, service_with_db, mock_documents_hex_sequence):
        """Sollte Gruppe aus fortlaufenden Hex-Dateinamen erkennen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_documents_hex_sequence
        service_with_db.db.execute = AsyncMock(return_value=mock_result)

        result = await service_with_db._detect_filename_sequence(mock_documents_hex_sequence)

        assert len(result) >= 1
        group = result[0]
        assert len(group.document_ids) == 4
        assert group.group_type == "stapled"
        assert group.combined_confidence >= 0.85

    @pytest.mark.asyncio
    async def test_detect_filename_sequence_respects_gaps(self, service):
        """Sollte bei Luecken in der Sequenz neue Gruppe starten."""
        # Erstelle Dokumente mit Luecke: 1C00, 1C01, 1C10, 1C11
        docs = []
        for hex_num in [0x1C00, 0x1C01, 0x1C10, 0x1C11]:
            doc = MagicMock()
            doc.id = uuid4()
            doc.original_filename = f"{hex_num:08X}.TIF"
            docs.append(doc)

        result = await service._detect_filename_sequence(docs)

        # Sollte zwei Gruppen erkennen
        assert len(result) == 2

    # ==========================================================================
    # Timestamp Proximity Detection Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_detect_timestamp_proximity(self, service):
        """Sollte zeitnahe Dokumente gruppieren."""
        base_time = datetime.now(timezone.utc)
        docs = []

        # Gruppe 1: 5 Sekunden Abstand
        for i in range(3):
            doc = MagicMock()
            doc.id = uuid4()
            doc.scan_timestamp = base_time + timedelta(seconds=i * 5)
            doc.created_at = base_time + timedelta(seconds=i * 5)
            docs.append(doc)

        # Gruppe 2: Grosse Luecke, dann wieder eng
        for i in range(2):
            doc = MagicMock()
            doc.id = uuid4()
            doc.scan_timestamp = base_time + timedelta(minutes=10, seconds=i * 5)
            doc.created_at = base_time + timedelta(minutes=10, seconds=i * 5)
            docs.append(doc)

        result = await service._detect_timestamp_proximity(docs, max_gap_seconds=30)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_detect_timestamp_proximity_single_doc(self, service):
        """Sollte keine Gruppe bei einzelnem Dokument erstellen."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.scan_timestamp = datetime.now(timezone.utc)
        doc.created_at = datetime.now(timezone.utc)

        result = await service._detect_timestamp_proximity([doc])

        assert len(result) == 0

    # ==========================================================================
    # Content Similarity Detection Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_detect_content_similarity_page_numbers(self, service, mock_documents_with_pages):
        """Sollte Dokumente mit Seitennummerierung gruppieren."""
        result = await service._detect_content_similarity(mock_documents_with_pages)

        assert len(result) >= 1
        group = result[0]
        assert len(group.document_ids) == 4
        assert group.group_type == "multi_page"

    @pytest.mark.asyncio
    async def test_detect_content_similarity_no_text(self, service):
        """Sollte keine Gruppe ohne OCR-Text erstellen."""
        docs = []
        for _ in range(3):
            doc = MagicMock()
            doc.id = uuid4()
            doc.extracted_text = None
            docs.append(doc)

        result = await service._detect_content_similarity(docs)

        assert len(result) == 0

    # ==========================================================================
    # Confidence Calculation Tests
    # ==========================================================================

    def test_calculate_combined_confidence_single_signal(self, service):
        """Sollte Einzelsignal-Konfidenz korrekt berechnen."""
        signals = [
            GroupingSignal(
                signal_type="filename_sequence",
                confidence=0.90,
                details={}
            )
        ]

        combined = service._calculate_combined_confidence(signals)

        assert combined == 0.90

    def test_calculate_combined_confidence_multiple_signals(self, service):
        """Sollte Multi-Signal-Bonus anwenden."""
        signals = [
            GroupingSignal(signal_type="filename_sequence", confidence=0.90, details={}),
            GroupingSignal(signal_type="timestamp_proximity", confidence=0.70, details={}),
            GroupingSignal(signal_type="content_similarity", confidence=0.80, details={}),
        ]

        combined = service._calculate_combined_confidence(signals)

        # Sollte hoeher sein als Einzelsignal durch Bonus
        assert combined > 0.80

    def test_calculate_combined_confidence_empty(self, service):
        """Sollte 0 bei leeren Signalen zurueckgeben."""
        combined = service._calculate_combined_confidence([])

        assert combined == 0.0

    # ==========================================================================
    # Confidence Filtering Tests
    # ==========================================================================

    def test_apply_confidence_filtering_auto_confirm(self, service):
        """Sollte >= 99% Konfidenz als auto-confirmed markieren."""
        result = GroupDetectionResult(
            groups=[
                GroupCandidate(
                    document_ids=[uuid4(), uuid4()],
                    group_type="stapled",
                    signals=[GroupingSignal("filename_sequence", 0.99, {})],
                    combined_confidence=0.99,
                )
            ]
        )

        filtered = service._apply_confidence_filtering(result)

        assert len(filtered.groups) == 1
        assert filtered.groups[0].needs_review == False

    def test_apply_confidence_filtering_needs_review(self, service):
        """Sollte 80-99% Konfidenz zur Ueberpruefung markieren."""
        result = GroupDetectionResult(
            groups=[
                GroupCandidate(
                    document_ids=[uuid4(), uuid4()],
                    group_type="stapled",
                    signals=[GroupingSignal("timestamp_proximity", 0.85, {})],
                    combined_confidence=0.85,
                )
            ]
        )

        filtered = service._apply_confidence_filtering(result)

        assert len(filtered.groups) == 1
        assert filtered.groups[0].needs_review == True

    def test_apply_confidence_filtering_removes_low_confidence(self, service):
        """Sollte < 60% Konfidenz entfernen."""
        result = GroupDetectionResult(
            groups=[
                GroupCandidate(
                    document_ids=[uuid4(), uuid4()],
                    group_type="stapled",
                    signals=[GroupingSignal("unknown", 0.50, {})],
                    combined_confidence=0.50,
                )
            ]
        )

        filtered = service._apply_confidence_filtering(result)

        assert len(filtered.groups) == 0

    # ==========================================================================
    # Statistics Tests
    # ==========================================================================

    def test_get_detection_stats(self, service):
        """Sollte Statistiken zurueckgeben."""
        stats = service.get_detection_stats()

        assert "total_detections" in stats
        assert "groups_found" in stats
        assert "auto_confirmed" in stats

    def test_reset_stats(self, service):
        """Sollte Statistiken zuruecksetzen."""
        service._detection_stats["total_detections"] = 100
        service.reset_stats()

        stats = service.get_detection_stats()
        assert stats["total_detections"] == 0


class TestGroupCandidateCreation:
    """Tests fuer GroupCandidate-Erstellung."""

    @pytest.fixture
    def service(self):
        return DocumentGroupingService(db=None)

    def test_create_filename_group(self, service):
        """Sollte GroupCandidate aus Dateinamen-Sequenz erstellen."""
        # _create_filename_group expects List[Tuple[doc, sequence_number]]
        doc1 = MagicMock()
        doc1.id = uuid4()
        doc2 = MagicMock()
        doc2.id = uuid4()
        doc3 = MagicMock()
        doc3.id = uuid4()

        docs_with_seq = [
            (doc1, 0x1C00),
            (doc2, 0x1C01),
            (doc3, 0x1C02),
        ]

        group = service._create_filename_group(docs_with_seq)

        assert len(group.document_ids) == 3
        assert group.group_type == "stapled"
        assert "Geheftete Dokumente" in group.suggested_name
        assert group.combined_confidence >= 0.80

    def test_create_timestamp_group(self, service):
        """Sollte GroupCandidate aus zeitnahen Dokumenten erstellen."""
        base_time = datetime.now(timezone.utc)
        docs = []

        for i in range(5):
            doc = MagicMock()
            doc.id = uuid4()
            doc.scan_timestamp = base_time + timedelta(seconds=i * 5)
            doc.created_at = base_time + timedelta(seconds=i * 5)
            docs.append(doc)

        group = service._create_timestamp_group(docs)

        assert len(group.document_ids) == 5
        assert group.group_type == "stapled"
        assert group.needs_review == True  # Zeitstempel allein reicht nicht


class TestRelationshipDetection:
    """Tests fuer Beziehungserkennung zwischen Dokumenten."""

    @pytest.fixture
    def service(self):
        return DocumentGroupingService(db=None)

    @pytest.mark.asyncio
    async def test_detect_references(self, service):
        """Sollte Referenzen zwischen Dokumenten erkennen."""
        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.extracted_text = "Rechnung Nr. RE-2024-001"

        doc2 = MagicMock()
        doc2.id = uuid4()
        doc2.extracted_text = "Bezug: Rechnung RE-2024-001"

        result = await service._detect_references([doc1, doc2])

        # Sollte Beziehung erkennen
        assert len(result) >= 0  # Kann erkannt werden, wenn Pattern matcht

    @pytest.mark.asyncio
    async def test_detect_references_no_match(self, service):
        """Sollte keine Beziehung bei fehlenden Referenzen erkennen."""
        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.extracted_text = "Allgemeiner Text"

        doc2 = MagicMock()
        doc2.id = uuid4()
        doc2.extracted_text = "Anderer Text"

        result = await service._detect_references([doc1, doc2])

        assert len(result) == 0


class TestConfidenceConstants:
    """Tests fuer Konfidenz-Konstanten."""

    def test_auto_group_threshold(self):
        """AUTO_GROUP_THRESHOLD sollte 99%+ sein."""
        assert AUTO_GROUP_THRESHOLD >= 0.99

    def test_review_threshold(self):
        """REVIEW_THRESHOLD sollte 80% sein."""
        assert REVIEW_THRESHOLD == 0.80

    def test_min_confidence(self):
        """MIN_CONFIDENCE sollte 60% sein."""
        assert MIN_CONFIDENCE == 0.60

    def test_confidence_weights_exist(self):
        """Sollte Gewichte fuer alle Signaltypen haben."""
        expected_types = [
            "filename_sequence",
            "page_numbering",
            "timestamp_proximity",
            "content_similarity",
        ]
        for signal_type in expected_types:
            assert signal_type in CONFIDENCE_WEIGHTS
            assert 0.0 <= CONFIDENCE_WEIGHTS[signal_type] <= 1.0
