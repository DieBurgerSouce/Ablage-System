# -*- coding: utf-8 -*-
"""
LineItemExtractionService - Konvertiert Docling-Tabellen zu strukturierten Positionen.

Dieses Modul extrahiert Rechnungs- und Bestellpositionen aus:
1. Docling TableStructure (bevorzugt)
2. Fallback: Regex-basierte Extraktion aus OCR-Text

Typische deutsche Tabellenkoepfe werden erkannt:
- Pos, Nr, Artikel, Beschreibung, Menge, Einheit, Preis, Summe, MwSt

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Set, Tuple

from app.agents.ocr.models.layout_models import TableCell, TableStructure
from app.api.schemas.extracted_data import ExtractedDocumentType, ExtractedLineItem

logger = logging.getLogger(__name__)


# =============================================================================
# HEADER-MAPPING KONFIGURATION
# =============================================================================

@dataclass
class HeaderMapping:
    """Mapping von Tabellenkoepfen zu LineItem-Feldern."""

    # Feldname -> Liste von möglichen Header-Varianten (lowercase)
    PATTERNS: Dict[str, List[str]] = None

    def __post_init__(self) -> None:
        if self.PATTERNS is None:
            self.PATTERNS = {
                "position": [
                    "pos", "pos.", "nr", "nr.", "#", "position", "posnr", "pos-nr",
                    "lfd", "lfd.", "lfdnr", "zeile", "z"
                ],
                "article_number": [
                    "art", "art.", "art-nr", "artnr", "artikel", "artikelnr",
                    "artikel-nr", "artikelnummer", "bestell-nr", "bestellnr",
                    "product", "produktnr", "sku", "item"
                ],
                "description": [
                    "beschreibung", "bezeichnung", "leistung", "text",
                    "artikel/leistung", "dienstleistung", "position",
                    "leistungsbeschreibung", "artikelbezeichnung",
                    "product description", "benennung", "bez"
                ],
                "quantity": [
                    "menge", "anzahl", "stk", "stück", "stck",
                    "qty", "quantity", "anz", "me", "m"
                ],
                "unit": [
                    "einheit", "eh", "me", "einh", "unit",
                    "mengeneinheit", "vpe"
                ],
                "unit_price": [
                    "einzelpreis", "e-preis", "ep", "preis/eh", "preis",
                    "stückpreis", "stk-preis", "unit price", "einzelpr",
                    "ek", "vk", "netto-ep", "preis netto"
                ],
                "total_price": [
                    "gesamtpreis", "gesamt", "summe", "betrag", "netto",
                    "total", "gesamtbetrag", "positionssumme", "nettobetrag",
                    "wert", "ges-preis", "gespreis", "amount"
                ],
                "vat_rate": [
                    "mwst", "ust", "steuer", "%", "mwst%", "ust%",
                    "steuersatz", "vat", "tax"
                ]
            }


# Singleton Header-Mapping
HEADER_MAPPING = HeaderMapping()


# =============================================================================
# GERMAN DECIMAL PARSING
# =============================================================================

def parse_german_decimal(value: str) -> Optional[Decimal]:
    """
    Konvertiert deutsches Zahlenformat zu Decimal.

    Beispiele:
        "1.234,56" -> Decimal("1234.56")
        "1234,56"  -> Decimal("1234.56")
        "50,00"    -> Decimal("50.00")
        "1.234"    -> Decimal("1234")  (nur Tausendertrenner)
        "50"       -> Decimal("50")

    Args:
        value: String mit deutschem Zahlenformat

    Returns:
        Decimal oder None bei Parsing-Fehlern
    """
    if not value:
        return None

    # Bereinigen
    cleaned = value.strip()

    # Entferne Währungssymbole und Text
    cleaned = re.sub(r'[€$£\s]', '', cleaned)
    cleaned = re.sub(r'(EUR|USD|GBP|CHF)', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    if not cleaned:
        return None

    # Erkenne Format: deutsches Format verwendet Komma als Dezimaltrenner
    # und Punkt als Tausendertrenner
    has_comma = ',' in cleaned
    has_dot = '.' in cleaned

    try:
        if has_comma and has_dot:
            # Deutsches Format: "1.234,56"
            # Entferne Tausendertrenner (Punkte), ersetze Komma durch Punkt
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif has_comma:
            # Nur Komma: "1234,56" oder "50,00"
            cleaned = cleaned.replace(',', '.')
        elif has_dot:
            # Nur Punkt - könnte Tausendertrenner oder Dezimaltrenner sein
            # Wenn genau 3 Ziffern nach dem Punkt -> Tausendertrenner
            parts = cleaned.split('.')
            if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
                # Tausendertrenner: "1.234" -> "1234"
                cleaned = cleaned.replace('.', '')
            # Sonst: Dezimaltrenner: "50.00" -> "50.00"

        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        logger.debug(f"Konnte Zahl nicht parsen: '{value}' -> '{cleaned}'")
        return None


# =============================================================================
# LINE ITEM EXTRACTION SERVICE
# =============================================================================

class LineItemExtractionService:
    """
    Service zum Extrahieren von Positionen aus Dokumenten.

    Primäre Methode: Docling-Tabellen analysieren
    Fallback: Regex-basierte Extraktion aus OCR-Text
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._header_mapping = HEADER_MAPPING.PATTERNS

    async def extract_from_tables(
        self,
        tables: List[TableStructure],
        document_type: ExtractedDocumentType = ExtractedDocumentType.INVOICE
    ) -> List[ExtractedLineItem]:
        """
        Extrahiert Positionen aus Docling-Tabellen.

        Args:
            tables: Liste von TableStructure-Objekten von Docling
            document_type: Dokumenttyp für Kontextoptimierung

        Returns:
            Liste von ExtractedLineItem-Objekten
        """
        all_items: List[ExtractedLineItem] = []

        for table_idx, table in enumerate(tables):
            try:
                items = self._extract_from_single_table(table, table_idx)
                all_items.extend(items)
            except Exception as e:
                logger.warning(f"Fehler bei Tabelle {table_idx}: {e}")
                continue

        # Renummeriere Positionen
        for idx, item in enumerate(all_items, start=1):
            item.position = idx

        logger.info(f"Extrahiert: {len(all_items)} Positionen aus {len(tables)} Tabellen")
        return all_items

    def _extract_from_single_table(
        self,
        table: TableStructure,
        table_idx: int = 0
    ) -> List[ExtractedLineItem]:
        """
        Extrahiert Positionen aus einer einzelnen Tabelle.

        Algorithmus:
        1. Header-Zeile identifizieren
        2. Spalten-Mapping erstellen
        3. Datenzeilen iterieren und Werte extrahieren
        """
        if table.num_rows < 2 or table.num_cols < 2:
            logger.debug(f"Tabelle {table_idx} zu klein: {table.num_rows}x{table.num_cols}")
            return []

        # Schritt 1: Header-Zeile finden
        header_row_idx = self._identify_header_row(table)
        if header_row_idx < 0:
            logger.debug(f"Keine Header-Zeile in Tabelle {table_idx} gefunden")
            return []

        # Schritt 2: Spalten-Mapping erstellen
        header_cells = table.get_row(header_row_idx)
        column_mapping = self._create_column_mapping(header_cells)

        if not column_mapping:
            logger.debug(f"Kein Spalten-Mapping möglich für Tabelle {table_idx}")
            return []

        # Mindestens Beschreibung oder Preis muss vorhanden sein
        required_fields = {"description", "total_price", "unit_price"}
        if not any(field in column_mapping.values() for field in required_fields):
            logger.debug(f"Keine relevanten Spalten in Tabelle {table_idx}: {column_mapping}")
            return []

        # Schritt 3: Datenzeilen extrahieren
        items = []
        for row_idx in range(header_row_idx + 1, table.num_rows):
            item = self._extract_row(table, row_idx, column_mapping)
            if item:
                items.append(item)

        return items

    def _identify_header_row(self, table: TableStructure) -> int:
        """
        Findet die Header-Zeile in einer Tabelle.

        Strategie:
        1. Zeilen mit is_header=True bevorzugen
        2. Zeilen mit mehreren Header-Keywords suchen

        Returns:
            Zeilenindex (0-basiert) oder -1 wenn nicht gefunden
        """
        # Strategie 1: is_header Flag prüfen
        for row_idx in range(min(table.num_rows, 3)):  # Erste 3 Zeilen prüfen
            row_cells = table.get_row(row_idx)
            if any(cell.is_header for cell in row_cells):
                return row_idx

        # Strategie 2: Zeile mit den meisten Header-Keywords finden
        best_row = -1
        best_score = 0

        for row_idx in range(min(table.num_rows, 3)):  # Erste 3 Zeilen prüfen
            row_cells = table.get_row(row_idx)
            score = 0

            for cell in row_cells:
                cell_text = cell.text.strip().lower()
                for field, patterns in self._header_mapping.items():
                    if any(pattern in cell_text for pattern in patterns):
                        score += 1
                        break

            if score > best_score:
                best_score = score
                best_row = row_idx

        # Mindestens 1 Header-Keyword erforderlich (gesenkt von 2)
        # Dies verbessert die Erkennung bei einfachen Tabellen mit nur einer
        # markanten Spalte (z.B. nur "Beschreibung" oder nur "Preis")
        if best_score >= 1:
            return best_row

        return -1

    def _create_column_mapping(
        self,
        header_cells: List[TableCell]
    ) -> Dict[int, str]:
        """
        Erstellt ein Mapping von Spaltenindex zu Feldname.

        Verwendet zwei Passes:
        1. Exakte Matches (gesamter Header == Pattern)
        2. Teilmatches (Pattern in Header, min 3 Zeichen)

        Args:
            header_cells: Liste der Zellen in der Header-Zeile

        Returns:
            Dict: {spalten_index: feldname}
        """
        column_mapping: Dict[int, str] = {}
        used_fields: Set[str] = set()
        unmatched_cells: List[TableCell] = []

        # Pass 1: Exakte Matches
        for cell in header_cells:
            cell_text = cell.text.strip().lower()
            col_idx = cell.col
            matched = False

            for field, patterns in self._header_mapping.items():
                if field in used_fields:
                    continue

                for pattern in patterns:
                    if pattern == cell_text:
                        column_mapping[col_idx] = field
                        used_fields.add(field)
                        matched = True
                        break

                if matched:
                    break

            if not matched:
                unmatched_cells.append(cell)

        # Pass 2: Teilmatches (nur für noch nicht gematchte Zellen)
        # Mindestens 3 Zeichen für Teilmatch, um zu kurze Patterns zu vermeiden
        for cell in unmatched_cells:
            cell_text = cell.text.strip().lower()
            col_idx = cell.col

            for field, patterns in self._header_mapping.items():
                if field in used_fields:
                    continue

                for pattern in patterns:
                    # Nur Teilmatch wenn Pattern >= 3 Zeichen lang
                    if len(pattern) >= 3 and pattern in cell_text:
                        column_mapping[col_idx] = field
                        used_fields.add(field)
                        break

                if col_idx in column_mapping:
                    break

        logger.debug(f"Spalten-Mapping: {column_mapping}")
        return column_mapping

    def _extract_row(
        self,
        table: TableStructure,
        row_idx: int,
        column_mapping: Dict[int, str]
    ) -> Optional[ExtractedLineItem]:
        """
        Extrahiert eine Position aus einer Tabellenzeile.

        Args:
            table: Die Tabelle
            row_idx: Zeilenindex
            column_mapping: Spalte -> Feldname Mapping

        Returns:
            ExtractedLineItem oder None wenn ungültig
        """
        row_cells = table.get_row(row_idx)
        if not row_cells:
            return None

        # Werte sammeln
        values: Dict[str, str] = {}
        for cell in row_cells:
            field = column_mapping.get(cell.col)
            if field:
                values[field] = cell.text.strip()

        # Mindestens Beschreibung oder ein Preisfeld erforderlich
        if not values.get("description") and not values.get("total_price"):
            return None

        # Leere Zeilen überspringen
        if all(not v for v in values.values()):
            return None

        # ExtractedLineItem erstellen
        try:
            item = ExtractedLineItem(
                position=row_idx,  # Wird später renummeriert
                article_number=values.get("article_number") or None,
                description=values.get("description", "Unbekannte Position"),
                quantity=parse_german_decimal(values.get("quantity", "")),
                unit=values.get("unit") or None,
                unit_price=parse_german_decimal(values.get("unit_price", "")),
                total_price=parse_german_decimal(values.get("total_price", "")),
                vat_rate=parse_german_decimal(values.get("vat_rate", ""))
            )

            # Plausibilitaetsprüfung: Zeile muss sinnvollen Inhalt haben
            if self._is_valid_line_item(item):
                return item

        except Exception as e:
            logger.debug(f"Fehler beim Erstellen von LineItem in Zeile {row_idx}: {e}")

        return None

    def _is_valid_line_item(self, item: ExtractedLineItem) -> bool:
        """
        Prüft ob ein LineItem gültig ist.

        Kriterien:
        - Beschreibung nicht leer (oder nur Zahlen)
        - Mindestens ein Preisfeld vorhanden
        - Keine reinen Summenzeilen
        """
        # Beschreibung prüfen
        desc = item.description.strip()
        if not desc or desc.lower() in [
            "summe", "gesamt", "total", "zwischensumme",
            "netto", "brutto", "mwst", "ust", "endbetrag",
            "übertrag", "saldo", "---"
        ]:
            return False

        # Mindestens ein Wert sollte vorhanden sein
        if item.total_price is None and item.unit_price is None and item.quantity is None:
            return False

        return True

    async def extract_from_text(
        self,
        text: str,
        document_type: ExtractedDocumentType = ExtractedDocumentType.INVOICE
    ) -> List[ExtractedLineItem]:
        """
        Fallback: Extrahiert Positionen mittels Regex aus OCR-Text.

        Erkennt Muster wie:
        - "1  Beratungsleistung  8 Std  125,00  1.000,00"
        - "Pos 1: Artikel XYZ - Menge 5 - Preis 50,00 EUR"

        Args:
            text: OCR-Text des Dokuments
            document_type: Dokumenttyp

        Returns:
            Liste von ExtractedLineItem-Objekten
        """
        items: List[ExtractedLineItem] = []
        position_counter = 1

        # Pattern 1: Klassische Positionszeilen mit numerischer Position
        # Format: [Pos] [Beschreibung] [Menge] [Einheit] [Preis] [Gesamt]
        pattern_numeric_pos = re.compile(
            r'^\s*'
            r'(\d{1,3})\s+'  # Position (1-3 Ziffern)
            r'(.{3,80}?)\s+'  # Beschreibung (3-80 Zeichen)
            r'(\d+(?:[,\.]\d+)?)\s*'  # Menge
            r'(stk|st|stck|kg|l|m|h|std|psch|pieces?|pcs?|unit)?\s*'  # Einheit
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*'  # Preis (auch 3,40)
            r'(?:€|EUR)?\s*'  # Währung (optional)
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2}))?',  # Gesamtpreis (optional)
            re.IGNORECASE | re.MULTILINE
        )

        # Pattern 2: Artikelnummer-basierte Zeilen (z.B. GW-E5326.00)
        # Format: [ArtNr] [Beschreibung] [Menge] [Einheit] [E-Preis] [Gesamt]
        # Artikelnummer: Buchstaben/Zahlen mit Bindestrich/Punkt
        pattern_article_nr = re.compile(
            r'^\s*'
            r'([A-Z0-9]{1,4}[-]?[A-Z0-9]{1,10}(?:[-\.][A-Z0-9]+)*)\s+'  # Artikelnummer (flexibler)
            r'(.+?)\s+'  # Beschreibung (bis zur nächsten Zahl)
            r'(\d+)\s*'  # Menge (ganze Zahl)
            r'(stk|st|stck|kg|l|m|h|std|psch|pieces?|pcs?|unit|stück)?\s+'  # Einheit (mit Whitespace danach)
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2}))\s*'  # E-Preis
            r'(?:€|EUR)?\s*'
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2}))',  # Gesamtpreis (erforderlich)
            re.IGNORECASE | re.MULTILINE
        )

        # Pattern 3: Einfaches Format ohne Position/Artikelnummer
        # Format: [Beschreibung] [Menge] [Einheit] [E-Preis] [Gesamt]
        pattern_simple = re.compile(
            r'^\s*'
            r'([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß0-9\s,.\-/]{5,60}?)\s+'  # Beschreibung
            r'(\d+(?:[,\.]\d+)?)\s*'  # Menge
            r'(stk|st|stck|kg|l|m|h|std|psch|pieces?|pcs?|unit|stück)?\s*'  # Einheit
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*'  # E-Preis
            r'(?:€|EUR)?\s*'
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2}))',  # Gesamtpreis (erforderlich)
            re.IGNORECASE | re.MULTILINE
        )

        # Versuch Pattern 1: Numerische Positionen
        for match in pattern_numeric_pos.finditer(text):
            try:
                pos = int(match.group(1))
                desc = match.group(2).strip()
                qty = parse_german_decimal(match.group(3))
                unit = match.group(4)
                price = parse_german_decimal(match.group(5))
                total = parse_german_decimal(match.group(6)) if match.group(6) else None

                if total is None and qty and price:
                    total = qty * price

                item = ExtractedLineItem(
                    position=pos,
                    description=desc,
                    quantity=qty,
                    unit=unit.lower() if unit else None,
                    unit_price=price,
                    total_price=total
                )

                if self._is_valid_line_item(item):
                    items.append(item)

            except Exception as e:
                logger.debug(f"Pattern 1 Extraktion fehlgeschlagen: {e}")
                continue

        # Falls Pattern 1 nichts fand, versuch Pattern 2: Artikelnummern
        if not items:
            for match in pattern_article_nr.finditer(text):
                try:
                    article_nr = match.group(1).strip()
                    desc = match.group(2).strip()
                    qty = parse_german_decimal(match.group(3))
                    unit = match.group(4)
                    price = parse_german_decimal(match.group(5))
                    total = parse_german_decimal(match.group(6)) if match.group(6) else None

                    if total is None and qty and price:
                        total = qty * price

                    item = ExtractedLineItem(
                        position=position_counter,
                        article_number=article_nr,
                        description=desc,
                        quantity=qty,
                        unit=unit.lower() if unit else None,
                        unit_price=price,
                        total_price=total
                    )

                    if self._is_valid_line_item(item):
                        items.append(item)
                        position_counter += 1

                except Exception as e:
                    logger.debug(f"Pattern 2 Extraktion fehlgeschlagen: {e}")
                    continue

        # Falls auch Pattern 2 nichts fand, versuch Pattern 3: Einfaches Format
        if not items:
            for match in pattern_simple.finditer(text):
                try:
                    desc = match.group(1).strip()
                    qty = parse_german_decimal(match.group(2))
                    unit = match.group(3)
                    price = parse_german_decimal(match.group(4))
                    total = parse_german_decimal(match.group(5)) if match.group(5) else None

                    if total is None and qty and price:
                        total = qty * price

                    item = ExtractedLineItem(
                        position=position_counter,
                        description=desc,
                        quantity=qty,
                        unit=unit.lower() if unit else None,
                        unit_price=price,
                        total_price=total
                    )

                    if self._is_valid_line_item(item):
                        items.append(item)
                        position_counter += 1

                except Exception as e:
                    logger.debug(f"Pattern 3 Extraktion fehlgeschlagen: {e}")
                    continue

        # Pattern 4: Fragmentierte OCR-Ausgabe rekonstruieren
        if not items:
            items = self._extract_from_fragmented_ocr(text)

        logger.info(f"Regex-Fallback: {len(items)} Positionen extrahiert")
        return items

    def _extract_from_fragmented_ocr(self, text: str) -> List[ExtractedLineItem]:
        """
        Extrahiert Line Items aus fragmentierter OCR-Ausgabe.

        Behandelt Fälle, in denen OCR Tabellenspalten als separate Zeilen liest:
        1.305,60
        3,40
        384 Pieces
        Stapelbox 500 x 300 x 260 mm
        GW-E5326.00
        ...
        """
        items: List[ExtractedLineItem] = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Pattern für Artikelnummern (z.B. GW-E5326.00, ABC-123)
        article_pattern = re.compile(
            r'^([A-Z]{1,4}[-]?[A-Z0-9]{1,10}(?:[-\.][A-Z0-9]+)*)$',
            re.IGNORECASE
        )

        # Pattern für Menge + Einheit (z.B. "384 Pieces", "10 Stk")
        qty_unit_pattern = re.compile(
            r'^(\d+(?:[,\.]\d+)?)\s*(pieces?|pcs?|stk|st|stck|kg|l|m|h|std|psch|unit|stück)$',
            re.IGNORECASE
        )

        # Pattern für Preise (deutsches Format)
        price_pattern = re.compile(
            r'^(\d{1,3}(?:\.\d{3})*(?:,\d{1,2}))(?:\s*[€V✓🗸])?$'
        )

        # Pattern für einfache Dezimalzahlen (Einzelpreis wie 3,40)
        simple_price_pattern = re.compile(r'^(\d{1,3},\d{2})$')

        # Sammle potentielle Komponenten
        article_numbers: List[str] = []
        descriptions: List[str] = []
        quantities: List[Decimal] = []
        units: List[str] = []
        prices: List[Decimal] = []

        for line in lines:
            # Skip Header-Keywords und Summenzeilen
            line_lower = line.lower()
            if any(kw in line_lower for kw in [
                'description', 'no.', 'quantity', 'measure', 'unit price',
                'amount', 'total', 'summe', 'gesamt', 'netto', 'brutto',
                'mwst', 'ust', 'eur'
            ]):
                continue

            # Artikelnummer?
            if article_pattern.match(line):
                article_numbers.append(line)
                continue

            # Menge + Einheit?
            qty_match = qty_unit_pattern.match(line)
            if qty_match:
                qty = parse_german_decimal(qty_match.group(1))
                if qty:
                    quantities.append(qty)
                    units.append(qty_match.group(2).lower())
                continue

            # Preis (größer)?
            price_match = price_pattern.match(line)
            if price_match:
                price = parse_german_decimal(price_match.group(1))
                if price:
                    prices.append(price)
                continue

            # Einfacher Preis (kleiner, wie Einzelpreis)?
            simple_match = simple_price_pattern.match(line)
            if simple_match:
                price = parse_german_decimal(simple_match.group(1))
                if price:
                    prices.append(price)
                continue

            # Sonst könnte es eine Beschreibung sein
            if len(line) > 5 and re.search(r'[a-zA-ZäöüÄÖÜß]', line):
                if not re.match(r'^[\d\s,\.]+$', line):
                    descriptions.append(line)

        # Versuche die Komponenten zusammenzuführen
        if descriptions and prices:
            sorted_prices = sorted(prices, reverse=True)
            full_description = ' '.join(descriptions)

            item = ExtractedLineItem(
                position=1,
                article_number=article_numbers[0] if article_numbers else None,
                description=full_description,
                quantity=quantities[0] if quantities else None,
                unit=units[0] if units else None,
                unit_price=sorted_prices[-1] if len(sorted_prices) > 1 else None,
                total_price=sorted_prices[0] if sorted_prices else None,
            )

            if self._is_valid_line_item(item):
                items.append(item)
                logger.info(
                    f"Fragmentierte OCR rekonstruiert: "
                    f"Art={item.article_number}, "
                    f"Menge={item.quantity}, "
                    f"Gesamt={item.total_price}"
                )

        return items

    def validate_against_total(
        self,
        items: List[ExtractedLineItem],
        expected_net: Optional[Decimal]
    ) -> Tuple[bool, Optional[Decimal]]:
        """
        Validiert ob Summe der Positionen dem Nettobetrag entspricht.

        Args:
            items: Liste der Positionen
            expected_net: Erwarteter Nettobetrag

        Returns:
            (is_valid, calculated_sum)
        """
        if not items or expected_net is None:
            return True, None

        calculated_sum = Decimal("0")
        for item in items:
            if item.total_price:
                calculated_sum += item.total_price

        # Toleranz: 1% oder 2 EUR
        tolerance = max(expected_net * Decimal("0.01"), Decimal("2.00"))

        is_valid = abs(calculated_sum - expected_net) <= tolerance

        if not is_valid:
            logger.warning(
                f"Positionssumme ({calculated_sum}) weicht von Nettobetrag ({expected_net}) ab"
            )

        return is_valid, calculated_sum


# =============================================================================
# SINGLETON
# =============================================================================

_line_item_service: Optional[LineItemExtractionService] = None


def get_line_item_extraction_service() -> LineItemExtractionService:
    """Gibt die Singleton-Instanz des LineItemExtractionService zurück."""
    global _line_item_service
    if _line_item_service is None:
        _line_item_service = LineItemExtractionService()
    return _line_item_service


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    "LineItemExtractionService",
    "get_line_item_extraction_service",
    "parse_german_decimal",
]
