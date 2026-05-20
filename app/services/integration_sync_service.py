# -*- coding: utf-8 -*-
"""Integrations-Sync Dashboard Service.

Steuert Konfiguration, Status-Überwachung und manuelle Auslösung
aller externen Integrationen (DATEV, Lexware, Banking, Slack, E-Mail).

Feinpoliert und durchdacht - Enterprise-grade Integrations-Management.
"""

from datetime import timedelta
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, case, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models_integration_sync import (
    INTEGRATION_TYPES,
    IntegrationConfig,
    IntegrationSyncLog,
    SYNC_LOG_STATUS_VALUES,
    SYNC_TYPE_VALUES,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Celery-Task-Namen pro Integration (für send_task-Dispatch)
# ---------------------------------------------------------------------------

_SYNC_TASK_MAP: Dict[str, str] = {
    "datev": "app.workers.tasks.datev_connect_tasks.sync_datev_manual",
    "lexware": "app.workers.tasks.lexware_sync_tasks.sync_all_task",
    "banking": "app.workers.tasks.banking_tasks.sync_banking_manual",
    "slack": "app.workers.tasks.import_tasks.sync_slack_status",
    "email": "app.workers.tasks.import_tasks.run_email_import_all",
}

# Zeitraum für Fehler-Rate-Berechnung im Health-Check
_HEALTH_WINDOW_HOURS: int = 24

# Maximale Anzahl von Sync-Logs die pro Abfrage zurückgegeben werden
_MAX_HISTORY_LIMIT: int = 200


# ---------------------------------------------------------------------------
# IntegrationSyncService
# ---------------------------------------------------------------------------


class IntegrationSyncService:
    """Service für das Integrations-Sync Dashboard.

    Verwaltet Integrations-Konfigurationen, Sync-Protokolle und
    Health-Status aller externen Schnittstellen pro Mandant.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialisiert den Service mit einer Datenbankverbindung.

        Args:
            session: Async SQLAlchemy Session
        """
        self.session = session

    # =========================================================================
    # Integrations-Liste
    # =========================================================================

    async def get_integrations(
        self,
        company_id: UUID,
    ) -> List[Dict]:
        """Gibt alle Integrations-Konfigurationen eines Mandanten zurück.

        Enthält für jede Integration den letzten bekannten Sync-Status
        sowie den nächsten geplanten Sync-Zeitpunkt.

        Args:
            company_id: Mandanten-ID

        Returns:
            Liste von Integrations-Konfigurationen als Dictionaries
        """
        stmt = (
            select(IntegrationConfig)
            .where(IntegrationConfig.company_id == company_id)
            .order_by(IntegrationConfig.integration_type)
        )

        result = await self.session.execute(stmt)
        configs = result.scalars().all()

        integrations = []
        for cfg in configs:
            data = cfg.to_dict()
            # Nächsten Sync-Zeitpunkt berechnen (wenn aktiv und zuletzt synchronisiert)
            if cfg.is_active and cfg.last_sync_at:
                next_sync = cfg.last_sync_at + timedelta(
                    minutes=cfg.sync_interval_minutes
                )
                data["next_sync_at"] = next_sync.isoformat()
            else:
                data["next_sync_at"] = None
            integrations.append(data)

        logger.debug(
            "integration_sync_list_retrieved",
            company_id=str(company_id),
            count=len(integrations),
        )
        return integrations

    # =========================================================================
    # Sync-Verlauf
    # =========================================================================

    async def get_sync_history(
        self,
        company_id: UUID,
        integration_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Gibt den Sync-Verlauf eines Mandanten zurück.

        Args:
            company_id: Mandanten-ID
            integration_type: Optionaler Filter nach Integrations-Typ
            limit: Maximale Anzahl zurückgegebener Einträge (max. 200)

        Returns:
            Liste von Sync-Log-Einträgen, neueste zuerst

        Raises:
            ValueError: Wenn integration_type ungültig oder limit <= 0
        """
        if integration_type is not None and integration_type not in INTEGRATION_TYPES:
            raise ValueError(
                f"Ungültiger Integrations-Typ: '{integration_type}'. "
                f"Erlaubt: {', '.join(INTEGRATION_TYPES)}"
            )

        clamped_limit = min(max(1, limit), _MAX_HISTORY_LIMIT)

        # Korrektur: Inline-Subquery für Konfigurations-IDs des Mandanten
        config_filter_conditions = [IntegrationConfig.company_id == company_id]
        if integration_type:
            config_filter_conditions.append(
                IntegrationConfig.integration_type == integration_type
            )

        stmt = (
            select(IntegrationSyncLog)
            .where(
                and_(
                    IntegrationSyncLog.company_id == company_id,
                    IntegrationSyncLog.integration_config_id.in_(
                        select(IntegrationConfig.id).where(
                            and_(*config_filter_conditions)
                        )
                    ),
                )
            )
            .order_by(desc(IntegrationSyncLog.started_at))
            .limit(clamped_limit)
        )

        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        return [log.to_dict() for log in logs]

    # =========================================================================
    # Dashboard-Statistiken
    # =========================================================================

    async def get_dashboard_stats(self, company_id: UUID) -> Dict:
        """Aggregierte Dashboard-Statistiken für alle Integrationen eines Mandanten.

        Gibt eine Übersicht über aktive/fehlerhafte Integrationen,
        letzte Sync-Zeiten und Fehlerquoten zurück.

        Args:
            company_id: Mandanten-ID

        Returns:
            Dictionary mit Dashboard-Kennzahlen
        """
        # ----------------------------------------------------------------
        # Konfigurations-Aggregation
        # ----------------------------------------------------------------
        config_stats = await self.session.execute(
            select(
                func.count(IntegrationConfig.id).label("total"),
                func.sum(
                    case((IntegrationConfig.is_active.is_(True), 1), else_=0)
                ).label("active"),
                func.sum(
                    case(
                        (IntegrationConfig.last_sync_status == "error", 1),
                        else_=0,
                    )
                ).label("in_error"),
                func.sum(
                    case(
                        (IntegrationConfig.last_sync_status == "partial", 1),
                        else_=0,
                    )
                ).label("partial"),
                func.max(IntegrationConfig.last_sync_at).label("latest_sync"),
            ).where(IntegrationConfig.company_id == company_id)
        )
        row = config_stats.one()

        total: int = int(row.total or 0)
        active: int = int(row.active or 0)
        in_error: int = int(row.in_error or 0)
        partial: int = int(row.partial or 0)
        latest_sync_at = row.latest_sync

        # ----------------------------------------------------------------
        # Fehlerquote der letzten 24 Stunden
        # ----------------------------------------------------------------
        since = utc_now() - timedelta(hours=_HEALTH_WINDOW_HOURS)

        error_rate_result = await self.session.execute(
            select(
                func.count(IntegrationSyncLog.id).label("total_runs"),
                func.sum(
                    case(
                        (IntegrationSyncLog.status == "error", 1),
                        else_=0,
                    )
                ).label("error_runs"),
            ).where(
                and_(
                    IntegrationSyncLog.company_id == company_id,
                    IntegrationSyncLog.started_at >= since,
                )
            )
        )
        rate_row = error_rate_result.one()
        total_runs_24h: int = int(rate_row.total_runs or 0)
        error_runs_24h: int = int(rate_row.error_runs or 0)

        error_rate_24h: float = (
            round(error_runs_24h / total_runs_24h, 4)
            if total_runs_24h > 0
            else 0.0
        )

        # ----------------------------------------------------------------
        # Durchschnittliche Sync-Dauer der letzten 24 Stunden
        # ----------------------------------------------------------------
        avg_duration_result = await self.session.execute(
            select(
                func.avg(IntegrationSyncLog.duration_seconds).label("avg_duration"),
            ).where(
                and_(
                    IntegrationSyncLog.company_id == company_id,
                    IntegrationSyncLog.started_at >= since,
                    IntegrationSyncLog.status.in_(("success", "partial")),
                    IntegrationSyncLog.duration_seconds.is_not(None),
                )
            )
        )
        avg_duration_row = avg_duration_result.one()
        avg_duration: Optional[float] = (
            round(float(avg_duration_row.avg_duration), 2)
            if avg_duration_row.avg_duration is not None
            else None
        )

        return {
            "total_integrations": total,
            "active_integrations": active,
            "integrations_in_error": in_error,
            "integrations_partial": partial,
            "healthy_integrations": total - in_error - partial,
            "latest_sync_at": (
                latest_sync_at.isoformat() if latest_sync_at else None
            ),
            "error_rate_24h": error_rate_24h,
            "total_runs_24h": total_runs_24h,
            "error_runs_24h": error_runs_24h,
            "avg_sync_duration_seconds": avg_duration,
        }

    # =========================================================================
    # Manuellen Sync auslösen
    # =========================================================================

    async def trigger_sync(
        self,
        company_id: UUID,
        integration_type: str,
    ) -> Dict:
        """Löst einen manuellen Sync für eine bestimmte Integration aus.

        Sendet einen Celery-Task mit der Queue des jeweiligen Integrations-Typs.
        Erstellt dabei einen Sync-Log-Eintrag mit Status 'started'.

        Args:
            company_id: Mandanten-ID
            integration_type: Typ der Integration (datev, lexware, etc.)

        Returns:
            Dictionary mit task_id und Log-Eintrags-ID

        Raises:
            ValueError: Wenn Integration-Typ unbekannt oder nicht vorhanden
            RuntimeError: Wenn die Integration nicht aktiv ist
        """
        if integration_type not in INTEGRATION_TYPES:
            raise ValueError(
                f"Ungültiger Integrations-Typ: '{integration_type}'. "
                f"Erlaubt: {', '.join(INTEGRATION_TYPES)}"
            )

        # Konfiguration prüfen
        config = await self._get_config(company_id, integration_type)
        if config is None:
            raise ValueError(
                f"Keine Konfiguration für Integration '{integration_type}' "
                f"bei Mandant {company_id} gefunden."
            )
        if not config.is_active:
            raise RuntimeError(
                f"Integration '{integration_type}' ist deaktiviert. "
                "Bitte erst aktivieren, bevor ein manueller Sync ausgelöst wird."
            )

        # Sync-Log-Eintrag anlegen
        log_entry = IntegrationSyncLog(
            integration_config_id=config.id,
            company_id=company_id,
            sync_type="manual",
            status="started",
            started_at=utc_now(),
        )
        self.session.add(log_entry)
        await self.session.flush()  # ID generieren ohne commit

        log_id = str(log_entry.id)

        # Celery-Task senden
        task_name = _SYNC_TASK_MAP.get(integration_type)
        task_id: Optional[str] = None

        if task_name:
            try:
                from app.workers.celery_app import celery_app

                task = celery_app.send_task(
                    task_name,
                    kwargs={
                        "company_id": str(company_id),
                        "sync_log_id": log_id,
                        "triggered_by": "manual",
                    },
                )
                task_id = task.id
            except Exception as exc:
                logger.error(
                    "integration_sync_dispatch_failed",
                    integration_type=integration_type,
                    company_id=str(company_id),
                    **safe_error_log(exc),
                )
                # Log-Eintrag auf Fehler setzen
                log_entry.status = "error"
                log_entry.completed_at = utc_now()
                log_entry.error_details = {
                    "dispatch_error": "Celery-Task konnte nicht gesendet werden"
                }
                raise RuntimeError(
                    "Manueller Sync konnte nicht gestartet werden. "
                    "Bitte versuchen Sie es erneut."
                ) from exc

        logger.info(
            "integration_sync_triggered",
            integration_type=integration_type,
            company_id=str(company_id),
            log_id=log_id,
            task_id=task_id,
        )

        return {
            "sync_log_id": log_id,
            "task_id": task_id,
            "integration_type": integration_type,
            "status": "started",
            "message": (
                f"Manueller Sync für '{integration_type}' wurde gestartet."
            ),
        }

    # =========================================================================
    # Sync-Status aktualisieren (intern / von Celery-Tasks aufgerufen)
    # =========================================================================

    async def update_sync_status(
        self,
        config_id: UUID,
        status: str,
        items_processed: int = 0,
        items_failed: int = 0,
        items_total: int = 0,
        error: Optional[str] = None,
        error_details: Optional[Dict] = None,
        sync_log_id: Optional[UUID] = None,
    ) -> None:
        """Aktualisiert den Sync-Status nach Abschluss eines Sync-Laufs.

        Wird von Celery-Tasks nach Abschluss einer Synchronisation aufgerufen.
        Aktualisiert sowohl den Log-Eintrag als auch die denormalisierten
        Felder in IntegrationConfig.

        Args:
            config_id: ID der Integrations-Konfiguration
            status: Abschluss-Status (success, error, partial)
            items_processed: Anzahl erfolgreich verarbeiteter Datensätze
            items_failed: Anzahl fehlerhafter Datensätze
            items_total: Gesamtanzahl der Datensätze
            error: Optionale kurze Fehlerbeschreibung (für IntegrationConfig)
            error_details: Optionale strukturierte Fehlerdetails (für Log)
            sync_log_id: ID des zugehörigen Log-Eintrags (wenn vorhanden)
        """
        if status not in SYNC_LOG_STATUS_VALUES:
            raise ValueError(
                f"Ungültiger Status: '{status}'. "
                f"Erlaubt: {', '.join(SYNC_LOG_STATUS_VALUES)}"
            )

        now = utc_now()

        # IntegrationConfig aktualisieren (denormalisierter Status)
        await self.session.execute(
            update(IntegrationConfig)
            .where(IntegrationConfig.id == config_id)
            .values(
                last_sync_at=now,
                last_sync_status=status if status != "started" else None,
                last_error_message=error if status == "error" else None,
                updated_at=now,
            )
        )

        # Log-Eintrag abschließen (falls vorhanden)
        if sync_log_id:
            # Dauer berechnen
            log_result = await self.session.execute(
                select(IntegrationSyncLog.started_at).where(
                    IntegrationSyncLog.id == sync_log_id
                )
            )
            log_row = log_result.one_or_none()
            duration: Optional[float] = None
            if log_row and log_row.started_at:
                delta = now - log_row.started_at
                duration = round(delta.total_seconds(), 3)

            await self.session.execute(
                update(IntegrationSyncLog)
                .where(IntegrationSyncLog.id == sync_log_id)
                .values(
                    status=status,
                    items_processed=items_processed,
                    items_failed=items_failed,
                    items_total=items_total,
                    error_details=error_details or {},
                    completed_at=now,
                    duration_seconds=duration,
                )
            )

        logger.info(
            "integration_sync_status_updated",
            config_id=str(config_id),
            status=status,
            items_processed=items_processed,
            items_failed=items_failed,
        )

    # =========================================================================
    # Konfiguration aktualisieren
    # =========================================================================

    async def update_config(
        self,
        company_id: UUID,
        integration_type: str,
        is_active: Optional[bool] = None,
        sync_interval_minutes: Optional[int] = None,
        display_name: Optional[str] = None,
        config: Optional[Dict] = None,
    ) -> Dict:
        """Aktualisiert die Konfiguration einer Integration.

        Args:
            company_id: Mandanten-ID
            integration_type: Typ der zu aktualisierenden Integration
            is_active: Aktivierungs-Status (None = unverändert)
            sync_interval_minutes: Sync-Intervall in Minuten (min. 1, None = unverändert)
            display_name: Anzeigename (None = unverändert)
            config: Konfigurationsdaten (None = unverändert)

        Returns:
            Aktualisierte Konfiguration als Dictionary

        Raises:
            ValueError: Wenn Integration nicht gefunden oder Werte ungültig
        """
        if integration_type not in INTEGRATION_TYPES:
            raise ValueError(
                f"Ungültiger Integrations-Typ: '{integration_type}'."
            )

        cfg = await self._get_config(company_id, integration_type)
        if cfg is None:
            raise ValueError(
                f"Keine Konfiguration für '{integration_type}' gefunden."
            )

        updates: Dict = {"updated_at": utc_now()}

        if is_active is not None:
            updates["is_active"] = is_active

        if sync_interval_minutes is not None:
            if sync_interval_minutes < 1:
                raise ValueError(
                    "sync_interval_minutes muss mindestens 1 betragen."
                )
            updates["sync_interval_minutes"] = sync_interval_minutes

        if display_name is not None:
            display_name_stripped = display_name.strip()
            if not display_name_stripped:
                raise ValueError("display_name darf nicht leer sein.")
            updates["display_name"] = display_name_stripped

        if config is not None:
            updates["config"] = config

        await self.session.execute(
            update(IntegrationConfig)
            .where(
                and_(
                    IntegrationConfig.id == cfg.id,
                    IntegrationConfig.company_id == company_id,
                )
            )
            .values(**updates)
        )

        # Aktualisierte Konfiguration laden
        await self.session.refresh(cfg)

        logger.info(
            "integration_config_updated",
            integration_type=integration_type,
            company_id=str(company_id),
            updated_fields=list(updates.keys()),
        )

        return cfg.to_dict()

    # =========================================================================
    # Health-Status
    # =========================================================================

    async def get_health_status(self, company_id: UUID) -> List[Dict]:
        """Gibt den Health-Status jeder Integration zurück.

        Berechnet pro Integration eine Gesundheitsbewertung basierend auf:
        - Letztem Sync-Status
        - Fehlerquote der letzten 24 Stunden
        - Zeitspanne seit letzter Synchronisation

        Args:
            company_id: Mandanten-ID

        Returns:
            Liste von Health-Status-Objekten pro Integration
        """
        since = utc_now() - timedelta(hours=_HEALTH_WINDOW_HOURS)

        # Alle Konfigurationen des Mandanten laden
        configs_result = await self.session.execute(
            select(IntegrationConfig)
            .where(IntegrationConfig.company_id == company_id)
            .order_by(IntegrationConfig.integration_type)
        )
        configs = configs_result.scalars().all()

        if not configs:
            return []

        config_ids = [cfg.id for cfg in configs]

        # Fehlerquoten für alle Konfigurationen in einer Abfrage ermitteln
        error_stats = await self.session.execute(
            select(
                IntegrationSyncLog.integration_config_id,
                func.count(IntegrationSyncLog.id).label("total"),
                func.sum(
                    case(
                        (IntegrationSyncLog.status == "error", 1),
                        else_=0,
                    )
                ).label("errors"),
                func.avg(IntegrationSyncLog.duration_seconds).label("avg_duration"),
            )
            .where(
                and_(
                    IntegrationSyncLog.integration_config_id.in_(config_ids),
                    IntegrationSyncLog.started_at >= since,
                )
            )
            .group_by(IntegrationSyncLog.integration_config_id)
        )

        # Ergebnis indizieren
        stats_by_config: Dict[UUID, Dict] = {}
        for stat_row in error_stats:
            total = int(stat_row.total or 0)
            errors = int(stat_row.errors or 0)
            avg_dur = stat_row.avg_duration
            stats_by_config[stat_row.integration_config_id] = {
                "total_runs_24h": total,
                "error_runs_24h": errors,
                "error_rate_24h": round(errors / total, 4) if total > 0 else 0.0,
                "avg_duration_seconds": (
                    round(float(avg_dur), 2) if avg_dur is not None else None
                ),
            }

        # Health-Status pro Integration berechnen
        health_list = []
        now = utc_now()

        for cfg in configs:
            stats = stats_by_config.get(cfg.id, {
                "total_runs_24h": 0,
                "error_runs_24h": 0,
                "error_rate_24h": 0.0,
                "avg_duration_seconds": None,
            })

            health = _compute_health_level(
                is_active=cfg.is_active,
                last_sync_status=cfg.last_sync_status,
                last_sync_at=cfg.last_sync_at,
                sync_interval_minutes=cfg.sync_interval_minutes,
                error_rate_24h=stats["error_rate_24h"],
                now=now,
            )

            # Minuten seit letztem Sync berechnen
            minutes_since_sync: Optional[float] = None
            if cfg.last_sync_at:
                delta = now - cfg.last_sync_at
                minutes_since_sync = round(delta.total_seconds() / 60, 1)

            health_list.append({
                "integration_type": cfg.integration_type,
                "display_name": cfg.display_name,
                "is_active": cfg.is_active,
                "health_level": health,
                "last_sync_at": (
                    cfg.last_sync_at.isoformat() if cfg.last_sync_at else None
                ),
                "last_sync_status": cfg.last_sync_status,
                "minutes_since_last_sync": minutes_since_sync,
                "sync_interval_minutes": cfg.sync_interval_minutes,
                **stats,
            })

        return health_list

    # =========================================================================
    # Interne Hilfsmethoden
    # =========================================================================

    async def _get_config(
        self,
        company_id: UUID,
        integration_type: str,
    ) -> Optional[IntegrationConfig]:
        """Lädt eine Integrations-Konfiguration.

        Args:
            company_id: Mandanten-ID
            integration_type: Integrations-Typ

        Returns:
            IntegrationConfig oder None wenn nicht gefunden
        """
        result = await self.session.execute(
            select(IntegrationConfig).where(
                and_(
                    IntegrationConfig.company_id == company_id,
                    IntegrationConfig.integration_type == integration_type,
                )
            )
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Health-Level-Berechnung (pure function, testbar)
# ---------------------------------------------------------------------------


def _compute_health_level(
    is_active: bool,
    last_sync_status: Optional[str],
    last_sync_at,
    sync_interval_minutes: int,
    error_rate_24h: float,
    now,
) -> str:
    """Berechnet einen Health-Level-String für eine Integration.

    Levels:
    - healthy: Aktiv, letzter Sync erfolgreich, keine Fehler
    - warning: Letzte Synchronisation überfällig oder partielle Fehler
    - error: Letzter Sync fehlgeschlagen oder hohe Fehlerquote
    - inactive: Integration deaktiviert

    Args:
        is_active: Ob die Integration aktiv ist
        last_sync_status: Status der letzten Synchronisation
        last_sync_at: Zeitpunkt der letzten Synchronisation
        sync_interval_minutes: Konfiguriertes Sync-Intervall
        error_rate_24h: Fehlerquote der letzten 24 Stunden (0.0 - 1.0)
        now: Aktueller Zeitpunkt

    Returns:
        Health-Level: 'healthy' | 'warning' | 'error' | 'inactive'
    """
    if not is_active:
        return "inactive"

    # Fehlerhafter letzter Sync
    if last_sync_status == "error":
        return "error"

    # Hohe Fehlerquote (über 50 %)
    if error_rate_24h > 0.5:
        return "error"

    # Noch nie synchronisiert
    if last_sync_at is None:
        return "warning"

    # Überprüfung: Ist der Sync überfällig? (2× Intervall als Toleranz)
    overdue_threshold = timedelta(minutes=sync_interval_minutes * 2)
    if (now - last_sync_at) > overdue_threshold:
        return "warning"

    # Partieller Sync oder leicht erhöhte Fehlerquote
    if last_sync_status == "partial" or error_rate_24h > 0.1:
        return "warning"

    return "healthy"


# ---------------------------------------------------------------------------
# Factory / Dependency-Injection Hilfsfunktion
# ---------------------------------------------------------------------------


def get_integration_sync_service(session: AsyncSession) -> IntegrationSyncService:
    """Factory-Funktion für FastAPI Dependency Injection.

    Args:
        session: Async-Datenbank-Session (via Depends(get_db))

    Returns:
        IntegrationSyncService-Instanz
    """
    return IntegrationSyncService(session)
