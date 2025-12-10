# -*- coding: utf-8 -*-
"""
Structured Extraction Service.

Haupt-Orchestrierung fuer strukturierte Datenextraktion:
- Klassifizierung
- Typspezifische Extraktion (Invoice, Order, Contract)
- Plausibilitaetspruefung

Performance: < 200ms pro Dokument (ohne OCR)

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

import re
import structlog
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.api.schemas.extracted_data import (
    Currency,
    DocumentClassificationResult,
    ExtractedAddress,
    ExtractedBankAccount,
    ExtractedContractData,
    ExtractedDocumentData,
    ExtractedDocumentType,
    ExtractedInvoiceData,
    ExtractedLineItem,
    ExtractedOrderData,
)
from app.services.document_classification_service import (
    DocumentClassificationService,
    get_classification_service,
)
from app.services.entity_extraction_service import EntityExtractionService
from app.services.translation_service import (
    TranslationService,
    get_translation_service,
)

# Lazy import fuer LineItem-Extraktion (vermeidet zirkulaere Imports)
_line_item_service_class = None
_line_item_service_instance = None

logger = structlog.get_logger(__name__)


def _get_line_item_service():
    """Lazy-Load des LineItemExtractionService."""
    global _line_item_service_class, _line_item_service_instance
    if _line_item_service_instance is None:
        if _line_item_service_class is None:
            from app.services.line_item_extraction_service import (
                LineItemExtractionService,
            )
            _line_item_service_class = LineItemExtractionService
        _line_item_service_instance = _line_item_service_class()
    return _line_item_service_instance


# =============================================================================
# REGEX PATTERNS
# =============================================================================

class PaymentPatterns:
    """Patterns fuer Zahlungsbedingungen - KRITISCH fuer Buchhaltung!"""

    # Zahlungsziel: "Zahlbar innerhalb von 30 Tagen" oder "Zahlungsziel: 14 Tage netto"
    PAYMENT_DAYS = re.compile(
        r'(?:zahlbar|zahlungsziel|f[aä]llig|netto)[\s:]*'
        r'(?:innerhalb\s*(?:von\s*)?)?'
        r'(\d{1,3})\s*(?:tage|tagen)',
        re.IGNORECASE
    )

    # Erweitertes Payment Pattern - deckt mehr Varianten ab
    # "NET 30", "net 30 days", "30 Tage netto", "Netto 30", "30T"
    PAYMENT_DAYS_EXTENDED = re.compile(
        r'(?:'
        r'net(?:to)?\s*(\d{1,3})|'               # NET 30, netto 30
        r'(\d{1,3})\s*(?:tage?\s*)?net(?:to)?|'  # 30 Tage netto, 30T netto
        r'(\d{1,3})\s*days?\s*net|'              # 30 days net (englisch)
        r'zahlungsfrist\s*(\d{1,3})|'            # Zahlungsfrist 30
        r'payment\s*(?:within|in)\s*(\d{1,3})'   # payment within 30
        r')',
        re.IGNORECASE
    )

    # Sofortige Zahlung erkennen
    PAYMENT_IMMEDIATE = re.compile(
        r'(?:zahlbar\s*sofort|sofort\s*f[aä]llig|bar\s*bei\s*[uü]bergabe|'
        r'zahlung\s*bei\s*lieferung|vorauskasse|vorkasse|'
        r'due\s*(?:upon|on)\s*receipt)',
        re.IGNORECASE
    )

    # Fälligkeitsdatum direkt: "Fällig am 15.02.2024"
    DUE_DATE_DIRECT = re.compile(
        r'(?:f[aä]llig(?:keit)?|zahlbar\s*bis|zahlungsziel)[\s:]*'
        r'(?:am\s*)?(\d{1,2})\.(\d{1,2})\.(\d{4})',
        re.IGNORECASE
    )

    # Skonto-Prozent: "2% Skonto" oder "Skonto 2,0%"
    SKONTO_PERCENT = re.compile(
        r'(?:(\d{1,2}(?:[,\.]\d{1,2})?)\s*%?\s*(?:skonto|rabatt|nachlass)|'
        r'(?:skonto|rabatt|nachlass)\s*(\d{1,2}(?:[,\.]\d{1,2})?)\s*%)',
        re.IGNORECASE
    )

    # Skonto-Frist: "bei Zahlung innerhalb 10 Tagen"
    SKONTO_DAYS = re.compile(
        r'(?:skonto|rabatt).*?'
        r'(?:innerhalb|binnen)\s*(?:von\s*)?'
        r'(\d{1,3})\s*(?:tage|tagen)',
        re.IGNORECASE
    )

    # Kombiniertes Skonto-Pattern: "2% Skonto 10 Tage, 30 Tage netto"
    SKONTO_FULL = re.compile(
        r'(\d{1,2}(?:[,\.]\d)?)\s*%?\s*(?:skonto|nachlass)'
        r'.*?(\d{1,3})\s*(?:tage|tagen)',
        re.IGNORECASE
    )

    # Skonto-Volltext (fuer early_payment_info)
    SKONTO_FULLTEXT = re.compile(
        r'(\d{1,2}(?:[,\.]\d)?%?\s*(?:skonto|nachlass|rabatt)'
        r'.*?(?:innerhalb|binnen|bei\s*zahlung).*?\d{1,3}\s*tage\w*)',
        re.IGNORECASE
    )

    # Verzugszinsen: "Verzugszinsen 9% über Basiszinssatz"
    LATE_INTEREST = re.compile(
        r'verzugszins(?:en)?[\s:]*'
        r'(\d{1,2}(?:[,\.]\d{1,2})?)\s*%',
        re.IGNORECASE
    )

    # Verzugszinsen Volltext
    LATE_INTEREST_FULLTEXT = re.compile(
        r'(verzugszins(?:en)?.*?(?:basiszins|prozent|p\.?a\.?))',
        re.IGNORECASE
    )

    # Zahlungsart: "Zahlung per Überweisung"
    PAYMENT_METHOD = re.compile(
        r'(?:zahlung|bezahlung)\s*(?:per|via|durch)?\s*'
        r'([uü]berweisung|lastschrift|bar|kreditkarte|paypal|rechnung)',
        re.IGNORECASE
    )


class AmountPatterns:
    """Patterns fuer deutsche Geldbetraege."""

    # Deutsches Format: 1.234,56 EUR oder 1234,56 €
    GERMAN_AMOUNT = re.compile(
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR|Euro)?',
        re.IGNORECASE
    )

    # Nettobetrag mit Label
    NET_AMOUNT = re.compile(
        r'(?:netto(?:betrag)?|zwischensumme|summe\s*netto)[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)?',
        re.IGNORECASE
    )

    # Bruttobetrag mit Label (inkl. Bestellwert, Auftragswert)
    GROSS_AMOUNT = re.compile(
        r'(?:brutto(?:betrag)?|gesamt(?:betrag)?|endbetrag|summe|total|'
        r'zu\s*zahlen(?:der\s*betrag)?|rechnungsbetrag|'
        r'bestell(?:wert|betrag)|auftrags(?:wert|summe)|'
        r'vertrags(?:wert|summe))[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)?',
        re.IGNORECASE
    )

    # MwSt mit Satz und Betrag
    VAT_WITH_RATE = re.compile(
        r'(?:mwst\.?|ust\.?|mehrwertsteuer|umsatzsteuer)\s*'
        r'(\d{1,2})\s*%[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
        re.IGNORECASE
    )

    # MwSt nur Betrag
    VAT_AMOUNT = re.compile(
        r'(?:mwst\.?|ust\.?|mehrwertsteuer)[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
        re.IGNORECASE
    )

    # MwSt-Satz ohne Betrag
    VAT_RATE = re.compile(
        r'(?:mwst\.?|ust\.?|mehrwertsteuer)\s*'
        r'(\d{1,2})\s*%',
        re.IGNORECASE
    )


class ReferencePatterns:
    """Patterns fuer Dokumentreferenzen."""

    # Rechnungsnummer
    INVOICE_NUMBER = re.compile(
        r'(?:rechnung(?:s)?|re|rg|invoice|beleg|faktura)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Bestellnummer
    ORDER_NUMBER = re.compile(
        r'(?:bestell(?:ung)?|auftrag(?:s)?|order|po)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Kundennummer - auch mit Bindestrich wie "KD-78901"
    CUSTOMER_NUMBER = re.compile(
        r'(?:kunden?|kd\.?|customer)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9]{2,20})',
        re.IGNORECASE
    )

    # Lieferscheinnummer
    DELIVERY_NOTE = re.compile(
        r'(?:liefer(?:schein)?|ls|delivery)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Vertragsnummer
    CONTRACT_NUMBER = re.compile(
        r'(?:vertrag(?:s)?|contract|vtr)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Angebotsnummer
    QUOTATION_NUMBER = re.compile(
        r'(?:angebot(?:s)?|offerte|quote|ang)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )


class DatePatterns:
    """Patterns fuer deutsche Datumsformate."""

    # Deutsches Datum: 15.02.2024
    DATE_DE = re.compile(
        r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b'
    )

    # Rechnungsdatum
    INVOICE_DATE = re.compile(
        r'(?:rechnung(?:s)?datum|datum\s*der?\s*rechnung|ausgestellt\s*am)[\s:]*'
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        re.IGNORECASE
    )

    # Bestelldatum
    ORDER_DATE = re.compile(
        r'(?:bestell(?:ung)?(?:s)?datum|datum\s*der?\s*bestellung)[\s:]*'
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        re.IGNORECASE
    )

    # Liefertermin
    DELIVERY_DATE = re.compile(
        r'(?:liefer(?:ung)?(?:s)?(?:termin|datum)|gew[uü]nschte?\s*lieferung)[\s:]*'
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        re.IGNORECASE
    )

    # Leistungszeitraum: "Leistungszeitraum: 01.01.2024 - 31.01.2024"
    SERVICE_PERIOD = re.compile(
        r'(?:leistungs?zeitraum|abrechnungszeitraum|zeitraum)[\s:]*'
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s*'
        r'[-–bis]+\s*'
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        re.IGNORECASE
    )

    # Vertragslaufzeit: "Laufzeit: 12 Monate"
    CONTRACT_DURATION = re.compile(
        r'(?:laufzeit|vertrags?dauer|g[uü]ltigkeit)[\s:]*'
        r'(\d{1,3})\s*'
        r'(tage|wochen|monate|jahre)',
        re.IGNORECASE
    )

    # Kuendigungsfrist: "3 Monate zum Quartalsende"
    NOTICE_PERIOD = re.compile(
        r'(?:k[uü]ndigungs?frist|frist)[\s:]*'
        r'(\d{1,2})\s*'
        r'(tage|wochen|monate|jahre)'
        r'(?:\s*zum\s*(monatsende|quartalsende|jahresende))?',
        re.IGNORECASE
    )


# =============================================================================
# STRUCTURED EXTRACTION SERVICE
# =============================================================================

class StructuredExtractionService:
    """
    Orchestriert die strukturierte Datenextraktion.

    Workflow:
    1. Klassifizierung (Invoice, Order, Contract, ...)
    2. Typspezifische Extraktion
    3. Plausibilitaetspruefung
    4. Zusammenfuehrung zu ExtractedDocumentData

    Usage:
        service = StructuredExtractionService()
        result = await service.extract(ocr_text)
        print(result.classification.document_type)
        print(result.invoice.gross_amount)
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self.classification_service = get_classification_service()
        self.entity_service = EntityExtractionService()
        self.translation_service = get_translation_service()

    async def extract(
        self,
        text: str,
        document_id: Optional[str] = None,
        tables: Optional[List[Any]] = None,
        detected_language: Optional[str] = None,
    ) -> ExtractedDocumentData:
        """
        Extrahiert strukturierte Daten aus OCR-Text.

        Bei nicht-deutschen/englischen Texten wird automatisch uebersetzt,
        um einheitliche Keyword-Suche zu ermoeglichen.

        Args:
            text: OCR-Text
            document_id: Optionale Dokument-ID fuer Logging
            tables: Optionale Liste von TableStructure-Objekten (Docling)
            detected_language: Erkannte Sprache (ISO 639-1, z.B. "ru", "pl")

        Returns:
            ExtractedDocumentData mit Klassifizierung und typspezifischen Daten
        """
        start_time = datetime.now()

        # 0. Uebersetzung falls noetig (nicht-deutsche/englische Dokumente)
        original_language = detected_language
        was_translated = False
        translation_confidence: Optional[float] = None
        text_for_extraction = text

        if detected_language and self.translation_service.is_translation_needed(detected_language):
            translation_result = await self.translation_service.translate_for_extraction(
                text=text,
                source_language=detected_language,
            )
            if translation_result.was_translated:
                text_for_extraction = translation_result.translated_text
                was_translated = True
                translation_confidence = translation_result.confidence
                logger.info(
                    "text_translated_for_extraction",
                    document_id=document_id,
                    source_language=detected_language,
                    translation_duration_ms=translation_result.duration_ms,
                    translation_confidence=translation_result.confidence,
                )

        # 1. Klassifizierung (mit uebersetztem Text falls noetig)
        classification = self.classification_service.classify(text_for_extraction)

        # 2. Basis-Entities extrahieren (aus uebersetztem Text)
        entities = await self.entity_service.extract_entities(text_for_extraction)

        # 3. Typspezifische Extraktion
        result = ExtractedDocumentData(
            classification=classification,
            extraction_version="2.0.0",
            extracted_at=datetime.now().isoformat(),
            # Uebersetzungs-Metadaten
            original_language=original_language,
            was_translated=was_translated,
            translation_confidence=translation_confidence,
        )

        # Allgemeine Entities hinzufuegen
        result.vat_ids = [i.normalized_value for i in entities.identifiers if i.identifier_type == "vat_id"]
        result.ibans = [i.normalized_value for i in entities.identifiers if i.identifier_type == "iban"]
        result.companies = [c.name for c in entities.company_names]

        # Alle Daten extrahieren (aus uebersetztem Text)
        result.dates = self._extract_all_dates(text_for_extraction)

        # Alle Betraege extrahieren (aus uebersetztem Text)
        result.amounts = self._extract_all_amounts(text_for_extraction)

        # 4. Typspezifische Extraktion (mit uebersetztem Text)
        if classification.document_type == ExtractedDocumentType.INVOICE:
            result.invoice = await self._extract_invoice_data(
                text_for_extraction, entities, tables
            )
        elif classification.document_type == ExtractedDocumentType.ORDER:
            result.order = await self._extract_order_data(
                text_for_extraction, entities, tables
            )
        elif classification.document_type == ExtractedDocumentType.CONTRACT:
            result.contract = self._extract_contract_data(text_for_extraction, entities)

        # 5. Overall Confidence berechnen
        result.overall_confidence = self._calculate_overall_confidence(result)

        # Logging
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(
            "structured_extraction_completed",
            document_id=document_id,
            document_type=classification.document_type.value,
            classification_confidence=classification.confidence,
            overall_confidence=result.overall_confidence,
            elapsed_ms=round(elapsed, 2),
            original_language=original_language,
            was_translated=was_translated,
        )

        return result

    # =========================================================================
    # INVOICE EXTRACTION
    # =========================================================================

    async def _extract_invoice_data(
        self,
        text: str,
        entities: Any,
        tables: Optional[List[Any]] = None
    ) -> ExtractedInvoiceData:
        """Extrahiert Rechnungsdaten inkl. Positionen aus Tabellen."""
        invoice = ExtractedInvoiceData()
        warnings: List[str] = []

        # Referenznummern
        invoice.invoice_number = self._extract_first_match(
            ReferencePatterns.INVOICE_NUMBER, text
        )
        invoice.order_number = self._extract_first_match(
            ReferencePatterns.ORDER_NUMBER, text
        )
        invoice.customer_number = self._extract_first_match(
            ReferencePatterns.CUSTOMER_NUMBER, text
        )
        invoice.delivery_note_number = self._extract_first_match(
            ReferencePatterns.DELIVERY_NOTE, text
        )

        # Daten
        invoice.invoice_date = self._extract_labeled_date(
            DatePatterns.INVOICE_DATE, text
        ) or self._extract_first_date(text)

        # Faelligkeitsdatum
        due_date_match = PaymentPatterns.DUE_DATE_DIRECT.search(text)
        if due_date_match:
            invoice.due_date = self._parse_date_groups(
                due_date_match.group(1),
                due_date_match.group(2),
                due_date_match.group(3)
            )

        # Oder aus Zahlungsziel berechnen
        if not invoice.due_date and invoice.invoice_date:
            days_match = PaymentPatterns.PAYMENT_DAYS.search(text)
            if days_match:
                days = int(days_match.group(1))
                invoice.due_date = invoice.invoice_date + timedelta(days=days)

        # Leistungszeitraum
        period_match = DatePatterns.SERVICE_PERIOD.search(text)
        if period_match:
            invoice.service_period_start = self._parse_date_groups(
                period_match.group(1),
                period_match.group(2),
                period_match.group(3)
            )
            invoice.service_period_end = self._parse_date_groups(
                period_match.group(4),
                period_match.group(5),
                period_match.group(6)
            )

        # Betraege
        invoice.net_amount = self._extract_labeled_amount(
            AmountPatterns.NET_AMOUNT, text
        )
        invoice.gross_amount = self._extract_labeled_amount(
            AmountPatterns.GROSS_AMOUNT, text
        )

        # MwSt
        vat_with_rate = AmountPatterns.VAT_WITH_RATE.search(text)
        if vat_with_rate:
            invoice.vat_rate = Decimal(vat_with_rate.group(1))
            invoice.vat_amount = self._parse_german_amount(vat_with_rate.group(2))
        else:
            # Nur Betrag
            vat_amount_match = AmountPatterns.VAT_AMOUNT.search(text)
            if vat_amount_match:
                invoice.vat_amount = self._parse_german_amount(vat_amount_match.group(1))

            # Nur Satz
            vat_rate_match = AmountPatterns.VAT_RATE.search(text)
            if vat_rate_match:
                invoice.vat_rate = Decimal(vat_rate_match.group(1))

        # === ZAHLUNGSBEDINGUNGEN (KRITISCH!) ===

        # Zahlungsziel in Tagen - versuche mehrere Patterns
        payment_days_match = PaymentPatterns.PAYMENT_DAYS.search(text)
        days = None
        if payment_days_match:
            days = payment_days_match.group(1)
        else:
            # Fallback: Erweitertes Pattern für "NET 30", "30 days net", etc.
            extended_match = PaymentPatterns.PAYMENT_DAYS_EXTENDED.search(text)
            if extended_match:
                # Finde die erste nicht-None Gruppe
                for group in extended_match.groups():
                    if group:
                        days = group
                        break

        if days:
            invoice.payment_terms = f"{days} Tage netto"
        else:
            # Prüfe auf sofortige Zahlung
            immediate_match = PaymentPatterns.PAYMENT_IMMEDIATE.search(text)
            if immediate_match:
                invoice.payment_terms = "Zahlbar sofort"

        # Zahlungsart
        payment_method_match = PaymentPatterns.PAYMENT_METHOD.search(text)
        if payment_method_match:
            invoice.payment_method = payment_method_match.group(1).title()

        # Skonto - Kombination
        skonto_full_match = PaymentPatterns.SKONTO_FULL.search(text)
        if skonto_full_match:
            invoice.discount_percent = self._parse_german_amount(
                skonto_full_match.group(1).replace(",", ".")
            )
            invoice.discount_days = int(skonto_full_match.group(2))
        else:
            # Einzelne Patterns
            skonto_percent_match = PaymentPatterns.SKONTO_PERCENT.search(text)
            if skonto_percent_match:
                # Pattern hat zwei Gruppen - eine davon ist gesetzt
                percent_str = skonto_percent_match.group(1) or skonto_percent_match.group(2)
                if percent_str:
                    invoice.discount_percent = self._parse_german_amount(
                        percent_str.replace(",", ".")
                    )

            skonto_days_match = PaymentPatterns.SKONTO_DAYS.search(text)
            if skonto_days_match:
                invoice.discount_days = int(skonto_days_match.group(1))

        # Skonto-Betrag berechnen
        if invoice.discount_percent and invoice.gross_amount:
            invoice.discount_amount = (
                invoice.gross_amount * invoice.discount_percent / Decimal("100")
            ).quantize(Decimal("0.01"))

        # Skonto-Faelligkeitsdatum berechnen
        if invoice.discount_days and invoice.invoice_date:
            invoice.discount_due_date = (
                invoice.invoice_date + timedelta(days=invoice.discount_days)
            )

        # Skonto-Volltext
        skonto_fulltext_match = PaymentPatterns.SKONTO_FULLTEXT.search(text)
        if skonto_fulltext_match:
            invoice.early_payment_info = skonto_fulltext_match.group(1).strip()

        # Verzugszinsen
        late_interest_match = PaymentPatterns.LATE_INTEREST_FULLTEXT.search(text)
        if late_interest_match:
            invoice.late_payment_info = late_interest_match.group(1).strip()

        # Absender/Empfaenger aus Entities
        if entities.addresses:
            # Erste Adresse = Absender (meist oben)
            addr = entities.addresses[0]
            invoice.sender = ExtractedAddress(
                street=addr.street,
                zip_code=addr.postal_code,
                city=addr.city,
            )

            if len(entities.addresses) > 1:
                addr2 = entities.addresses[1]
                invoice.recipient = ExtractedAddress(
                    street=addr2.street,
                    zip_code=addr2.postal_code,
                    city=addr2.city,
                )

        # Firmenname
        if entities.company_names:
            if invoice.sender:
                invoice.sender.company = entities.company_names[0].name

        # USt-IdNr
        for identifier in entities.identifiers:
            if identifier.identifier_type == "vat_id":
                invoice.sender_vat_id = identifier.normalized_value
                break

        # Steuernummer
        for identifier in entities.identifiers:
            if identifier.identifier_type == "tax_number":
                invoice.sender_tax_number = identifier.normalized_value
                break

        # IBAN
        for identifier in entities.identifiers:
            if identifier.identifier_type == "iban":
                invoice.sender_bank = ExtractedBankAccount(
                    iban=identifier.normalized_value
                )
                break

        # E-Mail
        if entities.emails:
            invoice.sender_email = entities.emails[0]

        # Telefon
        if entities.phone_numbers:
            invoice.sender_phone = entities.phone_numbers[0]

        # === LINE ITEMS EXTRAKTION ===
        # Aus Docling-Tabellen extrahieren
        if tables:
            try:
                line_item_service = _get_line_item_service()
                invoice.line_items = await line_item_service.extract_from_tables(tables)

                # Plausibilitaet: Summe Positionen vs. Nettobetrag
                if invoice.line_items and invoice.net_amount:
                    is_valid, calculated = line_item_service.validate_against_total(
                        invoice.line_items, invoice.net_amount
                    )
                    if not is_valid and calculated:
                        warnings.append(
                            f"Positionssumme ({calculated}) weicht von Nettobetrag ({invoice.net_amount}) ab"
                        )
                        invoice.needs_review = True

                logger.debug(
                    "line_items_extracted",
                    count=len(invoice.line_items),
                    from_tables=len(tables),
                )
            except Exception as e:
                logger.warning(
                    "line_item_extraction_failed",
                    error=str(e),
                    table_count=len(tables),
                )
                warnings.append(f"Positionsextraktion fehlgeschlagen: {str(e)}")

        # Falls keine Tabellen oder Extraktion fehlgeschlagen: Regex-Fallback
        if not invoice.line_items and text:
            try:
                line_item_service = _get_line_item_service()
                invoice.line_items = await line_item_service.extract_from_text(text)
                if invoice.line_items:
                    logger.debug(
                        "line_items_from_text_fallback",
                        count=len(invoice.line_items),
                    )
            except Exception as e:
                logger.debug("line_item_text_fallback_failed", error=str(e))

        # Warnungen sammeln
        invoice.extraction_warnings = list(invoice.extraction_warnings) + warnings

        # Plausibilitaetspruefung
        invoice = self._validate_invoice(invoice)

        return invoice

    def _validate_invoice(self, invoice: ExtractedInvoiceData) -> ExtractedInvoiceData:
        """Prueft Plausibilitaet der Rechnungsdaten."""
        warnings = list(invoice.extraction_warnings)
        confidence = 0.5  # Basis-Konfidenz

        # Rechnungsnummer gefunden?
        if invoice.invoice_number:
            confidence += 0.15

        # Rechnungsdatum gefunden?
        if invoice.invoice_date:
            confidence += 0.10

        # Betraege vorhanden?
        if invoice.gross_amount:
            confidence += 0.10

        # Netto + MwSt = Brutto?
        if invoice.net_amount and invoice.vat_amount and invoice.gross_amount:
            expected = invoice.net_amount + invoice.vat_amount
            tolerance = Decimal("0.10")  # 10 Cent Toleranz
            if abs(expected - invoice.gross_amount) <= tolerance:
                confidence += 0.15
            else:
                warnings.append(
                    f"Betragsinkonsistenz: {invoice.net_amount} + {invoice.vat_amount} = "
                    f"{invoice.net_amount + invoice.vat_amount} != {invoice.gross_amount}"
                )
                invoice.needs_review = True

        # MwSt-Satz plausibel?
        if invoice.vat_rate:
            if invoice.vat_rate in [Decimal("7"), Decimal("19"), Decimal("0")]:
                confidence += 0.05
            else:
                warnings.append(f"Ungewoehnlicher MwSt-Satz: {invoice.vat_rate}%")

        # IBAN-Validierung (bereits in Entity-Service)
        if invoice.sender_bank and invoice.sender_bank.iban:
            confidence += 0.10

        # Skonto-Berechnung plausibel?
        if invoice.discount_percent and invoice.discount_days:
            if invoice.discount_percent <= Decimal("5") and invoice.discount_days <= 30:
                confidence += 0.05
            else:
                warnings.append(
                    f"Ungewoehnliche Skonto-Bedingungen: {invoice.discount_percent}% / {invoice.discount_days} Tage"
                )

        # Positionen gefunden?
        if invoice.line_items:
            confidence += 0.05  # Bonus fuer gefundene Positionen

        invoice.extraction_confidence = min(confidence, 0.99)
        invoice.extraction_warnings = warnings

        return invoice

    # =========================================================================
    # ORDER EXTRACTION
    # =========================================================================

    async def _extract_order_data(
        self,
        text: str,
        entities: Any,
        tables: Optional[List[Any]] = None
    ) -> ExtractedOrderData:
        """Extrahiert Bestelldaten inkl. Positionen aus Tabellen."""
        order = ExtractedOrderData()

        # Referenznummern
        order.order_number = self._extract_first_match(
            ReferencePatterns.ORDER_NUMBER, text
        )
        order.quotation_number = self._extract_first_match(
            ReferencePatterns.QUOTATION_NUMBER, text
        )
        order.customer_order_number = self._extract_first_match(
            ReferencePatterns.CUSTOMER_NUMBER, text
        )

        # Daten
        order.order_date = self._extract_labeled_date(
            DatePatterns.ORDER_DATE, text
        ) or self._extract_first_date(text)

        order.delivery_date = self._extract_labeled_date(
            DatePatterns.DELIVERY_DATE, text
        )

        # Betraege
        order.total_amount = self._extract_labeled_amount(
            AmountPatterns.GROSS_AMOUNT, text
        )

        # Adressen
        if entities.addresses:
            if len(entities.addresses) >= 1:
                addr = entities.addresses[0]
                order.orderer = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )
            if len(entities.addresses) >= 2:
                addr = entities.addresses[1]
                order.supplier = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )

        # Firmenname
        if entities.company_names:
            if order.orderer:
                order.orderer.company = entities.company_names[0].name

        # Zahlungsbedingungen
        payment_days_match = PaymentPatterns.PAYMENT_DAYS.search(text)
        if payment_days_match:
            order.payment_terms = f"{payment_days_match.group(1)} Tage netto"

        # === LINE ITEMS EXTRAKTION ===
        # Aus Docling-Tabellen extrahieren
        if tables:
            try:
                line_item_service = _get_line_item_service()
                order.line_items = await line_item_service.extract_from_tables(tables)
                logger.debug(
                    "order_line_items_extracted",
                    count=len(order.line_items),
                    from_tables=len(tables),
                )
            except Exception as e:
                logger.warning(
                    "order_line_item_extraction_failed",
                    error=str(e),
                    table_count=len(tables),
                )

        # Falls keine Tabellen: Regex-Fallback
        if not order.line_items and text:
            try:
                line_item_service = _get_line_item_service()
                order.line_items = await line_item_service.extract_from_text(text)
            except Exception as e:
                logger.debug("order_line_item_text_fallback_failed", error=str(e))

        # Konfidenz
        confidence = 0.5
        if order.order_number:
            confidence += 0.20
        if order.order_date:
            confidence += 0.15
        if order.delivery_date:
            confidence += 0.10
        if order.total_amount:
            confidence += 0.10
        if order.line_items:
            confidence += 0.05  # Bonus fuer gefundene Positionen

        order.extraction_confidence = min(confidence, 0.99)

        return order

    # =========================================================================
    # CONTRACT EXTRACTION
    # =========================================================================

    def _extract_contract_data(
        self,
        text: str,
        entities: Any
    ) -> ExtractedContractData:
        """Extrahiert Vertragsdaten."""
        contract = ExtractedContractData()

        # Vertragsnummer
        contract.contract_number = self._extract_first_match(
            ReferencePatterns.CONTRACT_NUMBER, text
        )

        # Daten
        contract.contract_date = self._extract_first_date(text)

        # Leistungszeitraum = Vertragszeitraum?
        period_match = DatePatterns.SERVICE_PERIOD.search(text)
        if period_match:
            contract.start_date = self._parse_date_groups(
                period_match.group(1),
                period_match.group(2),
                period_match.group(3)
            )
            contract.end_date = self._parse_date_groups(
                period_match.group(4),
                period_match.group(5),
                period_match.group(6)
            )

        # Vertragslaufzeit
        duration_match = DatePatterns.CONTRACT_DURATION.search(text)
        if duration_match:
            duration = int(duration_match.group(1))
            unit = duration_match.group(2).lower()

            if "monat" in unit:
                contract.duration_months = duration
            elif "jahr" in unit:
                contract.duration_months = duration * 12
            elif "woche" in unit:
                contract.duration_months = max(1, duration // 4)

        # Kuendigungsfrist
        notice_match = DatePatterns.NOTICE_PERIOD.search(text)
        if notice_match:
            notice_value = notice_match.group(1)
            notice_unit = notice_match.group(2)
            notice_deadline = notice_match.group(3) if len(notice_match.groups()) > 2 else None

            notice_text = f"{notice_value} {notice_unit}"
            if notice_deadline:
                notice_text += f" zum {notice_deadline}"
            contract.notice_period = notice_text

        # Automatische Verlaengerung suchen
        if re.search(r'verl[aä]nger(?:t|ung)|auto(?:matisch)?.*?renew', text, re.IGNORECASE):
            contract.auto_renewal = True

        # Betraege
        contract.contract_value = self._extract_labeled_amount(
            AmountPatterns.GROSS_AMOUNT, text
        )

        # Monatlicher Betrag (auch "Monatlicher Betrag: 1.000,00 EUR")
        monthly_match = re.search(
            r'(?:monatlich(?:er|e|es)?(?:\s+betrag)?|mtl\.?|pro\s*monat)[\s:]*'
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)?',
            text,
            re.IGNORECASE
        )
        if monthly_match:
            contract.monthly_value = self._parse_german_amount(monthly_match.group(1))

        # Vertragsparteien
        if entities.addresses:
            if len(entities.addresses) >= 1:
                addr = entities.addresses[0]
                contract.party_a = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )
            if len(entities.addresses) >= 2:
                addr = entities.addresses[1]
                contract.party_b = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )

        # Firmennamen
        if entities.company_names:
            if contract.party_a and len(entities.company_names) >= 1:
                contract.party_a.company = entities.company_names[0].name
            if contract.party_b and len(entities.company_names) >= 2:
                contract.party_b.company = entities.company_names[1].name

        # Vertragstyp erkennen
        if re.search(r'miet(?:vertrag)?|pacht', text, re.IGNORECASE):
            contract.contract_type = "Mietvertrag"
        elif re.search(r'dienst(?:leistungs?)?(?:vertrag)?|service', text, re.IGNORECASE):
            contract.contract_type = "Dienstleistungsvertrag"
        elif re.search(r'arbeits(?:vertrag)?', text, re.IGNORECASE):
            contract.contract_type = "Arbeitsvertrag"
        elif re.search(r'kauf(?:vertrag)?', text, re.IGNORECASE):
            contract.contract_type = "Kaufvertrag"
        elif re.search(r'rahmen(?:vertrag)?', text, re.IGNORECASE):
            contract.contract_type = "Rahmenvertrag"

        # Konfidenz
        confidence = 0.5
        if contract.contract_number:
            confidence += 0.15
        if contract.start_date or contract.end_date:
            confidence += 0.15
        if contract.notice_period:
            confidence += 0.10
        if contract.duration_months:
            confidence += 0.10
        if contract.contract_type:
            confidence += 0.10

        contract.extraction_confidence = min(confidence, 0.99)

        return contract

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _extract_first_match(
        self,
        pattern: re.Pattern,
        text: str
    ) -> Optional[str]:
        """Extrahiert den ersten Match eines Patterns."""
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return None

    def _extract_labeled_amount(
        self,
        pattern: re.Pattern,
        text: str
    ) -> Optional[Decimal]:
        """Extrahiert einen Betrag mit Label."""
        match = pattern.search(text)
        if match:
            return self._parse_german_amount(match.group(1))
        return None

    def _extract_labeled_date(
        self,
        pattern: re.Pattern,
        text: str
    ) -> Optional[date]:
        """Extrahiert ein Datum mit Label."""
        match = pattern.search(text)
        if match:
            return self._parse_date_groups(
                match.group(1),
                match.group(2),
                match.group(3)
            )
        return None

    def _extract_first_date(self, text: str) -> Optional[date]:
        """Extrahiert das erste gefundene Datum."""
        match = DatePatterns.DATE_DE.search(text)
        if match:
            return self._parse_date_groups(
                match.group(1),
                match.group(2),
                match.group(3)
            )
        return None

    def _extract_all_dates(self, text: str) -> List[date]:
        """Extrahiert alle Daten aus dem Text."""
        dates = []
        for match in DatePatterns.DATE_DE.finditer(text):
            d = self._parse_date_groups(
                match.group(1),
                match.group(2),
                match.group(3)
            )
            if d and d not in dates:
                dates.append(d)
        return dates

    def _extract_all_amounts(self, text: str) -> List[Decimal]:
        """Extrahiert alle Betraege aus dem Text."""
        amounts = []
        for match in AmountPatterns.GERMAN_AMOUNT.finditer(text):
            amount = self._parse_german_amount(match.group(1))
            if amount and amount not in amounts and amount > Decimal("0"):
                amounts.append(amount)
        return sorted(amounts, reverse=True)[:10]  # Top 10 Betraege

    def _parse_german_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parst einen deutschen Geldbetrag."""
        try:
            # Tausendertrenner (.) entfernen, Dezimalkomma zu Punkt
            cleaned = amount_str.replace(".", "").replace(",", ".")
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    def _parse_date_groups(
        self,
        day: str,
        month: str,
        year: str
    ) -> Optional[date]:
        """Parst Datumsgruppen zu einem date-Objekt."""
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    def _calculate_overall_confidence(
        self,
        result: ExtractedDocumentData
    ) -> float:
        """Berechnet die Gesamtkonfidenz."""
        confidences = []

        if result.classification:
            confidences.append(result.classification.confidence)

        primary_data = result.get_primary_data()
        if primary_data:
            confidences.append(primary_data.extraction_confidence)

        if not confidences:
            return 0.0

        return sum(confidences) / len(confidences)


# =============================================================================
# SINGLETON INSTANCE (Thread-Safe)
# =============================================================================

import threading

_structured_extraction_service: Optional[StructuredExtractionService] = None
_extraction_service_lock = threading.Lock()


def get_structured_extraction_service() -> StructuredExtractionService:
    """
    Gibt die Singleton-Instanz zurueck.

    Thread-safe durch Double-Checked Locking - wichtig fuer
    Celery Worker mit mehreren Prozessen/Threads.
    """
    global _structured_extraction_service

    # Fast path: Singleton bereits initialisiert
    if _structured_extraction_service is not None:
        return _structured_extraction_service

    # Slow path: Mit Lock initialisieren
    with _extraction_service_lock:
        # Nochmal pruefen nach Lock-Erwerb
        if _structured_extraction_service is not None:
            return _structured_extraction_service

        _structured_extraction_service = StructuredExtractionService()

    return _structured_extraction_service


def reset_structured_extraction_service() -> None:
    """Setzt die Singleton-Instanz zurueck (fuer Tests)."""
    global _structured_extraction_service
    with _extraction_service_lock:
        _structured_extraction_service = None
