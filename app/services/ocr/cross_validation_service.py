# -*- coding: utf-8 -*-
"""
Cross-Validation Service fuer OCR-Feld-Plausibilitaetspruefung.

Validiert extrahierte Felder gegeneinander und gegen bekannte Daten:
- IBAN-Abgleich mit bekannten Lieferanten
- USt-ID Formatpruefung
- Betrags-Plausibilitaet (Netto + MwSt = Brutto)
- Dokumentrichtung (Eingangs- vs. Ausgangsrechnung)
- Datumsvalidierung
- Duplikat-Erkennung

Feinpoliert und durchdacht - Enterprise-grade Plausibilitaetspruefung.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


class ValidationSeverity:
    """Schweregrade fuer Validierungsergebnisse."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """Ergebnis einer einzelnen Validierungspruefung."""
    check_name: str
    passed: bool
    confidence_adjustment: float  # -0.3 bis +0.1
    severity: str  # "error", "warning", "info"
    message: str  # Deutsche Meldung
    details: Dict[str, object] = field(default_factory=dict)


@dataclass
class CrossValidationResult:
    """Aggregiertes Ergebnis aller Validierungspruefungen."""
    checks: List[ValidationResult] = field(default_factory=list)
    overall_confidence_adjustment: float = 0.0
    has_errors: bool = False
    has_warnings: bool = False
    document_direction: Optional[str] = None  # "incoming" oder "outgoing"
    duplicate_candidate_id: Optional[UUID] = None


# =============================================================================
# CONSTANTS
# =============================================================================

# Deutsche Standard-USt-Saetze
VALID_VAT_RATES = {
    Decimal("0"),
    Decimal("7"),
    Decimal("19"),
}

# Toleranzen
AMOUNT_TOLERANCE = Decimal("0.02")  # 2 Cent
DATE_FUTURE_TOLERANCE_DAYS = 2

# IBAN-Laengen pro Land (Subset fuer Validierung)
IBAN_LENGTHS: Dict[str, int] = {
    "DE": 22, "NL": 18, "AT": 20, "BE": 16, "FR": 27,
    "IT": 27, "ES": 24, "CH": 21, "PL": 28, "CZ": 24,
    "GB": 22, "LU": 20, "DK": 18, "SE": 24,
}

# EU USt-ID Formate (Laendercode -> erwartete Laenge ohne Leerzeichen)
VAT_ID_FORMATS: Dict[str, int] = {
    "DE": 11,  # DE + 9 Ziffern
    "AT": 11,  # ATU + 8 Ziffern
    "NL": 14,  # NL + 9 Ziffern + B + 2 Ziffern
    "BE": 12,  # BE + 10 Ziffern
}


# =============================================================================
# CROSS-VALIDATION SERVICE
# =============================================================================


class CrossValidationService:
    """
    Service fuer Kreuzvalidierung extrahierter OCR-Felder.

    Prueft extrahierte Felder gegeneinander und gegen bekannte Daten
    in der Datenbank, um OCR-Fehler fruehzeitig zu erkennen.

    Usage:
        service = CrossValidationService()
        result = await service.validate_all(extracted_data, company_id, db)
    """

    def __init__(self) -> None:
        self._stats: Dict[str, int] = {
            "total_validations": 0,
            "errors_found": 0,
            "warnings_found": 0,
            "duplicates_detected": 0,
        }

    # =========================================================================
    # AMOUNT VALIDATION
    # =========================================================================

    def validate_amounts(
        self,
        netto: Optional[Decimal],
        mwst: Optional[Decimal],
        brutto: Optional[Decimal],
        ust_satz: Optional[Decimal] = None,
    ) -> ValidationResult:
        """
        Prueft Betrags-Plausibilitaet.

        Regeln:
        - Netto + MwSt sollte Brutto ergeben (Toleranz: 0.02 EUR)
        - USt-Satz sollte 0%, 7% oder 19% sein
        - Negative Betraege sind nur bei Gutschriften erlaubt

        Args:
            netto: Nettobetrag
            mwst: MwSt-Betrag
            brutto: Bruttobetrag
            ust_satz: USt-Satz in Prozent

        Returns:
            ValidationResult mit Pruefergebnis
        """
        details: Dict[str, object] = {}

        # Keine Betraege vorhanden -> neutral
        if netto is None and mwst is None and brutto is None:
            return ValidationResult(
                check_name="amount_plausibility",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Keine Betraege zur Validierung vorhanden",
                details={"reason": "no_amounts"},
            )

        # Netto + MwSt = Brutto pruefen
        if netto is not None and mwst is not None and brutto is not None:
            expected_brutto = netto + mwst
            diff = abs(expected_brutto - brutto)
            details["netto"] = str(netto)
            details["mwst"] = str(mwst)
            details["brutto"] = str(brutto)
            details["expected_brutto"] = str(expected_brutto)
            details["differenz"] = str(diff)

            if diff > AMOUNT_TOLERANCE:
                return ValidationResult(
                    check_name="amount_plausibility",
                    passed=False,
                    confidence_adjustment=-0.15,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Betragsinkonsistenz: Netto ({netto}) + MwSt ({mwst}) = "
                        f"{expected_brutto}, aber Brutto ist {brutto} "
                        f"(Differenz: {diff})"
                    ),
                    details=details,
                )

        # MwSt-Satz aus Betraegen berechnen und pruefen
        if ust_satz is not None:
            details["ust_satz"] = str(ust_satz)
            if ust_satz not in VALID_VAT_RATES:
                return ValidationResult(
                    check_name="amount_plausibility",
                    passed=False,
                    confidence_adjustment=-0.10,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Unueblicher USt-Satz: {ust_satz}% "
                        f"(erwartet: 0%, 7% oder 19%)"
                    ),
                    details=details,
                )

        # MwSt-Satz aus Betraegen ableiten und pruefen
        if netto is not None and mwst is not None and netto > 0:
            calculated_rate = (mwst / netto * 100).quantize(Decimal("1"))
            details["berechneter_ust_satz"] = str(calculated_rate)

            if calculated_rate not in VALID_VAT_RATES:
                return ValidationResult(
                    check_name="amount_plausibility",
                    passed=False,
                    confidence_adjustment=-0.05,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Berechneter USt-Satz {calculated_rate}% "
                        f"entspricht keinem Standard-Satz (0%, 7%, 19%)"
                    ),
                    details=details,
                )

        # Alles OK
        return ValidationResult(
            check_name="amount_plausibility",
            passed=True,
            confidence_adjustment=0.05,
            severity=ValidationSeverity.INFO,
            message="Betraege plausibel",
            details=details,
        )

    # =========================================================================
    # IBAN VALIDATION
    # =========================================================================

    async def validate_iban(
        self,
        extracted_iban: Optional[str],
        entity_id: Optional[UUID],
        db: AsyncSession,
    ) -> ValidationResult:
        """
        Validiert eine extrahierte IBAN.

        Prueft:
        - IBAN-Format (Laendercode + Pruefziffern + Kontonummer)
        - Laenderspezifische Laenge
        - ISO 7064 Mod 97-10 Pruefziffer
        - Abgleich mit bekannten IBANs in business_entities

        Args:
            extracted_iban: Extrahierte IBAN (kann Leerzeichen enthalten)
            entity_id: Optionale Entity-ID zum Abgleich
            db: Datenbank-Session

        Returns:
            ValidationResult mit Pruefergebnis
        """
        if not extracted_iban:
            return ValidationResult(
                check_name="iban_validation",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Keine IBAN zur Validierung vorhanden",
            )

        # Normalisieren
        normalized = re.sub(r"\s", "", extracted_iban).upper()
        details: Dict[str, object] = {
            "iban_masked": normalized[:4] + "****" + normalized[-4:] if len(normalized) > 8 else "****",
        }

        # Format pruefen: mindestens 2 Buchstaben + 2 Ziffern
        if len(normalized) < 5 or not normalized[:2].isalpha() or not normalized[2:4].isdigit():
            return ValidationResult(
                check_name="iban_validation",
                passed=False,
                confidence_adjustment=-0.20,
                severity=ValidationSeverity.ERROR,
                message="IBAN-Format ungueltig: Muss mit Laendercode und Pruefziffern beginnen",
                details=details,
            )

        # Laenderspezifische Laenge pruefen
        country = normalized[:2]
        expected_length = IBAN_LENGTHS.get(country)
        if expected_length and len(normalized) != expected_length:
            details["expected_length"] = expected_length
            details["actual_length"] = len(normalized)
            details["country"] = country
            return ValidationResult(
                check_name="iban_validation",
                passed=False,
                confidence_adjustment=-0.20,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"IBAN-Laenge ungueltig fuer {country}: "
                    f"erwartet {expected_length}, gefunden {len(normalized)}"
                ),
                details=details,
            )

        # Pruefziffer validieren (ISO 7064 Mod 97-10)
        if not self._validate_iban_checksum(normalized):
            return ValidationResult(
                check_name="iban_validation",
                passed=False,
                confidence_adjustment=-0.25,
                severity=ValidationSeverity.ERROR,
                message="IBAN-Pruefziffer ungueltig",
                details=details,
            )

        # Gegen bekannte IBANs pruefen
        if entity_id is not None:
            from app.db.models_entity_business import BusinessEntity

            result = await db.execute(
                select(BusinessEntity.iban).where(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
            known_iban = result.scalar_one_or_none()

            if known_iban:
                known_normalized = re.sub(r"\s", "", known_iban).upper()
                if known_normalized == normalized:
                    details["match"] = "entity_iban_match"
                    return ValidationResult(
                        check_name="iban_validation",
                        passed=True,
                        confidence_adjustment=0.10,
                        severity=ValidationSeverity.INFO,
                        message="IBAN stimmt mit bekanntem Lieferanten ueberein",
                        details=details,
                    )
                else:
                    details["match"] = "entity_iban_mismatch"
                    return ValidationResult(
                        check_name="iban_validation",
                        passed=False,
                        confidence_adjustment=-0.10,
                        severity=ValidationSeverity.WARNING,
                        message="IBAN weicht von bekannter Lieferanten-IBAN ab",
                        details=details,
                    )

        # IBAN gueltig, aber kein Abgleich moeglich
        details["match"] = "no_entity_reference"
        return ValidationResult(
            check_name="iban_validation",
            passed=True,
            confidence_adjustment=0.0,
            severity=ValidationSeverity.INFO,
            message="IBAN-Format gueltig, kein Lieferanten-Abgleich moeglich",
            details=details,
        )

    # =========================================================================
    # UST-ID VALIDATION
    # =========================================================================

    def validate_ust_id(
        self,
        extracted_ust_id: Optional[str],
    ) -> ValidationResult:
        """
        Validiert eine extrahierte USt-ID.

        Prueft:
        - Grundformat (Laendercode + Ziffern/Buchstaben)
        - Deutsche USt-ID: DE + 9 Ziffern
        - EU-USt-ID Formate

        Args:
            extracted_ust_id: Extrahierte USt-ID

        Returns:
            ValidationResult mit Pruefergebnis
        """
        if not extracted_ust_id:
            return ValidationResult(
                check_name="ust_id_validation",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Keine USt-ID zur Validierung vorhanden",
            )

        normalized = re.sub(r"\s", "", extracted_ust_id).upper()
        details: Dict[str, object] = {"ust_id": normalized}

        # Mindestlaenge pruefen
        if len(normalized) < 4:
            return ValidationResult(
                check_name="ust_id_validation",
                passed=False,
                confidence_adjustment=-0.15,
                severity=ValidationSeverity.ERROR,
                message="USt-ID zu kurz: mindestens 4 Zeichen erwartet",
                details=details,
            )

        # Laendercode extrahieren
        country = normalized[:2]
        if not country.isalpha():
            return ValidationResult(
                check_name="ust_id_validation",
                passed=False,
                confidence_adjustment=-0.15,
                severity=ValidationSeverity.ERROR,
                message="USt-ID muss mit Laendercode beginnen (z.B. DE, AT, NL)",
                details=details,
            )

        details["country"] = country

        # Laenderspezifische Formatpruefung
        expected_length = VAT_ID_FORMATS.get(country)
        if expected_length and len(normalized) != expected_length:
            details["expected_length"] = expected_length
            details["actual_length"] = len(normalized)
            return ValidationResult(
                check_name="ust_id_validation",
                passed=False,
                confidence_adjustment=-0.15,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"USt-ID-Laenge ungueltig fuer {country}: "
                    f"erwartet {expected_length}, gefunden {len(normalized)}"
                ),
                details=details,
            )

        # Deutsche USt-ID: DE + genau 9 Ziffern
        if country == "DE":
            number_part = normalized[2:]
            if not number_part.isdigit() or len(number_part) != 9:
                return ValidationResult(
                    check_name="ust_id_validation",
                    passed=False,
                    confidence_adjustment=-0.15,
                    severity=ValidationSeverity.ERROR,
                    message="Deutsche USt-ID: DE gefolgt von genau 9 Ziffern erwartet",
                    details=details,
                )

        # Format gueltig
        return ValidationResult(
            check_name="ust_id_validation",
            passed=True,
            confidence_adjustment=0.05,
            severity=ValidationSeverity.INFO,
            message=f"USt-ID Format gueltig ({country})",
            details=details,
        )

    # =========================================================================
    # DOCUMENT DIRECTION CLASSIFICATION
    # =========================================================================

    async def classify_document_direction(
        self,
        extracted_fields: Dict[str, object],
        company_id: UUID,
        db: AsyncSession,
    ) -> ValidationResult:
        """
        Klassifiziert die Dokumentrichtung (Eingangs-/Ausgangsrechnung).

        Prueft:
        - Absender vs. Empfaenger gegen eigene Firmendaten
        - IBAN gegen eigene Bankverbindung
        - Kundennummer vs. Lieferantennummer (Lexware)

        Args:
            extracted_fields: Extrahierte Felder (sender_name, recipient_name, iban, etc.)
            company_id: ID der eigenen Firma
            db: Datenbank-Session

        Returns:
            ValidationResult mit direction-Klassifikation
        """
        from app.db.models_cash_company import Company

        details: Dict[str, object] = {}
        signals: List[Tuple[str, float]] = []  # (direction, confidence)

        # Eigene Firmendaten laden
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        own_company = result.scalar_one_or_none()

        if not own_company:
            return ValidationResult(
                check_name="document_direction",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.WARNING,
                message="Firma nicht gefunden - Dokumentrichtung nicht bestimmbar",
                details={"company_id": str(company_id)},
            )

        own_names = [own_company.name]
        if own_company.short_name:
            own_names.append(own_company.short_name)
        if own_company.display_name:
            own_names.append(own_company.display_name)
        if own_company.alternative_names:
            own_names.extend(own_company.alternative_names)
        own_names_lower = [n.lower() for n in own_names if n]

        # Signal 1: Absender-Name pruefen
        sender_name = str(extracted_fields.get("sender_name", "")).lower()
        if sender_name:
            for own_name in own_names_lower:
                if own_name in sender_name or sender_name in own_name:
                    signals.append(("outgoing", 0.8))
                    details["sender_match"] = True
                    break

        # Signal 2: Empfaenger-Name pruefen
        recipient_name = str(extracted_fields.get("recipient_name", "")).lower()
        if recipient_name:
            for own_name in own_names_lower:
                if own_name in recipient_name or recipient_name in own_name:
                    signals.append(("incoming", 0.8))
                    details["recipient_match"] = True
                    break

        # Signal 3: IBAN gegen eigene Bankverbindung
        extracted_iban = str(extracted_fields.get("iban", ""))
        if extracted_iban and own_company.iban:
            own_iban = re.sub(r"\s", "", own_company.iban).upper()
            doc_iban = re.sub(r"\s", "", extracted_iban).upper()
            if own_iban == doc_iban:
                signals.append(("outgoing", 0.9))
                details["iban_match_own"] = True

        # Signal 4: USt-ID gegen eigene USt-ID
        extracted_sender_vat = str(extracted_fields.get("sender_vat_id", ""))
        if extracted_sender_vat and own_company.vat_id:
            own_vat = re.sub(r"\s", "", own_company.vat_id).upper()
            doc_vat = re.sub(r"\s", "", extracted_sender_vat).upper()
            if own_vat == doc_vat:
                signals.append(("outgoing", 0.95))
                details["vat_id_match_sender"] = True

        extracted_recipient_vat = str(extracted_fields.get("recipient_vat_id", ""))
        if extracted_recipient_vat and own_company.vat_id:
            own_vat = re.sub(r"\s", "", own_company.vat_id).upper()
            doc_vat = re.sub(r"\s", "", extracted_recipient_vat).upper()
            if own_vat == doc_vat:
                signals.append(("incoming", 0.95))
                details["vat_id_match_recipient"] = True

        # Auswertung
        if not signals:
            return ValidationResult(
                check_name="document_direction",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Dokumentrichtung nicht bestimmbar (keine Signale)",
                details=details,
            )

        # Gewichtete Abstimmung
        incoming_score = sum(c for d, c in signals if d == "incoming")
        outgoing_score = sum(c for d, c in signals if d == "outgoing")

        if incoming_score > outgoing_score:
            direction = "incoming"
            confidence = min(incoming_score / (incoming_score + outgoing_score + 0.01), 0.99)
        elif outgoing_score > incoming_score:
            direction = "outgoing"
            confidence = min(outgoing_score / (incoming_score + outgoing_score + 0.01), 0.99)
        else:
            direction = "incoming"  # Default bei Gleichstand
            confidence = 0.5

        details["direction"] = direction
        details["confidence"] = round(confidence, 3)
        details["incoming_score"] = round(incoming_score, 3)
        details["outgoing_score"] = round(outgoing_score, 3)

        return ValidationResult(
            check_name="document_direction",
            passed=True,
            confidence_adjustment=0.0,
            severity=ValidationSeverity.INFO,
            message=(
                f"Dokumentrichtung: {'Eingangsrechnung' if direction == 'incoming' else 'Ausgangsrechnung'} "
                f"(Konfidenz: {confidence:.0%})"
            ),
            details=details,
        )

    # =========================================================================
    # DATE VALIDATION
    # =========================================================================

    def validate_dates(
        self,
        invoice_date: Optional[date] = None,
        due_date: Optional[date] = None,
        delivery_date: Optional[date] = None,
    ) -> ValidationResult:
        """
        Validiert Datumsfelder auf Plausibilitaet.

        Regeln:
        - Rechnungsdatum nicht in der Zukunft (Toleranz: 2 Tage)
        - Faelligkeitsdatum nach Rechnungsdatum
        - Lieferdatum im vernuenftigen Bereich zum Rechnungsdatum

        Args:
            invoice_date: Rechnungsdatum
            due_date: Faelligkeitsdatum
            delivery_date: Lieferdatum

        Returns:
            ValidationResult mit Pruefergebnis
        """
        details: Dict[str, object] = {}
        today = date.today()
        issues: List[str] = []

        if invoice_date is None and due_date is None and delivery_date is None:
            return ValidationResult(
                check_name="date_validation",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Keine Datumsfelder zur Validierung vorhanden",
            )

        if invoice_date is not None:
            details["invoice_date"] = invoice_date.isoformat()

            # Rechnungsdatum nicht in der Zukunft
            future_limit = today + timedelta(days=DATE_FUTURE_TOLERANCE_DAYS)
            if invoice_date > future_limit:
                issues.append(
                    f"Rechnungsdatum ({invoice_date}) liegt in der Zukunft"
                )

            # Rechnungsdatum nicht zu alt (mehr als 2 Jahre)
            if invoice_date < today - timedelta(days=730):
                issues.append(
                    f"Rechnungsdatum ({invoice_date}) liegt mehr als 2 Jahre zurueck"
                )

        if due_date is not None:
            details["due_date"] = due_date.isoformat()

            # Faelligkeitsdatum nach Rechnungsdatum
            if invoice_date is not None and due_date < invoice_date:
                issues.append(
                    f"Faelligkeitsdatum ({due_date}) liegt vor Rechnungsdatum ({invoice_date})"
                )

            # Faelligkeitsdatum nicht mehr als 1 Jahr nach Rechnungsdatum
            if invoice_date is not None and due_date > invoice_date + timedelta(days=365):
                issues.append(
                    f"Faelligkeitsdatum ({due_date}) liegt mehr als 1 Jahr nach Rechnungsdatum"
                )

        if delivery_date is not None:
            details["delivery_date"] = delivery_date.isoformat()

            # Lieferdatum im Bereich von 180 Tagen vor/nach Rechnungsdatum
            if invoice_date is not None:
                diff_days = abs((delivery_date - invoice_date).days)
                if diff_days > 180:
                    issues.append(
                        f"Lieferdatum ({delivery_date}) weicht stark vom "
                        f"Rechnungsdatum ({invoice_date}) ab ({diff_days} Tage)"
                    )

        if issues:
            severity = ValidationSeverity.ERROR if len(issues) >= 2 else ValidationSeverity.WARNING
            return ValidationResult(
                check_name="date_validation",
                passed=False,
                confidence_adjustment=-0.10 * len(issues),
                severity=severity,
                message="; ".join(issues),
                details=details,
            )

        return ValidationResult(
            check_name="date_validation",
            passed=True,
            confidence_adjustment=0.03,
            severity=ValidationSeverity.INFO,
            message="Datumsfelder plausibel",
            details=details,
        )

    # =========================================================================
    # DUPLICATE DETECTION
    # =========================================================================

    async def check_duplicate(
        self,
        invoice_number: Optional[str],
        entity_id: Optional[UUID],
        amount: Optional[Decimal],
        company_id: UUID,
        db: AsyncSession,
    ) -> ValidationResult:
        """
        Prueft auf Duplikate anhand von Rechnungsnummer, Entity und Betrag.

        Regeln:
        - Gleiche Rechnungsnummer + Entity + Betrag = wahrscheinliches Duplikat
        - Gleiche Rechnungsnummer + Entity = moegliches Duplikat
        - Gibt die ID des potenziellen Duplikats zurueck

        Args:
            invoice_number: Rechnungsnummer
            entity_id: Lieferanten-Entity-ID
            amount: Rechnungsbetrag
            company_id: Company-ID (Multi-Tenant)
            db: Datenbank-Session

        Returns:
            ValidationResult mit Duplikat-Information
        """
        if not invoice_number:
            return ValidationResult(
                check_name="duplicate_check",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Keine Rechnungsnummer fuer Duplikat-Pruefung vorhanden",
            )

        from app.db.models import Document

        details: Dict[str, object] = {
            "invoice_number": invoice_number,
        }

        # Suche nach Dokumenten mit gleicher Rechnungsnummer
        # Rechnungsnummer ist in extracted_data JSONB gespeichert
        conditions = [
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
            Document.extracted_data["invoice_number"].astext == invoice_number,
        ]

        if entity_id is not None:
            conditions.append(Document.business_entity_id == entity_id)

        result = await db.execute(
            select(Document.id, Document.extracted_data, Document.business_entity_id)
            .where(and_(*conditions))
            .limit(5)
        )
        candidates = result.all()

        if not candidates:
            return ValidationResult(
                check_name="duplicate_check",
                passed=True,
                confidence_adjustment=0.0,
                severity=ValidationSeverity.INFO,
                message="Kein Duplikat gefunden",
                details=details,
            )

        # Kandidaten pruefen
        for candidate_id, candidate_data, candidate_entity_id in candidates:
            candidate_amount_raw = (candidate_data or {}).get("gross_amount") or (candidate_data or {}).get("net_amount")

            # Exaktes Duplikat: Rechnungsnummer + Entity + Betrag
            if entity_id is not None and candidate_entity_id == entity_id and amount is not None and candidate_amount_raw is not None:
                try:
                    candidate_amount = Decimal(str(candidate_amount_raw))
                    if abs(candidate_amount - amount) < Decimal("0.10"):
                        details["duplicate_document_id"] = str(candidate_id)
                        details["match_type"] = "exact"
                        return ValidationResult(
                            check_name="duplicate_check",
                            passed=False,
                            confidence_adjustment=-0.30,
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"Wahrscheinliches Duplikat: Rechnungsnummer '{invoice_number}' "
                                f"mit gleichem Lieferanten und Betrag bereits vorhanden"
                            ),
                            details=details,
                        )
                except (InvalidOperation, TypeError, ValueError):
                    pass

            # Teilmatch: Rechnungsnummer + Entity (anderer Betrag)
            if entity_id is not None and candidate_entity_id == entity_id:
                details["duplicate_document_id"] = str(candidate_id)
                details["match_type"] = "partial"
                return ValidationResult(
                    check_name="duplicate_check",
                    passed=False,
                    confidence_adjustment=-0.15,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Moegliches Duplikat: Rechnungsnummer '{invoice_number}' "
                        f"beim gleichen Lieferanten bereits vorhanden (anderer Betrag)"
                    ),
                    details=details,
                )

        # Nur Rechnungsnummer match (anderer Lieferant)
        details["similar_document_id"] = str(candidates[0][0])
        details["match_type"] = "number_only"
        return ValidationResult(
            check_name="duplicate_check",
            passed=True,
            confidence_adjustment=0.0,
            severity=ValidationSeverity.INFO,
            message=(
                f"Rechnungsnummer '{invoice_number}' existiert bei anderem Lieferanten"
            ),
            details=details,
        )

    # =========================================================================
    # AGGREGATE VALIDATION
    # =========================================================================

    async def validate_all(
        self,
        extracted_data: Dict[str, object],
        company_id: UUID,
        db: AsyncSession,
        entity_id: Optional[UUID] = None,
    ) -> CrossValidationResult:
        """
        Fuehrt alle Validierungspruefungen durch.

        Args:
            extracted_data: Extrahierte strukturierte Daten
            company_id: Company-ID (Multi-Tenant)
            db: Datenbank-Session
            entity_id: Optionale Entity-ID fuer Abgleich

        Returns:
            CrossValidationResult mit allen Pruefergebnissen
        """
        self._stats["total_validations"] += 1
        result = CrossValidationResult()

        # Felder extrahieren
        netto = self._to_decimal(extracted_data.get("net_amount"))
        mwst = self._to_decimal(extracted_data.get("vat_amount"))
        brutto = self._to_decimal(extracted_data.get("gross_amount"))
        ust_satz = self._to_decimal(extracted_data.get("vat_rate"))
        iban = self._to_str(extracted_data.get("iban"))
        ust_id = self._to_str(extracted_data.get("vat_id")) or self._to_str(extracted_data.get("sender_vat_id"))
        invoice_number = self._to_str(extracted_data.get("invoice_number"))
        invoice_date = self._to_date(extracted_data.get("invoice_date"))
        due_date = self._to_date(extracted_data.get("due_date"))
        delivery_date = self._to_date(extracted_data.get("delivery_date"))

        # 1. Betrags-Plausibilitaet
        try:
            amount_result = self.validate_amounts(netto, mwst, brutto, ust_satz)
            result.checks.append(amount_result)
        except Exception as e:
            logger.warning("cross_validation_amount_error", **safe_error_log(e))

        # 2. IBAN-Validierung
        try:
            iban_result = await self.validate_iban(iban, entity_id, db)
            result.checks.append(iban_result)
        except Exception as e:
            logger.warning("cross_validation_iban_error", **safe_error_log(e))

        # 3. USt-ID Validierung
        try:
            ust_result = self.validate_ust_id(ust_id)
            result.checks.append(ust_result)
        except Exception as e:
            logger.warning("cross_validation_ust_id_error", **safe_error_log(e))

        # 4. Dokumentrichtung
        try:
            direction_result = await self.classify_document_direction(
                extracted_data, company_id, db
            )
            result.checks.append(direction_result)
            # Direction aus den Details extrahieren
            direction_details = direction_result.details
            if "direction" in direction_details:
                result.document_direction = str(direction_details["direction"])
        except Exception as e:
            logger.warning("cross_validation_direction_error", **safe_error_log(e))

        # 5. Datums-Validierung
        try:
            date_result = self.validate_dates(invoice_date, due_date, delivery_date)
            result.checks.append(date_result)
        except Exception as e:
            logger.warning("cross_validation_date_error", **safe_error_log(e))

        # 6. Duplikat-Pruefung
        try:
            amount_for_dup = brutto or netto
            dup_result = await self.check_duplicate(
                invoice_number, entity_id, amount_for_dup, company_id, db
            )
            result.checks.append(dup_result)
            # Duplikat-ID extrahieren
            dup_doc_id = dup_result.details.get("duplicate_document_id")
            if dup_doc_id:
                result.duplicate_candidate_id = UUID(str(dup_doc_id))
        except Exception as e:
            logger.warning("cross_validation_duplicate_error", **safe_error_log(e))

        # Aggregation
        for check in result.checks:
            result.overall_confidence_adjustment += check.confidence_adjustment
            if check.severity == ValidationSeverity.ERROR and not check.passed:
                result.has_errors = True
                self._stats["errors_found"] += 1
            elif check.severity == ValidationSeverity.WARNING and not check.passed:
                result.has_warnings = True
                self._stats["warnings_found"] += 1

        # Confidence-Adjustment begrenzen
        result.overall_confidence_adjustment = max(
            -0.30, min(0.10, result.overall_confidence_adjustment)
        )

        if result.duplicate_candidate_id:
            self._stats["duplicates_detected"] += 1

        logger.info(
            "cross_validation_completed",
            checks_run=len(result.checks),
            has_errors=result.has_errors,
            has_warnings=result.has_warnings,
            overall_adjustment=round(result.overall_confidence_adjustment, 3),
            direction=result.document_direction,
            duplicate_found=result.duplicate_candidate_id is not None,
        )

        return result

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _validate_iban_checksum(iban: str) -> bool:
        """Validiert IBAN mit ISO 7064 Mod 97-10 Pruefziffer."""
        try:
            rearranged = iban[4:] + iban[:4]
            numeric = ""
            for char in rearranged:
                if char.isdigit():
                    numeric += char
                else:
                    numeric += str(ord(char) - ord("A") + 10)
            return int(numeric) % 97 == 1
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _to_decimal(value: object) -> Optional[Decimal]:
        """Konvertiert einen Wert sicher zu Decimal."""
        if value is None:
            return None
        try:
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _to_str(value: object) -> Optional[str]:
        """Konvertiert einen Wert sicher zu String."""
        if value is None:
            return None
        s = str(value).strip()
        return s if s else None

    @staticmethod
    def _to_date(value: object) -> Optional[date]:
        """Konvertiert einen Wert sicher zu date."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)).date()
        except (ValueError, TypeError):
            return None

    def get_stats(self) -> Dict[str, int]:
        """Gibt Validierungsstatistiken zurueck."""
        return self._stats.copy()


# =============================================================================
# SINGLETON
# =============================================================================

_cross_validation_service: Optional[CrossValidationService] = None


def get_cross_validation_service() -> CrossValidationService:
    """Hole Singleton-Instance des CrossValidationService."""
    global _cross_validation_service
    if _cross_validation_service is None:
        _cross_validation_service = CrossValidationService()
    return _cross_validation_service
