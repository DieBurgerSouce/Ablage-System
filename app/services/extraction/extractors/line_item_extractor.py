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
        """
        items: List[ExtractedLineItem] = []

        # Pattern 1: Standard format with position number
        # "1  Beratungsleistung  8 Std  125,00  1.000,00"
        pattern1 = re.compile(
            r"^\s*(\d{1,3})\s+"  # Position
            r"(.{3,80}?)\s+"  # Description
            r"(\d+(?:[,\.]\d+)?)\s*"  # Quantity
            r"(stk|st|stck|kg|l|m|h|std|psch)?\s*"  # Unit
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*"  # Unit price
            r"(?:€|EUR)?\s*"
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2}))?",  # Total
            re.IGNORECASE | re.MULTILINE,
        )

        # Pattern 2: Description-first format (common in German)
        # "Beratungsleistung IT                    1.000,00 EUR"
        pattern2 = re.compile(
            r"^\s*([A-ZÄÖÜa-zäöüß][A-Za-zäöüßÄÖÜ0-9\s\-\.]+?)\s{2,}"
            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)?\s*$",
            re.MULTILINE,
        )

        # Extract with pattern 1
        for match in pattern1.finditer(text):
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
            except (ValueError, IndexError):
                continue

        # Extract with pattern 2 if no items found
        if not items:
            pos = 1
            for match in pattern2.finditer(text):
                try:
                    description = match.group(1).strip()
                    if self._is_summary_row(description):
                        continue

                    item = ExtractedLineItem(
                        position=pos,
                        description=description,
                        total_price=parse_german_decimal(match.group(2)),
                        confidence=0.60,
                    )
                    if item.is_complete():
                        items.append(item)
                        pos += 1
                except (ValueError, IndexError):
                    continue

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
                    except ValueError:
                        pass

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
                    except ValueError:
                        pass

            # Total price
            if "total_price" in column_map:
                total_text = row[column_map["total_price"]].strip()
                if total_text:
                    try:
                        item.total_price = parse_german_decimal(total_text)
                    except ValueError:
                        pass

            # VAT rate
            if "vat_rate" in column_map:
                vat_text = row[column_map["vat_rate"]].strip()
                vat_match = re.search(r"(\d{1,2})", vat_text)
                if vat_match:
                    item.vat_rate = Decimal(vat_match.group(1))

            return item

        except Exception as e:
            logger.debug("row_extraction_error", error=str(e), row=row)
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
                except (ValueError, IndexError):
                    pass

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
