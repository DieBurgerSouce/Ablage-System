# -*- coding: utf-8 -*-
"""
Contract Service V2 Celery Tasks.

Automatische Vertragsmanagement-Tasks mit V2-Features:
- Datumsertraktion aus OCR-Dokumenten
- Deadline-Pruefung und Erinnerungen
- iCal-Export-Generierung
- Vertragsstatistik-Aktualisierung

Feinpoliert und durchdacht - Enterprise Contract Management V2.
"""

import asyncio
import structlog
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Company, Document
from app.db.models_contract import Contract, ContractDeadline, ContractStatus
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# OCR Date Extraction Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.extract_contract_dates_v2_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def extract_contract_dates_v2_task(
    self,
    document_id: str,
    company_id: str,
    contract_id: Optional[str] = None,
    create_contract: bool = False,
) -> Dict[str, Any]:
    """
    Extrahiert Vertragsdaten aus OCR-Text eines Dokuments (V2).

    Wird nach OCR-Abschluss fuer Vertragsdokumente aufgerufen.
    Erweiterte Erkennung mit:
    - Deutsche Datumsformate
    - Kuendigungsfristen
    - Automatische Verlaengerung
    - Laufzeit-Berechnung

    Args:
        document_id: ID des Dokuments
        company_id: Firmen-ID
        contract_id: Optional - Vertrag zum Aktualisieren
        create_contract: Neuen Vertrag erstellen wenn kein contract_id

    Returns:
        Dict mit extrahierten Daten
    """
    from app.services.contract_service_v2 import get_contract_service_v2

    async def _extract_dates() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_service_v2(db)

            # Daten extrahieren
            extracted = await service.extract_dates_from_document(
                document_id=UUID(document_id),
                company_id=UUID(company_id),
            )

            if not extracted:
                return {
                    "document_id": document_id,
                    "success": False,
                    "error": "Dokument nicht gefunden oder kein OCR-Text",
                }

            result = {
                "document_id": document_id,
                "success": True,
                "extracted_dates": {
                    "effective_date": extracted.effective_date.isoformat() if extracted.effective_date else None,
                    "expiration_date": extracted.expiration_date.isoformat() if extracted.expiration_date else None,
                    "notice_period_days": extracted.notice_period_days,
                    "notice_deadline": extracted.notice_deadline.isoformat() if extracted.notice_deadline else None,
                    "auto_renewal": extracted.auto_renewal,
                    "renewal_period_months": extracted.renewal_period_months,
                    "duration_months": extracted.duration_months,
                },
                "confidence": extracted.confidence,
                "extraction_notes": extracted.extraction_notes,
                "all_dates_found": [d.isoformat() for d in extracted.all_dates_found],
                "contract_updated": False,
                "contract_created": False,
            }

            # Bestehenden Vertrag aktualisieren
            if contract_id:
                contract = await service.get_contract(
                    contract_id=UUID(contract_id),
                    company_id=UUID(company_id),
                )
                if contract:
                    updates = {}
                    if extracted.effective_date:
                        updates["effective_date"] = extracted.effective_date
                    if extracted.expiration_date:
                        updates["expiration_date"] = extracted.expiration_date
                    if extracted.notice_period_days:
                        updates["notice_period_days"] = extracted.notice_period_days
                    if extracted.auto_renewal:
                        updates["auto_renewal"] = extracted.auto_renewal
                    if extracted.renewal_period_months:
                        updates["renewal_period_months"] = extracted.renewal_period_months

                    if updates:
                        await service.update_contract(
                            contract_id=UUID(contract_id),
                            company_id=UUID(company_id),
                            **updates,
                        )
                        result["contract_updated"] = True
                        result["contract_id"] = contract_id

            # Neuen Vertrag erstellen
            elif create_contract and extracted.confidence >= 0.5:
                # Dokumenttitel als Vertragstitel
                doc_result = await db.execute(
                    select(Document).where(Document.id == UUID(document_id))
                )
                document = doc_result.scalar_one_or_none()
                title = document.filename if document else "Automatisch erkannter Vertrag"

                contract = await service.create_contract(
                    company_id=UUID(company_id),
                    title=title,
                    document_id=UUID(document_id),
                    effective_date=extracted.effective_date,
                    expiration_date=extracted.expiration_date,
                    notice_period_days=extracted.notice_period_days,
                    auto_renewal=extracted.auto_renewal,
                    renewal_period_months=extracted.renewal_period_months,
                    extract_from_document=False,  # Bereits extrahiert
                )

                result["contract_created"] = True
                result["contract_id"] = str(contract.id)

            return result

    try:
        result = asyncio.run(_extract_dates())
        logger.info(
            "contract_dates_v2_extracted",
            document_id=document_id,
            success=result["success"],
            confidence=result.get("confidence", 0),
            contract_updated=result.get("contract_updated"),
            contract_created=result.get("contract_created"),
        )
        return result
    except Exception as e:
        logger.error(
            "contract_dates_v2_extraction_failed",
            document_id=document_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Deadline Check Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.check_upcoming_deadlines_v2_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_upcoming_deadlines_v2_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 90,
) -> Dict[str, Any]:
    """
    Prueft auf bevorstehende Vertragsfristen (V2).

    Wird taeglich um 08:00 Uhr automatisch ausgefuehrt.
    Erstellt Benachrichtigungen basierend auf reminder_days_before.

    Args:
        company_id: Optional - nur fuer spezifische Firma
        days_ahead: Vorausschau in Tagen

    Returns:
        Dict mit Statistiken
    """
    from app.services.contract_service_v2 import get_contract_service_v2
    from app.services.notification_service import get_notification_service, NotificationPriority

    async def _check_deadlines() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "companies_checked": 0,
                "deadlines_found": 0,
                "notifications_sent": 0,
                "by_type": {},
                "by_priority": {},
                "errors": [],
            }

            notification_service = get_notification_service()

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1

                try:
                    service = get_contract_service_v2(db)
                    deadlines = await service.get_upcoming_deadlines(
                        company_id=company.id,
                        days_ahead=days_ahead,
                    )

                    today = date.today()

                    for deadline in deadlines:
                        stats["deadlines_found"] += 1

                        # Typ zaehlen
                        deadline_type = deadline.deadline_type
                        stats["by_type"][deadline_type] = stats["by_type"].get(deadline_type, 0) + 1

                        # Prioritaet zaehlen
                        priority = deadline.priority
                        stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

                        # Pruefen ob heute Reminder faellig ist
                        days_until = (deadline.deadline_date - today).days
                        reminder_days = deadline.reminder_days_before or [30, 14, 7, 1]

                        if days_until in reminder_days:
                            # Notification senden
                            try:
                                # Prioritaet basierend auf verbleibenden Tagen
                                if days_until <= 1:
                                    notif_priority = NotificationPriority.CRITICAL
                                elif days_until <= 7:
                                    notif_priority = NotificationPriority.HIGH
                                elif days_until <= 30:
                                    notif_priority = NotificationPriority.NORMAL
                                else:
                                    notif_priority = NotificationPriority.LOW

                                # Vertragstitel holen (SECURITY: kurz halten)
                                contract_title = "Vertrag"
                                if deadline.contract and deadline.contract.title:
                                    contract_title = deadline.contract.title[:30]

                                await notification_service.notify(
                                    notification_type="contract_deadline",
                                    context={
                                        "deadline_title": deadline.title,
                                        "contract_title": contract_title,
                                        "days_until": days_until,
                                        "deadline_date": deadline.deadline_date.strftime("%d.%m.%Y"),
                                        "deadline_id": str(deadline.id),
                                        "contract_id": str(deadline.contract_id),
                                    },
                                    user_id=str(deadline.assignee_id) if deadline.assignee_id else None,
                                    priority=notif_priority.value,
                                )
                                stats["notifications_sent"] += 1

                                # Last reminder update
                                deadline.last_reminder_sent = datetime.now(timezone.utc)

                            except Exception as notif_e:
                                logger.warning(
                                    "deadline_notification_failed",
                                    deadline_id=str(deadline.id),
                                    error_type=type(notif_e).__name__,
                                )

                    await db.commit()

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Deadline-Check"),
                    })
                    logger.warning(
                        "deadline_check_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_check_deadlines())
        logger.info(
            "deadline_check_v2_completed",
            companies_checked=result["companies_checked"],
            deadlines_found=result["deadlines_found"],
            notifications_sent=result["notifications_sent"],
            by_type=result["by_type"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("deadline_check_v2_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# iCal Export Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.generate_ical_export_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="maintenance",
)
def generate_ical_export_task(
    self,
    company_id: str,
    days_ahead: int = 365,
    contract_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generiert iCal-Export fuer Vertragsfristen.

    Kann manuell oder per API getriggert werden.

    Args:
        company_id: Firmen-ID
        days_ahead: Vorausschau in Tagen
        contract_ids: Optional - nur bestimmte Vertraege

    Returns:
        Dict mit iCal-Daten und Statistiken
    """
    from app.services.contract_service_v2 import get_contract_service_v2

    async def _generate_ical() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_service_v2(db)

            contract_uuids = None
            if contract_ids:
                contract_uuids = [UUID(cid) for cid in contract_ids]

            ical_content = await service.export_deadlines_to_ical(
                company_id=UUID(company_id),
                days_ahead=days_ahead,
                contract_ids=contract_uuids,
            )

            # Event-Anzahl zaehlen
            event_count = ical_content.count("BEGIN:VEVENT")

            return {
                "success": True,
                "company_id": company_id,
                "days_ahead": days_ahead,
                "event_count": event_count,
                "ical_content": ical_content,
                "content_length": len(ical_content),
            }

    try:
        result = asyncio.run(_generate_ical())
        logger.info(
            "ical_export_generated",
            company_id=company_id,
            event_count=result["event_count"],
            content_length=result["content_length"],
        )
        return result
    except Exception as e:
        logger.error(
            "ical_export_failed",
            company_id=company_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Statistics Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.update_contract_statistics_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def update_contract_statistics_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aktualisiert Vertragsstatistiken (V2).

    Wird taeglich um 04:00 Uhr automatisch ausgefuehrt.

    Args:
        company_id: Optional - nur fuer spezifische Firma

    Returns:
        Dict mit aggregierten Statistiken
    """
    from app.services.contract_service_v2 import get_contract_service_v2

    async def _update_stats() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            aggregated_stats = {
                "companies_processed": 0,
                "total_contracts": 0,
                "active_contracts": 0,
                "total_value": 0.0,
                "expiring_30_days": 0,
                "expiring_60_days": 0,
                "expiring_90_days": 0,
                "by_company": {},
                "errors": [],
            }

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                try:
                    service = get_contract_service_v2(db)
                    stats = await service.get_contract_statistics(company.id)

                    aggregated_stats["companies_processed"] += 1
                    aggregated_stats["total_contracts"] += stats["total_contracts"]
                    aggregated_stats["active_contracts"] += stats["active_contracts"]
                    aggregated_stats["total_value"] += stats["total_value"]
                    aggregated_stats["expiring_30_days"] += stats["expiring_30_days"]
                    aggregated_stats["expiring_60_days"] += stats["expiring_60_days"]
                    aggregated_stats["expiring_90_days"] += stats["expiring_90_days"]

                    aggregated_stats["by_company"][str(company.id)] = stats

                except Exception as e:
                    aggregated_stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Statistik"),
                    })
                    logger.warning(
                        "contract_stats_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            aggregated_stats["generated_at"] = datetime.now(timezone.utc).isoformat()
            return aggregated_stats

    try:
        result = asyncio.run(_update_stats())
        logger.info(
            "contract_statistics_updated",
            companies=result["companies_processed"],
            total_contracts=result["total_contracts"],
            active_contracts=result["active_contracts"],
            expiring_30d=result["expiring_30_days"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("contract_statistics_update_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Contract Status Update Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.check_expired_contracts_v2_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_expired_contracts_v2_task(self) -> Dict[str, Any]:
    """
    Markiert abgelaufene Vertraege als EXPIRED.

    Wird taeglich um 00:30 Uhr automatisch ausgefuehrt.

    Returns:
        Dict mit Statistiken
    """
    async def _check_expired() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            today = date.today()

            stats = {
                "total_checked": 0,
                "expired": 0,
                "errors": [],
            }

            # Aktive Vertraege mit abgelaufenem Enddatum
            result = await db.execute(
                select(Contract).where(
                    and_(
                        Contract.status == ContractStatus.ACTIVE.value,
                        Contract.expiration_date.isnot(None),
                        Contract.expiration_date < today,
                    )
                )
            )
            contracts = result.scalars().all()

            for contract in contracts:
                stats["total_checked"] += 1
                try:
                    contract.status = ContractStatus.EXPIRED.value
                    contract.updated_at = datetime.now(timezone.utc)
                    stats["expired"] += 1

                    logger.debug(
                        "contract_marked_expired",
                        contract_id=str(contract.id),
                        expiration_date=str(contract.expiration_date),
                    )

                except Exception as e:
                    stats["errors"].append({
                        "contract_id": str(contract.id),
                        "error": safe_error_detail(e, "Status-Update"),
                    })

            await db.commit()
            return stats

    try:
        result = asyncio.run(_check_expired())
        logger.info(
            "expired_contracts_v2_check_completed",
            total_checked=result["total_checked"],
            expired=result["expired"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("expired_contracts_v2_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.complete_contract_deadline_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="metadata",
)
def complete_contract_deadline_task(
    self,
    deadline_id: str,
    company_id: str,
    completed_by_id: Optional[str] = None,
    action_taken: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Markiert eine Vertragsfrist als erledigt.

    Kann von API oder UI getriggert werden.

    Args:
        deadline_id: Deadline-ID
        company_id: Firmen-ID
        completed_by_id: ID des abschliessenden Benutzers
        action_taken: Durchgefuehrte Aktion

    Returns:
        Dict mit Status
    """
    from app.services.contract_service_v2 import get_contract_service_v2

    async def _complete_deadline() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_service_v2(db)

            deadline = await service.complete_deadline(
                deadline_id=UUID(deadline_id),
                company_id=UUID(company_id),
                completed_by_id=UUID(completed_by_id) if completed_by_id else None,
                action_taken=action_taken,
            )

            if deadline:
                return {
                    "success": True,
                    "deadline_id": deadline_id,
                    "contract_id": str(deadline.contract_id),
                    "completed_at": deadline.completed_at.isoformat() if deadline.completed_at else None,
                }
            else:
                return {
                    "success": False,
                    "error": "Deadline nicht gefunden",
                }

    try:
        result = asyncio.run(_complete_deadline())
        if result["success"]:
            logger.info(
                "deadline_completed_v2",
                deadline_id=deadline_id,
                contract_id=result.get("contract_id"),
            )
        return result
    except Exception as e:
        logger.error(
            "deadline_completion_failed",
            deadline_id=deadline_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Document Linking Tasks
# =============================================================================


# =============================================================================
# Auto-Renewal Tasks (Phase 1.3 - Beat Schedule Activated)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.check_auto_renewals_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="metadata",
)
def check_auto_renewals_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 30,
) -> Dict[str, Any]:
    """
    Prueft und fuehrt automatische Vertragsverlaengerungen durch.

    Wird taeglich um 09:15 Uhr automatisch ausgefuehrt.
    Findet Vertraege mit:
    - auto_renewal=True
    - Ablaufdatum innerhalb days_ahead Tagen
    - Kuendigungsfrist nicht verpasst

    Args:
        company_id: Optional - nur fuer spezifische Firma
        days_ahead: Vorausschau in Tagen (default 30)

    Returns:
        Dict mit Renewal-Statistiken
    """
    async def _check_renewals() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "companies_checked": 0,
                "contracts_checked": 0,
                "renewals_triggered": 0,
                "renewals_skipped": 0,
                "notifications_sent": 0,
                "errors": [],
                "renewed_contracts": [],
            }

            today = date.today()
            check_until = today + timedelta(days=days_ahead)

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1

                try:
                    # Vertraege mit auto_renewal finden
                    contracts_query = select(Contract).where(
                        and_(
                            Contract.company_id == company.id,
                            Contract.status == ContractStatus.ACTIVE.value,
                            Contract.auto_renewal == True,
                            Contract.expiration_date.isnot(None),
                            Contract.expiration_date >= today,
                            Contract.expiration_date <= check_until,
                        )
                    )

                    contracts_result = await db.execute(contracts_query)
                    contracts = contracts_result.scalars().all()

                    for contract in contracts:
                        stats["contracts_checked"] += 1

                        try:
                            # Pruefen ob Kuendigungsfrist schon vorbei
                            notice_deadline = None
                            if contract.notice_period_days and contract.expiration_date:
                                notice_deadline = contract.expiration_date - timedelta(
                                    days=contract.notice_period_days
                                )

                            # Wenn Kuendigungsfrist noch nicht abgelaufen -> noch Zeit zum Kuendigen
                            if notice_deadline and notice_deadline > today:
                                stats["renewals_skipped"] += 1
                                continue

                            # Verlaengerungszeitraum bestimmen
                            renewal_months = contract.renewal_period_months or 12

                            # Neues Ablaufdatum berechnen
                            old_expiration = contract.expiration_date
                            # Monate hinzufuegen (vereinfacht)
                            new_year = old_expiration.year + (old_expiration.month + renewal_months - 1) // 12
                            new_month = ((old_expiration.month + renewal_months - 1) % 12) + 1
                            try:
                                new_expiration = old_expiration.replace(year=new_year, month=new_month)
                            except ValueError:
                                # Fuer Monate mit weniger Tagen (z.B. 31. -> 28. Feb)
                                new_expiration = old_expiration.replace(
                                    year=new_year, month=new_month, day=28
                                )

                            contract.expiration_date = new_expiration
                            contract.updated_at = datetime.now(timezone.utc)

                            # Audit-Eintrag (Metadaten)
                            if not contract.metadata:
                                contract.metadata = {}
                            if "renewals" not in contract.metadata:
                                contract.metadata["renewals"] = []
                            contract.metadata["renewals"].append({
                                "old_expiration": old_expiration.isoformat(),
                                "new_expiration": new_expiration.isoformat(),
                                "renewed_at": datetime.now(timezone.utc).isoformat(),
                                "renewal_months": renewal_months,
                            })

                            stats["renewals_triggered"] += 1
                            stats["renewed_contracts"].append({
                                "contract_id": str(contract.id),
                                "old_expiration": old_expiration.isoformat(),
                                "new_expiration": new_expiration.isoformat(),
                            })

                            logger.info(
                                "contract_auto_renewed_v2",
                                contract_id=str(contract.id),
                                old_expiration=str(old_expiration),
                                new_expiration=str(new_expiration),
                                renewal_months=renewal_months,
                            )

                            # Notification senden
                            try:
                                from app.services.notification_service import get_notification_service

                                notification_service = get_notification_service()
                                await notification_service.notify(
                                    notification_type="contract_auto_renewed",
                                    context={
                                        "contract_id": str(contract.id),
                                        "contract_title": contract.title[:50] if contract.title else "Vertrag",
                                        "old_expiration": old_expiration.strftime("%d.%m.%Y"),
                                        "new_expiration": new_expiration.strftime("%d.%m.%Y"),
                                        "renewal_months": renewal_months,
                                    },
                                    priority="normal",
                                )
                                stats["notifications_sent"] += 1
                            except Exception as notif_e:
                                logger.debug(
                                    "contract_renewal_notification_failed",
                                    error_type=type(notif_e).__name__,
                                )

                        except Exception as contract_e:
                            stats["errors"].append({
                                "contract_id": str(contract.id),
                                "error": safe_error_detail(contract_e, "Verlaengerung"),
                            })
                            logger.warning(
                                "contract_renewal_failed_v2",
                                contract_id=str(contract.id),
                                **safe_error_log(contract_e),
                            )

                    await db.commit()

                except Exception as company_e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(company_e, "Vertragssuche"),
                    })
                    logger.warning(
                        "contract_renewal_company_error_v2",
                        company_id=str(company.id),
                        **safe_error_log(company_e),
                    )

            stats["generated_at"] = datetime.now(timezone.utc).isoformat()
            return stats

    try:
        result = asyncio.run(_check_renewals())
        logger.info(
            "check_auto_renewals_v2_completed",
            companies_checked=result["companies_checked"],
            contracts_checked=result["contracts_checked"],
            renewals_triggered=result["renewals_triggered"],
            notifications_sent=result["notifications_sent"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("check_auto_renewals_v2_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Document Linking Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.link_document_to_contract_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="metadata",
)
def link_document_to_contract_task(
    self,
    contract_id: str,
    document_id: str,
    company_id: str,
    is_primary: bool = False,
) -> Dict[str, Any]:
    """
    Verknuepft ein Dokument mit einem Vertrag.

    Args:
        contract_id: Vertrags-ID
        document_id: Dokument-ID
        company_id: Firmen-ID
        is_primary: Als Hauptdokument setzen

    Returns:
        Dict mit Status
    """
    from app.services.contract_service_v2 import get_contract_service_v2

    async def _link_document() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_service_v2(db)

            success = await service.link_document(
                contract_id=UUID(contract_id),
                document_id=UUID(document_id),
                company_id=UUID(company_id),
                is_primary=is_primary,
            )

            return {
                "success": success,
                "contract_id": contract_id,
                "document_id": document_id,
                "is_primary": is_primary,
            }

    try:
        result = asyncio.run(_link_document())
        if result["success"]:
            logger.info(
                "document_linked_to_contract_v2",
                contract_id=contract_id,
                document_id=document_id,
                is_primary=is_primary,
            )
        return result
    except Exception as e:
        logger.error(
            "document_linking_failed",
            contract_id=contract_id,
            document_id=document_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Contract V2 Enhancements - Clause Recognition Tasks (Phase 5)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.extract_contract_clauses_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def extract_contract_clauses_task(
    self,
    contract_id: str,
    company_id: str,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extrahiert Vertragsklauseln aus einem Vertrag/Dokument.

    Erkennt automatisch:
    - Preisanpassungsklauseln
    - Mindestlaufzeiten
    - Kuendigungsfristen
    - Automatische Verlaengerung
    - Vertragsstrafen
    - Haftungsbegrenzungen
    - Gerichtsstand

    Args:
        contract_id: Vertrags-ID
        company_id: Firmen-ID
        document_id: Optional - spezifisches Dokument

    Returns:
        Dict mit extrahierten Klauseln
    """
    from app.services.contracts import get_clause_recognition_service
    from app.db.models_contract import Contract
    from app.db.models import Document

    async def _extract_clauses() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_clause_recognition_service(db)

            # Vertrag laden
            contract = await db.get(Contract, UUID(contract_id))
            if not contract or contract.company_id != UUID(company_id):
                return {
                    "success": False,
                    "error": "Vertrag nicht gefunden",
                    "contract_id": contract_id,
                }

            # Text beschaffen
            text = None
            doc_id = UUID(document_id) if document_id else contract.document_id

            if doc_id:
                document = await db.get(Document, doc_id)
                if document and document.extracted_text:
                    text = document.extracted_text

            if not text:
                return {
                    "success": False,
                    "error": "Kein Text zum Analysieren verfuegbar",
                    "contract_id": contract_id,
                }

            # Klauseln extrahieren und speichern
            clauses = await service.extract_and_store_clauses(
                contract_id=UUID(contract_id),
                company_id=UUID(company_id),
                text=text,
            )

            return {
                "success": True,
                "contract_id": contract_id,
                "clauses_found": len(clauses),
                "clause_types": list(set(c.clause_type.value for c in clauses)),
                "high_confidence_count": sum(1 for c in clauses if c.confidence >= 0.8),
                "high_risk_count": sum(1 for c in clauses if c.risk_level == "high"),
            }

    try:
        result = asyncio.run(_extract_clauses())
        logger.info(
            "contract_clauses_extracted",
            contract_id=contract_id,
            success=result["success"],
            clauses_found=result.get("clauses_found", 0),
        )
        return result
    except Exception as e:
        logger.error(
            "contract_clause_extraction_failed",
            contract_id=contract_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.extract_all_contract_clauses_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def extract_all_contract_clauses_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Batch-Extraktion von Klauseln fuer alle Vertraege.

    Wird woechentlich am Sonntag um 03:00 ausgefuehrt.

    Args:
        company_id: Optional - nur fuer spezifische Firma

    Returns:
        Dict mit Statistiken
    """
    from app.db.models_contract import Contract, ContractStatus

    async def _extract_all() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "contracts_processed": 0,
                "clauses_extracted": 0,
                "errors": [],
            }

            # Aktive Vertraege laden
            query = select(Contract).where(
                Contract.status.in_([
                    ContractStatus.ACTIVE.value,
                    ContractStatus.DRAFT.value,
                ])
            )
            if company_id:
                query = query.where(Contract.company_id == UUID(company_id))

            result = await db.execute(query)
            contracts = result.scalars().all()

            for contract in contracts:
                try:
                    # Task fuer jeden Vertrag triggern
                    extract_contract_clauses_task.delay(
                        contract_id=str(contract.id),
                        company_id=str(contract.company_id),
                    )
                    stats["contracts_processed"] += 1
                except Exception as e:
                    stats["errors"].append({
                        "contract_id": str(contract.id),
                        "error": safe_error_detail(e, "Klausel-Extraktion"),
                    })

            return stats

    try:
        result = asyncio.run(_extract_all())
        logger.info(
            "batch_clause_extraction_triggered",
            contracts_processed=result["contracts_processed"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("batch_clause_extraction_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Contract V2 Enhancements - Benchmark Tasks (Phase 5)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.compare_contract_to_benchmark_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="metadata",
)
def compare_contract_to_benchmark_task(
    self,
    contract_id: str,
    company_id: str,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Vergleicht einen Vertrag mit Markt-Benchmarks.

    Args:
        contract_id: Vertrags-ID
        company_id: Firmen-ID
        category: Optional - Benchmark-Kategorie

    Returns:
        Dict mit Benchmark-Ergebnis
    """
    from app.services.contracts import get_contract_benchmark_service
    from app.db.models_contract import Contract

    async def _compare_benchmark() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_benchmark_service(db)

            contract = await db.get(Contract, UUID(contract_id))
            if not contract or contract.company_id != UUID(company_id):
                return {
                    "success": False,
                    "error": "Vertrag nicht gefunden",
                    "contract_id": contract_id,
                }

            result = await service.compare_contract_to_benchmark(
                contract=contract,
                category=category,
            )

            # Verhandlungsvorschlaege generieren
            suggestions = await service.get_negotiation_suggestions(result)

            return {
                "success": True,
                "contract_id": contract_id,
                "benchmark_category": result.category,
                "metrics": [
                    {
                        "name": m.metric_name,
                        "contract_value": m.contract_value,
                        "benchmark_value": m.benchmark_value,
                        "percentile": m.percentile,
                        "recommendation": m.recommendation,
                    }
                    for m in result.metrics
                ],
                "overall_assessment": result.overall_assessment,
                "negotiation_suggestions": suggestions,
            }

    try:
        result = asyncio.run(_compare_benchmark())
        logger.info(
            "contract_benchmark_compared",
            contract_id=contract_id,
            success=result["success"],
            category=result.get("benchmark_category"),
        )
        return result
    except Exception as e:
        logger.error(
            "contract_benchmark_comparison_failed",
            contract_id=contract_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.update_contract_benchmarks_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def update_contract_benchmarks_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aktualisiert Benchmark-Daten basierend auf Vertraegen.

    Wird monatlich am 1. um 04:00 ausgefuehrt.

    Args:
        company_id: Optional - nur fuer spezifische Firma

    Returns:
        Dict mit Statistiken
    """
    from app.services.contracts import get_contract_benchmark_service

    async def _update_benchmarks() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_benchmark_service(db)

            cid = UUID(company_id) if company_id else None
            benchmarks = await service.update_benchmark_from_contracts(
                company_id=cid,
            )

            return {
                "success": True,
                "benchmarks_updated": len(benchmarks),
                "categories": list(set(b.category for b in benchmarks)),
            }

    try:
        result = asyncio.run(_update_benchmarks())
        logger.info(
            "contract_benchmarks_updated",
            benchmarks_updated=result["benchmarks_updated"],
        )
        return result
    except Exception as e:
        logger.error("contract_benchmarks_update_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Contract V2 Enhancements - Auto-Cancellation Tasks (Phase 5)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.process_scheduled_cancellations_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def process_scheduled_cancellations_task(self) -> Dict[str, Any]:
    """
    Verarbeitet geplante Vertragskunedigungen.

    Wird taeglich um 08:30 ausgefuehrt.
    Sendet Kuendigungsschreiben die zur Versendung faellig sind.

    Returns:
        Dict mit Statistiken
    """
    from app.services.contracts import get_auto_cancellation_service
    from app.db.models_contract import ContractCancellation, CancellationStatus

    async def _process_cancellations() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "cancellations_processed": 0,
                "emails_sent": 0,
                "errors": [],
            }

            today = date.today()

            # Genehmigte Kuendigungen die heute gesendet werden sollen
            result = await db.execute(
                select(ContractCancellation).where(
                    and_(
                        ContractCancellation.status == CancellationStatus.APPROVED.value,
                        ContractCancellation.send_date <= today,
                    )
                )
            )
            cancellations = result.scalars().all()

            service = get_auto_cancellation_service(db)

            for cancellation in cancellations:
                try:
                    updated = await service.send_cancellation(
                        cancellation_id=cancellation.id,
                        company_id=cancellation.company_id,
                        send_method="email",
                    )
                    if updated:
                        stats["cancellations_processed"] += 1
                        stats["emails_sent"] += 1
                except Exception as e:
                    stats["errors"].append({
                        "cancellation_id": str(cancellation.id),
                        "error": safe_error_detail(e, "Kuendigungs-Versand"),
                    })
                    logger.warning(
                        "cancellation_send_failed",
                        cancellation_id=str(cancellation.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_process_cancellations())
        logger.info(
            "scheduled_cancellations_processed",
            processed=result["cancellations_processed"],
            emails_sent=result["emails_sent"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("scheduled_cancellations_processing_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.check_cancellation_deadlines_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_cancellation_deadlines_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 30,
) -> Dict[str, Any]:
    """
    Prueft Kuendigungsfristen und erstellt Warnungen.

    Wird taeglich um 09:00 ausgefuehrt.
    Benachrichtigt bei bevorstehenden Kuendigungsfristen.

    Args:
        company_id: Optional - nur fuer spezifische Firma
        days_ahead: Vorausschau in Tagen

    Returns:
        Dict mit Statistiken
    """
    from app.db.models_contract import Contract, ContractStatus
    from app.services.notification_service import get_notification_service, NotificationPriority

    async def _check_deadlines() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "contracts_checked": 0,
                "warnings_created": 0,
                "critical_deadlines": 0,
            }

            today = date.today()
            deadline_limit = today + timedelta(days=days_ahead)

            # Vertraege mit Kuendigungsfrist-Berechnung
            query = select(Contract).where(
                and_(
                    Contract.status == ContractStatus.ACTIVE.value,
                    Contract.expiration_date.isnot(None),
                    Contract.notice_period_days.isnot(None),
                )
            )
            if company_id:
                query = query.where(Contract.company_id == UUID(company_id))

            result = await db.execute(query)
            contracts = result.scalars().all()

            notification_service = get_notification_service()

            for contract in contracts:
                stats["contracts_checked"] += 1

                # Kuendigungsfrist berechnen
                notice_deadline = contract.expiration_date - timedelta(
                    days=contract.notice_period_days
                )

                if today <= notice_deadline <= deadline_limit:
                    days_until = (notice_deadline - today).days

                    # Prioritaet bestimmen
                    if days_until <= 7:
                        priority = NotificationPriority.CRITICAL
                        stats["critical_deadlines"] += 1
                    elif days_until <= 14:
                        priority = NotificationPriority.HIGH
                    else:
                        priority = NotificationPriority.NORMAL

                    try:
                        await notification_service.notify(
                            notification_type="contract_cancellation_deadline",
                            context={
                                "contract_id": str(contract.id),
                                "contract_title": contract.title[:50] if contract.title else "Vertrag",
                                "notice_deadline": notice_deadline.strftime("%d.%m.%Y"),
                                "expiration_date": contract.expiration_date.strftime("%d.%m.%Y"),
                                "days_until": days_until,
                            },
                            priority=priority.value,
                        )
                        stats["warnings_created"] += 1
                    except Exception:
                        pass  # Notification-Fehler nicht kritisch

            return stats

    try:
        result = asyncio.run(_check_deadlines())
        logger.info(
            "cancellation_deadlines_checked",
            contracts_checked=result["contracts_checked"],
            warnings_created=result["warnings_created"],
            critical_deadlines=result["critical_deadlines"],
        )
        return result
    except Exception as e:
        logger.error("cancellation_deadline_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Contract V2 Enhancements - Cost Analysis Tasks (Phase 5)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.analyze_contract_costs_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="metadata",
)
def analyze_contract_costs_task(
    self,
    contract_id: str,
    company_id: str,
) -> Dict[str, Any]:
    """
    Analysiert Kosten eines Vertrags.

    Args:
        contract_id: Vertrags-ID
        company_id: Firmen-ID

    Returns:
        Dict mit Kostenanalyse
    """
    from app.services.contracts import get_contract_cost_analyzer
    from app.db.models_contract import Contract

    async def _analyze_costs() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_cost_analyzer(db)

            contract = await db.get(Contract, UUID(contract_id))
            if not contract or contract.company_id != UUID(company_id):
                return {
                    "success": False,
                    "error": "Vertrag nicht gefunden",
                    "contract_id": contract_id,
                }

            analysis = await service.analyze_contract_costs(
                contract=contract,
                include_projections=True,
            )

            return {
                "success": True,
                "contract_id": contract_id,
                "total_costs": float(analysis.total_costs),
                "annual_costs": float(analysis.annual_costs),
                "cost_breakdown": analysis.cost_breakdown,
                "trend": analysis.trend,
                "projections": analysis.projections,
                "optimization_potential": float(analysis.optimization_potential),
                "suggestions_count": len(analysis.optimization_suggestions),
            }

    try:
        result = asyncio.run(_analyze_costs())
        logger.info(
            "contract_costs_analyzed",
            contract_id=contract_id,
            success=result["success"],
            annual_costs=result.get("annual_costs"),
        )
        return result
    except Exception as e:
        logger.error(
            "contract_cost_analysis_failed",
            contract_id=contract_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_v2_tasks.generate_contract_cost_report_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def generate_contract_cost_report_task(
    self,
    company_id: str,
) -> Dict[str, Any]:
    """
    Generiert Kosten-Report fuer alle Vertraege.

    Wird monatlich am 1. um 06:00 ausgefuehrt.

    Args:
        company_id: Firmen-ID

    Returns:
        Dict mit Report-Daten
    """
    from app.services.contracts import get_contract_cost_analyzer

    async def _generate_report() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_contract_cost_analyzer(db)

            summary = await service.get_portfolio_summary(
                company_id=UUID(company_id),
            )

            trends = await service.get_cost_trends(
                company_id=UUID(company_id),
                months=12,
            )

            return {
                "success": True,
                "company_id": company_id,
                "summary": {
                    "total_annual_costs": float(summary["total_annual_costs"]),
                    "total_monthly_costs": float(summary["total_monthly_costs"]),
                    "contracts_count": summary["contracts_count"],
                    "optimization_potential": float(summary["optimization_potential"]),
                },
                "cost_trends": trends,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = asyncio.run(_generate_report())
        logger.info(
            "contract_cost_report_generated",
            company_id=company_id,
            total_annual_costs=result.get("summary", {}).get("total_annual_costs"),
        )
        return result
    except Exception as e:
        logger.error(
            "contract_cost_report_generation_failed",
            company_id=company_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)
