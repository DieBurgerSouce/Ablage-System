# -*- coding: utf-8 -*-
"""Semantic Validation Service für OCR-Ergebnisse.

Phase 2.1: Validiert OCR-Extrakte gegen Stammdaten und Business Rules.

Features:
- Kundennummern gegen Lexware Master Data validieren
- Lieferantennamen Fuzzy-Matchen
- IBANs gegen bekannte Konten prüfen
- Betragsgrenzen und Plausibilitäts-Checks
- Konsistenz-Checks (Summe = Netto + MwSt)

SECURITY: Keine sensiblen Daten in Logs.
"""

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple, Union
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, Document

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums und Models
# =============================================================================


class ValidationSeverity(str, Enum):
    """Schweregrad der Validierungsmeldung."""

    ERROR = "error"  # Kritisch, muss korrigiert werden
    WARNING = "warning"  # Sollte geprüft werden
    INFO = "info"  # Hinweis
    SUCCESS = "success"  # Validierung erfolgreich


class ValidationType(str, Enum):
    """Typ der Validierung."""

    # Master Data Validation
    CUSTOMER_NUMBER = "customer_number"
    SUPPLIER_NAME = "supplier_name"
    IBAN = "iban"
    VAT_ID = "vat_id"
    ENTITY_MATCH = "entity_match"

    # Amount Validation
    AMOUNT_PLAUSIBILITY = "amount_plausibility"
    AMOUNT_CONSISTENCY = "amount_consistency"
    TAX_CALCULATION = "tax_calculation"

    # Format Validation
    DATE_FORMAT = "date_format"
    INVOICE_NUMBER = "invoice_number"
    REFERENCE_FORMAT = "reference_format"

    # Cross-Field Validation
    FIELD_CONSISTENCY = "field_consistency"
    DUPLICATE_CHECK = "duplicate_check"


class ValidationResult(BaseModel):
    """Einzelnes Validierungsergebnis."""

    validation_type: ValidationType
    field_name: str
    severity: ValidationSeverity
    message: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    suggestion: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SemanticValidationReport(BaseModel):
    """Vollständiger Validierungsbericht für ein Dokument."""

    document_id: str
    validated_at: datetime
    total_checks: int
    errors: int
    warnings: int
    passed: int
    overall_score: float = Field(ge=0.0, le=1.0)
    results: List[ValidationResult]
    matched_entity: Optional[Dict[str, Any]] = None
    suggestions: List[str] = Field(default_factory=list)


# =============================================================================
# Utility Functions
# =============================================================================


def normalize_text(text: str) -> str:
    """Normalisiert Text für Vergleiche."""
    if not text:
        return ""
    text = str(text).strip().lower()
    # Umlaute normalisieren
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    # Mehrfache Leerzeichen entfernen
    text = re.sub(r"\s+", " ", text)
    return text


def calculate_similarity(text1: str, text2: str) -> float:
    """Berechnet Ähnlichkeit zwischen zwei Texten (0.0-1.0)."""
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(
        None, normalize_text(text1), normalize_text(text2)
    ).ratio()


def validate_iban_checksum(iban: str) -> bool:
    """Validiert IBAN-Prüfsumme (ISO 7064 Mod 97-10)."""
    if not iban:
        return False

    # Entferne Leerzeichen und konvertiere zu Großbuchstaben
    iban = iban.replace(" ", "").upper()

    # Mindestlänge prüfen
    if len(iban) < 15:
        return False

    # Verschiebe die ersten 4 Zeichen ans Ende
    rearranged = iban[4:] + iban[:4]

    # Ersetze Buchstaben durch Zahlen (A=10, B=11, ..., Z=35)
    numeric = ""
    for char in rearranged:
        if char.isdigit():
            numeric += char
        else:
            numeric += str(ord(char) - 55)

    # Mod 97 Prüfung
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def validate_vat_id_format(vat_id: str) -> Tuple[bool, str]:
    """
    Validiert USt-ID Format (nur Format, keine externe Prüfung).

    Returns:
        Tuple von (is_valid, message)
    """
    if not vat_id:
        return False, "Keine USt-ID angegeben"

    vat_id = vat_id.replace(" ", "").upper()

    # Deutsche USt-ID: DE + 9 Ziffern
    if vat_id.startswith("DE"):
        if re.match(r"^DE\d{9}$", vat_id):
            return True, "Gültiges DE USt-ID Format"
        return False, "Deutsche USt-ID muss DE + 9 Ziffern sein"

    # Österreich: ATU + 8 Zeichen
    if vat_id.startswith("ATU"):
        if re.match(r"^ATU\d{8}$", vat_id):
            return True, "Gültiges AT USt-ID Format"
        return False, "Österreichische USt-ID muss ATU + 8 Ziffern sein"

    # Weitere EU-Länder (vereinfacht)
    eu_patterns = {
        "BE": r"^BE\d{10}$",
        "NL": r"^NL\d{9}B\d{2}$",
        "FR": r"^FR[A-Z0-9]{2}\d{9}$",
        "IT": r"^IT\d{11}$",
        "ES": r"^ES[A-Z0-9]\d{7}[A-Z0-9]$",
        "PL": r"^PL\d{10}$",
        "CZ": r"^CZ\d{8,10}$",
    }

    country_code = vat_id[:2]
    if country_code in eu_patterns:
        if re.match(eu_patterns[country_code], vat_id):
            return True, f"Gültiges {country_code} USt-ID Format"
        return False, f"Ungültiges {country_code} USt-ID Format"

    return False, f"Unbekanntes Länder-Präfix: {country_code}"


def parse_amount(amount_str: str) -> Optional[Decimal]:
    """Parst Betragsstring zu Decimal."""
    if not amount_str:
        return None

    # Entferne Währungssymbole und Whitespace
    cleaned = re.sub(r"[€$£\s]", "", str(amount_str))

    # Deutsche Notation: 1.234,56 -> 1234.56
    if "," in cleaned and "." in cleaned:
        # Tausendertrennzeichen entfernen
        cleaned = cleaned.replace(".", "")
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned:
        # Nur Komma = Dezimaltrennzeichen
        cleaned = cleaned.replace(",", ".")

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


# =============================================================================
# Semantic Validation Service
# =============================================================================


class SemanticValidationService:
    """
    Service für semantische Validierung von OCR-Ergebnissen.

    Phase 2.1: Validiert extrahierte Daten gegen:
    - Lexware Master Data (Kunden/Lieferanten)
    - Business Rules (Plausibilität, Konsistenz)
    - Format-Regeln (IBAN, USt-ID, Datumsformate)

    Verwendung:
        service = SemanticValidationService(db)
        report = await service.validate_document(document_id)
    """

    # Konfiguration
    SIMILARITY_THRESHOLD = 0.75  # Mindest-Ähnlichkeit für Fuzzy-Match
    MAX_AMOUNT_DEVIATION = Decimal("0.02")  # 2 Cent Toleranz bei Betragsberechnung
    MAX_TAX_DEVIATION_PERCENT = Decimal("0.5")  # 0.5% Toleranz bei MwSt-Berechnung

    # Standard MwSt-Sätze Deutschland
    VALID_TAX_RATES = [
        Decimal("0"),  # Steuerfrei
        Decimal("7"),  # Ermäßigt
        Decimal("19"),  # Normal
    ]

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den Service.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db

    async def validate_document(
        self,
        document_id: str,
        extracted_data: Optional[Dict[str, Any]] = None,
    ) -> SemanticValidationReport:
        """
        Führt vollständige semantische Validierung für ein Dokument durch.

        Args:
            document_id: Document UUID
            extracted_data: Optional vorgefüllte extrahierte Daten

        Returns:
            SemanticValidationReport mit allen Ergebnissen
        """
        # Hole Dokument wenn extracted_data nicht gegeben
        if extracted_data is None:
            document = await self._get_document(document_id)
            if not document:
                return self._create_error_report(
                    document_id, "Dokument nicht gefunden"
                )
            extracted_data = document.extracted_data or {}

        results: List[ValidationResult] = []

        # 1. Master Data Validation
        entity_match = await self._validate_against_master_data(
            extracted_data, results
        )

        # 2. Amount Validation
        self._validate_amounts(extracted_data, results)

        # 3. Format Validation
        self._validate_formats(extracted_data, results)

        # 4. Cross-Field Consistency
        self._validate_field_consistency(extracted_data, results)

        # Calculate overall score
        errors = sum(1 for r in results if r.severity == ValidationSeverity.ERROR)
        warnings = sum(1 for r in results if r.severity == ValidationSeverity.WARNING)
        passed = sum(1 for r in results if r.severity == ValidationSeverity.SUCCESS)

        total = len(results)
        if total > 0:
            # Score: 100% - (Errors * 10% + Warnings * 2%)
            score = max(0, 1.0 - (errors * 0.1 + warnings * 0.02))
        else:
            score = 1.0

        # Collect suggestions
        suggestions = [
            r.suggestion for r in results
            if r.suggestion and r.severity in (ValidationSeverity.ERROR, ValidationSeverity.WARNING)
        ]

        return SemanticValidationReport(
            document_id=document_id,
            validated_at=datetime.now(timezone.utc),
            total_checks=total,
            errors=errors,
            warnings=warnings,
            passed=passed,
            overall_score=round(score, 3),
            results=results,
            matched_entity=entity_match,
            suggestions=suggestions,
        )

    # =========================================================================
    # Master Data Validation
    # =========================================================================

    async def _validate_against_master_data(
        self,
        extracted_data: Dict[str, Any],
        results: List[ValidationResult],
    ) -> Optional[Dict[str, Any]]:
        """
        Validiert gegen Lexware Master Data.

        Returns:
            Matched Entity Info oder None
        """
        entity_match = None

        # 1. Kundennummer validieren
        customer_number = extracted_data.get("customer_number") or extracted_data.get("kd_nr")
        if customer_number:
            entity = await self._find_entity_by_customer_number(customer_number)
            if entity:
                results.append(ValidationResult(
                    validation_type=ValidationType.CUSTOMER_NUMBER,
                    field_name="customer_number",
                    severity=ValidationSeverity.SUCCESS,
                    message=f"Kundennummer {customer_number[:4]}*** gefunden",
                    actual_value=customer_number,
                    confidence=0.99,
                    metadata={"entity_id": str(entity.id)},
                ))
                entity_match = {
                    "id": str(entity.id),
                    "name": entity.name,
                    "match_type": "customer_number",
                    "confidence": 0.99,
                }
            else:
                results.append(ValidationResult(
                    validation_type=ValidationType.CUSTOMER_NUMBER,
                    field_name="customer_number",
                    severity=ValidationSeverity.WARNING,
                    message=f"Kundennummer nicht im Stamm gefunden",
                    actual_value=customer_number,
                    suggestion="Prüfen Sie die Kundennummer oder legen Sie den Kunden neu an",
                    confidence=0.0,
                ))

        # 2. Lieferantenname Fuzzy-Match
        supplier_name = extracted_data.get("supplier_name") or extracted_data.get("vendor")
        if supplier_name and not entity_match:
            entity, similarity = await self._find_entity_by_name_fuzzy(supplier_name)
            if entity and similarity >= self.SIMILARITY_THRESHOLD:
                results.append(ValidationResult(
                    validation_type=ValidationType.SUPPLIER_NAME,
                    field_name="supplier_name",
                    severity=ValidationSeverity.SUCCESS if similarity > 0.9 else ValidationSeverity.INFO,
                    message=f"Lieferant gefunden (Ähnlichkeit: {similarity:.0%})",
                    actual_value=supplier_name,
                    expected_value=entity.name,
                    confidence=similarity,
                    metadata={"entity_id": str(entity.id)},
                ))
                if not entity_match:
                    entity_match = {
                        "id": str(entity.id),
                        "name": entity.name,
                        "match_type": "fuzzy_name",
                        "confidence": similarity,
                    }
            elif supplier_name and len(supplier_name) > 3:
                results.append(ValidationResult(
                    validation_type=ValidationType.SUPPLIER_NAME,
                    field_name="supplier_name",
                    severity=ValidationSeverity.INFO,
                    message="Kein passender Lieferant im Stamm gefunden",
                    actual_value=supplier_name,
                    suggestion="Prüfen Sie den Lieferantennamen oder legen Sie ihn neu an",
                ))

        # 3. IBAN validieren
        iban = extracted_data.get("iban")
        if iban:
            entity = await self._find_entity_by_iban(iban)
            if entity:
                results.append(ValidationResult(
                    validation_type=ValidationType.IBAN,
                    field_name="iban",
                    severity=ValidationSeverity.SUCCESS,
                    message="IBAN im Stamm gefunden",
                    actual_value=iban[:8] + "****",
                    confidence=0.95,
                    metadata={"entity_id": str(entity.id)},
                ))
                if not entity_match:
                    entity_match = {
                        "id": str(entity.id),
                        "name": entity.name,
                        "match_type": "iban",
                        "confidence": 0.95,
                    }
            else:
                # IBAN Format prüfen
                if validate_iban_checksum(iban):
                    results.append(ValidationResult(
                        validation_type=ValidationType.IBAN,
                        field_name="iban",
                        severity=ValidationSeverity.INFO,
                        message="IBAN gültig, aber nicht im Stamm",
                        actual_value=iban[:8] + "****",
                    ))
                else:
                    results.append(ValidationResult(
                        validation_type=ValidationType.IBAN,
                        field_name="iban",
                        severity=ValidationSeverity.ERROR,
                        message="IBAN-Prüfsumme ungültig",
                        actual_value=iban[:8] + "****",
                        suggestion="Prüfen Sie die IBAN auf Tippfehler",
                    ))

        # 4. USt-ID validieren
        vat_id = extracted_data.get("vat_id") or extracted_data.get("ust_id")
        if vat_id:
            is_valid, message = validate_vat_id_format(vat_id)
            if is_valid:
                results.append(ValidationResult(
                    validation_type=ValidationType.VAT_ID,
                    field_name="vat_id",
                    severity=ValidationSeverity.SUCCESS,
                    message=message,
                    actual_value=vat_id,
                ))
            else:
                results.append(ValidationResult(
                    validation_type=ValidationType.VAT_ID,
                    field_name="vat_id",
                    severity=ValidationSeverity.WARNING,
                    message=message,
                    actual_value=vat_id,
                    suggestion="Prüfen Sie das Format der USt-ID",
                ))

        return entity_match

    async def _find_entity_by_customer_number(
        self, customer_number: str
    ) -> Optional[BusinessEntity]:
        """Sucht Entity nach Kundennummer."""
        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.primary_customer_number == customer_number.strip(),
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_entity_by_name_fuzzy(
        self, name: str, limit: int = 10
    ) -> Tuple[Optional[BusinessEntity], float]:
        """
        Sucht Entity per Fuzzy-Name-Match.

        Returns:
            Tuple von (Entity, Similarity Score)
        """
        # Hole potenzielle Matches (vereinfacht: alle nicht gelöschten)
        stmt = select(BusinessEntity).where(
            BusinessEntity.deleted_at.is_(None)
        ).limit(1000)

        result = await self.db.execute(stmt)
        entities = result.scalars().all()

        best_match = None
        best_similarity = 0.0

        for entity in entities:
            similarity = calculate_similarity(name, entity.name)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = entity

        return best_match, best_similarity

    async def _find_entity_by_iban(self, iban: str) -> Optional[BusinessEntity]:
        """Sucht Entity nach IBAN."""
        iban_clean = iban.replace(" ", "").upper()

        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.iban == iban_clean,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # Amount Validation
    # =========================================================================

    def _validate_amounts(
        self,
        extracted_data: Dict[str, Any],
        results: List[ValidationResult],
    ) -> None:
        """Validiert Beträge auf Plausibilität und Konsistenz."""

        # Parse amounts
        gross_amount = parse_amount(
            extracted_data.get("gross_amount") or extracted_data.get("total_amount") or "0"
        )
        net_amount = parse_amount(
            extracted_data.get("net_amount") or extracted_data.get("subtotal") or "0"
        )
        tax_amount = parse_amount(
            extracted_data.get("tax_amount") or extracted_data.get("vat_amount") or "0"
        )
        tax_rate = parse_amount(
            extracted_data.get("tax_rate") or extracted_data.get("vat_rate") or "19"
        )

        # 1. Plausibilitätsprüfung Bruttobetrag
        if gross_amount is not None:
            if gross_amount < 0:
                results.append(ValidationResult(
                    validation_type=ValidationType.AMOUNT_PLAUSIBILITY,
                    field_name="gross_amount",
                    severity=ValidationSeverity.ERROR,
                    message="Bruttobetrag ist negativ",
                    actual_value=str(gross_amount),
                    suggestion="Prüfen Sie, ob es sich um eine Gutschrift handelt",
                ))
            elif gross_amount > Decimal("1000000"):
                results.append(ValidationResult(
                    validation_type=ValidationType.AMOUNT_PLAUSIBILITY,
                    field_name="gross_amount",
                    severity=ValidationSeverity.WARNING,
                    message="Ungewöhnlich hoher Bruttobetrag",
                    actual_value=str(gross_amount),
                    suggestion="Bitte Betrag manuell verifizieren",
                ))
            else:
                results.append(ValidationResult(
                    validation_type=ValidationType.AMOUNT_PLAUSIBILITY,
                    field_name="gross_amount",
                    severity=ValidationSeverity.SUCCESS,
                    message="Bruttobetrag plausibel",
                    actual_value=str(gross_amount),
                ))

        # 2. Konsistenz: Brutto = Netto + MwSt
        if gross_amount and net_amount and tax_amount:
            expected_gross = net_amount + tax_amount
            deviation = abs(gross_amount - expected_gross)

            if deviation <= self.MAX_AMOUNT_DEVIATION:
                results.append(ValidationResult(
                    validation_type=ValidationType.AMOUNT_CONSISTENCY,
                    field_name="amount_calculation",
                    severity=ValidationSeverity.SUCCESS,
                    message="Betragsberechnung korrekt: Brutto = Netto + MwSt",
                    expected_value=str(expected_gross),
                    actual_value=str(gross_amount),
                ))
            else:
                results.append(ValidationResult(
                    validation_type=ValidationType.AMOUNT_CONSISTENCY,
                    field_name="amount_calculation",
                    severity=ValidationSeverity.ERROR,
                    message=f"Betragsabweichung: {deviation:.2f}€",
                    expected_value=str(expected_gross),
                    actual_value=str(gross_amount),
                    suggestion="Prüfen Sie Netto, MwSt und Brutto-Beträge",
                ))

        # 3. MwSt-Berechnung prüfen
        if net_amount and tax_amount and tax_rate:
            expected_tax = net_amount * (tax_rate / Decimal("100"))
            deviation_percent = (
                abs(tax_amount - expected_tax) / expected_tax * 100
                if expected_tax > 0 else Decimal("0")
            )

            if deviation_percent <= self.MAX_TAX_DEVIATION_PERCENT:
                results.append(ValidationResult(
                    validation_type=ValidationType.TAX_CALCULATION,
                    field_name="tax_calculation",
                    severity=ValidationSeverity.SUCCESS,
                    message=f"MwSt-Berechnung korrekt ({tax_rate}%)",
                    expected_value=str(round(expected_tax, 2)),
                    actual_value=str(tax_amount),
                ))
            else:
                results.append(ValidationResult(
                    validation_type=ValidationType.TAX_CALCULATION,
                    field_name="tax_calculation",
                    severity=ValidationSeverity.WARNING,
                    message=f"MwSt-Abweichung: {deviation_percent:.1f}%",
                    expected_value=str(round(expected_tax, 2)),
                    actual_value=str(tax_amount),
                    suggestion=f"Erwartete MwSt bei {tax_rate}%: {expected_tax:.2f}€",
                ))

        # 4. MwSt-Satz prüfen
        if tax_rate and tax_rate not in self.VALID_TAX_RATES:
            results.append(ValidationResult(
                validation_type=ValidationType.TAX_CALCULATION,
                field_name="tax_rate",
                severity=ValidationSeverity.WARNING,
                message=f"Ungewöhnlicher MwSt-Satz: {tax_rate}%",
                actual_value=str(tax_rate),
                suggestion="Übliche Sätze in DE: 0%, 7%, 19%",
            ))

    # =========================================================================
    # Format Validation
    # =========================================================================

    def _validate_formats(
        self,
        extracted_data: Dict[str, Any],
        results: List[ValidationResult],
    ) -> None:
        """Validiert Formate (Datum, Rechnungsnummer, etc.)."""

        # 1. Rechnungsnummer
        invoice_number = extracted_data.get("invoice_number")
        if invoice_number:
            if len(invoice_number) < 3:
                results.append(ValidationResult(
                    validation_type=ValidationType.INVOICE_NUMBER,
                    field_name="invoice_number",
                    severity=ValidationSeverity.WARNING,
                    message="Rechnungsnummer sehr kurz",
                    actual_value=invoice_number,
                ))
            elif len(invoice_number) > 50:
                results.append(ValidationResult(
                    validation_type=ValidationType.INVOICE_NUMBER,
                    field_name="invoice_number",
                    severity=ValidationSeverity.WARNING,
                    message="Rechnungsnummer ungewöhnlich lang",
                    actual_value=invoice_number[:50] + "...",
                ))
            else:
                results.append(ValidationResult(
                    validation_type=ValidationType.INVOICE_NUMBER,
                    field_name="invoice_number",
                    severity=ValidationSeverity.SUCCESS,
                    message="Rechnungsnummer-Format OK",
                    actual_value=invoice_number,
                ))

        # 2. Datum
        invoice_date = extracted_data.get("invoice_date") or extracted_data.get("date")
        if invoice_date:
            date_valid, date_msg = self._validate_date(invoice_date)
            results.append(ValidationResult(
                validation_type=ValidationType.DATE_FORMAT,
                field_name="invoice_date",
                severity=ValidationSeverity.SUCCESS if date_valid else ValidationSeverity.WARNING,
                message=date_msg,
                actual_value=str(invoice_date),
            ))

    def _validate_date(self, date_value: Union[str, datetime, None]) -> Tuple[bool, str]:
        """Validiert ein Datum."""
        if isinstance(date_value, datetime):
            # Prüfe auf Zukunftsdatum
            if date_value > datetime.now(timezone.utc):
                return False, "Rechnungsdatum liegt in der Zukunft"
            # Prüfe auf zu altes Datum (>10 Jahre)
            if (datetime.now(timezone.utc) - date_value).days > 3650:
                return False, "Rechnungsdatum liegt mehr als 10 Jahre zurück"
            return True, "Datum plausibel"

        if isinstance(date_value, str):
            # Versuche verschiedene Formate
            formats = [
                "%d.%m.%Y",
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%d-%m-%Y",
            ]
            for fmt in formats:
                try:
                    parsed = datetime.strptime(date_value, fmt)
                    return self._validate_date(parsed.replace(tzinfo=timezone.utc))
                except ValueError:
                    continue
            return False, "Datum konnte nicht geparst werden"

        return False, "Ungültiges Datumsformat"

    # =========================================================================
    # Cross-Field Validation
    # =========================================================================

    def _validate_field_consistency(
        self,
        extracted_data: Dict[str, Any],
        results: List[ValidationResult],
    ) -> None:
        """Validiert Konsistenz zwischen Feldern."""

        # 1. Fälligkeitsdatum nach Rechnungsdatum
        invoice_date = extracted_data.get("invoice_date")
        due_date = extracted_data.get("due_date")

        if invoice_date and due_date:
            try:
                if isinstance(invoice_date, str):
                    invoice_date = datetime.strptime(invoice_date, "%Y-%m-%d")
                if isinstance(due_date, str):
                    due_date = datetime.strptime(due_date, "%Y-%m-%d")

                if due_date < invoice_date:
                    results.append(ValidationResult(
                        validation_type=ValidationType.FIELD_CONSISTENCY,
                        field_name="due_date",
                        severity=ValidationSeverity.ERROR,
                        message="Fälligkeitsdatum liegt vor Rechnungsdatum",
                        expected_value=f">= {invoice_date}",
                        actual_value=str(due_date),
                        suggestion="Prüfen Sie Rechnungs- und Fälligkeitsdatum",
                    ))
            except (ValueError, TypeError) as e:
                # Datumsformat eigentlich in Format-Validation geprueft; hier nur Sichtbarkeit
                logger.debug("semantic_date_consistency_check_skipped", error_type=type(e).__name__)

        # 2. Zahlungsziel-Plausibilität
        payment_terms = extracted_data.get("payment_terms")
        if payment_terms:
            # Extrahiere Tage aus "30 Tage netto" etc.
            days_match = re.search(r"(\d+)\s*(?:Tage|days)", str(payment_terms), re.I)
            if days_match:
                days = int(days_match.group(1))
                if days > 180:
                    results.append(ValidationResult(
                        validation_type=ValidationType.FIELD_CONSISTENCY,
                        field_name="payment_terms",
                        severity=ValidationSeverity.WARNING,
                        message=f"Ungewöhnlich langes Zahlungsziel: {days} Tage",
                        actual_value=payment_terms,
                    ))

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_document(self, document_id: str) -> Optional[Document]:
        """Lädt ein Dokument aus der Datenbank."""
        try:
            stmt = select(Document).where(Document.id == UUID(document_id))
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except ValueError:
            return None

    def _create_error_report(
        self, document_id: str, error_message: str
    ) -> SemanticValidationReport:
        """Erstellt einen Fehlerbericht."""
        return SemanticValidationReport(
            document_id=document_id,
            validated_at=datetime.now(timezone.utc),
            total_checks=1,
            errors=1,
            warnings=0,
            passed=0,
            overall_score=0.0,
            results=[
                ValidationResult(
                    validation_type=ValidationType.FIELD_CONSISTENCY,
                    field_name="_document",
                    severity=ValidationSeverity.ERROR,
                    message=error_message,
                )
            ],
        )
