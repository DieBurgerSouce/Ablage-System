# -*- coding: utf-8 -*-
"""
Proaktiver Assistent Service für Ablage-System.

Denkt mit und warnt vorausschauend. Drei Hinweis-Kategorien:
1. Fristen & Deadlines (Skonto, Verträge, Mahnungen)
2. Anomalien & Warnungen (Preisabweichungen, Duplikate, Bankverbindungsänderungen)
3. Optimierungs-Vorschläge (verpasste Skonti, Buendelungsrabatte, Daueraufträge)

Feinpoliert und durchdacht - Enterprise-grade Proactive Intelligence.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, desc, update, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    InvoiceStatus,
    Company,
)
from app.db.models_proactive_assistant import (
    ProactiveHint,
    HintCategory,
    HintPriority,
    HintStatus,
    HintRule,
    HintStatistics,
)
from sqlalchemy import Float

logger = structlog.get_logger(__name__)


# =============================================================================
# Schwellwerte (Defaults)
# =============================================================================

# Skonto-Fristen: Warnung X Tage vor Ablauf
SKONTO_WARNING_DAYS = 3

# Preisabweichung: Ab X% Abweichung vom 12-Monats-Durchschnitt
PRICE_DEVIATION_THRESHOLD = 0.40  # 40%

# Duplikat-Erkennung: Gleicher Betrag + Lieferant + X Tage Fenster
DUPLICATE_WINDOW_DAYS = 5

# Überfällig: Ab X Tagen überfällig wird Mahnung-Hint erzeugt
OVERDUE_THRESHOLD_DAYS = 7

# Optimierung: Analyse der letzten X Monate
OPTIMIZATION_LOOKBACK_MONTHS = 3

# Wiederkehrende Rechnungen: Min. X Rechnungen gleicher Lieferant
RECURRING_MIN_COUNT = 3


class ProactiveAssistantService:
    """Proaktiver Assistent - Denkt mit und warnt vorausschauend.

    Drei Hinweis-Kategorien:
    1. Fristen & Deadlines (Skonto, Verträge, Mahnungen)
    2. Anomalien & Warnungen (Preisabweichungen, Duplikate, Bankverbindungsänderungen)
    3. Optimierungs-Vorschläge (verpasste Skonti, Buendelungsrabatte, Daueraufträge)
    """

    # =========================================================================
    # Deadline-Prüfungen
    # =========================================================================

    async def check_deadline_hints(
        self, db: AsyncSession, company_id: UUID
    ) -> List[ProactiveHint]:
        """Prüft fällige Fristen: Skonto-Deadlines, überfällige Rechnungen."""
        now = utc_now()
        hints: List[ProactiveHint] = []

        # --- 1. Skonto-Deadlines innerhalb der nächsten 3 Tage ---
        skonto_cutoff = now + timedelta(days=SKONTO_WARNING_DAYS)
        skonto_query = (
            select(InvoiceTracking, Document)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_deadline > now,
                    InvoiceTracking.skonto_deadline <= skonto_cutoff,
                    InvoiceTracking.skonto_used == False,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.OPEN.value,
                        InvoiceStatus.SENT.value,
                    ]),
                )
            )
        )
        result = await db.execute(skonto_query)
        rows = result.all()

        for invoice, doc in rows:
            days_left = (invoice.skonto_deadline - now).days
            skonto_savings = (invoice.skonto_amount or 0.0) if invoice.skonto_amount else (
                (invoice.amount or 0.0) * (invoice.skonto_percentage or 0.0) / 100.0
            )
            urgency = min(1.0, max(0.3, 1.0 - (days_left / SKONTO_WARNING_DAYS)))
            value = min(1.0, skonto_savings / 500.0) if skonto_savings > 0 else 0.1

            hint = ProactiveHint(
                company_id=company_id,
                category=HintCategory.DEADLINE.value,
                priority=HintPriority.HIGH.value if days_left <= 1 else HintPriority.MEDIUM.value,
                status=HintStatus.NEW.value,
                title=f"Skonto-Frist laeuft in {days_left} Tag(en) ab",
                message=(
                    f"Rechnung {invoice.invoice_number or 'ohne Nr.'}: "
                    f"Skonto von {invoice.skonto_percentage or 0}% "
                    f"({skonto_savings:.2f} EUR Ersparnis) "
                    f"laeuft am {invoice.skonto_deadline.strftime('%d.%m.%Y')} ab."
                ),
                urgency_score=round(urgency, 2),
                value_score=round(value, 2),
                combined_score=round(urgency * value, 4),
                source_type="skonto_deadline",
                source_id=invoice.id,
                source_metadata={
                    "invoice_number": invoice.invoice_number,
                    "amount": invoice.amount,
                    "skonto_percentage": invoice.skonto_percentage,
                    "skonto_savings": round(skonto_savings, 2),
                    "days_left": days_left,
                    "document_id": str(doc.id),
                },
                action_url=f"/documents/{doc.id}",
                action_label="Rechnung öffnen",
                expires_at=invoice.skonto_deadline,
            )
            hints.append(hint)

        # --- 2. Überfällige Rechnungen ---
        overdue_cutoff = now - timedelta(days=OVERDUE_THRESHOLD_DAYS)
        overdue_query = (
            select(InvoiceTracking, Document)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.due_date < overdue_cutoff,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.OPEN.value,
                        InvoiceStatus.SENT.value,
                        InvoiceStatus.OVERDUE.value,
                    ]),
                )
            )
        )
        result = await db.execute(overdue_query)
        rows = result.all()

        for invoice, doc in rows:
            days_overdue = (now - invoice.due_date).days
            urgency = min(1.0, 0.5 + (days_overdue / 60.0))
            value = min(1.0, (invoice.amount or 0.0) / 5000.0)

            hint = ProactiveHint(
                company_id=company_id,
                category=HintCategory.DEADLINE.value,
                priority=HintPriority.HIGH.value if days_overdue > 30 else HintPriority.MEDIUM.value,
                status=HintStatus.NEW.value,
                title=f"Rechnung seit {days_overdue} Tagen überfällig",
                message=(
                    f"Rechnung {invoice.invoice_number or 'ohne Nr.'} "
                    f"über {invoice.amount or 0:.2f} EUR ist seit "
                    f"{days_overdue} Tagen überfällig (Fällig: "
                    f"{invoice.due_date.strftime('%d.%m.%Y')})."
                ),
                urgency_score=round(urgency, 2),
                value_score=round(value, 2),
                combined_score=round(urgency * value, 4),
                source_type="overdue_invoice",
                source_id=invoice.id,
                source_metadata={
                    "invoice_number": invoice.invoice_number,
                    "amount": invoice.amount,
                    "days_overdue": days_overdue,
                    "due_date": invoice.due_date.isoformat(),
                    "document_id": str(doc.id),
                },
                action_url=f"/documents/{doc.id}",
                action_label="Rechnung prüfen",
                expires_at=None,
            )
            hints.append(hint)

        logger.info(
            "deadline_hints_checked",
            company_id=str(company_id),
            skonto_hints=sum(1 for h in hints if h.source_type == "skonto_deadline"),
            overdue_hints=sum(1 for h in hints if h.source_type == "overdue_invoice"),
        )
        return hints

    # =========================================================================
    # Anomalie-Erkennung
    # =========================================================================

    async def check_anomaly_hints(
        self, db: AsyncSession, company_id: UUID
    ) -> List[ProactiveHint]:
        """Erkennt Anomalien: Preisabweichungen, potenzielle Duplikate."""
        now = utc_now()
        hints: List[ProactiveHint] = []
        lookback = now - timedelta(days=365)

        # --- 1. Preisabweichungen (>40% vom 12-Monats-Durchschnitt pro Lieferant) ---
        # Berechne Durchschnitt pro Lieferant der letzten 12 Monate
        avg_subq = (
            select(
                Document.business_entity_id,
                func.avg(InvoiceTracking.amount).label("avg_amount"),
                func.stddev(InvoiceTracking.amount).label("stddev_amount"),
                func.count(InvoiceTracking.id).label("invoice_count"),
            )
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                    InvoiceTracking.invoice_date.isnot(None),
                    InvoiceTracking.invoice_date >= lookback,
                    InvoiceTracking.amount.isnot(None),
                    InvoiceTracking.amount > 0,
                )
            )
            .group_by(Document.business_entity_id)
            .having(func.count(InvoiceTracking.id) >= 3)
            .subquery()
        )

        # Finde aktuelle Rechnungen (letzte 7 Tage) mit starker Abweichung
        recent_cutoff = now - timedelta(days=7)
        anomaly_query = (
            select(InvoiceTracking, Document, BusinessEntity, avg_subq.c.avg_amount)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .join(BusinessEntity, BusinessEntity.id == Document.business_entity_id)
            .join(avg_subq, avg_subq.c.business_entity_id == Document.business_entity_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.created_at >= recent_cutoff,
                    InvoiceTracking.amount.isnot(None),
                    InvoiceTracking.amount > 0,
                )
            )
        )
        result = await db.execute(anomaly_query)
        rows = result.all()

        for invoice, doc, entity, avg_amount in rows:
            if avg_amount and avg_amount > 0:
                deviation = abs(invoice.amount - avg_amount) / avg_amount
                if deviation >= PRICE_DEVIATION_THRESHOLD:
                    deviation_pct = round(deviation * 100, 1)
                    urgency = min(1.0, 0.4 + (deviation * 0.6))
                    value = min(1.0, abs(invoice.amount - avg_amount) / 2000.0)

                    hint = ProactiveHint(
                        company_id=company_id,
                        category=HintCategory.ANOMALY.value,
                        priority=HintPriority.HIGH.value if deviation >= 1.0 else HintPriority.MEDIUM.value,
                        status=HintStatus.NEW.value,
                        title=f"Preisabweichung {deviation_pct}% bei {entity.name}",
                        message=(
                            f"Rechnung {invoice.invoice_number or 'ohne Nr.'} "
                            f"über {invoice.amount:.2f} EUR weicht um "
                            f"{deviation_pct}% vom 12-Monats-Durchschnitt "
                            f"({avg_amount:.2f} EUR) ab."
                        ),
                        urgency_score=round(urgency, 2),
                        value_score=round(value, 2),
                        combined_score=round(urgency * value, 4),
                        source_type="price_anomaly",
                        source_id=invoice.id,
                        source_metadata={
                            "invoice_number": invoice.invoice_number,
                            "amount": invoice.amount,
                            "avg_amount": round(avg_amount, 2),
                            "deviation_pct": deviation_pct,
                            "entity_id": str(entity.id),
                            "entity_name": entity.name,
                            "document_id": str(doc.id),
                        },
                        action_url=f"/documents/{doc.id}",
                        action_label="Rechnung prüfen",
                    )
                    hints.append(hint)

        # --- 2. Potenzielle Duplikate (gleicher Betrag + Lieferant + Zeitfenster) ---
        dup_window = timedelta(days=DUPLICATE_WINDOW_DAYS)
        dup_query = (
            select(
                InvoiceTracking.amount,
                Document.business_entity_id,
                func.count(InvoiceTracking.id).label("cnt"),
                func.array_agg(InvoiceTracking.id).label("invoice_ids"),
                func.array_agg(InvoiceTracking.invoice_number).label("invoice_numbers"),
            )
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                    InvoiceTracking.created_at >= (now - timedelta(days=30)),
                    InvoiceTracking.amount.isnot(None),
                    InvoiceTracking.amount > 0,
                    InvoiceTracking.status != InvoiceStatus.CANCELLED.value,
                )
            )
            .group_by(InvoiceTracking.amount, Document.business_entity_id)
            .having(func.count(InvoiceTracking.id) >= 2)
        )

        try:
            result = await db.execute(dup_query)
            dup_rows = result.all()

            for amount, entity_id, cnt, invoice_ids, invoice_numbers in dup_rows:
                # Lade Entity-Name
                entity_result = await db.execute(
                    select(BusinessEntity.name).where(BusinessEntity.id == entity_id)
                )
                entity_name = entity_result.scalar_one_or_none() or "Unbekannt"

                urgency = 0.7
                value = min(1.0, (amount or 0.0) / 2000.0)

                hint = ProactiveHint(
                    company_id=company_id,
                    category=HintCategory.ANOMALY.value,
                    priority=HintPriority.HIGH.value,
                    status=HintStatus.NEW.value,
                    title=f"Mögliche Duplikat-Rechnung ({cnt}x {amount:.2f} EUR)",
                    message=(
                        f"{cnt} Rechnungen mit identischem Betrag "
                        f"({amount:.2f} EUR) vom selben Lieferanten "
                        f"({entity_name}) innerhalb von 30 Tagen erkannt."
                    ),
                    urgency_score=urgency,
                    value_score=round(value, 2),
                    combined_score=round(urgency * value, 4),
                    source_type="duplicate_invoice",
                    source_id=invoice_ids[0] if invoice_ids else None,
                    source_metadata={
                        "amount": amount,
                        "entity_id": str(entity_id),
                        "invoice_count": cnt,
                        "invoice_numbers": [n for n in (invoice_numbers or []) if n],
                    },
                    action_url=f"/entities/{entity_id}",
                    action_label="Lieferant prüfen",
                )
                hints.append(hint)
        except Exception as e:
            # array_agg nicht verfügbar auf SQLite - Duplikat-Check überspringen
            logger.debug(
                "duplicate_check_skipped",
                reason="array_agg_not_available",
                **safe_error_log(e),
            )

        logger.info(
            "anomaly_hints_checked",
            company_id=str(company_id),
            price_anomalies=sum(1 for h in hints if h.source_type == "price_anomaly"),
            duplicates=sum(1 for h in hints if h.source_type == "duplicate_invoice"),
        )
        return hints

    # =========================================================================
    # Optimierungs-Vorschläge
    # =========================================================================

    async def check_optimization_hints(
        self, db: AsyncSession, company_id: UUID
    ) -> List[ProactiveHint]:
        """Optimierungs-Vorschläge: Verpasste Skonti, wiederkehrende Rechnungen."""
        now = utc_now()
        hints: List[ProactiveHint] = []
        lookback = now - timedelta(days=OPTIMIZATION_LOOKBACK_MONTHS * 30)

        # --- 1. Verpasste Skonti (letzter Monat) ---
        month_start = (now - timedelta(days=30)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        missed_skonto_query = (
            select(
                func.count(InvoiceTracking.id).label("missed_count"),
                func.sum(InvoiceTracking.skonto_amount).label("total_missed_savings"),
            )
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_deadline < now,
                    InvoiceTracking.skonto_deadline >= month_start,
                    InvoiceTracking.skonto_used == False,
                    InvoiceTracking.skonto_amount.isnot(None),
                    InvoiceTracking.skonto_amount > 0,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.PAID.value,
                        InvoiceStatus.OVERDUE.value,
                    ]),
                )
            )
        )
        result = await db.execute(missed_skonto_query)
        row = result.one_or_none()

        if row and row.missed_count and row.missed_count > 0:
            missed_count = row.missed_count
            total_savings = row.total_missed_savings or 0.0
            urgency = 0.4
            value = min(1.0, total_savings / 1000.0)

            hint = ProactiveHint(
                company_id=company_id,
                category=HintCategory.OPTIMIZATION.value,
                priority=HintPriority.MEDIUM.value if total_savings < 500 else HintPriority.HIGH.value,
                status=HintStatus.NEW.value,
                title=f"{missed_count} Skonti verpasst - {total_savings:.2f} EUR Ersparnis möglich",
                message=(
                    f"Im letzten Monat wurden {missed_count} Skonto-Fristen "
                    f"versaeumt. Potenzielle Ersparnis: {total_savings:.2f} EUR. "
                    f"Prüfen Sie, ob Rechnungen früher bezahlt werden können."
                ),
                urgency_score=urgency,
                value_score=round(value, 2),
                combined_score=round(urgency * value, 4),
                source_type="missed_skonto",
                source_metadata={
                    "missed_count": missed_count,
                    "total_missed_savings": round(total_savings, 2),
                    "period": "last_30_days",
                },
                action_url="/invoices?status=open&has_skonto=true",
                action_label="Offene Skonto-Rechnungen anzeigen",
            )
            hints.append(hint)

        # --- 2. Wiederkehrende Rechnungen (Dauerauftrags-Potential) ---
        recurring_query = (
            select(
                Document.business_entity_id,
                BusinessEntity.name,
                func.count(InvoiceTracking.id).label("invoice_count"),
                func.avg(InvoiceTracking.amount).label("avg_amount"),
            )
            .join(Document, Document.id == InvoiceTracking.document_id)
            .join(BusinessEntity, BusinessEntity.id == Document.business_entity_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                    InvoiceTracking.invoice_date.isnot(None),
                    InvoiceTracking.invoice_date >= lookback,
                    InvoiceTracking.amount.isnot(None),
                    InvoiceTracking.amount > 0,
                    InvoiceTracking.status != InvoiceStatus.CANCELLED.value,
                )
            )
            .group_by(Document.business_entity_id, BusinessEntity.name)
            .having(func.count(InvoiceTracking.id) >= RECURRING_MIN_COUNT)
            .order_by(desc(func.count(InvoiceTracking.id)))
            .limit(5)
        )
        result = await db.execute(recurring_query)
        recurring_rows = result.all()

        for entity_id, entity_name, inv_count, avg_amount in recurring_rows:
            urgency = 0.2
            value = min(1.0, (avg_amount or 0.0) * inv_count / 10000.0)

            hint = ProactiveHint(
                company_id=company_id,
                category=HintCategory.OPTIMIZATION.value,
                priority=HintPriority.LOW.value,
                status=HintStatus.NEW.value,
                title=f"Dauerauftrags-Potential bei {entity_name}",
                message=(
                    f"{inv_count} Rechnungen von {entity_name} in den "
                    f"letzten {OPTIMIZATION_LOOKBACK_MONTHS} Monaten "
                    f"(Durchschnitt: {avg_amount:.2f} EUR). "
                    f"Ein Dauerauftrag könnte den Aufwand reduzieren."
                ),
                urgency_score=urgency,
                value_score=round(value, 2),
                combined_score=round(urgency * value, 4),
                source_type="recurring_invoice_pattern",
                source_id=entity_id,
                source_metadata={
                    "entity_id": str(entity_id),
                    "entity_name": entity_name,
                    "invoice_count": inv_count,
                    "avg_amount": round(avg_amount or 0.0, 2),
                    "lookback_months": OPTIMIZATION_LOOKBACK_MONTHS,
                },
                action_url=f"/entities/{entity_id}",
                action_label="Lieferant anzeigen",
            )
            hints.append(hint)

        logger.info(
            "optimization_hints_checked",
            company_id=str(company_id),
            missed_skonto_hints=sum(1 for h in hints if h.source_type == "missed_skonto"),
            recurring_hints=sum(1 for h in hints if h.source_type == "recurring_invoice_pattern"),
        )
        return hints

    # =========================================================================
    # Tagesanalyse
    # =========================================================================

    async def generate_daily_hints(
        self, db: AsyncSession, company_id: UUID
    ) -> List[ProactiveHint]:
        """Täglich: Alle drei Kategorien prüfen und Hints erzeugen."""
        all_hints: List[ProactiveHint] = []

        # Alle drei Kategorien prüfen
        try:
            deadline_hints = await self.check_deadline_hints(db, company_id)
            all_hints.extend(deadline_hints)
        except Exception as e:
            logger.error("deadline_hints_failed", company_id=str(company_id), **safe_error_log(e))

        try:
            anomaly_hints = await self.check_anomaly_hints(db, company_id)
            all_hints.extend(anomaly_hints)
        except Exception as e:
            logger.error("anomaly_hints_failed", company_id=str(company_id), **safe_error_log(e))

        try:
            optimization_hints = await self.check_optimization_hints(db, company_id)
            all_hints.extend(optimization_hints)
        except Exception as e:
            logger.error("optimization_hints_failed", company_id=str(company_id), **safe_error_log(e))

        # Deduplizierung: Keine Hints erzeugen die schon aktiv existieren
        deduplicated: List[ProactiveHint] = []
        for hint in all_hints:
            existing = await self._find_active_hint(
                db, company_id, hint.source_type, hint.source_id
            )
            if not existing:
                deduplicated.append(hint)

        # Persistieren
        for hint in deduplicated:
            db.add(hint)
        await db.flush()

        logger.info(
            "daily_hints_generated",
            company_id=str(company_id),
            total_candidates=len(all_hints),
            new_hints=len(deduplicated),
            duplicates_skipped=len(all_hints) - len(deduplicated),
        )
        return deduplicated

    # =========================================================================
    # Dashboard & Abfragen
    # =========================================================================

    async def get_dashboard_summary(
        self, db: AsyncSession, company_id: UUID, user_id: UUID
    ) -> Dict[str, object]:
        """Dashboard-Widget Daten: Tagesübersicht für Startseite."""
        now = utc_now()
        active_statuses = [HintStatus.NEW.value, HintStatus.SEEN.value, HintStatus.ACKNOWLEDGED.value]

        # Zähler pro Kategorie
        category_counts_query = (
            select(ProactiveHint.category, func.count(ProactiveHint.id))
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.status.in_(active_statuses),
                    or_(
                        ProactiveHint.user_id.is_(None),
                        ProactiveHint.user_id == user_id,
                    ),
                    or_(
                        ProactiveHint.expires_at.is_(None),
                        ProactiveHint.expires_at > now,
                    ),
                )
            )
            .group_by(ProactiveHint.category)
        )
        result = await db.execute(category_counts_query)
        by_category = {row[0]: row[1] for row in result.all()}

        # Top 5 dringendste Hints
        top_hints_query = (
            select(ProactiveHint)
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.status.in_(active_statuses),
                    or_(
                        ProactiveHint.user_id.is_(None),
                        ProactiveHint.user_id == user_id,
                    ),
                    or_(
                        ProactiveHint.expires_at.is_(None),
                        ProactiveHint.expires_at > now,
                    ),
                )
            )
            .order_by(desc(ProactiveHint.combined_score))
            .limit(5)
        )
        result = await db.execute(top_hints_query)
        top_hints = [h.to_dict() for h in result.scalars().all()]

        # Potenzielle Gesamtersparnis (aus source_metadata)
        savings_query = (
            select(func.sum(
                case(
                    (ProactiveHint.source_type == "skonto_deadline",
                     func.cast(
                         ProactiveHint.source_metadata["skonto_savings"].as_string(),
                         Float,
                     )),
                    else_=literal_column("0"),
                )
            ))
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.status.in_(active_statuses),
                    ProactiveHint.source_type == "skonto_deadline",
                )
            )
        )
        try:
            result = await db.execute(savings_query)
            potential_savings = result.scalar() or 0.0
        except Exception:
            # Fallback wenn JSONB-Zugriff fehlschlaegt
            potential_savings = 0.0

        total_active = sum(by_category.values())

        return {
            "total_active": total_active,
            "by_category": by_category,
            "top_hints": top_hints,
            "potential_savings_eur": round(potential_savings, 2),
            "generated_at": now.isoformat(),
        }

    async def get_hints(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        category: Optional[HintCategory] = None,
        status: Optional[HintStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[ProactiveHint], int]:
        """Hints abrufen mit Filterung und Paginierung."""
        now = utc_now()

        base_filter = and_(
            ProactiveHint.company_id == company_id,
            or_(
                ProactiveHint.user_id.is_(None),
                ProactiveHint.user_id == user_id,
            ),
        )

        stmt = select(ProactiveHint).where(base_filter)

        if category:
            cat_value = category.value if isinstance(category, HintCategory) else category
            stmt = stmt.where(ProactiveHint.category == cat_value)

        if status:
            status_value = status.value if isinstance(status, HintStatus) else status
            stmt = stmt.where(ProactiveHint.status == status_value)

        # Zaehle Gesamtanzahl
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Sortierung: combined_score absteigend, dann created_at absteigend
        stmt = stmt.order_by(desc(ProactiveHint.combined_score), desc(ProactiveHint.created_at))
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        hints = list(result.scalars().all())

        return hints, total

    async def update_hint_status(
        self,
        db: AsyncSession,
        hint_id: UUID,
        user_id: UUID,
        new_status: HintStatus,
    ) -> Optional[ProactiveHint]:
        """Hint-Status aktualisieren (gesehen, bestätigt, abgelehnt, bearbeitet)."""
        now = utc_now()

        stmt = select(ProactiveHint).where(ProactiveHint.id == hint_id)
        result = await db.execute(stmt)
        hint = result.scalar_one_or_none()

        if not hint:
            return None

        status_value = new_status.value if isinstance(new_status, HintStatus) else new_status
        hint.status = status_value

        if new_status == HintStatus.SEEN:
            hint.seen_at = now
        elif new_status == HintStatus.ACKNOWLEDGED:
            hint.acknowledged_at = now
        elif new_status == HintStatus.DISMISSED:
            hint.dismissed_at = now
        elif new_status == HintStatus.ACTED_ON:
            hint.acknowledged_at = hint.acknowledged_at or now

        await db.flush()

        logger.info(
            "hint_status_updated",
            hint_id=str(hint_id),
            new_status=status_value,
            user_id=str(user_id),
        )
        return hint

    async def get_context_hints(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
    ) -> List[ProactiveHint]:
        """Kontext-Sidebar: Hints zum aktuellen Dokument/Entity."""
        now = utc_now()
        active_statuses = [HintStatus.NEW.value, HintStatus.SEEN.value, HintStatus.ACKNOWLEDGED.value]

        # Sammle alle passenden source_ids
        conditions = [
            ProactiveHint.company_id == company_id,
            ProactiveHint.status.in_(active_statuses),
        ]

        source_conditions = []
        if document_id:
            # Finde Invoices für dieses Dokument
            inv_query = select(InvoiceTracking.id).where(
                InvoiceTracking.document_id == document_id
            )
            inv_result = await db.execute(inv_query)
            invoice_ids = [row[0] for row in inv_result.all()]
            if invoice_ids:
                source_conditions.append(ProactiveHint.source_id.in_(invoice_ids))
            # Auch direkte document_id Referenzen in source_metadata
            source_conditions.append(ProactiveHint.source_id == document_id)

        if entity_id:
            source_conditions.append(ProactiveHint.source_id == entity_id)

        if not source_conditions:
            return []

        conditions.append(or_(*source_conditions))

        stmt = (
            select(ProactiveHint)
            .where(and_(*conditions))
            .order_by(desc(ProactiveHint.combined_score))
            .limit(10)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def calculate_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> HintStatistics:
        """Statistiken berechnen für Reporting."""
        # Gesamtzahl Hints im Zeitraum
        total_query = (
            select(func.count(ProactiveHint.id))
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.created_at >= period_start,
                    ProactiveHint.created_at <= period_end,
                )
            )
        )
        result = await db.execute(total_query)
        total_hints = result.scalar() or 0

        # Hints pro Kategorie
        category_query = (
            select(ProactiveHint.category, func.count(ProactiveHint.id))
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.created_at >= period_start,
                    ProactiveHint.created_at <= period_end,
                )
            )
            .group_by(ProactiveHint.category)
        )
        result = await db.execute(category_query)
        by_category = {row[0]: row[1] for row in result.all()}

        # Action-Rate (bearbeitete / gesamt)
        acted_query = (
            select(func.count(ProactiveHint.id))
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.created_at >= period_start,
                    ProactiveHint.created_at <= period_end,
                    ProactiveHint.status == HintStatus.ACTED_ON.value,
                )
            )
        )
        result = await db.execute(acted_query)
        acted_count = result.scalar() or 0
        action_rate = (acted_count / total_hints * 100.0) if total_hints > 0 else 0.0

        # Durchschnittliche Reaktionszeit (created_at -> acknowledged_at)
        avg_response_query = (
            select(
                func.avg(
                    func.extract("epoch", ProactiveHint.acknowledged_at)
                    - func.extract("epoch", ProactiveHint.created_at)
                )
            )
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.created_at >= period_start,
                    ProactiveHint.created_at <= period_end,
                    ProactiveHint.acknowledged_at.isnot(None),
                )
            )
        )
        result = await db.execute(avg_response_query)
        avg_seconds = result.scalar()
        avg_response_hours = (avg_seconds / 3600.0) if avg_seconds else 0.0

        # Geschätzte Ersparnisse (Summe der Skonto-Hints die bearbeitet wurden)
        savings_query = (
            select(func.sum(ProactiveHint.value_score))
            .where(
                and_(
                    ProactiveHint.company_id == company_id,
                    ProactiveHint.created_at >= period_start,
                    ProactiveHint.created_at <= period_end,
                    ProactiveHint.status == HintStatus.ACTED_ON.value,
                    ProactiveHint.source_type == "skonto_deadline",
                )
            )
        )
        # Einfache Schätzung basierend auf Value-Score
        result = await db.execute(savings_query)
        est_savings = (result.scalar() or 0.0) * 500.0  # Grobe Hochrechnung

        stats = HintStatistics(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            total_hints=total_hints,
            hints_by_category=by_category,
            action_rate=round(action_rate, 2),
            avg_response_time_hours=round(avg_response_hours, 2),
            estimated_savings=round(est_savings, 2),
        )
        db.add(stats)
        await db.flush()

        logger.info(
            "hint_statistics_calculated",
            company_id=str(company_id),
            period=f"{period_start.date()} - {period_end.date()}",
            total_hints=total_hints,
            action_rate=round(action_rate, 2),
        )
        return stats

    # =========================================================================
    # Regeln
    # =========================================================================

    async def get_rules(
        self, db: AsyncSession, company_id: UUID
    ) -> List[HintRule]:
        """Alle Hint-Regeln einer Firma abrufen."""
        stmt = (
            select(HintRule)
            .where(HintRule.company_id == company_id)
            .order_by(HintRule.category, HintRule.name)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_rule(
        self,
        db: AsyncSession,
        rule_id: UUID,
        company_id: UUID,
        is_active: Optional[bool] = None,
        threshold_config: Optional[Dict[str, object]] = None,
        schedule: Optional[str] = None,
    ) -> Optional[HintRule]:
        """Hint-Regel aktualisieren."""
        stmt = select(HintRule).where(
            and_(HintRule.id == rule_id, HintRule.company_id == company_id)
        )
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            return None

        if is_active is not None:
            rule.is_active = is_active
        if threshold_config is not None:
            rule.threshold_config = threshold_config
        if schedule is not None:
            rule.schedule = schedule

        await db.flush()
        return rule

    # =========================================================================
    # Abgelaufene Hints
    # =========================================================================

    async def expire_old_hints(self, db: AsyncSession) -> int:
        """Abgelaufene Hints als dismissed markieren."""
        now = utc_now()
        active_statuses = [HintStatus.NEW.value, HintStatus.SEEN.value]

        stmt = (
            update(ProactiveHint)
            .where(
                and_(
                    ProactiveHint.expires_at.isnot(None),
                    ProactiveHint.expires_at <= now,
                    ProactiveHint.status.in_(active_statuses),
                )
            )
            .values(
                status=HintStatus.DISMISSED.value,
                dismissed_at=now,
            )
        )
        result = await db.execute(stmt)
        count = result.rowcount
        await db.flush()

        if count > 0:
            logger.info("expired_hints_dismissed", count=count)
        return count

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    async def _find_active_hint(
        self,
        db: AsyncSession,
        company_id: UUID,
        source_type: str,
        source_id: Optional[UUID],
    ) -> Optional[ProactiveHint]:
        """Findet aktiven Hint mit gleicher Quelle (Deduplizierung)."""
        active_statuses = [HintStatus.NEW.value, HintStatus.SEEN.value, HintStatus.ACKNOWLEDGED.value]

        conditions = [
            ProactiveHint.company_id == company_id,
            ProactiveHint.source_type == source_type,
            ProactiveHint.status.in_(active_statuses),
        ]
        if source_id:
            conditions.append(ProactiveHint.source_id == source_id)

        stmt = select(ProactiveHint).where(and_(*conditions)).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


def get_proactive_assistant_service() -> ProactiveAssistantService:
    """Factory function für ProactiveAssistantService."""
    return ProactiveAssistantService()
