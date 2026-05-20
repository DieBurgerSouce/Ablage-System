# -*- coding: utf-8 -*-
"""Anomalie-Erkennungs-Service.

Hybrid-Ansatz: Regelbasiert + Statistisch.
Erkennt verdaechtige Muster in Rechnungen, Zahlungen und Dokumenten.

Erkennungsarten:
- Doppelte Rechnungen (gleiche Nummer, aehnlicher Betrag, gleicher Lieferant)
- Betrags-Ausreisser pro Lieferant (Standardabweichung)
- Verdaechtige Lieferanten-Aenderungen (IBAN-Wechsel)
- Fehlende Dokumente in Auftragsketten
- Ungewoehnliche Rechnungshaeufigkeit

SECURITY: NEVER log financial details, IBANs or PII.
Phase 2.3 der Feature-Roadmap (Februar 2026).
"""

import math
from datetime import timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import (
    BusinessEntity,
    Document,
    DocumentType,
    InvoiceTracking,
)
from app.db.models_anomaly import (
    Anomaly,
    AnomalyRule,
    AnomalyRuleType,
    AnomalySeverity,
    AnomalyStatus,
)

logger = structlog.get_logger(__name__)


def get_anomaly_detection_service(
    session: AsyncSession,
) -> "AnomalyDetectionService":
    """Factory-Funktion fuer den Anomalie-Erkennungs-Service."""
    return AnomalyDetectionService(session)


class AnomalyDetectionService:
    """Hybrid-Anomalie-Erkennung: Regelbasiert + Statistisch.

    Fuehrt verschiedene Pruefungen durch, um verdaechtige Muster
    in Rechnungen, Zahlungen und Dokumenten zu erkennen.
    """

    # Standard-Konfiguration fuer Pruefungen
    DEFAULT_SIGMA: float = 2.5
    DEFAULT_LOOKBACK_DAYS: int = 365
    DEFAULT_FREQUENCY_LOOKBACK_DAYS: int = 90
    DEFAULT_FREQUENCY_SIGMA: float = 2.0
    MIN_SAMPLES_FOR_STATISTICS: int = 3

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # Hauptmethoden
    # =========================================================================

    async def run_all_checks(self, company_id: UUID) -> List[Anomaly]:
        """Fuehrt alle aktiven Anomalie-Pruefungen durch.

        Laedt die aktiven Regeln und fuehrt die entsprechenden
        Pruefungen aus. Neue Anomalien werden in der DB gespeichert.

        Args:
            company_id: Mandanten-ID

        Returns:
            Liste aller neu erkannten Anomalien
        """
        all_anomalies: List[Anomaly] = []

        # Lade aktive Regeln fuer diesen Mandanten
        rules = await self._get_active_rules(company_id)
        rule_types = {r.rule_type for r in rules}
        rule_map: Dict[str, AnomalyRule] = {r.rule_type: r for r in rules}

        check_methods = {
            AnomalyRuleType.DUPLICATE_INVOICE.value: self.check_duplicate_invoices,
            AnomalyRuleType.AMOUNT_OUTLIER.value: self.check_amount_outliers,
            AnomalyRuleType.SUPPLIER_CHANGE.value: self.check_supplier_changes,
            AnomalyRuleType.MISSING_CHAIN_DOC.value: self.check_missing_chain_documents,
            AnomalyRuleType.UNUSUAL_FREQUENCY.value: self.check_unusual_frequency,
            AnomalyRuleType.AMOUNT_THRESHOLD.value: self.check_amount_threshold,
        }

        for rule_type, check_method in check_methods.items():
            if rule_type not in rule_types:
                continue

            rule = rule_map[rule_type]
            try:
                if rule_type == AnomalyRuleType.AMOUNT_OUTLIER.value:
                    sigma = float(
                        (rule.config or {}).get(
                            "threshold_sigma", self.DEFAULT_SIGMA
                        )
                    )
                    anomalies = await check_method(
                        company_id, sigma=sigma, rule=rule
                    )
                else:
                    anomalies = await check_method(company_id, rule=rule)
                all_anomalies.extend(anomalies)
            except Exception as exc:
                logger.warning(
                    "anomaly_check_failed",
                    rule_type=rule_type,
                    company_id=str(company_id),
                    **safe_error_log(exc),
                )

        if all_anomalies:
            self.session.add_all(all_anomalies)
            await self.session.flush()

        logger.info(
            "anomaly_run_all_checks_completed",
            company_id=str(company_id),
            total_anomalies=len(all_anomalies),
            rules_checked=len(rule_types & set(check_methods.keys())),
        )

        return all_anomalies

    # =========================================================================
    # Einzelne Pruefungen
    # =========================================================================

    async def check_duplicate_invoices(
        self,
        company_id: UUID,
        rule: Optional[AnomalyRule] = None,
    ) -> List[Anomaly]:
        """Prueft auf doppelte Rechnungen.

        Erkennt Rechnungen mit gleicher Nummer und gleichem Lieferanten.
        GROUP BY invoice_number, business_entity_id HAVING COUNT(*) > 1.

        Args:
            company_id: Mandanten-ID
            rule: Optionale Regel-Referenz

        Returns:
            Liste erkannter Duplikat-Anomalien
        """
        # Suche nach Duplikaten: gleiche Rechnungsnummer + gleicher Lieferant
        stmt = (
            select(
                InvoiceTracking.invoice_number,
                Document.business_entity_id,
                func.count(InvoiceTracking.id).label("cnt"),
                func.array_agg(InvoiceTracking.id).label("invoice_ids"),
                func.array_agg(InvoiceTracking.amount).label("amounts"),
            )
            .join(
                Document,
                and_(
                    Document.id == InvoiceTracking.document_id,
                    Document.deleted_at.is_(None),
                ),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_number.isnot(None),
                    InvoiceTracking.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                )
            )
            .group_by(
                InvoiceTracking.invoice_number,
                Document.business_entity_id,
            )
            .having(func.count(InvoiceTracking.id) > 1)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        anomalies: List[Anomaly] = []

        for row in rows:
            invoice_number = row.invoice_number
            entity_id = row.business_entity_id
            count = row.cnt
            invoice_ids = row.invoice_ids
            amounts = row.amounts

            # Duplikat bereits als offene Anomalie vorhanden?
            existing = await self._anomaly_exists(
                company_id=company_id,
                anomaly_type=AnomalyRuleType.DUPLICATE_INVOICE.value,
                source_table="invoice_tracking",
                source_id=invoice_ids[0],
            )
            if existing:
                continue

            # Score: 0.7 fuer exakten Betrag, 0.5 fuer aehnliche Betraege
            amounts_set = set(amounts)
            score = 0.7 if len(amounts_set) == 1 else 0.5

            anomaly = Anomaly(
                rule_id=rule.id if rule else None,
                anomaly_type=AnomalyRuleType.DUPLICATE_INVOICE.value,
                severity=(
                    rule.severity
                    if rule
                    else AnomalySeverity.WARNING.value
                ),
                title=(
                    f"Doppelte Rechnung erkannt: {invoice_number} "
                    f"({count} Eintraege)"
                ),
                description=(
                    f"Die Rechnungsnummer '{invoice_number}' existiert "
                    f"{count}-mal fuer denselben Lieferanten. "
                    f"Bitte pruefen Sie, ob es sich um eine "
                    f"Doppelerfassung handelt."
                ),
                source_table="invoice_tracking",
                source_id=invoice_ids[0],
                related_ids=[str(uid) for uid in invoice_ids[1:]],
                score=score,
                details={
                    "invoice_number": invoice_number,
                    "entity_id": str(entity_id),
                    "duplicate_count": count,
                    "amounts": amounts,
                },
                company_id=company_id,
            )
            anomalies.append(anomaly)

        return anomalies

    async def check_amount_outliers(
        self,
        company_id: UUID,
        sigma: float = 2.5,
        rule: Optional[AnomalyRule] = None,
    ) -> List[Anomaly]:
        """Erkennt Betrags-Ausreisser pro Lieferant.

        Berechnet Mittelwert und Standardabweichung der letzten
        12 Monate pro Lieferant. Meldet Rechnungen mit Betraegen
        ueber mean + sigma * stddev.

        Args:
            company_id: Mandanten-ID
            sigma: Sigma-Schwellenwert (Standard: 2.5)
            rule: Optionale Regel-Referenz

        Returns:
            Liste erkannter Betrags-Anomalien
        """
        lookback_days = (
            int((rule.config or {}).get(
                "lookback_days", self.DEFAULT_LOOKBACK_DAYS
            ))
            if rule
            else self.DEFAULT_LOOKBACK_DAYS
        )
        cutoff = utc_now() - timedelta(days=lookback_days)

        # Statistiken pro Lieferant berechnen
        stats_stmt = (
            select(
                Document.business_entity_id,
                func.avg(InvoiceTracking.amount).label("avg_amount"),
                func.stddev_pop(InvoiceTracking.amount).label("stddev_amount"),
                func.count(InvoiceTracking.id).label("invoice_count"),
            )
            .join(
                Document,
                and_(
                    Document.id == InvoiceTracking.document_id,
                    Document.deleted_at.is_(None),
                ),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= cutoff,
                    InvoiceTracking.amount > 0,
                    InvoiceTracking.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                )
            )
            .group_by(Document.business_entity_id)
            .having(
                func.count(InvoiceTracking.id) >= self.MIN_SAMPLES_FOR_STATISTICS
            )
        )

        stats_result = await self.session.execute(stats_stmt)
        entity_stats = stats_result.all()

        anomalies: List[Anomaly] = []

        for stat in entity_stats:
            entity_id = stat.business_entity_id
            avg_amount = float(stat.avg_amount or 0)
            stddev_amount = float(stat.stddev_amount or 0)
            invoice_count = stat.invoice_count

            if stddev_amount == 0 or math.isnan(stddev_amount):
                continue

            threshold = avg_amount + sigma * stddev_amount

            # Finde Rechnungen ueber dem Schwellenwert
            outlier_stmt = (
                select(InvoiceTracking)
                .join(
                    Document,
                    and_(
                        Document.id == InvoiceTracking.document_id,
                        Document.deleted_at.is_(None),
                    ),
                )
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= cutoff,
                        InvoiceTracking.amount > threshold,
                        InvoiceTracking.deleted_at.is_(None),
                        Document.business_entity_id == entity_id,
                    )
                )
            )

            outlier_result = await self.session.execute(outlier_stmt)
            outliers = outlier_result.scalars().all()

            for invoice in outliers:
                existing = await self._anomaly_exists(
                    company_id=company_id,
                    anomaly_type=AnomalyRuleType.AMOUNT_OUTLIER.value,
                    source_table="invoice_tracking",
                    source_id=invoice.id,
                )
                if existing:
                    continue

                deviation = (
                    (float(invoice.amount) - avg_amount) / stddev_amount
                    if stddev_amount > 0
                    else 0
                )
                # Score: normalisiert auf 0-1 basierend auf Sigma-Abweichung
                score = min(1.0, deviation / (sigma * 2))

                anomaly = Anomaly(
                    rule_id=rule.id if rule else None,
                    anomaly_type=AnomalyRuleType.AMOUNT_OUTLIER.value,
                    severity=(
                        AnomalySeverity.CRITICAL.value
                        if deviation > sigma * 2
                        else (
                            rule.severity
                            if rule
                            else AnomalySeverity.WARNING.value
                        )
                    ),
                    title=(
                        f"Ungewoehnlich hoher Rechnungsbetrag: "
                        f"{invoice.amount:.2f} {invoice.currency}"
                    ),
                    description=(
                        f"Der Rechnungsbetrag liegt {deviation:.1f} "
                        f"Standardabweichungen ueber dem Durchschnitt "
                        f"({avg_amount:.2f} {invoice.currency}) "
                        f"fuer diesen Lieferanten "
                        f"(basierend auf {invoice_count} Rechnungen)."
                    ),
                    source_table="invoice_tracking",
                    source_id=invoice.id,
                    related_ids=[str(entity_id)],
                    score=score,
                    details={
                        "amount": float(invoice.amount),
                        "currency": invoice.currency,
                        "avg_amount": round(avg_amount, 2),
                        "stddev_amount": round(stddev_amount, 2),
                        "threshold": round(threshold, 2),
                        "sigma_deviation": round(deviation, 2),
                        "entity_id": str(entity_id),
                        "sample_size": invoice_count,
                    },
                    company_id=company_id,
                )
                anomalies.append(anomaly)

        return anomalies

    async def check_supplier_changes(
        self,
        company_id: UUID,
        rule: Optional[AnomalyRule] = None,
    ) -> List[Anomaly]:
        """Erkennt verdaechtige Aenderungen an Lieferantendaten.

        Prueft auf kuerzliche IBAN-Aenderungen bei Lieferanten durch
        Vergleich mit der IBAN-Baseline-Tabelle.

        Args:
            company_id: Mandanten-ID
            rule: Optionale Regel-Referenz

        Returns:
            Liste erkannter Lieferanten-Aenderungs-Anomalien
        """
        from app.db.models_fraud import IBANBaseline

        lookback_days = (
            int((rule.config or {}).get("lookback_days", 30))
            if rule
            else 30
        )
        cutoff = utc_now() - timedelta(days=lookback_days)

        # Finde Lieferanten mit mehreren IBANs (aktiv + kuerzlich geaendert)
        stmt = (
            select(
                IBANBaseline.entity_id,
                func.count(IBANBaseline.id).label("iban_count"),
            )
            .where(
                and_(
                    IBANBaseline.company_id == company_id,
                    IBANBaseline.is_active.is_(True),
                )
            )
            .group_by(IBANBaseline.entity_id)
            .having(func.count(IBANBaseline.id) > 1)
        )

        result = await self.session.execute(stmt)
        multi_iban_entities = result.all()

        anomalies: List[Anomaly] = []

        for row in multi_iban_entities:
            entity_id = row.entity_id

            # Pruefe ob eine kuerzliche Aenderung vorliegt
            recent_stmt = (
                select(IBANBaseline)
                .where(
                    and_(
                        IBANBaseline.entity_id == entity_id,
                        IBANBaseline.company_id == company_id,
                        IBANBaseline.is_active.is_(True),
                        IBANBaseline.first_seen_at >= cutoff,
                    )
                )
                .order_by(IBANBaseline.first_seen_at.desc())
            )

            recent_result = await self.session.execute(recent_stmt)
            recent_ibans = recent_result.scalars().all()

            if not recent_ibans:
                continue

            existing = await self._anomaly_exists(
                company_id=company_id,
                anomaly_type=AnomalyRuleType.SUPPLIER_CHANGE.value,
                source_table="business_entities",
                source_id=entity_id,
            )
            if existing:
                continue

            is_verified = all(ib.is_verified for ib in recent_ibans)
            score = 0.3 if is_verified else 0.8

            anomaly = Anomaly(
                rule_id=rule.id if rule else None,
                anomaly_type=AnomalyRuleType.SUPPLIER_CHANGE.value,
                severity=(
                    AnomalySeverity.INFO.value
                    if is_verified
                    else (
                        rule.severity
                        if rule
                        else AnomalySeverity.WARNING.value
                    )
                ),
                title=(
                    f"Neue Bankverbindung bei Lieferant erkannt "
                    f"({row.iban_count} aktive IBANs)"
                ),
                description=(
                    f"Fuer diesen Lieferanten wurden {row.iban_count} "
                    f"aktive Bankverbindungen gefunden. "
                    f"Neue IBAN(s) seit {cutoff.strftime('%d.%m.%Y')} "
                    f"hinzugefuegt. "
                    + (
                        "Alle IBANs sind verifiziert."
                        if is_verified
                        else "ACHTUNG: Nicht alle IBANs sind verifiziert!"
                    )
                ),
                source_table="business_entities",
                source_id=entity_id,
                related_ids=[str(ib.id) for ib in recent_ibans],
                score=score,
                details={
                    "entity_id": str(entity_id),
                    "active_iban_count": row.iban_count,
                    "new_ibans_count": len(recent_ibans),
                    "all_verified": is_verified,
                },
                company_id=company_id,
            )
            anomalies.append(anomaly)

        return anomalies

    async def check_missing_chain_documents(
        self,
        company_id: UUID,
        rule: Optional[AnomalyRule] = None,
    ) -> List[Anomaly]:
        """Findet fehlende Dokumente in Auftragsketten.

        Prueft ob Rechnungen einen zugehoerigen Lieferschein haben
        und ob Auftraege ein Angebot referenzieren.

        Erwartete Kette: Angebot -> Auftrag -> Lieferschein -> Rechnung

        Args:
            company_id: Mandanten-ID
            rule: Optionale Regel-Referenz

        Returns:
            Liste erkannter Luecken in Auftragsketten
        """
        lookback_days = (
            int((rule.config or {}).get("lookback_days", 90))
            if rule
            else 90
        )
        cutoff = utc_now() - timedelta(days=lookback_days)

        # Finde Rechnungen mit chain_id aber ohne Lieferschein in derselben Kette
        invoice_stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == DocumentType.INVOICE.value,
                    Document.chain_id.isnot(None),
                    Document.created_at >= cutoff,
                    Document.deleted_at.is_(None),
                )
            )
        )

        invoice_result = await self.session.execute(invoice_stmt)
        invoices = invoice_result.scalars().all()

        anomalies: List[Anomaly] = []

        for invoice in invoices:
            # Pruefe ob ein Lieferschein in derselben Kette existiert
            delivery_stmt = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.chain_id == invoice.chain_id,
                        Document.document_type == DocumentType.DELIVERY_NOTE.value,
                        Document.deleted_at.is_(None),
                    )
                )
            )

            delivery_result = await self.session.execute(delivery_stmt)
            delivery_count = delivery_result.scalar() or 0

            if delivery_count > 0:
                continue

            existing = await self._anomaly_exists(
                company_id=company_id,
                anomaly_type=AnomalyRuleType.MISSING_CHAIN_DOC.value,
                source_table="documents",
                source_id=invoice.id,
            )
            if existing:
                continue

            anomaly = Anomaly(
                rule_id=rule.id if rule else None,
                anomaly_type=AnomalyRuleType.MISSING_CHAIN_DOC.value,
                severity=(
                    rule.severity
                    if rule
                    else AnomalySeverity.INFO.value
                ),
                title=(
                    f"Fehlender Lieferschein in Auftragskette "
                    f"'{invoice.chain_id}'"
                ),
                description=(
                    f"Fuer die Rechnung '{invoice.filename}' in "
                    f"Auftragskette '{invoice.chain_id}' wurde kein "
                    f"zugehoeriger Lieferschein gefunden. "
                    f"Bitte pruefen Sie die Vollstaendigkeit."
                ),
                source_table="documents",
                source_id=invoice.id,
                related_ids=[],
                score=0.4,
                details={
                    "chain_id": invoice.chain_id,
                    "document_type": invoice.document_type,
                    "missing_type": "delivery_note",
                },
                company_id=company_id,
            )
            anomalies.append(anomaly)

        return anomalies

    async def check_unusual_frequency(
        self,
        company_id: UUID,
        rule: Optional[AnomalyRule] = None,
    ) -> List[Anomaly]:
        """Erkennt ungewoehnliche Rechnungshaeufigkeit pro Lieferant.

        Vergleicht die aktuelle Rechnungshaeufigkeit mit dem
        historischen Durchschnitt pro Lieferant.

        Args:
            company_id: Mandanten-ID
            rule: Optionale Regel-Referenz

        Returns:
            Liste erkannter Frequenz-Anomalien
        """
        lookback_days = (
            int((rule.config or {}).get(
                "lookback_days", self.DEFAULT_FREQUENCY_LOOKBACK_DAYS
            ))
            if rule
            else self.DEFAULT_FREQUENCY_LOOKBACK_DAYS
        )
        frequency_sigma = (
            float((rule.config or {}).get(
                "frequency_sigma", self.DEFAULT_FREQUENCY_SIGMA
            ))
            if rule
            else self.DEFAULT_FREQUENCY_SIGMA
        )

        cutoff = utc_now() - timedelta(days=lookback_days)
        recent_cutoff = utc_now() - timedelta(days=30)

        # Historische Haeufigkeit pro Lieferant (Rechnungen pro Monat)
        # Gesamtzeitraum
        hist_stmt = (
            select(
                Document.business_entity_id,
                func.count(InvoiceTracking.id).label("total_invoices"),
            )
            .join(
                Document,
                and_(
                    Document.id == InvoiceTracking.document_id,
                    Document.deleted_at.is_(None),
                ),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= cutoff,
                    InvoiceTracking.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                )
            )
            .group_by(Document.business_entity_id)
            .having(
                func.count(InvoiceTracking.id)
                >= self.MIN_SAMPLES_FOR_STATISTICS
            )
        )

        hist_result = await self.session.execute(hist_stmt)
        hist_data = hist_result.all()

        # Aktuelle Haeufigkeit (letzte 30 Tage)
        recent_stmt = (
            select(
                Document.business_entity_id,
                func.count(InvoiceTracking.id).label("recent_invoices"),
            )
            .join(
                Document,
                and_(
                    Document.id == InvoiceTracking.document_id,
                    Document.deleted_at.is_(None),
                ),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= recent_cutoff,
                    InvoiceTracking.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                )
            )
            .group_by(Document.business_entity_id)
        )

        recent_result = await self.session.execute(recent_stmt)
        recent_map: Dict[UUID, int] = {
            row.business_entity_id: row.recent_invoices
            for row in recent_result.all()
        }

        anomalies: List[Anomaly] = []
        months = max(1, lookback_days / 30.0)

        for row in hist_data:
            entity_id = row.business_entity_id
            total = row.total_invoices
            monthly_avg = total / months
            monthly_stddev = math.sqrt(monthly_avg)  # Poisson-Approximation

            if monthly_stddev == 0:
                continue

            recent_count = recent_map.get(entity_id, 0)
            threshold = monthly_avg + frequency_sigma * monthly_stddev

            if recent_count <= threshold:
                continue

            existing = await self._anomaly_exists(
                company_id=company_id,
                anomaly_type=AnomalyRuleType.UNUSUAL_FREQUENCY.value,
                source_table="business_entities",
                source_id=entity_id,
            )
            if existing:
                continue

            deviation = (
                (recent_count - monthly_avg) / monthly_stddev
                if monthly_stddev > 0
                else 0
            )
            score = min(1.0, deviation / (frequency_sigma * 2))

            anomaly = Anomaly(
                rule_id=rule.id if rule else None,
                anomaly_type=AnomalyRuleType.UNUSUAL_FREQUENCY.value,
                severity=(
                    rule.severity
                    if rule
                    else AnomalySeverity.WARNING.value
                ),
                title=(
                    f"Ungewoehnlich viele Rechnungen: "
                    f"{recent_count} in 30 Tagen "
                    f"(Durchschnitt: {monthly_avg:.1f}/Monat)"
                ),
                description=(
                    f"Fuer diesen Lieferanten wurden in den letzten "
                    f"30 Tagen {recent_count} Rechnungen erfasst. "
                    f"Der historische Durchschnitt liegt bei "
                    f"{monthly_avg:.1f} Rechnungen pro Monat "
                    f"({total} Rechnungen in {months:.0f} Monaten). "
                    f"Die Abweichung betraegt {deviation:.1f} Sigma."
                ),
                source_table="business_entities",
                source_id=entity_id,
                related_ids=[],
                score=score,
                details={
                    "entity_id": str(entity_id),
                    "recent_count": recent_count,
                    "monthly_avg": round(monthly_avg, 2),
                    "monthly_stddev": round(monthly_stddev, 2),
                    "threshold": round(threshold, 2),
                    "sigma_deviation": round(deviation, 2),
                    "lookback_days": lookback_days,
                },
                company_id=company_id,
            )
            anomalies.append(anomaly)

        return anomalies

    async def check_amount_threshold(
        self,
        company_id: UUID,
        rule: Optional[AnomalyRule] = None,
    ) -> List[Anomaly]:
        """Prueft ob Rechnungsbetraege einen konfigurierten Schwellenwert ueberschreiten.

        Laedt aktive amount_threshold Regeln und vergleicht
        Rechnungsbetraege mit dem konfigurierten Maximalwert.
        Erstellt Anomalien fuer jede Ueberschreitung.

        Args:
            company_id: Mandanten-ID
            rule: Optionale Regel-Referenz

        Returns:
            Liste erkannter Schwellenwert-Anomalien
        """
        max_amount = float((rule.config or {}).get("max_amount", 0))
        if max_amount <= 0:
            logger.debug(
                "amount_threshold_skipped_no_max",
                company_id=str(company_id),
            )
            return []

        raw_currency = (rule.config or {}).get("currency")
        stripped_currency = raw_currency.strip() if isinstance(raw_currency, str) else ""
        currency_filter = stripped_currency.upper() if stripped_currency else None
        lookback_days = int((rule.config or {}).get("lookback_days", 90))
        cutoff = utc_now() - timedelta(days=lookback_days)

        # Finde Rechnungen ueber dem Schwellenwert
        stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.amount > 0,
                    InvoiceTracking.amount > max_amount,
                    InvoiceTracking.created_at >= cutoff,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )

        if currency_filter:
            stmt = stmt.where(InvoiceTracking.currency == currency_filter)

        result = await self.session.execute(stmt)
        invoices = result.scalars().all()

        anomalies: List[Anomaly] = []

        for invoice in invoices:
            existing = await self._anomaly_exists(
                company_id=company_id,
                anomaly_type=AnomalyRuleType.AMOUNT_THRESHOLD.value,
                source_table="invoice_tracking",
                source_id=invoice.id,
            )
            if existing:
                continue

            excess_ratio = float(invoice.amount) / max_amount
            # Score: 0.5 fuer knapp drueber, bis 1.0 fuer deutlich drueber
            score = min(1.0, 0.5 + (excess_ratio - 1.0) * 0.5)

            anomaly = Anomaly(
                rule_id=rule.id if rule else None,
                anomaly_type=AnomalyRuleType.AMOUNT_THRESHOLD.value,
                severity=(
                    AnomalySeverity.CRITICAL.value
                    if excess_ratio > 2.0
                    else (
                        rule.severity
                        if rule
                        else AnomalySeverity.WARNING.value
                    )
                ),
                title=(
                    f"Rechnungsbetrag ueberschreitet Schwellenwert: "
                    f"{invoice.amount:.2f} {invoice.currency} "
                    f"(Limit: {max_amount:.2f})"
                ),
                description=(
                    f"Der Rechnungsbetrag von {invoice.amount:.2f} "
                    f"{invoice.currency} ueberschreitet den "
                    f"konfigurierten Schwellenwert von "
                    f"{max_amount:.2f} {invoice.currency} "
                    f"um {(excess_ratio - 1.0) * 100:.0f}%. "
                    f"Bitte pruefen Sie diese Rechnung."
                ),
                source_table="invoice_tracking",
                source_id=invoice.id,
                related_ids=[],
                score=score,
                details={
                    "amount": float(invoice.amount),
                    "currency": invoice.currency,
                    "max_amount": max_amount,
                    "excess_ratio": round(excess_ratio, 2),
                    "lookback_days": lookback_days,
                },
                company_id=company_id,
            )
            anomalies.append(anomaly)

        return anomalies

    # =========================================================================
    # Status-Verwaltung
    # =========================================================================

    async def resolve_anomaly(
        self,
        anomaly_id: UUID,
        user_id: UUID,
        status: str,
        note: Optional[str] = None,
    ) -> Anomaly:
        """Markiert Anomalie als aufgeloest oder Fehlalarm.

        Args:
            anomaly_id: ID der Anomalie
            user_id: ID des bearbeitenden Benutzers
            status: Neuer Status (resolved/false_positive)
            note: Optionale Begruendung

        Returns:
            Aktualisierte Anomalie

        Raises:
            ValueError: Ungueltiger Status
        """
        valid_statuses = {
            AnomalyStatus.RESOLVED.value,
            AnomalyStatus.FALSE_POSITIVE.value,
            AnomalyStatus.INVESTIGATING.value,
        }
        if status not in valid_statuses:
            raise ValueError(
                f"Ungueltiger Status '{status}'. "
                f"Erlaubt: {', '.join(sorted(valid_statuses))}"
            )

        stmt = select(Anomaly).where(Anomaly.id == anomaly_id)
        result = await self.session.execute(stmt)
        anomaly = result.scalar_one_or_none()

        if anomaly is None:
            raise ValueError(f"Anomalie nicht gefunden: {anomaly_id}")

        anomaly.status = status
        anomaly.resolved_by_id = user_id
        anomaly.resolution_note = note

        if status in (
            AnomalyStatus.RESOLVED.value,
            AnomalyStatus.FALSE_POSITIVE.value,
        ):
            anomaly.resolved_at = utc_now()

        await self.session.flush()

        logger.info(
            "anomaly_resolved",
            anomaly_id=str(anomaly_id),
            new_status=status,
        )

        return anomaly

    # =========================================================================
    # Statistiken
    # =========================================================================

    async def get_anomaly_stats(
        self, company_id: UUID
    ) -> Dict[str, object]:
        """Statistiken: offene, geloeste, Fehlalarme pro Typ.

        Args:
            company_id: Mandanten-ID

        Returns:
            Dictionary mit Anomalie-Statistiken
        """
        # Gesamt nach Status
        status_stmt = (
            select(
                Anomaly.status,
                func.count(Anomaly.id).label("count"),
            )
            .where(Anomaly.company_id == company_id)
            .group_by(Anomaly.status)
        )
        status_result = await self.session.execute(status_stmt)
        by_status: Dict[str, int] = {
            row.status: row.count for row in status_result.all()
        }

        # Gesamt nach Typ
        type_stmt = (
            select(
                Anomaly.anomaly_type,
                func.count(Anomaly.id).label("count"),
            )
            .where(Anomaly.company_id == company_id)
            .group_by(Anomaly.anomaly_type)
        )
        type_result = await self.session.execute(type_stmt)
        by_type: Dict[str, int] = {
            row.anomaly_type: row.count for row in type_result.all()
        }

        # Gesamt nach Schweregrad
        severity_stmt = (
            select(
                Anomaly.severity,
                func.count(Anomaly.id).label("count"),
            )
            .where(Anomaly.company_id == company_id)
            .group_by(Anomaly.severity)
        )
        severity_result = await self.session.execute(severity_stmt)
        by_severity: Dict[str, int] = {
            row.severity: row.count for row in severity_result.all()
        }

        total = sum(by_status.values())
        open_count = by_status.get(AnomalyStatus.OPEN.value, 0)
        investigating_count = by_status.get(
            AnomalyStatus.INVESTIGATING.value, 0
        )

        return {
            "total": total,
            "open": open_count,
            "investigating": investigating_count,
            "resolved": by_status.get(AnomalyStatus.RESOLVED.value, 0),
            "false_positive": by_status.get(
                AnomalyStatus.FALSE_POSITIVE.value, 0
            ),
            "by_type": by_type,
            "by_severity": by_severity,
        }

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    async def _get_active_rules(
        self, company_id: UUID
    ) -> List[AnomalyRule]:
        """Laedt alle aktiven Regeln fuer einen Mandanten."""
        stmt = (
            select(AnomalyRule)
            .where(
                and_(
                    AnomalyRule.company_id == company_id,
                    AnomalyRule.is_active.is_(True),
                )
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _anomaly_exists(
        self,
        company_id: UUID,
        anomaly_type: str,
        source_table: str,
        source_id: UUID,
    ) -> bool:
        """Prueft ob eine offene Anomalie bereits existiert."""
        stmt = (
            select(func.count(Anomaly.id))
            .where(
                and_(
                    Anomaly.company_id == company_id,
                    Anomaly.anomaly_type == anomaly_type,
                    Anomaly.source_table == source_table,
                    Anomaly.source_id == source_id,
                    Anomaly.status.in_([
                        AnomalyStatus.OPEN.value,
                        AnomalyStatus.INVESTIGATING.value,
                    ]),
                )
            )
        )
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count > 0
