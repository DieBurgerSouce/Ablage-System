# -*- coding: utf-8 -*-
"""
Auto-Template Generation Service.

Automatische Erkennung und Generierung von OCR-Templates
basierend auf wiederkehrenden Dokumenten eines Lieferanten.

Wenn 3+ Dokumente vom selben Lieferanten aehnliche Layouts haben,
wird automatisch ein Template generiert.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, OCRResult
from app.db.models_ocr_template import SupplierOCRTemplate, OCRTemplateSample
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Minimum documents needed for template auto-generation
MIN_DOCUMENTS_FOR_TEMPLATE = 3
# Position tolerance for field matching (5% of page dimension)
POSITION_TOLERANCE = 0.05


@dataclass
class FieldPosition:
    """Position eines extrahierten Feldes auf der Seite."""
    field_name: str
    x: float  # Normalisierte X-Position (0-1)
    y: float  # Normalisierte Y-Position (0-1)
    width: float
    height: float
    page: int = 1


@dataclass
class TemplateCandidateResult:
    """Ergebnis der Template-Kandidaten-Erkennung."""
    entity_id: UUID
    company_id: UUID
    document_count: int
    matching_fields: List[str]
    avg_position_variance: float
    is_candidate: bool
    document_ids: List[UUID]
    field_positions: Dict[str, List[FieldPosition]]


class AutoTemplateService:
    """Service fuer automatische Template-Generierung."""

    async def detect_template_candidate(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[TemplateCandidateResult]:
        """
        Pruefe ob ein Lieferant genug aehnliche Dokumente hat fuer ein Template.

        Analysiert OCR-Ergebnisse der letzten Dokumente und vergleicht
        Feld-Positionen (Bounding Boxes) auf Konsistenz.
        """
        # Query documents from this entity with OCR results
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.entity_id == entity_id,
                    Document.ocr_status == "completed",
                )
            )
            .order_by(Document.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        documents = result.scalars().all()

        if len(documents) < MIN_DOCUMENTS_FOR_TEMPLATE:
            return None

        # Extract field positions from OCR results for each document
        all_positions: Dict[UUID, Dict[str, FieldPosition]] = {}
        for doc in documents:
            positions = await self._extract_field_positions(db, doc.id)
            if positions:
                all_positions[doc.id] = positions

        if len(all_positions) < MIN_DOCUMENTS_FOR_TEMPLATE:
            return None

        # Compare positions across documents
        common_fields = self._find_common_fields(all_positions)
        if not common_fields:
            return None

        # Calculate position variance for common fields
        field_positions_map: Dict[str, List[FieldPosition]] = {}
        total_variance = 0.0
        field_count = 0

        for field_name in common_fields:
            positions_list: List[FieldPosition] = []
            for doc_id, positions in all_positions.items():
                if field_name in positions:
                    positions_list.append(positions[field_name])

            field_positions_map[field_name] = positions_list
            variance = self._calculate_position_variance(positions_list)
            total_variance += variance
            field_count += 1

        avg_variance = total_variance / max(field_count, 1)
        is_candidate = avg_variance < POSITION_TOLERANCE and len(common_fields) >= 3

        return TemplateCandidateResult(
            entity_id=entity_id,
            company_id=company_id,
            document_count=len(all_positions),
            matching_fields=common_fields,
            avg_position_variance=avg_variance,
            is_candidate=is_candidate,
            document_ids=list(all_positions.keys()),
            field_positions=field_positions_map,
        )

    async def generate_template(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        document_ids: List[UUID],
        name: Optional[str] = None,
    ) -> SupplierOCRTemplate:
        """
        Generiere ein Template aus mehreren Dokumenten eines Lieferanten.

        Berechnet durchschnittliche Feld-Positionen und erstellt
        Extraktionsregeln basierend auf Feldtyp-Mustern.
        """
        # Get field positions for all specified documents
        all_positions: Dict[UUID, Dict[str, FieldPosition]] = {}
        for doc_id in document_ids:
            positions = await self._extract_field_positions(db, doc_id)
            if positions:
                all_positions[doc_id] = positions

        if len(all_positions) < MIN_DOCUMENTS_FOR_TEMPLATE:
            raise ValueError(
                f"Mindestens {MIN_DOCUMENTS_FOR_TEMPLATE} Dokumente mit OCR-Ergebnissen benoetigt"
            )

        # Build averaged field definitions
        common_fields = self._find_common_fields(all_positions)
        field_definitions = self._build_field_definitions(all_positions, common_fields)

        # Create template
        template_name = name or f"Auto-Template Lieferant"
        template = SupplierOCRTemplate(
            id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
            name=template_name,
            description=f"Automatisch generiert aus {len(all_positions)} Dokumenten",
            document_type="invoice_incoming",
            matching_strategy="combined",
            field_definitions=field_definitions,
            training_document_count=len(all_positions),
            is_active=True,
            is_verified=False,
            auto_apply=False,  # Not auto-apply until verified
            is_auto_generated=True,
            source_document_ids=[str(did) for did in document_ids],
            auto_confidence=self._calculate_template_confidence(all_positions, common_fields),
        )

        db.add(template)

        # Create training samples
        for doc_id in document_ids:
            sample = OCRTemplateSample(
                id=uuid4(),
                template_id=template.id,
                document_id=doc_id,
                company_id=company_id,
                is_used_for_training=True,
            )
            db.add(sample)

        await db.flush()

        logger.info(
            "Auto-Template generiert",
            template_id=str(template.id),
            entity_id=str(entity_id),
            fields=len(field_definitions),
            documents=len(all_positions),
        )

        return template

    async def list_candidates(
        self,
        db: AsyncSession,
        company_id: UUID,
        min_documents: int = MIN_DOCUMENTS_FOR_TEMPLATE,
    ) -> List[TemplateCandidateResult]:
        """Liste alle Template-Kandidaten fuer eine Company."""
        # Find entities with enough documents that don't have a template yet
        stmt = (
            select(
                Document.entity_id,
                func.count(Document.id).label("doc_count"),
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.entity_id.isnot(None),
                    Document.ocr_status == "completed",
                )
            )
            .group_by(Document.entity_id)
            .having(func.count(Document.id) >= min_documents)
        )
        result = await db.execute(stmt)
        entity_counts = result.all()

        candidates: List[TemplateCandidateResult] = []
        for row in entity_counts:
            entity_id = row[0]
            if entity_id is None:
                continue

            # Check if template already exists
            existing = await db.execute(
                select(SupplierOCRTemplate.id).where(
                    and_(
                        SupplierOCRTemplate.entity_id == entity_id,
                        SupplierOCRTemplate.company_id == company_id,
                        SupplierOCRTemplate.is_active == True,
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue

            candidate = await self.detect_template_candidate(db, entity_id, company_id)
            if candidate and candidate.is_candidate:
                candidates.append(candidate)

        return candidates

    async def _extract_field_positions(
        self, db: AsyncSession, document_id: UUID
    ) -> Dict[str, FieldPosition]:
        """Extrahiere Feld-Positionen aus OCR-Ergebnissen eines Dokuments."""
        stmt = select(OCRResult).where(OCRResult.document_id == document_id)
        result = await db.execute(stmt)
        ocr_result = result.scalar_one_or_none()

        if not ocr_result or not ocr_result.extracted_fields:
            return {}

        positions: Dict[str, FieldPosition] = {}
        extracted = ocr_result.extracted_fields
        if not isinstance(extracted, dict):
            return {}

        for field_name, field_data in extracted.items():
            if isinstance(field_data, dict) and "bounding_box" in field_data:
                bbox = field_data["bounding_box"]
                if isinstance(bbox, dict):
                    positions[field_name] = FieldPosition(
                        field_name=field_name,
                        x=float(bbox.get("x", 0)),
                        y=float(bbox.get("y", 0)),
                        width=float(bbox.get("width", 0)),
                        height=float(bbox.get("height", 0)),
                        page=int(bbox.get("page", 1)),
                    )

        return positions

    def _find_common_fields(
        self, all_positions: Dict[UUID, Dict[str, FieldPosition]]
    ) -> List[str]:
        """Finde Felder die in mindestens 2/3 der Dokumente vorkommen."""
        field_counts: Dict[str, int] = {}
        for positions in all_positions.values():
            for field_name in positions:
                field_counts[field_name] = field_counts.get(field_name, 0) + 1

        threshold = max(len(all_positions) * 2 // 3, MIN_DOCUMENTS_FOR_TEMPLATE)
        return [
            name for name, count in field_counts.items()
            if count >= threshold
        ]

    def _calculate_position_variance(self, positions: List[FieldPosition]) -> float:
        """Berechne die Positionsvarianz fuer eine Liste von Feld-Positionen."""
        if len(positions) < 2:
            return 0.0

        x_values = [p.x for p in positions]
        y_values = [p.y for p in positions]

        x_mean = sum(x_values) / len(x_values)
        y_mean = sum(y_values) / len(y_values)

        x_var = sum((x - x_mean) ** 2 for x in x_values) / len(x_values)
        y_var = sum((y - y_mean) ** 2 for y in y_values) / len(y_values)

        return (x_var + y_var) ** 0.5

    def _build_field_definitions(
        self,
        all_positions: Dict[UUID, Dict[str, FieldPosition]],
        common_fields: List[str],
    ) -> List[Dict[str, object]]:
        """Erstelle Field-Definitionen mit gemittelten Positionen."""
        definitions: List[Dict[str, object]] = []

        for field_name in common_fields:
            positions: List[FieldPosition] = []
            for doc_positions in all_positions.values():
                if field_name in doc_positions:
                    positions.append(doc_positions[field_name])

            if not positions:
                continue

            avg_x = sum(p.x for p in positions) / len(positions)
            avg_y = sum(p.y for p in positions) / len(positions)
            avg_w = sum(p.width for p in positions) / len(positions)
            avg_h = sum(p.height for p in positions) / len(positions)

            # Determine field label based on name
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

            definitions.append({
                "name": field_name,
                "label": field_labels.get(field_name, field_name),
                "type": "bounding_box",
                "coordinates": {
                    "x": round(avg_x, 4),
                    "y": round(avg_y, 4),
                    "width": round(avg_w, 4),
                    "height": round(avg_h, 4),
                },
                "page": positions[0].page,
                "sample_count": len(positions),
                "confidence_boost": 0.10,
            })

        return definitions

    def _calculate_template_confidence(
        self,
        all_positions: Dict[UUID, Dict[str, FieldPosition]],
        common_fields: List[str],
    ) -> float:
        """Berechne Gesamtvertrauen des Templates."""
        if not common_fields:
            return 0.0

        total_score = 0.0
        for field_name in common_fields:
            positions: List[FieldPosition] = []
            for doc_positions in all_positions.values():
                if field_name in doc_positions:
                    positions.append(doc_positions[field_name])

            variance = self._calculate_position_variance(positions)
            # Lower variance = higher confidence
            field_score = max(0.0, 1.0 - variance * 10)
            total_score += field_score

        return round(total_score / len(common_fields), 3)


    async def update_template_from_correction(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        field_name: str,
        corrected_bounding_box: Dict[str, float],
        corrected_value: str,
    ) -> Optional[SupplierOCRTemplate]:
        """
        Aktualisiere Template-Feldpositionen basierend auf User-Korrektur.

        Wenn ein Benutzer ein OCR-Feld korrigiert und ein Template fuer
        diese Entity existiert, werden die Koordinaten per gewichtetem
        Durchschnitt aktualisiert.

        Args:
            db: Datenbank-Session
            entity_id: Entity-ID des Lieferanten
            company_id: Company-ID (Multi-Tenant)
            field_name: Name des korrigierten Feldes
            corrected_bounding_box: Neue Bounding Box (x, y, width, height)
            corrected_value: Der korrigierte Wert

        Returns:
            Aktualisiertes Template oder None
        """
        # Template fuer diese Entity laden
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
        template = result.scalar_one_or_none()

        if not template:
            return None

        if not template.field_definitions:
            return None

        field_definitions: List[Dict[str, object]] = list(template.field_definitions)
        field_updated = False

        for idx, field_def in enumerate(field_definitions):
            if field_def.get("name") != field_name:
                continue

            existing_coords = field_def.get("coordinates", {})
            if not existing_coords:
                # Erstes Mal: Setze Koordinaten direkt
                field_definitions[idx]["coordinates"] = {
                    "x": round(corrected_bounding_box.get("x", 0), 4),
                    "y": round(corrected_bounding_box.get("y", 0), 4),
                    "width": round(corrected_bounding_box.get("width", 0), 4),
                    "height": round(corrected_bounding_box.get("height", 0), 4),
                }
            else:
                # Gewichteter Durchschnitt: bestehend (80%) + korrektur (20%)
                sample_count = field_def.get("sample_count", 1)
                weight_existing = min(sample_count, 10) / (min(sample_count, 10) + 1)
                weight_new = 1.0 - weight_existing

                field_definitions[idx]["coordinates"] = {
                    "x": round(
                        float(existing_coords.get("x", 0)) * weight_existing
                        + corrected_bounding_box.get("x", 0) * weight_new,
                        4,
                    ),
                    "y": round(
                        float(existing_coords.get("y", 0)) * weight_existing
                        + corrected_bounding_box.get("y", 0) * weight_new,
                        4,
                    ),
                    "width": round(
                        float(existing_coords.get("width", 0)) * weight_existing
                        + corrected_bounding_box.get("width", 0) * weight_new,
                        4,
                    ),
                    "height": round(
                        float(existing_coords.get("height", 0)) * weight_existing
                        + corrected_bounding_box.get("height", 0) * weight_new,
                        4,
                    ),
                }

            field_definitions[idx]["sample_count"] = field_def.get("sample_count", 1) + 1
            field_updated = True
            break

        if not field_updated:
            # Feld existiert noch nicht im Template: hinzufuegen
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
            field_definitions.append({
                "name": field_name,
                "label": field_labels.get(field_name, field_name),
                "type": "bounding_box",
                "coordinates": {
                    "x": round(corrected_bounding_box.get("x", 0), 4),
                    "y": round(corrected_bounding_box.get("y", 0), 4),
                    "width": round(corrected_bounding_box.get("width", 0), 4),
                    "height": round(corrected_bounding_box.get("height", 0), 4),
                },
                "page": 1,
                "sample_count": 1,
                "confidence_boost": 0.10,
            })

        template.field_definitions = field_definitions
        template.training_document_count += 1

        # Durchschnittliche Confidence neu berechnen
        if template.average_confidence is not None:
            # Gleitender Durchschnitt
            template.average_confidence = round(
                template.average_confidence * 0.9 + 0.95 * 0.1, 4
            )
        else:
            template.average_confidence = 0.85

        await db.flush()

        # Auto-Aktivierung pruefen
        await self.check_and_auto_activate(db, template)

        logger.info(
            "template_updated_from_correction",
            template_id=str(template.id),
            entity_id=str(entity_id),
            field_name=field_name,
            training_count=template.training_document_count,
        )

        return template

    async def check_and_auto_activate(
        self,
        db: AsyncSession,
        template: SupplierOCRTemplate,
    ) -> bool:
        """
        Pruefe ob Template automatisch aktiviert werden soll.

        Aktiviert auto_apply wenn:
        - auto_confidence >= 0.85
        - training_document_count >= 5
        - Template noch nicht auto_apply ist

        Args:
            db: Datenbank-Session
            template: Das zu pruefende Template

        Returns:
            True wenn auto_apply aktiviert wurde
        """
        if template.auto_apply:
            return False

        auto_confidence = template.auto_confidence or 0.0
        avg_confidence = template.average_confidence or 0.0
        effective_confidence = max(auto_confidence, avg_confidence)

        if effective_confidence >= 0.85 and template.training_document_count >= 5:
            template.auto_apply = True
            await db.flush()

            logger.info(
                "template_auto_activated",
                template_id=str(template.id),
                entity_id=str(template.entity_id),
                confidence=effective_confidence,
                training_count=template.training_document_count,
            )
            return True

        return False


def get_auto_template_service() -> AutoTemplateService:
    """Factory fuer AutoTemplateService."""
    return AutoTemplateService()
