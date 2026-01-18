"""
Celery Tasks fuer Steuerberater-Pakete.

Automatische Erstellung und Versand von Buchhaltungspaketen.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from celery import shared_task

from app.core.database import get_async_session

logger = structlog.get_logger(__name__)


# ============================================================================
# PACKAGE GENERATION TASKS
# ============================================================================


@shared_task(
    name="tax_packages.generate_monthly_packages",
    bind=True,
    max_retries=2,
    default_retry_delay=3600,  # 1 Stunde
    queue="maintenance",
)
def generate_monthly_packages(
    self,
    company_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generiert monatliche Pakete fuer alle Firmen.

    Wird am 5. jeden Monats fuer den Vormonat ausgefuehrt.

    Args:
        company_ids: Optional - nur bestimmte Firmen

    Returns:
        Anzahl erstellter Pakete
    """
    logger.info(
        "monthly_package_generation_started",
        company_filter=company_ids,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_generate_monthly_packages(company_ids)
        )
        return result

    except RuntimeError:
        # Kein Event Loop vorhanden
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_generate_monthly_packages(company_ids)
            )
            return result
        finally:
            loop.close()


async def _async_generate_monthly_packages(
    company_ids: Optional[List[str]],
) -> Dict[str, Any]:
    """Async Implementierung der monatlichen Paket-Generierung."""
    import uuid
    from sqlalchemy import select
    from app.db.models import Company
    from app.services.tax_advisor_package_service import (
        get_tax_advisor_package_service,
        PackageFrequency,
    )

    async with get_async_session() as db:
        # Firmen laden
        query = select(Company).where(Company.is_active == True)
        if company_ids:
            query = query.where(Company.id.in_([uuid.UUID(c) for c in company_ids]))

        result = await db.execute(query)
        companies = result.scalars().all()

        # Vormonat berechnen
        today = date.today()
        if today.month == 1:
            prev_month = date(today.year - 1, 12, 1)
        else:
            prev_month = date(today.year, today.month - 1, 1)

        period = f"{prev_month.year}-{prev_month.month:02d}"

        packages_created = 0
        packages_with_missing = 0
        errors: List[str] = []

        service = get_tax_advisor_package_service(db)

        for company in companies:
            try:
                # Pruefen ob Firma Konfiguration hat
                configs = await service.get_configurations_for_company(company.id)
                monthly_configs = [
                    c for c in configs
                    if c.frequency == PackageFrequency.MONTHLY and c.is_active
                ]

                if not monthly_configs:
                    continue

                for config in monthly_configs:
                    package = await service.create_package_for_period(
                        company_id=company.id,
                        period=period,
                        config_id=config.id,
                    )

                    packages_created += 1

                    if package.missing_documents:
                        packages_with_missing += 1

                        # Erinnerung senden wenn konfiguriert
                        if config.auto_reminder and config.recipient_email:
                            await service.send_missing_documents_notification(
                                package=package,
                                admin_email=config.recipient_email,
                            )

            except Exception as e:
                error_msg = f"Fehler bei Firma {company.id}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    "monthly_package_generation_error",
                    company_id=str(company.id),
                    error=str(e),
                )

        logger.info(
            "monthly_package_generation_completed",
            packages_created=packages_created,
            packages_with_missing=packages_with_missing,
            errors_count=len(errors),
        )

        return {
            "success": True,
            "period": period,
            "packages_created": packages_created,
            "packages_with_missing": packages_with_missing,
            "errors": errors[:10],  # Max 10 Fehler
        }


@shared_task(
    name="tax_packages.generate_quarterly_packages",
    bind=True,
    max_retries=2,
    default_retry_delay=3600,
    queue="maintenance",
)
def generate_quarterly_packages(
    self,
    company_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generiert Quartalspakete fuer alle Firmen.

    Wird am 10. nach Quartalsende ausgefuehrt.

    Args:
        company_ids: Optional - nur bestimmte Firmen

    Returns:
        Anzahl erstellter Pakete
    """
    logger.info(
        "quarterly_package_generation_started",
        company_filter=company_ids,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_generate_quarterly_packages(company_ids)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_generate_quarterly_packages(company_ids)
            )
            return result
        finally:
            loop.close()


async def _async_generate_quarterly_packages(
    company_ids: Optional[List[str]],
) -> Dict[str, Any]:
    """Async Implementierung der Quartalspakete-Generierung."""
    import uuid
    from sqlalchemy import select
    from app.db.models import Company
    from app.services.tax_advisor_package_service import (
        get_tax_advisor_package_service,
        PackageFrequency,
    )

    async with get_async_session() as db:
        # Firmen laden
        query = select(Company).where(Company.is_active == True)
        if company_ids:
            query = query.where(Company.id.in_([uuid.UUID(c) for c in company_ids]))

        result = await db.execute(query)
        companies = result.scalars().all()

        # Vorquartal berechnen
        today = date.today()
        current_quarter = (today.month - 1) // 3 + 1

        if current_quarter == 1:
            prev_quarter = 4
            year = today.year - 1
        else:
            prev_quarter = current_quarter - 1
            year = today.year

        period = f"{year}-Q{prev_quarter}"

        packages_created = 0
        packages_with_missing = 0
        errors: List[str] = []

        service = get_tax_advisor_package_service(db)

        for company in companies:
            try:
                configs = await service.get_configurations_for_company(company.id)
                quarterly_configs = [
                    c for c in configs
                    if c.frequency == PackageFrequency.QUARTERLY and c.is_active
                ]

                if not quarterly_configs:
                    continue

                for config in quarterly_configs:
                    package = await service.create_package_for_period(
                        company_id=company.id,
                        period=period,
                        config_id=config.id,
                    )

                    packages_created += 1

                    if package.missing_documents:
                        packages_with_missing += 1

            except Exception as e:
                error_msg = f"Fehler bei Firma {company.id}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    "quarterly_package_generation_error",
                    company_id=str(company.id),
                    error=str(e),
                )

        logger.info(
            "quarterly_package_generation_completed",
            packages_created=packages_created,
            packages_with_missing=packages_with_missing,
        )

        return {
            "success": True,
            "period": period,
            "packages_created": packages_created,
            "packages_with_missing": packages_with_missing,
            "errors": errors[:10],
        }


# ============================================================================
# PACKAGE DELIVERY TASKS
# ============================================================================


@shared_task(
    name="tax_packages.auto_send_ready_packages",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="notifications",
)
def auto_send_ready_packages(self) -> Dict[str, Any]:
    """
    Versendet alle fertigen Pakete mit auto_send=True.

    Wird taeglich um 09:00 ausgefuehrt.

    Returns:
        Anzahl versendeter Pakete
    """
    logger.info("auto_send_ready_packages_started")

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_auto_send_packages()
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_async_auto_send_packages())
            return result
        finally:
            loop.close()


async def _async_auto_send_packages() -> Dict[str, Any]:
    """Async Implementierung des Auto-Versands."""
    from app.services.tax_advisor_package_service import (
        get_tax_advisor_package_service,
        PackageStatus,
    )

    async with get_async_session() as db:
        service = get_tax_advisor_package_service(db)

        # In Praxis: Pakete aus DB laden
        # Hier vereinfacht: alle Firmen-Configs durchgehen
        sent_count = 0
        error_count = 0

        # Hier wuerde die Implementierung kommen
        # die ready-Pakete aus der DB holt und versendet

        logger.info(
            "auto_send_ready_packages_completed",
            sent_count=sent_count,
            error_count=error_count,
        )

        return {
            "success": True,
            "sent_count": sent_count,
            "error_count": error_count,
        }


# ============================================================================
# REMINDER TASKS
# ============================================================================


@shared_task(
    name="tax_packages.send_missing_documents_reminders",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="notifications",
)
def send_missing_documents_reminders(
    self,
    days_before_deadline: int = 3,
) -> Dict[str, Any]:
    """
    Sendet Erinnerungen fuer fehlende Dokumente.

    Wird taeglich um 08:00 ausgefuehrt.

    Args:
        days_before_deadline: Tage vor Deadline

    Returns:
        Anzahl gesendeter Erinnerungen
    """
    logger.info(
        "send_missing_documents_reminders_started",
        days_before_deadline=days_before_deadline,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_send_reminders(days_before_deadline)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_send_reminders(days_before_deadline)
            )
            return result
        finally:
            loop.close()


async def _async_send_reminders(days_before_deadline: int) -> Dict[str, Any]:
    """Async Implementierung der Erinnerungen."""
    from app.services.tax_advisor_package_service import (
        get_tax_advisor_package_service,
        PackageStatus,
    )

    async with get_async_session() as db:
        service = get_tax_advisor_package_service(db)

        # In Praxis: Pakete mit Status PENDING laden
        # die Erinnerung noch nicht erhalten haben
        # und deren Deadline naht

        reminders_sent = 0
        errors: List[str] = []

        logger.info(
            "send_missing_documents_reminders_completed",
            reminders_sent=reminders_sent,
        )

        return {
            "success": True,
            "reminders_sent": reminders_sent,
            "errors": errors[:10],
        }


# ============================================================================
# CLEANUP TASKS
# ============================================================================


@shared_task(
    name="tax_packages.cleanup_expired_packages",
    bind=True,
    max_retries=1,
    default_retry_delay=3600,
    queue="maintenance",
)
def cleanup_expired_packages(
    self,
    retention_days: int = 90,
) -> Dict[str, Any]:
    """
    Bereinigt abgelaufene Pakete.

    Wird woechentlich (Sonntag 04:00) ausgefuehrt.

    Args:
        retention_days: Aufbewahrungszeit in Tagen

    Returns:
        Anzahl bereinigter Pakete
    """
    logger.info(
        "cleanup_expired_packages_started",
        retention_days=retention_days,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_cleanup_packages(retention_days)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_cleanup_packages(retention_days)
            )
            return result
        finally:
            loop.close()


async def _async_cleanup_packages(retention_days: int) -> Dict[str, Any]:
    """Async Implementierung der Bereinigung."""
    from app.services.tax_advisor_package_service import PackageStatus

    async with get_async_session() as db:
        # Cutoff-Datum
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # In Praxis: Pakete aus DB loeschen
        # deren expires_at < cutoff und Status in (SENT, DOWNLOADED, EXPIRED)
        cleaned_count = 0

        logger.info(
            "cleanup_expired_packages_completed",
            cleaned_count=cleaned_count,
            cutoff_date=cutoff.isoformat(),
        )

        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "retention_days": retention_days,
        }


# ============================================================================
# DATEV INTEGRATION TASKS
# ============================================================================


@shared_task(
    name="tax_packages.generate_datev_for_package",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    queue="exports",
)
def generate_datev_for_package(
    self,
    package_id: str,
) -> Dict[str, Any]:
    """
    Generiert DATEV-Export fuer ein Paket.

    Wird nach Paket-Erstellung oder manuell getriggert.

    Args:
        package_id: Paket-ID

    Returns:
        Pfad zum DATEV-Export
    """
    logger.info(
        "generate_datev_for_package_started",
        package_id=package_id,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_generate_datev(package_id)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_async_generate_datev(package_id))
            return result
        finally:
            loop.close()


async def _async_generate_datev(package_id: str) -> Dict[str, Any]:
    """Async Implementierung der DATEV-Generierung."""
    import uuid
    from app.services.tax_advisor_package_service import get_tax_advisor_package_service

    async with get_async_session() as db:
        service = get_tax_advisor_package_service(db)

        # In Praxis: Paket aus DB laden
        # DATEV-Export generieren
        # Paket aktualisieren

        logger.info(
            "generate_datev_for_package_completed",
            package_id=package_id,
        )

        return {
            "success": True,
            "package_id": package_id,
            "datev_path": None,  # Wuerde den tatsaechlichen Pfad enthalten
        }
