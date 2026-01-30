"""
Enhanced Line Item Extractor.

Multi-pass extraction strategy for line items:
- Pass 1: Header-based (standard tables)
- Pass 2: Heuristic (tables without headers)
- Pass 3: Positional (column inference)
- Pass 4: Regex fallback (text-based)
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from app.services.extraction.base import ExtractionConfig, parse_german_decimal
from app.core.safe_errors import safe_error_log
from app.services.extraction.config import (

    MAX_DESCRIPTION_LENGTH,
    MAX_QUANTITY,
    MAX_UNIT_PRICE,
    MIN_DESCRIPTION_LENGTH,
    SUMMARY_ROW_INDICATORS,
)

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedLineItem:
    """A single line item extracted from a document."""

    position: int
    """Position/row number."""

    description: str
    """Item description."""

    quantity: Optional[Decimal] = None
    """Quantity."""

    unit: Optional[str] = None
    """Unit of measurement (Stk, kg, h, etc.)."""

    unit_price: Optional[Decimal] = None
    """Price per unit."""

    total_price: Optional[Decimal] = None
    """Total price for this line."""

    vat_rate: Optional[Decimal] = None
    """VAT rate for this item (if per-line VAT)."""

    article_number: Optional[str] = None
    """Article/SKU number."""

    confidence: float = 0.8
    """Extraction confidence."""

    raw_row: Optional[List[str]] = None
    """Original row data for debugging."""

    def is_complete(self) -> bool:
        """Check if line item has minimum required data."""
        has_description = bool(self.description and len(self.description) >= MIN_DESCRIPTION_LENGTH)
        has_amount = self.total_price is not None or self.unit_price is not None
        return has_description and has_amount

    def validate_math(self) -> bool:
        """Check if qty * unit_price ≈ total_price."""
        if self.quantity and self.unit_price and self.total_price:
            expected = self.quantity * self.unit_price
            tolerance = max(Decimal("0.01"), self.total_price * Decimal("0.001"))
            return abs(expected - self.total_price) <= tolerance
        return True  # Can't validate if missing values

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "position": self.position,
            "description": self.description,
            "quantity": float(self.quantity) if self.quantity else None,
            "unit": self.unit,
            "unit_price": float(self.unit_price) if self.unit_price else None,
            "total_price": float(self.total_price) if self.total_price else None,
            "vat_rate": float(self.vat_rate) if self.vat_rate else None,
            "article_number": self.article_number,
            "confidence": self.confidence,
        }


@dataclass
class TableStructure:
    """Simplified table structure for extraction."""

    rows: List[List[str]]
    """Table rows (list of cell texts)."""

    num_rows: int = 0
    num_cols: int = 0

    def __post_init__(self):
        self.num_rows = len(self.rows)
        self.num_cols = max(len(row) for row in self.rows) if self.rows else 0

    def get_row(self, idx: int) -> List[str]:
        """Get row by index."""
        if 0 <= idx < len(self.rows):
            return self.rows[idx]
        return []

    def get_cell(self, row: int, col: int) -> str:
        """Get cell text."""
        try:
            return self.rows[row][col]
        except IndexError:
            return ""


class EnhancedLineItemExtractor:
    """
    Multi-pass line item extractor.

    Pass 1: Header-based - Find header row, map columns, extract items
    Pass 2: Heuristic - Infer column types from content
    Pass 3: Positional - Use column positions for standard layouts
    Pass 4: Regex - Extract from raw text as fallback
    """

    # Header keywords for column identification
    HEADER_KEYWORDS: Dict[str, Set[str]] = {
        "position": {"pos", "nr", "nr.", "position", "posnr", "zeile", "#", "lfd"},
        "article": {"art", "art.", "artikel", "artikelnr", "sku", "art-nr"},
        "description": {
            "beschreibung", "bezeichnung", "leistung", "dienstleistung",
            "artikel", "position", "text", "produkt", "name", "description",
        },
        "quantity": {"menge", "anzahl", "stk", "qty", "quantity", "anz", "stück", "anz.", "mge"},
        "unit": {"einheit", "eh", "me", "unit", "einh"},
        "unit_price": {
            "einzelpreis", "e-preis", "ep", "preis", "stückpreis",
            "unit price", "price", "€/stk", "eur/stk",
        },
        "total_price": {
            "gesamtpreis", "gp", "summe", "betrag", "netto", "gesamt",
            "total", "gesamtbetrag", "total price", "amount", "ges.",
        },
        "vat_rate": {"mwst", "ust", "steuer", "steuersatz", "vat", "tax"},
    }

    # Units of measurement
    UNITS: Set[str] = {
        "stk", "st", "stck", "stück", "pcs",
        "kg", "g", "mg", "t",
        "l", "ml", "m³",
        "m", "cm", "mm", "km", "m²",
        "h", "std", "min", "stunden",
        "psch", "pausch", "pauschal",
        "tag", "tage", "monat", "jahr",
    }

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self.config = config or ExtractionConfig()

    def extract_from_tables(
        self,
        tables: List[Any],
        fallback_to_text: bool = True,
    ) -> List[ExtractedLineItem]:
        """
        Extract line items from tables with multi-pass strategy.

        Args:
            tables: List of table structures (from Docling or similar)
            fallback_to_text: Whether to try regex if tables fail

        Returns:
            List of extracted line items
        """
        all_items: List[ExtractedLineItem] = []

        for table in tables:
            # Convert to TableStructure if needed
            if isinstance(table, dict):
                table_struct = self._dict_to_table(table)
            elif isinstance(table, TableStructure):
                table_struct = table
            elif hasattr(table, "rows"):
                table_struct = TableStructure(rows=table.rows)
            else:
                continue

            # Pass 1: Header-based extraction
            items = self._extract_with_headers(table_struct)

            # Pass 2: Heuristic extraction (if Pass 1 failed)
            if not items:
                items = self._extract_heuristic(table_struct)

            # Pass 3: Positional extraction (if Pass 2 failed)
            if not items:
                items = self._extract_positional(table_struct)

            all_items.extend(items)

        # Post-processing: Handle continuation rows
        all_items = self._merge_continuation_rows(all_items)

        # Renumber positions
        for idx, item in enumerate(all_items, 1):
            item.position = idx

        return all_items

    def extract_from_text(self, text: str) -> List[ExtractedLineItem]:
        """
        Extract line items from raw text using regex.

        This is Pass 4 (fallback) of the extraction strategy.
        Uses multiple patterns to handle various formats.
        """
        items: List[ExtractedLineItem] = []
        position_counter = 1

        # Pattern 1: Standard format with numeric position number
        # "1  Beratungsleistung  8 Std  125,00  1.000,00"
        pattern_numeric_pos = re.compile(
            r"^\s*(\d{1,3})\s+"  # Position
            r"(.{3,80}?)\s+"  # Description
            r"(\d+(?:[,\.]\d+)?)\s*"  # Quantity
            r"(stk|st|stck|kg|l|m|h|std|psch|pieces?|pcs?|unit|stueck)?\s*"  # Unit
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*"  # Unit price
            r"(?:€|EUR)?\s*"
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2}))?",  # Total
            re.IGNORECASE | re.MULTILINE,
        )

        # Pattern 2: Article number format (e.g. GW-E5326.00)
        # "GW-E5326.00  Stapelbox...  384 Pieces  3,40  1.305,60"
        pattern_article_nr = re.compile(
            r"^\s*"
            r"([A-Z0-9]{1,4}[-]?[A-Z0-9]{1,10}(?:[-\.][A-Z0-9]+)*)\s+"  # Article number
            r"(.+?)\s+"  # Description (greedy until quantity)
            r"(\d+)\s*"  # Quantity (whole number)
            r"(stk|st|stck|kg|l|m|h|std|psch|pieces?|pcs?|unit|stueck)?\s+"  # Unit
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2}))\s*"  # Unit price
            r"(?:€|EUR)?\s*"
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2}))",  # Total (required)
            re.IGNORECASE | re.MULTILINE,
        )

        # Pattern 3: Description-first format (common in German)
        # "Beratungsleistung IT                    1.000,00 EUR"
        pattern_desc_first = re.compile(
            r"^\s*([A-ZÄÖÜa-zäöüß][A-Za-zäöüßÄÖÜ0-9\s\-\.]+?)\s{2,}"
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)?\s*$",
            re.MULTILINE,
        )

        # Pattern 4: Simple format - description, quantity, unit, price, total
        pattern_simple = re.compile(
            r"^\s*"
            r"([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß0-9\s,.\-/]{5,60}?)\s+"  # Description
            r"(\d+(?:[,\.]\d+)?)\s*"  # Quantity
            r"(stk|st|stck|kg|l|m|h|std|psch|pieces?|pcs?|unit|stueck)?\s*"  # Unit
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*"  # Unit price
            r"(?:€|EUR)?\s*"
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2}))",  # Total (required)
            re.IGNORECASE | re.MULTILINE,
        )

        # Try Pattern 1: Numeric positions
        for match in pattern_numeric_pos.finditer(text):
            try:
                description = match.group(2).strip()
                if self._is_summary_row(description):
                    continue

                item = ExtractedLineItem(
                    position=int(match.group(1)),
                    description=description,
                    quantity=parse_german_decimal(match.group(3)),
                    unit=match.group(4).lower() if match.group(4) else None,
                    unit_price=parse_german_decimal(match.group(5)),
                    total_price=(
                        parse_german_decimal(match.group(6))
                        if match.group(6) else None
                    ),
                    confidence=0.70,
                )
                if item.is_complete():
                    items.append(item)
            except (ValueError, IndexError) as e:
                logger.debug("line_item_extraction_parse_error", error_type=type(e).__name__)
                continue

        # Try Pattern 2: Article numbers (if no items found)
        if not items:
            for match in pattern_article_nr.finditer(text):
                try:
                    article_nr = match.group(1).strip()
                    description = match.group(2).strip()
                    if self._is_summary_row(description):
                        continue

                    item = ExtractedLineItem(
                        position=position_counter,
                        article_number=article_nr,
                        description=description,
                        quantity=parse_german_decimal(match.group(3)),
                        unit=match.group(4).lower() if match.group(4) else None,
                        unit_price=parse_german_decimal(match.group(5)),
                        total_price=parse_german_decimal(match.group(6)),
                        confidence=0.75,
                    )
                    if item.is_complete():
                        items.append(item)
                        position_counter += 1
                except (ValueError, IndexError) as e:
                    logger.debug("article_number_extraction_parse_error", error_type=type(e).__name__)
                    continue

        # Try Pattern 3: Description-first (if no items found)
        if not items:
            for match in pattern_desc_first.finditer(text):
                try:
                    description = match.group(1).strip()
                    if self._is_summary_row(description):
                        continue

                    item = ExtractedLineItem(
                        position=position_counter,
                        description=description,
                        total_price=parse_german_decimal(match.group(2)),
                        confidence=0.60,
                    )
                    if item.is_complete():
                        items.append(item)
                        position_counter += 1
                except (ValueError, IndexError) as e:
                    logger.debug("description_first_extraction_parse_error", error_type=type(e).__name__)
                    continue

        # Try Pattern 4: Simple format (if no items found)
        if not items:
            for match in pattern_simple.finditer(text):
                try:
                    description = match.group(1).strip()
                    if self._is_summary_row(description):
                        continue

                    item = ExtractedLineItem(
                        position=position_counter,
                        description=description,
                        quantity=parse_german_decimal(match.group(2)),
                        unit=match.group(3).lower() if match.group(3) else None,
                        unit_price=parse_german_decimal(match.group(4)),
                        total_price=parse_german_decimal(match.group(5)),
                        confidence=0.65,
                    )
                    if item.is_complete():
                        items.append(item)
                        position_counter += 1
                except (ValueError, IndexError) as e:
                    logger.debug("simple_format_extraction_parse_error", error_type=type(e).__name__)
                    continue

        # Pattern 5: Fragmented OCR - reconstruct from scattered lines
        # This handles OCR output where table columns become separate lines
        # WICHTIG: Auch bei schlechten Items den fragmentierten Parser versuchen!
        fragmented_items = self._extract_from_fragmented_ocr(text)

        if fragmented_items:
            # Wenn wir keine Items haben, nimm die fragmentierten
            if not items:
                logger.info(
                    "using_fragmented_extraction",
                    reason="no_other_items_found",
                    fragmented_count=len(fragmented_items),
                )
                items = fragmented_items
            else:
                # Vergleiche Qualität: Fragmentierte vs. bestehende
                existing_has_header = any(
                    any(h in (i.description or "").lower() for h in [
                        'description', 'no.', 'quantity', 'amount', 'price'
                    ])
                    for i in items
                )
                fragmented_has_header = any(
                    any(h in (i.description or "").lower() for h in [
                        'description', 'no.', 'quantity', 'amount', 'price'
                    ])
                    for i in fragmented_items
                )

                # Fragmentierte übernehmen wenn sie besser sind
                if existing_has_header and not fragmented_has_header:
                    logger.info(
                        "using_fragmented_extraction",
                        reason="existing_has_headers",
                        existing_count=len(items),
                        fragmented_count=len(fragmented_items),
                    )
                    items = fragmented_items
                elif (fragmented_items[0].total_price and
                      fragmented_items[0].total_price > Decimal(100) and
                      all(i.total_price is None or i.total_price < Decimal(10) for i in items)):
                    # Fragmentierte haben plausiblere Preise
                    logger.info(
                        "using_fragmented_extraction",
                        reason="better_prices",
                        existing_prices=[str(i.total_price) for i in items],
                        fragmented_price=str(fragmented_items[0].total_price),
                    )
                    items = fragmented_items

        return items

    def _extract_from_fragmented_ocr(self, text: str) -> List[ExtractedLineItem]:
        """
        Extract line items from fragmented OCR output.

        Handles cases where OCR reads table columns as separate lines:
        1.305,60
        3,40
        384 Pieces
        Stapelbox 500 x 300 x 260 mm
        GW-E5326.00
        ...
        """
        items: List[ExtractedLineItem] = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Pattern für Artikelnummern (z.B. GW-E5326.00, ABC-123, E5326.00)
        # Erlaubt: Buchstaben, Zahlen, Bindestriche, Punkte
        article_pattern = re.compile(
            r'^([A-Z]{1,4}[-]?[A-Z0-9]{1,10}(?:[-\.][A-Z0-9]+)*)$',
            re.IGNORECASE
        )
        # Alternatives Pattern für Artikelnummern mit mehr Flexibilität
        article_pattern_flex = re.compile(
            r'^([A-Z]{1,3}[-]?[A-Z]?\d{3,6}(?:\.\d{1,2})?)$',  # z.B. GW-E5326.00, E5326.00
            re.IGNORECASE
        )

        # Pattern für Menge + Einheit (z.B. "384 Pieces", "10 Stk")
        qty_unit_pattern = re.compile(
            r'^(\d+(?:[,\.]\d+)?)\s*(pieces?|pcs?|stk|st|stck|kg|l|m|h|std|psch|unit|stueck)$',
            re.IGNORECASE
        )

        # Pattern für Preise (deutsches Format, mit optionalen Zeichen)
        price_pattern = re.compile(
            r'^(\d{1,3}(?:\.\d{3})*(?:,\d{1,2}))(?:\s*[€V✓🗸])?$'
        )

        # Pattern für einfache Dezimalzahlen (Einzelpreis wie 3,40)
        simple_price_pattern = re.compile(r'^(\d{1,3},\d{2})$')

        # Header-Keywords die übersprungen werden sollen (auch Einzelwörter!)
        header_keywords = {
            'description', 'no.', 'no', 'quantity', 'measure', 'unit price',
            'amount', 'total', 'summe', 'gesamt', 'netto', 'brutto',
            'mwst', 'ust', 'eur', 'pos', 'pos.', 'artikel', 'menge',
            'einheit', 'preis', 'betrag', 'unit', 'price', 'qty',
            '<b>unit of</b>', '<b>unit price</b>', '<b>amount</b>',
            '<b>quantity measure</b>', 'factuurdatum', 'due date',
            'payment terms', 'bank', 'account', 'iban', 'swift', 'btw',
            'vat', 'invoice', 'order', 'bill-to', 'phone', 'fax'
        }

        # Sammle potentielle Komponenten
        article_numbers: List[str] = []
        descriptions: List[str] = []
        quantities: List[Decimal] = []
        units: List[str] = []
        prices: List[Decimal] = []

        logger.debug(
            "fragmented_ocr_starting",
            total_lines=len(lines),
        )

        for line in lines:
            line_lower = line.lower().strip()

            # Skip leere oder sehr kurze Zeilen
            if len(line_lower) < 2:
                continue

            # Skip Header-Keywords (exakte Übereinstimmung oder enthält)
            is_header = False
            for kw in header_keywords:
                if line_lower == kw or (len(kw) > 3 and kw in line_lower):
                    is_header = True
                    break
            if is_header:
                logger.debug("fragmented_ocr_skip_header", line=line)
                continue

            # Skip HTML-Tags und formatierte Header
            if line.startswith('<') and line.endswith('>'):
                continue

            # Artikelnummer? (z.B. GW-E5326.00)
            if article_pattern.match(line) or article_pattern_flex.match(line):
                # Zusätzliche Validierung
                if re.search(r'\d', line):  # Muss mindestens eine Zahl enthalten
                    # ABER: Keine USt-IdNr, IBAN, oder reine Zahlenfolgen!
                    # USt-IdNr beginnt mit 2 Buchstaben + Zahlen (DE123456789)
                    is_vat_id = re.match(r'^[A-Z]{2}\d{8,12}$', line, re.IGNORECASE)
                    is_iban = re.match(r'^[A-Z]{2}\d{2}', line, re.IGNORECASE) and len(line) > 15
                    is_date_like = re.match(r'^\d{2}[-/.]\d{2}[-/.]\d{2,4}$', line)
                    is_order_nr = line_lower.startswith(('v-', 'f-'))  # V-210089, F-201401

                    if not is_vat_id and not is_iban and not is_date_like and not is_order_nr:
                        article_numbers.append(line)
                        logger.debug("fragmented_ocr_found_article", article=line)
                        continue
                    else:
                        logger.debug("fragmented_ocr_skip_not_article", line=line, reason="vat_iban_date_order")

            # Menge + Einheit? (z.B. "384 Pieces")
            qty_match = qty_unit_pattern.match(line)
            if qty_match:
                qty = parse_german_decimal(qty_match.group(1))
                unit = qty_match.group(2).lower()
                quantities.append(qty)
                units.append(unit)
                logger.debug("fragmented_ocr_found_qty", qty=str(qty), unit=unit)
                continue

            # Preis mit Tausender-Trennzeichen (z.B. 1.305,60)?
            price_match = price_pattern.match(line)
            if price_match:
                price = parse_german_decimal(price_match.group(1))
                prices.append(price)
                logger.debug("fragmented_ocr_found_price", price=str(price))
                continue

            # Einfacher Preis (z.B. 3,40)?
            simple_match = simple_price_pattern.match(line)
            if simple_match:
                price = parse_german_decimal(simple_match.group(1))
                prices.append(price)
                logger.debug("fragmented_ocr_found_simple_price", price=str(price))
                continue

            # Produktbeschreibung?
            # Muss Buchstaben enthalten, nicht nur Zahlen, mindestens 5 Zeichen
            if (len(line) >= 5 and
                re.search(r'[a-zA-ZäöüÄÖÜß]', line) and
                not re.match(r'^[\d\s,\.\-€]+$', line)):
                # Überspringe wenn es wie Adresse/Firmenname/Metadaten aussieht
                skip_patterns = [
                    # Adressen
                    'str.', 'strasse', 'straße', 'weg ', 'platz', 'landeweg',
                    'magnus', 'albertus',  # Straßennamen
                    # Firmenformen und Firmennamen
                    'gmbh', ' bv', ' ag', ' kg', 'firmenich', 'alpac',
                    'kunststof', 'bakken', 'pallets', 'spargelmesser',
                    # Kontakt - erweitert!
                    'tel:', 'tel.', 'mail:', '@', 'fax', 'phone', 'phone no', 'fax no',
                    # Bank/Finanzen
                    'bank', 'iban', 'swift', 'ingb', 'account', 'ing ',
                    # Web
                    'www.', 'http', '.nl', '.de', '.com',
                    # Rechtliches/IDs
                    'vat reg', 'btw:', 'kvk', 'voorwaarden', 'gedeponeerd',
                    'registration', 'customer no', 'bill-to', 'algemene',
                    # Datum/Referenzen
                    'april', 'januar', 'februar', 'märz', 'mai', 'juni',
                    'juli', 'august', 'september', 'oktober', 'november', 'dezember',
                    # Städte/Orte/Länder
                    'deventer', 'solingen', 'duitsland', 'deutschland',
                    # Dokumenttypen
                    'invoice', 'order', 'sales',
                    # Sonstiges
                    'onze', 'onder nummer',
                ]

                # Nur echte Produktbeschreibungen akzeptieren
                # Typische Produktbegriffe
                product_indicators = [
                    'stapel', 'box', 'container', 'kiste', 'palette',
                    'liter', 'perforiert', 'hdpe', 'lila', 'rot', 'blau', 'grün',
                    'mm', 'cm', 'x ',  # Maßangaben
                    '500', '300', '260',  # Typische Maße
                ]

                is_skip = any(skip in line_lower for skip in skip_patterns)
                is_product = any(prod in line_lower for prod in product_indicators)

                # NUR echte Produktbeschreibungen akzeptieren - STRENGER Filter
                # Muss ein Produktindikator haben ODER Maßangaben enthalten
                has_dimensions = re.search(r'\d+\s*x\s*\d+', line)  # z.B. 500 x 300

                if is_product or has_dimensions:
                    # Zusätzlich: Überspringe wenn es wie eine Postleitzahl aussieht
                    if not re.match(r'^\d{4,5}\s*[A-Z]{0,2}\s+\w+', line):
                        descriptions.append(line)
                        logger.debug("fragmented_ocr_found_desc", desc=line[:50])

        # Log gesammelte Komponenten
        logger.info(
            "fragmented_ocr_components_collected",
            articles=article_numbers,
            descriptions=[d[:30] for d in descriptions],
            quantities=[str(q) for q in quantities],
            units=units,
            prices=[str(p) for p in prices],
        )

        # Versuche die Komponenten zusammenzuführen
        if descriptions or (article_numbers and prices):
            # Sortiere Preise nach Größe (größter ist wahrscheinlich Gesamtpreis)
            sorted_prices = sorted(prices, reverse=True) if prices else []

            # Kombiniere Beschreibungen zu einer
            # NICHT die Artikelnummer in die Beschreibung!
            # Filtere nochmal unerwünschte Teile raus
            clean_descriptions = []
            unwanted_parts = [
                'fax no', 'phone no', 'tel no', 'vat reg', 'btw:',
                'onze algemene', 'voorwaarden', 'gedeponeerd', 'kvk',
                'onder nummer', 'alpac', 'kunststof bakken',
            ]
            for desc in descriptions:
                desc_lower = desc.lower()
                if not any(unwanted in desc_lower for unwanted in unwanted_parts):
                    clean_descriptions.append(desc)

            full_description = ', '.join(clean_descriptions) if clean_descriptions else ""

            # Bestimme Total und Unit Price
            total_price = sorted_prices[0] if sorted_prices else None
            unit_price = None
            if len(sorted_prices) > 1:
                # Kleinster Preis ist wahrscheinlich Einzelpreis
                unit_price = sorted_prices[-1]
                # Validiere: Unit Price sollte kleiner als Total sein
                if unit_price and total_price and unit_price >= total_price:
                    unit_price = None

            # Einheiten ins Deutsche übersetzen
            unit_translations = {
                'pieces': 'Stück',
                'piece': 'Stück',
                'pcs': 'Stück',
                'pc': 'Stück',
                'unit': 'Stück',
                'units': 'Stück',
                'stk': 'Stück',
                'st': 'Stück',
                'stck': 'Stück',
                'stueck': 'Stück',
            }
            translated_unit = None
            if units:
                raw_unit = units[0].lower()
                translated_unit = unit_translations.get(raw_unit, units[0])

            # Erstelle Line Item
            item = ExtractedLineItem(
                position=1,
                article_number=article_numbers[0] if article_numbers else None,
                description=full_description,
                quantity=quantities[0] if quantities else None,
                unit=translated_unit,
                unit_price=unit_price,
                total_price=total_price,
                confidence=0.70,  # Höhere Confidence wenn alle Komponenten gefunden
            )

            # Validiere mathematisch wenn möglich
            if item.quantity and item.unit_price and item.total_price:
                expected = item.quantity * item.unit_price
                tolerance = max(Decimal("0.01"), item.total_price * Decimal("0.01"))
                if abs(expected - item.total_price) <= tolerance:
                    item.confidence = 0.85  # Noch höher wenn Mathematik stimmt
                    logger.debug(
                        "fragmented_ocr_math_validated",
                        qty=str(item.quantity),
                        unit_price=str(item.unit_price),
                        expected=str(expected),
                        actual=str(item.total_price),
                    )

            if item.is_complete():
                items.append(item)
                logger.info(
                    "fragmented_ocr_extraction_success",
                    article=item.article_number,
                    description=item.description[:50] if item.description else None,
                    quantity=float(item.quantity) if item.quantity else None,
                    unit_price=float(item.unit_price) if item.unit_price else None,
                    total_price=float(item.total_price) if item.total_price else None,
                    confidence=item.confidence,
                )
            else:
                logger.warning(
                    "fragmented_ocr_item_incomplete",
                    has_description=bool(item.description),
                    has_price=item.total_price is not None or item.unit_price is not None,
                    description=item.description[:30] if item.description else None,
                )
        else:
            logger.debug(
                "fragmented_ocr_no_components",
                has_descriptions=bool(descriptions),
                has_prices=bool(prices),
                has_articles=bool(article_numbers),
            )

        return items

    def _dict_to_table(self, table_dict: Dict) -> TableStructure:
        """Convert dictionary table to TableStructure."""
        rows = table_dict.get("rows", [])
        if not rows and "cells" in table_dict:
            # Convert cells format to rows
            cells = table_dict["cells"]
            max_row = max(c.get("row", 0) for c in cells) + 1 if cells else 0
            max_col = max(c.get("col", 0) for c in cells) + 1 if cells else 0
            rows = [[""] * max_col for _ in range(max_row)]
            for cell in cells:
                r, c = cell.get("row", 0), cell.get("col", 0)
                rows[r][c] = cell.get("text", "")
        return TableStructure(rows=rows)

    def _extract_with_headers(self, table: TableStructure) -> List[ExtractedLineItem]:
        """Pass 1: Header-based extraction."""
        items: List[ExtractedLineItem] = []

        # Find header row
        header_row_idx = self._identify_header_row(table)
        if header_row_idx < 0:
            return items

        # Map columns
        column_map = self._map_columns(table.get_row(header_row_idx))
        if not column_map:
            return items

        logger.debug(
            "header_extraction",
            header_row=header_row_idx,
            column_map=column_map,
        )

        # Extract data rows
        for row_idx in range(header_row_idx + 1, table.num_rows):
            row = table.get_row(row_idx)
            item = self._extract_row(row, column_map, row_idx - header_row_idx)
            if item and item.is_complete() and self._is_valid_line_item(item):
                items.append(item)

        return items

    def _identify_header_row(self, table: TableStructure) -> int:
        """Find the header row index."""
        candidates: List[Tuple[int, int]] = []

        for row_idx in range(min(table.num_rows, self.config.header_search_depth)):
            row = table.get_row(row_idx)
            score = self._score_header_row(row)
            candidates.append((row_idx, score))

        if not candidates:
            return -1

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_idx, best_score = candidates[0]

        if best_score >= self.config.header_keyword_threshold:
            return best_idx

        return -1

    def _score_header_row(self, row: List[str]) -> int:
        """Score a row as potential header."""
        score = 0

        for cell in row:
            cell_lower = cell.strip().lower()
            if not cell_lower:
                continue

            # Check against all header keywords
            for field, keywords in self.HEADER_KEYWORDS.items():
                if any(kw in cell_lower for kw in keywords):
                    score += 1
                    break

            # Penalize numeric content (likely data row)
            if re.match(r"^\d+[,\.]\d+$", cell_lower):
                score -= 1

        return score

    def _map_columns(self, header_row: List[str]) -> Dict[str, int]:
        """Map column indices to field names."""
        column_map: Dict[str, int] = {}

        for col_idx, cell in enumerate(header_row):
            cell_lower = cell.strip().lower()
            if not cell_lower:
                continue

            # Check each field type
            for field, keywords in self.HEADER_KEYWORDS.items():
                if field in column_map:
                    continue  # Already mapped

                # Exact match
                if cell_lower in keywords:
                    column_map[field] = col_idx
                    break

                # Partial match (cell contains keyword)
                for keyword in keywords:
                    if len(keyword) >= 3 and keyword in cell_lower:
                        column_map[field] = col_idx
                        break

        return column_map

    def _extract_row(
        self,
        row: List[str],
        column_map: Dict[str, int],
        row_num: int,
    ) -> Optional[ExtractedLineItem]:
        """Extract line item from a single row."""
        try:
            # Get description (required) - fallback to article if no description column
            desc_idx = column_map.get("description")
            if desc_idx is None:
                desc_idx = column_map.get("article")  # "Artikel" column as fallback
            if desc_idx is None:
                return None

            description = row[desc_idx].strip() if desc_idx < len(row) else ""
            if not description or len(description) < MIN_DESCRIPTION_LENGTH:
                return None

            item = ExtractedLineItem(
                position=row_num,
                description=description,
                raw_row=row,
            )

            # Position
            if "position" in column_map:
                pos_text = row[column_map["position"]].strip()
                if pos_text.isdigit():
                    item.position = int(pos_text)

            # Article number
            if "article" in column_map:
                item.article_number = row[column_map["article"]].strip() or None

            # Quantity
            if "quantity" in column_map:
                qty_text = row[column_map["quantity"]].strip()
                if qty_text:
                    try:
                        item.quantity = parse_german_decimal(qty_text)
                    except ValueError as e:
                        logger.debug(
                            "quantity_parse_failed",
                            error_type=type(e).__name__,
                            qty_text=qty_text,
                        )

            # Unit
            if "unit" in column_map:
                unit_text = row[column_map["unit"]].strip().lower()
                if unit_text in self.UNITS:
                    item.unit = unit_text

            # Unit price
            if "unit_price" in column_map:
                price_text = row[column_map["unit_price"]].strip()
                if price_text:
                    try:
                        item.unit_price = parse_german_decimal(price_text)
                    except ValueError as e:
                        logger.debug(
                            "unit_price_parse_failed",
                            error_type=type(e).__name__,
                            price_text=price_text,
                        )

            # Total price
            if "total_price" in column_map:
                total_text = row[column_map["total_price"]].strip()
                if total_text:
                    try:
                        item.total_price = parse_german_decimal(total_text)
                    except ValueError as e:
                        logger.debug(
                            "total_price_parse_failed",
                            error_type=type(e).__name__,
                            total_text=total_text,
                        )

            # VAT rate
            if "vat_rate" in column_map:
                vat_text = row[column_map["vat_rate"]].strip()
                vat_match = re.search(r"(\d{1,2})", vat_text)
                if vat_match:
                    item.vat_rate = Decimal(vat_match.group(1))

            return item

        except Exception as e:
            logger.debug("row_extraction_error", **safe_error_log(e), row=row)
            return None

    def _extract_heuristic(self, table: TableStructure) -> List[ExtractedLineItem]:
        """Pass 2: Heuristic extraction without headers."""
        if table.num_rows < 2 or table.num_cols < 2:
            return []

        # Analyze column content
        column_types = self._infer_column_types(table)

        desc_col = column_types.get("description")
        amount_cols = column_types.get("amounts", [])

        if desc_col is None or not amount_cols:
            return []

        items: List[ExtractedLineItem] = []

        for row_idx in range(table.num_rows):
            row = table.get_row(row_idx)

            # Skip header-like or summary rows
            if self._looks_like_header_or_summary(row):
                continue

            description = row[desc_col].strip() if desc_col < len(row) else ""
            if not description or len(description) < MIN_DESCRIPTION_LENGTH:
                continue

            item = ExtractedLineItem(
                position=len(items) + 1,
                description=description,
                confidence=0.65,
            )

            # Take rightmost amount column as total
            if amount_cols:
                rightmost = max(amount_cols)
                try:
                    total_text = row[rightmost].strip()
                    item.total_price = parse_german_decimal(total_text)
                except (ValueError, IndexError) as e:
                    logger.debug(
                        "heuristic_total_price_parse_failed",
                        error_type=type(e).__name__,
                        rightmost_col=rightmost,
                    )

            if item.is_complete():
                items.append(item)

        return items

    def _infer_column_types(self, table: TableStructure) -> Dict[str, Any]:
        """Analyze table content to infer column purposes."""
        column_stats: Dict[int, Dict[str, Any]] = {}

        for col_idx in range(table.num_cols):
            texts = [
                table.get_cell(row, col_idx).strip()
                for row in range(table.num_rows)
            ]

            non_empty = [t for t in texts if t]
            if not non_empty:
                continue

            stats = {
                "avg_length": statistics.mean(len(t) for t in non_empty),
                "numeric_ratio": sum(1 for t in texts if self._is_numeric(t)) / len(texts),
                "empty_ratio": sum(1 for t in texts if not t) / len(texts),
            }
            column_stats[col_idx] = stats

        # Find description column (longest average text, low numeric ratio)
        desc_candidates = [
            (col, s) for col, s in column_stats.items()
            if s["avg_length"] > 10 and s["numeric_ratio"] < 0.3
        ]
        desc_col = (
            max(desc_candidates, key=lambda x: x[1]["avg_length"])[0]
            if desc_candidates else None
        )

        # Find amount columns (high numeric ratio)
        amount_cols = [
            col for col, s in column_stats.items()
            if s["numeric_ratio"] > 0.6
        ]

        return {"description": desc_col, "amounts": amount_cols}

    def _extract_positional(self, table: TableStructure) -> List[ExtractedLineItem]:
        """Pass 3: Position-based extraction for standard layouts."""
        # Standard German invoice layout:
        # Pos | Description | Qty | Unit | Price | Total
        # Or: Description | ... | Total

        if table.num_cols < 2:
            return []

        items: List[ExtractedLineItem] = []

        for row_idx in range(table.num_rows):
            row = table.get_row(row_idx)

            # Skip short rows
            if len(row) < 2:
                continue

            # Skip header/summary
            if self._looks_like_header_or_summary(row):
                continue

            # Find longest cell as description
            desc_idx = max(range(len(row)), key=lambda i: len(row[i]))
            description = row[desc_idx].strip()

            if len(description) < MIN_DESCRIPTION_LENGTH:
                continue

            item = ExtractedLineItem(
                position=len(items) + 1,
                description=description,
                confidence=0.55,
            )

            # Find rightmost number as total
            for cell in reversed(row):
                try:
                    if self._is_numeric(cell):
                        item.total_price = parse_german_decimal(cell)
                        break
                except ValueError:
                    continue

            if item.is_complete():
                items.append(item)

        return items

    def _merge_continuation_rows(
        self,
        items: List[ExtractedLineItem],
    ) -> List[ExtractedLineItem]:
        """Merge continuation rows (multi-line descriptions)."""
        if not items:
            return items

        merged: List[ExtractedLineItem] = []

        for item in items:
            # Continuation: No amount, no position number
            is_continuation = (
                item.total_price is None and
                item.unit_price is None and
                item.quantity is None and
                merged
            )

            if is_continuation:
                # Append to previous item's description
                merged[-1].description += " " + item.description
            else:
                merged.append(item)

        return merged

    def _is_numeric(self, text: str) -> bool:
        """Check if text is a numeric value."""
        text = text.strip()
        # Remove currency and spaces
        text = re.sub(r"[€$\s]", "", text)
        # Check if it matches number format
        return bool(re.match(r"^\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?$", text))

    def _is_summary_row(self, description: str) -> bool:
        """Check if description indicates a summary row."""
        desc_lower = description.lower()
        return any(ind in desc_lower for ind in SUMMARY_ROW_INDICATORS)

    def _is_valid_line_item(self, item: ExtractedLineItem) -> bool:
        """Validate a line item."""
        # Check description
        if not item.description or len(item.description) < MIN_DESCRIPTION_LENGTH:
            return False
        if len(item.description) > MAX_DESCRIPTION_LENGTH:
            return False

        # Check for summary row
        if self._is_summary_row(item.description):
            return False

        # Check amounts
        if item.quantity is not None and item.quantity > MAX_QUANTITY:
            return False
        if item.unit_price is not None and item.unit_price > MAX_UNIT_PRICE:
            return False

        # Must have at least one amount
        if item.total_price is None and item.unit_price is None:
            return False

        return True

    def _looks_like_header_or_summary(self, row: List[str]) -> bool:
        """Check if row looks like a header or summary."""
        row_text = " ".join(row).lower()

        # Check for header keywords
        header_keywords = set()
        for keywords in self.HEADER_KEYWORDS.values():
            header_keywords.update(keywords)

        header_count = sum(1 for kw in header_keywords if kw in row_text)
        if header_count >= 2:
            return True

        # Check for summary keywords
        if any(ind in row_text for ind in SUMMARY_ROW_INDICATORS):
            return True

        return False


# Singleton instance
_line_item_extractor: Optional[EnhancedLineItemExtractor] = None


def get_line_item_extractor() -> EnhancedLineItemExtractor:
    """Get singleton line item extractor instance."""
    global _line_item_extractor
    if _line_item_extractor is None:
        _line_item_extractor = EnhancedLineItemExtractor()
    return _line_item_extractor
