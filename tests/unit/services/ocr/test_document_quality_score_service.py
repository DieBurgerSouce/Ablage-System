# -*- coding: utf-8 -*-
"""
Unit Tests fuer DocumentQualityScoreService.

Testet:
- Composite Quality Score Berechnung
- Ampel-Schwellenwerte (gruen/gelb/rot)
- Feld-Vollstaendigkeit
- Verarbeitungs-Status
- Company Quality Overview
- Fehlerfaelle (Dokument nicht gefunden)

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from uuid import UUID

from app.services.ocr.document_quality_score_service import (
    DocumentQualityScoreService,
    DocumentQualityScore,
    CompanyQualityOverview,
    QualityDimension,
    AmpelColor,
    _score_to_ampel,
    REQUIRED_FIELDS,
)


# Test-Konstanten
TEST_DOC_UUID = UUID("00000000-0000-0000-0000-000000000007")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")

pytestmark = [pytest.mark.unit]


# ========================= Fixtures =========================


@pytest.fixture
def service() -> DocumentQualityScoreService:
    """Service-Instanz."""
    return DocumentQualityScoreService()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock DB Session."""
    return AsyncMock()


def _make_mock_document(
    doc_id: str = str(TEST_DOC_UUID),
    ocr_confidence: float = 0.92,
    document_type: str = "invoice",
    status: str = "completed",
    extracted_data: object = None,
) -> Mock:
    """Hilfsfunktion: Erzeugt ein Mock-Dokument."""
    mock_document = Mock()
    mock_document.id = doc_id
    mock_document.ocr_confidence = ocr_confidence
    mock_document.document_type = document_type
    mock_document.status = status
    mock_document.company_id = str(TEST_COMPANY_UUID)
    if extracted_data is None:
        extracted_data = {
            "invoice_number": "INV-001",
            "invoice_date": "2026-01-15",
            "net_amount": "1000.00",
            "gross_amount": "1190.00",
            "vat_amount": "190.00",
            "sender_company": "Test GmbH",
            "recipient_company": "Empfaenger AG",
        }
    mock_document.extracted_data = extracted_data
    return mock_document


def _setup_session_with_document(
    mock_session: AsyncMock,
    document: object,
) -> None:
    """Richtet die Mock-Session ein, um ein Dokument zurueckzugeben."""
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = document
    mock_session.execute.return_value = mock_result


# ========================= Ampel Schwellenwerte =========================


class TestScoreToAmpel:
    """Tests fuer die _score_to_ampel Hilfsfunktion."""

    def test_ampel_threshold_green(self) -> None:
        """Score >= 0.80 ergibt GRUEN."""
        color, label = _score_to_ampel(0.80)
        assert color == AmpelColor.GRUEN
        assert label == "Vollständig und vertrauenswuerdig"

    def test_ampel_threshold_green_high(self) -> None:
        """Perfekter Score ergibt GRUEN."""
        color, label = _score_to_ampel(1.0)
        assert color == AmpelColor.GRUEN

    def test_ampel_threshold_yellow(self) -> None:
        """Score 0.50-0.79 ergibt GELB."""
        color, label = _score_to_ampel(0.65)
        assert color == AmpelColor.GELB
        assert label == "Prüfung empfohlen"

    def test_ampel_threshold_yellow_lower_bound(self) -> None:
        """Score exakt 0.50 ergibt GELB."""
        color, label = _score_to_ampel(0.50)
        assert color == AmpelColor.GELB

    def test_ampel_threshold_red(self) -> None:
        """Score < 0.50 ergibt ROT."""
        color, label = _score_to_ampel(0.30)
        assert color == AmpelColor.ROT
        assert label == "Manuelle Korrektur erforderlich"

    def test_ampel_threshold_red_zero(self) -> None:
        """Score 0.0 ergibt ROT."""
        color, label = _score_to_ampel(0.0)
        assert color == AmpelColor.ROT


# ========================= Calculate Quality Score =========================


class TestCalculateQualityScore:
    """Tests fuer calculate_quality_score."""

    @pytest.mark.asyncio
    async def test_calculate_quality_high_score(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Hoher Score bei guten Werten ergibt GRUEN."""
        mock_doc = _make_mock_document(
            ocr_confidence=0.95,
            status="completed",
            document_type="invoice",
            extracted_data={
                "invoice_number": "INV-001",
                "invoice_date": "2026-01-15",
                "net_amount": "1000.00",
                "gross_amount": "1190.00",
                "vat_amount": "190.00",
                "sender_company": "Test GmbH",
                "recipient_company": "Empfaenger AG",
                "category": "eingangsrechnung",
            },
        )
        _setup_session_with_document(mock_session, mock_doc)

        result = await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

        assert isinstance(result, DocumentQualityScore)
        assert result.ampel_color == AmpelColor.GRUEN
        assert result.score >= 0.80
        assert len(result.dimensions) == 3

    @pytest.mark.asyncio
    async def test_calculate_quality_medium_score(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Mittlerer Score bei gemischten Werten ergibt GELB."""
        mock_doc = _make_mock_document(
            ocr_confidence=0.70,
            status="completed",
            document_type="invoice",
            extracted_data={
                "invoice_number": "INV-002",
                "invoice_date": "2026-02-01",
                # Fehlende Felder: net_amount, gross_amount, vat_amount,
                # sender_company, recipient_company
            },
        )
        _setup_session_with_document(mock_session, mock_doc)

        result = await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

        assert result.ampel_color == AmpelColor.GELB
        assert 0.50 <= result.score < 0.80

    @pytest.mark.asyncio
    async def test_calculate_quality_low_score(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Niedriger Score bei schlechten Werten ergibt ROT."""
        mock_doc = _make_mock_document(
            ocr_confidence=0.20,
            status="pending",
            document_type="other",
            extracted_data={},
        )
        _setup_session_with_document(mock_session, mock_doc)

        result = await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

        assert result.ampel_color == AmpelColor.ROT
        assert result.score < 0.50

    @pytest.mark.asyncio
    async def test_document_not_found(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """ValueError wenn Dokument nicht gefunden."""
        _setup_session_with_document(mock_session, None)

        with pytest.raises(ValueError, match="Dokument nicht gefunden"):
            await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

    @pytest.mark.asyncio
    async def test_recommendations_for_low_confidence(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Empfehlung bei niedriger OCR-Konfidenz."""
        mock_doc = _make_mock_document(ocr_confidence=0.50)
        _setup_session_with_document(mock_session, mock_doc)

        result = await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

        assert any(
            "niedrige Konfidenz" in r for r in result.recommendations
        )

    @pytest.mark.asyncio
    async def test_recommendations_for_medium_confidence(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Empfehlung bei mittlerer OCR-Konfidenz."""
        mock_doc = _make_mock_document(ocr_confidence=0.80)
        _setup_session_with_document(mock_session, mock_doc)

        result = await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

        assert any(
            "Stichprobenartige" in r for r in result.recommendations
        )

    @pytest.mark.asyncio
    async def test_composite_score_weighted_correctly(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Composite Score nutzt korrekte Gewichtungen."""
        mock_doc = _make_mock_document(
            ocr_confidence=0.92,
            status="completed",
            extracted_data={
                "invoice_number": "INV-001",
                "invoice_date": "2026-01-15",
                "net_amount": "1000.00",
                "gross_amount": "1190.00",
                "vat_amount": "190.00",
                "sender_company": "Test GmbH",
                "recipient_company": "Empfaenger AG",
            },
        )
        _setup_session_with_document(mock_session, mock_doc)

        result = await service.calculate_quality_score(str(TEST_DOC_UUID), mock_session)

        # Manuell berechnen: OCR=0.92*0.40 + Field=1.0*0.35 + Status varies
        # Status: ocr_completed=1.0 (completed), categorized=0.0, classified=1.0 (invoice) -> 2/3
        expected_status = 2.0 / 3.0
        expected_score = (0.92 * 0.40) + (1.0 * 0.35) + (expected_status * 0.25)
        assert abs(result.score - expected_score) < 0.01


# ========================= Field Completeness =========================


class TestFieldCompleteness:
    """Tests fuer die Feld-Vollstaendigkeitsberechnung."""

    def test_field_completeness_all_present(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Alle Pflichtfelder vorhanden ergibt Score 1.0."""
        extracted_data = {
            "invoice_number": "INV-001",
            "invoice_date": "2026-01-15",
            "net_amount": "1000.00",
            "gross_amount": "1190.00",
            "vat_amount": "190.00",
            "sender_company": "Test GmbH",
            "recipient_company": "Empfaenger AG",
        }

        score, sub_scores = service._calculate_field_completeness(
            "invoice", extracted_data
        )

        assert score == 1.0
        assert all(v == 1.0 for v in sub_scores.values())

    def test_field_completeness_missing_fields(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Fehlende Pflichtfelder senken den Score."""
        extracted_data = {
            "invoice_number": "INV-002",
            "invoice_date": "2026-02-01",
            # 5 von 7 Feldern fehlen
        }

        score, sub_scores = service._calculate_field_completeness(
            "invoice", extracted_data
        )

        assert score < 1.0
        expected_score = 2.0 / 7.0  # 2 von 7 Feldern vorhanden
        assert abs(score - expected_score) < 0.01
        assert sub_scores["invoice_number"] == 1.0
        assert sub_scores["net_amount"] == 0.0

    def test_field_completeness_empty_data(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Leere Daten ergeben Score 0.0."""
        score, sub_scores = service._calculate_field_completeness("invoice", {})
        assert score == 0.0
        assert all(v == 0.0 for v in sub_scores.values())

    def test_field_completeness_unknown_type_uses_default(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Unbekannter Dokumenttyp nutzt Default-Felder."""
        extracted_data = {
            "document_date": "2026-01-01",
            "sender": "Test GmbH",
        }
        score, sub_scores = service._calculate_field_completeness(
            "unknown_type", extracted_data
        )

        assert score == 1.0
        assert sub_scores["document_date"] == 1.0
        assert sub_scores["sender"] == 1.0

    def test_field_completeness_none_data(
        self, service: DocumentQualityScoreService
    ) -> None:
        """None als extracted_data behandeln."""
        score, sub_scores = service._calculate_field_completeness("invoice", None)
        assert score == 0.0

    def test_field_completeness_empty_string_not_counted(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Leere Strings zaehlen nicht als gefuellte Felder."""
        extracted_data = {
            "invoice_number": "",
            "invoice_date": "   ",
            "net_amount": "1000.00",
            "gross_amount": "1190.00",
            "vat_amount": "190.00",
            "sender_company": "Test GmbH",
            "recipient_company": "Empfaenger AG",
        }
        score, sub_scores = service._calculate_field_completeness(
            "invoice", extracted_data
        )

        assert sub_scores["invoice_number"] == 0.0
        assert sub_scores["invoice_date"] == 0.0
        assert sub_scores["net_amount"] == 1.0
        assert score == 5.0 / 7.0


# ========================= Processing Status =========================


class TestProcessingStatus:
    """Tests fuer die Verarbeitungs-Status Berechnung."""

    def test_processing_status_all_complete(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Vollstaendig verarbeitetes Dokument ergibt Score 1.0."""
        mock_doc = _make_mock_document(
            status="completed",
            document_type="invoice",
            extracted_data={"category": "eingangsrechnung"},
        )

        score, sub_scores = service._calculate_processing_status(mock_doc)

        assert score == 1.0
        assert sub_scores["ocr_completed"] == 1.0
        assert sub_scores["categorized"] == 1.0
        assert sub_scores["classified"] == 1.0

    def test_processing_status_partial(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Teilweise verarbeitetes Dokument ergibt niedrigeren Score."""
        mock_doc = _make_mock_document(
            status="completed",
            document_type="invoice",
            extracted_data={},  # keine Kategorie
        )

        score, sub_scores = service._calculate_processing_status(mock_doc)

        assert sub_scores["ocr_completed"] == 1.0
        assert sub_scores["categorized"] == 0.0
        assert sub_scores["classified"] == 1.0
        assert abs(score - (2.0 / 3.0)) < 0.01

    def test_processing_status_not_completed(
        self, service: DocumentQualityScoreService
    ) -> None:
        """Nicht abgeschlossenes OCR ergibt 0.0 fuer ocr_completed."""
        mock_doc = _make_mock_document(
            status="pending",
            document_type="other",
            extracted_data={},
        )

        score, sub_scores = service._calculate_processing_status(mock_doc)

        assert sub_scores["ocr_completed"] == 0.0
        assert sub_scores["classified"] == 0.0  # "other" zaehlt nicht
        assert score < 0.50


# ========================= Company Quality Overview =========================


class TestCompanyQualityOverview:
    """Tests fuer get_company_quality_overview."""

    @pytest.mark.asyncio
    async def test_company_quality_overview_empty(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Leere Uebersicht bei total_documents=0."""
        # Mock: SELECT count, avg -> (0, None)
        mock_row = Mock()
        mock_row.total = 0
        mock_row.avg_confidence = None
        mock_result = Mock()
        mock_result.one.return_value = mock_row
        mock_session.execute.return_value = mock_result

        result = await service.get_company_quality_overview(
            str(TEST_COMPANY_UUID), mock_session
        )

        assert isinstance(result, CompanyQualityOverview)
        assert result.total_documents == 0
        assert result.average_score == 0.0
        assert result.gruen_count == 0
        assert result.gelb_count == 0
        assert result.rot_count == 0

    @pytest.mark.asyncio
    async def test_company_quality_overview_with_documents(
        self, service: DocumentQualityScoreService, mock_session: AsyncMock
    ) -> None:
        """Uebersicht mit Dokumenten berechnet korrekte Verteilung."""
        # Mock aggregate query
        mock_row = Mock()
        mock_row.total = 100
        mock_row.avg_confidence = 0.82
        mock_agg_result = Mock()
        mock_agg_result.one.return_value = mock_row

        # Mock count queries (gruen, gelb)
        mock_gruen_result = Mock()
        mock_gruen_result.scalar.return_value = 60
        mock_gelb_result = Mock()
        mock_gelb_result.scalar.return_value = 30

        # execute is called 3 times: aggregate, gruen count, gelb count
        mock_session.execute.side_effect = [
            mock_agg_result,
            mock_gruen_result,
            mock_gelb_result,
        ]

        result = await service.get_company_quality_overview(
            str(TEST_COMPANY_UUID), mock_session
        )

        assert result.total_documents == 100
        assert result.average_score == 0.82
        assert result.gruen_count == 60
        assert result.gelb_count == 30
        assert result.rot_count == 10  # 100 - 60 - 30
        assert result.gruen_percent == 60.0
        assert result.gelb_percent == 30.0
        assert result.rot_percent == 10.0


# ========================= to_dict Tests =========================


class TestToDict:
    """Tests fuer die to_dict Serialisierung."""

    def test_document_quality_score_to_dict(self) -> None:
        """DocumentQualityScore.to_dict() liefert korrektes Format."""
        quality = DocumentQualityScore(
            document_id=str(TEST_DOC_UUID),
            score=0.8532,
            ampel_color=AmpelColor.GRUEN,
            ampel_label="Vollstaendig und vertrauenswuerdig",
            dimensions=[
                QualityDimension(
                    name="OCR-Konfidenz",
                    score=0.92345,
                    weight=0.40,
                    details="Gute OCR-Qualitaet",
                    sub_scores={"raw_confidence": 0.92345},
                ),
            ],
            recommendations=["Test-Empfehlung"],
        )

        result = quality.to_dict()

        assert result["document_id"] == str(TEST_DOC_UUID)
        assert result["score"] == 0.8532  # rounded to 4 decimal places
        assert result["ampel_color"] == "gruen"
        assert result["ampel_label"] == "Vollstaendig und vertrauenswuerdig"
        assert len(result["dimensions"]) == 1
        assert result["dimensions"][0]["score"] == round(0.92345, 4)
        assert result["dimensions"][0]["sub_scores"]["raw_confidence"] == round(0.92345, 4)
        assert result["recommendations"] == ["Test-Empfehlung"]

    def test_company_quality_overview_to_dict(self) -> None:
        """CompanyQualityOverview.to_dict() liefert korrektes Format."""
        overview = CompanyQualityOverview(
            total_documents=50,
            average_score=0.78123,
            gruen_count=30,
            gelb_count=15,
            rot_count=5,
            gruen_percent=60.0,
            gelb_percent=30.0,
            rot_percent=10.0,
        )

        result = overview.to_dict()

        assert result["total_documents"] == 50
        assert result["average_score"] == 0.7812  # rounded
        assert result["verteilung"]["gruen"]["anzahl"] == 30
        assert result["verteilung"]["gruen"]["prozent"] == 60.0
        assert result["verteilung"]["gelb"]["anzahl"] == 15
        assert result["verteilung"]["rot"]["anzahl"] == 5


# ========================= Required Fields Constant =========================


class TestRequiredFields:
    """Tests fuer die REQUIRED_FIELDS Konfiguration."""

    def test_invoice_required_fields(self) -> None:
        """Invoice hat 7 Pflichtfelder."""
        assert len(REQUIRED_FIELDS["invoice"]) == 7
        assert "invoice_number" in REQUIRED_FIELDS["invoice"]
        assert "gross_amount" in REQUIRED_FIELDS["invoice"]

    def test_order_required_fields(self) -> None:
        """Order hat 4 Pflichtfelder."""
        assert len(REQUIRED_FIELDS["order"]) == 4
        assert "order_number" in REQUIRED_FIELDS["order"]

    def test_default_required_fields(self) -> None:
        """Default hat 2 Pflichtfelder."""
        assert len(REQUIRED_FIELDS["default"]) == 2
        assert "document_date" in REQUIRED_FIELDS["default"]
        assert "sender" in REQUIRED_FIELDS["default"]
