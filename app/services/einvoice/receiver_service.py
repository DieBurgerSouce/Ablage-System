# -*- coding: utf-8 -*-
"""
E-Invoice Receiver Service - Empfang und Verarbeitung eingehender E-Rechnungen.

Implementiert:
- Parsing von XRechnung/ZUGFeRD aus verschiedenen Quellen
- Automatische Validierung (BR-DE Rules)
- Entity-Matching (Absender erkennen)
- Alert-Generierung bei Fehlern
- Integration ins Dokumentensystem

Unterstützte Eingangskanaele:
- Peppol AS4 Webhook
- Email-Import (via EmailImportService)
- Manueller Upload (API)
- Portal-Download

SECURITY: Eingehende XMLs werden gegen XXE-Angriffe geschuetzt.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

import structlog
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Sicherer XML Parser (XXE Prevention)
SECURE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    remove_blank_text=True
)


# =============================================================================
# DATA CLASSES
# =============================================================================

class IncomingInvoiceStatus(str, Enum):
    """Status einer eingehenden E-Rechnung."""
    RECEIVED = "received"  # Empfangen, noch nicht verarbeitet
    VALIDATING = "validating"  # Wird validiert
    VALIDATED = "validated"  # Validierung erfolgreich
    VALIDATION_FAILED = "validation_failed"  # Validierung fehlgeschlagen
    LINKING = "linking"  # Entity-Linking laeuft
    LINKED = "linked"  # Mit Entity verknüpft
    PROCESSED = "processed"  # Vollständig verarbeitet
    REJECTED = "rejected"  # Abgelehnt
    ERROR = "error"  # Fehler bei Verarbeitung


@dataclass
class ExtractedInvoiceInfo:
    """Aus E-Invoice extrahierte Basisdaten."""
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    seller_name: Optional[str] = None
    seller_vat_id: Optional[str] = None
    seller_address: Optional[str] = None
    buyer_reference: Optional[str] = None  # Leitweg-ID
    buyer_name: Optional[str] = None
    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    currency: str = "EUR"
    payment_reference: Optional[str] = None
    iban: Optional[str] = None
    format: Optional[str] = None  # xrechnung_cii, xrechnung_ubl, zugferd
    profile: Optional[str] = None


@dataclass
class ValidationError:
    """Einzelner Validierungsfehler."""
    code: str
    message: str
    location: Optional[str] = None
    rule_id: Optional[str] = None
    severity: str = "error"  # error, warning, info


@dataclass
class ProcessingResult:
    """Ergebnis der E-Invoice Verarbeitung."""
    success: bool
    incoming_invoice_id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    invoice_info: Optional[ExtractedInvoiceInfo] = None
    validation_passed: bool = True
    validation_errors: List[ValidationError] = field(default_factory=list)
    validation_warnings: List[ValidationError] = field(default_factory=list)
    alerts_created: List[UUID] = field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# E-INVOICE RECEIVER SERVICE
# =============================================================================

class EInvoiceReceiverService:
    """
    Service für Empfang und Verarbeitung eingehender E-Rechnungen.

    Usage:
        receiver = EInvoiceReceiverService()

        # E-Rechnung verarbeiten
        result = await receiver.process_incoming_invoice(
            xml_content=xml_string,
            source="peppol",
            company_id=uuid,
            db=session
        )

        # Peppol Webhook verarbeiten
        result = await receiver.handle_peppol_webhook(request_data, db)
    """

    def __init__(self) -> None:
        """Initialisiere Receiver Service."""
        self._validator = None  # Lazy load

    async def _get_validator(self):
        """Lazy load des Validator Service."""
        if self._validator is None:
            from app.services.einvoice.validator_service import get_validator_service
            self._validator = get_validator_service()
        return self._validator

    async def process_incoming_invoice(
        self,
        xml_content: str,
        source: str,
        company_id: UUID,
        db: AsyncSession,
        source_metadata: Optional[Dict[str, Any]] = None,
        pdf_content: Optional[bytes] = None,
        original_filename: Optional[str] = None,
        auto_link_entity: bool = True,
        create_document: bool = True,
    ) -> ProcessingResult:
        """
        Verarbeitet eine eingehende E-Rechnung.

        Args:
            xml_content: E-Invoice XML Content
            source: Herkunft (peppol, email, portal, upload)
            company_id: Empfänger-Company
            db: Database Session
            source_metadata: Zusätzliche Metadaten (Message-ID, Sender, etc.)
            pdf_content: Optional PDF (bei ZUGFeRD)
            original_filename: Originaler Dateiname
            auto_link_entity: Automatisch Absender-Entity verknüpfen
            create_document: Dokument in DB erstellen

        Returns:
            ProcessingResult mit Verarbeitungsstatus
        """
        from app.db.models_einvoice import IncomingEInvoice
        from app.db.models import Document
        from app.services.storage_service import get_storage_service

        result = ProcessingResult(success=False)
        source_metadata = source_metadata or {}

        try:
            # 1. XML Validierung (Syntax)
            try:
                root = etree.fromstring(xml_content.encode("utf-8"), parser=SECURE_XML_PARSER)
            except etree.XMLSyntaxError as e:
                result.error = f"Ungültiges XML: {safe_error_detail(e, 'XML-Parsing')}"
                result.validation_errors.append(ValidationError(
                    code="XML_SYNTAX_ERROR",
                    message="XML-Syntax ungültig",
                    severity="error"
                ))
                return result

            # 2. Format erkennen
            format_info = self._detect_format(root)
            result.invoice_info = ExtractedInvoiceInfo(
                format=format_info["format"],
                profile=format_info.get("profile")
            )

            # 3. Basisdaten extrahieren
            invoice_info = self._extract_invoice_info(root, format_info["format"])
            result.invoice_info = invoice_info

            # 4. XML Hash berechnen
            xml_hash = hashlib.sha256(xml_content.encode("utf-8")).hexdigest()

            # 5. Validierung durchführen
            validator = await self._get_validator()
            validation_result = await validator.validate_xml(
                xml_content,
                format_hint=format_info["format"]
            )

            result.validation_passed = validation_result.valid
            for msg in validation_result.messages:
                error = ValidationError(
                    code=msg.code,
                    message=msg.message,
                    location=msg.location,
                    rule_id=msg.rule_id,
                    severity=msg.severity.value
                )
                if msg.severity.value in ("fatal", "error"):
                    result.validation_errors.append(error)
                else:
                    result.validation_warnings.append(error)

            # 6. IncomingEInvoice Record erstellen
            incoming_id = uuid4()
            incoming = IncomingEInvoice(
                id=incoming_id,
                channel=source,
                received_at=datetime.now(timezone.utc),
                format=format_info["format"],
                xml_content=xml_content,
                xml_hash=xml_hash,
                original_filename=original_filename,
                has_pdf_attachment=pdf_content is not None,
                invoice_number=invoice_info.invoice_number,
                invoice_date=invoice_info.invoice_date,
                seller_name=invoice_info.seller_name,
                buyer_reference=invoice_info.buyer_reference,
                total_amount=invoice_info.gross_amount,
                currency=invoice_info.currency,
                is_valid=validation_result.valid,
                validation_errors=[e.__dict__ for e in result.validation_errors],
                validation_warnings=[w.__dict__ for w in result.validation_warnings],
                status=IncomingInvoiceStatus.VALIDATED.value if validation_result.valid else IncomingInvoiceStatus.VALIDATION_FAILED.value,
                company_id=company_id,
            )

            # Peppol-Metadaten
            if source == "peppol":
                incoming.peppol_message_id = source_metadata.get("message_id")
                incoming.peppol_sender_id = source_metadata.get("sender_id")
                incoming.peppol_document_type = source_metadata.get("document_type")

            # Email-Metadaten
            if source == "email":
                incoming.email_sender = source_metadata.get("sender")
                incoming.email_subject = source_metadata.get("subject")
                incoming.email_message_id = source_metadata.get("message_id")

            db.add(incoming)
            result.incoming_invoice_id = incoming_id

            # 7. PDF speichern (falls vorhanden)
            if pdf_content:
                storage = get_storage_service()
                pdf_path = f"incoming_einvoice/{company_id}/{incoming_id}.pdf"
                await storage.upload_document(
                    file_data=pdf_content,
                    filename=f"{incoming_id}.pdf",
                    content_type="application/pdf",
                    user_id=str(company_id),
                    metadata={"type": "incoming_einvoice"}
                )
                incoming.pdf_storage_path = pdf_path

            # 8. Entity-Linking (Absender erkennen)
            if auto_link_entity and invoice_info.seller_vat_id:
                entity_id = await self._find_entity_by_vat_id(
                    db, company_id, invoice_info.seller_vat_id
                )
                if entity_id:
                    incoming.entity_id = entity_id
                    incoming.status = IncomingInvoiceStatus.LINKED.value
                    result.entity_id = entity_id
                    logger.info(
                        "einvoice_entity_linked",
                        incoming_id=str(incoming_id),
                        entity_id=str(entity_id),
                    )

            # 9. Dokument erstellen (optional)
            if create_document and (pdf_content or xml_content):
                document = await self._create_document(
                    db=db,
                    incoming=incoming,
                    xml_content=xml_content,
                    pdf_content=pdf_content,
                    company_id=company_id,
                    invoice_info=invoice_info,
                )
                if document:
                    incoming.document_id = document.id
                    result.document_id = document.id

            # 10. Alerts erstellen bei Validierungsfehlern
            if not validation_result.valid:
                alert_ids = await self._create_validation_alerts(
                    db=db,
                    incoming=incoming,
                    errors=result.validation_errors,
                    company_id=company_id,
                )
                result.alerts_created = alert_ids

            # 11. Status finalisieren
            if validation_result.valid:
                incoming.status = IncomingInvoiceStatus.PROCESSED.value
                incoming.processed_at = datetime.now(timezone.utc)

            await db.commit()

            result.success = True
            logger.info(
                "einvoice_processed",
                incoming_id=str(incoming_id),
                format=format_info["format"],
                valid=validation_result.valid,
                invoice_number=invoice_info.invoice_number,
            )

            return result

        except Exception as e:
            logger.error("einvoice_processing_failed", **safe_error_log(e))
            result.error = safe_error_detail(e, "E-Invoice Verarbeitung")
            return result

    async def handle_peppol_webhook(
        self,
        request_data: Dict[str, Any],
        db: AsyncSession,
    ) -> ProcessingResult:
        """
        Verarbeitet eingehenden Peppol Webhook (AS4 Receipt).

        Args:
            request_data: Webhook Request Payload
            db: Database Session

        Returns:
            ProcessingResult
        """
        # Extrahiere Daten aus Webhook
        xml_content = request_data.get("payload")
        message_id = request_data.get("message_id")
        sender_id = request_data.get("sender_id")
        receiver_id = request_data.get("receiver_id")
        document_type = request_data.get("document_type")

        if not xml_content:
            return ProcessingResult(
                success=False,
                error="Kein XML-Payload im Webhook"
            )

        # Company ID aus Receiver ermitteln (Leitweg-ID -> Company Mapping)
        company_id = await self._resolve_company_from_leitweg(db, receiver_id)
        if not company_id:
            return ProcessingResult(
                success=False,
                error=f"Unbekannter Empfänger: {receiver_id}"
            )

        return await self.process_incoming_invoice(
            xml_content=xml_content,
            source="peppol",
            company_id=company_id,
            db=db,
            source_metadata={
                "message_id": message_id,
                "sender_id": sender_id,
                "document_type": document_type,
            }
        )

    def _detect_format(self, root: etree._Element) -> Dict[str, Any]:
        """Erkennt E-Invoice Format aus XML Root."""
        tag = root.tag.lower() if root.tag else ""
        result = {"format": "unknown", "profile": None}

        # UBL Invoice
        if "invoice" in tag and "oasis" in tag:
            result["format"] = "xrechnung_ubl"
            # Profil aus CustomizationID
            customization = root.find(".//{*}CustomizationID")
            if customization is not None and customization.text:
                if "xrechnung" in customization.text.lower():
                    result["profile"] = "XRECHNUNG"
                elif "en16931" in customization.text.lower():
                    result["profile"] = "EN16931"

        # CII (CrossIndustryInvoice)
        elif "crossindustryinvoice" in tag:
            # XRechnung oder ZUGFeRD?
            guideline = root.find(".//{*}GuidelineSpecifiedDocumentContextParameter/{*}ID")
            if guideline is not None and guideline.text:
                text_lower = guideline.text.lower()
                if "xrechnung" in text_lower or "xeinkauf" in text_lower:
                    result["format"] = "xrechnung_cii"
                    result["profile"] = "XRECHNUNG"
                elif "extended" in text_lower:
                    result["format"] = "zugferd"
                    result["profile"] = "EXTENDED"
                elif "en16931" in text_lower:
                    result["format"] = "zugferd"
                    result["profile"] = "EN16931"
                elif "basic" in text_lower:
                    result["format"] = "zugferd"
                    result["profile"] = "BASIC"
                elif "minimum" in text_lower:
                    result["format"] = "zugferd"
                    result["profile"] = "MINIMUM"
                else:
                    result["format"] = "zugferd"
            else:
                result["format"] = "zugferd"

        return result

    def _extract_invoice_info(
        self,
        root: etree._Element,
        format_type: str
    ) -> ExtractedInvoiceInfo:
        """Extrahiert Rechnungsinformationen aus XML."""
        info = ExtractedInvoiceInfo(format=format_type)

        if format_type in ("xrechnung_cii", "zugferd"):
            info = self._extract_cii_info(root, info)
        elif format_type == "xrechnung_ubl":
            info = self._extract_ubl_info(root, info)

        return info

    def _extract_cii_info(
        self,
        root: etree._Element,
        info: ExtractedInvoiceInfo
    ) -> ExtractedInvoiceInfo:
        """Extrahiert Daten aus CII Format."""
        # Rechnungsnummer
        id_elem = root.find(".//{*}ExchangedDocument/{*}ID")
        if id_elem is not None:
            info.invoice_number = id_elem.text

        # Rechnungsdatum
        date_elem = root.find(".//{*}ExchangedDocument/{*}IssueDateTime/{*}DateTimeString")
        if date_elem is not None and date_elem.text:
            info.invoice_date = self._parse_date(date_elem.text)

        # Leitweg-ID (BT-10)
        buyer_ref = root.find(".//{*}ApplicableHeaderTradeAgreement/{*}BuyerReference")
        if buyer_ref is not None:
            info.buyer_reference = buyer_ref.text

        # Seller
        seller_name = root.find(".//{*}SellerTradeParty/{*}Name")
        if seller_name is not None:
            info.seller_name = seller_name.text

        seller_vat = root.find(".//{*}SellerTradeParty/{*}SpecifiedTaxRegistration/{*}ID[@schemeID='VA']")
        if seller_vat is not None:
            info.seller_vat_id = seller_vat.text

        # Buyer
        buyer_name = root.find(".//{*}BuyerTradeParty/{*}Name")
        if buyer_name is not None:
            info.buyer_name = buyer_name.text

        # Betraege
        summary = root.find(".//{*}SpecifiedTradeSettlementHeaderMonetarySummation")
        if summary is not None:
            net = summary.find(".//{*}LineTotalAmount")
            if net is not None and net.text:
                info.net_amount = Decimal(net.text)

            tax = summary.find(".//{*}TaxTotalAmount")
            if tax is not None and tax.text:
                info.vat_amount = Decimal(tax.text)

            gross = summary.find(".//{*}GrandTotalAmount")
            if gross is not None and gross.text:
                info.gross_amount = Decimal(gross.text)

        # Währung
        currency = root.find(".//{*}InvoiceCurrencyCode")
        if currency is not None and currency.text:
            info.currency = currency.text

        # IBAN
        iban = root.find(".//{*}PayeePartyCreditorFinancialAccount/{*}IBANID")
        if iban is not None:
            info.iban = iban.text

        # Zahlungsreferenz
        payment_ref = root.find(".//{*}ApplicableHeaderTradeSettlement/{*}PaymentReference")
        if payment_ref is not None:
            info.payment_reference = payment_ref.text

        # Fälligkeitsdatum
        due_date = root.find(".//{*}SpecifiedTradePaymentTerms/{*}DueDateDateTime/{*}DateTimeString")
        if due_date is not None and due_date.text:
            info.due_date = self._parse_date(due_date.text)

        return info

    def _extract_ubl_info(
        self,
        root: etree._Element,
        info: ExtractedInvoiceInfo
    ) -> ExtractedInvoiceInfo:
        """Extrahiert Daten aus UBL Format."""
        # Namespace handling
        ns = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
              "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"}

        # Rechnungsnummer
        id_elem = root.find(".//{*}ID")
        if id_elem is not None:
            info.invoice_number = id_elem.text

        # Rechnungsdatum
        date_elem = root.find(".//{*}IssueDate")
        if date_elem is not None and date_elem.text:
            info.invoice_date = self._parse_date(date_elem.text)

        # Fälligkeitsdatum
        due_date = root.find(".//{*}DueDate")
        if due_date is not None and due_date.text:
            info.due_date = self._parse_date(due_date.text)

        # Leitweg-ID (BT-10)
        buyer_ref = root.find(".//{*}BuyerReference")
        if buyer_ref is not None:
            info.buyer_reference = buyer_ref.text

        # Seller (AccountingSupplierParty)
        seller_name = root.find(".//{*}AccountingSupplierParty/{*}Party/{*}PartyName/{*}Name")
        if seller_name is not None:
            info.seller_name = seller_name.text

        seller_vat = root.find(".//{*}AccountingSupplierParty/{*}Party/{*}PartyTaxScheme/{*}CompanyID")
        if seller_vat is not None:
            info.seller_vat_id = seller_vat.text

        # Buyer
        buyer_name = root.find(".//{*}AccountingCustomerParty/{*}Party/{*}PartyName/{*}Name")
        if buyer_name is not None:
            info.buyer_name = buyer_name.text

        # Betraege (LegalMonetaryTotal)
        total = root.find(".//{*}LegalMonetaryTotal")
        if total is not None:
            net = total.find(".//{*}TaxExclusiveAmount")
            if net is not None and net.text:
                info.net_amount = Decimal(net.text)

            gross = total.find(".//{*}TaxInclusiveAmount")
            if gross is not None and gross.text:
                info.gross_amount = Decimal(gross.text)

        # Tax Total
        tax = root.find(".//{*}TaxTotal/{*}TaxAmount")
        if tax is not None and tax.text:
            info.vat_amount = Decimal(tax.text)

        # Währung
        currency = root.find(".//{*}DocumentCurrencyCode")
        if currency is not None and currency.text:
            info.currency = currency.text

        # IBAN
        iban = root.find(".//{*}PaymentMeans/{*}PayeeFinancialAccount/{*}ID")
        if iban is not None:
            info.iban = iban.text

        return info

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parst Datum aus verschiedenen Formaten."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Format 102: YYYYMMDD
        if len(date_str) == 8 and date_str.isdigit():
            try:
                return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                pass

        # ISO Format: YYYY-MM-DD
        if len(date_str) >= 10 and date_str[4] == "-":
            try:
                return date.fromisoformat(date_str[:10])
            except ValueError:
                pass

        return None

    async def _find_entity_by_vat_id(
        self,
        db: AsyncSession,
        company_id: UUID,
        vat_id: str
    ) -> Optional[UUID]:
        """Sucht Entity anhand USt-IdNr."""
        from app.db.models import Entity

        # USt-ID normalisieren (Leerzeichen/Bindestriche entfernen)
        vat_id_normalized = re.sub(r"[\s\-]", "", vat_id.upper())

        query = select(Entity.id).where(
            Entity.company_id == company_id,
            Entity.vat_id.ilike(f"%{vat_id_normalized}%"),
            Entity.deleted_at.is_(None)
        ).limit(1)

        result = await db.execute(query)
        entity_id = result.scalar_one_or_none()

        return entity_id

    async def _create_document(
        self,
        db: AsyncSession,
        incoming,
        xml_content: str,
        pdf_content: Optional[bytes],
        company_id: UUID,
        invoice_info: ExtractedInvoiceInfo,
    ):
        """Erstellt Dokument aus eingehender E-Rechnung."""
        from app.db.models import Document
        from app.services.storage_service import get_storage_service

        storage = get_storage_service()

        # Bestimme primären Content (PDF bevorzugt, sonst XML)
        if pdf_content:
            content = pdf_content
            mime_type = "application/pdf"
            filename = f"einvoice_{invoice_info.invoice_number or incoming.id}.pdf"
        else:
            content = xml_content.encode("utf-8")
            mime_type = "application/xml"
            filename = f"einvoice_{invoice_info.invoice_number or incoming.id}.xml"

        # In Storage hochladen
        file_hash = hashlib.sha256(content).hexdigest()
        storage_path = f"documents/{company_id}/{filename}"

        await storage.upload_document(
            file_data=content,
            filename=filename,
            content_type=mime_type,
            user_id=str(company_id),
            metadata={"source": "einvoice_receiver"}
        )

        # Document erstellen
        document = Document(
            id=uuid4(),
            filename=filename,
            original_filename=incoming.original_filename or filename,
            file_path=storage_path,
            file_size=len(content),
            mime_type=mime_type,
            checksum=file_hash,
            document_type="invoice",
            status="processed",
            owner_id=None,  # System-owned für eingehende
            company_id=company_id,
            extracted_data={
                "invoice": {
                    "invoice_number": invoice_info.invoice_number,
                    "invoice_date": invoice_info.invoice_date.isoformat() if invoice_info.invoice_date else None,
                    "due_date": invoice_info.due_date.isoformat() if invoice_info.due_date else None,
                    "seller_name": invoice_info.seller_name,
                    "seller_vat_id": invoice_info.seller_vat_id,
                    "buyer_reference": invoice_info.buyer_reference,
                    "net_amount": str(invoice_info.net_amount) if invoice_info.net_amount else None,
                    "vat_amount": str(invoice_info.vat_amount) if invoice_info.vat_amount else None,
                    "gross_amount": str(invoice_info.gross_amount) if invoice_info.gross_amount else None,
                    "currency": invoice_info.currency,
                    "iban": invoice_info.iban,
                    "payment_reference": invoice_info.payment_reference,
                }
            },
            document_metadata={
                "einvoice_format": invoice_info.format,
                "einvoice_profile": invoice_info.profile,
                "source": "einvoice_receiver",
                "incoming_einvoice_id": str(incoming.id),
            }
        )

        db.add(document)
        await db.flush()

        logger.info(
            "einvoice_document_created",
            document_id=str(document.id),
            invoice_number=invoice_info.invoice_number,
        )

        return document

    async def _create_validation_alerts(
        self,
        db: AsyncSession,
        incoming,
        errors: List[ValidationError],
        company_id: UUID,
    ) -> List[UUID]:
        """Erstellt Alerts für Validierungsfehler."""
        from app.services.alert_center_service import get_alert_center_service

        alert_ids = []

        try:
            alert_service = get_alert_center_service()

            # Haupt-Alert für ungültige E-Rechnung
            error_summary = "; ".join([e.message for e in errors[:3]])
            if len(errors) > 3:
                error_summary += f" (+{len(errors) - 3} weitere)"

            alert = await alert_service.create_alert(
                db=db,
                alert_code="COMP_004",  # E-Invoice Validation Failed
                title=f"E-Rechnung ungültig: {incoming.invoice_number or 'Unbekannt'}",
                message=f"Eingehende E-Rechnung hat {len(errors)} Validierungsfehler: {error_summary}",
                category="compliance",
                severity="high" if len(errors) > 5 else "medium",
                company_id=company_id,
                metadata={
                    "incoming_einvoice_id": str(incoming.id),
                    "invoice_number": incoming.invoice_number,
                    "seller_name": incoming.seller_name,
                    "error_count": len(errors),
                    "errors": [e.__dict__ for e in errors],
                },
                context={
                    "entity_type": "incoming_einvoice",
                    "entity_id": str(incoming.id),
                }
            )

            if alert:
                alert_ids.append(alert.id)

        except Exception as e:
            logger.warning("einvoice_alert_creation_failed", **safe_error_log(e))

        return alert_ids

    async def _resolve_company_from_leitweg(
        self,
        db: AsyncSession,
        leitweg_id: str
    ) -> Optional[UUID]:
        """Loest Leitweg-ID zu Company-ID auf."""
        from app.db.models import Company

        if not leitweg_id:
            return None

        # Leitweg-ID Format: XXXX-XXXX-XX (vereinfacht)
        # Suche nach Company mit dieser Leitweg-ID in den Settings
        query = select(Company.id).where(
            Company.settings["leitweg_id"].astext == leitweg_id,
            Company.deleted_at.is_(None)
        ).limit(1)

        result = await db.execute(query)
        return result.scalar_one_or_none()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_receiver_service_instance: Optional[EInvoiceReceiverService] = None


def get_receiver_service() -> EInvoiceReceiverService:
    """
    Factory-Funktion für EInvoiceReceiverService (Singleton).

    Returns:
        EInvoiceReceiverService: Globale Instanz
    """
    global _receiver_service_instance
    if _receiver_service_instance is None:
        _receiver_service_instance = EInvoiceReceiverService()
    return _receiver_service_instance
