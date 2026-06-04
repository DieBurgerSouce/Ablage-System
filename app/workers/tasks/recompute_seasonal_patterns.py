"""Woechentlicher Celery Beat Task fuer Seasonal Pattern Recomputation.

Berechnet saisonale Zahlungsmuster fuer alle aktiven Entities
und persistiert sie in der entity_seasonal_patterns Tabelle.
"""

import asyncio
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import structlog

from app.workers.celery_app import celery_app
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="recompute_seasonal_patterns",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="low_priority",
)
def recompute_seasonal_patterns(
    self: "celery_app.Task",  # type: ignore[name-defined]
) -> Dict[str, int]:
    """Berechnet saisonale Zahlungsmuster fuer alle aktiven Entities.

    Laeuft woechentlich via Celery Beat (Sonntag 03:00 Uhr).
    Analysiert historische Zahlungsdaten und persistiert erkannte Muster.

    Returns:
        Dict mit entities_processed und patterns_updated Zaehler.
    """
    return asyncio.run(_run_seasonal_recomputation())


async def _run_seasonal_recomputation() -> Dict[str, int]:
    """Asynchrone Hauptlogik fuer Seasonal Pattern Recomputation."""
    from sqlalchemy import select, and_

    from app.db.models import InvoiceTracking, Document
    from app.db.session import async_session_factory

    entities_processed = 0
    patterns_updated = 0

    async with async_session_factory() as db:
        # Hole alle einzigartigen (entity_id, company_id) Kombinationen
        # die genug Zahlungsdaten haben
        entity_company_stmt = (
            select(
                Document.business_entity_id,
                InvoiceTracking.company_id,
            )
            .join(
                Document,
                Document.id == InvoiceTracking.document_id,
            )
            .where(
                and_(
                    Document.business_entity_id.isnot(None),
                    InvoiceTracking.company_id.isnot(None),
                    InvoiceTracking.paid_at.isnot(None),
                    InvoiceTracking.due_date.isnot(None),
                )
            )
            .group_by(
                Document.business_entity_id,
                InvoiceTracking.company_id,
            )
            .limit(2000)
        )

        result = await db.execute(entity_company_stmt)
        entity_company_pairs: List[Tuple[object, object]] = result.fetchall()

        for entity_id, company_id in entity_company_pairs:
            if entity_id is None or company_id is None:
                continue
            try:
                updated = await _compute_entity_patterns(
                    db, entity_id, company_id
                )
                entities_processed += 1
                if updated:
                    patterns_updated += 1
            except Exception as e:
                logger.warning(
                    "seasonal_pattern_computation_failed",
                    entity_id=str(entity_id),
                    error_type=type(e).__name__,
                )

        await db.commit()

    logger.info(
        "seasonal_patterns_recomputed",
        entities_processed=entities_processed,
        patterns_updated=patterns_updated,
    )
    return {
        "entities_processed": entities_processed,
        "patterns_updated": patterns_updated,
    }


async def _compute_entity_patterns(
    db: "AsyncSession",  # type: ignore[name-defined]
    entity_id: object,
    company_id: object,
) -> bool:
    """Berechnet und persistiert saisonale Muster fuer eine Entity.

    Args:
        db: Async DB Session.
        entity_id: UUID der Business Entity.
        company_id: UUID der Company.

    Returns:
        True wenn ein Pattern erstellt oder aktualisiert wurde.
    """
    from sqlalchemy import select, func, and_, extract
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import InvoiceTracking, Document
    from app.db.models_predictions import EntitySeasonalPattern

    # Analysiere Zahlungsverzoegerungen nach Monat
    stmt = (
        select(
            extract("month", InvoiceTracking.paid_at).label("pay_month"),
            func.avg(
                extract(
                    "epoch",
                    InvoiceTracking.paid_at - InvoiceTracking.due_date,
                ) / 86400
            ).label("avg_delay"),
            func.count().label("sample_count"),
        )
        .join(
            Document,
            Document.id == InvoiceTracking.document_id,
        )
        .where(
            and_(
                Document.business_entity_id == entity_id,
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.paid_at.isnot(None),
                InvoiceTracking.due_date.isnot(None),
            )
        )
        .group_by(extract("month", InvoiceTracking.paid_at))
    )

    result = await db.execute(stmt)
    monthly_data = result.fetchall()

    if len(monthly_data) < 3:
        return False  # Nicht genug Daten fuer saisonale Analyse

    # Berechne Gesamtdurchschnitt
    total_avg = sum(
        float(row.avg_delay) for row in monthly_data
    ) / len(monthly_data)
    if total_avg == 0:
        return False

    # Finde Monate mit signifikanter Abweichung (>10%)
    affected_months: List[int] = []
    for row in monthly_data:
        if int(row.sample_count) >= 3:  # Mindestens 3 Datenpunkte
            ratio = float(row.avg_delay) / total_avg if total_avg else 1.0
            if abs(ratio - 1.0) > 0.1:
                affected_months.append(int(row.pay_month))

    if not affected_months:
        return False

    # Bestimme Pattern-Type
    winter_months = {11, 12, 1, 2}
    summer_months = {6, 7, 8}
    affected_set = set(affected_months)

    if affected_set & winter_months:
        pattern_type = "holiday_slowdown"
    elif affected_set & summer_months:
        pattern_type = "summer_slowdown"
    else:
        pattern_type = "periodic_variation"

    avg_adjustment = sum(
        float(row.avg_delay) / total_avg
        for row in monthly_data
        if int(row.pay_month) in affected_set
    ) / len(affected_months)

    total_samples = sum(
        int(row.sample_count)
        for row in monthly_data
        if int(row.pay_month) in affected_set
    )
    confidence = min(1.0, total_samples / 30)  # Volle Konfidenz ab 30 Samples

    # Upsert Pattern
    existing_stmt = select(EntitySeasonalPattern).where(
        and_(
            EntitySeasonalPattern.entity_id == entity_id,
            EntitySeasonalPattern.company_id == company_id,
            EntitySeasonalPattern.pattern_type == pattern_type,
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing: Optional[EntitySeasonalPattern] = (
        existing_result.scalar_one_or_none()
    )

    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.affected_months = affected_months
        existing.avg_delay_adjustment = avg_adjustment
        existing.confidence = confidence
        existing.sample_count = total_samples
        existing.last_computed_at = now
    else:
        pattern = EntitySeasonalPattern(
            id=uuid_mod.uuid4(),
            entity_id=entity_id,
            company_id=company_id,
            pattern_type=pattern_type,
            affected_months=affected_months,
            avg_delay_adjustment=avg_adjustment,
            confidence=confidence,
            sample_count=total_samples,
            last_computed_at=now,
        )
        db.add(pattern)

    return True
