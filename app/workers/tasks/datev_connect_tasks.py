# -*- coding: utf-8 -*-
"""
DATEV Connect Celery Tasks.

Hintergrund-Jobs für DATEV-Integration:
- Token Refresh
- Stammdaten Sync
- Buchungsstapel Push
- Belegbilder Upload
- GoBD Compliance Check

Feinpoliert und durchdacht - Zuverlässige DATEV-Synchronisation.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from celery import shared_task
from sqlalchemy import select, and_

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import get_async_session_context
from app.workers.celery_app import celery_app as celery

logger = structlog.get_logger(__name__)


# =============================================================================
# Token Management Tasks
# =============================================================================

@celery.task(
    name="app.workers.tasks.datev_connect_tasks.refresh_all_datev_tokens",
    queue="datev",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def refresh_all_datev_tokens(self) -> Dict[str, Any]:
    """
    Aktualisiert alle DATEV OAuth-Tokens die bald ablaufen.

    Wird alle 30 Minuten ausgeführt um Token-Expiration zu vermeiden.
    """
    import asyncio

    async def _refresh_tokens() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import get_datev_auth_service

        auth_service = get_datev_auth_service()
        results = {"refreshed": 0, "failed": 0, "skipped": 0}

        async with get_async_session_context() as db:
            # Connections mit bald ablaufenden Tokens finden
            buffer = timedelta(minutes=10)
            expiry_threshold = utc_now() + buffer

            connections_result = await db.execute(
                select(models.DATEVConnection).where(
                    and_(
                        models.DATEVConnection.is_active == True,
                        models.DATEVConnection.token_expires_at.isnot(None),
                        models.DATEVConnection.token_expires_at < expiry_threshold,
                        models.DATEVConnection.refresh_token_encrypted.isnot(None),
                    )
                )
            )
            connections = connections_result.scalars().all()

            for conn in connections:
                try:
                    # Client Secret entschluesseln
                    from app.core.encryption import decrypt_value
                    client_secret = decrypt_value(conn.client_secret_encrypted) or ""

                    success = await auth_service.refresh_tokens(
                        db=db,
                        connection_id=conn.id,
                        refresh_token_encrypted=conn.refresh_token_encrypted,
                        client_id=conn.client_id,
                        client_secret=client_secret,
                        environment=conn.api_environment,
                    )

                    if success:
                        results["refreshed"] += 1
                    else:
                        results["failed"] += 1
                        logger.warning(
                            "datev_token_refresh_failed",
                            connection_id=str(conn.id),
                        )

                except Exception as e:
                    results["failed"] += 1
                    logger.error(
                        "datev_token_refresh_error",
                        connection_id=str(conn.id),
                        **safe_error_log(e)
                    )

        return results

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_refresh_tokens())
    finally:
        loop.close()


# =============================================================================
# Stammdaten Sync Tasks
# =============================================================================

@celery.task(
    name="app.workers.tasks.datev_connect_tasks.sync_datev_stammdaten",
    queue="datev",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_datev_stammdaten(
    self,
    connection_id: str,
    entity_type: str = "all",  # customer, supplier, all
) -> Dict[str, Any]:
    """
    Synchronisiert Stammdaten (Kunden/Lieferanten) mit DATEV.

    Args:
        connection_id: UUID der DATEV-Verbindung
        entity_type: Zu synchronisierende Entitaeten

    Returns:
        Sync-Ergebnis
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import DATEVConnector, DATEVConnectionConfig
        from app.services.erp.base_connector import ERPSyncDirection

        async with get_async_session_context() as db:
            # Connection laden
            conn_result = await db.execute(
                select(models.DATEVConnection).where(
                    models.DATEVConnection.id == uuid.UUID(connection_id)
                )
            )
            conn = conn_result.scalar_one_or_none()

            if not conn:
                return {"success": False, "error": "Verbindung nicht gefunden"}

            if not conn.is_active:
                return {"success": False, "error": "Verbindung nicht aktiv"}

            # Connector erstellen
            from app.core.encryption import decrypt_value
            config = DATEVConnectionConfig(
                beraternummer=conn.beraternummer,
                mandantennummer=conn.mandantennummer,
                client_id=conn.client_id or "",
                client_secret=decrypt_value(conn.client_secret_encrypted) or "",
                access_token=decrypt_value(conn.access_token_encrypted) or "",
                refresh_token=decrypt_value(conn.refresh_token_encrypted) or "",
                token_expires_at=conn.token_expires_at,
                api_environment=conn.api_environment,
                kontenrahmen=conn.kontenrahmen,
            )
            connector = DATEVConnector(config)

            results = {
                "connection_id": connection_id,
                "customers": {"synced": 0, "failed": 0},
                "suppliers": {"synced": 0, "failed": 0},
            }

            # Kunden synchronisieren
            if entity_type in ("customer", "all"):
                customer_result = await connector.sync_customers(
                    direction=ERPSyncDirection.PULL,
                    since=conn.last_stammdaten_sync,
                )
                results["customers"] = {
                    "synced": customer_result.records_synced,
                    "failed": customer_result.records_failed,
                }

            # Lieferanten synchronisieren
            if entity_type in ("supplier", "all"):
                supplier_result = await connector.sync_suppliers(
                    direction=ERPSyncDirection.PULL,
                    since=conn.last_stammdaten_sync,
                )
                results["suppliers"] = {
                    "synced": supplier_result.records_synced,
                    "failed": supplier_result.records_failed,
                }

            # Letzte Sync-Zeit aktualisieren
            conn.last_stammdaten_sync = utc_now()
            await db.commit()

            # Sync-History eintragen
            history = models.DATEVSyncHistory(
                id=uuid.uuid4(),
                connection_id=conn.id,
                sync_type="stammdaten",
                sync_direction="pull",
                status="success",
                records_total=results["customers"]["synced"] + results["suppliers"]["synced"],
                records_created=results["customers"]["synced"] + results["suppliers"]["synced"],
                started_at=utc_now(),
                completed_at=utc_now(),
                triggered_by="scheduled",
            )
            db.add(history)
            await db.commit()

            return results

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_sync())
    finally:
        loop.close()


@celery.task(
    name="app.workers.tasks.datev_connect_tasks.sync_all_datev_stammdaten",
    queue="datev",
)
def sync_all_datev_stammdaten() -> Dict[str, Any]:
    """
    Synchronisiert Stammdaten für alle aktiven DATEV-Verbindungen.

    Wird alle 4 Stunden per Beat-Schedule ausgeführt.
    """
    import asyncio

    async def _sync_all() -> Dict[str, Any]:
        from app.db import models

        async with get_async_session_context() as db:
            connections_result = await db.execute(
                select(models.DATEVConnection.id).where(
                    models.DATEVConnection.is_active == True,
                    models.DATEVConnection.connection_status == "connected",
                )
            )
            connection_ids = [str(c) for c in connections_result.scalars().all()]

        # Tasks für alle Verbindungen starten
        tasks_started = 0
        for conn_id in connection_ids:
            sync_datev_stammdaten.delay(conn_id, "all")
            tasks_started += 1

        return {
            "connections_found": len(connection_ids),
            "tasks_started": tasks_started,
        }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_sync_all())
    finally:
        loop.close()


# =============================================================================
# Buchungsstapel Tasks
# =============================================================================

@celery.task(
    name="app.workers.tasks.datev_connect_tasks.push_datev_buchungsstapel",
    queue="datev",
    bind=True,
    max_retries=3,
    default_retry_delay=600,
)
def push_datev_buchungsstapel(
    self,
    connection_id: str,
    buchung_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Pusht Buchungsstapel zu DATEV.

    Args:
        connection_id: UUID der DATEV-Verbindung
        buchung_ids: Optional: Nur bestimmte Buchungen

    Returns:
        Push-Ergebnis
    """
    import asyncio

    async def _push() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import DATEVConnector, DATEVConnectionConfig

        async with get_async_session_context() as db:
            # Connection laden
            conn_result = await db.execute(
                select(models.DATEVConnection).where(
                    models.DATEVConnection.id == uuid.UUID(connection_id)
                )
            )
            conn = conn_result.scalar_one_or_none()

            if not conn:
                return {"success": False, "error": "Verbindung nicht gefunden"}

            # Buchungen laden
            query = select(models.DATEVBuchung).where(
                models.DATEVBuchung.connection_id == conn.id,
                models.DATEVBuchung.sync_status == "pending",
            )

            if buchung_ids:
                query = query.where(
                    models.DATEVBuchung.id.in_([uuid.UUID(b) for b in buchung_ids])
                )

            buchungen_result = await db.execute(query)
            buchungen = buchungen_result.scalars().all()

            if not buchungen:
                return {"success": True, "message": "Keine Buchungen zu pushen"}

            # Connector erstellen
            from app.core.encryption import decrypt_value
            config = DATEVConnectionConfig(
                beraternummer=conn.beraternummer,
                mandantennummer=conn.mandantennummer,
                client_id=conn.client_id or "",
                client_secret=decrypt_value(conn.client_secret_encrypted) or "",
                access_token=decrypt_value(conn.access_token_encrypted) or "",
                token_expires_at=conn.token_expires_at,
                api_environment=conn.api_environment,
            )
            connector = DATEVConnector(config)

            # Buchungen vorbereiten
            buchungen_data = [
                {
                    "umsatz": float(b.umsatz),
                    "soll_haben": b.soll_haben,
                    "konto": b.konto,
                    "gegenkonto": b.gegenkonto,
                    "bu_schluessel": b.bu_schluessel,
                    "belegdatum": b.belegdatum,
                    "belegfeld_1": b.belegfeld_1,
                    "belegfeld_2": b.belegfeld_2,
                    "buchungstext": b.buchungstext,
                    "kostenstelle_1": b.kostenstelle_1,
                }
                for b in buchungen
            ]

            # Push durchführen
            success, stapel_id, errors = await connector.push_buchungsstapel(buchungen_data)

            if success:
                # Buchungen als synced markieren
                for b in buchungen:
                    b.sync_status = "synced"
                    b.synced_at = utc_now()
                    b.datev_buchung_id = stapel_id

                conn.last_buchungen_sync = utc_now()
                await db.commit()

            # Sync-History
            history = models.DATEVSyncHistory(
                id=uuid.uuid4(),
                connection_id=conn.id,
                sync_type="buchungen",
                sync_direction="push",
                status="success" if success else "failed",
                records_total=len(buchungen),
                records_created=len(buchungen) if success else 0,
                records_failed=0 if success else len(buchungen),
                started_at=utc_now(),
                completed_at=utc_now(),
                triggered_by="api",
                error_message="; ".join(errors) if errors else None,
            )
            db.add(history)
            await db.commit()

            return {
                "success": success,
                "stapel_id": stapel_id,
                "buchungen_count": len(buchungen),
                "errors": errors,
            }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_push())
    finally:
        loop.close()


# =============================================================================
# Belegbilder Tasks
# =============================================================================

@celery.task(
    name="app.workers.tasks.datev_connect_tasks.upload_pending_datev_belege",
    queue="datev",
)
def upload_pending_datev_belege() -> Dict[str, Any]:
    """
    Laedt ausstehende Belegbilder zu DATEV hoch.

    Wird alle 15 Minuten per Beat-Schedule ausgeführt.
    """
    import asyncio

    async def _upload() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import DATEVConnector, DATEVConnectionConfig

        results = {"uploaded": 0, "failed": 0}

        async with get_async_session_context() as db:
            # Pending Beleglinks finden
            links_result = await db.execute(
                select(models.DATEVBeleglink)
                .join(models.DATEVBuchung)
                .join(models.DATEVConnection)
                .where(
                    models.DATEVBeleglink.upload_status == "pending",
                    models.DATEVConnection.is_active == True,
                )
                .limit(50)  # Batch-Größe
            )
            links = links_result.scalars().all()

            for link in links:
                try:
                    # Load document from MinIO and upload to DATEV
                    from app.services.storage.minio_service import get_minio_service
                    from app.services.datev.connect.datev_connector import DATEVConnector, ERPEntity

                    # Get connection configuration
                    buchung = link.buchung
                    connection = buchung.connection if buchung else None

                    if not connection or not connection.is_active:
                        link.upload_status = "skipped"
                        link.upload_error = "Connection inactive"
                        continue

                    # Load document from MinIO
                    minio_service = get_minio_service()
                    document = link.document
                    if not document or not document.file_path:
                        link.upload_status = "failed"
                        link.upload_error = "Document not found"
                        results["failed"] += 1
                        continue

                    document_data = await minio_service.get_document(document.file_path)
                    if not document_data:
                        link.upload_status = "failed"
                        link.upload_error = "Document data not found in storage"
                        results["failed"] += 1
                        continue

                    # Initialize DATEV connector
                    config = DATEVConnectionConfig(
                        mandantennummer=connection.mandantennummer,
                        berater_nr=connection.berater_nr,
                        wirtschaftsjahr=connection.wirtschaftsjahr or datetime.now().year,
                        kontenrahmen=connection.kontenrahmen,
                        access_token=connection.access_token,
                    )
                    connector = DATEVConnector(config)

                    # Upload to DATEV
                    success = await connector.attach_document(
                        entity=ERPEntity.BOOKING,  # Belegbilder are booking-related
                        erp_id=str(buchung.datev_guid) if buchung.datev_guid else str(link.id),
                        document_data=document_data,
                        filename=document.original_filename or f"beleg_{link.id}.pdf",
                        mime_type=document.mime_type or "application/pdf",
                    )

                    if success:
                        link.upload_status = "uploaded"
                        link.uploaded_at = utc_now()
                        link.datev_document_id = str(buchung.datev_guid) if buchung else None
                        results["uploaded"] += 1
                        logger.info(
                            "datev_beleg_uploaded",
                            link_id=str(link.id),
                            document_id=str(document.id) if document else None,
                        )
                    else:
                        link.upload_status = "failed"
                        link.upload_error = "DATEV API rejected upload"
                        results["failed"] += 1

                except Exception as e:
                    link.upload_status = "failed"
                    link.upload_error = safe_error_detail(e, "Beleg-Upload")
                    results["failed"] += 1
                    logger.warning(
                        "datev_beleg_upload_error",
                        link_id=str(link.id),
                        error_type=type(e).__name__,
                    )

            await db.commit()

        return results

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_upload())
    finally:
        loop.close()


# =============================================================================
# GoBD Compliance Tasks
# =============================================================================

@celery.task(
    name="app.workers.tasks.datev_connect_tasks.datev_gobd_compliance_check",
    queue="maintenance",
)
def datev_gobd_compliance_check() -> Dict[str, Any]:
    """
    Führt GoBD-Compliance-Check für alle Verbindungen durch.

    Wird täglich um 05:00 per Beat-Schedule ausgeführt.
    """
    import asyncio

    async def _check() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import get_gobd_service

        gobd_service = get_gobd_service()
        results = {"checked": 0, "compliant": 0, "non_compliant": 0}

        async with get_async_session_context() as db:
            connections_result = await db.execute(
                select(models.DATEVConnection).where(
                    models.DATEVConnection.is_active == True,
                    models.DATEVConnection.gobd_enabled == True,
                )
            )
            connections = connections_result.scalars().all()

            for conn in connections:
                try:
                    validation = await gobd_service.validate_gobd_compliance(
                        db=db,
                        connection_id=conn.id,
                    )
                    results["checked"] += 1
                    if validation.is_compliant:
                        results["compliant"] += 1
                    else:
                        results["non_compliant"] += 1
                        logger.warning(
                            "datev_gobd_non_compliant",
                            connection_id=str(conn.id),
                            findings=len(validation.findings),
                        )
                        # Send alert for non-compliance
                        try:
                            from app.services.slack_service import SlackService, SlackNotificationType, SlackMessagePriority

                            slack = SlackService()
                            if slack.is_enabled:
                                findings_summary = ", ".join(
                                    [f.get("description", "Unbekannter Befund")[:50] for f in validation.findings[:3]]
                                )
                                await slack.send_notification(
                                    notification_type=SlackNotificationType.SYSTEM_ALERT,
                                    title="DATEV GoBD Non-Compliance",
                                    message=f"Verbindung {str(conn.id)[:8]} hat {len(validation.findings)} GoBD-Befunde: {findings_summary}",
                                    priority=SlackMessagePriority.HIGH,
                                    context={
                                        "connection_id": str(conn.id),
                                        "findings_count": len(validation.findings),
                                        "severity": validation.severity if hasattr(validation, "severity") else "warning",
                                    }
                                )
                        except Exception as notification_error:
                            logger.warning(
                                "datev_compliance_notification_failed",
                                connection_id=str(conn.id),
                                error_type=type(notification_error).__name__
                            )
                except Exception as e:
                    logger.error(
                        "datev_gobd_check_error",
                        connection_id=str(conn.id),
                        **safe_error_log(e)
                    )

        return results

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_check())
    finally:
        loop.close()


@celery.task(
    name="app.workers.tasks.datev_connect_tasks.datev_auto_festschreibung",
    queue="maintenance",
)
def datev_auto_festschreibung() -> Dict[str, Any]:
    """
    Führt automatische Festschreibung am Monatsende durch.

    Wird am 1. jeden Monats um 02:00 ausgeführt.
    """
    import asyncio

    async def _festschreiben() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import get_gobd_service

        gobd_service = get_gobd_service()
        results = {"connections": 0, "buchungen": 0, "fehler": []}

        # Letzter Tag des Vormonats
        heute = date.today()
        erster_dieses_monats = heute.replace(day=1)
        letzter_vormonat = erster_dieses_monats - timedelta(days=1)

        async with get_async_session_context() as db:
            connections_result = await db.execute(
                select(models.DATEVConnection).where(
                    models.DATEVConnection.is_active == True,
                    models.DATEVConnection.festschreibung_automatisch == True,
                )
            )
            connections = connections_result.scalars().all()

            for conn in connections:
                try:
                    result = await gobd_service.festschreiben_buchungen(
                        db=db,
                        connection_id=conn.id,
                        bis_datum=letzter_vormonat,
                    )
                    results["connections"] += 1
                    results["buchungen"] += result.buchungen_count
                    if result.fehler:
                        results["fehler"].extend(result.fehler)
                except Exception as e:
                    results["fehler"].append(f"{conn.id}: {str(e)}")
                    logger.error(
                        "datev_auto_festschreibung_error",
                        connection_id=str(conn.id),
                        **safe_error_log(e)
                    )

        return results

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_festschreiben())
    finally:
        loop.close()


# =============================================================================
# Kontenplan Sync Tasks
# =============================================================================

@celery.task(
    name="app.workers.tasks.datev_connect_tasks.sync_datev_kontenplan",
    queue="datev",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_datev_kontenplan(
    self,
    connection_id: str,
) -> Dict[str, Any]:
    """
    Synchronisiert Kontenplan von DATEV.

    Args:
        connection_id: UUID der DATEV-Verbindung

    Returns:
        Sync-Ergebnis
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        from app.db import models
        from app.services.datev.connect import DATEVConnector, DATEVConnectionConfig

        async with get_async_session_context() as db:
            # Connection laden
            conn_result = await db.execute(
                select(models.DATEVConnection).where(
                    models.DATEVConnection.id == uuid.UUID(connection_id)
                )
            )
            conn = conn_result.scalar_one_or_none()

            if not conn:
                return {"success": False, "error": "Verbindung nicht gefunden"}

            # Connector erstellen
            from app.core.encryption import decrypt_value
            config = DATEVConnectionConfig(
                beraternummer=conn.beraternummer,
                mandantennummer=conn.mandantennummer,
                client_id=conn.client_id or "",
                client_secret=decrypt_value(conn.client_secret_encrypted) or "",
                access_token=decrypt_value(conn.access_token_encrypted) or "",
                token_expires_at=conn.token_expires_at,
                api_environment=conn.api_environment,
            )
            connector = DATEVConnector(config)

            # Kontenplan abrufen
            konten = await connector.get_kontenplan()

            if not konten:
                return {"success": False, "error": "Kontenplan konnte nicht abgerufen werden"}

            # Lokale Konten aktualisieren
            created = 0
            updated = 0

            for konto_data in konten:
                kontonummer = konto_data.get("number", konto_data.get("kontonummer", ""))

                # Existierendes Konto suchen
                existing_result = await db.execute(
                    select(models.DATEVKontenplan).where(
                        models.DATEVKontenplan.connection_id == conn.id,
                        models.DATEVKontenplan.kontonummer == kontonummer,
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if existing:
                    existing.kontobezeichnung = konto_data.get("name", konto_data.get("kontobezeichnung", ""))
                    existing.kontotyp = konto_data.get("type", "sachkonto")
                    existing.last_synced_at = utc_now()
                    updated += 1
                else:
                    new_konto = models.DATEVKontenplan(
                        id=uuid.uuid4(),
                        connection_id=conn.id,
                        kontonummer=kontonummer,
                        kontobezeichnung=konto_data.get("name", konto_data.get("kontobezeichnung", "")),
                        kontotyp=konto_data.get("type", "sachkonto"),
                        kontenklasse=kontonummer[0] if kontonummer else None,
                        steuercode_default=konto_data.get("tax_code", ""),
                        ist_automatikkonto=konto_data.get("is_automatic", False),
                        ist_gesperrt=konto_data.get("is_locked", False),
                        last_synced_at=utc_now(),
                    )
                    db.add(new_konto)
                    created += 1

            await db.commit()

            return {
                "success": True,
                "konten_total": len(konten),
                "created": created,
                "updated": updated,
            }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_sync())
    finally:
        loop.close()


