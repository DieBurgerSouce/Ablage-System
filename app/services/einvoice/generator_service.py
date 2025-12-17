# -*- coding: utf-8 -*-
"""
E-Invoice Generator Service.

Generiert E-Rechnungen aus ExtractedInvoiceData:
- ZUGFeRD-PDFs (mit eingebettetem XML)
- XRechnung-XML (standalone)

Unterstuetzt Profile:
- MINIMUM, BASIC, BASIC_WL, EN16931, EXTENDED, XRECHNUNG
"""

import hashlib
import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.einvoice import (
    EInvoiceGenerateResponse,
    EInvoiceValidationResponse,
    XRechnungSyntax,
    ZUGFeRDProfile,
)
from app.api.schemas.extracted_data import ExtractedInvoiceData
from app.db import models

from .mapping.zugferd_mapper import ZUGFeRDMapper

logger = logging.getLogger(__name__)


class EInvoiceGeneratorService:
    """
    Service zur Generierung von E-Rechnungen.

    Verwendung:
        generator = EInvoiceGeneratorService()

        # ZUGFeRD-PDF generieren
        pdf_bytes, einvoice_id = await generator.generate_zugferd_pdf(
            document_id=uuid,
            profile=ZUGFeRDProfile.EN16931,
            db=session
        )

        # XRechnung-XML generieren
        xml_string, einvoice_id = await generator.generate_xrechnung_xml(
            document_id=uuid,
            syntax=XRechnungSyntax.CII,
            db=session
        )
    """

    def __init__(self) -> None:
        """Initialisiere Generator mit Mapper."""
        self.mapper = ZUGFeRDMapper()
        self._facturx_available = self._check_facturx()

    def _check_facturx(self) -> bool:
        """Prueft ob factur-x verfuegbar ist."""
        try:
            import facturx
            return True
        except ImportError:
            logger.warning(
                "factur-x nicht installiert. "
                "PDF-Generierung eingeschraenkt. "
                "Installiere mit: pip install factur-x"
            )
            return False

    async def generate_zugferd_pdf(
        self,
        document_id: UUID,
        db: AsyncSession,
        profile: ZUGFeRDProfile = ZUGFeRDProfile.EN16931,
        user_id: Optional[UUID] = None,
        base_pdf: Optional[bytes] = None,
        validate: bool = True
    ) -> Tuple[bytes, UUID]:
        """
        Generiert ein ZUGFeRD-PDF mit eingebettetem XML.

        Args:
            document_id: Dokument-ID mit extrahierten Daten
            db: Datenbank-Session
            profile: ZUGFeRD-Profil
            user_id: Generierender User
            base_pdf: Optional: Basis-PDF (sonst wird einfaches PDF erstellt)
            validate: Daten vor Generierung validieren

        Returns:
            Tuple aus PDF-Bytes und EInvoice-ID

        Raises:
            ValueError: Bei fehlenden Pflichtdaten
            ImportError: Wenn factur-x nicht verfuegbar
        """
        if not self._facturx_available:
            raise ImportError(
                "factur-x nicht installiert. "
                "Bitte installieren: pip install factur-x"
            )

        from facturx import generate_from_binary

        logger.info(
            "einvoice_generate_zugferd_start",
            extra={"document_id": str(document_id), "profile": profile.value}
        )

        # Dokument laden
        document = await self._get_document(db, document_id)
        if not document:
            raise ValueError(f"Dokument nicht gefunden: {document_id}")

        # ExtractedInvoiceData laden
        invoice_data = self._get_invoice_data(document)
        if not invoice_data:
            raise ValueError(
                f"Keine Rechnungsdaten fuer Dokument: {document_id}"
            )

        # XML generieren
        xml_content = self.mapper.invoice_data_to_xml(invoice_data, profile.value)

        # Basis-PDF erstellen oder verwenden
        if base_pdf is None:
            base_pdf = await self._create_simple_pdf(invoice_data)

        # ZUGFeRD-PDF generieren
        pdf_bytes = generate_from_binary(
            base_pdf,
            xml_content.encode("utf-8"),
            flavor="factur-x",
            level=self._profile_to_level(profile)
        )

        # Hash berechnen
        xml_hash = hashlib.sha256(xml_content.encode("utf-8")).hexdigest()

        # In DB speichern
        einvoice_doc = models.EInvoiceDocument(
            document_id=document_id,
            format="zugferd",
            profile=profile.value,
            version="2.3.3",
            xml_content=xml_content,
            xml_hash=xml_hash,
            was_generated=True,
            was_extracted=False,
            generation_timestamp=datetime.now(timezone.utc),
            generated_by_id=user_id,
            leitweg_id=invoice_data.buyer_reference,
        )

        db.add(einvoice_doc)
        await db.flush()

        logger.info(
            "einvoice_generate_zugferd_success",
            extra={
                "document_id": str(document_id),
                "einvoice_id": str(einvoice_doc.id),
                "profile": profile.value,
                "pdf_size_bytes": len(pdf_bytes),
            }
        )

        return pdf_bytes, einvoice_doc.id

    async def generate_xrechnung_xml(
        self,
        document_id: UUID,
        db: AsyncSession,
        syntax: XRechnungSyntax = XRechnungSyntax.CII,
        user_id: Optional[UUID] = None,
        validate: bool = True
    ) -> Tuple[str, UUID]:
        """
        Generiert ein XRechnung-XML.

        Args:
            document_id: Dokument-ID mit extrahierten Daten
            db: Datenbank-Session
            syntax: CII oder UBL
            user_id: Generierender User
            validate: Daten vor Generierung validieren

        Returns:
            Tuple aus XML-String und EInvoice-ID

        Raises:
            ValueError: Bei fehlenden Pflichtdaten (z.B. Leitweg-ID)
        """
        logger.info(
            "einvoice_generate_xrechnung_start",
            extra={"document_id": str(document_id), "syntax": syntax.value}
        )

        # Dokument laden
        document = await self._get_document(db, document_id)
        if not document:
            raise ValueError(f"Dokument nicht gefunden: {document_id}")

        # ExtractedInvoiceData laden
        invoice_data = self._get_invoice_data(document)
        if not invoice_data:
            raise ValueError(
                f"Keine Rechnungsdaten fuer Dokument: {document_id}"
            )

        # XRechnung erfordert Leitweg-ID
        if not invoice_data.buyer_reference:
            raise ValueError(
                "Leitweg-ID (buyer_reference) fehlt - "
                "Pflicht fuer XRechnung B2G-Rechnungen"
            )

        # XML generieren (CII-Syntax ueber Mapper, UBL wuerde Mustang erfordern)
        if syntax == XRechnungSyntax.UBL:
            # UBL erfordert zusaetzlichen Konverter oder Mustang
            raise NotImplementedError(
                "UBL-Syntax erfordert Mustang Microservice. "
                "Bitte CII-Syntax verwenden oder Mustang aktivieren."
            )

        xml_content = self.mapper.invoice_data_to_xml(invoice_data, "XRECHNUNG")

        # Hash berechnen
        xml_hash = hashlib.sha256(xml_content.encode("utf-8")).hexdigest()

        # In DB speichern
        einvoice_doc = models.EInvoiceDocument(
            document_id=document_id,
            format="xrechnung_cii",
            profile="XRECHNUNG",
            version="3.0.2",
            xml_content=xml_content,
            xml_hash=xml_hash,
            was_generated=True,
            was_extracted=False,
            generation_timestamp=datetime.now(timezone.utc),
            generated_by_id=user_id,
            leitweg_id=invoice_data.buyer_reference,
        )

        db.add(einvoice_doc)
        await db.flush()

        logger.info(
            "einvoice_generate_xrechnung_success",
            extra={
                "document_id": str(document_id),
                "einvoice_id": str(einvoice_doc.id),
                "syntax": syntax.value,
            }
        )

        return xml_content, einvoice_doc.id

    async def generate_xml_only(
        self,
        invoice_data: ExtractedInvoiceData,
        profile: str = "EN16931"
    ) -> str:
        """
        Generiert XML ohne DB-Speicherung.

        Nuetzlich fuer Vorschau oder Tests.

        Args:
            invoice_data: Rechnungsdaten
            profile: ZUGFeRD-Profil

        Returns:
            XML als String
        """
        return self.mapper.invoice_data_to_xml(invoice_data, profile)

    async def _get_document(
        self,
        db: AsyncSession,
        document_id: UUID
    ) -> Optional[models.Document]:
        """Laedt Dokument aus DB."""
        result = await db.execute(
            select(models.Document).where(models.Document.id == document_id)
        )
        return result.scalar_one_or_none()

    def _get_invoice_data(
        self,
        document: models.Document
    ) -> Optional[ExtractedInvoiceData]:
        """Extrahiert InvoiceData aus Dokument."""
        if not document.extracted_data:
            return None

        extracted = document.extracted_data
        if isinstance(extracted, dict) and "invoice" in extracted:
            invoice_dict = extracted["invoice"]
            if invoice_dict:
                try:
                    return ExtractedInvoiceData.model_validate(invoice_dict)
                except Exception as e:
                    logger.warning(
                        "invoice_data_parse_error",
                        extra={"document_id": str(document.id), "error": str(e)}
                    )

        return None

    async def _create_simple_pdf(
        self,
        invoice_data: ExtractedInvoiceData
    ) -> bytes:
        """
        Erstellt ein einfaches PDF fuer ZUGFeRD-Embedding.

        Wird verwendet wenn kein Basis-PDF vorhanden ist.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table

            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            # Titel
            story.append(Paragraph(
                f"<b>Rechnung {invoice_data.invoice_number or ''}</b>",
                styles['Title']
            ))
            story.append(Spacer(1, 0.5 * cm))

            # Absender
            if invoice_data.sender:
                story.append(Paragraph("<b>Von:</b>", styles['Normal']))
                story.append(Paragraph(
                    invoice_data.sender.to_single_line(),
                    styles['Normal']
                ))
                story.append(Spacer(1, 0.3 * cm))

            # Empfaenger
            if invoice_data.recipient:
                story.append(Paragraph("<b>An:</b>", styles['Normal']))
                story.append(Paragraph(
                    invoice_data.recipient.to_single_line(),
                    styles['Normal']
                ))
                story.append(Spacer(1, 0.5 * cm))

            # Rechnungsdaten
            story.append(Paragraph(
                f"<b>Rechnungsdatum:</b> {invoice_data.invoice_date or '-'}",
                styles['Normal']
            ))
            if invoice_data.due_date:
                story.append(Paragraph(
                    f"<b>Faellig am:</b> {invoice_data.due_date}",
                    styles['Normal']
                ))
            story.append(Spacer(1, 0.5 * cm))

            # Betraege
            story.append(Paragraph("<b>Betraege:</b>", styles['Normal']))
            if invoice_data.net_amount is not None:
                story.append(Paragraph(
                    f"Netto: {invoice_data.net_amount:.2f} {invoice_data.currency.value}",
                    styles['Normal']
                ))
            if invoice_data.vat_amount is not None:
                story.append(Paragraph(
                    f"MwSt ({invoice_data.vat_rate or 0}%): "
                    f"{invoice_data.vat_amount:.2f} {invoice_data.currency.value}",
                    styles['Normal']
                ))
            if invoice_data.gross_amount is not None:
                story.append(Paragraph(
                    f"<b>Brutto: {invoice_data.gross_amount:.2f} "
                    f"{invoice_data.currency.value}</b>",
                    styles['Normal']
                ))

            story.append(Spacer(1, 1 * cm))

            # Hinweis
            story.append(Paragraph(
                "<i>Dies ist eine maschinell generierte E-Rechnung im "
                "ZUGFeRD-Format mit eingebettetem XML.</i>",
                styles['Normal']
            ))

            doc.build(story)
            return buffer.getvalue()

        except ImportError:
            # Fallback: Minimales PDF
            logger.warning("reportlab nicht verfuegbar, verwende Minimal-PDF")
            return self._create_minimal_pdf()

    def _create_minimal_pdf(self) -> bytes:
        """Erstellt ein minimales PDF."""
        # Minimales PDF (1 Seite, leer)
        pdf_content = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >>
startxref
196
%%EOF"""
        return pdf_content

    def _profile_to_level(self, profile: ZUGFeRDProfile) -> str:
        """Konvertiert ZUGFeRD-Profil zu factur-x Level."""
        mapping = {
            ZUGFeRDProfile.MINIMUM: "minimum",
            ZUGFeRDProfile.BASIC: "basic",
            ZUGFeRDProfile.BASIC_WL: "basicwl",
            ZUGFeRDProfile.EN16931: "en16931",
            ZUGFeRDProfile.EXTENDED: "extended",
            ZUGFeRDProfile.XRECHNUNG: "en16931",  # XRechnung basiert auf EN16931
        }
        return mapping.get(profile, "en16931")


# Singleton Instance
_generator_service: Optional[EInvoiceGeneratorService] = None


def get_generator_service() -> EInvoiceGeneratorService:
    """Gibt Singleton Generator Service zurueck."""
    global _generator_service
    if _generator_service is None:
        _generator_service = EInvoiceGeneratorService()
    return _generator_service
