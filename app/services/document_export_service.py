"""Export-Service fuer Dokumentenexport in verschiedenen Formaten.

Unterstuetzt JSON, CSV, ZIP und PDF Export mit optionalen Inhalten.
"""

from typing import List, Tuple, Optional
from datetime import datetime, timezone
from uuid import UUID
import json
import csv
import io
import zipfile

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document
from app.db.schemas import (
    BatchOperationError,
    BatchExportResult,
    ExportFormat,
)

logger = structlog.get_logger(__name__)


class DocumentExportService:
    """Service fuer Dokumentenexport.

    Unterstuetzt mehrere Formate:
    - JSON: Strukturierte Daten
    - CSV: Tabellenformat
    - ZIP: Archiv mit einzelnen JSON-Dateien
    - PDF: Formatierter Report mit reportlab
    """

    async def batch_export(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        user_id: UUID,
        format: ExportFormat = ExportFormat.JSON,
        include_text: bool = True,
        include_metadata: bool = True
    ) -> Tuple[bytes, str, BatchExportResult]:
        """Mehrere Dokumente exportieren.

        Args:
            db: Datenbank-Session
            document_ids: Liste der zu exportierenden Dokument-IDs
            user_id: Benutzer-ID
            format: Export-Format (JSON, CSV, ZIP, PDF)
            include_text: Extrahierten Text einbeziehen
            include_metadata: Metadaten einbeziehen

        Returns:
            Tuple von (export_bytes, content_type, result)
        """
        # Dokumente laden
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(
                Document.id.in_(document_ids),
                Document.owner_id == user_id
            ))
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        found_ids = {doc.id for doc in documents}
        not_found = [doc_id for doc_id in document_ids if doc_id not in found_ids]

        errors = [
            BatchOperationError(
                document_id=doc_id,
                error="Dokument nicht gefunden oder keine Berechtigung",
                error_code="NOT_FOUND"
            )
            for doc_id in not_found
        ]

        # Export durchfuehren
        if format == ExportFormat.JSON:
            export_data, content_type = self._export_json(
                documents, include_text, include_metadata
            )
        elif format == ExportFormat.CSV:
            export_data, content_type = self._export_csv(
                documents, include_text, include_metadata
            )
        elif format == ExportFormat.PDF:
            export_data, content_type = self._export_pdf(
                documents, include_text, include_metadata
            )
        else:
            # ZIP mit einzelnen Dateien
            export_data, content_type = self._export_zip(
                documents, include_text, include_metadata
            )

        export_result = BatchExportResult(
            success=len(errors) == 0,
            operation="export",
            total_requested=len(document_ids),
            processed=len(documents),
            failed=len(errors),
            errors=errors,
            message=f"{len(documents)} Dokument(e) exportiert",
            download_url=None,  # Wird vom Router gesetzt
            expires_at=None,
            file_size_bytes=len(export_data),
            format=format
        )

        logger.info(
            "batch_export_completed",
            format=format.value,
            total=len(document_ids),
            exported=len(documents)
        )

        return export_data, content_type, export_result

    def _export_json(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als JSON."""
        export_data = []
        for doc in documents:
            item = {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "file_size": doc.file_size,
                "page_count": doc.page_count,
                "ocr_confidence": doc.ocr_confidence,
                "tags": [t.name for t in doc.tags] if doc.tags else []
            }

            if include_text:
                item["extracted_text"] = doc.extracted_text

            if include_metadata:
                item["metadata"] = doc.document_metadata
                item["detected_language"] = doc.detected_language
                item["has_umlauts"] = doc.has_umlauts

            export_data.append(item)

        return json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"

    def _export_csv(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als CSV."""
        output = io.StringIO()
        fieldnames = [
            "id", "filename", "document_type", "status",
            "created_at", "file_size", "page_count", "ocr_confidence", "tags"
        ]

        if include_text:
            fieldnames.append("extracted_text")
        if include_metadata:
            fieldnames.extend(["detected_language", "has_umlauts"])

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for doc in documents:
            row = {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else "",
                "file_size": doc.file_size or 0,
                "page_count": doc.page_count or 0,
                "ocr_confidence": doc.ocr_confidence or 0,
                "tags": ",".join(t.name for t in doc.tags) if doc.tags else ""
            }

            if include_text:
                # Text kuerzen fuer CSV
                text = doc.extracted_text or ""
                row["extracted_text"] = text[:1000] + "..." if len(text) > 1000 else text

            if include_metadata:
                row["detected_language"] = doc.detected_language or ""
                row["has_umlauts"] = str(doc.has_umlauts or False)

            writer.writerow(row)

        return output.getvalue().encode("utf-8"), "text/csv"

    def _export_zip(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als ZIP mit einzelnen JSON-Dateien."""
        output = io.BytesIO()

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                item = {
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "file_size": doc.file_size,
                    "page_count": doc.page_count,
                    "ocr_confidence": doc.ocr_confidence,
                    "tags": [t.name for t in doc.tags] if doc.tags else []
                }

                if include_text:
                    item["extracted_text"] = doc.extracted_text

                if include_metadata:
                    item["metadata"] = doc.document_metadata
                    item["detected_language"] = doc.detected_language
                    item["has_umlauts"] = doc.has_umlauts

                json_content = json.dumps(item, ensure_ascii=False, indent=2)
                filename = f"{doc.filename.rsplit('.', 1)[0]}_{doc.id}.json"
                zf.writestr(filename, json_content.encode("utf-8"))

        return output.getvalue(), "application/zip"

    def _export_pdf(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als PDF mit reportlab."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        )

        output = io.BytesIO()
        pdf_doc = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # Styles definieren
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            textColor=colors.darkblue
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15,
            textColor=colors.darkblue
        )
        text_style = ParagraphStyle(
            'CustomText',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            spaceAfter=6
        )

        elements = []

        # Titelseite
        elements.append(Paragraph("Ablage-System - Dokumentenexport", title_style))
        elements.append(Paragraph(
            f"Exportiert am: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC",
            text_style
        ))
        elements.append(Paragraph(f"Anzahl Dokumente: {len(documents)}", text_style))
        elements.append(Spacer(1, 30))

        # Jedes Dokument
        for idx, document in enumerate(documents):
            if idx > 0:
                elements.append(PageBreak())

            # Dokumenttitel
            safe_filename = document.filename.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            elements.append(Paragraph(f"Dokument: {safe_filename}", heading_style))

            # Metadaten-Tabelle
            metadata_rows = [
                ["Feld", "Wert"],
                ["ID", str(document.id)],
                ["Dateiname", document.filename or "Unbekannt"],
                ["Typ", document.document_type or "Sonstiges"],
                ["Status", document.status or "Unbekannt"],
                ["Erstellt", document.created_at.strftime("%d.%m.%Y %H:%M") if document.created_at else "-"],
                ["Groesse", f"{(document.file_size or 0) / 1024:.1f} KB"],
                ["Seiten", str(document.page_count or "-")],
                ["OCR-Konfidenz", f"{(document.ocr_confidence or 0) * 100:.1f}%"],
            ]

            # Optionale Metadaten
            if include_metadata:
                if document.detected_language:
                    metadata_rows.append(["Sprache", document.detected_language])
                if document.has_umlauts is not None:
                    metadata_rows.append(["Hat Umlaute", "Ja" if document.has_umlauts else "Nein"])
                if document.ocr_backend_used:
                    metadata_rows.append(["OCR-Backend", document.ocr_backend_used])

            # Tags
            if document.tags:
                tag_names = ", ".join(t.name for t in document.tags)
                metadata_rows.append(["Tags", tag_names])

            # Tabelle erstellen
            table = Table(metadata_rows, colWidths=[4*cm, 12*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 15))

            # Extrahierter Text
            if include_text and document.extracted_text:
                elements.append(Paragraph("Extrahierter Text:", heading_style))

                # Text aufbereiten (HTML-Entities und Zeilenumbrueche)
                text = document.extracted_text[:10000]  # Limit fuer sehr lange Texte
                if len(document.extracted_text) > 10000:
                    text += "... [Text gekuerzt]"

                # Sonderzeichen escapen
                text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                text = text.replace('\n', '<br/>')

                elements.append(Paragraph(text, text_style))

        # PDF generieren
        pdf_doc.build(elements)
        return output.getvalue(), "application/pdf"


# Singleton Instance
_export_service: Optional[DocumentExportService] = None


def get_document_export_service() -> DocumentExportService:
    """Document-Export-Service-Instanz abrufen (singleton)."""
    global _export_service
    if _export_service is None:
        _export_service = DocumentExportService()
    return _export_service
