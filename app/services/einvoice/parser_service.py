# -*- coding: utf-8 -*-
"""
E-Invoice Parser Service.

Parst eingehende E-Rechnungen:
- ZUGFeRD-PDFs (Factur-X) via factur-x library
- XRechnung-XML (standalone)

Unterstuetzt:
- ZUGFeRD 1.0, 2.0, 2.1, 2.2, 2.3
- Factur-X 1.0
- XRechnung 2.x, 3.x (CII und UBL)
"""

import hashlib
import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.einvoice import (
    EInvoiceFormatDetected,
    EInvoiceParseResponse,
    ZUGFeRDProfile,
)
from app.api.schemas.extracted_data import ExtractedInvoiceData
from app.db import models

from .mapping.zugferd_mapper import ZUGFeRDMapper

logger = logging.getLogger(__name__)


class EInvoiceParserService:
    """
    Service zum Parsen von E-Rechnungen.

    Verwendung:
        parser = EInvoiceParserService()

        # PDF parsen
        result = await parser.parse_pdf(pdf_bytes, filename="rechnung.pdf")

        # XML parsen
        result = await parser.parse_xml(xml_string)

        # Mit DB-Speicherung
        result = await parser.parse_and_store(
            pdf_bytes,
            filename="rechnung.pdf",
            document_id=uuid,
            db=session
        )
    """

    def __init__(self) -> None:
        """Initialisiere Parser mit Mapper."""
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
                "PDF-Parsing eingeschraenkt. "
                "Installiere mit: pip install factur-x"
            )
            return False

    async def parse_pdf(
        self,
        pdf_content: bytes,
        filename: Optional[str] = None
    ) -> EInvoiceParseResponse:
        """
        Parst ein ZUGFeRD/Factur-X PDF.

        Args:
            pdf_content: PDF als Bytes
            filename: Optionaler Dateiname fuer Logging

        Returns:
            EInvoiceParseResponse mit extrahierten Daten

        Raises:
            ValueError: Wenn kein XML im PDF gefunden
            ImportError: Wenn factur-x nicht verfuegbar
        """
        if not self._facturx_available:
            raise ImportError(
                "factur-x nicht installiert. "
                "Bitte installieren: pip install factur-x"
            )

        from facturx import get_xml_from_pdf

        logger.info(
            "einvoice_parse_pdf_start",
            extra={"filename": filename, "size_bytes": len(pdf_content)}
        )

        try:
            # XML aus PDF extrahieren
            xml_content, xml_filename = get_xml_from_pdf(BytesIO(pdf_content))

            if not xml_content:
                raise ValueError(
                    f"Kein ZUGFeRD/Factur-X XML im PDF gefunden: {filename}"
                )

            # XML parsen
            invoice_data, metadata = self.mapper.xml_to_invoice_data(xml_content)

            # Format erkennen
            format_detected = self._detect_format(metadata)
            profile = self._map_profile(metadata.get("profile"))

            logger.info(
                "einvoice_parse_pdf_success",
                extra={
                    "filename": filename,
                    "format": format_detected.value,
                    "profile": profile.value if profile else None,
                    "invoice_number": invoice_data.invoice_number,
                }
            )

            return EInvoiceParseResponse(
                success=True,
                format_detected=format_detected,
                profile=profile,
                version=metadata.get("version"),
                invoice_data=invoice_data,
                xml_content=xml_content.decode("utf-8") if isinstance(xml_content, bytes) else xml_content,
                warnings=[],
            )

        except Exception as e:
            logger.error(
                "einvoice_parse_pdf_error",
                extra={"filename": filename, "error": str(e)},
                exc_info=True
            )
            raise

    async def parse_xml(
        self,
        xml_content: Union[str, bytes],
        filename: Optional[str] = None
    ) -> EInvoiceParseResponse:
        """
        Parst ein standalone XRechnung/ZUGFeRD XML.

        Args:
            xml_content: XML als String oder Bytes
            filename: Optionaler Dateiname fuer Logging

        Returns:
            EInvoiceParseResponse mit extrahierten Daten
        """
        logger.info(
            "einvoice_parse_xml_start",
            extra={"filename": filename}
        )

        try:
            invoice_data, metadata = self.mapper.xml_to_invoice_data(xml_content)

            format_detected = self._detect_format(metadata)
            profile = self._map_profile(metadata.get("profile"))

            logger.info(
                "einvoice_parse_xml_success",
                extra={
                    "filename": filename,
                    "format": format_detected.value,
                    "invoice_number": invoice_data.invoice_number,
                }
            )

            return EInvoiceParseResponse(
                success=True,
                format_detected=format_detected,
                profile=profile,
                version=metadata.get("version"),
                invoice_data=invoice_data,
                xml_content=xml_content if isinstance(xml_content, str) else xml_content.decode("utf-8"),
                warnings=[],
            )

        except Exception as e:
            logger.error(
                "einvoice_parse_xml_error",
                extra={"filename": filename, "error": str(e)},
                exc_info=True
            )
            raise

    async def parse_file(
        self,
        file_content: bytes,
        filename: str
    ) -> EInvoiceParseResponse:
        """
        Parst eine Datei basierend auf Dateiendung.

        Args:
            file_content: Dateiinhalt als Bytes
            filename: Dateiname mit Endung

        Returns:
            EInvoiceParseResponse
        """
        suffix = Path(filename).suffix.lower()

        if suffix == ".pdf":
            return await self.parse_pdf(file_content, filename)
        elif suffix == ".xml":
            return await self.parse_xml(file_content, filename)
        else:
            # Versuche als PDF
            if file_content[:4] == b"%PDF":
                return await self.parse_pdf(file_content, filename)
            # Versuche als XML
            if file_content.strip().startswith(b"<?xml") or file_content.strip().startswith(b"<"):
                return await self.parse_xml(file_content, filename)

            raise ValueError(
                f"Unbekanntes Dateiformat: {filename}. "
                "Unterstuetzt: PDF, XML"
            )

    async def parse_and_store(
        self,
        file_content: bytes,
        filename: str,
        document_id: UUID,
        db: AsyncSession,
        user_id: Optional[UUID] = None
    ) -> EInvoiceParseResponse:
        """
        Parst E-Rechnung und speichert in Datenbank.

        Args:
            file_content: Dateiinhalt
            filename: Dateiname
            document_id: Zugehoeriges Dokument
            db: Datenbank-Session
            user_id: Optional User ID

        Returns:
            EInvoiceParseResponse mit einvoice_id
        """
        # Parsen
        result = await self.parse_file(file_content, filename)

        if not result.success:
            return result

        # In DB speichern
        xml_hash = hashlib.sha256(
            result.xml_content.encode("utf-8") if result.xml_content else b""
        ).hexdigest()

        einvoice_doc = models.EInvoiceDocument(
            document_id=document_id,
            format=result.format_detected.value.split("_")[0],  # zugferd, xrechnung
            profile=result.profile.value if result.profile else None,
            version=result.version,
            xml_content=result.xml_content,
            xml_hash=xml_hash,
            was_extracted=True,
            was_generated=False,
            source_filename=filename,
            extraction_method="facturx",
            leitweg_id=result.invoice_data.buyer_reference,
        )

        db.add(einvoice_doc)
        await db.flush()

        result.einvoice_id = einvoice_doc.id
        result.document_id = document_id

        logger.info(
            "einvoice_stored",
            extra={
                "einvoice_id": str(einvoice_doc.id),
                "document_id": str(document_id),
                "format": result.format_detected.value,
            }
        )

        return result

    def _detect_format(
        self,
        metadata: Dict[str, Any]
    ) -> EInvoiceFormatDetected:
        """Erkennt das genaue Format aus Metadaten."""
        format_str = metadata.get("format", "unknown")
        version = metadata.get("version", "")

        if format_str == "xrechnung_cii":
            if version.startswith("3."):
                return EInvoiceFormatDetected.XRECHNUNG_3_0
            elif version.startswith("2.3"):
                return EInvoiceFormatDetected.XRECHNUNG_2_3
            elif version.startswith("2.2"):
                return EInvoiceFormatDetected.XRECHNUNG_2_2
            elif version.startswith("2.1"):
                return EInvoiceFormatDetected.XRECHNUNG_2_1
            else:
                return EInvoiceFormatDetected.XRECHNUNG_2_0

        if format_str == "zugferd":
            if version.startswith("2.3"):
                return EInvoiceFormatDetected.ZUGFERD_2_3
            elif version.startswith("2.2"):
                return EInvoiceFormatDetected.ZUGFERD_2_2
            elif version.startswith("2.1"):
                return EInvoiceFormatDetected.ZUGFERD_2_1
            elif version.startswith("2.0"):
                return EInvoiceFormatDetected.ZUGFERD_2_0
            elif version.startswith("1."):
                return EInvoiceFormatDetected.ZUGFERD_1_0
            else:
                return EInvoiceFormatDetected.ZUGFERD_2_3

        if format_str == "facturx":
            return EInvoiceFormatDetected.FACTURX

        return EInvoiceFormatDetected.UNKNOWN

    def _map_profile(
        self,
        profile: Optional[str]
    ) -> Optional[ZUGFeRDProfile]:
        """Mappt Profil-String zu Enum."""
        if not profile:
            return None

        profile_upper = profile.upper()
        try:
            return ZUGFeRDProfile(profile_upper)
        except ValueError:
            # Fallback-Mapping
            if "MINIMUM" in profile_upper:
                return ZUGFeRDProfile.MINIMUM
            elif "BASIC" in profile_upper and "WL" in profile_upper:
                return ZUGFeRDProfile.BASIC_WL
            elif "BASIC" in profile_upper:
                return ZUGFeRDProfile.BASIC
            elif "EN16931" in profile_upper or "COMFORT" in profile_upper:
                return ZUGFeRDProfile.EN16931
            elif "EXTENDED" in profile_upper:
                return ZUGFeRDProfile.EXTENDED
            elif "XRECHNUNG" in profile_upper:
                return ZUGFeRDProfile.XRECHNUNG

            return None


# Singleton Instance
_parser_service: Optional[EInvoiceParserService] = None


def get_parser_service() -> EInvoiceParserService:
    """Gibt Singleton Parser Service zurueck."""
    global _parser_service
    if _parser_service is None:
        _parser_service = EInvoiceParserService()
    return _parser_service
