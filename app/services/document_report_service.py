# -*- coding: utf-8 -*-
"""
Document Report Service für Ablage-System OCR.

Generiert detaillierte PDF-Berichte für einzelne Dokumente:
- OCR-Ergebnisse und Konfidenz
- Erkannte Entitäten (Daten, Beträge, IBAN, USt-ID)
- Deutsche Validierung
- Verarbeitungshistorie

Feinpoliert und durchdacht - Enterprise-grade Dokumentation.
"""

import io
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, ListFlowable, ListItem
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import Document, AuditLog

logger = structlog.get_logger(__name__)


class DocumentReportService:
    """Service für Dokumentenberichte."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Definiert benutzerdefinierte Styles."""
        self.title_style = ParagraphStyle(
            'ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=20,
            spaceAfter=20,
            textColor=colors.HexColor('#1a365d'),
            alignment=TA_CENTER
        )

        self.subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=30,
            textColor=colors.HexColor('#4a5568'),
            alignment=TA_CENTER
        )

        self.heading_style = ParagraphStyle(
            'SectionHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2d3748'),
            borderPadding=5
        )

        self.body_style = ParagraphStyle(
            'BodyText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceBefore=5,
            spaceAfter=5,
            alignment=TA_JUSTIFY,
            leading=14
        )

        self.label_style = ParagraphStyle(
            'Label',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#718096')
        )

        self.value_style = ParagraphStyle(
            'Value',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1a202c')
        )

        self.text_style = ParagraphStyle(
            'ExtractedText',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=12,
            fontName='Courier',
            backColor=colors.HexColor('#f7fafc'),
            borderPadding=10
        )

    async def generate_document_report(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID,
        include_text: bool = True,
        include_history: bool = True,
        include_entities: bool = True
    ) -> bytes:
        """
        Generiert einen detaillierten PDF-Bericht für ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID (für Berechtigungsprüfung)
            include_text: Extrahierten Text einschließen
            include_history: Verarbeitungshistorie einschließen
            include_entities: Erkannte Entitäten einschließen

        Returns:
            PDF-Bytes
        """
        # Dokument laden
        result = await db.execute(
            select(Document)
            .options(selectinload(Document.tags))
            .where(
                Document.id == document_id,
                Document.owner_id == user_id
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden oder keine Berechtigung")

        # Historie laden wenn gewünscht
        history = []
        if include_history:
            history_result = await db.execute(
                select(AuditLog)
                .where(AuditLog.resource_id == str(document_id))
                .order_by(AuditLog.created_at.desc())
                .limit(20)
            )
            history = list(history_result.scalars().all())

        # PDF generieren
        pdf_bytes = self._generate_pdf(
            document=document,
            history=history,
            include_text=include_text,
            include_history=include_history,
            include_entities=include_entities
        )

        logger.info(
            "document_report_generated",
            document_id=str(document_id)[:8],
            size_bytes=len(pdf_bytes)
        )

        return pdf_bytes

    def _generate_pdf(
        self,
        document: Document,
        history: List[AuditLog],
        include_text: bool,
        include_history: bool,
        include_entities: bool
    ) -> bytes:
        """Generiert das PDF-Dokument."""
        output = io.BytesIO()

        doc = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2.5*cm,
            bottomMargin=2*cm
        )

        story = []

        # Titel
        story.append(Paragraph("Dokumentenbericht", self.title_style))
        story.append(Paragraph(
            f"Erstellt am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}",
            self.subtitle_style
        ))

        # Dokumentinformationen
        story.append(Paragraph("Dokumentinformationen", self.heading_style))
        story.append(self._create_info_table(document))
        story.append(Spacer(1, 0.5*cm))

        # OCR-Ergebnisse
        story.append(Paragraph("OCR-Verarbeitungsergebnisse", self.heading_style))
        story.append(self._create_ocr_table(document))
        story.append(Spacer(1, 0.5*cm))

        # Tags
        if document.tags:
            story.append(Paragraph("Tags", self.heading_style))
            tags_text = ", ".join([tag.name for tag in document.tags])
            story.append(Paragraph(tags_text, self.body_style))
            story.append(Spacer(1, 0.5*cm))

        # Erkannte Entitäten
        if include_entities and document.document_metadata:
            entities = self._extract_entities(document)
            if entities:
                story.append(Paragraph("Erkannte Entitäten", self.heading_style))
                story.append(self._create_entities_table(entities))
                story.append(Spacer(1, 0.5*cm))

        # Deutsche Validierung
        if document.has_umlauts is not None or document.detected_language:
            story.append(Paragraph("Deutsche Textvalidierung", self.heading_style))
            story.append(self._create_german_validation_table(document))
            story.append(Spacer(1, 0.5*cm))

        # Extrahierter Text
        if include_text and document.extracted_text:
            story.append(PageBreak())
            story.append(Paragraph("Extrahierter Text", self.heading_style))

            # Text in Absätze aufteilen für bessere Darstellung
            text = document.extracted_text
            # Maximal 5000 Zeichen im Bericht
            if len(text) > 5000:
                text = text[:5000] + "\n\n[... Text gekürzt, vollständiger Text im Originaldokument ...]"

            # Escape HTML-Zeichen
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace("\n", "<br/>")

            story.append(Paragraph(text, self.text_style))

        # Verarbeitungshistorie
        if include_history and history:
            story.append(PageBreak())
            story.append(Paragraph("Verarbeitungshistorie", self.heading_style))
            story.append(self._create_history_table(history))

        # Footer-Hinweis
        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor('#e2e8f0')
        ))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(
            "Dieser Bericht wurde automatisch vom Ablage-System OCR generiert. "
            "Die extrahierten Daten wurden mittels OCR erfasst und können von den "
            "Originaldaten abweichen. Bitte prüfen Sie kritische Informationen.",
            ParagraphStyle(
                'Footer',
                parent=self.styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#a0aec0'),
                alignment=TA_CENTER
            )
        ))

        # PDF bauen
        doc.build(story)
        return output.getvalue()

    def _create_info_table(self, document: Document) -> Table:
        """Erstellt Tabelle mit Dokumentinformationen."""
        data = [
            ["Dateiname:", document.filename or "Unbekannt"],
            ["Original-Dateiname:", document.original_filename or "-"],
            ["Dokument-ID:", str(document.id)[:8] + "..."],
            ["Typ:", document.document_type or "Nicht klassifiziert"],
            ["Status:", self._translate_status(document.status)],
            ["Größe:", self._format_size(document.file_size)],
            ["Seitenzahl:", str(document.page_count or "-")],
            ["Erstellt am:", document.created_at.strftime("%d.%m.%Y %H:%M") if document.created_at else "-"],
            ["Verarbeitet am:", document.processed_date.strftime("%d.%m.%Y %H:%M") if document.processed_date else "-"],
        ]

        table = Table(data, colWidths=[5*cm, 10*cm])
        table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#718096')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1a202c')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _create_ocr_table(self, document: Document) -> Table:
        """Erstellt Tabelle mit OCR-Ergebnissen."""
        confidence = document.ocr_confidence or 0
        confidence_color = self._get_confidence_color(confidence)

        data = [
            ["OCR-Backend:", document.ocr_backend_used or "Unbekannt"],
            ["Konfidenz:", f"{confidence * 100:.1f}%"],
            ["Wortanzahl:", str(len((document.extracted_text or "").split()))],
            ["Zeichenanzahl:", str(len(document.extracted_text or ""))],
        ]

        table = Table(data, colWidths=[5*cm, 10*cm])
        table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#718096')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1a202c')),
            ('TEXTCOLOR', (1, 1), (1, 1), confidence_color),
            ('FONTNAME', (1, 1), (1, 1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _create_german_validation_table(self, document: Document) -> Table:
        """Erstellt Tabelle mit deutscher Validierung."""
        data = [
            ["Erkannte Sprache:", document.detected_language or "Nicht erkannt"],
            ["Umlaute vorhanden:", "Ja" if document.has_umlauts else "Nein"],
        ]

        table = Table(data, colWidths=[5*cm, 10*cm])
        table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#718096')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1a202c')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _create_entities_table(self, entities: Dict[str, List[str]]) -> Table:
        """Erstellt Tabelle mit erkannten Entitäten."""
        data = [["Typ", "Erkannte Werte"]]

        entity_labels = {
            "dates": "Datumsangaben",
            "amounts": "Geldbeträge",
            "ibans": "IBAN-Nummern",
            "vat_ids": "USt-IdNr.",
            "emails": "E-Mail-Adressen",
            "phones": "Telefonnummern",
        }

        for key, values in entities.items():
            if values:
                label = entity_labels.get(key, key)
                # Maximal 5 Werte anzeigen
                display_values = values[:5]
                if len(values) > 5:
                    display_values.append(f"... (+{len(values) - 5} weitere)")
                data.append([label, ", ".join(display_values)])

        if len(data) == 1:
            return Paragraph("Keine Entitäten erkannt", self.body_style)

        table = Table(data, colWidths=[4*cm, 11*cm])
        table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf2f7')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        return table

    def _create_history_table(self, history: List[AuditLog]) -> Table:
        """Erstellt Tabelle mit Verarbeitungshistorie."""
        data = [["Zeitpunkt", "Aktion", "Details"]]

        for entry in history[:10]:  # Maximal 10 Einträge
            timestamp = entry.created_at.strftime("%d.%m.%Y %H:%M") if entry.created_at else "-"
            action = self._translate_action(entry.action)
            details = entry.details.get("message", "") if entry.details else ""
            if len(details) > 50:
                details = details[:50] + "..."
            data.append([timestamp, action, details])

        table = Table(data, colWidths=[4*cm, 4*cm, 7*cm])
        table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf2f7')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        return table

    def _extract_entities(self, document: Document) -> Dict[str, List[str]]:
        """Extrahiert Entitäten aus Dokumentmetadaten."""
        entities = {}
        metadata = document.document_metadata or {}

        # Aus Metadaten extrahieren
        if "dates" in metadata:
            entities["dates"] = metadata["dates"]
        if "amounts" in metadata:
            entities["amounts"] = metadata["amounts"]
        if "ibans" in metadata:
            entities["ibans"] = metadata["ibans"]
        if "vat_ids" in metadata:
            entities["vat_ids"] = metadata["vat_ids"]
        if "emails" in metadata:
            entities["emails"] = metadata["emails"]
        if "phones" in metadata:
            entities["phones"] = metadata["phones"]

        return entities

    def _translate_status(self, status: str) -> str:
        """Übersetzt Status in Deutsch."""
        translations = {
            "pending": "Ausstehend",
            "processing": "In Verarbeitung",
            "completed": "Abgeschlossen",
            "failed": "Fehlgeschlagen",
            "deleted": "Gelöscht",
        }
        return translations.get(status, status)

    def _translate_action(self, action: str) -> str:
        """Übersetzt Aktion in Deutsch."""
        translations = {
            "document_created": "Erstellt",
            "document_updated": "Aktualisiert",
            "document_deleted": "Gelöscht",
            "ocr_started": "OCR gestartet",
            "ocr_completed": "OCR abgeschlossen",
            "ocr_failed": "OCR fehlgeschlagen",
        }
        return translations.get(action, action)

    def _format_size(self, size_bytes: Optional[int]) -> str:
        """Formatiert Dateigröße."""
        if not size_bytes:
            return "-"

        if size_bytes < 1024:
            return f"{size_bytes} Bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _get_confidence_color(self, confidence: float) -> colors.Color:
        """Gibt Farbe basierend auf Konfidenz zurück."""
        if confidence >= 0.9:
            return colors.HexColor('#38a169')  # Grün
        elif confidence >= 0.7:
            return colors.HexColor('#d69e2e')  # Orange
        else:
            return colors.HexColor('#e53e3e')  # Rot


# Singleton
_report_service: Optional[DocumentReportService] = None


def get_document_report_service() -> DocumentReportService:
    """Gibt DocumentReportService-Singleton zurück."""
    global _report_service
    if _report_service is None:
        _report_service = DocumentReportService()
    return _report_service
