"""ValidationFieldService - Feld-Validierung und -Review.

Dieser Service verwaltet die Validierung einzelner extrahierter Felder.
Er integriert den UmlautValidationService und CrossFieldValidator fuer
umfassende deutsche Textvalidierung.

Verwendung:
    from app.services.validation_field_service import get_validation_field_service

    service = get_validation_field_service(db)
    fields = await service.get_fields_for_review(queue_item_id)
"""
import uuid
from datetime import datetime
from app.core.datetime_utils import utc_now
from typing import Optional, List, Dict, Any
import structlog
import re

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ValidationQueueItem,
    ValidationFieldReview,
    Document
)
from app.db.schemas import (
    ValidationFieldCreate,
    ValidationFieldUpdate,
    ValidationFieldResponse,
    ValidationFieldValidateResult,
)
from app.services.umlaut_validation_service import get_umlaut_validation_service
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# Deutsche Feld-Labels Mapping
FIELD_LABELS_DE = {
    "invoice_number": "Rechnungsnummer",
    "invoice_date": "Rechnungsdatum",
    "due_date": "Faelligkeitsdatum",
    "total_amount": "Gesamtbetrag",
    "net_amount": "Nettobetrag",
    "vat_amount": "Mehrwertsteuerbetrag",
    "vat_rate": "Steuersatz",
    "vendor_name": "Lieferant",
    "vendor_address": "Lieferantenadresse",
    "customer_name": "Kunde",
    "customer_address": "Kundenadresse",
    "iban": "IBAN",
    "bic": "BIC",
    "bank_name": "Bankname",
    "account_holder": "Kontoinhaber",
    "payment_terms": "Zahlungsbedingungen",
    "order_number": "Bestellnummer",
    "delivery_date": "Lieferdatum",
    "currency": "Waehrung",
    "tax_id": "Steuernummer",
    "vat_id": "USt-IdNr.",
}

# Feld-Typ-Mapping
FIELD_TYPES = {
    "invoice_number": "text",
    "invoice_date": "date",
    "due_date": "date",
    "total_amount": "currency",
    "net_amount": "currency",
    "vat_amount": "currency",
    "vat_rate": "percentage",
    "iban": "iban",
    "bic": "text",
    "vat_id": "vat_id",
    "tax_id": "text",
}


class ValidationFieldService:
    """Service fuer Feld-Validierung und -Review."""

    def __init__(self, db: AsyncSession):
        """Initialisiere den Service."""
        self.db = db
        self.umlaut_service = get_umlaut_validation_service()

    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================

    async def create_field_reviews(
        self,
        queue_item_id: uuid.UUID,
        extracted_data: Dict[str, Any],
        confidence_data: Optional[Dict[str, float]] = None,
        bounding_boxes: Optional[Dict[str, Dict[str, Any]]] = None,
        ocr_backend: Optional[str] = None,
        confidence_threshold: float = 0.85
    ) -> List[ValidationFieldReview]:
        """Erstellt Feld-Reviews aus extrahierten Daten.

        Args:
            queue_item_id: ID des Queue-Items
            extracted_data: Extrahierte Felder als Dict
            confidence_data: Confidence-Scores pro Feld
            bounding_boxes: PDF-Koordinaten pro Feld
            ocr_backend: Verwendetes OCR-Backend
            confidence_threshold: Schwellenwert fuer niedrige Confidence

        Returns:
            Liste der erstellten FieldReviews
        """
        confidence_data = confidence_data or {}
        bounding_boxes = bounding_boxes or {}
        field_reviews = []

        for field_key, value in extracted_data.items():
            if value is None:
                continue

            # Stringify value
            str_value = str(value) if not isinstance(value, str) else value

            # Get confidence
            confidence = confidence_data.get(field_key)
            is_below = False
            if confidence is not None:
                is_below = confidence < confidence_threshold

            # Get label and type
            field_label = FIELD_LABELS_DE.get(field_key, field_key.replace("_", " ").title())
            field_type = FIELD_TYPES.get(field_key, "text")

            field_review = ValidationFieldReview(
                queue_item_id=queue_item_id,
                field_key=field_key,
                field_label=field_label,
                field_type=field_type,
                original_value=str_value,
                confidence_score=confidence,
                confidence_threshold=confidence_threshold,
                is_below_threshold=is_below,
                bounding_box=bounding_boxes.get(field_key),
                ocr_backend=ocr_backend
            )

            self.db.add(field_review)
            field_reviews.append(field_review)

        await self.db.commit()

        # Refresh all
        for fr in field_reviews:
            await self.db.refresh(fr)

        logger.info(
            "field_reviews_created",
            queue_item_id=str(queue_item_id),
            field_count=len(field_reviews),
            below_threshold_count=sum(1 for f in field_reviews if f.is_below_threshold)
        )

        return field_reviews

    async def get_fields_for_review(
        self,
        queue_item_id: uuid.UUID
    ) -> List[ValidationFieldReview]:
        """Holt alle Feld-Reviews fuer ein Queue-Item.

        Args:
            queue_item_id: ID des Queue-Items

        Returns:
            Liste der FieldReviews
        """
        result = await self.db.execute(
            select(ValidationFieldReview)
            .where(ValidationFieldReview.queue_item_id == queue_item_id)
            .order_by(ValidationFieldReview.is_below_threshold.desc())  # Problematische zuerst
            .order_by(ValidationFieldReview.field_key.asc())
        )
        return list(result.scalars().all())

    async def get_field(self, field_id: uuid.UUID) -> Optional[ValidationFieldReview]:
        """Holt ein einzelnes Feld.

        Args:
            field_id: ID des Felds

        Returns:
            Das Feld oder None
        """
        result = await self.db.execute(
            select(ValidationFieldReview).where(ValidationFieldReview.id == field_id)
        )
        return result.scalar_one_or_none()

    async def update_field(
        self,
        field_id: uuid.UUID,
        corrected_value: str,
        reviewed_by_id: uuid.UUID
    ) -> Optional[ValidationFieldReview]:
        """Aktualisiert einen Feldwert.

        Args:
            field_id: ID des Felds
            corrected_value: Korrigierter Wert
            reviewed_by_id: ID des Reviewers

        Returns:
            Das aktualisierte Feld oder None
        """
        field = await self.get_field(field_id)
        if not field:
            return None

        # Check if value changed
        was_corrected = field.original_value != corrected_value

        field.corrected_value = corrected_value
        field.was_corrected = was_corrected
        field.reviewed_by_id = reviewed_by_id
        field.reviewed_at = utc_now()
        field.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(field)

        logger.info(
            "field_updated",
            field_id=str(field_id),
            field_key=field.field_key,
            was_corrected=was_corrected
        )

        return field

    # =========================================================================
    # VALIDATION
    # =========================================================================

    async def validate_field(
        self,
        field_id: uuid.UUID
    ) -> ValidationFieldValidateResult:
        """Validiert ein einzelnes Feld.

        Fuehrt Umlaut-Pruefung und Format-Validierung durch.

        Args:
            field_id: ID des Felds

        Returns:
            ValidationFieldValidateResult mit Fehlern und Vorschlaegen
        """
        field = await self.get_field(field_id)
        if not field:
            raise ValueError(f"Feld {field_id} nicht gefunden")

        value = field.corrected_value or field.original_value
        if not value:
            return ValidationFieldValidateResult(
                field_id=field_id,
                field_key=field.field_key,
                is_valid=True,
                errors=[],
                umlaut_issues=[],
                format_issues=[]
            )

        errors = []
        umlaut_issues = []
        format_issues = []
        suggested_correction = None

        # 1. Umlaut-Validierung
        try:
            umlaut_result = self.umlaut_service.validate_text(value)
            if umlaut_result and umlaut_result.get("suggestions"):
                for suggestion in umlaut_result["suggestions"]:
                    umlaut_issues.append({
                        "type": suggestion.get("type", "unknown"),
                        "position": suggestion.get("position"),
                        "original": suggestion.get("original"),
                        "suggested": suggestion.get("suggested"),
                        "confidence": suggestion.get("confidence", 0.0)
                    })

                # Beste Korrektur vorschlagen
                if umlaut_result.get("corrected_text"):
                    suggested_correction = umlaut_result["corrected_text"]
        except Exception as e:
            logger.warning("umlaut_validation_error", **safe_error_log(e), field_id=str(field_id))

        # 2. Format-Validierung basierend auf Feldtyp
        format_issues = self._validate_format(value, field.field_type, field.field_key)

        # 3. Speichern der Validierungsergebnisse
        all_errors = []
        if umlaut_issues:
            all_errors.extend([{"type": "umlaut", **issue} for issue in umlaut_issues])
        if format_issues:
            all_errors.extend([{"type": "format", **issue} for issue in format_issues])

        field.validation_errors = all_errors
        field.umlaut_issues = umlaut_issues
        field.format_issues = format_issues
        field.validation_status = "validated" if not all_errors else "error"
        field.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(field)

        is_valid = len(all_errors) == 0

        return ValidationFieldValidateResult(
            field_id=field_id,
            field_key=field.field_key,
            is_valid=is_valid,
            errors=all_errors,
            umlaut_issues=umlaut_issues,
            format_issues=format_issues,
            suggested_correction=suggested_correction
        )

    async def validate_all_fields(
        self,
        queue_item_id: uuid.UUID
    ) -> List[ValidationFieldValidateResult]:
        """Validiert alle Felder eines Queue-Items.

        Args:
            queue_item_id: ID des Queue-Items

        Returns:
            Liste der Validierungsergebnisse
        """
        fields = await self.get_fields_for_review(queue_item_id)
        results = []

        for field in fields:
            try:
                result = await self.validate_field(field.id)
                results.append(result)
            except Exception as e:
                logger.error(
                    "field_validation_failed",
                    field_id=str(field.id),
                    **safe_error_log(e)
                )
                results.append(ValidationFieldValidateResult(
                    field_id=field.id,
                    field_key=field.field_key,
                    is_valid=False,
                    errors=[{"type": "error", "message": safe_error_detail(e, "Validierung")}],
                    umlaut_issues=[],
                    format_issues=[]
                ))

        logger.info(
            "all_fields_validated",
            queue_item_id=str(queue_item_id),
            field_count=len(results),
            valid_count=sum(1 for r in results if r.is_valid)
        )

        return results

    def _validate_format(
        self,
        value: str,
        field_type: Optional[str],
        field_key: str
    ) -> List[Dict[str, Any]]:
        """Validiert das Format eines Feldwerts.

        Args:
            value: Der zu validierende Wert
            field_type: Typ des Felds
            field_key: Key des Felds

        Returns:
            Liste von Format-Fehlern
        """
        issues = []

        if not field_type or not value:
            return issues

        if field_type == "date":
            # Deutsche Datumsformate: DD.MM.YYYY, DD.MM.YY
            date_patterns = [
                r"^\d{1,2}\.\d{1,2}\.\d{4}$",
                r"^\d{1,2}\.\d{1,2}\.\d{2}$",
                r"^\d{4}-\d{2}-\d{2}$"  # ISO
            ]
            if not any(re.match(p, value.strip()) for p in date_patterns):
                issues.append({
                    "field": field_key,
                    "message": "Ungueltiges Datumsformat. Erwartet: TT.MM.JJJJ",
                    "expected_format": "TT.MM.JJJJ"
                })

        elif field_type == "currency":
            # Deutsche Waehrungsformate: 1.234,56 EUR oder 1234,56€
            currency_pattern = r"^-?[\d\s.]*,\d{2}\s*(EUR|€|CHF)?$|^-?[\d,]*\.\d{2}\s*(EUR|€|USD)?$"
            if not re.match(currency_pattern, value.strip(), re.IGNORECASE):
                issues.append({
                    "field": field_key,
                    "message": "Ungueltiges Waehrungsformat. Erwartet: 1.234,56 EUR",
                    "expected_format": "1.234,56 EUR"
                })

        elif field_type == "iban":
            # IBAN Validierung (vereinfacht)
            iban_clean = value.replace(" ", "").upper()
            if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$", iban_clean):
                issues.append({
                    "field": field_key,
                    "message": "Ungueltiges IBAN-Format",
                    "expected_format": "DE12 3456 7890 1234 5678 90"
                })
            elif len(iban_clean) < 15 or len(iban_clean) > 34:
                issues.append({
                    "field": field_key,
                    "message": "IBAN hat ungueltige Laenge",
                    "expected_length": "15-34 Zeichen"
                })

        elif field_type == "vat_id":
            # USt-IdNr. Format: DE123456789
            vat_clean = value.replace(" ", "").upper()
            if not re.match(r"^[A-Z]{2}[A-Z0-9]{2,12}$", vat_clean):
                issues.append({
                    "field": field_key,
                    "message": "Ungueltige USt-IdNr. Format: DE + 9 Ziffern",
                    "expected_format": "DE123456789"
                })

        elif field_type == "percentage":
            # Prozent: 19%, 19,00%, 7.5%
            percent_pattern = r"^-?\d+([.,]\d+)?%?$"
            if not re.match(percent_pattern, value.strip()):
                issues.append({
                    "field": field_key,
                    "message": "Ungueltiges Prozentformat",
                    "expected_format": "19% oder 19,00"
                })

        return issues

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    async def count_fields_below_threshold(
        self,
        queue_item_id: uuid.UUID
    ) -> int:
        """Zaehlt Felder unter dem Confidence-Schwellenwert.

        Args:
            queue_item_id: ID des Queue-Items

        Returns:
            Anzahl der problematischen Felder
        """
        result = await self.db.execute(
            select(func.count(ValidationFieldReview.id)).where(
                and_(
                    ValidationFieldReview.queue_item_id == queue_item_id,
                    ValidationFieldReview.is_below_threshold == True
                )
            )
        )
        return result.scalar() or 0

    async def get_field_stats(
        self,
        queue_item_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Holt Statistiken zu Feldern eines Queue-Items.

        Args:
            queue_item_id: ID des Queue-Items

        Returns:
            Dictionary mit Statistiken
        """
        fields = await self.get_fields_for_review(queue_item_id)

        total = len(fields)
        below_threshold = sum(1 for f in fields if f.is_below_threshold)
        corrected = sum(1 for f in fields if f.was_corrected)
        with_errors = sum(1 for f in fields if f.validation_errors)

        avg_confidence = None
        min_confidence = None
        if fields:
            confidences = [f.confidence_score for f in fields if f.confidence_score is not None]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                min_confidence = min(confidences)

        return {
            "total_fields": total,
            "below_threshold": below_threshold,
            "corrected": corrected,
            "with_errors": with_errors,
            "avg_confidence": avg_confidence,
            "min_confidence": min_confidence
        }


def get_validation_field_service(db: AsyncSession) -> ValidationFieldService:
    """Factory-Funktion fuer den ValidationFieldService.

    Args:
        db: Async-Datenbankverbindung

    Returns:
        ValidationFieldService Instanz
    """
    return ValidationFieldService(db)
