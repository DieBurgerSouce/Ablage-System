# -*- coding: utf-8 -*-
"""
Plausibility Service fuer Auto-Booking.

Validiert extrahierte Rechnungsdaten vor der automatischen Buchung:
- Duplikat-Erkennung (gleiche Rechnungsnummer + Entity + Periode)
- USt-Validierung (Satz, Betrag, Reverse Charge)
- Betrags-Plausibilitaet (Statistischer Ausreisser-Test)
- Kontierungs-Pruefung (SKR03/04 Validierung)
- GoBD-Pflichtfelder
- Confidence-basiertes Routing (auto_book / review / manual)

Feinpoliert und durchdacht - Enterprise-grade Buchungs-Plausibilitaet.
"""

import threading
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func, extract, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.services.datev.kontenrahmen import SKR03, SKR04, BaseKontenrahmen

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class PlausibilityCheck:
    """Ergebnis einer einzelnen Plausibilitaetspruefung."""

    check_name: str
    passed: bool
    severity: str  # "error", "warning", "info"
    message: str  # Deutsch
    details: Dict[str, object] = field(default_factory=dict)


@dataclass
class RoutingDecision:
    """Routing-Entscheidung basierend auf Plausibilitaetspruefungen."""

    routing: str  # "auto_book", "review", "manual"
    confidence: float
    reason: str  # Deutsche Erklaerung
    checks_passed: int
    checks_failed: int
    suggested_actions: List[str] = field(default_factory=list)


@dataclass
class PlausibilityResult:
    """Aggregiertes Ergebnis aller Plausibilitaetspruefungen."""

    checks: List[PlausibilityCheck] = field(default_factory=list)
    routing: Optional[RoutingDecision] = None
    is_bookable: bool = False
    overall_score: float = 0.0


# =============================================================================
# CONSTANTS
# =============================================================================

# Deutsche Standard-USt-Saetze (Prozent)
VALID_UST_RATES_DE: Set[int] = {0, 7, 19}

# MwSt-Berechnungstoleranz
UST_TOLERANCE = Decimal("0.02")

# Statistische Ausreisser-Schwelle (Standardabweichungen)
OUTLIER_SIGMA = 3

# Mindestanzahl historischer Rechnungen fuer Statistik
MIN_HISTORY_COUNT = 3

# Kontotypen die nicht als Soll+Haben-Paar auftreten sollten
ACCOUNT_TYPES: Dict[str, str] = {
    # SKR03 Aufwandskonten (Klasse 3+4)
    "3": "aufwand",
    "4": "aufwand",
    # SKR03 Erloeskonten (Klasse 8)
    "8": "erloes",
    # SKR04 Aufwandskonten (Klasse 5+6+7)
    "5": "aufwand",
    "6": "aufwand",
    "7": "aufwand",
}


# =============================================================================
# PLAUSIBILITY SERVICE
# =============================================================================


class PlausibilityService:
    """
    Service fuer Plausibilitaetspruefung von Buchungsvorschlaegen.

    Validiert extrahierte Daten vor der automatischen Buchung und
    routet Dokumente basierend auf der Pruefungs-Konfidenz.

    Usage:
        service = PlausibilityService()
        result = await service.evaluate_all(
            extracted_data=data,
            company_id=company_uuid,
            entity_id=entity_uuid,
            db=session,
        )
        if result.routing.routing == "auto_book":
            # Automatisch buchen
            ...
    """

    def __init__(self, skr_type: str = "skr03") -> None:
        """
        Initialisiert den Service.

        Args:
            skr_type: Kontenrahmen-Typ ("skr03" oder "skr04")
        """
        self._kontenrahmen: BaseKontenrahmen = (
            SKR03() if skr_type.lower() == "skr03" else SKR04()
        )
        self._skr_type = skr_type.lower()

    # =========================================================================
    # CHECK 1: DUPLIKAT-ERKENNUNG
    # =========================================================================

    async def check_duplicate_invoice(
        self,
        invoice_number: Optional[str],
        entity_id: Optional[UUID],
        period: Optional[date],
        company_id: UUID,
        db: AsyncSession,
    ) -> PlausibilityCheck:
        """
        Prueft auf doppelte Rechnungsnummern in der gleichen Buchungsperiode.

        Args:
            invoice_number: Rechnungsnummer
            entity_id: Geschaeftspartner-ID
            period: Belegdatum (fuer Periodenbestimmung)
            company_id: Mandanten-ID
            db: Datenbank-Session

        Returns:
            PlausibilityCheck mit Pruefergebnis
        """
        if not invoice_number:
            return PlausibilityCheck(
                check_name="duplicate_invoice",
                passed=True,
                severity="info",
                message="Keine Rechnungsnummer vorhanden - Duplikat-Pruefung uebersprungen",
                details={"reason": "no_invoice_number"},
            )

        from app.db.models import Document

        try:
            conditions = [
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                cast(Document.extracted_data, JSONB)["invoice_number"].astext == invoice_number,
            ]

            if entity_id is not None:
                conditions.append(Document.business_entity_id == entity_id)

            # Periodenfilter: gleiches Jahr + Monat
            if period is not None:
                conditions.append(
                    extract("year", Document.created_at) == period.year
                )
                conditions.append(
                    extract("month", Document.created_at) == period.month
                )

            result = await db.execute(
                select(func.count(Document.id)).where(and_(*conditions))
            )
            duplicate_count = result.scalar() or 0

            if duplicate_count > 0:
                return PlausibilityCheck(
                    check_name="duplicate_invoice",
                    passed=False,
                    severity="error",
                    message=(
                        f"Duplikat erkannt: Rechnungsnummer '{invoice_number}' "
                        f"existiert bereits {duplicate_count}x in dieser Periode"
                    ),
                    details={
                        "invoice_number": invoice_number,
                        "duplicate_count": duplicate_count,
                        "period": period.isoformat() if period else None,
                    },
                )

            return PlausibilityCheck(
                check_name="duplicate_invoice",
                passed=True,
                severity="info",
                message="Keine Duplikate gefunden",
                details={"invoice_number": invoice_number},
            )

        except Exception as e:
            logger.warning("plausibility_duplicate_check_error", **safe_error_log(e))
            return PlausibilityCheck(
                check_name="duplicate_invoice",
                passed=True,
                severity="warning",
                message="Duplikat-Pruefung konnte nicht durchgefuehrt werden",
                details={"reason": "query_error"},
            )

    # =========================================================================
    # CHECK 2: UST-VALIDIERUNG
    # =========================================================================

    def check_ust_validity(
        self,
        ust_satz: Optional[float],
        ust_betrag: Optional[Decimal],
        netto_betrag: Optional[Decimal],
        country: str = "DE",
    ) -> PlausibilityCheck:
        """
        Prueft USt-Satz und berechneten MwSt-Betrag.

        Regeln:
        - Deutsche Standardsaetze: 0%, 7%, 19%
        - Berechnete MwSt muss extrahierter MwSt entsprechen (Toleranz 0.02 EUR)
        - EU Reverse Charge: USt-Satz 0% bei auslaendischem Lieferanten

        Args:
            ust_satz: USt-Satz in Prozent (z.B. 19.0)
            ust_betrag: Extrahierter MwSt-Betrag
            netto_betrag: Extrahierter Netto-Betrag
            country: Laendercode des Lieferanten

        Returns:
            PlausibilityCheck mit Pruefergebnis
        """
        details: Dict[str, object] = {"country": country}

        # Kein USt-Satz vorhanden
        if ust_satz is None:
            return PlausibilityCheck(
                check_name="ust_validity",
                passed=True,
                severity="info",
                message="Kein USt-Satz extrahiert - Pruefung uebersprungen",
                details=details,
            )

        details["ust_satz"] = ust_satz

        # Deutsche Standardsaetze pruefen
        if country == "DE":
            ust_int = int(round(ust_satz))
            if ust_int not in VALID_UST_RATES_DE:
                return PlausibilityCheck(
                    check_name="ust_validity",
                    passed=False,
                    severity="error",
                    message=(
                        f"Ungueltiger USt-Satz: {ust_satz}% "
                        f"(zulaessig in DE: 0%, 7%, 19%)"
                    ),
                    details=details,
                )

        # EU Reverse Charge Pruefung
        if country != "DE" and ust_satz > 0:
            return PlausibilityCheck(
                check_name="ust_validity",
                passed=False,
                severity="warning",
                message=(
                    f"USt-Satz {ust_satz}% bei auslaendischem Lieferanten ({country}) - "
                    f"Reverse Charge pruefen"
                ),
                details=details,
            )

        # MwSt-Betrag gegen Netto pruefen
        if netto_betrag is not None and ust_betrag is not None and ust_satz > 0:
            try:
                expected_ust = netto_betrag * Decimal(str(ust_satz / 100))
                diff = abs(expected_ust - ust_betrag)
                details["expected_ust"] = str(expected_ust.quantize(Decimal("0.01")))
                details["actual_ust"] = str(ust_betrag)
                details["differenz"] = str(diff.quantize(Decimal("0.01")))

                if diff > UST_TOLERANCE:
                    return PlausibilityCheck(
                        check_name="ust_validity",
                        passed=False,
                        severity="error",
                        message=(
                            f"MwSt-Berechnung inkonsistent: "
                            f"erwartet {expected_ust.quantize(Decimal('0.01'))} EUR, "
                            f"extrahiert {ust_betrag} EUR "
                            f"(Differenz: {diff.quantize(Decimal('0.01'))} EUR)"
                        ),
                        details=details,
                    )
            except (InvalidOperation, ArithmeticError) as e:
                logger.warning("datev_ust_plausibility_check_skipped", error_type=type(e).__name__)

        return PlausibilityCheck(
            check_name="ust_validity",
            passed=True,
            severity="info",
            message=f"USt-Satz {ust_satz}% gueltig",
            details=details,
        )

    # =========================================================================
    # CHECK 3: BETRAGS-PLAUSIBILITAET
    # =========================================================================

    async def check_amount_plausibility(
        self,
        amount: Optional[Decimal],
        entity_id: Optional[UUID],
        company_id: UUID,
        db: AsyncSession,
    ) -> PlausibilityCheck:
        """
        Prueft ob ein Rechnungsbetrag statistisch plausibel ist.

        Laedt historische Rechnungen fuer die Entity und prueft,
        ob der aktuelle Betrag ein statistischer Ausreisser ist.

        Args:
            amount: Bruttobetrag der Rechnung
            entity_id: Geschaeftspartner-ID
            company_id: Mandanten-ID
            db: Datenbank-Session

        Returns:
            PlausibilityCheck mit Pruefergebnis
        """
        details: Dict[str, object] = {}

        if amount is None:
            return PlausibilityCheck(
                check_name="amount_plausibility",
                passed=False,
                severity="error",
                message="Kein Betrag extrahiert",
                details={"reason": "no_amount"},
            )

        details["betrag"] = str(amount)

        # Negativer oder Null-Betrag
        if amount <= 0:
            return PlausibilityCheck(
                check_name="amount_plausibility",
                passed=False,
                severity="error",
                message=f"Ungueltiger Betrag: {amount} EUR (muss positiv sein)",
                details=details,
            )

        # Ohne Entity kein Statistikvergleich moeglich
        if entity_id is None:
            return PlausibilityCheck(
                check_name="amount_plausibility",
                passed=True,
                severity="info",
                message="Betrag positiv, kein Lieferant fuer Statistikvergleich vorhanden",
                details=details,
            )

        from app.db.models import Document

        try:
            # Historische Betraege laden
            result = await db.execute(
                select(cast(Document.extracted_data, JSONB)["gross_amount"].astext)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.business_entity_id == entity_id,
                        Document.deleted_at.is_(None),
                        cast(Document.extracted_data, JSONB)["gross_amount"].astext.isnot(None),
                    )
                )
                .limit(100)
            )
            raw_amounts = result.scalars().all()

            historical_amounts: List[Decimal] = []
            for raw in raw_amounts:
                try:
                    val = Decimal(str(raw))
                    if val > 0:
                        historical_amounts.append(val)
                except (InvalidOperation, TypeError, ValueError):
                    continue

            details["historical_count"] = len(historical_amounts)

            if len(historical_amounts) < MIN_HISTORY_COUNT:
                return PlausibilityCheck(
                    check_name="amount_plausibility",
                    passed=True,
                    severity="info",
                    message=(
                        f"Betrag {amount} EUR - zu wenig historische Daten "
                        f"fuer Statistikvergleich ({len(historical_amounts)} Rechnungen)"
                    ),
                    details=details,
                )

            # Mittelwert und Standardabweichung
            n = len(historical_amounts)
            mean = sum(historical_amounts) / n
            variance = sum((x - mean) ** 2 for x in historical_amounts) / n
            # sqrt via Decimal
            std_dev = variance.sqrt() if variance > 0 else Decimal("0")

            details["mean"] = str(mean.quantize(Decimal("0.01")))
            details["std_dev"] = str(std_dev.quantize(Decimal("0.01")))

            # Ausreisser-Test: Betrag > mean + 3*std
            if std_dev > 0:
                threshold = mean + Decimal(str(OUTLIER_SIGMA)) * std_dev
                details["threshold"] = str(threshold.quantize(Decimal("0.01")))

                if amount > threshold:
                    return PlausibilityCheck(
                        check_name="amount_plausibility",
                        passed=False,
                        severity="warning",
                        message=(
                            f"Betrag {amount} EUR ist ungewoehnlich hoch "
                            f"(Durchschnitt: {mean.quantize(Decimal('0.01'))} EUR, "
                            f"Schwelle: {threshold.quantize(Decimal('0.01'))} EUR)"
                        ),
                        details=details,
                    )

            return PlausibilityCheck(
                check_name="amount_plausibility",
                passed=True,
                severity="info",
                message=f"Betrag {amount} EUR liegt im erwarteten Bereich",
                details=details,
            )

        except Exception as e:
            logger.warning("plausibility_amount_check_error", **safe_error_log(e))
            return PlausibilityCheck(
                check_name="amount_plausibility",
                passed=True,
                severity="info",
                message="Betrags-Statistikpruefung konnte nicht durchgefuehrt werden",
                details={"reason": "query_error"},
            )

    # =========================================================================
    # CHECK 4: KONTIERUNGS-PRUEFUNG
    # =========================================================================

    def check_kontierung(
        self,
        konto: Optional[str],
        gegenkonto: Optional[str],
        skr_type: Optional[str] = None,
    ) -> PlausibilityCheck:
        """
        Prueft ob Konto und Gegenkonto gueltig und sinnvoll kombiniert sind.

        Args:
            konto: Hauptkonto (Sachkonto/Personenkonto)
            gegenkonto: Gegenkonto
            skr_type: Kontenrahmen-Typ (falls abweichend vom Service-Default)

        Returns:
            PlausibilityCheck mit Pruefergebnis
        """
        details: Dict[str, object] = {}
        effective_skr = skr_type or self._skr_type

        if not konto:
            return PlausibilityCheck(
                check_name="kontierung",
                passed=False,
                severity="error",
                message="Kein Konto angegeben",
                details=details,
            )

        if not gegenkonto:
            return PlausibilityCheck(
                check_name="kontierung",
                passed=False,
                severity="error",
                message="Kein Gegenkonto angegeben",
                details=details,
            )

        details["konto"] = konto
        details["gegenkonto"] = gegenkonto
        details["skr_type"] = effective_skr

        kontenrahmen = (
            SKR03() if effective_skr == "skr03" else SKR04()
        )

        # Alle gueltigen Kontonummern sammeln
        all_accounts: Set[str] = set()
        all_accounts.update(kontenrahmen.expense_accounts.values())
        all_accounts.update(kontenrahmen.revenue_accounts.values())
        all_accounts.add(kontenrahmen.sammelkonto_kreditoren)
        all_accounts.add(kontenrahmen.sammelkonto_debitoren)
        all_accounts.add(kontenrahmen.vorsteuer_19)
        all_accounts.add(kontenrahmen.vorsteuer_7)
        all_accounts.add(kontenrahmen.umsatzsteuer_19)
        all_accounts.add(kontenrahmen.umsatzsteuer_7)

        # Personenkonten-Bereich ebenfalls gueltig
        is_konto_person = kontenrahmen.is_creditor_account(konto) or kontenrahmen.is_debtor_account(konto)
        is_gegen_person = kontenrahmen.is_creditor_account(gegenkonto) or kontenrahmen.is_debtor_account(gegenkonto)

        # Konto pruefen
        if konto not in all_accounts and not is_konto_person:
            return PlausibilityCheck(
                check_name="kontierung",
                passed=False,
                severity="warning",
                message=f"Konto {konto} nicht im {effective_skr.upper()} Standardkontenrahmen gefunden",
                details=details,
            )

        # Gegenkonto pruefen
        if gegenkonto not in all_accounts and not is_gegen_person:
            return PlausibilityCheck(
                check_name="kontierung",
                passed=False,
                severity="warning",
                message=f"Gegenkonto {gegenkonto} nicht im {effective_skr.upper()} Standardkontenrahmen gefunden",
                details=details,
            )

        # Sinnvolle Kombination pruefen
        konto_type = self._get_account_type(konto, kontenrahmen)
        gegen_type = self._get_account_type(gegenkonto, kontenrahmen)

        details["konto_type"] = konto_type
        details["gegenkonto_type"] = gegen_type

        # Beide Seiten gleicher Typ (z.B. beide Aufwand) ist verdaechtig
        if (
            konto_type == gegen_type
            and konto_type in ("aufwand", "erloes")
        ):
            return PlausibilityCheck(
                check_name="kontierung",
                passed=False,
                severity="warning",
                message=(
                    f"Unuebliche Kontierung: Konto {konto} ({konto_type}) "
                    f"und Gegenkonto {gegenkonto} ({gegen_type}) "
                    f"sind beide vom Typ '{konto_type}'"
                ),
                details=details,
            )

        return PlausibilityCheck(
            check_name="kontierung",
            passed=True,
            severity="info",
            message=f"Kontierung {konto} / {gegenkonto} plausibel",
            details=details,
        )

    # =========================================================================
    # CHECK 5: GOBD-PFLICHTFELDER
    # =========================================================================

    def check_gobd_compliance(
        self,
        extracted_data: Dict[str, object],
    ) -> PlausibilityCheck:
        """
        Prueft ob alle GoBD-Pflichtfelder vorhanden sind.

        Pflichtfelder:
        - Rechnungsnummer
        - Belegdatum
        - Betrag
        - Lieferant/Kunde

        Args:
            extracted_data: Extrahierte strukturierte Daten

        Returns:
            PlausibilityCheck mit Pruefergebnis
        """
        missing: List[str] = []
        details: Dict[str, object] = {}

        # Pflichtfelder-Mapping: interner Schluessel -> deutscher Name
        mandatory_fields: Dict[str, List[str]] = {
            "Rechnungsnummer": ["invoice_number", "belegnummer"],
            "Belegdatum": ["invoice_date", "document_date", "date"],
            "Betrag": ["gross_amount", "total_amount", "amount", "net_amount"],
            "Lieferant": ["sender_name", "supplier_name", "entity_name"],
        }

        for field_name, keys in mandatory_fields.items():
            found = False
            for key in keys:
                value = extracted_data.get(key)
                if value is not None and str(value).strip():
                    found = True
                    break
            if not found:
                missing.append(field_name)

        details["missing_fields"] = missing
        details["checked_fields"] = list(mandatory_fields.keys())

        if missing:
            return PlausibilityCheck(
                check_name="gobd_compliance",
                passed=False,
                severity="error" if len(missing) >= 2 else "warning",
                message=(
                    f"GoBD-Pflichtfelder fehlen: {', '.join(missing)}"
                ),
                details=details,
            )

        return PlausibilityCheck(
            check_name="gobd_compliance",
            passed=True,
            severity="info",
            message="Alle GoBD-Pflichtfelder vorhanden",
            details=details,
        )

    # =========================================================================
    # ROUTING
    # =========================================================================

    def route_by_confidence(
        self,
        overall_confidence: float,
        checks: List[PlausibilityCheck],
    ) -> RoutingDecision:
        """
        Routet ein Dokument basierend auf Konfidenz und Pruefungsergebnis.

        Routing-Logik:
        - Alle Pruefungen bestanden UND Konfidenz >95%: auto_book
        - Alle Pruefungen bestanden UND Konfidenz 70-95%: review
        - Mindestens eine Pruefung fehlgeschlagen ODER Konfidenz <70%: manual

        Args:
            overall_confidence: Gesamt-Konfidenz (0.0-1.0)
            checks: Liste der Pruefungsergebnisse

        Returns:
            RoutingDecision mit Routing und Begruendung
        """
        checks_passed = sum(1 for c in checks if c.passed)
        checks_failed = sum(1 for c in checks if not c.passed)
        has_errors = any(c.severity == "error" and not c.passed for c in checks)

        suggested_actions: List[str] = []
        for check in checks:
            if not check.passed:
                suggested_actions.append(f"Pruefen: {check.message}")

        # Routing-Entscheidung
        if has_errors or overall_confidence < 0.70:
            return RoutingDecision(
                routing="manual",
                confidence=overall_confidence,
                reason=(
                    "Manuelle Pruefung erforderlich: "
                    + (
                        f"{checks_failed} Pruefung(en) fehlgeschlagen"
                        if checks_failed
                        else f"Konfidenz zu niedrig ({overall_confidence:.0%})"
                    )
                ),
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                suggested_actions=suggested_actions,
            )

        if checks_failed == 0 and overall_confidence > 0.95:
            return RoutingDecision(
                routing="auto_book",
                confidence=overall_confidence,
                reason=(
                    f"Automatische Buchung: alle {checks_passed} Pruefungen bestanden, "
                    f"Konfidenz {overall_confidence:.0%}"
                ),
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                suggested_actions=[],
            )

        # Dazwischen: review
        return RoutingDecision(
            routing="review",
            confidence=overall_confidence,
            reason=(
                f"Zur Pruefung vorgelegt: Konfidenz {overall_confidence:.0%}"
                + (f", {checks_failed} Warnung(en)" if checks_failed else "")
            ),
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggested_actions=suggested_actions,
        )

    # =========================================================================
    # AGGREGATE: evaluate_all
    # =========================================================================

    async def evaluate_all(
        self,
        extracted_data: Dict[str, object],
        company_id: UUID,
        entity_id: Optional[UUID],
        db: AsyncSession,
        confidence: Optional[float] = None,
    ) -> PlausibilityResult:
        """
        Fuehrt alle Plausibilitaetspruefungen durch und routet das Dokument.

        Args:
            extracted_data: Extrahierte strukturierte Daten
            company_id: Mandanten-ID
            entity_id: Geschaeftspartner-ID
            db: Datenbank-Session
            confidence: Externe OCR-Konfidenz (falls vorhanden)

        Returns:
            PlausibilityResult mit allen Pruefungen und Routing
        """
        result = PlausibilityResult()
        checks: List[PlausibilityCheck] = []

        # Felder extrahieren
        invoice_number = _to_str(extracted_data.get("invoice_number"))
        invoice_date = _to_date(extracted_data.get("invoice_date"))
        gross_amount = _to_decimal(extracted_data.get("gross_amount"))
        net_amount = _to_decimal(extracted_data.get("net_amount"))
        ust_betrag = _to_decimal(extracted_data.get("vat_amount"))
        ust_satz = _to_float(extracted_data.get("vat_rate"))
        country = _to_str(extracted_data.get("country")) or "DE"
        konto = _to_str(extracted_data.get("konto")) or _to_str(extracted_data.get("sollkonto"))
        gegenkonto = _to_str(extracted_data.get("gegenkonto")) or _to_str(extracted_data.get("habenkonto"))

        amount = gross_amount or net_amount

        # 1. Duplikat-Pruefung
        try:
            dup_check = await self.check_duplicate_invoice(
                invoice_number=invoice_number,
                entity_id=entity_id,
                period=invoice_date,
                company_id=company_id,
                db=db,
            )
            checks.append(dup_check)
        except Exception as e:
            logger.warning("plausibility_duplicate_error", **safe_error_log(e))

        # 2. USt-Validierung
        try:
            ust_check = self.check_ust_validity(
                ust_satz=ust_satz,
                ust_betrag=ust_betrag,
                netto_betrag=net_amount,
                country=country,
            )
            checks.append(ust_check)
        except Exception as e:
            logger.warning("plausibility_ust_error", **safe_error_log(e))

        # 3. Betrags-Plausibilitaet
        try:
            amount_check = await self.check_amount_plausibility(
                amount=amount,
                entity_id=entity_id,
                company_id=company_id,
                db=db,
            )
            checks.append(amount_check)
        except Exception as e:
            logger.warning("plausibility_amount_error", **safe_error_log(e))

        # 4. Kontierungs-Pruefung (nur wenn Konten vorhanden)
        if konto or gegenkonto:
            try:
                kont_check = self.check_kontierung(
                    konto=konto,
                    gegenkonto=gegenkonto,
                )
                checks.append(kont_check)
            except Exception as e:
                logger.warning("plausibility_kontierung_error", **safe_error_log(e))

        # 5. GoBD-Pflichtfelder
        try:
            gobd_check = self.check_gobd_compliance(extracted_data)
            checks.append(gobd_check)
        except Exception as e:
            logger.warning("plausibility_gobd_error", **safe_error_log(e))

        # Score berechnen
        if checks:
            passed_count = sum(1 for c in checks if c.passed)
            result.overall_score = passed_count / len(checks)
        else:
            result.overall_score = 0.0

        # Externe Konfidenz einbeziehen
        overall_confidence = confidence if confidence is not None else result.overall_score

        # Routing
        routing = self.route_by_confidence(overall_confidence, checks)

        result.checks = checks
        result.routing = routing
        result.is_bookable = routing.routing == "auto_book"

        logger.info(
            "plausibility_evaluation_completed",
            checks_total=len(checks),
            checks_passed=routing.checks_passed,
            checks_failed=routing.checks_failed,
            overall_score=round(result.overall_score, 3),
            routing=routing.routing,
            is_bookable=result.is_bookable,
        )

        return result

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    @staticmethod
    def _get_account_type(
        account: str,
        kontenrahmen: BaseKontenrahmen,
    ) -> str:
        """Bestimmt den Kontotyp anhand der Kontonummer."""
        if kontenrahmen.is_creditor_account(account):
            return "kreditor"
        if kontenrahmen.is_debtor_account(account):
            return "debitor"

        # Erste Ziffer bestimmt die Kontenklasse
        if account and account[0] in ACCOUNT_TYPES:
            return ACCOUNT_TYPES[account[0]]

        return "sonstige"


# =============================================================================
# HELPER FUNCTIONS (module-level)
# =============================================================================


def _to_str(value: object) -> Optional[str]:
    """Konvertiert einen Wert sicher zu String."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


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


def _to_float(value: object) -> Optional[float]:
    """Konvertiert einen Wert sicher zu float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value: object) -> Optional[date]:
    """Konvertiert einen Wert sicher zu date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value)).date()
    except (ValueError, TypeError):
        return None


# =============================================================================
# SINGLETON
# =============================================================================

_plausibility_service: Optional[PlausibilityService] = None
_service_lock = threading.Lock()


def get_plausibility_service(skr_type: str = "skr03") -> PlausibilityService:
    """
    Factory fuer PlausibilityService (Thread-Safe Singleton).

    Args:
        skr_type: Kontenrahmen-Typ

    Returns:
        PlausibilityService Instanz
    """
    global _plausibility_service
    if _plausibility_service is None:
        with _service_lock:
            if _plausibility_service is None:
                _plausibility_service = PlausibilityService(skr_type=skr_type)
    return _plausibility_service
