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

from app.core.safe_errors import safe_error_log
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

        # Pruefen ob bereits eine E-Invoice existiert
        stmt = select(models.EInvoiceDocument).where(
            models.EInvoiceDocument.document_id == document_id
        )
        result = await db.execute(stmt)
        existing_einvoice = result.scalar_one_or_none()

        if existing_einvoice:
            # Existierenden Record aktualisieren
            existing_einvoice.format = "zugferd"
            existing_einvoice.profile = profile.value
            existing_einvoice.version = "2.3.3"
            existing_einvoice.xml_content = xml_content
            existing_einvoice.xml_hash = xml_hash
            existing_einvoice.was_generated = True
            existing_einvoice.generation_timestamp = datetime.now(timezone.utc)
            existing_einvoice.generated_by_id = user_id
            existing_einvoice.leitweg_id = invoice_data.buyer_reference
            # Validierung zuruecksetzen bei Regenerierung
            existing_einvoice.is_valid = None
            existing_einvoice.validation_timestamp = None
            einvoice_doc = existing_einvoice
            logger.info(
                "einvoice_update_existing",
                extra={"document_id": str(document_id), "einvoice_id": str(einvoice_doc.id)}
            )
        else:
            # Neuen Record erstellen
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

        # XML generieren
        if syntax == XRechnungSyntax.UBL:
            # UBL-Syntax ueber XRechnungUBLMapper
            from .mapping.xrechnung_ubl_mapper import get_ubl_mapper
            ubl_mapper = get_ubl_mapper()
            xml_content = ubl_mapper.invoice_data_to_ubl(
                invoice=invoice_data,
                leitweg_id=invoice_data.buyer_reference,
            )
        else:
            # CII-Syntax (Default) ueber ZUGFeRD Mapper
            xml_content = self.mapper.invoice_data_to_xml(invoice_data, "XRECHNUNG")

        # Hash berechnen
        xml_hash = hashlib.sha256(xml_content.encode("utf-8")).hexdigest()

        # Format basierend auf Syntax
        format_name = "xrechnung_ubl" if syntax == XRechnungSyntax.UBL else "xrechnung_cii"

        # In DB speichern
        einvoice_doc = models.EInvoiceDocument(
            document_id=document_id,
            format=format_name,
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
                        extra={"document_id": str(document.id), **safe_error_log(e)}
                    )

        return None

    def _ensure_fonts(self) -> bool:
        """Registriert DejaVu Fonts für korrekte Umlaut-Darstellung."""
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            # Prüfen ob bereits registriert
            if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames():
                return True

            # DejaVu Sans registrieren
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            ]
            for path in font_paths:
                if Path(path).exists():
                    font_name = Path(path).stem
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    logger.debug(f"Font registriert: {font_name}")

            return 'DejaVuSans' in pdfmetrics.getRegisteredFontNames()

        except Exception as e:
            logger.warning(f"Font-Registrierung fehlgeschlagen: {e}")
            return False

    async def _create_simple_pdf(
        self,
        invoice_data: ExtractedInvoiceData
    ) -> bytes:
        """
        Erstellt ein professionelles PDF für ZUGFeRD-Embedding.

        Features:
        - Unicode-Fonts (DejaVu Sans) für korrekte Umlaute
        - Mehrzeilige Adressen
        - Line Items Tabelle
        - USt-ID, IBAN, Zahlungsbedingungen
        - Verbesserte MwSt-Logik
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            )

            # Font registrieren
            use_dejavu = self._ensure_fonts()

            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                leftMargin=2*cm,
                rightMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            styles = getSampleStyleSheet()

            # Styles mit DejaVu Font wenn verfügbar
            if use_dejavu:
                styles['Normal'].fontName = 'DejaVuSans'
                styles['Title'].fontName = 'DejaVuSans-Bold'
                styles['Heading1'].fontName = 'DejaVuSans-Bold'

            # Custom Styles
            small_style = ParagraphStyle(
                'Small',
                parent=styles['Normal'],
                fontSize=8,
                fontName='DejaVuSans' if use_dejavu else 'Helvetica'
            )
            meta_style = ParagraphStyle(
                'Meta',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#666666'),
                fontName='DejaVuSans' if use_dejavu else 'Helvetica'
            )
            label_style = ParagraphStyle(
                'Label',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=2,
                fontName='DejaVuSans-Bold' if use_dejavu else 'Helvetica-Bold'
            )

            # Waehrung und Formatierungs-Helper (global fuer gesamte PDF)
            currency = invoice_data.currency.value if invoice_data.currency else "EUR"

            def format_amount(val: float, with_currency: bool = True) -> str:
                """Formatiert Betrag: 15000.00 -> 15.000,00 EUR"""
                formatted = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                return f"{formatted} {currency}" if with_currency else formatted

            story = []

            # ===== TITEL =====
            story.append(Paragraph(
                f"<b>Rechnung {invoice_data.invoice_number or ''}</b>",
                styles['Title']
            ))
            story.append(Spacer(1, 0.5 * cm))

            # ===== ABSENDER-BLOCK (komplett gruppiert) =====
            if invoice_data.sender:
                story.append(Paragraph("Absender", label_style))
                for line in invoice_data.sender.to_multiline():
                    story.append(Paragraph(line, styles['Normal']))

                # USt-ID direkt nach Absender-Adresse
                if invoice_data.sender_vat_id:
                    story.append(Paragraph(
                        f"USt-IdNr.: {invoice_data.sender_vat_id}",
                        meta_style
                    ))
                if invoice_data.sender_tax_number:
                    story.append(Paragraph(
                        f"Steuernr.: {invoice_data.sender_tax_number}",
                        meta_style
                    ))

                # IBAN direkt nach USt-ID
                if invoice_data.sender_bank and invoice_data.sender_bank.iban:
                    bank_parts = [f"IBAN: {invoice_data.sender_bank.iban}"]
                    if invoice_data.sender_bank.bic:
                        bank_parts.append(f"BIC: {invoice_data.sender_bank.bic}")
                    story.append(Paragraph(" | ".join(bank_parts), meta_style))

                story.append(Spacer(1, 0.3 * cm))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc')))
                story.append(Spacer(1, 0.3 * cm))

            # ===== EMPFÄNGER-BLOCK =====
            if invoice_data.recipient:
                story.append(Paragraph("Empfänger", label_style))
                for line in invoice_data.recipient.to_multiline():
                    story.append(Paragraph(line, styles['Normal']))
                story.append(Spacer(1, 0.3 * cm))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc')))
                story.append(Spacer(1, 0.3 * cm))

            # ===== RECHNUNGSDATEN =====
            # Deutsches Datumsformat: DD.MM.YYYY
            def format_date_de(d) -> str:
                if d is None:
                    return "-"
                if hasattr(d, 'strftime'):
                    return d.strftime("%d.%m.%Y")
                # Falls String im ISO-Format
                if isinstance(d, str) and len(d) == 10 and d[4] == '-':
                    parts = d.split('-')
                    return f"{parts[2]}.{parts[1]}.{parts[0]}"
                return str(d)

            story.append(Paragraph(
                f"<b>Rechnungsdatum:</b> {format_date_de(invoice_data.invoice_date)}",
                styles['Normal']
            ))
            if invoice_data.due_date:
                story.append(Paragraph(
                    f"<b>Fällig am:</b> {format_date_de(invoice_data.due_date)}",
                    styles['Normal']
                ))

            # ===== ZAHLUNGSBEDINGUNGEN =====
            if invoice_data.payment_terms:
                story.append(Paragraph(
                    f"<b>Zahlungsbedingungen:</b> {invoice_data.payment_terms}",
                    styles['Normal']
                ))
            story.append(Spacer(1, 0.5 * cm))

            # ===== LINE ITEMS TABELLE =====
            if invoice_data.line_items:
                story.append(Paragraph("Positionen", label_style))
                story.append(Spacer(1, 0.2 * cm))

                # Tabellen-Style fuer Beschreibungs-Zellen
                desc_style = ParagraphStyle(
                    'TableDesc',
                    parent=styles['Normal'],
                    fontSize=8,
                    fontName='DejaVuSans' if use_dejavu else 'Helvetica'
                )

                table_data = [["Pos", "Beschreibung", "Menge", "Einzelpreis", "Gesamt"]]
                for item in invoice_data.line_items:
                    # Volle Beschreibung mit Paragraph (automatischer Umbruch)
                    desc_para = Paragraph(item.description or "-", desc_style)
                    # Menge mit Einheit
                    unit = item.unit or "Stk"
                    qty = f"{int(item.quantity)} {unit}" if item.quantity else "-"
                    table_data.append([
                        str(item.position),
                        desc_para,
                        qty,
                        format_amount(float(item.unit_price)) if item.unit_price else "-",
                        format_amount(float(item.total_price)) if item.total_price else "-"
                    ])

                table = Table(
                    table_data,
                    colWidths=[1*cm, 8*cm, 2*cm, 2.5*cm, 2.5*cm]  # Menge 1.5->2cm
                )
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a4a4a')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold' if use_dejavu else 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans' if use_dejavu else 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ]))
                story.append(table)
                story.append(Spacer(1, 0.5 * cm))

            # ===== BETRÄGE =====
            story.append(Paragraph("Beträge", label_style))
            if invoice_data.net_amount is not None:
                story.append(Paragraph(
                    f"Netto: {format_amount(float(invoice_data.net_amount))}",
                    styles['Normal']
                ))

            # MwSt-Logik verbessert
            if invoice_data.vat_amount is not None and invoice_data.vat_amount > 0:
                vat_rate = invoice_data.vat_rate if invoice_data.vat_rate else 19
                story.append(Paragraph(
                    f"MwSt ({vat_rate}%): {format_amount(float(invoice_data.vat_amount))}",
                    styles['Normal']
                ))
            elif invoice_data.is_reverse_charge:
                story.append(Paragraph(
                    "<i>Reverse Charge - Steuerschuldnerschaft des Leistungsempfängers</i>",
                    small_style
                ))
            elif (invoice_data.net_amount is not None and
                  invoice_data.gross_amount is not None and
                  invoice_data.net_amount == invoice_data.gross_amount):
                story.append(Paragraph(
                    "<i>Steuerfreie Rechnung</i>",
                    small_style
                ))

            if invoice_data.gross_amount is not None:
                story.append(Paragraph(
                    f"<b>Brutto: {format_amount(float(invoice_data.gross_amount))}</b>",
                    styles['Normal']
                ))

            story.append(Spacer(1, 1 * cm))

            # ===== HINWEIS =====
            story.append(Paragraph(
                "<i>Dies ist eine maschinell generierte E-Rechnung im "
                "ZUGFeRD-Format mit eingebettetem XML.</i>",
                small_style
            ))

            doc.build(story)
            return buffer.getvalue()

        except ImportError as e:
            logger.warning(f"reportlab nicht verfügbar: {e}, verwende Minimal-PDF")
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
