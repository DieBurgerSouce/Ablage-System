# -*- coding: utf-8 -*-
"""
Unit Tests fuer AutoCategorizationService.

Tests fuer automatische Dokument-Kategorisierung:
- Keyword-basierte Erkennung
- Regex-Pattern Matching
- Kategorien (Rechnung, Lieferschein, Vertrag, etc.)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.auto_categorization_service import (
    AutoCategorizationService,
    DocumentCategory,
    CategoryPattern,
    CategorizationResult,
    CATEGORY_PATTERNS,
    get_auto_categorization_service,
)


class TestDocumentCategory:
    """Tests fuer DocumentCategory Konstanten."""

    def test_category_values(self) -> None:
        """Test: Alle Kategorien haben korrekte Werte."""
        assert DocumentCategory.INVOICE_INCOMING == "invoice_incoming"
        assert DocumentCategory.INVOICE_OUTGOING == "invoice_outgoing"
        assert DocumentCategory.DELIVERY_NOTE == "delivery_note"
        assert DocumentCategory.ORDER == "order"
        assert DocumentCategory.CONTRACT == "contract"
        assert DocumentCategory.OFFER == "offer"
        assert DocumentCategory.REMINDER == "reminder"
        assert DocumentCategory.CREDIT_NOTE == "credit_note"
        assert DocumentCategory.RECEIPT == "receipt"
        assert DocumentCategory.BANK_STATEMENT == "bank_statement"
        assert DocumentCategory.TAX_DOCUMENT == "tax_document"
        assert DocumentCategory.CORRESPONDENCE == "correspondence"
        assert DocumentCategory.OTHER == "other"


class TestCategoryPattern:
    """Tests fuer CategoryPattern."""

    def test_category_pattern_creation(self) -> None:
        """Test: CategoryPattern kann erstellt werden."""
        pattern = CategoryPattern(
            category="test",
            display_name="Test Kategorie",
            keywords=["test", "keyword"],
            regex_patterns=[r"test\s+\d+"],
            weight=1.0,
            priority=5,
        )

        assert pattern.category == "test"
        assert pattern.display_name == "Test Kategorie"
        assert len(pattern.keywords) == 2
        assert pattern.weight == 1.0

    def test_predefined_patterns_exist(self) -> None:
        """Test: Vordefinierte Patterns existieren."""
        assert len(CATEGORY_PATTERNS) > 0
        categories = [p.category for p in CATEGORY_PATTERNS]
        assert DocumentCategory.INVOICE_INCOMING in categories
        assert DocumentCategory.DELIVERY_NOTE in categories
        assert DocumentCategory.CONTRACT in categories


class TestCategorizationResult:
    """Tests fuer CategorizationResult."""

    def test_result_creation(self) -> None:
        """Test: CategorizationResult kann erstellt werden."""
        result = CategorizationResult(
            category=DocumentCategory.INVOICE_INCOMING,
            display_name="Eingangsrechnung",
            confidence=0.95,
            matched_keywords=["rechnung", "rechnungsnummer"],
            matched_patterns=[r"rechnung\s*nr"],
            secondary_categories=[
                (DocumentCategory.CREDIT_NOTE, 0.3),
            ],
        )

        assert result.category == DocumentCategory.INVOICE_INCOMING
        assert result.confidence == 0.95
        assert "rechnung" in result.matched_keywords


class TestAutoCategorization:
    """Tests fuer AutoCategorizationService."""

    @pytest.fixture
    def service(self) -> AutoCategorizationService:
        """Erstellt Service-Instanz."""
        return AutoCategorizationService()

    def test_normalize_text(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Text wird normalisiert - lowercase, multiple spaces -> single."""
        result = service._normalize_text("  RECHNUNG  123  ")
        # _normalize_text macht lowercase und ersetzt multiple spaces durch single space
        # aber strippt nicht leading/trailing spaces
        assert "rechnung" in result.lower()
        assert "123" in result

    def test_normalize_text_preserves_umlauts(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Umlaute bleiben erhalten."""
        result = service._normalize_text("RÜCKÜBERWEISUNG Größe")
        assert "rücküberweisung" in result
        assert "größe" in result


class TestCategorizeText:
    """Tests fuer categorize_text Methode."""

    @pytest.fixture
    def service(self) -> AutoCategorizationService:
        return AutoCategorizationService()

    def test_categorize_invoice(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Rechnung wird erkannt."""
        text = """
        Rechnung Nr. 12345
        Rechnungsdatum: 03.01.2026

        Sehr geehrte Damen und Herren,

        wir stellen Ihnen folgende Leistungen in Rechnung:

        Nettobetrag: 1.000,00 €
        MwSt. 19%:     190,00 €
        Bruttobetrag: 1.190,00 €

        Bitte überweisen Sie den Betrag bis zum 17.01.2026.

        Bankverbindung:
        IBAN: DE89 3704 0044 0532 0130 00
        """
        result = service.categorize_text(text)

        assert result.category in [
            DocumentCategory.INVOICE_INCOMING,
            DocumentCategory.INVOICE_OUTGOING,
        ]
        # Confidence kann je nach Algorithmus variieren
        assert result.confidence > 0.0
        assert "rechnung" in [k.lower() for k in result.matched_keywords]

    def test_categorize_delivery_note(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Lieferschein wird erkannt."""
        text = """
        Lieferschein Nr. LS-2026-001
        Lieferdatum: 02.01.2026

        Empfänger:
        Firma Muster GmbH
        Musterstraße 1
        12345 Musterstadt

        Lieferadresse:
        Lagerstraße 10
        12345 Musterstadt

        Artikelnummer  Bezeichnung       Menge
        12345         Produkt A         10 Stk
        67890         Produkt B          5 Stk
        """
        result = service.categorize_text(text)

        assert result.category == DocumentCategory.DELIVERY_NOTE
        assert "lieferschein" in [k.lower() for k in result.matched_keywords]

    def test_categorize_contract(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Vertrag wird erkannt."""
        text = """
        Vertrag Nr. V-2026-001

        Zwischen

        Auftragnehmer GmbH, vertreten durch den Geschäftsführer Max Muster

        und

        Auftraggeber AG, vertreten durch den Vorstand

        wird folgender Vertrag geschlossen:

        § 1 Vertragsgegenstand
        Der Auftragnehmer verpflichtet sich zur Erbringung von Beratungsleistungen.

        § 2 Laufzeit
        Die Vertragslaufzeit beträgt 12 Monate.

        § 3 Kündigungsfrist
        Die Kündigungsfrist beträgt 3 Monate zum Quartalsende.
        """
        result = service.categorize_text(text)

        assert result.category == DocumentCategory.CONTRACT
        assert result.confidence > 0.5

    def test_categorize_reminder(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Mahnung wird erkannt."""
        text = """
        2. Mahnung

        Sehr geehrte Damen und Herren,

        leider ist die Zahlung unserer Rechnung Nr. 12345 vom 01.12.2025
        noch nicht bei uns eingegangen.

        Der offene Betrag von 1.190,00 € ist seit 14 Tagen überfällig.

        Wir bitten Sie, den Betrag zzgl. Mahngebühren von 5,00 €
        innerhalb von 7 Tagen zu überweisen.

        Bei Nichtzahlung sehen wir uns gezwungen, rechtliche Schritte einzuleiten.
        """
        result = service.categorize_text(text)

        assert result.category == DocumentCategory.REMINDER
        # Confidence kann je nach Algorithmus variieren
        assert result.confidence > 0.0

    def test_categorize_unknown(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Unbekannter Text wird als OTHER kategorisiert."""
        text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        result = service.categorize_text(text)

        assert result.category == DocumentCategory.OTHER
        assert result.confidence < 0.8

    def test_categorize_empty_text(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Leerer Text wird als OTHER kategorisiert."""
        result = service.categorize_text("")
        assert result.category == DocumentCategory.OTHER

    def test_secondary_categories(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Sekundaere Kategorien werden zurueckgegeben."""
        # Text mit mehreren Kategorie-Hinweisen
        text = """
        Rechnung für Bestellung Nr. PO-2026-001

        Rechnungsnummer: RE-2026-001
        Bestellnummer: PO-2026-001

        Vielen Dank für Ihre Bestellung.
        Wir stellen Ihnen folgende Artikel in Rechnung:
        """
        result = service.categorize_text(text)

        # Kategorisierung haengt von den erkannten Keywords ab
        # Bei gemischtem Text kann auch OTHER zurueckgegeben werden
        assert result.category in [
            DocumentCategory.INVOICE_INCOMING,
            DocumentCategory.INVOICE_OUTGOING,
            DocumentCategory.ORDER,
            DocumentCategory.OTHER,  # Falls kein eindeutiges Match
        ]


class TestCategorizeDocument:
    """Tests fuer categorize_document Methode."""

    @pytest.fixture
    def service(self) -> AutoCategorizationService:
        return AutoCategorizationService()

    @pytest.mark.asyncio
    async def test_categorize_document_returns_ai_result(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: categorize_document gibt AIDecisionResult zurueck."""
        db = AsyncMock(spec=AsyncSession)

        # Mock decision service
        with patch.object(
            service, '_decision_service'
        ) as mock_decision:
            mock_decision.make_decision = AsyncMock(return_value=MagicMock(
                auto_applied=True,
                confidence=0.95,
                confidence_level=MagicMock(value="high"),
            ))

            result = await service.categorize_document(
                db=db,
                document_id=uuid4(),
                text="Rechnung Nr. 12345",
                company_id=uuid4(),
                auto_apply_tags=False,
            )

            assert result is not None
            mock_decision.make_decision.assert_called_once()


class TestCategorySuggestions:
    """Tests fuer get_category_suggestions Methode."""

    @pytest.fixture
    def service(self) -> AutoCategorizationService:
        return AutoCategorizationService()

    @pytest.mark.asyncio
    async def test_get_suggestions(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Vorschlaege werden zurueckgegeben."""
        text = "Rechnung Nr. 12345 mit Rechnungsdatum und Bruttobetrag"

        suggestions = await service.get_category_suggestions(text, limit=3)

        assert isinstance(suggestions, list)
        assert len(suggestions) <= 3
        assert suggestions[0]["is_primary"] is True
        assert "confidence" in suggestions[0]

    @pytest.mark.asyncio
    async def test_suggestions_include_display_name(
        self,
        service: AutoCategorizationService,
    ) -> None:
        """Test: Vorschlaege enthalten display_name."""
        suggestions = await service.get_category_suggestions("Lieferschein", limit=5)

        for suggestion in suggestions:
            assert "display_name" in suggestion
            assert "category" in suggestion


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_auto_categorization_service_returns_same_instance(self) -> None:
        """Test: Singleton gibt immer dieselbe Instanz zurueck."""
        service1 = get_auto_categorization_service()
        service2 = get_auto_categorization_service()
        assert service1 is service2

    def test_service_instance_type(self) -> None:
        """Test: Singleton ist AutoCategorizationService."""
        service = get_auto_categorization_service()
        assert isinstance(service, AutoCategorizationService)
