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
    - invoice -> InvoiceTracking (eigene ORM-Tabelle)
    - delivery_note -> document_metadata["delivery_note_data"] (JSONB)
    - order -> document_metadata["order_data"] (JSONB)
    - contract -> document_metadata["contract_data"] (JSONB)
    - offer -> document_metadata["offer_data"] (JSONB)
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
            elif classification_type == "delivery_note":
                return await self._create_delivery_note_data(
                    document_id=document_id,
                    extracted_fields=extracted_fields,
                    entity_id=entity_id,
                    company_id=company_id,
                    db=db,
                )
            elif classification_type == "order":
                return await self._create_order_data(
                    document_id=document_id,
                    extracted_fields=extracted_fields,
                    entity_id=entity_id,
                    company_id=company_id,
                    db=db,
                )
            elif classification_type == "contract":
                return await self._create_contract_data(
                    document_id=document_id,
                    extracted_fields=extracted_fields,
                    entity_id=entity_id,
                    company_id=company_id,
                    db=db,
                )
            elif classification_type == "offer":
                return await self._create_offer_data(
                    document_id=document_id,
                    extracted_fields=extracted_fields,
                    entity_id=entity_id,
                    company_id=company_id,
                    db=db,
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

        # InvoiceTracking erstellen.
        # Hinweis: InvoiceTracking hat KEINE vendor_name-Spalte - der
        # Geschaeftspartner wird ueber entity_id verknuepft (vendor_name
        # dient nur dem Logging). company_id/entity_id sind Pflicht fuer
        # Multi-Tenant-Isolation.
        invoice_tracking = InvoiceTracking(
            document_id=document_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date_dt,
            due_date=due_date_dt,
            amount=amount_float,
            currency=currency,
            status=InvoiceStatus.OPEN.value,
            company_id=company_id,
            entity_id=entity_id,
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

    async def _create_delivery_note_data(
        self,
        document_id: UUID,
        extracted_fields: Dict[str, Dict[str, Any]],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> BusinessObjectResult:
        """
        Speichert Lieferschein-Daten im Dokument-Metadaten-Feld.

        Extrahiert lieferscheinspezifische Felder und legt sie unter
        ``document_metadata["delivery_note_data"]`` ab.

        Args:
            document_id: ID des Dokuments
            extracted_fields: Extrahierte Felder
            entity_id: Optional Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            BusinessObjectResult mit document_id als object_id
        """
        from sqlalchemy import and_

        logger.debug(
            "creating_delivery_note_data",
            document_id=str(document_id),
        )

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
                object_type="delivery_note",
                error="Dokument nicht gefunden",
            )

        # Idempotenz: bereits verarbeitet?
        metadata: Dict[str, object] = document.document_metadata or {}
        if "delivery_note_data" in metadata:
            logger.info(
                "delivery_note_data_already_exists",
                document_id=str(document_id),
            )
            return BusinessObjectResult(
                success=True,
                object_type="delivery_note",
                object_id=document_id,
            )

        # Felder extrahieren
        delivery_note_number = self._extract_field_value(extracted_fields, "delivery_note_number")
        delivery_date = self._extract_field_value(extracted_fields, "delivery_date")
        order_reference = self._extract_field_value(extracted_fields, "order_reference")
        sender_name = self._extract_field_value(extracted_fields, "sender_name")
        recipient_name = self._extract_field_value(extracted_fields, "recipient_name")
        items_count = self._extract_field_value(extracted_fields, "items_count")

        delivery_date_dt = self._parse_date(delivery_date)

        delivery_note_data: Dict[str, object] = {
            "delivery_note_number": delivery_note_number,
            "delivery_date": delivery_date_dt.isoformat() if delivery_date_dt else None,
            "order_reference": order_reference,
            "sender_name": sender_name,
            "recipient_name": recipient_name,
            "items_count": items_count,
            "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        metadata["delivery_note_data"] = delivery_note_data
        document.document_metadata = metadata

        await db.flush()

        logger.info(
            "delivery_note_data_created",
            document_id=str(document_id),
            has_number=delivery_note_number is not None,
        )

        return BusinessObjectResult(
            success=True,
            object_type="delivery_note",
            object_id=document_id,
        )

    async def _create_order_data(
        self,
        document_id: UUID,
        extracted_fields: Dict[str, Dict[str, Any]],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> BusinessObjectResult:
        """
        Speichert Bestellungs-Daten im Dokument-Metadaten-Feld.

        Extrahiert bestellungsspezifische Felder und legt sie unter
        ``document_metadata["order_data"]`` ab.

        Args:
            document_id: ID des Dokuments
            extracted_fields: Extrahierte Felder
            entity_id: Optional Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            BusinessObjectResult mit document_id als object_id
        """
        from sqlalchemy import and_

        logger.debug(
            "creating_order_data",
            document_id=str(document_id),
        )

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
                object_type="order",
                error="Dokument nicht gefunden",
            )

        metadata = document.document_metadata or {}
        if "order_data" in metadata:
            logger.info(
                "order_data_already_exists",
                document_id=str(document_id),
            )
            return BusinessObjectResult(
                success=True,
                object_type="order",
                object_id=document_id,
            )

        # Felder extrahieren
        order_number = self._extract_field_value(extracted_fields, "order_number")
        order_date = self._extract_field_value(extracted_fields, "order_date")
        vendor_name = self._extract_field_value(extracted_fields, "vendor_name")
        total_amount = self._extract_field_value(extracted_fields, "total_amount")
        currency = self._extract_field_value(extracted_fields, "currency") or "EUR"
        delivery_date_expected = self._extract_field_value(extracted_fields, "delivery_date_expected")
        payment_terms = self._extract_field_value(extracted_fields, "payment_terms")

        order_date_dt = self._parse_date(order_date)
        delivery_expected_dt = self._parse_date(delivery_date_expected)

        order_data: Dict[str, object] = {
            "order_number": order_number,
            "order_date": order_date_dt.isoformat() if order_date_dt else None,
            "vendor_name": vendor_name,
            "total_amount": total_amount,
            "currency": currency,
            "delivery_date_expected": delivery_expected_dt.isoformat() if delivery_expected_dt else None,
            "payment_terms": payment_terms,
            "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        metadata["order_data"] = order_data
        document.document_metadata = metadata

        await db.flush()

        logger.info(
            "order_data_created",
            document_id=str(document_id),
            has_number=order_number is not None,
        )

        return BusinessObjectResult(
            success=True,
            object_type="order",
            object_id=document_id,
        )

    async def _create_contract_data(
        self,
        document_id: UUID,
        extracted_fields: Dict[str, Dict[str, Any]],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> BusinessObjectResult:
        """
        Speichert Vertrags-Daten im Dokument-Metadaten-Feld.

        Extrahiert vertragsspezifische Felder und legt sie unter
        ``document_metadata["contract_data"]`` ab.

        Args:
            document_id: ID des Dokuments
            extracted_fields: Extrahierte Felder
            entity_id: Optional Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            BusinessObjectResult mit document_id als object_id
        """
        from sqlalchemy import and_

        logger.debug(
            "creating_contract_data",
            document_id=str(document_id),
        )

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
                object_type="contract",
                error="Dokument nicht gefunden",
            )

        metadata = document.document_metadata or {}
        if "contract_data" in metadata:
            logger.info(
                "contract_data_already_exists",
                document_id=str(document_id),
            )
            return BusinessObjectResult(
                success=True,
                object_type="contract",
                object_id=document_id,
            )

        # Felder extrahieren
        contract_number = self._extract_field_value(extracted_fields, "contract_number")
        contract_date = self._extract_field_value(extracted_fields, "contract_date")
        contract_type = self._extract_field_value(extracted_fields, "contract_type")
        party_a = self._extract_field_value(extracted_fields, "party_a")
        party_b = self._extract_field_value(extracted_fields, "party_b")
        start_date = self._extract_field_value(extracted_fields, "start_date")
        end_date = self._extract_field_value(extracted_fields, "end_date")
        value = self._extract_field_value(extracted_fields, "value")

        contract_date_dt = self._parse_date(contract_date)
        start_date_dt = self._parse_date(start_date)
        end_date_dt = self._parse_date(end_date)

        contract_data: Dict[str, object] = {
            "contract_number": contract_number,
            "contract_date": contract_date_dt.isoformat() if contract_date_dt else None,
            "contract_type": contract_type,
            "party_a": party_a,
            "party_b": party_b,
            "start_date": start_date_dt.isoformat() if start_date_dt else None,
            "end_date": end_date_dt.isoformat() if end_date_dt else None,
            "value": value,
            "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        metadata["contract_data"] = contract_data
        document.document_metadata = metadata

        await db.flush()

        logger.info(
            "contract_data_created",
            document_id=str(document_id),
            has_number=contract_number is not None,
        )

        return BusinessObjectResult(
            success=True,
            object_type="contract",
            object_id=document_id,
        )

    async def _create_offer_data(
        self,
        document_id: UUID,
        extracted_fields: Dict[str, Dict[str, Any]],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> BusinessObjectResult:
        """
        Speichert Angebots-Daten im Dokument-Metadaten-Feld.

        Extrahiert angebotsspezifische Felder und legt sie unter
        ``document_metadata["offer_data"]`` ab.

        Args:
            document_id: ID des Dokuments
            extracted_fields: Extrahierte Felder
            entity_id: Optional Geschäftspartner-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            BusinessObjectResult mit document_id als object_id
        """
        from sqlalchemy import and_

        logger.debug(
            "creating_offer_data",
            document_id=str(document_id),
        )

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
                object_type="offer",
                error="Dokument nicht gefunden",
            )

        metadata = document.document_metadata or {}
        if "offer_data" in metadata:
            logger.info(
                "offer_data_already_exists",
                document_id=str(document_id),
            )
            return BusinessObjectResult(
                success=True,
                object_type="offer",
                object_id=document_id,
            )

        # Felder extrahieren
        offer_number = self._extract_field_value(extracted_fields, "offer_number")
        offer_date = self._extract_field_value(extracted_fields, "offer_date")
        vendor_name = self._extract_field_value(extracted_fields, "vendor_name")
        total_amount = self._extract_field_value(extracted_fields, "total_amount")
        currency = self._extract_field_value(extracted_fields, "currency") or "EUR"
        valid_until = self._extract_field_value(extracted_fields, "valid_until")

        offer_date_dt = self._parse_date(offer_date)
        valid_until_dt = self._parse_date(valid_until)

        offer_data: Dict[str, object] = {
            "offer_number": offer_number,
            "offer_date": offer_date_dt.isoformat() if offer_date_dt else None,
            "vendor_name": vendor_name,
            "total_amount": total_amount,
            "currency": currency,
            "valid_until": valid_until_dt.isoformat() if valid_until_dt else None,
            "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        metadata["offer_data"] = offer_data
        document.document_metadata = metadata

        await db.flush()

        logger.info(
            "offer_data_created",
            document_id=str(document_id),
            has_number=offer_number is not None,
        )

        return BusinessObjectResult(
            success=True,
            object_type="offer",
            object_id=document_id,
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
