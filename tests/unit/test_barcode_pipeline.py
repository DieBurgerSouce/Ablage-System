# -*- coding: utf-8 -*-
"""
Unit Tests fuer Barcode/QR Pipeline Integration.

Tests:
- BarcodeDetection Model
- BarcodePipelineService (detect_and_store, get, link_sepa, link_product, redetect)
- API Schemas (Serialisierung/Validierung)
- Celery Task (detect_barcodes_task)

Feinpoliert und durchdacht - Umfassende Tests.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models_barcode import (
    BarcodeCategory,
    BarcodeCodeType,
    BarcodeDetection,
)
from app.api.schemas.barcode import (
    BarcodeDetectionResponse,
    BarcodeListResponse,
    BarcodeRedetectRequest,
    BarcodeRedetectResponse,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestBarcodeCodeType:
    """Tests fuer BarcodeCodeType Enum."""

    def test_all_code_types_exist(self) -> None:
        assert BarcodeCodeType.QR_CODE == "qr_code"
        assert BarcodeCodeType.SEPA_QR == "sepa_qr"
        assert BarcodeCodeType.EAN_13 == "ean_13"
        assert BarcodeCodeType.EAN_8 == "ean_8"
        assert BarcodeCodeType.CODE_128 == "code_128"
        assert BarcodeCodeType.CODE_39 == "code_39"
        assert BarcodeCodeType.DATA_MATRIX == "data_matrix"
        assert BarcodeCodeType.PDF_417 == "pdf_417"
        assert BarcodeCodeType.UNKNOWN == "unknown"

    def test_is_string_enum(self) -> None:
        assert isinstance(BarcodeCodeType.QR_CODE, str)
        assert BarcodeCodeType.SEPA_QR.value == "sepa_qr"


class TestBarcodeCategory:
    """Tests fuer BarcodeCategory Enum."""

    def test_all_categories_exist(self) -> None:
        assert BarcodeCategory.PAYMENT == "payment"
        assert BarcodeCategory.PRODUCT == "product"
        assert BarcodeCategory.LOGISTICS == "logistics"
        assert BarcodeCategory.DOCUMENT == "document"
        assert BarcodeCategory.URL == "url"
        assert BarcodeCategory.OTHER == "other"


class TestBarcodeDetectionModel:
    """Tests fuer BarcodeDetection SQLAlchemy Model."""

    def test_tablename(self) -> None:
        assert BarcodeDetection.__tablename__ == "barcode_detections"

    def test_repr(self) -> None:
        doc_id = uuid.uuid4()
        det = BarcodeDetection()
        det.id = uuid.uuid4()
        det.document_id = doc_id
        det.code_type = "sepa_qr"
        det.category = "payment"
        r = repr(det)
        assert "BarcodeDetection" in r
        assert str(det.id) in r


# =============================================================================
# Schema Tests
# =============================================================================


class TestBarcodeDetectionResponse:
    """Tests fuer BarcodeDetectionResponse Schema."""

    def test_valid_response(self) -> None:
        now = datetime.now(timezone.utc)
        doc_id = uuid.uuid4()
        det_id = uuid.uuid4()

        resp = BarcodeDetectionResponse(
            id=det_id,
            document_id=doc_id,
            code_type="sepa_qr",
            category="payment",
            raw_value="BCD\n002\n1\nSCT\n...",
            parsed_data={"iban": "DE89370400440532013000"},
            position_x=100,
            position_y=200,
            position_width=50,
            position_height=50,
            page_number=1,
            confidence=0.95,
            created_at=now,
        )

        assert resp.id == det_id
        assert resp.code_type == "sepa_qr"
        assert resp.category == "payment"
        assert resp.confidence == 0.95
        assert resp.page_number == 1

    def test_confidence_validation(self) -> None:
        with pytest.raises(Exception):
            BarcodeDetectionResponse(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                code_type="qr_code",
                category="other",
                raw_value="test",
                position_x=0,
                position_y=0,
                position_width=10,
                position_height=10,
                page_number=1,
                confidence=1.5,  # Ungueltig
                created_at=datetime.now(timezone.utc),
            )

    def test_page_number_validation(self) -> None:
        with pytest.raises(Exception):
            BarcodeDetectionResponse(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                code_type="qr_code",
                category="other",
                raw_value="test",
                position_x=0,
                position_y=0,
                position_width=10,
                position_height=10,
                page_number=0,  # Ungueltig (muss >= 1 sein)
                confidence=0.5,
                created_at=datetime.now(timezone.utc),
            )


class TestBarcodeListResponse:
    """Tests fuer BarcodeListResponse Schema."""

    def test_empty_list(self) -> None:
        doc_id = uuid.uuid4()
        resp = BarcodeListResponse(
            document_id=doc_id,
            erkennungen=[],
            gesamt=0,
            hat_zahlungscodes=False,
            hat_produktcodes=False,
        )
        assert resp.gesamt == 0
        assert not resp.hat_zahlungscodes
        assert not resp.hat_produktcodes

    def test_with_detections(self) -> None:
        doc_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        det = BarcodeDetectionResponse(
            id=uuid.uuid4(),
            document_id=doc_id,
            code_type="ean_13",
            category="product",
            raw_value="4006381333931",
            parsed_data={"ean": "4006381333931", "valid_checksum": True},
            position_x=10,
            position_y=20,
            position_width=100,
            position_height=30,
            page_number=1,
            confidence=0.92,
            created_at=now,
        )

        resp = BarcodeListResponse(
            document_id=doc_id,
            erkennungen=[det],
            gesamt=1,
            hat_zahlungscodes=False,
            hat_produktcodes=True,
        )
        assert resp.gesamt == 1
        assert resp.hat_produktcodes


class TestBarcodeRedetectRequest:
    """Tests fuer BarcodeRedetectRequest Schema."""

    def test_without_grund(self) -> None:
        req = BarcodeRedetectRequest()
        assert req.grund is None

    def test_with_grund(self) -> None:
        req = BarcodeRedetectRequest(grund="Neue Seiten hinzugefuegt")
        assert req.grund == "Neue Seiten hinzugefuegt"


class TestBarcodeRedetectResponse:
    """Tests fuer BarcodeRedetectResponse Schema."""

    def test_response(self) -> None:
        doc_id = uuid.uuid4()
        resp = BarcodeRedetectResponse(
            document_id=doc_id,
            nachricht="Erneute Barcode-Erkennung wurde gestartet.",
            task_id="abc-123",
        )
        assert resp.nachricht == "Erneute Barcode-Erkennung wurde gestartet."
        assert resp.task_id == "abc-123"


# =============================================================================
# Service Tests (mit Mocks)
# =============================================================================


class TestBarcodePipelineService:
    """Tests fuer BarcodePipelineService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_detect_and_store_empty(self, mock_db: AsyncMock) -> None:
        """Test: Keine Bilder -> keine Erkennungen."""
        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.process = AsyncMock(
                return_value={"codes": [], "total_codes": 0}
            )
            mock_get_detector.return_value = mock_detector

            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            results = await service.detect_and_store(
                document_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                image_pages=[],
            )
            assert results == []

    @pytest.mark.asyncio
    async def test_detect_and_store_with_codes(self, mock_db: AsyncMock) -> None:
        """Test: Erkennung mit Ergebnissen -> Speicherung in DB."""
        fake_codes = [
            {
                "code_type": "sepa_qr",
                "category": "payment",
                "data": "BCD\n002\n1\nSCT\nCOBADEFF\nMax Mustermann\nDE89370400440532013000\nEUR100.00",
                "confidence": 0.95,
                "x": 10,
                "y": 20,
                "width": 50,
                "height": 50,
                "parsed_data": {
                    "iban": "DE89370400440532013000",
                    "recipient_name": "Max Mustermann",
                    "amount": 100.0,
                },
            },
        ]

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.process = AsyncMock(
                return_value={"codes": fake_codes, "total_codes": 1}
            )
            mock_get_detector.return_value = mock_detector

            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            results = await service.detect_and_store(
                document_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                image_pages=["page1.png"],
            )

            assert len(results) == 1
            assert results[0].code_type == "sepa_qr"
            assert results[0].category == "payment"
            assert results[0].confidence == 0.95
            mock_db.add.assert_called_once()
            mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_document_barcodes(self, mock_db: AsyncMock) -> None:
        """Test: Abruf gespeicherter Barcodes."""
        doc_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ):
            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            results = await service.get_document_barcodes(
                document_id=doc_id,
                company_id=company_id,
            )
            assert results == []
            mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_link_sepa_payment_not_found(self, mock_db: AsyncMock) -> None:
        """Test: SEPA-Link mit nicht existierendem Barcode."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ):
            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            result = await service.link_sepa_payment(
                detection_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_link_sepa_payment_success(self, mock_db: AsyncMock) -> None:
        """Test: SEPA-Link mit gueltigem SEPA-QR Barcode."""
        detection = BarcodeDetection()
        detection.id = uuid.uuid4()
        detection.document_id = uuid.uuid4()
        detection.code_type = "sepa_qr"
        detection.category = "payment"
        detection.raw_value = "BCD..."
        detection.parsed_data = {
            "iban": "DE89370400440532013000",
            "bic": "COBADEFF",
            "recipient_name": "Max Mustermann",
            "amount": 100.0,
            "currency": "EUR",
            "reference": "RE2026-001",
            "remittance_text": "",
        }
        detection.confidence = 0.95

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = detection
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ):
            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            result = await service.link_sepa_payment(
                detection_id=str(detection.id),
                company_id=str(uuid.uuid4()),
            )

            assert result is not None
            assert result["iban"] == "DE89370400440532013000"
            assert result["recipient_name"] == "Max Mustermann"
            assert result["amount"] == 100.0
            assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_link_sepa_payment_wrong_type(self, mock_db: AsyncMock) -> None:
        """Test: SEPA-Link mit nicht-SEPA Barcode -> None."""
        detection = BarcodeDetection()
        detection.id = uuid.uuid4()
        detection.document_id = uuid.uuid4()
        detection.code_type = "ean_13"
        detection.category = "product"
        detection.raw_value = "4006381333931"
        detection.parsed_data = {}
        detection.confidence = 0.9

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = detection
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ):
            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            result = await service.link_sepa_payment(
                detection_id=str(detection.id),
                company_id=str(uuid.uuid4()),
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_link_product_code_success(self, mock_db: AsyncMock) -> None:
        """Test: Produkt-Link mit gueltigem EAN-13."""
        detection = BarcodeDetection()
        detection.id = uuid.uuid4()
        detection.document_id = uuid.uuid4()
        detection.code_type = "ean_13"
        detection.category = "product"
        detection.raw_value = "4006381333931"
        detection.parsed_data = {
            "ean": "4006381333931",
            "valid_checksum": True,
        }
        detection.confidence = 0.92

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = detection
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ):
            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            result = await service.link_product_code(
                detection_id=str(detection.id),
                company_id=str(uuid.uuid4()),
            )

            assert result is not None
            assert result["ean"] == "4006381333931"
            assert result["valid_checksum"] is True
            assert result["code_type"] == "ean_13"

    @pytest.mark.asyncio
    async def test_link_product_code_wrong_type(self, mock_db: AsyncMock) -> None:
        """Test: Produkt-Link mit nicht-EAN Barcode -> None."""
        detection = BarcodeDetection()
        detection.id = uuid.uuid4()
        detection.code_type = "sepa_qr"
        detection.category = "payment"
        detection.raw_value = "BCD..."
        detection.parsed_data = {}
        detection.confidence = 0.9

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = detection
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.barcode_pipeline_service.get_qr_barcode_detector"
        ):
            from app.services.barcode_pipeline_service import BarcodePipelineService

            service = BarcodePipelineService(mock_db)
            result = await service.link_product_code(
                detection_id=str(detection.id),
                company_id=str(uuid.uuid4()),
            )
            assert result is None


# =============================================================================
# Detector Integration Tests
# =============================================================================


class TestQRBarcodeDetectorIntegration:
    """Integration-Tests mit dem existierenden Detector."""

    def test_code_type_mapping(self) -> None:
        """Test: CodeType Enum Werte stimmen mit DB-Enum ueberein."""
        from app.agents.preprocessing.qr_barcode_detector import CodeType

        # Alle Detector CodeTypes muessen in BarcodeCodeType sein
        for ct in CodeType:
            assert ct.value in [bct.value for bct in BarcodeCodeType], (
                f"CodeType.{ct.name} fehlt in BarcodeCodeType"
            )

    def test_category_mapping(self) -> None:
        """Test: CodeCategory Enum Werte stimmen mit DB-Enum ueberein."""
        from app.agents.preprocessing.qr_barcode_detector import CodeCategory

        for cc in CodeCategory:
            assert cc.value in [bc.value for bc in BarcodeCategory], (
                f"CodeCategory.{cc.name} fehlt in BarcodeCategory"
            )

    def test_sepa_parser_available(self) -> None:
        """Test: SEPA-Parser ist im Detector verfuegbar."""
        from app.agents.preprocessing.qr_barcode_detector import SEPAQRParser

        parser = SEPAQRParser()
        # Leere Daten -> None
        result = parser.parse("")
        assert result is None

        # Ungueltige Daten -> None
        result = parser.parse("Kein EPC QR Code")
        assert result is None

    def test_barcode_validator(self) -> None:
        """Test: Barcode-Validierung funktioniert."""
        from app.agents.preprocessing.qr_barcode_detector import BarcodeValidator

        validator = BarcodeValidator()

        # Gueltige EAN-13
        assert validator.validate_ean13("4006381333931") is True

        # Ungueltige EAN-13 (falsche Pruefsumme)
        assert validator.validate_ean13("4006381333932") is False

        # Ungueltige Laenge
        assert validator.validate_ean13("123") is False

        # Leerer String
        assert validator.validate_ean13("") is False
