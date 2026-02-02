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
    name="contracts_v2.extract_dates_from_document",
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
    name="contracts_v2.check_upcoming_deadlines",
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
    name="contracts_v2.generate_ical_export",
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
    name="contracts_v2.update_statistics",
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
    name="contracts_v2.check_expired_contracts",
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
    name="contracts_v2.complete_deadline",
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


@celery_app.task(
    name="contracts_v2.link_document",
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
