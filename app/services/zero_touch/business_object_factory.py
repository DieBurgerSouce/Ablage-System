"""
Business Object Factory.

Erstellt Business-Objekte (z.B. InvoiceTracking) aus OCR-Extraktionsdaten.
Unterstützt verschiedene Dokumententypen mit spezifischen Datenmodellen.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Union
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, InvoiceTracking, InvoiceStatus
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


@dataclass
class BusinessObjectResult:
    """Ergebnis der Business-Object-Erstellung."""

    success: bool
    object_type: str
    object_id: Optional[UUID] = None
    error: Optional[str] = None


class BusinessObjectFactory:
    """
    Factory zum Erstellen von Business-Objekten aus Extraktionsdaten.

    Unterstützt:
    - invoice -> InvoiceTracking
    - contract -> (zukünftig)
    - delivery_note -> (zukünftig)
    - order -> (zukünftig)
    - offer -> (zukünftig)
    """

    async def create_business_object(
        self,
        document_id: UUID,
        classification_type: str,
        extracted_fields: Dict[str, Dict[str, Any]],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> BusinessObjectResult:
        """
        Erstellt ein Business-Objekt basierend auf Dokumententyp.

        Args:
            document_id: ID des Dokuments
            classification_type: Dokumententyp (invoice, contract, etc.)
            extracted_fields: Extrahierte Felder mit {field_name: {value, confidence}}
            entity_id: Optional Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            BusinessObjectResult mit Erfolgs-Status und Objekt-ID
        """
        logger.info(
            "creating_business_object",
            document_id=str(document_id),
            classification_type=classification_type,
            has_entity=entity_id is not None,
        )

        try:
            # Dokumententyp-spezifische Erstellung
            if classification_type == "invoice":
                return await self._create_invoice_tracking(
                    document_id=document_id,
                    extracted_fields=extracted_fields,
                    entity_id=entity_id,
                    company_id=company_id,
                    db=db,
                )
            elif classification_type in ("contract", "delivery_note", "order", "offer"):
                # Zukünftige Implementierung
                logger.info(
                    "business_object_type_not_yet_implemented",
                    type=classification_type,
                )
                return BusinessObjectResult(
                    success=False,
                    object_type=classification_type,
                    error=f"Dokumententyp '{classification_type}' noch nicht implementiert",
                )
            else:
                logger.warning(
                    "unknown_classification_type",
                    type=classification_type,
                )
                return BusinessObjectResult(
                    success=False,
                    object_type=classification_type,
                    error=f"Unbekannter Dokumententyp: {classification_type}",
                )

        except Exception as e:
            logger.error(
                "business_object_creation_failed",
                document_id=str(document_id),
                type=classification_type,
                **safe_error_log(e),
                exc_info=True,
            )
            return BusinessObjectResult(
                success=False,
                object_type=classification_type,
                error=safe_error_detail(e, "Business-Object"),
            )

    async def _create_invoice_tracking(
        self,
        document_id: UUID,
        extracted_fields: Dict[str, Dict[str, Any]],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> BusinessObjectResult:
        """
        Erstellt ein InvoiceTracking-Objekt aus Extraktionsdaten.

        Args:
            document_id: ID des Dokuments
            extracted_fields: Extrahierte Felder
            entity_id: Optional Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            BusinessObjectResult mit InvoiceTracking-ID
        """
        from sqlalchemy import and_

        logger.debug(
            "creating_invoice_tracking",
            document_id=str(document_id),
        )

        # SECURITY FIX: Dokument abrufen mit company_id Filter
        doc_result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            return BusinessObjectResult(
                success=False,
                object_type="invoice",
                error="Dokument nicht gefunden",
            )

        # SECURITY FIX: Prüfen ob bereits InvoiceTracking existiert mit company_id Filter
        existing_result = await db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.document_id == document_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            logger.info(
                "invoice_tracking_already_exists",
                document_id=str(document_id),
                invoice_id=str(existing.id),
            )
            return BusinessObjectResult(
                success=True,
                object_type="invoice",
                object_id=existing.id,
            )

        # Felder extrahieren
        invoice_number = self._extract_field_value(extracted_fields, "invoice_number")
        amount = self._extract_field_value(extracted_fields, "amount")
        currency = self._extract_field_value(extracted_fields, "currency") or "EUR"
        due_date = self._extract_field_value(extracted_fields, "due_date")
        invoice_date = self._extract_field_value(extracted_fields, "invoice_date")
        vendor_name = self._extract_field_value(extracted_fields, "vendor_name")

        # Amount konvertieren
        amount_float: float = 0.0
        if amount is not None:
            try:
                if isinstance(amount, (int, float)):
                    amount_float = float(amount)
                elif isinstance(amount, Decimal):
                    amount_float = float(amount)
                elif isinstance(amount, str):
                    # Komma zu Punkt konvertieren (Deutsche Notation)
                    amount_str = amount.replace(",", ".").replace(" ", "")
                    amount_float = float(amount_str)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "amount_conversion_failed",
                    amount=amount,
                    **safe_error_log(e),
                )
                amount_float = 0.0

        # Datumsfelder konvertieren
        invoice_date_dt = self._parse_date(invoice_date)
        due_date_dt = self._parse_date(due_date)

        # InvoiceTracking erstellen
        invoice_tracking = InvoiceTracking(
            document_id=document_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date_dt,
            due_date=due_date_dt,
            amount=amount_float,
            currency=currency,
            status=InvoiceStatus.OPEN.value,
            vendor_name=vendor_name,
        )

        db.add(invoice_tracking)
        await db.flush()  # ID generieren ohne commit

        logger.info(
            "invoice_tracking_created",
            document_id=str(document_id),
            invoice_id=str(invoice_tracking.id),
            invoice_number=invoice_number,
            amount=amount_float,
            currency=currency,
        )

        return BusinessObjectResult(
            success=True,
            object_type="invoice",
            object_id=invoice_tracking.id,
        )

    def _extract_field_value(
        self,
        extracted_fields: Dict[str, Dict[str, Any]],
        field_name: str,
    ) -> Optional[object]:
        """
        Extrahiert einen Feldwert aus den Extraktionsdaten.

        Args:
            extracted_fields: Dictionary mit {field_name: {value, confidence}}
            field_name: Name des zu extrahierenden Felds

        Returns:
            Feldwert oder None
        """
        field_data = extracted_fields.get(field_name)
        if not field_data:
            return None

        if isinstance(field_data, dict):
            return field_data.get("value")
        else:
            # Fallback: Direkter Wert ohne confidence
            return field_data

    def _parse_date(self, date_value: Union[str, datetime, date, None]) -> Optional[datetime]:
        """
        Parst einen Datumswert zu datetime.

        Args:
            date_value: Datumswert (str, datetime, date, etc.)

        Returns:
            datetime-Objekt oder None
        """
        if date_value is None:
            return None

        if isinstance(date_value, datetime):
            # Sicherstellen dass timezone-aware
            if date_value.tzinfo is None:
                return date_value.replace(tzinfo=timezone.utc)
            return date_value

        if isinstance(date_value, str):
            # Verschiedene Datumsformate versuchen
            date_formats = [
                "%Y-%m-%d",           # ISO format
                "%d.%m.%Y",           # Deutsche Notation
                "%d/%m/%Y",           # Alternative
                "%Y-%m-%dT%H:%M:%S",  # ISO mit Zeit
                "%Y-%m-%d %H:%M:%S",  # Alternative mit Zeit
            ]

            for fmt in date_formats:
                try:
                    dt = datetime.strptime(date_value, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue

            logger.warning(
                "date_parsing_failed",
                date_value=date_value,
            )
            return None

        return None
