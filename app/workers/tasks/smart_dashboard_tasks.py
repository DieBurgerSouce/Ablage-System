# -*- coding: utf-8 -*-
"""
Celery Tasks fuer Smart Dashboard.

Periodische Tasks fuer:
- KPI-Aktualisierung (alle 30 Sekunden)
- Taegliche Trend-Berechnung
- Bereinigung alter Progress-Tracker

Feinpoliert und durchdacht - Enterprise Dashboard Background Tasks.
"""

from typing import Optional

import structlog
from celery import shared_task

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@shared_task(
    name="smart_dashboard.refresh_kpis",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    soft_time_limit=25,
    time_limit=30,
)
def refresh_kpis_task(self) -> dict:
    """KPIs fuer alle Firmen aktualisieren.

    Laeuft alle 30 Sekunden und berechnet aktuelle KPI-Werte
    aus den Datenbank-Tabellen.

    Returns:
        Dictionary mit Ergebnissen der Aktualisierung
    """
    import asyncio
    from app.api.dependencies import AsyncSessionLocal

    async def _refresh() -> dict:
        from sqlalchemy import select, and_, text
        from app.db.models_smart_dashboard import DashboardKPI

        async with AsyncSessionLocal() as db:
            try:
                now = utc_now()

                # Alle aktiven Firmen-IDs ermitteln
                company_stmt = text(
                    "SELECT DISTINCT id FROM companies WHERE is_active = true"
                )
                result = await db.execute(company_stmt)
                company_ids = [row[0] for row in result.all()]

                updated_count = 0

                for company_id in company_ids:
                    kpis = await _calculate_company_kpis(db, company_id, now)

                    for kpi_key, kpi_data in kpis.items():
                        # Existierenden KPI-Eintrag suchen
                        existing_stmt = select(DashboardKPI).where(
                            and_(
                                DashboardKPI.company_id == company_id,
                                DashboardKPI.kpi_key == kpi_key,
                            )
                        ).order_by(DashboardKPI.calculated_at.desc()).limit(1)

                        existing_result = await db.execute(existing_stmt)
                        existing = existing_result.scalar_one_or_none()

                        previous_value = existing.current_value if existing else None

                        # Neuen KPI-Eintrag erstellen
                        new_kpi = DashboardKPI(
                            company_id=company_id,
                            kpi_key=kpi_key,
                            current_value=kpi_data["value"],
                            previous_value=previous_value,
                            unit=kpi_data["unit"],
                            trend_direction=_calc_trend(
                                kpi_data["value"], previous_value,
                            ),
                            calculated_at=now,
                            kpi_metadata=kpi_data.get("metadata", {}),
                        )
                        db.add(new_kpi)
                        updated_count += 1

                await db.commit()

                logger.info(
                    "smart_dashboard.kpis_refreshed",
                    company_count=len(company_ids),
                    kpi_count=updated_count,
                )

                return {
                    "status": "success",
                    "companies": len(company_ids),
                    "kpis_updated": updated_count,
                    "timestamp": now.isoformat(),
                }

            except Exception as e:
                await db.rollback()
                logger.error(
                    "smart_dashboard.kpi_refresh_failed",
                    **safe_error_log(e),
                )
                raise

    try:
        result = asyncio.run(_refresh())
        return result
    except Exception as exc:
        logger.error("smart_dashboard.refresh_kpis_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="smart_dashboard.calculate_daily_trends",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def calculate_daily_trends_task(self) -> dict:
    """Taegliche KPI-Trend-Berechnung.

    Laeuft einmal taeglich und berechnet KPI-Trends
    im Vergleich zur Vorperiode.

    Returns:
        Dictionary mit Trend-Ergebnissen
    """
    import asyncio
    from app.api.dependencies import AsyncSessionLocal

    async def _calculate_trends() -> dict:
        from app.services.smart_dashboard_service import SmartDashboardService
        from sqlalchemy import text

        service = SmartDashboardService()

        async with AsyncSessionLocal() as db:
            try:
                # Alle aktiven Firmen
                company_stmt = text(
                    "SELECT DISTINCT id FROM companies WHERE is_active = true"
                )
                result = await db.execute(company_stmt)
                company_ids = [row[0] for row in result.all()]

                trend_count = 0

                for company_id in company_ids:
                    trends = await service.calculate_kpi_trends(db, company_id)
                    trend_count += len(trends)

                await db.commit()

                logger.info(
                    "smart_dashboard.daily_trends_calculated",
                    company_count=len(company_ids),
                    trend_count=trend_count,
                )

                return {
                    "status": "success",
                    "companies": len(company_ids),
                    "trends_calculated": trend_count,
                }

            except Exception as e:
                await db.rollback()
                logger.error(
                    "smart_dashboard.daily_trends_failed",
                    **safe_error_log(e),
                )
                raise

    try:
        result = asyncio.run(_calculate_trends())
        return result
    except Exception as exc:
        logger.error("smart_dashboard.daily_trends_task_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="smart_dashboard.cleanup_completed_trackers",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=60,
    time_limit=120,
)
def cleanup_completed_trackers_task(self, older_than_days: int = 7) -> dict:
    """Alte abgeschlossene Progress-Tracker bereinigen.

    Laeuft taeglich und entfernt Tracker fuer Dokumente
    die vor mehr als X Tagen fertig verarbeitet wurden.

    Args:
        older_than_days: Alter in Tagen (Standard: 7)

    Returns:
        Dictionary mit Bereinigungs-Ergebnissen
    """
    import asyncio
    from app.api.dependencies import AsyncSessionLocal

    async def _cleanup() -> dict:
        from app.services.document_progress_service import DocumentProgressService

        service = DocumentProgressService()

        async with AsyncSessionLocal() as db:
            try:
                deleted = await service.cleanup_completed_trackers(
                    db, older_than_days=older_than_days,
                )
                await db.commit()

                logger.info(
                    "smart_dashboard.trackers_cleaned",
                    deleted_count=deleted,
                    older_than_days=older_than_days,
                )

                return {
                    "status": "success",
                    "deleted_count": deleted,
                    "older_than_days": older_than_days,
                }

            except Exception as e:
                await db.rollback()
                logger.error(
                    "smart_dashboard.cleanup_failed",
                    **safe_error_log(e),
                )
                raise

    try:
        result = asyncio.run(_cleanup())
        return result
    except Exception as exc:
        logger.error("smart_dashboard.cleanup_task_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


# =============================================================================
# Hilfsfunktionen
# =============================================================================

async def _calculate_company_kpis(
    db: "AsyncSession",
    company_id: "UUID",
    now: "datetime",
) -> dict:
    """KPIs fuer eine einzelne Firma berechnen.

    Args:
        db: Async Datenbank-Session
        company_id: Firmen-ID
        now: Aktueller Zeitstempel

    Returns:
        Dictionary mit KPI-Key -> {value, unit, metadata}
    """
    from sqlalchemy import text

    kpis: dict = {}
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Offene Rechnungen zaehlen
    try:
        inv_count_result = await db.execute(text(
            "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) "
            "FROM invoices "
            "WHERE company_id = :cid AND status IN ('open', 'partial') "
            "AND deleted_at IS NULL"
        ), {"cid": company_id})
        row = inv_count_result.fetchone()
        if row:
            kpis["open_invoices_total"] = {"value": float(row[0]), "unit": "count"}
            kpis["open_invoices_amount"] = {"value": float(row[1]), "unit": "EUR"}
    except Exception:
        kpis["open_invoices_total"] = {"value": 0.0, "unit": "count"}
        kpis["open_invoices_amount"] = {"value": 0.0, "unit": "EUR"}

    # Ueberfaellige Rechnungen
    try:
        overdue_result = await db.execute(text(
            "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) "
            "FROM invoices "
            "WHERE company_id = :cid AND status = 'overdue' "
            "AND deleted_at IS NULL"
        ), {"cid": company_id})
        row = overdue_result.fetchone()
        if row:
            kpis["overdue_invoices_count"] = {"value": float(row[0]), "unit": "count"}
            kpis["overdue_invoices_amount"] = {"value": float(row[1]), "unit": "EUR"}
    except Exception:
        kpis["overdue_invoices_count"] = {"value": 0.0, "unit": "count"}
        kpis["overdue_invoices_amount"] = {"value": 0.0, "unit": "EUR"}

    # Dokumente heute
    try:
        docs_today_result = await db.execute(text(
            "SELECT COUNT(*) FROM documents "
            "WHERE company_id = :cid AND created_at >= :today "
            "AND deleted_at IS NULL"
        ), {"cid": company_id, "today": today_start})
        row = docs_today_result.fetchone()
        kpis["documents_today"] = {
            "value": float(row[0]) if row else 0.0,
            "unit": "count",
        }
    except Exception:
        kpis["documents_today"] = {"value": 0.0, "unit": "count"}

    # OCR-Warteschlange
    try:
        queue_result = await db.execute(text(
            "SELECT COUNT(*) FROM document_progress_trackers "
            "WHERE company_id = :cid "
            "AND current_step IN ('ocr_warteschlange', 'ocr_laeuft')"
        ), {"cid": company_id})
        row = queue_result.fetchone()
        kpis["ocr_queue_length"] = {
            "value": float(row[0]) if row else 0.0,
            "unit": "count",
        }
    except Exception:
        kpis["ocr_queue_length"] = {"value": 0.0, "unit": "count"}

    # Aktive Alerts
    try:
        alerts_result = await db.execute(text(
            "SELECT COUNT(*) FROM alerts "
            "WHERE company_id = :cid AND status IN ('new', 'acknowledged')"
        ), {"cid": company_id})
        row = alerts_result.fetchone()
        kpis["active_alerts"] = {
            "value": float(row[0]) if row else 0.0,
            "unit": "count",
        }
    except Exception:
        kpis["active_alerts"] = {"value": 0.0, "unit": "count"}

    return kpis


def _calc_trend(current: float, previous: Optional[float]) -> str:
    """Trend-Richtung berechnen.

    Args:
        current: Aktueller Wert
        previous: Vorheriger Wert

    Returns:
        Trend-Richtung: "up", "down" oder "stable"
    """
    if previous is None or previous == 0:
        return "stable"
    change_pct = ((current - previous) / abs(previous)) * 100
    if change_pct > 1.0:
        return "up"
    elif change_pct < -1.0:
        return "down"
    return "stable"
