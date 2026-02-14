# -*- coding: utf-8 -*-
"""
Supplier OCR Template Service.

Vision 2026+ Feature #2: Dokumenten-Template-System (Lieferanten-spezifisch)
OCR-Genauigkeit von 95% auf 99%+ fuer wiederkehrende Lieferanten.

Features:
- Template pro Lieferant definieren
- Feste Feldpositionen (Bounding Boxes)
- Automatische Template-Erkennung via Logo/Layout
- Fallback auf Standard-OCR wenn Template nicht matched
- Template-Training via korrigierte Dokumente
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity
from app.core.safe_errors import safe_error_log
from app.db.models_ocr_template import (

    SupplierOCRTemplate,
    OCRTemplateSample,
    OCRTemplateMatchLog,
    FieldExtractionType,
    TemplateMatchingStrategy,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

TEMPLATE_MATCH_COUNTER = Counter(
    "ocr_template_match_total",
    "Anzahl der Template-Matching-Versuche",
    ["result"]  # matched, no_match, error
)

TEMPLATE_MATCH_DURATION = Histogram(
    "ocr_template_match_duration_seconds",
    "Dauer des Template-Matchings",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

TEMPLATE_EXTRACTION_COUNTER = Counter(
    "ocr_template_extraction_total",
    "Anzahl der Template-basierten Extraktionen",
    ["template_id", "result"]  # success, partial, failed
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FieldDefinition:
    """Definition eines zu extrahierenden Feldes."""
    name: str
    label: str
    extraction_type: str
    coordinates: Optional[Dict[str, int]] = None  # x, y, width, height
    page: int = 1
    anchor_text: Optional[str] = None
    offset: Optional[Dict[str, int]] = None
    regex_pattern: Optional[str] = None
    preprocessing: List[str] = field(default_factory=list)
    validation_regex: Optional[str] = None
    confidence_boost: float = 0.0
    required: bool = False


@dataclass
class ExtractionResult:
    """Ergebnis einer Feld-Extraktion."""
    field_name: str
    value: Optional[str]
    confidence: float
    source: str  # "template", "ocr_fallback", "corrected"
    coordinates: Optional[Dict[str, int]] = None
    validation_passed: bool = True
    raw_value: Optional[str] = None


@dataclass
class TemplateMatchResult:
    """Ergebnis des Template-Matchings."""
    matched: bool
    template: Optional[SupplierOCRTemplate] = None
    confidence: float = 0.0
    strategy_used: Optional[str] = None
    match_details: Dict[str, Any] = field(default_factory=dict)
    candidates_checked: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TemplateExtractionResult:
    """Vollstaendiges Ergebnis einer Template-basierten Extraktion."""
    template_id: Optional[uuid.UUID]
    template_name: Optional[str]
    match_confidence: float
    extractions: List[ExtractionResult]
    overall_confidence: float
    used_template: bool
    fields_extracted: int
    fields_failed: int
    processing_time_ms: int


class SupplierTemplateService:
    """
    Service fuer Lieferanten-spezifische OCR-Templates.

    Verwaltet Templates und wendet sie bei der OCR-Verarbeitung an.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service."""
        self.db = db

    # =========================================================================
    # Template CRUD
    # =========================================================================

    async def create_template(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        document_type: str = "invoice_incoming",
        field_definitions: Optional[List[Dict[str, Any]]] = None,
        text_anchors: Optional[List[str]] = None,
        matching_strategy: str = TemplateMatchingStrategy.COMBINED.value,
        description: Optional[str] = None,
    ) -> SupplierOCRTemplate:
        """
        Erstellt ein neues OCR-Template fuer einen Lieferanten.

        Args:
            entity_id: ID des Lieferanten
            company_id: Company-ID
            user_id: Ersteller
            name: Name des Templates
            document_type: Dokumenttyp (invoice_incoming, delivery_note, etc.)
            field_definitions: Liste der Feld-Definitionen
            text_anchors: Text-Anker fuer Matching
            matching_strategy: Strategie fuer Template-Erkennung
            description: Beschreibung

        Returns:
            Erstelltes Template
        """
        template = SupplierOCRTemplate(
            entity_id=entity_id,
            company_id=company_id,
            created_by_id=user_id,
            name=name,
            document_type=document_type,
            description=description,
            matching_strategy=matching_strategy,
            text_anchors=text_anchors or [],
            field_definitions=field_definitions or [],
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(
            "ocr_template_created",
            template_id=str(template.id),
            entity_id=str(entity_id),
            name=name,
        )

        return template

    async def get_template(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[SupplierOCRTemplate]:
        """Holt ein Template anhand seiner ID."""
        result = await self.db.execute(
            select(SupplierOCRTemplate).where(
                SupplierOCRTemplate.id == template_id,
                SupplierOCRTemplate.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_templates_for_entity(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[SupplierOCRTemplate]:
        """Holt alle Templates fuer einen Lieferanten."""
        query = select(SupplierOCRTemplate).where(
            SupplierOCRTemplate.entity_id == entity_id,
            SupplierOCRTemplate.company_id == company_id,
        )

        if active_only:
            query = query.where(SupplierOCRTemplate.is_active == True)

        query = query.order_by(SupplierOCRTemplate.version.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_template(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID,
        **kwargs,
    ) -> Optional[SupplierOCRTemplate]:
        """Aktualisiert ein Template."""
        template = await self.get_template(template_id, company_id)
        if not template:
            return None

        allowed_fields = {
            "name", "description", "document_type", "matching_strategy",
            "text_anchors", "header_patterns", "field_definitions",
            "is_active", "is_verified", "auto_apply",
        }

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(template, key, value)

        # Version erhoehen bei Feld-Aenderungen
        if "field_definitions" in kwargs:
            template.version += 1

        await self.db.commit()
        await self.db.refresh(template)

        return template

    async def delete_template(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Loescht ein Template (soft-delete via is_active)."""
        template = await self.get_template(template_id, company_id)
        if not template:
            return False

        template.is_active = False
        await self.db.commit()

        logger.info("ocr_template_deleted", template_id=str(template_id))
        return True

    # =========================================================================
    # Template Matching
    # =========================================================================

    async def find_matching_template(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
        ocr_text: Optional[str] = None,
    ) -> TemplateMatchResult:
        """
        Findet das passende Template fuer ein Dokument.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID
            entity_id: Optionale Entity-ID (falls bekannt)
            ocr_text: OCR-Text des Dokuments (fuer Text-Anchor-Matching)

        Returns:
            TemplateMatchResult mit gematchtem Template oder leer
        """
        start_time = time.perf_counter()
        candidates_checked = []

        # Lade Kandidaten-Templates
        query = select(SupplierOCRTemplate).where(
            SupplierOCRTemplate.company_id == company_id,
            SupplierOCRTemplate.is_active == True,
            SupplierOCRTemplate.auto_apply == True,
        )

        # Wenn Entity bekannt, bevorzuge deren Templates
        if entity_id:
            query = query.where(
                or_(
                    SupplierOCRTemplate.entity_id == entity_id,
                    SupplierOCRTemplate.entity_id.is_(None),  # Globale Templates
                )
            )

        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        if not templates:
            TEMPLATE_MATCH_COUNTER.labels(result="no_match").inc()
            return TemplateMatchResult(matched=False)

        best_match: Optional[SupplierOCRTemplate] = None
        best_score = 0.0
        best_strategy = None

        for template in templates:
            score, strategy, details = await self._calculate_match_score(
                template, ocr_text, entity_id
            )

            candidates_checked.append({
                "template_id": str(template.id),
                "template_name": template.name,
                "score": score,
                "strategy": strategy,
            })

            if score > best_score:
                best_score = score
                best_match = template
                best_strategy = strategy

        # Minimum-Threshold fuer Match
        MATCH_THRESHOLD = 0.7

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        TEMPLATE_MATCH_DURATION.observe(duration_ms / 1000)

        if best_match and best_score >= MATCH_THRESHOLD:
            TEMPLATE_MATCH_COUNTER.labels(result="matched").inc()

            # Log Match
            await self._log_match(
                document_id=document_id,
                company_id=company_id,
                template=best_match,
                confidence=best_score,
                strategy=best_strategy,
                candidates=candidates_checked,
                duration_ms=duration_ms,
            )

            return TemplateMatchResult(
                matched=True,
                template=best_match,
                confidence=best_score,
                strategy_used=best_strategy,
                match_details={"threshold": MATCH_THRESHOLD},
                candidates_checked=candidates_checked,
            )

        TEMPLATE_MATCH_COUNTER.labels(result="no_match").inc()
        return TemplateMatchResult(
            matched=False,
            confidence=best_score,
            candidates_checked=candidates_checked,
        )

    async def _calculate_match_score(
        self,
        template: SupplierOCRTemplate,
        ocr_text: Optional[str],
        entity_id: Optional[uuid.UUID],
    ) -> Tuple[float, str, Dict[str, Any]]:
        """
        Berechnet den Match-Score fuer ein Template.

        Returns:
            (score, strategy_used, details)
        """
        scores: Dict[str, float] = {}
        details: Dict[str, Any] = {}

        # 1. Entity-Match (hoechste Prioritaet)
        if entity_id and template.entity_id == entity_id:
            scores["entity"] = 0.5
            details["entity_match"] = True
        else:
            scores["entity"] = 0.0
            details["entity_match"] = False

        # 2. Text-Anchor-Match
        if ocr_text and template.text_anchors:
            anchor_matches = 0
            for anchor in template.text_anchors:
                if anchor.lower() in ocr_text.lower():
                    anchor_matches += 1

            if template.text_anchors:
                anchor_score = anchor_matches / len(template.text_anchors)
                scores["text_anchors"] = anchor_score * 0.3
                details["text_anchor_matches"] = anchor_matches
                details["text_anchor_total"] = len(template.text_anchors)

        # 3. Header-Pattern-Match
        if ocr_text and template.header_patterns:
            pattern_matches = 0
            for pattern in template.header_patterns:
                try:
                    if re.search(pattern, ocr_text, re.IGNORECASE):
                        pattern_matches += 1
                except re.error:
                    pass

            if template.header_patterns:
                pattern_score = pattern_matches / len(template.header_patterns)
                scores["header_patterns"] = pattern_score * 0.2
                details["pattern_matches"] = pattern_matches

        # 4. Historische Erfolgsrate
        if template.usage_count > 0:
            success_rate = template.successful_extractions / template.usage_count
            scores["history"] = success_rate * 0.1
            details["success_rate"] = success_rate

        # Gesamtscore
        total_score = sum(scores.values())

        # Strategie bestimmen
        strategy = template.matching_strategy
        if scores.get("entity", 0) > 0:
            strategy = "entity_match"
        elif scores.get("text_anchors", 0) > 0.2:
            strategy = "text_anchor"

        return total_score, strategy, details

    async def _log_match(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        template: Optional[SupplierOCRTemplate],
        confidence: float,
        strategy: Optional[str],
        candidates: List[Dict[str, Any]],
        duration_ms: int,
    ) -> None:
        """Loggt einen Match-Versuch."""
        log_entry = OCRTemplateMatchLog(
            document_id=document_id,
            company_id=company_id,
            matched_template_id=template.id if template else None,
            match_confidence=confidence,
            match_strategy_used=strategy,
            candidates_checked=candidates,
            match_duration_ms=duration_ms,
        )

        self.db.add(log_entry)
        await self.db.commit()

    # =========================================================================
    # Template-basierte Extraktion
    # =========================================================================

    async def apply_template_extraction(
        self,
        template: SupplierOCRTemplate,
        document_id: uuid.UUID,
        ocr_result: Dict[str, Any],
    ) -> TemplateExtractionResult:
        """
        Wendet ein Template auf OCR-Ergebnisse an.

        Args:
            template: Das anzuwendende Template
            document_id: Dokument-ID
            ocr_result: Rohe OCR-Ergebnisse (mit Bounding Boxes)

        Returns:
            TemplateExtractionResult mit extrahierten Feldern
        """
        start_time = time.perf_counter()
        extractions: List[ExtractionResult] = []
        fields_extracted = 0
        fields_failed = 0
        confidence_sum = 0.0

        for field_def in template.field_definitions:
            try:
                extraction = await self._extract_field(
                    field_def, ocr_result
                )
                extractions.append(extraction)

                if extraction.value:
                    fields_extracted += 1
                    confidence_sum += extraction.confidence
                else:
                    fields_failed += 1

            except Exception as e:
                logger.warning(
                    "field_extraction_failed",
                    field=field_def.get("name"),
                    **safe_error_log(e),
                )
                fields_failed += 1
                extractions.append(ExtractionResult(
                    field_name=field_def.get("name", "unknown"),
                    value=None,
                    confidence=0.0,
                    source="error",
                    validation_passed=False,
                ))

        # Durchschnittliche Confidence
        overall_confidence = (
            confidence_sum / fields_extracted if fields_extracted > 0 else 0.0
        )

        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Template-Statistiken aktualisieren
        template.usage_count += 1
        if fields_extracted > 0:
            template.successful_extractions += 1
        else:
            template.failed_extractions += 1

        template.last_used_at = datetime.now(timezone.utc)

        # Running Average fuer Confidence
        if template.average_confidence is None:
            template.average_confidence = overall_confidence
        else:
            template.average_confidence = (
                template.average_confidence * 0.9 + overall_confidence * 0.1
            )

        await self.db.commit()

        # Metriken
        result_label = "success" if fields_extracted > 0 else "failed"
        TEMPLATE_EXTRACTION_COUNTER.labels(
            template_id=str(template.id),
            result=result_label,
        ).inc()

        return TemplateExtractionResult(
            template_id=template.id,
            template_name=template.name,
            match_confidence=1.0,  # Template war bereits gematched
            extractions=extractions,
            overall_confidence=overall_confidence,
            used_template=True,
            fields_extracted=fields_extracted,
            fields_failed=fields_failed,
            processing_time_ms=processing_time_ms,
        )

    async def _extract_field(
        self,
        field_def: Dict[str, Any],
        ocr_result: Dict[str, Any],
    ) -> ExtractionResult:
        """
        Extrahiert ein einzelnes Feld basierend auf der Definition.
        """
        field_name = field_def.get("name", "unknown")
        extraction_type = field_def.get("type", "bounding_box")
        confidence_boost = field_def.get("confidence_boost", 0.0)

        value = None
        confidence = 0.0
        coordinates = None

        if extraction_type == FieldExtractionType.BOUNDING_BOX.value:
            value, confidence, coordinates = self._extract_by_bounding_box(
                field_def, ocr_result
            )

        elif extraction_type == FieldExtractionType.ANCHOR_RELATIVE.value:
            value, confidence = self._extract_by_anchor(
                field_def, ocr_result
            )

        elif extraction_type == FieldExtractionType.REGEX.value:
            value, confidence = self._extract_by_regex(
                field_def, ocr_result
            )

        # Preprocessing anwenden
        if value and field_def.get("preprocessing"):
            value = self._apply_preprocessing(value, field_def["preprocessing"])

        # Confidence-Boost
        confidence = min(1.0, confidence + confidence_boost)

        # Validierung
        validation_passed = True
        if value and field_def.get("validation_regex"):
            try:
                if not re.match(field_def["validation_regex"], value):
                    validation_passed = False
                    confidence *= 0.5  # Reduce confidence on validation failure
            except re.error:
                pass

        return ExtractionResult(
            field_name=field_name,
            value=value,
            confidence=confidence,
            source="template",
            coordinates=coordinates,
            validation_passed=validation_passed,
            raw_value=value,
        )

    def _extract_by_bounding_box(
        self,
        field_def: Dict[str, Any],
        ocr_result: Dict[str, Any],
    ) -> Tuple[Optional[str], float, Optional[Dict[str, int]]]:
        """Extrahiert Text aus einer Bounding Box."""
        coords = field_def.get("coordinates", {})
        target_page = field_def.get("page", 1)

        if not coords:
            return None, 0.0, None

        x, y = coords.get("x", 0), coords.get("y", 0)
        width, height = coords.get("width", 100), coords.get("height", 30)

        # Suche nach Text-Bloecken die in der Box liegen
        # (Vereinfachte Implementierung - echte wuerde OCR-Blöcke pruefen)
        blocks = ocr_result.get("blocks", [])
        matching_text = []
        total_confidence = 0.0
        count = 0

        for block in blocks:
            block_coords = block.get("coordinates", {})
            bx, by = block_coords.get("x", 0), block_coords.get("y", 0)

            # Pruefen ob Block in der Zielbox liegt
            if (x <= bx <= x + width and y <= by <= y + height):
                matching_text.append(block.get("text", ""))
                total_confidence += block.get("confidence", 0.8)
                count += 1

        if matching_text:
            value = " ".join(matching_text).strip()
            avg_confidence = total_confidence / count if count > 0 else 0.8
            return value, avg_confidence, coords

        return None, 0.0, coords

    def _extract_by_anchor(
        self,
        field_def: Dict[str, Any],
        ocr_result: Dict[str, Any],
    ) -> Tuple[Optional[str], float]:
        """Extrahiert Text relativ zu einem Anker-Text."""
        anchor_text = field_def.get("anchor_text", "")
        full_text = ocr_result.get("full_text", "")

        if not anchor_text or not full_text:
            return None, 0.0

        # Finde Anker-Position
        anchor_pos = full_text.lower().find(anchor_text.lower())
        if anchor_pos == -1:
            return None, 0.0

        # Extrahiere Text nach dem Anker
        start_pos = anchor_pos + len(anchor_text)

        # Finde das Ende (naechster Zeilenumbruch oder festes Offset)
        end_pos = full_text.find("\n", start_pos)
        if end_pos == -1:
            end_pos = start_pos + 100  # Max 100 Zeichen

        value = full_text[start_pos:end_pos].strip()

        # Entferne fuehrende Trennzeichen
        value = re.sub(r'^[:\s]+', '', value)

        return value, 0.85 if value else 0.0

    def _extract_by_regex(
        self,
        field_def: Dict[str, Any],
        ocr_result: Dict[str, Any],
    ) -> Tuple[Optional[str], float]:
        """Extrahiert Text mittels Regex-Pattern."""
        pattern = field_def.get("regex_pattern", "")
        full_text = ocr_result.get("full_text", "")

        if not pattern or not full_text:
            return None, 0.0

        try:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                # Verwende erste Gruppe falls vorhanden
                value = match.group(1) if match.groups() else match.group(0)
                return value.strip(), 0.9

        except re.error:
            pass

        return None, 0.0

    def _apply_preprocessing(
        self,
        value: str,
        steps: List[str],
    ) -> str:
        """Wendet Preprocessing-Schritte auf extrahierten Wert an."""
        result = value

        for step in steps:
            if step == "trim":
                result = result.strip()

            elif step == "uppercase":
                result = result.upper()

            elif step == "lowercase":
                result = result.lower()

            elif step.startswith("remove_prefix:"):
                prefix = step[14:]
                if result.startswith(prefix):
                    result = result[len(prefix):].strip()

            elif step.startswith("remove_suffix:"):
                suffix = step[14:]
                if result.endswith(suffix):
                    result = result[:-len(suffix)].strip()

            elif step == "extract_number":
                # Extrahiere nur numerische Teile
                numbers = re.findall(r'[\d.,]+', result)
                if numbers:
                    result = numbers[0]

            elif step == "normalize_german_number":
                # 1.234,56 -> 1234.56
                result = result.replace(".", "").replace(",", ".")

        return result

    # =========================================================================
    # High-Level Template Application (Document-ID based)
    # =========================================================================

    async def extract_with_template_for_document(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> TemplateExtractionResult:
        """
        Finde und wende das beste Template fuer ein Dokument an.

        Sucht das passende Template basierend auf Entity des Dokuments,
        extrahiert Felder und loggt das Ergebnis in OCRTemplateMatchLog.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID (Multi-Tenant)

        Returns:
            TemplateExtractionResult mit extrahierten Feldern

        Raises:
            ValueError: Wenn Dokument nicht gefunden
        """
        from app.db.models import Document, OCRResult

        # Dokument laden
        doc_result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            raise ValueError("Dokument nicht gefunden")

        entity_id = document.business_entity_id

        # OCR-Ergebnis laden
        ocr_stmt = select(OCRResult).where(OCRResult.document_id == document_id)
        ocr_res = await self.db.execute(ocr_stmt)
        ocr_result_row = ocr_res.scalar_one_or_none()

        if not ocr_result_row:
            return TemplateExtractionResult(
                template_id=None,
                template_name=None,
                match_confidence=0.0,
                extractions=[],
                overall_confidence=0.0,
                used_template=False,
                fields_extracted=0,
                fields_failed=0,
                processing_time_ms=0,
            )

        # Baue OCR-Ergebnis Dict aus verfuegbaren Daten
        ocr_data: Dict[str, Any] = {}
        if ocr_result_row.bounding_boxes:
            ocr_data["blocks"] = ocr_result_row.bounding_boxes
        else:
            ocr_data["blocks"] = []
        if ocr_result_row.extracted_text:
            ocr_data["full_text"] = ocr_result_row.extracted_text

        # Template-Matching
        match_result = await self.find_matching_template(
            document_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            ocr_text=ocr_data.get("full_text"),
        )

        if not match_result.matched or not match_result.template:
            return TemplateExtractionResult(
                template_id=None,
                template_name=None,
                match_confidence=match_result.confidence,
                extractions=[],
                overall_confidence=0.0,
                used_template=False,
                fields_extracted=0,
                fields_failed=0,
                processing_time_ms=0,
            )

        # Template anwenden
        extraction_result = await self.apply_template_extraction(
            template=match_result.template,
            document_id=document_id,
            ocr_result=ocr_data,
        )

        # Match-Log mit Extraktion aktualisieren
        log_stmt = (
            select(OCRTemplateMatchLog)
            .where(
                and_(
                    OCRTemplateMatchLog.document_id == document_id,
                    OCRTemplateMatchLog.matched_template_id == match_result.template.id,
                )
            )
            .order_by(OCRTemplateMatchLog.created_at.desc())
            .limit(1)
        )
        log_res = await self.db.execute(log_stmt)
        match_log = log_res.scalar_one_or_none()

        if match_log:
            match_log.extraction_applied = True
            match_log.extraction_confidence = extraction_result.overall_confidence
            match_log.fields_extracted = extraction_result.fields_extracted
            match_log.extraction_duration_ms = extraction_result.processing_time_ms

        await self.db.commit()

        logger.info(
            "template_extraction_for_document",
            document_id=str(document_id),
            template_id=str(extraction_result.template_id),
            fields_extracted=extraction_result.fields_extracted,
            overall_confidence=extraction_result.overall_confidence,
        )

        return extraction_result

    # =========================================================================
    # Template Training
    # =========================================================================

    async def train_from_document(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        corrected_values: Dict[str, Any],
        entity_id: Optional[uuid.UUID] = None,
        template_id: Optional[uuid.UUID] = None,
    ) -> SupplierOCRTemplate:
        """
        Trainiert oder erstellt ein Template basierend auf korrigierten Werten.

        Args:
            document_id: Dokument das als Training dient
            company_id: Company-ID
            user_id: User der korrigiert hat
            corrected_values: Korrigierte Feldwerte
            entity_id: Lieferanten-ID
            template_id: Existierendes Template zum Verbessern

        Returns:
            Aktualisiertes oder neues Template
        """
        # Lade Dokument
        doc_result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        # Entity bestimmen
        if not entity_id:
            entity_id = document.business_entity_id

        if not entity_id:
            raise ValueError("Keine Entity fuer Template-Training vorhanden")

        # Existierendes Template laden oder neues erstellen
        if template_id:
            template = await self.get_template(template_id, company_id)
            if not template:
                raise ValueError("Template nicht gefunden")
        else:
            # Suche existierendes Template fuer diese Entity
            templates = await self.get_templates_for_entity(
                entity_id, company_id, active_only=True
            )

            if templates:
                template = templates[0]  # Neuestes verwenden
            else:
                # Neues Template erstellen
                template = await self.create_template(
                    entity_id=entity_id,
                    company_id=company_id,
                    user_id=user_id,
                    name=f"Auto-Template {datetime.now().strftime('%Y-%m-%d')}",
                    document_type=document.document_type or "invoice_incoming",
                )

        # Training-Sample erstellen
        sample = OCRTemplateSample(
            template_id=template.id,
            document_id=document_id,
            company_id=company_id,
            corrected_by_id=user_id,
            corrected_extraction=corrected_values,
            corrected_fields=list(corrected_values.keys()),
            is_verified=True,
            is_used_for_training=True,
        )

        self.db.add(sample)
        template.training_document_count += 1

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(
            "template_trained",
            template_id=str(template.id),
            document_id=str(document_id),
            fields=list(corrected_values.keys()),
        )

        return template

    # =========================================================================
    # Statistiken
    # =========================================================================

    async def get_template_statistics(
        self,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken ueber alle Templates."""
        # Anzahl Templates
        count_result = await self.db.execute(
            select(func.count(SupplierOCRTemplate.id)).where(
                SupplierOCRTemplate.company_id == company_id,
                SupplierOCRTemplate.is_active == True,
            )
        )
        total_templates = count_result.scalar() or 0

        # Durchschnittliche Erfolgsrate
        stats_result = await self.db.execute(
            select(
                func.sum(SupplierOCRTemplate.usage_count),
                func.sum(SupplierOCRTemplate.successful_extractions),
                func.avg(SupplierOCRTemplate.average_confidence),
            ).where(
                SupplierOCRTemplate.company_id == company_id,
                SupplierOCRTemplate.is_active == True,
            )
        )
        row = stats_result.one()

        total_usage = row[0] or 0
        total_success = row[1] or 0
        avg_confidence = row[2] or 0.0

        success_rate = total_success / total_usage if total_usage > 0 else 0.0

        return {
            "total_templates": total_templates,
            "total_usage": total_usage,
            "total_successful": total_success,
            "success_rate": round(success_rate, 4),
            "average_confidence": round(avg_confidence, 4) if avg_confidence else None,
        }
