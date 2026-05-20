# -*- coding: utf-8 -*-
"""
Barcode/QR Pipeline Service fuer Ablage-System.

Integriert die QR/Barcode-Erkennung in die Dokumentenverarbeitung:
- Erkennung und Speicherung in DB
- SEPA-Payment-Verknuepfung
- Produkt-Code-Verknuepfung
- Re-Detection bei Bedarf

Feinpoliert und durchdacht - Enterprise-grade Barcode Pipeline.
"""

import uuid
from typing import Dict, List, Optional, Union

import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.preprocessing.qr_barcode_detector import (
    CodeCategory,
    CodeDetectionResult,
    CodeType,
    DetectedCode,
    get_qr_barcode_detector,
)
from app.core.safe_errors import safe_error_log
from app.db.models_barcode import BarcodeDetection

logger = structlog.get_logger(__name__)


class BarcodePipelineService:
    """
    Service fuer Barcode/QR-Erkennung und Verarbeitung.

    Verbindet den QRBarcodeDetectorAgent mit der Datenbank
    und der OCR-Pipeline.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._detector = get_qr_barcode_detector()

    async def detect_and_store(
        self,
        document_id: str,
        company_id: str,
        image_pages: List[Union[str, object]],
    ) -> List[BarcodeDetection]:
        """
        Fuehre Barcode/QR-Erkennung auf allen Seiten durch und speichere Ergebnisse.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID (Multi-Tenant)
            image_pages: Liste von Bild-Pfaden oder numpy arrays (je Seite)

        Returns:
            Liste der gespeicherten BarcodeDetection Eintraege
        """
        all_detections: List[BarcodeDetection] = []

        for page_idx, image in enumerate(image_pages, start=1):
            try:
                result = await self._detector.process({
                    "image": image,
                    "detect_sepa": True,
                    "detect_products": True,
                })

                codes: List[Dict[str, object]] = result.get("codes", [])

                for code_data in codes:
                    detection = BarcodeDetection(
                        id=uuid.uuid4(),
                        document_id=uuid.UUID(document_id),
                        company_id=uuid.UUID(company_id),
                        code_type=str(code_data.get("code_type", "unknown")),
                        category=str(code_data.get("category", "other")),
                        raw_value=str(code_data.get("data", "")),
                        parsed_data=code_data.get("parsed_data") or {},
                        position_x=int(code_data.get("x", 0)),
                        position_y=int(code_data.get("y", 0)),
                        position_width=int(code_data.get("width", 0)),
                        position_height=int(code_data.get("height", 0)),
                        page_number=page_idx,
                        confidence=float(code_data.get("confidence", 0.0)),
                    )
                    self.db.add(detection)
                    all_detections.append(detection)

                logger.info(
                    "barcode_page_detected",
                    document_id=document_id,
                    page_number=page_idx,
                    codes_found=len(codes),
                )

            except Exception as e:
                logger.warning(
                    "barcode_page_detection_error",
                    document_id=document_id,
                    page_number=page_idx,
                    **safe_error_log(e),
                )

        if all_detections:
            await self.db.flush()

        logger.info(
            "barcode_detect_and_store_complete",
            document_id=document_id,
            total_detections=len(all_detections),
            pages_processed=len(image_pages),
        )

        return all_detections

    async def get_document_barcodes(
        self,
        document_id: str,
        company_id: str,
        category: Optional[str] = None,
        page_number: Optional[int] = None,
    ) -> List[BarcodeDetection]:
        """
        Hole alle erkannten Barcodes fuer ein Dokument.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID (Multi-Tenant)
            category: Optionaler Kategorie-Filter
            page_number: Optionaler Seiten-Filter

        Returns:
            Liste der BarcodeDetection Eintraege
        """
        stmt = (
            select(BarcodeDetection)
            .where(
                BarcodeDetection.document_id == uuid.UUID(document_id),
                BarcodeDetection.company_id == uuid.UUID(company_id),
            )
            .order_by(BarcodeDetection.page_number, BarcodeDetection.created_at)
        )

        if category is not None:
            stmt = stmt.where(BarcodeDetection.category == category)

        if page_number is not None:
            stmt = stmt.where(BarcodeDetection.page_number == page_number)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_barcode_by_id(
        self,
        barcode_id: str,
        company_id: str,
    ) -> Optional[BarcodeDetection]:
        """
        Hole einen einzelnen Barcode-Eintrag.

        Args:
            barcode_id: Barcode-Detection-ID
            company_id: Company-ID (Multi-Tenant)

        Returns:
            BarcodeDetection oder None
        """
        stmt = select(BarcodeDetection).where(
            BarcodeDetection.id == uuid.UUID(barcode_id),
            BarcodeDetection.company_id == uuid.UUID(company_id),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def link_sepa_payment(
        self,
        detection_id: str,
        company_id: str,
    ) -> Optional[Dict[str, object]]:
        """
        Verknuepfe SEPA-QR-Erkennung mit Rechnungs-Metadaten.

        Liest die geparsten SEPA-Daten und gibt sie zurueck,
        damit der Aufrufer sie in die Rechnung uebernehmen kann.

        Args:
            detection_id: Barcode-Detection-ID
            company_id: Company-ID (Multi-Tenant)

        Returns:
            Dict mit SEPA-Payment-Daten oder None
        """
        detection = await self.get_barcode_by_id(detection_id, company_id)
        if detection is None:
            return None

        if detection.code_type != CodeType.SEPA_QR.value:
            logger.warning(
                "barcode_not_sepa",
                detection_id=detection_id,
                code_type=detection.code_type,
            )
            return None

        parsed = detection.parsed_data or {}
        if not parsed.get("iban"):
            logger.warning(
                "barcode_sepa_no_iban",
                detection_id=detection_id,
            )
            return None

        sepa_data: Dict[str, object] = {
            "iban": parsed.get("iban", ""),
            "bic": parsed.get("bic"),
            "recipient_name": parsed.get("recipient_name", ""),
            "amount": parsed.get("amount"),
            "currency": parsed.get("currency", "EUR"),
            "reference": parsed.get("reference", ""),
            "remittance_text": parsed.get("remittance_text", ""),
            "detection_id": str(detection.id),
            "confidence": detection.confidence,
        }

        logger.info(
            "barcode_sepa_linked",
            detection_id=detection_id,
            document_id=str(detection.document_id),
        )

        return sepa_data

    async def link_product_code(
        self,
        detection_id: str,
        company_id: str,
    ) -> Optional[Dict[str, object]]:
        """
        Verknuepfe EAN-Code-Erkennung mit Produktdaten.

        Args:
            detection_id: Barcode-Detection-ID
            company_id: Company-ID (Multi-Tenant)

        Returns:
            Dict mit Produkt-Daten oder None
        """
        detection = await self.get_barcode_by_id(detection_id, company_id)
        if detection is None:
            return None

        if detection.code_type not in (
            CodeType.EAN_13.value,
            CodeType.EAN_8.value,
        ):
            logger.warning(
                "barcode_not_ean",
                detection_id=detection_id,
                code_type=detection.code_type,
            )
            return None

        parsed = detection.parsed_data or {}

        product_data: Dict[str, object] = {
            "ean": parsed.get("ean", detection.raw_value),
            "valid_checksum": parsed.get("valid_checksum", False),
            "code_type": detection.code_type,
            "detection_id": str(detection.id),
            "confidence": detection.confidence,
        }

        logger.info(
            "barcode_product_linked",
            detection_id=detection_id,
            ean=detection.raw_value,
        )

        return product_data

    async def redetect_document(
        self,
        document_id: str,
        company_id: str,
        image_pages: List[Union[str, object]],
    ) -> List[BarcodeDetection]:
        """
        Loesche alte Erkennungen und fuehre erneute Erkennung durch.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID (Multi-Tenant)
            image_pages: Liste von Bild-Pfaden oder numpy arrays

        Returns:
            Liste der neuen BarcodeDetection Eintraege
        """
        # Alte Erkennungen loeschen
        del_stmt = delete(BarcodeDetection).where(
            BarcodeDetection.document_id == uuid.UUID(document_id),
            BarcodeDetection.company_id == uuid.UUID(company_id),
        )
        await self.db.execute(del_stmt)

        logger.info(
            "barcode_redetect_cleared",
            document_id=document_id,
        )

        # Neu erkennen
        return await self.detect_and_store(
            document_id=document_id,
            company_id=company_id,
            image_pages=image_pages,
        )
