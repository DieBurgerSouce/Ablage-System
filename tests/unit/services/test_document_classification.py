# -*- coding: utf-8 -*-
"""
Unit Tests fuer DocumentClassificationService.

Testet die Keyword-basierte Klassifizierung von Dokumenten:
- Rechnungen
- Bestellungen
- Vertraege
- Lieferscheine
- Quittungen
"""

import pytest
from app.services.document_classification_service import (
    DocumentClassificationService,
    get_classification_service,
)
from app.api.schemas.extracted_data import ExtractedDocumentType


class TestDocumentClassificationService:
    """Tests fuer DocumentClassificationService."""

    @pytest.fixture
    def service(self) -> DocumentClassificationService:
        """Erstellt eine frische Service-Instanz."""
        return DocumentClassificationService()

    # =========================================================================
    # RECHNUNGEN
    # =========================================================================

    def test_classify_invoice_basic(self, service: DocumentClassificationService) -> None:
        """Einfache Rechnung erkennen."""
        text = """
        Rechnung Nr. RE-2024-00123
        Rechnungsdatum: 15.01.2024

        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR

        Zahlungsziel: 30 Tage netto
        IBAN: DE89370400440532013000
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.INVOICE
        assert result.confidence >= 0.7
        assert "rechnung" in [k.lower() for k in result.matched_keywords]

    def test_classify_invoice_with_skonto(self, service: DocumentClassificationService) -> None:
        """Rechnung mit Skonto-Bedingungen erkennen."""
        text = """
        RECHNUNG
        Rechnungsnummer: 2024/1234

        Gesamtbetrag: 2.380,00 EUR

        Zahlungsbedingungen:
        2% Skonto bei Zahlung innerhalb 10 Tagen
        30 Tage netto

        Bankverbindung:
        IBAN: DE89370400440532013000
        BIC: COBADEFFXXX
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.INVOICE
        assert result.confidence >= 0.8
        assert "skonto" in [k.lower() for k in result.matched_keywords]

    def test_classify_invoice_english_keywords(self, service: DocumentClassificationService) -> None:
        """Rechnung mit englischen Keywords erkennen."""
        text = """
        Invoice No. INV-2024-001
        Invoice Date: 2024-01-15

        Total Amount: 1,190.00 EUR
        VAT 19%: 190.00 EUR

        Payment terms: Net 30
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.INVOICE
        assert result.confidence >= 0.5

    # =========================================================================
    # BESTELLUNGEN
    # =========================================================================

    def test_classify_order_basic(self, service: DocumentClassificationService) -> None:
        """Einfache Bestellung erkennen."""
        text = """
        Bestellung
        Bestell-Nr.: BEST-2024-001
        Bestelldatum: 10.01.2024

        Liefertermin: 01.02.2024
        Lieferadresse: Musterstrasse 123, 12345 Berlin

        Position 1: Artikel A - 10 Stueck - 50,00 EUR
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.ORDER
        assert result.confidence >= 0.7
        assert "bestellung" in [k.lower() for k in result.matched_keywords]

    def test_classify_order_confirmation(self, service: DocumentClassificationService) -> None:
        """Auftragsbestaetigung erkennen."""
        text = """
        AUFTRAGSBESTAETIGUNG
        Auftragsnummer: AB-2024-5678

        Vielen Dank fuer Ihre Bestellung.

        Liefertermin: 15.02.2024
        Versand: DHL Express
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.ORDER
        assert result.confidence >= 0.6

    # =========================================================================
    # VERTRAEGE
    # =========================================================================

    def test_classify_contract_basic(self, service: DocumentClassificationService) -> None:
        """Einfachen Vertrag erkennen."""
        text = """
        DIENSTLEISTUNGSVERTRAG
        Vertragsnummer: VTR-2024-001

        Zwischen
        Firma A GmbH (Auftraggeber)
        und
        Firma B AG (Auftragnehmer)

        Laufzeit: 12 Monate
        Kuendigungsfrist: 3 Monate zum Quartalsende
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.CONTRACT
        assert result.confidence >= 0.7
        assert "vertrag" in [k.lower() for k in result.matched_keywords]

    def test_classify_rental_contract(self, service: DocumentClassificationService) -> None:
        """Mietvertrag erkennen."""
        text = """
        Mietvertrag

        Vertragsparteien:
        Vermieter: Max Mustermann
        Mieter: Erika Musterfrau

        Vertragslaufzeit: unbefristet
        Kuendigungsfrist: 3 Monate
        Monatliche Miete: 1.200,00 EUR
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.CONTRACT
        assert result.confidence >= 0.6

    # =========================================================================
    # LIEFERSCHEINE
    # =========================================================================

    def test_classify_delivery_note(self, service: DocumentClassificationService) -> None:
        """Lieferschein erkennen."""
        text = """
        LIEFERSCHEIN
        Lieferschein-Nr.: LS-2024-789

        Empfaenger:
        Kunde GmbH
        Kundenweg 45
        54321 Muenchen

        Anzahl Pakete: 3
        Gesamtgewicht: 15,5 kg
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.DELIVERY_NOTE
        assert result.confidence >= 0.6
        assert "lieferschein" in [k.lower() for k in result.matched_keywords]

    # =========================================================================
    # QUITTUNGEN
    # =========================================================================

    def test_classify_receipt(self, service: DocumentClassificationService) -> None:
        """Quittung erkennen."""
        text = """
        QUITTUNG

        Betrag erhalten: 50,00 EUR
        Zahlungsart: Bar

        Datum: 15.01.2024
        Kassierer: M. Mueller
        """
        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.RECEIPT
        assert result.confidence >= 0.5

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_classify_empty_text(self, service: DocumentClassificationService) -> None:
        """Leerer Text sollte UNKNOWN zurueckgeben."""
        result = service.classify("")

        assert result.document_type == ExtractedDocumentType.UNKNOWN
        assert result.confidence == 0.0
        assert result.matched_keywords == []

    def test_classify_unknown_document(self, service: DocumentClassificationService) -> None:
        """Unbekanntes Dokument sollte UNKNOWN zurueckgeben."""
        text = "Dies ist ein einfacher Text ohne spezielle Keywords."

        result = service.classify(text)

        assert result.document_type == ExtractedDocumentType.UNKNOWN
        assert result.confidence < 0.3

    def test_classify_ambiguous_document(self, service: DocumentClassificationService) -> None:
        """Dokument mit mehreren Typen sollte Alternative liefern."""
        text = """
        Rechnung zur Bestellung
        Rechnungsnummer: RE-2024-001
        Bestellnummer: BEST-2024-001
        """
        result = service.classify(text)

        # Sollte entweder Invoice oder Order sein
        assert result.document_type in [ExtractedDocumentType.INVOICE, ExtractedDocumentType.ORDER]
        # Sollte Alternative haben
        if result.alternative_type:
            assert result.alternative_type != result.document_type

    # =========================================================================
    # STATISTIKEN
    # =========================================================================

    def test_get_stats(self, service: DocumentClassificationService) -> None:
        """Statistiken abfragen."""
        # Einige Klassifizierungen durchfuehren
        service.classify("Rechnung Nr. 123")
        service.classify("Bestellung Nr. 456")
        service.classify("Rechnung Nr. 789")

        stats = service.get_stats()

        assert stats["total_classifications"] == 3
        assert stats["by_type"]["invoice"] >= 1
        assert stats["by_type"]["order"] >= 0

    def test_reset_stats(self, service: DocumentClassificationService) -> None:
        """Statistiken zuruecksetzen."""
        service.classify("Rechnung Nr. 123")
        service.reset_stats()

        stats = service.get_stats()

        assert stats["total_classifications"] == 0

    # =========================================================================
    # BATCH-VERARBEITUNG
    # =========================================================================

    def test_classify_batch(self, service: DocumentClassificationService) -> None:
        """Mehrere Dokumente gleichzeitig klassifizieren."""
        texts = [
            "Rechnung Nr. RE-2024-001",
            "Bestellung Nr. BEST-2024-002",
            "Vertrag Nr. VTR-2024-003",
        ]

        results = service.classify_batch(texts)

        assert len(results) == 3
        assert results[0].document_type == ExtractedDocumentType.INVOICE
        assert results[1].document_type == ExtractedDocumentType.ORDER
        assert results[2].document_type == ExtractedDocumentType.CONTRACT


class TestGetClassificationServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_returns_same_instance(self) -> None:
        """Singleton sollte immer dieselbe Instanz zurueckgeben."""
        service1 = get_classification_service()
        service2 = get_classification_service()

        assert service1 is service2
