# -*- coding: utf-8 -*-
"""
Unit tests for SmartTaggingService.

Vision 2026+ Feature #5: Smart Auto-Tagging
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.smart_tagging_service import (
    SmartTaggingService,
    SmartTag,
    SmartTaggingResult,
    TagCategory,
    SMART_TAG_DEFINITIONS,
    get_smart_tagging_service,
)


class TestSmartTaggingService:
    """Tests fuer SmartTaggingService."""

    @pytest.fixture
    def service(self) -> SmartTaggingService:
        """Gibt eine Service-Instanz zurueck."""
        return SmartTaggingService()

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        """Erstellt ein Mock-Dokument."""
        doc = MagicMock()
        doc.id = uuid.uuid4()
        doc.extracted_text = "Dies ist ein Testdokument."
        doc.ocr_confidence = 0.92
        doc.checksum = "abc123"
        doc.business_entity_id = None
        doc.tags = []
        return doc

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt eine Mock-DB-Session."""
        db = AsyncMock()
        # Mock execute to return empty results by default
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        db.execute.return_value = mock_result
        return db

    # -------------------------------------------------------------------------
    # Basic Tests
    # -------------------------------------------------------------------------

    def test_service_initialization(self, service: SmartTaggingService) -> None:
        """Service sollte korrekt initialisiert werden."""
        assert service is not None
        assert len(service._tag_definitions) == len(SMART_TAG_DEFINITIONS)

    def test_get_available_smart_tags(self, service: SmartTaggingService) -> None:
        """Sollte alle verfuegbaren Smart Tag Definitionen zurueckgeben."""
        tags = service.get_available_smart_tags()
        assert len(tags) > 0
        assert all("name" in t and "category" in t for t in tags)

    def test_singleton_pattern(self) -> None:
        """Singleton Pattern sollte funktionieren."""
        service1 = get_smart_tagging_service()
        service2 = get_smart_tagging_service()
        assert service1 is service2

    # -------------------------------------------------------------------------
    # Urgency Analysis Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_urgency_keywords_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Dringlichkeits-Keywords erkennen."""
        mock_document.extracted_text = "DRINGEND! Diese Rechnung muss sofort bezahlt werden."

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        urgency_tags = [t for t in result.suggested_tags if t.category == TagCategory.URGENCY]
        assert len(urgency_tags) > 0
        assert any(t.name == "dringend" for t in urgency_tags)

    @pytest.mark.asyncio
    async def test_overdue_invoice_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte ueberfaellige Rechnungen erkennen."""
        # Mock InvoiceTracking mit ueberfaelligem due_date
        mock_invoice = MagicMock()
        mock_invoice.due_date = (datetime.now(timezone.utc) - timedelta(days=10)).date()
        mock_invoice.skonto_deadline = None
        mock_invoice.skonto_used = False
        mock_invoice.amount = Decimal("100.00")
        mock_invoice.status = "overdue"
        mock_invoice.dunning_level = 1
        mock_invoice.invoice_date = (datetime.now(timezone.utc) - timedelta(days=40)).date()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        assert any(t.name == "überfällig" for t in result.suggested_tags)

    # -------------------------------------------------------------------------
    # Financial Analysis Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_skonto_detection_in_text(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Skonto-Bedingungen im Text erkennen."""
        mock_document.extracted_text = "Bei Zahlung binnen 14 Tagen gewähren wir 2% Skonto."

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        financial_tags = [t for t in result.suggested_tags if t.category == TagCategory.FINANCIAL]
        assert any(t.name == "skonto-möglich" for t in financial_tags)

    @pytest.mark.asyncio
    async def test_high_amount_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte hohe Betraege erkennen."""
        # Mock InvoiceTracking mit hohem Betrag
        mock_invoice = MagicMock()
        mock_invoice.due_date = None
        mock_invoice.skonto_deadline = None
        mock_invoice.skonto_used = False
        mock_invoice.amount = Decimal("10000.00")  # Ueber 5000 EUR Schwellwert
        mock_invoice.status = "open"
        mock_invoice.dunning_level = 0
        mock_invoice.invoice_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        assert any(t.name == "hoher-betrag" for t in result.suggested_tags)

    @pytest.mark.asyncio
    async def test_high_amount_detection_from_text(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte hohe Betraege aus Text erkennen."""
        mock_document.extracted_text = "Gesamtsumme: 7.500,00 € inkl. MwSt."

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        financial_tags = [t for t in result.suggested_tags if t.category == TagCategory.FINANCIAL]
        assert any(t.name == "hoher-betrag" for t in financial_tags)

    # -------------------------------------------------------------------------
    # Quality Analysis Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_low_ocr_confidence_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte niedrige OCR-Konfidenz erkennen."""
        mock_document.ocr_confidence = 0.65  # Unter 0.75 Schwellwert

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        quality_tags = [t for t in result.suggested_tags if t.category == TagCategory.QUALITY]
        assert any(t.name == "ocr-unsicher" for t in quality_tags)

    @pytest.mark.asyncio
    async def test_duplicate_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte moegliche Duplikate erkennen."""
        # Mock: Es gibt 2 Dokumente mit gleichem Checksum
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 2  # 2 Duplikate gefunden
        mock_db.execute.return_value = mock_result

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        quality_tags = [t for t in result.suggested_tags if t.category == TagCategory.QUALITY]
        assert any(t.name == "duplikat-möglich" for t in quality_tags)

    @pytest.mark.asyncio
    async def test_incomplete_invoice_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte unvollstaendige Rechnungen erkennen (fehlende Pflichtfelder)."""
        # Rechnung ohne USt-IdNr, Bankverbindung oder Rechnungsnummer
        mock_document.extracted_text = """
        Rechnung
        Musterfirma GmbH
        Musterstraße 1
        12345 Musterstadt

        Artikel     Menge   Preis
        Widget X    10      100,00 €
        Widget Y    5       50,00 €

        Gesamtsumme: 150,00 €
        """

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        quality_tags = [t for t in result.suggested_tags if t.category == TagCategory.QUALITY]
        assert any(t.name == "unvollständig" for t in quality_tags)

    # -------------------------------------------------------------------------
    # Action Analysis Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_approval_required_for_high_amount(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Genehmigung fuer hohe Betraege vorschlagen."""
        mock_invoice = MagicMock()
        mock_invoice.due_date = None
        mock_invoice.skonto_deadline = None
        mock_invoice.skonto_used = False
        mock_invoice.amount = Decimal("3000.00")  # Ueber 2500 EUR
        mock_invoice.status = "open"
        mock_invoice.dunning_level = 0
        mock_invoice.invoice_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        action_tags = [t for t in result.suggested_tags if t.category == TagCategory.ACTION]
        assert any(t.name == "genehmigung-erforderlich" for t in action_tags)

    @pytest.mark.asyncio
    async def test_dunning_required_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte faellige Mahnungen erkennen."""
        mock_invoice = MagicMock()
        mock_invoice.due_date = (datetime.now(timezone.utc) - timedelta(days=20)).date()
        mock_invoice.skonto_deadline = None
        mock_invoice.skonto_used = False
        mock_invoice.amount = Decimal("500.00")
        mock_invoice.status = "overdue"
        mock_invoice.dunning_level = 1  # Noch nicht letzte Mahnstufe
        mock_invoice.invoice_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        action_tags = [t for t in result.suggested_tags if t.category == TagCategory.ACTION]
        assert any(t.name == "mahnung-fällig" for t in action_tags)

    # -------------------------------------------------------------------------
    # Trust Analysis Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_high_risk_entity_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Risiko-Partner erkennen."""
        mock_document.business_entity_id = uuid.uuid4()

        mock_entity = MagicMock()
        mock_entity.risk_score = 85  # Ueber 75 Schwellwert
        mock_entity.first_document_date = (datetime.now(timezone.utc) - timedelta(days=200)).date()
        mock_entity.verified = False
        mock_entity.document_count = 5

        # Setup mock to return entity
        def execute_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            # Check if it's an entity query by looking at the query text
            query = str(args[0]) if args else ""
            if "business_entities" in query.lower():
                mock_result.scalar_one_or_none.return_value = mock_entity
            else:
                mock_result.scalar_one_or_none.return_value = None
            mock_result.scalar.return_value = 0
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        trust_tags = [t for t in result.suggested_tags if t.category == TagCategory.TRUST]
        assert any(t.name == "risiko-partner" for t in trust_tags)

    @pytest.mark.asyncio
    async def test_new_supplier_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte neue Lieferanten erkennen."""
        mock_document.business_entity_id = uuid.uuid4()

        mock_entity = MagicMock()
        mock_entity.risk_score = 30
        mock_entity.first_document_date = (datetime.now(timezone.utc) - timedelta(days=30)).date()  # Neu
        mock_entity.verified = False
        mock_entity.document_count = 2

        def execute_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            query = str(args[0]) if args else ""
            if "business_entities" in query.lower():
                mock_result.scalar_one_or_none.return_value = mock_entity
            else:
                mock_result.scalar_one_or_none.return_value = None
            mock_result.scalar.return_value = 0
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        trust_tags = [t for t in result.suggested_tags if t.category == TagCategory.TRUST]
        assert any(t.name == "neuer-lieferant" for t in trust_tags)

    @pytest.mark.asyncio
    async def test_known_partner_detection(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte bekannte Partner erkennen."""
        mock_document.business_entity_id = uuid.uuid4()

        mock_entity = MagicMock()
        mock_entity.risk_score = 20
        mock_entity.first_document_date = (datetime.now(timezone.utc) - timedelta(days=365)).date()
        mock_entity.verified = True  # Verifiziert
        mock_entity.document_count = 50  # Viele Dokumente

        def execute_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            query = str(args[0]) if args else ""
            if "business_entities" in query.lower():
                mock_result.scalar_one_or_none.return_value = mock_entity
            else:
                mock_result.scalar_one_or_none.return_value = None
            mock_result.scalar.return_value = 0
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        trust_tags = [t for t in result.suggested_tags if t.category == TagCategory.TRUST]
        assert any(t.name == "bekannter-partner" for t in trust_tags)

    # -------------------------------------------------------------------------
    # Tag Application Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_auto_apply_with_high_confidence(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Tags mit hoher Konfidenz automatisch anwenden."""
        mock_document.extracted_text = "DRINGEND! Zahlungserinnerung"
        mock_document.tags = []

        # Mock Tag creation
        mock_tag = MagicMock()
        mock_tag.name = "dringend"

        async def mock_flush():
            pass

        async def mock_commit():
            pass

        mock_db.flush = mock_flush
        mock_db.commit = mock_commit
        mock_db.add = MagicMock()

        # First call returns None (no existing tag), subsequent calls return mock_tag
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] <= 2:  # First queries for entity and invoice
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalar.return_value = 0
            else:  # Tag query
                mock_result.scalar_one_or_none.return_value = mock_tag

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=True,
        )

        # Tags sollten vorgeschlagen werden
        assert len(result.suggested_tags) > 0

    @pytest.mark.asyncio
    async def test_no_auto_apply_when_disabled(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte keine Tags anwenden wenn auto_apply=False."""
        mock_document.extracted_text = "DRINGEND! Diese Rechnung ist sofort zu bezahlen!"

        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        assert len(result.applied_tags) == 0
        assert len(result.suggested_tags) > 0

    # -------------------------------------------------------------------------
    # Metadata Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_analysis_metadata_populated(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Analyse-Metadaten korrekt setzen."""
        result = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
        )

        assert "duration_ms" in result.analysis_metadata
        assert "text_length" in result.analysis_metadata
        assert "has_entity" in result.analysis_metadata
        assert "tags_suggested" in result.analysis_metadata

    @pytest.mark.asyncio
    async def test_confidence_filtering(
        self, service: SmartTaggingService, mock_db: AsyncMock, mock_document: MagicMock
    ) -> None:
        """Sollte Tags unter min_confidence filtern."""
        mock_document.extracted_text = "Ein normaler Text ohne besondere Merkmale."

        result_low = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
            min_confidence=0.1,
        )

        result_high = await service.analyze_document(
            db=mock_db,
            document=mock_document,
            auto_apply=False,
            min_confidence=0.99,
        )

        # Mit hohem min_confidence sollten weniger Tags vorgeschlagen werden
        assert len(result_high.suggested_tags) <= len(result_low.suggested_tags)
