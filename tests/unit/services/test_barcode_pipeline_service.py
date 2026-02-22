# -*- coding: utf-8 -*-
"""
Tests fuer BarcodePipelineService.

Testet Erkennung, Speicherung, SEPA-Verknuepfung,
Produkt-Code-Verknuepfung und Re-Detection.
"""

import pytest
import uuid
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.barcode_pipeline_service import BarcodePipelineService


# =============================================================================
# Hilfklassen
# =============================================================================


class _FakeBarcodeDetection:
    """Ersatz fuer SQLAlchemy BarcodeDetection um Mapper-Init zu vermeiden."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# =============================================================================
# Fixtures
# =============================================================================

DOCUMENT_ID = str(uuid.uuid4())
COMPANY_ID = str(uuid.uuid4())


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock-Datenbank-Session."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_detector() -> AsyncMock:
    """Mock QR/Barcode Detector."""
    detector = AsyncMock()
    return detector


@pytest.fixture
def service(mock_db: AsyncMock, mock_detector: AsyncMock) -> BarcodePipelineService:
    """BarcodePipelineService mit gemocktem Detector."""
    with patch(
        "app.services.barcode_pipeline_service.get_qr_barcode_detector",
        return_value=mock_detector,
    ):
        svc = BarcodePipelineService(mock_db)
    return svc


def make_code_data(
    code_type: str = "qr_code",
    category: str = "other",
    data: str = "test-data",
    confidence: float = 0.95,
    parsed_data: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """Erzeugt ein Code-Dict wie vom Detector zurueckgegeben."""
    return {
        "code_type": code_type,
        "category": category,
        "data": data,
        "confidence": confidence,
        "x": 100,
        "y": 200,
        "width": 50,
        "height": 50,
        "parsed_data": parsed_data or {},
    }


# =============================================================================
# detect_and_store Tests
# =============================================================================


@patch("app.services.barcode_pipeline_service.BarcodeDetection", _FakeBarcodeDetection)
class TestDetectAndStore:
    """Tests fuer detect_and_store."""

    @pytest.mark.asyncio
    async def test_erkennung_einer_seite(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock
    ) -> None:
        """Ein Code auf einer Seite wird erkannt und gespeichert."""
        mock_detector.process.return_value = {
            "codes": [make_code_data()]
        }

        results = await service.detect_and_store(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            image_pages=["page1.png"],
        )

        assert len(results) == 1
        assert mock_db.add.call_count == 1
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_erkennung_mehrerer_seiten(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock
    ) -> None:
        """Mehrere Seiten mit mehreren Codes."""
        mock_detector.process.side_effect = [
            {"codes": [make_code_data(), make_code_data(code_type="ean_13")]},
            {"codes": [make_code_data(code_type="sepa_qr")]},
        ]

        results = await service.detect_and_store(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            image_pages=["page1.png", "page2.png"],
        )

        assert len(results) == 3
        assert mock_db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_keine_codes_gefunden(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock
    ) -> None:
        """Keine Codes auf Seite -> leere Liste, kein flush."""
        mock_detector.process.return_value = {"codes": []}

        results = await service.detect_and_store(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            image_pages=["page1.png"],
        )

        assert len(results) == 0
        mock_db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fehler_auf_einer_seite_ueberspringt(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock
    ) -> None:
        """Fehler auf einer Seite ueberspringt sie, andere werden verarbeitet."""
        mock_detector.process.side_effect = [
            Exception("Image corrupt"),
            {"codes": [make_code_data()]},
        ]

        results = await service.detect_and_store(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            image_pages=["bad.png", "good.png"],
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_seitennummer_korrekt(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock
    ) -> None:
        """Seitennummern beginnen bei 1."""
        mock_detector.process.side_effect = [
            {"codes": [make_code_data()]},
            {"codes": [make_code_data()]},
        ]

        results = await service.detect_and_store(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            image_pages=["p1.png", "p2.png"],
        )

        assert results[0].page_number == 1
        assert results[1].page_number == 2

    @pytest.mark.asyncio
    async def test_detection_felder_korrekt_gemappt(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock
    ) -> None:
        """Code-Daten werden korrekt auf BarcodeDetection gemappt."""
        code = make_code_data(
            code_type="ean_13",
            category="product",
            data="4006381333931",
            confidence=0.99,
        )
        mock_detector.process.return_value = {"codes": [code]}

        results = await service.detect_and_store(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            image_pages=["page.png"],
        )

        det = results[0]
        assert det.code_type == "ean_13"
        assert det.category == "product"
        assert det.raw_value == "4006381333931"
        assert det.confidence == 0.99
        assert det.position_x == 100
        assert det.position_y == 200


# =============================================================================
# get_document_barcodes Tests
# =============================================================================


class TestGetDocumentBarcodes:
    """Tests fuer get_document_barcodes."""

    @pytest.mark.asyncio
    async def test_alle_barcodes_abrufen(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Alle Barcodes eines Dokuments werden abgerufen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        mock_db.execute.return_value = mock_result

        results = await service.get_document_barcodes(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_filter_nach_kategorie(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Filter nach Kategorie wird angewendet."""
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

        await service.get_document_barcodes(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            category="sepa",
        )

        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_filter_nach_seite(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Filter nach Seitennummer wird angewendet."""
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

        await service.get_document_barcodes(
            document_id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            page_number=2,
        )

        mock_db.execute.assert_awaited_once()


# =============================================================================
# get_barcode_by_id Tests
# =============================================================================


class TestGetBarcodeById:
    """Tests fuer get_barcode_by_id."""

    @pytest.mark.asyncio
    async def test_barcode_gefunden(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Barcode wird per ID gefunden."""
        mock_detection = MagicMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_detection)
        )

        result = await service.get_barcode_by_id(str(uuid.uuid4()), COMPANY_ID)
        assert result is mock_detection

    @pytest.mark.asyncio
    async def test_barcode_nicht_gefunden(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Barcode nicht gefunden gibt None zurueck."""
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )

        result = await service.get_barcode_by_id(str(uuid.uuid4()), COMPANY_ID)
        assert result is None


# =============================================================================
# link_sepa_payment Tests
# =============================================================================


class TestLinkSepaPayment:
    """Tests fuer link_sepa_payment."""

    @pytest.mark.asyncio
    async def test_sepa_verknuepfung_erfolgreich(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """SEPA-QR-Code wird korrekt verknuepft."""
        detection = MagicMock()
        detection.id = uuid.uuid4()
        detection.document_id = uuid.uuid4()
        detection.code_type = "sepa_qr"
        detection.confidence = 0.98
        detection.parsed_data = {
            "iban": "DE89370400440532013000",
            "bic": "COBADEFFXXX",
            "recipient_name": "Mueller GmbH",
            "amount": "1234.56",
            "currency": "EUR",
            "reference": "RE-4711",
            "remittance_text": "Rechnung 4711",
        }

        with patch.object(service, "get_barcode_by_id", return_value=detection):
            result = await service.link_sepa_payment(str(uuid.uuid4()), COMPANY_ID)

        assert result is not None
        assert result["iban"] == "DE89370400440532013000"
        assert result["recipient_name"] == "Mueller GmbH"
        assert result["amount"] == "1234.56"
        assert result["confidence"] == 0.98

    @pytest.mark.asyncio
    async def test_kein_sepa_typ_gibt_none(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Nicht-SEPA Code-Typ gibt None zurueck."""
        detection = MagicMock()
        detection.code_type = "ean_13"

        with patch.object(service, "get_barcode_by_id", return_value=detection):
            result = await service.link_sepa_payment(str(uuid.uuid4()), COMPANY_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_sepa_ohne_iban_gibt_none(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """SEPA-Code ohne IBAN gibt None zurueck."""
        detection = MagicMock()
        detection.code_type = "sepa_qr"
        detection.parsed_data = {"recipient_name": "Test"}

        with patch.object(service, "get_barcode_by_id", return_value=detection):
            result = await service.link_sepa_payment(str(uuid.uuid4()), COMPANY_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_detection_nicht_gefunden_gibt_none(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Nicht vorhandene Detection gibt None zurueck."""
        with patch.object(service, "get_barcode_by_id", return_value=None):
            result = await service.link_sepa_payment(str(uuid.uuid4()), COMPANY_ID)

        assert result is None


# =============================================================================
# link_product_code Tests
# =============================================================================


class TestLinkProductCode:
    """Tests fuer link_product_code."""

    @pytest.mark.asyncio
    async def test_ean13_verknuepfung(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """EAN-13 Code wird korrekt verknuepft."""
        detection = MagicMock()
        detection.id = uuid.uuid4()
        detection.code_type = "ean_13"
        detection.raw_value = "4006381333931"
        detection.confidence = 0.99
        detection.parsed_data = {
            "ean": "4006381333931",
            "valid_checksum": True,
        }

        with patch.object(service, "get_barcode_by_id", return_value=detection):
            result = await service.link_product_code(str(uuid.uuid4()), COMPANY_ID)

        assert result is not None
        assert result["ean"] == "4006381333931"
        assert result["valid_checksum"] is True
        assert result["code_type"] == "ean_13"

    @pytest.mark.asyncio
    async def test_ean8_verknuepfung(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """EAN-8 Code wird ebenfalls akzeptiert."""
        detection = MagicMock()
        detection.id = uuid.uuid4()
        detection.code_type = "ean_8"
        detection.raw_value = "12345678"
        detection.confidence = 0.95
        detection.parsed_data = {"ean": "12345678"}

        with patch.object(service, "get_barcode_by_id", return_value=detection):
            result = await service.link_product_code(str(uuid.uuid4()), COMPANY_ID)

        assert result is not None
        assert result["ean"] == "12345678"

    @pytest.mark.asyncio
    async def test_kein_ean_typ_gibt_none(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Nicht-EAN Code-Typ gibt None zurueck."""
        detection = MagicMock()
        detection.code_type = "qr_code"

        with patch.object(service, "get_barcode_by_id", return_value=detection):
            result = await service.link_product_code(str(uuid.uuid4()), COMPANY_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_detection_nicht_gefunden_gibt_none(
        self, service: BarcodePipelineService, mock_db: AsyncMock
    ) -> None:
        """Nicht vorhandene Detection gibt None zurueck."""
        with patch.object(service, "get_barcode_by_id", return_value=None):
            result = await service.link_product_code(str(uuid.uuid4()), COMPANY_ID)

        assert result is None


# =============================================================================
# redetect_document Tests
# =============================================================================


class TestRedetectDocument:
    """Tests fuer redetect_document."""

    @pytest.mark.asyncio
    async def test_alte_erkennungen_geloescht(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock,
    ) -> None:
        """Alte Erkennungen werden vor Re-Detection geloescht."""
        mock_detector.process.return_value = {"codes": [make_code_data()]}

        with patch("app.services.barcode_pipeline_service.delete") as mock_delete, \
             patch("app.services.barcode_pipeline_service.BarcodeDetection") as MockBD:
            mock_delete.return_value = MagicMock(where=MagicMock(return_value="del_stmt"))

            await service.redetect_document(
                document_id=DOCUMENT_ID,
                company_id=COMPANY_ID,
                image_pages=["page.png"],
            )

        mock_delete.assert_called_once_with(MockBD)
        mock_db.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_neue_erkennungen_nach_loeschung(
        self, service: BarcodePipelineService, mock_detector: AsyncMock, mock_db: AsyncMock,
    ) -> None:
        """Nach Loeschung werden neue Codes erkannt und gespeichert."""
        mock_detector.process.return_value = {
            "codes": [make_code_data(), make_code_data(code_type="ean_8")]
        }

        with patch("app.services.barcode_pipeline_service.delete") as mock_delete, \
             patch("app.services.barcode_pipeline_service.BarcodeDetection"):
            mock_delete.return_value = MagicMock(where=MagicMock(return_value="del_stmt"))

            results = await service.redetect_document(
                document_id=DOCUMENT_ID,
                company_id=COMPANY_ID,
                image_pages=["page.png"],
            )

        assert len(results) == 2
