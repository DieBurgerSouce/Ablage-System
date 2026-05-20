# -*- coding: utf-8 -*-
"""
Document DNA Service - Adaptive Field Extraction.

Statt starrer Lieferanten-Templates lernt Document DNA
die strukturellen Muster eines Dokuments:
- Relative Positionen (nicht absolute Koordinaten)
- Layout-Zonen (Header, Footer, Tabelle, Body)
- Textanker (wiederkehrende Textmuster pro Lieferant)
- Feld-Beziehungen (welche Felder nahe beieinander liegen)

Das System erstellt einen strukturellen Fingerprint (DNA)
und nutzt diesen fuer adaptive Feld-Extraktion.
"""

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_ocr_template import SupplierOCRTemplate
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# --- Konfiguration ---

# EMA-Gewichtung: 80% bestehend + 20% neue Korrektur
EMA_WEIGHT_EXISTING = 0.8
EMA_WEIGHT_NEW = 0.2

# Layout-Zonen-Schwellenwerte (normalisiert 0-1)
HEADER_ZONE_END = 0.15
FOOTER_ZONE_START = 0.90
SIDEBAR_ZONE_MAX_WIDTH = 0.20
TABLE_ZONE_MIN_HEIGHT = 0.20

# Matching-Schwellenwerte
EXACT_MATCH_THRESHOLD = 0.90
SIMILAR_MATCH_THRESHOLD = 0.60
ANCHOR_MATCH_THRESHOLD = 0.70

# Maximale Anzahl gespeicherter Anker pro DNA
MAX_TEXT_ANCHORS = 50


# =============================================================================
# Datenklassen
# =============================================================================


@dataclass
class NormalizedBounds:
    """Normalisierte Bounding Box (alle Werte 0-1)."""
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": round(self.x, 6),
            "y": round(self.y, 6),
            "width": round(self.width, 6),
            "height": round(self.height, 6),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "NormalizedBounds":
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            width=float(data.get("width", 0.0)),
            height=float(data.get("height", 0.0)),
        )


@dataclass
class LayoutZone:
    """Eine Layout-Zone auf der Seite."""
    zone_type: str  # "header", "footer", "table", "body", "sidebar"
    bounds: NormalizedBounds
    confidence: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "zone_type": self.zone_type,
            "bounds": self.bounds.to_dict(),
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "LayoutZone":
        return cls(
            zone_type=str(data.get("zone_type", "body")),
            bounds=NormalizedBounds.from_dict(data.get("bounds", {})),
            confidence=float(data.get("confidence", 0.0)),
        )


@dataclass
class RelativePosition:
    """Position eines Feldes relativ zur Zone und zum naechsten Textanker."""
    zone: str
    x_rel: float  # Position innerhalb der Zone (0-1)
    y_rel: float  # Position innerhalb der Zone (0-1)
    nearest_anchor: Optional[str]
    anchor_offset_x: float
    anchor_offset_y: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "zone": self.zone,
            "x_rel": round(self.x_rel, 6),
            "y_rel": round(self.y_rel, 6),
            "nearest_anchor": self.nearest_anchor,
            "anchor_offset_x": round(self.anchor_offset_x, 6),
            "anchor_offset_y": round(self.anchor_offset_y, 6),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "RelativePosition":
        return cls(
            zone=str(data.get("zone", "body")),
            x_rel=float(data.get("x_rel", 0.0)),
            y_rel=float(data.get("y_rel", 0.0)),
            nearest_anchor=data.get("nearest_anchor"),
            anchor_offset_x=float(data.get("anchor_offset_x", 0.0)),
            anchor_offset_y=float(data.get("anchor_offset_y", 0.0)),
        )


@dataclass
class TextAnchor:
    """Wiederkehrendes Textmuster auf dem Dokument."""
    text: str
    normalized_position: NormalizedBounds
    frequency: float  # Wie oft dieses Muster vorkommt (0-1)

    def to_dict(self) -> Dict[str, object]:
        return {
            "text": self.text,
            "normalized_position": self.normalized_position.to_dict(),
            "frequency": round(self.frequency, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "TextAnchor":
        return cls(
            text=str(data.get("text", "")),
            normalized_position=NormalizedBounds.from_dict(
                data.get("normalized_position", {})
            ),
            frequency=float(data.get("frequency", 0.0)),
        )


@dataclass
class FieldRelationship:
    """Raeumliche Beziehung zwischen zwei Feldern."""
    field_a: str
    field_b: str
    relationship: str  # "above", "below", "left_of", "right_of", "same_line"
    distance: float  # Normalisierte Distanz

    def to_dict(self) -> Dict[str, object]:
        return {
            "field_a": self.field_a,
            "field_b": self.field_b,
            "relationship": self.relationship,
            "distance": round(self.distance, 6),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "FieldRelationship":
        return cls(
            field_a=str(data.get("field_a", "")),
            field_b=str(data.get("field_b", "")),
            relationship=str(data.get("relationship", "same_line")),
            distance=float(data.get("distance", 0.0)),
        )


@dataclass
class ExtractionHint:
    """Hinweis fuer die strukturierte Extraktion eines Feldes."""
    field_name: str
    expected_zone: str
    expected_bounds: NormalizedBounds
    nearest_anchor: Optional[str]
    confidence: float
    source: str  # "exact_match", "similar_layout", "learned_pattern"

    def to_dict(self) -> Dict[str, object]:
        return {
            "field_name": self.field_name,
            "expected_zone": self.expected_zone,
            "expected_bounds": self.expected_bounds.to_dict(),
            "nearest_anchor": self.nearest_anchor,
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }


@dataclass
class DocumentDNA:
    """Struktureller Fingerprint eines Dokument-Layouts."""
    layout_zones: List[LayoutZone]
    field_positions: Dict[str, RelativePosition]
    text_anchors: List[TextAnchor]
    field_relationships: List[FieldRelationship]
    structural_hash: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "layout_zones": [z.to_dict() for z in self.layout_zones],
            "field_positions": {
                k: v.to_dict() for k, v in self.field_positions.items()
            },
            "text_anchors": [a.to_dict() for a in self.text_anchors],
            "field_relationships": [r.to_dict() for r in self.field_relationships],
            "structural_hash": self.structural_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "DocumentDNA":
        zones_data = data.get("layout_zones", [])
        positions_data = data.get("field_positions", {})
        anchors_data = data.get("text_anchors", [])
        relationships_data = data.get("field_relationships", [])

        return cls(
            layout_zones=[LayoutZone.from_dict(z) for z in zones_data],
            field_positions={
                k: RelativePosition.from_dict(v)
                for k, v in positions_data.items()
            },
            text_anchors=[TextAnchor.from_dict(a) for a in anchors_data],
            field_relationships=[
                FieldRelationship.from_dict(r) for r in relationships_data
            ],
            structural_hash=str(data.get("structural_hash", "")),
        )


@dataclass
class DNAMatchResult:
    """Ergebnis eines DNA-Abgleichs."""
    template_id: UUID
    entity_id: UUID
    similarity_score: float
    match_type: str  # "exact_entity", "structural", "field_similarity"
    dna: DocumentDNA


# =============================================================================
# Service-Klasse
# =============================================================================


class DocumentDNAService:
    """
    Service fuer dokumentenstrukturbasierte Feld-Extraktion.

    Lernt die strukturellen Muster (DNA) von Dokumenten und nutzt
    diese fuer adaptive, relative Feld-Extraktion statt starrer
    absoluter Koordinaten.
    """

    # Bekannte deutsche Feld-Label als Textanker
    KNOWN_ANCHORS: List[str] = [
        "Rechnungsnummer",
        "Rechnungsnr",
        "Re-Nr",
        "Rechnung Nr",
        "Rechnungsdatum",
        "Datum",
        "Faelligkeitsdatum",
        "Faellig am",
        "Gesamtbetrag",
        "Gesamtsumme",
        "Summe",
        "Endbetrag",
        "Nettobetrag",
        "Netto",
        "Mehrwertsteuer",
        "MwSt",
        "USt",
        "Lieferant",
        "Absender",
        "IBAN",
        "BIC",
        "Bestellnummer",
        "Bestell-Nr",
        "Lieferscheinnummer",
        "Lieferschein-Nr",
        "Kundennummer",
        "Kunden-Nr",
        "Artikelnummer",
        "Menge",
        "Einzelpreis",
        "Steuernummer",
        "USt-IdNr",
        "Zahlungsbedingungen",
        "Bankverbindung",
        "Kontonummer",
    ]

    # --- DNA-Extraktion ---

    def extract_dna(
        self,
        ocr_text: str,
        extracted_fields: Dict[str, Dict[str, object]],
        page_width: float = 1.0,
        page_height: float = 1.0,
    ) -> DocumentDNA:
        """
        Extrahiere die strukturelle DNA aus einem OCR-Ergebnis.

        Analysiert das Layout, berechnet relative Feldpositionen,
        findet Textanker und bestimmt Feld-Beziehungen.

        Args:
            ocr_text: Der rohe OCR-Text
            extracted_fields: Extrahierte Felder mit Bounding Boxes
                Format: {"field_name": {"value": "...", "bounding_box": {...}, ...}}
            page_width: Seitenbreite (fuer Normalisierung, Standard 1.0 = bereits normalisiert)
            page_height: Seitenhoehe (fuer Normalisierung)

        Returns:
            DocumentDNA mit strukturellem Fingerprint
        """
        # 1. Layout-Zonen analysieren
        layout_zones = self._analyze_layout_zones(extracted_fields, page_width, page_height)

        # 2. Textanker finden
        text_anchors = self._find_text_anchors(ocr_text, extracted_fields, page_width, page_height)

        # 3. Relative Feldpositionen berechnen
        field_positions = self._calculate_relative_positions(
            extracted_fields, layout_zones, text_anchors, page_width, page_height
        )

        # 4. Feld-Beziehungen bestimmen
        field_relationships = self._determine_field_relationships(
            extracted_fields, page_width, page_height
        )

        # 5. Strukturellen Hash berechnen
        structural_hash = self._compute_structural_hash(
            layout_zones, field_positions, text_anchors
        )

        dna = DocumentDNA(
            layout_zones=layout_zones,
            field_positions=field_positions,
            text_anchors=text_anchors,
            field_relationships=field_relationships,
            structural_hash=structural_hash,
        )

        logger.debug(
            "document_dna_extracted",
            zones=len(layout_zones),
            fields=len(field_positions),
            anchors=len(text_anchors),
            relationships=len(field_relationships),
            hash=structural_hash[:16],
        )

        return dna

    # --- DNA-Matching ---

    async def find_matching_dna(
        self,
        dna: DocumentDNA,
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[DNAMatchResult]:
        """
        Finde die am besten passende gespeicherte DNA.

        Prueft in dieser Reihenfolge:
        1. Exakter Entity-Match (gleicher Lieferant)
        2. Strukturelle Aehnlichkeit (Layout-Fingerprint)
        3. Feld-Positions-Aehnlichkeit (Cosine Similarity)

        Args:
            dna: Die zu matchende Document DNA
            entity_id: Entity-ID des Lieferanten (optional)
            company_id: Company-ID (Multi-Tenant)
            db: Datenbank-Session

        Returns:
            Bestes Match-Ergebnis oder None
        """
        # 1. Exakter Entity-Match
        if entity_id is not None:
            match = await self._find_entity_match(dna, entity_id, company_id, db)
            if match is not None:
                return match

        # 2. Strukturelle Aehnlichkeit (Layout-Hash)
        match = await self._find_structural_match(dna, company_id, db)
        if match is not None:
            return match

        # 3. Feld-Positions-Aehnlichkeit
        match = await self._find_field_similarity_match(dna, company_id, db)
        if match is not None:
            return match

        logger.debug(
            "kein_dna_match_gefunden",
            entity_id=str(entity_id) if entity_id else None,
            hash=dna.structural_hash[:16],
        )
        return None

    # --- DNA-Anwendung ---

    def apply_dna(
        self,
        matched_dna: DocumentDNA,
        match_type: str,
        similarity_score: float,
    ) -> Dict[str, ExtractionHint]:
        """
        Wende eine gematchte DNA auf ein neues Dokument an.

        Berechnet fuer jedes Feld in der DNA die erwartete Position
        und gibt Extraktions-Hinweise mit Confidence zurueck.

        Args:
            matched_dna: Die gematchte DNA
            match_type: Art des Matches ("exact_entity", "structural", "field_similarity")
            similarity_score: Aehnlichkeitswert (0-1)

        Returns:
            Dict von Feldnamen zu ExtractionHints
        """
        hints: Dict[str, ExtractionHint] = {}

        # Basis-Confidence basierend auf Match-Qualitaet
        base_confidence = self._calculate_hint_confidence(match_type, similarity_score)

        for field_name, rel_pos in matched_dna.field_positions.items():
            # Erwartete Bounds aus Zone + relativer Position berechnen
            expected_bounds = self._calculate_expected_bounds(
                rel_pos, matched_dna.layout_zones
            )

            hints[field_name] = ExtractionHint(
                field_name=field_name,
                expected_zone=rel_pos.zone,
                expected_bounds=expected_bounds,
                nearest_anchor=rel_pos.nearest_anchor,
                confidence=base_confidence,
                source=match_type,
            )

        logger.debug(
            "dna_hints_generiert",
            hint_count=len(hints),
            match_type=match_type,
            base_confidence=round(base_confidence, 3),
        )

        return hints

    # --- Lernen aus Korrekturen ---

    async def learn_from_correction(
        self,
        entity_id: UUID,
        company_id: UUID,
        field_name: str,
        old_position: Dict[str, float],
        new_position: Dict[str, float],
        db: AsyncSession,
    ) -> bool:
        """
        Aktualisiere die gespeicherte DNA mit einer korrigierten Position.

        Verwendet EMA (Exponential Moving Average):
        80% bestehende Position + 20% neue Korrektur.

        Args:
            entity_id: Entity-ID des Lieferanten
            company_id: Company-ID (Multi-Tenant)
            field_name: Name des korrigierten Feldes
            old_position: Bisherige Bounding Box {"x", "y", "width", "height"}
            new_position: Korrigierte Bounding Box {"x", "y", "width", "height"}
            db: Datenbank-Session

        Returns:
            True wenn DNA erfolgreich aktualisiert wurde
        """
        # Template fuer diesen Lieferanten laden
        template = await self._load_active_template(entity_id, company_id, db)
        if template is None:
            logger.debug(
                "kein_template_fuer_dna_korrektur",
                entity_id=str(entity_id),
                field_name=field_name,
            )
            return False

        # DNA aus field_definitions laden
        dna_data = self._extract_dna_from_template(template)
        if dna_data is None:
            return False

        dna = DocumentDNA.from_dict(dna_data)

        # Feld-Position aktualisieren mit EMA
        if field_name in dna.field_positions:
            existing = dna.field_positions[field_name]
            new_bounds = NormalizedBounds.from_dict(new_position)

            # EMA: 80% bestehend + 20% neu
            updated_x = existing.x_rel * EMA_WEIGHT_EXISTING + new_bounds.x * EMA_WEIGHT_NEW
            updated_y = existing.y_rel * EMA_WEIGHT_EXISTING + new_bounds.y * EMA_WEIGHT_NEW

            dna.field_positions[field_name] = RelativePosition(
                zone=existing.zone,
                x_rel=updated_x,
                y_rel=updated_y,
                nearest_anchor=existing.nearest_anchor,
                anchor_offset_x=existing.anchor_offset_x * EMA_WEIGHT_EXISTING
                + (new_bounds.x - existing.x_rel) * EMA_WEIGHT_NEW,
                anchor_offset_y=existing.anchor_offset_y * EMA_WEIGHT_EXISTING
                + (new_bounds.y - existing.y_rel) * EMA_WEIGHT_NEW,
            )
        else:
            # Neues Feld: direkt Position setzen
            new_bounds = NormalizedBounds.from_dict(new_position)
            zone = self._determine_zone_for_position(
                new_bounds.center_x, new_bounds.center_y
            )
            dna.field_positions[field_name] = RelativePosition(
                zone=zone,
                x_rel=new_bounds.x,
                y_rel=new_bounds.y,
                nearest_anchor=None,
                anchor_offset_x=0.0,
                anchor_offset_y=0.0,
            )

        # Structural Hash neu berechnen
        dna.structural_hash = self._compute_structural_hash(
            dna.layout_zones, dna.field_positions, dna.text_anchors
        )

        # Zurueck ins Template schreiben
        await self._save_dna_to_template(template, dna, db)

        logger.info(
            "dna_korrektur_gelernt",
            entity_id=str(entity_id),
            field_name=field_name,
            training_count=template.training_document_count,
        )

        return True

    # --- DNA-Speicherung ---

    async def store_dna(
        self,
        entity_id: UUID,
        company_id: UUID,
        dna: DocumentDNA,
        db: AsyncSession,
    ) -> UUID:
        """
        Speichere DNA persistent (nutzt SupplierOCRTemplate-Tabelle).

        Wenn ein aktives Template fuer diese Entity existiert,
        wird es aktualisiert. Sonst wird ein neues erstellt.

        Args:
            entity_id: Entity-ID des Lieferanten
            company_id: Company-ID (Multi-Tenant)
            dna: Die zu speichernde DNA
            db: Datenbank-Session

        Returns:
            Template-ID
        """
        # Bestehendes Template suchen
        template = await self._load_active_template(entity_id, company_id, db)

        if template is not None:
            # Bestehendes Template aktualisieren
            await self._save_dna_to_template(template, dna, db)
            logger.info(
                "dna_gespeichert_update",
                template_id=str(template.id),
                entity_id=str(entity_id),
            )
            return template.id

        # Neues Template erstellen
        import uuid as uuid_mod
        template_id = uuid_mod.uuid4()

        new_template = SupplierOCRTemplate(
            id=template_id,
            entity_id=entity_id,
            company_id=company_id,
            name="Document DNA Auto-Template",
            description="Automatisch generiert durch Document DNA Service",
            document_type="invoice_incoming",
            matching_strategy="combined",
            layout_fingerprint=dna.structural_hash,
            text_anchors=[a.text for a in dna.text_anchors],
            field_definitions=self._dna_to_field_definitions(dna),
            training_document_count=1,
            is_active=True,
            is_verified=False,
            auto_apply=False,
            is_auto_generated=True,
            auto_confidence=0.5,
        )
        db.add(new_template)
        await db.flush()

        logger.info(
            "dna_gespeichert_neu",
            template_id=str(template_id),
            entity_id=str(entity_id),
            fields=len(dna.field_positions),
            anchors=len(dna.text_anchors),
        )

        return template_id

    # ==========================================================================
    # Private Hilfsmethoden
    # ==========================================================================

    def _analyze_layout_zones(
        self,
        extracted_fields: Dict[str, Dict[str, object]],
        page_width: float,
        page_height: float,
    ) -> List[LayoutZone]:
        """Analysiere Layout-Zonen basierend auf Feldpositionen."""
        zones: List[LayoutZone] = []

        # Standard-Zonen definieren
        zones.append(LayoutZone(
            zone_type="header",
            bounds=NormalizedBounds(x=0.0, y=0.0, width=1.0, height=HEADER_ZONE_END),
            confidence=0.9,
        ))
        zones.append(LayoutZone(
            zone_type="footer",
            bounds=NormalizedBounds(
                x=0.0, y=FOOTER_ZONE_START, width=1.0, height=1.0 - FOOTER_ZONE_START
            ),
            confidence=0.9,
        ))
        zones.append(LayoutZone(
            zone_type="body",
            bounds=NormalizedBounds(
                x=0.0, y=HEADER_ZONE_END, width=1.0,
                height=FOOTER_ZONE_START - HEADER_ZONE_END,
            ),
            confidence=0.8,
        ))

        # Tabellen-Zone erkennen (Cluster von Feldern in einer Region)
        table_zone = self._detect_table_zone(extracted_fields, page_width, page_height)
        if table_zone is not None:
            zones.append(table_zone)

        # Sidebar-Zone erkennen (schmaler Bereich links oder rechts)
        sidebar_zone = self._detect_sidebar_zone(extracted_fields, page_width, page_height)
        if sidebar_zone is not None:
            zones.append(sidebar_zone)

        return zones

    def _detect_table_zone(
        self,
        extracted_fields: Dict[str, Dict[str, object]],
        page_width: float,
        page_height: float,
    ) -> Optional[LayoutZone]:
        """Erkenne eine Tabellen-Zone anhand geclusterter Felder."""
        # Sammle Y-Positionen aller Felder
        y_positions: List[float] = []
        for field_data in extracted_fields.values():
            if not isinstance(field_data, dict):
                continue
            bbox = field_data.get("bounding_box", {})
            if isinstance(bbox, dict) and "y" in bbox:
                y_norm = float(bbox["y"]) / max(page_height, 1.0)
                y_positions.append(y_norm)

        if len(y_positions) < 3:
            return None

        y_positions.sort()

        # Finde den dichtesten Bereich (Cluster)
        best_start = y_positions[0]
        best_end = y_positions[-1]
        max_density = 0.0

        window_size = TABLE_ZONE_MIN_HEIGHT
        for i, y_start in enumerate(y_positions):
            y_end = y_start + window_size
            count = sum(1 for y in y_positions if y_start <= y <= y_end)
            density = count / window_size if window_size > 0 else 0.0
            if density > max_density:
                max_density = density
                best_start = y_start
                best_end = y_end

        # Tabellen-Zone nur wenn genug Felder darin liegen
        fields_in_zone = sum(1 for y in y_positions if best_start <= y <= best_end)
        if fields_in_zone < 3:
            return None

        return LayoutZone(
            zone_type="table",
            bounds=NormalizedBounds(
                x=0.0,
                y=max(0.0, best_start - 0.02),
                width=1.0,
                height=min(1.0, best_end - best_start + 0.04),
            ),
            confidence=min(0.9, fields_in_zone / max(len(y_positions), 1)),
        )

    def _detect_sidebar_zone(
        self,
        extracted_fields: Dict[str, Dict[str, object]],
        page_width: float,
        page_height: float,
    ) -> Optional[LayoutZone]:
        """Erkenne eine Sidebar-Zone (schmaler Bereich links oder rechts)."""
        left_count = 0
        right_count = 0
        total = 0

        for field_data in extracted_fields.values():
            if not isinstance(field_data, dict):
                continue
            bbox = field_data.get("bounding_box", {})
            if not isinstance(bbox, dict) or "x" not in bbox:
                continue
            x_norm = float(bbox["x"]) / max(page_width, 1.0)
            total += 1
            if x_norm < SIDEBAR_ZONE_MAX_WIDTH:
                left_count += 1
            elif x_norm > (1.0 - SIDEBAR_ZONE_MAX_WIDTH):
                right_count += 1

        if total < 3:
            return None

        # Sidebar rechts
        if right_count >= 3 and right_count / total >= 0.3:
            return LayoutZone(
                zone_type="sidebar",
                bounds=NormalizedBounds(
                    x=1.0 - SIDEBAR_ZONE_MAX_WIDTH,
                    y=HEADER_ZONE_END,
                    width=SIDEBAR_ZONE_MAX_WIDTH,
                    height=FOOTER_ZONE_START - HEADER_ZONE_END,
                ),
                confidence=0.7,
            )

        return None

    def _find_text_anchors(
        self,
        ocr_text: str,
        extracted_fields: Dict[str, Dict[str, object]],
        page_width: float,
        page_height: float,
    ) -> List[TextAnchor]:
        """Finde wiederkehrende Textmuster (Anker) im OCR-Text."""
        anchors: List[TextAnchor] = []

        if not ocr_text:
            return anchors

        text_lower = ocr_text.lower()

        for anchor_text in self.KNOWN_ANCHORS:
            anchor_lower = anchor_text.lower()
            # Suche nach dem Anker-Text (auch mit Doppelpunkt)
            patterns = [anchor_lower, anchor_lower + ":", anchor_lower + " :"]
            found = False

            for pattern in patterns:
                pos = text_lower.find(pattern)
                if pos >= 0:
                    found = True
                    # Grobe Position anhand der Zeichenposition im Text schaetzen
                    text_fraction = pos / max(len(ocr_text), 1)
                    # Heuristik: Text-Position -> Y-Koordinate (linearisiert)
                    estimated_y = text_fraction
                    # X-Position: Anker stehen typischerweise links
                    estimated_x = 0.05

                    anchors.append(TextAnchor(
                        text=anchor_text,
                        normalized_position=NormalizedBounds(
                            x=estimated_x,
                            y=min(estimated_y, 0.95),
                            width=0.15,
                            height=0.02,
                        ),
                        frequency=1.0,
                    ))
                    break

            if not found:
                continue

        # Anker-Positionen aus extrahierten Feldern verfeinern
        for field_name, field_data in extracted_fields.items():
            if not isinstance(field_data, dict):
                continue
            bbox = field_data.get("bounding_box", {})
            if not isinstance(bbox, dict):
                continue

            # Suche nach passendem Anker
            for anchor in anchors:
                if self._anchor_matches_field(anchor.text, field_name):
                    x_norm = float(bbox.get("x", 0)) / max(page_width, 1.0)
                    y_norm = float(bbox.get("y", 0)) / max(page_height, 1.0)
                    # Anker ist typischerweise links des Feld-Wertes
                    anchor.normalized_position = NormalizedBounds(
                        x=max(0.0, x_norm - 0.15),
                        y=y_norm,
                        width=0.15,
                        height=float(bbox.get("height", 0.02)) / max(page_height, 1.0),
                    )

        # Auf MAX_TEXT_ANCHORS beschraenken
        return anchors[:MAX_TEXT_ANCHORS]

    def _anchor_matches_field(self, anchor_text: str, field_name: str) -> bool:
        """Pruefe ob ein Textanker zu einem Feldnamen passt."""
        mappings: Dict[str, List[str]] = {
            "invoice_number": ["Rechnungsnummer", "Rechnungsnr", "Re-Nr", "Rechnung Nr"],
            "invoice_date": ["Rechnungsdatum", "Datum"],
            "due_date": ["Faelligkeitsdatum", "Faellig am"],
            "total_amount": ["Gesamtbetrag", "Gesamtsumme", "Summe", "Endbetrag"],
            "net_amount": ["Nettobetrag", "Netto"],
            "vat_amount": ["Mehrwertsteuer", "MwSt", "USt"],
            "supplier_name": ["Lieferant", "Absender"],
            "iban": ["IBAN"],
            "bic": ["BIC"],
            "order_number": ["Bestellnummer", "Bestell-Nr"],
            "delivery_note_number": ["Lieferscheinnummer", "Lieferschein-Nr"],
            "customer_number": ["Kundennummer", "Kunden-Nr"],
        }

        field_anchors = mappings.get(field_name, [])
        return anchor_text in field_anchors

    def _calculate_relative_positions(
        self,
        extracted_fields: Dict[str, Dict[str, object]],
        layout_zones: List[LayoutZone],
        text_anchors: List[TextAnchor],
        page_width: float,
        page_height: float,
    ) -> Dict[str, RelativePosition]:
        """Berechne relative Feldpositionen innerhalb ihrer Zonen."""
        positions: Dict[str, RelativePosition] = {}

        for field_name, field_data in extracted_fields.items():
            if not isinstance(field_data, dict):
                continue
            bbox = field_data.get("bounding_box", {})
            if not isinstance(bbox, dict) or "x" not in bbox:
                continue

            x_norm = float(bbox.get("x", 0)) / max(page_width, 1.0)
            y_norm = float(bbox.get("y", 0)) / max(page_height, 1.0)

            # Zone bestimmen
            zone = self._determine_zone_for_position(x_norm, y_norm)
            zone_bounds = self._get_zone_bounds(zone, layout_zones)

            # Relative Position innerhalb der Zone
            if zone_bounds is not None and zone_bounds.width > 0 and zone_bounds.height > 0:
                x_rel = (x_norm - zone_bounds.x) / zone_bounds.width
                y_rel = (y_norm - zone_bounds.y) / zone_bounds.height
            else:
                x_rel = x_norm
                y_rel = y_norm

            # Naechsten Textanker finden
            nearest_anchor, anchor_offset_x, anchor_offset_y = self._find_nearest_anchor(
                x_norm, y_norm, text_anchors
            )

            positions[field_name] = RelativePosition(
                zone=zone,
                x_rel=max(0.0, min(1.0, x_rel)),
                y_rel=max(0.0, min(1.0, y_rel)),
                nearest_anchor=nearest_anchor,
                anchor_offset_x=anchor_offset_x,
                anchor_offset_y=anchor_offset_y,
            )

        return positions

    def _determine_zone_for_position(self, x: float, y: float) -> str:
        """Bestimme die Zone fuer eine gegebene Position."""
        if y < HEADER_ZONE_END:
            return "header"
        if y > FOOTER_ZONE_START:
            return "footer"
        if x > (1.0 - SIDEBAR_ZONE_MAX_WIDTH):
            return "sidebar"
        return "body"

    def _get_zone_bounds(
        self, zone_type: str, layout_zones: List[LayoutZone]
    ) -> Optional[NormalizedBounds]:
        """Hole die Bounds fuer eine Zone."""
        for zone in layout_zones:
            if zone.zone_type == zone_type:
                return zone.bounds
        return None

    def _find_nearest_anchor(
        self, x: float, y: float, text_anchors: List[TextAnchor]
    ) -> Tuple[Optional[str], float, float]:
        """Finde den naechsten Textanker und berechne den Offset."""
        if not text_anchors:
            return None, 0.0, 0.0

        nearest: Optional[TextAnchor] = None
        min_dist = float("inf")

        for anchor in text_anchors:
            anchor_x = anchor.normalized_position.center_x
            anchor_y = anchor.normalized_position.center_y
            dist = math.sqrt((x - anchor_x) ** 2 + (y - anchor_y) ** 2)
            if dist < min_dist:
                min_dist = dist
                nearest = anchor

        if nearest is None or min_dist > 0.5:
            return None, 0.0, 0.0

        offset_x = x - nearest.normalized_position.center_x
        offset_y = y - nearest.normalized_position.center_y

        return nearest.text, offset_x, offset_y

    def _determine_field_relationships(
        self,
        extracted_fields: Dict[str, Dict[str, object]],
        page_width: float,
        page_height: float,
    ) -> List[FieldRelationship]:
        """Bestimme raeumliche Beziehungen zwischen Feldern."""
        relationships: List[FieldRelationship] = []

        # Feld-Positionen extrahieren
        field_coords: Dict[str, Tuple[float, float]] = {}
        for field_name, field_data in extracted_fields.items():
            if not isinstance(field_data, dict):
                continue
            bbox = field_data.get("bounding_box", {})
            if not isinstance(bbox, dict) or "x" not in bbox:
                continue
            x_norm = float(bbox.get("x", 0)) / max(page_width, 1.0)
            y_norm = float(bbox.get("y", 0)) / max(page_height, 1.0)
            field_coords[field_name] = (x_norm, y_norm)

        field_names = list(field_coords.keys())

        # Paarweise Beziehungen (nur benachbarte Felder)
        for i in range(len(field_names)):
            for j in range(i + 1, len(field_names)):
                name_a = field_names[i]
                name_b = field_names[j]
                x_a, y_a = field_coords[name_a]
                x_b, y_b = field_coords[name_b]

                dx = x_b - x_a
                dy = y_b - y_a
                distance = math.sqrt(dx ** 2 + dy ** 2)

                # Nur nahegelegene Felder (< 30% der Seitendiagonale)
                if distance > 0.3:
                    continue

                # Beziehungstyp bestimmen
                same_line_threshold = 0.03
                if abs(dy) < same_line_threshold:
                    relationship = "same_line"
                elif abs(dx) < same_line_threshold:
                    relationship = "above" if dy > 0 else "below"
                elif dy > 0:
                    relationship = "left_of" if dx < 0 else "right_of"
                else:
                    relationship = "left_of" if dx < 0 else "right_of"

                relationships.append(FieldRelationship(
                    field_a=name_a,
                    field_b=name_b,
                    relationship=relationship,
                    distance=distance,
                ))

        return relationships

    def _compute_structural_hash(
        self,
        layout_zones: List[LayoutZone],
        field_positions: Dict[str, RelativePosition],
        text_anchors: List[TextAnchor],
    ) -> str:
        """Berechne einen strukturellen Hash fuer schnelles Matching."""
        # Hash-Bestandteile: Zonen-Typen + Feld-Zonen + Anker-Texte
        components: List[str] = []

        # Zonen-Typen (sortiert)
        zone_types = sorted(z.zone_type for z in layout_zones)
        components.append("zones:" + ",".join(zone_types))

        # Feld-Zonen-Zuordnung (sortiert)
        field_zones = sorted(
            f"{name}:{pos.zone}" for name, pos in field_positions.items()
        )
        components.append("fields:" + ",".join(field_zones))

        # Anker-Texte (sortiert, nur die ersten 10)
        anchor_texts = sorted(a.text for a in text_anchors[:10])
        components.append("anchors:" + ",".join(anchor_texts))

        hash_input = "|".join(components)
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:32]

    def _calculate_hint_confidence(
        self, match_type: str, similarity_score: float
    ) -> float:
        """Berechne die Confidence fuer Extraktions-Hinweise."""
        base_confidence_map: Dict[str, float] = {
            "exact_entity": 0.85,
            "structural": 0.65,
            "field_similarity": 0.50,
        }
        base = base_confidence_map.get(match_type, 0.40)
        # Skaliere mit dem Aehnlichkeitswert
        return min(0.95, base * similarity_score)

    def _calculate_expected_bounds(
        self,
        rel_pos: RelativePosition,
        layout_zones: List[LayoutZone],
    ) -> NormalizedBounds:
        """Berechne erwartete Bounds aus relativer Position + Zone."""
        zone_bounds = self._get_zone_bounds(rel_pos.zone, layout_zones)

        if zone_bounds is not None:
            x = zone_bounds.x + rel_pos.x_rel * zone_bounds.width
            y = zone_bounds.y + rel_pos.y_rel * zone_bounds.height
        else:
            x = rel_pos.x_rel
            y = rel_pos.y_rel

        # Standard-Feldgroesse
        return NormalizedBounds(
            x=max(0.0, min(0.95, x)),
            y=max(0.0, min(0.95, y)),
            width=0.15,
            height=0.03,
        )

    # --- DB-Hilfsmethoden ---

    async def _load_active_template(
        self,
        entity_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[SupplierOCRTemplate]:
        """Lade das aktive Template fuer eine Entity."""
        stmt = (
            select(SupplierOCRTemplate)
            .where(
                and_(
                    SupplierOCRTemplate.entity_id == entity_id,
                    SupplierOCRTemplate.company_id == company_id,
                    SupplierOCRTemplate.is_active == True,
                )
            )
            .order_by(SupplierOCRTemplate.version.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _extract_dna_from_template(
        self, template: SupplierOCRTemplate
    ) -> Optional[Dict[str, object]]:
        """Extrahiere DNA-Daten aus einem Template."""
        field_defs = template.field_definitions
        if not field_defs or not isinstance(field_defs, list):
            return None

        # DNA aus field_definitions und Template-Metadaten rekonstruieren
        dna_data: Dict[str, object] = {
            "layout_zones": [],
            "field_positions": {},
            "text_anchors": [],
            "field_relationships": [],
            "structural_hash": template.layout_fingerprint or "",
        }

        # Standard-Zonen
        dna_data["layout_zones"] = [
            {"zone_type": "header", "bounds": {"x": 0, "y": 0, "width": 1, "height": HEADER_ZONE_END}, "confidence": 0.9},
            {"zone_type": "body", "bounds": {"x": 0, "y": HEADER_ZONE_END, "width": 1, "height": FOOTER_ZONE_START - HEADER_ZONE_END}, "confidence": 0.8},
            {"zone_type": "footer", "bounds": {"x": 0, "y": FOOTER_ZONE_START, "width": 1, "height": 1 - FOOTER_ZONE_START}, "confidence": 0.9},
        ]

        # Felder aus field_definitions mappen
        for field_def in field_defs:
            if not isinstance(field_def, dict):
                continue
            name = field_def.get("name")
            coords = field_def.get("coordinates", {})
            if not name or not coords:
                continue

            x = float(coords.get("x", 0))
            y = float(coords.get("y", 0))
            zone = self._determine_zone_for_position(x, y)

            dna_data["field_positions"][name] = {
                "zone": zone,
                "x_rel": x,
                "y_rel": y,
                "nearest_anchor": None,
                "anchor_offset_x": 0.0,
                "anchor_offset_y": 0.0,
            }

        # Textanker aus Template
        if template.text_anchors and isinstance(template.text_anchors, list):
            for anchor_text in template.text_anchors:
                if isinstance(anchor_text, str):
                    dna_data["text_anchors"].append({
                        "text": anchor_text,
                        "normalized_position": {"x": 0.05, "y": 0.5, "width": 0.15, "height": 0.02},
                        "frequency": 1.0,
                    })

        return dna_data

    async def _save_dna_to_template(
        self,
        template: SupplierOCRTemplate,
        dna: DocumentDNA,
        db: AsyncSession,
    ) -> None:
        """Speichere DNA zurueck ins Template."""
        template.layout_fingerprint = dna.structural_hash
        template.text_anchors = [a.text for a in dna.text_anchors]
        template.field_definitions = self._dna_to_field_definitions(dna)
        template.training_document_count = (template.training_document_count or 0) + 1

        # Confidence aktualisieren (gleitender Durchschnitt)
        if template.average_confidence is not None:
            template.average_confidence = round(
                template.average_confidence * 0.9 + 0.85 * 0.1, 4
            )
        else:
            template.average_confidence = 0.75

        await db.flush()

    def _dna_to_field_definitions(self, dna: DocumentDNA) -> List[Dict[str, object]]:
        """Konvertiere DNA-Feldpositionen in Template field_definitions."""
        field_labels: Dict[str, str] = {
            "invoice_number": "Rechnungsnummer",
            "invoice_date": "Rechnungsdatum",
            "due_date": "Faelligkeitsdatum",
            "total_amount": "Gesamtbetrag",
            "net_amount": "Nettobetrag",
            "vat_amount": "Mehrwertsteuer",
            "vat_rate": "MwSt-Satz",
            "supplier_name": "Lieferant",
            "iban": "IBAN",
            "bic": "BIC",
            "order_number": "Bestellnummer",
            "delivery_note_number": "Lieferscheinnummer",
            "customer_number": "Kundennummer",
        }

        definitions: List[Dict[str, object]] = []

        for field_name, rel_pos in dna.field_positions.items():
            definitions.append({
                "name": field_name,
                "label": field_labels.get(field_name, field_name),
                "type": "anchor_relative" if rel_pos.nearest_anchor else "bounding_box",
                "coordinates": {
                    "x": round(rel_pos.x_rel, 4),
                    "y": round(rel_pos.y_rel, 4),
                    "width": 0.15,
                    "height": 0.03,
                },
                "zone": rel_pos.zone,
                "nearest_anchor": rel_pos.nearest_anchor,
                "anchor_offset": {
                    "x": round(rel_pos.anchor_offset_x, 4),
                    "y": round(rel_pos.anchor_offset_y, 4),
                } if rel_pos.nearest_anchor else None,
                "page": 1,
                "confidence_boost": 0.10,
            })

        return definitions

    # --- Matching-Hilfsmethoden ---

    async def _find_entity_match(
        self,
        dna: DocumentDNA,
        entity_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[DNAMatchResult]:
        """Finde Match ueber exakte Entity-ID."""
        template = await self._load_active_template(entity_id, company_id, db)
        if template is None:
            return None

        dna_data = self._extract_dna_from_template(template)
        if dna_data is None:
            return None

        stored_dna = DocumentDNA.from_dict(dna_data)
        similarity = self._calculate_dna_similarity(dna, stored_dna)

        if similarity < SIMILAR_MATCH_THRESHOLD:
            return None

        return DNAMatchResult(
            template_id=template.id,
            entity_id=entity_id,
            similarity_score=similarity,
            match_type="exact_entity",
            dna=stored_dna,
        )

    async def _find_structural_match(
        self,
        dna: DocumentDNA,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[DNAMatchResult]:
        """Finde Match ueber Layout-Fingerprint."""
        if not dna.structural_hash:
            return None

        stmt = (
            select(SupplierOCRTemplate)
            .where(
                and_(
                    SupplierOCRTemplate.company_id == company_id,
                    SupplierOCRTemplate.is_active == True,
                    SupplierOCRTemplate.layout_fingerprint == dna.structural_hash,
                )
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        template = result.scalar_one_or_none()

        if template is None:
            return None

        dna_data = self._extract_dna_from_template(template)
        if dna_data is None:
            return None

        stored_dna = DocumentDNA.from_dict(dna_data)

        return DNAMatchResult(
            template_id=template.id,
            entity_id=template.entity_id,
            similarity_score=EXACT_MATCH_THRESHOLD,
            match_type="structural",
            dna=stored_dna,
        )

    async def _find_field_similarity_match(
        self,
        dna: DocumentDNA,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[DNAMatchResult]:
        """Finde Match ueber Feld-Positions-Aehnlichkeit."""
        # Alle aktiven Templates laden
        stmt = (
            select(SupplierOCRTemplate)
            .where(
                and_(
                    SupplierOCRTemplate.company_id == company_id,
                    SupplierOCRTemplate.is_active == True,
                )
            )
            .limit(50)  # Performance-Limit
        )
        result = await db.execute(stmt)
        templates = result.scalars().all()

        best_match: Optional[DNAMatchResult] = None
        best_score = 0.0

        for template in templates:
            dna_data = self._extract_dna_from_template(template)
            if dna_data is None:
                continue

            stored_dna = DocumentDNA.from_dict(dna_data)
            similarity = self._calculate_dna_similarity(dna, stored_dna)

            if similarity > best_score and similarity >= SIMILAR_MATCH_THRESHOLD:
                best_score = similarity
                best_match = DNAMatchResult(
                    template_id=template.id,
                    entity_id=template.entity_id,
                    similarity_score=similarity,
                    match_type="field_similarity",
                    dna=stored_dna,
                )

        return best_match

    def _calculate_dna_similarity(
        self, dna_a: DocumentDNA, dna_b: DocumentDNA
    ) -> float:
        """Berechne Aehnlichkeit zwischen zwei DNAs (0-1)."""
        scores: List[float] = []

        # 1. Feld-Ueberlappung (Jaccard-Index)
        fields_a = set(dna_a.field_positions.keys())
        fields_b = set(dna_b.field_positions.keys())
        if fields_a or fields_b:
            intersection = len(fields_a & fields_b)
            union = len(fields_a | fields_b)
            field_overlap = intersection / max(union, 1)
            scores.append(field_overlap)

        # 2. Zonen-Uebereinstimmung
        zones_a = {z.zone_type for z in dna_a.layout_zones}
        zones_b = {z.zone_type for z in dna_b.layout_zones}
        if zones_a or zones_b:
            zone_intersection = len(zones_a & zones_b)
            zone_union = len(zones_a | zones_b)
            zone_overlap = zone_intersection / max(zone_union, 1)
            scores.append(zone_overlap)

        # 3. Positions-Aehnlichkeit fuer gemeinsame Felder
        common_fields = fields_a & fields_b if (fields_a and fields_b) else set()
        if common_fields:
            position_scores: List[float] = []
            for field_name in common_fields:
                pos_a = dna_a.field_positions[field_name]
                pos_b = dna_b.field_positions[field_name]
                dist = math.sqrt(
                    (pos_a.x_rel - pos_b.x_rel) ** 2
                    + (pos_a.y_rel - pos_b.y_rel) ** 2
                )
                # Distanz in Aehnlichkeit umwandeln (0 Distanz = 1.0)
                position_scores.append(max(0.0, 1.0 - dist * 5.0))

            if position_scores:
                scores.append(sum(position_scores) / len(position_scores))

        # 4. Anker-Uebereinstimmung
        anchors_a = {a.text for a in dna_a.text_anchors}
        anchors_b = {a.text for a in dna_b.text_anchors}
        if anchors_a or anchors_b:
            anchor_intersection = len(anchors_a & anchors_b)
            anchor_union = len(anchors_a | anchors_b)
            anchor_overlap = anchor_intersection / max(anchor_union, 1)
            scores.append(anchor_overlap)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)


# =============================================================================
# Factory
# =============================================================================


def get_document_dna_service() -> DocumentDNAService:
    """Factory fuer DocumentDNAService."""
    return DocumentDNAService()
