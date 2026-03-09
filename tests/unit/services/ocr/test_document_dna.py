# -*- coding: utf-8 -*-
"""
Unit Tests fuer DocumentDNAService.

Testet:
- DNA-Extraktion aus OCR-Ergebnissen
- Layout-Zonen-Analyse
- Textanker-Erkennung
- Feld-Beziehungen
- DNA-Matching (Entity, strukturell, Feld-Aehnlichkeit)
- DNA-Anwendung (Extraktions-Hints)
- Lernen aus Korrekturen (EMA)
- Datenklassen-Serialisierung
"""

import pytest
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ocr.document_dna_service import (
    DocumentDNAService,
    DocumentDNA,
    NormalizedBounds,
    LayoutZone,
    RelativePosition,
    TextAnchor,
    FieldRelationship,
    ExtractionHint,
    DNAMatchResult,
    EMA_WEIGHT_EXISTING,
    EMA_WEIGHT_NEW,
    HEADER_ZONE_END,
    FOOTER_ZONE_START,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> DocumentDNAService:
    """Erstelle Service-Instanz."""
    return DocumentDNAService()


@pytest.fixture
def sample_extracted_fields() -> Dict[str, Dict[str, object]]:
    """Beispiel-Felder mit Bounding Boxes."""
    return {
        "invoice_number": {
            "value": "RE-2024-001",
            "bounding_box": {"x": 0.6, "y": 0.05, "width": 0.2, "height": 0.02},
        },
        "invoice_date": {
            "value": "15.03.2024",
            "bounding_box": {"x": 0.6, "y": 0.08, "width": 0.15, "height": 0.02},
        },
        "total_amount": {
            "value": "1.234,56 €",
            "bounding_box": {"x": 0.7, "y": 0.85, "width": 0.15, "height": 0.02},
        },
    }


@pytest.fixture
def sample_ocr_text() -> str:
    """Beispiel-OCR-Text."""
    return (
        "Müller GmbH\n"
        "Musterstraße 1\n"
        "12345 Berlin\n\n"
        "Rechnungsnummer: RE-2024-001\n"
        "Datum: 15.03.2024\n\n"
        "Pos  Artikel       Menge  Preis\n"
        "1    Widget A      5      19,99€\n"
        "2    Widget B      3      29,99€\n\n"
        "Netto: 1.037,36 €\n"
        "MwSt 19%: 197,10 €\n"
        "Gesamtbetrag: 1.234,56 €\n"
        "IBAN: DE89 3704 0044 0532 0130 00\n"
    )


@pytest.fixture
def sample_dna() -> DocumentDNA:
    """Beispiel-DNA fuer Tests."""
    return DocumentDNA(
        layout_zones=[
            LayoutZone(
                zone_type="header",
                bounds=NormalizedBounds(x=0.0, y=0.0, width=1.0, height=0.15),
                confidence=0.9,
            ),
            LayoutZone(
                zone_type="body",
                bounds=NormalizedBounds(x=0.0, y=0.15, width=1.0, height=0.75),
                confidence=0.85,
            ),
            LayoutZone(
                zone_type="footer",
                bounds=NormalizedBounds(x=0.0, y=0.90, width=1.0, height=0.10),
                confidence=0.9,
            ),
        ],
        field_positions={
            "invoice_number": RelativePosition(
                zone="header",
                x_rel=0.6,
                y_rel=0.05,
                nearest_anchor="Rechnungsnummer",
                anchor_offset_x=0.1,
                anchor_offset_y=0.0,
            ),
            "total_amount": RelativePosition(
                zone="footer",
                x_rel=0.7,
                y_rel=0.92,
                nearest_anchor="Gesamtbetrag",
                anchor_offset_x=0.15,
                anchor_offset_y=0.0,
            ),
        },
        text_anchors=[
            TextAnchor(
                text="Rechnungsnummer",
                normalized_position=NormalizedBounds(x=0.05, y=0.05, width=0.15, height=0.02),
                frequency=1.0,
            ),
        ],
        field_relationships=[
            FieldRelationship(
                field_a="invoice_number",
                field_b="invoice_date",
                relationship="above",
                distance=0.03,
            ),
        ],
        structural_hash="abc123def456",
    )


# =============================================================================
# NormalizedBounds Tests
# =============================================================================


class TestNormalizedBounds:
    """Tests fuer NormalizedBounds Datenklasse."""

    def test_center_x(self) -> None:
        """Zentrum X wird korrekt berechnet."""
        bounds = NormalizedBounds(x=0.2, y=0.3, width=0.4, height=0.1)
        assert bounds.center_x == pytest.approx(0.4)

    def test_center_y(self) -> None:
        """Zentrum Y wird korrekt berechnet."""
        bounds = NormalizedBounds(x=0.2, y=0.3, width=0.4, height=0.1)
        assert bounds.center_y == pytest.approx(0.35)

    def test_to_dict(self) -> None:
        """to_dict() gibt korrektes Format zurueck."""
        bounds = NormalizedBounds(x=0.123456789, y=0.5, width=0.3, height=0.1)
        d = bounds.to_dict()
        assert d["x"] == 0.123457  # Gerundet auf 6 Stellen
        assert d["y"] == 0.5

    def test_from_dict(self) -> None:
        """from_dict() erstellt korrekte Instanz."""
        bounds = NormalizedBounds.from_dict(
            {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
        )
        assert bounds.x == 0.1
        assert bounds.height == 0.4

    def test_from_dict_defaults(self) -> None:
        """from_dict() verwendet Defaults bei fehlenden Werten."""
        bounds = NormalizedBounds.from_dict({})
        assert bounds.x == 0.0
        assert bounds.y == 0.0


# =============================================================================
# LayoutZone Tests
# =============================================================================


class TestLayoutZone:
    """Tests fuer LayoutZone Datenklasse."""

    def test_to_dict(self) -> None:
        """to_dict() gibt korrektes Format zurueck."""
        zone = LayoutZone(
            zone_type="header",
            bounds=NormalizedBounds(x=0.0, y=0.0, width=1.0, height=0.15),
            confidence=0.9,
        )
        d = zone.to_dict()
        assert d["zone_type"] == "header"
        assert d["confidence"] == 0.9

    def test_from_dict(self) -> None:
        """from_dict() erstellt korrekte Instanz."""
        zone = LayoutZone.from_dict({
            "zone_type": "footer",
            "bounds": {"x": 0.0, "y": 0.9, "width": 1.0, "height": 0.1},
            "confidence": 0.85,
        })
        assert zone.zone_type == "footer"
        assert zone.confidence == 0.85


# =============================================================================
# DocumentDNA Tests
# =============================================================================


class TestDocumentDNA:
    """Tests fuer DocumentDNA Datenklasse."""

    def test_to_dict(self, sample_dna: DocumentDNA) -> None:
        """to_dict() gibt korrektes Format zurueck."""
        d = sample_dna.to_dict()
        assert "layout_zones" in d
        assert "field_positions" in d
        assert "text_anchors" in d
        assert "field_relationships" in d
        assert "structural_hash" in d

    def test_from_dict_roundtrip(self, sample_dna: DocumentDNA) -> None:
        """from_dict(to_dict()) erhaelt die Struktur."""
        d = sample_dna.to_dict()
        restored = DocumentDNA.from_dict(d)

        assert len(restored.layout_zones) == len(sample_dna.layout_zones)
        assert set(restored.field_positions.keys()) == set(sample_dna.field_positions.keys())
        assert len(restored.text_anchors) == len(sample_dna.text_anchors)
        assert restored.structural_hash == sample_dna.structural_hash


# =============================================================================
# DNA Extraction Tests
# =============================================================================


class TestDNAExtraction:
    """Tests fuer DNA-Extraktion."""

    def test_extract_dna_basic(
        self,
        service: DocumentDNAService,
        sample_ocr_text: str,
        sample_extracted_fields: Dict[str, Dict[str, object]],
    ) -> None:
        """DNA-Extraktion erzeugt gueltige DNA."""
        dna = service.extract_dna(sample_ocr_text, sample_extracted_fields)

        assert isinstance(dna, DocumentDNA)
        assert len(dna.layout_zones) > 0
        assert len(dna.text_anchors) > 0
        assert len(dna.structural_hash) > 0

    def test_extract_dna_empty_text(self, service: DocumentDNAService) -> None:
        """Leerer OCR-Text ergibt DNA ohne Anker."""
        dna = service.extract_dna("", {})

        assert isinstance(dna, DocumentDNA)
        assert len(dna.text_anchors) == 0
        assert len(dna.field_positions) == 0

    def test_extract_dna_with_fields(
        self,
        service: DocumentDNAService,
        sample_ocr_text: str,
        sample_extracted_fields: Dict[str, Dict[str, object]],
    ) -> None:
        """Feld-Positionen werden in DNA aufgenommen."""
        dna = service.extract_dna(sample_ocr_text, sample_extracted_fields)

        assert "invoice_number" in dna.field_positions
        assert "total_amount" in dna.field_positions

    def test_extract_dna_field_relationships(
        self,
        service: DocumentDNAService,
        sample_ocr_text: str,
        sample_extracted_fields: Dict[str, Dict[str, object]],
    ) -> None:
        """Feld-Beziehungen werden berechnet."""
        dna = service.extract_dna(sample_ocr_text, sample_extracted_fields)
        # Mit 3 Feldern sollten Beziehungen existieren
        assert len(dna.field_relationships) > 0

    def test_structural_hash_deterministic(
        self,
        service: DocumentDNAService,
        sample_ocr_text: str,
        sample_extracted_fields: Dict[str, Dict[str, object]],
    ) -> None:
        """Structural Hash ist deterministisch."""
        dna1 = service.extract_dna(sample_ocr_text, sample_extracted_fields)
        dna2 = service.extract_dna(sample_ocr_text, sample_extracted_fields)

        assert dna1.structural_hash == dna2.structural_hash


# =============================================================================
# DNA Apply Tests
# =============================================================================


class TestDNAApply:
    """Tests fuer DNA-Anwendung."""

    def test_apply_dna_generates_hints(
        self, service: DocumentDNAService, sample_dna: DocumentDNA
    ) -> None:
        """DNA-Anwendung erzeugt Extraktions-Hinweise."""
        hints = service.apply_dna(sample_dna, "exact_entity", 0.95)

        assert "invoice_number" in hints
        assert "total_amount" in hints
        assert isinstance(hints["invoice_number"], ExtractionHint)

    def test_apply_dna_confidence_varies(
        self, service: DocumentDNAService, sample_dna: DocumentDNA
    ) -> None:
        """Confidence haengt von Match-Typ und Score ab."""
        hints_exact = service.apply_dna(sample_dna, "exact_entity", 0.95)
        hints_similar = service.apply_dna(sample_dna, "field_similarity", 0.6)

        # Exakter Match sollte hoehere Confidence haben
        assert hints_exact["invoice_number"].confidence > hints_similar["invoice_number"].confidence

    def test_apply_dna_source_field(
        self, service: DocumentDNAService, sample_dna: DocumentDNA
    ) -> None:
        """Source-Feld in Hints stimmt mit Match-Typ ueberein."""
        hints = service.apply_dna(sample_dna, "structural", 0.8)
        assert hints["invoice_number"].source == "structural"


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests fuer Datenklassen-Serialisierung."""

    def test_relative_position_roundtrip(self) -> None:
        """RelativePosition ueberlebt to_dict/from_dict."""
        pos = RelativePosition(
            zone="header", x_rel=0.5, y_rel=0.1,
            nearest_anchor="Rechnungsnummer",
            anchor_offset_x=0.05, anchor_offset_y=0.0,
        )
        restored = RelativePosition.from_dict(pos.to_dict())
        assert restored.zone == "header"
        assert restored.nearest_anchor == "Rechnungsnummer"

    def test_text_anchor_roundtrip(self) -> None:
        """TextAnchor ueberlebt to_dict/from_dict."""
        anchor = TextAnchor(
            text="Datum",
            normalized_position=NormalizedBounds(x=0.1, y=0.1, width=0.1, height=0.02),
            frequency=0.9,
        )
        restored = TextAnchor.from_dict(anchor.to_dict())
        assert restored.text == "Datum"
        assert restored.frequency == 0.9

    def test_field_relationship_roundtrip(self) -> None:
        """FieldRelationship ueberlebt to_dict/from_dict."""
        rel = FieldRelationship(
            field_a="a", field_b="b",
            relationship="right_of", distance=0.1,
        )
        restored = FieldRelationship.from_dict(rel.to_dict())
        assert restored.relationship == "right_of"

    def test_extraction_hint_to_dict(self) -> None:
        """ExtractionHint.to_dict() gibt korrektes Format zurueck."""
        hint = ExtractionHint(
            field_name="invoice_number",
            expected_zone="header",
            expected_bounds=NormalizedBounds(x=0.5, y=0.1, width=0.2, height=0.02),
            nearest_anchor="Rechnungsnummer",
            confidence=0.9,
            source="exact_entity",
        )
        d = hint.to_dict()
        assert d["field_name"] == "invoice_number"
        assert d["confidence"] == 0.9


# =============================================================================
# Known Anchors Tests
# =============================================================================


class TestKnownAnchors:
    """Tests fuer vordefinierte Textanker."""

    def test_known_anchors_exist(self, service: DocumentDNAService) -> None:
        """Vordefinierte deutsche Textanker existieren."""
        assert len(service.KNOWN_ANCHORS) > 10
        assert "Rechnungsnummer" in service.KNOWN_ANCHORS
        assert "Datum" in service.KNOWN_ANCHORS
        assert "IBAN" in service.KNOWN_ANCHORS
        assert "MwSt" in service.KNOWN_ANCHORS
