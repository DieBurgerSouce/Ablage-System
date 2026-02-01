# -*- coding: utf-8 -*-
"""SLA Monitoring Service fuer BPMN Workflows.

Enterprise-Grade SLA Tracking mit:
- Definition von SLAs pro Workflow-Typ
- Progressives Alert-System (50%, 75%, 90%, 100%)
- Eskalation bei Ueberschreitung
- SLA-Metriken und Reporting

Migration: 150_add_workflow_sla_monitoring.py
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID
import structlog

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.bpmn_models.bpmn import (
    ProcessInstance,
    ProcessDefinition,
    ProcessHistory,
    ProcessStatus,
)
from app.services.alert_center_service import (
    AlertCenterService,
    AlertCodes,
    get_alert_center_service,
)
from app.db.models_alert import AlertCategory, AlertSeverity

logger = structlog.get_logger(__name__)


# =============================================================================
# SLA Enums and Constants
# =============================================================================

class SLAStatus(str, Enum):
    """SLA tracking status."""
    ON_TRACK = "on_track"          # Innerhalb der Zeit
    WARNING = "warning"            # 50-75% der Zeit verbraucht
    AT_RISK = "at_risk"            # 75-90% der Zeit verbraucht
    CRITICAL = "critical"          # 90-100% der Zeit verbraucht
    BREACHED = "breached"          # SLA ueberschritten


class SLAAlertThreshold(str, Enum):
    """SLA Alert threshold levels."""
    INFO_50 = "info_50"            # 50% Zeit verbraucht
    WARNING_75 = "warning_75"      # 75% Zeit verbraucht
    HIGH_90 = "high_90"            # 90% Zeit verbraucht
    CRITICAL_100 = "critical_100"  # SLA ueberschritten


# Alert Code Extensions fuer SLA
class SLAAlertCodes:
    """SLA-spezifische Alert-Codes."""
    SLA_INFO_50 = "SLA_001"
    SLA_WARNING_75 = "SLA_002"
    SLA_HIGH_90 = "SLA_003"
    SLA_BREACHED = "SLA_004"
    SLA_AUTO_ESCALATED = "SLA_005"


# =============================================================================
# SLA Service
# =============================================================================

class SLAService:
    """Service fuer SLA Monitoring und Tracking.

    Verwaltet SLA-Definitionen und ueberwacht Workflow-Instanzen
    auf Einhaltung der definierten Zeitlimits.
    """

    # Default SLA-Konfigurationen (in Stunden)
    DEFAULT_SLAS: Dict[str, int] = {
        "invoice-approval": 24,          # 24h fuer Rechnungsfreigabe
        "document-review": 48,            # 48h fuer Dokumentenpruefung
        "contract-approval": 72,          # 72h fuer Vertragsfreigabe
        "expense-claim": 24,              # 24h fuer Spesenabrechnung
        "leave-request": 8,               # 8h fuer Urlaubsantrag
        "purchase-order": 24,             # 24h fuer Bestellung
        "vendor-onboarding": 168,         # 7 Tage fuer Lieferanten-Onboarding
        "default": 48,                    # Default: 48h
    }

    # Alert Thresholds (Prozent der Zeit verbraucht)
    ALERT_THRESHOLDS = [
        (0.50, SLAAlertThreshold.INFO_50, AlertSeverity.INFO),
        (0.75, SLAAlertThreshold.WARNING_75, AlertSeverity.MEDIUM),
        (0.90, SLAAlertThreshold.HIGH_90, AlertSeverity.HIGH),
        (1.00, SLAAlertThreshold.CRITICAL_100, AlertSeverity.CRITICAL),
    ]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize SLA service."""
        self.session = session
        self._alert_service: Optional[AlertCenterService] = None

    @property
    def alert_service(self) -> AlertCenterService:
        """Lazy-load alert service."""
        if self._alert_service is None:
            self._alert_service = get_alert_center_service(self.session)
        return self._alert_service

    # =========================================================================
    # SLA Definition
    # =========================================================================

    async def define_sla(
        self,
        workflow_type: str,
        max_duration_hours: int,
        company_id: UUID,
        description: Optional[str] = None,
        escalation_user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Definiert SLA fuer einen Workflow-Typ.

        Args:
            workflow_type: Key der Prozess-Definition
            max_duration_hours: Maximale Dauer in Stunden
            company_id: Mandant
            description: Optionale Beschreibung
            escalation_user_id: User fuer Eskalation

        Returns:
            SLA-Definition als Dictionary
        """
        # Validierung
        if max_duration_hours <= 0:
            raise ValueError("SLA-Dauer muss groesser als 0 sein")

        if max_duration_hours > 720:  # Max 30 Tage
            raise ValueError("SLA-Dauer darf maximal 720 Stunden (30 Tage) betragen")

        # Prozess-Definition pruefen
        definition = await self._get_definition_by_key(workflow_type, company_id)
        if not definition:
            raise ValueError(f"Prozess-Definition '{workflow_type}' nicht gefunden")

        # SLA in Definition speichern (als JSONB-Erweiterung)
        current_data = dict(definition.process_data)
        current_data["sla_config"] = {
            "max_duration_hours": max_duration_hours,
            "description": description,
            "escalation_user_id": str(escalation_user_id) if escalation_user_id else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        definition.process_data = current_data

        await self.session.flush()

        logger.info(
            "sla_defined",
            workflow_type=workflow_type,
            max_duration_hours=max_duration_hours,
            company_id=str(company_id),
        )

        return {
            "workflow_type": workflow_type,
            "max_duration_hours": max_duration_hours,
            "description": description,
            "escalation_user_id": str(escalation_user_id) if escalation_user_id else None,
        }

    async def get_sla_definition(
        self,
        workflow_type: str,
        company_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Gibt SLA-Definition fuer einen Workflow-Typ zurueck.

        Args:
            workflow_type: Key der Prozess-Definition
            company_id: Mandant

        Returns:
            SLA-Definition oder None
        """
        definition = await self._get_definition_by_key(workflow_type, company_id)
        if not definition:
            return None

        process_data = definition.process_data or {}
        sla_config = process_data.get("sla_config")

        if sla_config:
            return {
                "workflow_type": workflow_type,
                "max_duration_hours": sla_config.get("max_duration_hours"),
                "description": sla_config.get("description"),
                "escalation_user_id": sla_config.get("escalation_user_id"),
            }

        # Default SLA zurueckgeben
        default_hours = self.DEFAULT_SLAS.get(workflow_type, self.DEFAULT_SLAS["default"])
        return {
            "workflow_type": workflow_type,
            "max_duration_hours": default_hours,
            "description": f"Standard-SLA ({default_hours}h)",
            "escalation_user_id": None,
            "is_default": True,
        }

    # =========================================================================
    # SLA Tracking
    # =========================================================================

    async def start_sla_tracking(
        self,
        workflow_instance_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Startet SLA-Tracking fuer eine Workflow-Instanz.

        Wird automatisch beim Start eines Workflows aufgerufen.

        Args:
            workflow_instance_id: Instanz-ID
            company_id: Mandant

        Returns:
            SLA-Tracking-Info
        """
        instance = await self._get_instance(workflow_instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        # Definition laden fuer SLA-Konfiguration
        definition = await self._get_definition_by_id(instance.definition_id)
        if not definition:
            raise ValueError("Prozess-Definition nicht gefunden")

        # SLA-Dauer ermitteln
        process_data = definition.process_data or {}
        sla_config = process_data.get("sla_config", {})
        max_hours = sla_config.get(
            "max_duration_hours",
            self.DEFAULT_SLAS.get(definition.key, self.DEFAULT_SLAS["default"])
        )

        # SLA-Deadline berechnen
        start_time = instance.started_at or datetime.now(timezone.utc)
        deadline = start_time + timedelta(hours=max_hours)

        # SLA-Tracking in Instanz-Variablen speichern
        current_vars = dict(instance.variables)
        current_vars["_sla"] = {
            "start_time": start_time.isoformat(),
            "deadline": deadline.isoformat(),
            "max_duration_hours": max_hours,
            "alerts_sent": [],
            "status": SLAStatus.ON_TRACK.value,
        }
        instance.variables = current_vars

        await self.session.flush()

        logger.info(
            "sla_tracking_started",
            instance_id=str(workflow_instance_id),
            deadline=deadline.isoformat(),
            max_hours=max_hours,
        )

        return {
            "instance_id": str(workflow_instance_id),
            "start_time": start_time.isoformat(),
            "deadline": deadline.isoformat(),
            "max_duration_hours": max_hours,
            "status": SLAStatus.ON_TRACK.value,
        }

    async def check_sla_status(
        self,
        workflow_instance_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Prueft aktuellen SLA-Status einer Instanz.

        Args:
            workflow_instance_id: Instanz-ID
            company_id: Mandant

        Returns:
            Aktueller SLA-Status mit Details
        """
        instance = await self._get_instance(workflow_instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        sla_data = (instance.variables or {}).get("_sla")
        if not sla_data:
            return {
                "instance_id": str(workflow_instance_id),
                "has_sla": False,
                "message": "Keine SLA-Konfiguration fuer diese Instanz",
            }

        now = datetime.now(timezone.utc)
        start_time = datetime.fromisoformat(sla_data["start_time"])
        deadline = datetime.fromisoformat(sla_data["deadline"])
        max_hours = sla_data["max_duration_hours"]

        # Prozess bereits beendet?
        if instance.status in (ProcessStatus.COMPLETED, ProcessStatus.TERMINATED):
            end_time = instance.ended_at or now
            duration_hours = (end_time - start_time).total_seconds() / 3600
            was_on_time = end_time <= deadline

            return {
                "instance_id": str(workflow_instance_id),
                "has_sla": True,
                "status": SLAStatus.ON_TRACK.value if was_on_time else SLAStatus.BREACHED.value,
                "start_time": start_time.isoformat(),
                "deadline": deadline.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_hours": round(duration_hours, 2),
                "max_duration_hours": max_hours,
                "completed": True,
                "on_time": was_on_time,
            }

        # Laufender Prozess
        elapsed = now - start_time
        total_allowed = deadline - start_time
        elapsed_percent = elapsed.total_seconds() / total_allowed.total_seconds()
        remaining_hours = (deadline - now).total_seconds() / 3600

        # Status ermitteln
        if now > deadline:
            status = SLAStatus.BREACHED
        elif elapsed_percent >= 0.90:
            status = SLAStatus.CRITICAL
        elif elapsed_percent >= 0.75:
            status = SLAStatus.AT_RISK
        elif elapsed_percent >= 0.50:
            status = SLAStatus.WARNING
        else:
            status = SLAStatus.ON_TRACK

        return {
            "instance_id": str(workflow_instance_id),
            "has_sla": True,
            "status": status.value,
            "start_time": start_time.isoformat(),
            "deadline": deadline.isoformat(),
            "max_duration_hours": max_hours,
            "elapsed_hours": round(elapsed.total_seconds() / 3600, 2),
            "elapsed_percent": round(elapsed_percent * 100, 1),
            "remaining_hours": max(0, round(remaining_hours, 2)),
            "completed": False,
            "alerts_sent": sla_data.get("alerts_sent", []),
        }

    async def check_all_slas(
        self,
        company_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Prueft SLA-Status aller laufenden Workflows.

        Wird periodisch von Celery Beat aufgerufen.

        Args:
            company_id: Optional: Nur fuer diese Firma

        Returns:
            Zusammenfassung der Pruefung
        """
        # Alle laufenden Instanzen laden
        conditions = [ProcessInstance.status == ProcessStatus.RUNNING]
        if company_id:
            conditions.append(ProcessInstance.company_id == company_id)

        query = (
            select(ProcessInstance)
            .where(and_(*conditions))
            .options(selectinload(ProcessInstance.definition))
        )

        result = await self.session.execute(query)
        instances = list(result.scalars().all())

        stats = {
            "checked": 0,
            "on_track": 0,
            "warning": 0,
            "at_risk": 0,
            "critical": 0,
            "breached": 0,
            "alerts_sent": 0,
        }

        for instance in instances:
            sla_data = (instance.variables or {}).get("_sla")
            if not sla_data:
                continue

            stats["checked"] += 1

            try:
                status_result = await self.check_sla_status(
                    instance.id,
                    instance.company_id
                )

                status = status_result.get("status")
                if status == SLAStatus.ON_TRACK.value:
                    stats["on_track"] += 1
                elif status == SLAStatus.WARNING.value:
                    stats["warning"] += 1
                elif status == SLAStatus.AT_RISK.value:
                    stats["at_risk"] += 1
                elif status == SLAStatus.CRITICAL.value:
                    stats["critical"] += 1
                elif status == SLAStatus.BREACHED.value:
                    stats["breached"] += 1

                # Alerts pruefen und senden
                alerts_sent = await self._check_and_send_alerts(
                    instance,
                    sla_data,
                    status_result
                )
                stats["alerts_sent"] += alerts_sent

            except Exception as e:
                logger.warning(
                    "sla_check_failed",
                    instance_id=str(instance.id),
                    error=str(e),
                )

        logger.info(
            "sla_check_completed",
            company_id=str(company_id) if company_id else "all",
            **stats,
        )

        return stats

    # =========================================================================
    # SLA Breaches and Metrics
    # =========================================================================

    async def get_sla_breaches(
        self,
        company_id: UUID,
        time_range_days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Gibt alle SLA-Verletzungen im Zeitraum zurueck.

        Args:
            company_id: Mandant
            time_range_days: Zeitraum in Tagen
            limit: Max. Anzahl Ergebnisse

        Returns:
            Liste der SLA-Verletzungen
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

        # Beendete Instanzen mit SLA-Verletzung suchen
        query = (
            select(ProcessInstance)
            .join(ProcessDefinition)
            .where(
                and_(
                    ProcessInstance.company_id == company_id,
                    ProcessInstance.status.in_([
                        ProcessStatus.COMPLETED,
                        ProcessStatus.TERMINATED
                    ]),
                    ProcessInstance.ended_at >= start_date,
                )
            )
            .order_by(ProcessInstance.ended_at.desc())
            .limit(limit * 2)  # Mehr laden, dann filtern
        )

        result = await self.session.execute(query)
        instances = list(result.scalars().all())

        breaches = []
        for instance in instances:
            sla_data = (instance.variables or {}).get("_sla")
            if not sla_data:
                continue

            deadline = datetime.fromisoformat(sla_data["deadline"])
            end_time = instance.ended_at

            if end_time and end_time > deadline:
                start_time = datetime.fromisoformat(sla_data["start_time"])
                duration = (end_time - start_time).total_seconds() / 3600
                breach_by = (end_time - deadline).total_seconds() / 3600

                breaches.append({
                    "instance_id": str(instance.id),
                    "business_key": instance.business_key,
                    "workflow_key": instance.definition.key if instance.definition else None,
                    "workflow_name": instance.definition.name if instance.definition else None,
                    "start_time": start_time.isoformat(),
                    "deadline": deadline.isoformat(),
                    "end_time": end_time.isoformat(),
                    "max_duration_hours": sla_data["max_duration_hours"],
                    "actual_duration_hours": round(duration, 2),
                    "breach_by_hours": round(breach_by, 2),
                })

            if len(breaches) >= limit:
                break

        return breaches

    async def calculate_sla_metrics(
        self,
        company_id: UUID,
        time_range_days: int = 30,
    ) -> Dict[str, Any]:
        """Berechnet SLA-Performance-Metriken.

        Args:
            company_id: Mandant
            time_range_days: Zeitraum in Tagen

        Returns:
            SLA-Metriken
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

        # Alle beendeten Instanzen im Zeitraum
        query = (
            select(ProcessInstance)
            .join(ProcessDefinition)
            .where(
                and_(
                    ProcessInstance.company_id == company_id,
                    ProcessInstance.status.in_([
                        ProcessStatus.COMPLETED,
                        ProcessStatus.TERMINATED
                    ]),
                    ProcessInstance.ended_at >= start_date,
                )
            )
        )

        result = await self.session.execute(query)
        instances = list(result.scalars().all())

        total_with_sla = 0
        on_time = 0
        breached = 0
        total_duration = 0.0
        by_workflow: Dict[str, Dict[str, Any]] = {}

        for instance in instances:
            sla_data = (instance.variables or {}).get("_sla")
            if not sla_data:
                continue

            total_with_sla += 1

            deadline = datetime.fromisoformat(sla_data["deadline"])
            start_time = datetime.fromisoformat(sla_data["start_time"])
            end_time = instance.ended_at or datetime.now(timezone.utc)

            duration = (end_time - start_time).total_seconds() / 3600
            total_duration += duration

            was_on_time = end_time <= deadline
            if was_on_time:
                on_time += 1
            else:
                breached += 1

            # Per-Workflow Statistiken
            workflow_key = instance.definition.key if instance.definition else "unknown"
            if workflow_key not in by_workflow:
                by_workflow[workflow_key] = {
                    "total": 0,
                    "on_time": 0,
                    "breached": 0,
                    "total_duration": 0.0,
                }

            by_workflow[workflow_key]["total"] += 1
            by_workflow[workflow_key]["total_duration"] += duration
            if was_on_time:
                by_workflow[workflow_key]["on_time"] += 1
            else:
                by_workflow[workflow_key]["breached"] += 1

        # Prozentsaetze berechnen
        compliance_rate = (on_time / total_with_sla * 100) if total_with_sla > 0 else 100.0
        avg_duration = (total_duration / total_with_sla) if total_with_sla > 0 else 0.0

        # Per-Workflow Prozentsaetze
        for key, stats in by_workflow.items():
            stats["compliance_rate"] = (
                stats["on_time"] / stats["total"] * 100
            ) if stats["total"] > 0 else 100.0
            stats["avg_duration_hours"] = (
                stats["total_duration"] / stats["total"]
            ) if stats["total"] > 0 else 0.0

        return {
            "time_range_days": time_range_days,
            "total_workflows": total_with_sla,
            "on_time": on_time,
            "breached": breached,
            "compliance_rate": round(compliance_rate, 2),
            "avg_duration_hours": round(avg_duration, 2),
            "by_workflow": by_workflow,
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _check_and_send_alerts(
        self,
        instance: ProcessInstance,
        sla_data: Dict[str, Any],
        status_result: Dict[str, Any],
    ) -> int:
        """Prueft und sendet SLA-Alerts.

        Returns:
            Anzahl gesendeter Alerts
        """
        alerts_sent_list: List[str] = sla_data.get("alerts_sent", [])
        elapsed_percent = status_result.get("elapsed_percent", 0) / 100
        alerts_sent = 0

        for threshold, alert_type, severity in self.ALERT_THRESHOLDS:
            if elapsed_percent >= threshold and alert_type.value not in alerts_sent_list:
                # Alert senden
                await self._send_sla_alert(
                    instance,
                    alert_type,
                    severity,
                    status_result,
                )
                alerts_sent_list.append(alert_type.value)
                alerts_sent += 1

                # Bei 100% automatisch eskalieren
                if threshold >= 1.0:
                    await self._auto_escalate(instance, status_result)

        # Alerts in Instanz aktualisieren
        if alerts_sent > 0:
            current_vars = dict(instance.variables)
            current_vars["_sla"]["alerts_sent"] = alerts_sent_list
            current_vars["_sla"]["status"] = status_result.get("status")
            instance.variables = current_vars
            await self.session.flush()

        return alerts_sent

    async def _send_sla_alert(
        self,
        instance: ProcessInstance,
        alert_type: SLAAlertThreshold,
        severity: AlertSeverity,
        status_result: Dict[str, Any],
    ) -> None:
        """Sendet einen SLA-Alert."""
        alert_codes = {
            SLAAlertThreshold.INFO_50: SLAAlertCodes.SLA_INFO_50,
            SLAAlertThreshold.WARNING_75: SLAAlertCodes.SLA_WARNING_75,
            SLAAlertThreshold.HIGH_90: SLAAlertCodes.SLA_HIGH_90,
            SLAAlertThreshold.CRITICAL_100: SLAAlertCodes.SLA_BREACHED,
        }

        titles = {
            SLAAlertThreshold.INFO_50: "SLA-Warnung: 50% der Zeit verbraucht",
            SLAAlertThreshold.WARNING_75: "SLA-Warnung: 75% der Zeit verbraucht",
            SLAAlertThreshold.HIGH_90: "SLA-Kritisch: 90% der Zeit verbraucht",
            SLAAlertThreshold.CRITICAL_100: "SLA-Verletzung: Zeitlimit ueberschritten",
        }

        remaining = status_result.get("remaining_hours", 0)
        elapsed = status_result.get("elapsed_percent", 0)

        message = (
            f"Workflow '{instance.business_key or instance.id}' hat "
            f"{elapsed:.1f}% der SLA-Zeit verbraucht. "
            f"Verbleibend: {remaining:.1f} Stunden."
        )

        await self.alert_service.create_alert(
            company_id=instance.company_id,
            alert_code=alert_codes.get(alert_type, SLAAlertCodes.SLA_WARNING_75),
            category=AlertCategory.WORKFLOW,
            severity=severity,
            title=titles.get(alert_type, "SLA-Warnung"),
            message=message,
            source_type="sla_monitoring",
            source_id=str(instance.id),
            metadata={
                "instance_id": str(instance.id),
                "business_key": instance.business_key,
                "elapsed_percent": elapsed,
                "remaining_hours": remaining,
                "deadline": status_result.get("deadline"),
            },
            available_actions=["acknowledge", "escalate", "dismiss"],
            recurrence_key=f"sla_{instance.id}_{alert_type.value}",
        )

        logger.info(
            "sla_alert_sent",
            instance_id=str(instance.id),
            alert_type=alert_type.value,
            severity=severity.value,
        )

    async def _auto_escalate(
        self,
        instance: ProcessInstance,
        status_result: Dict[str, Any],
    ) -> None:
        """Eskaliert automatisch bei SLA-Verletzung."""
        # Eskalations-User aus Definition holen
        definition = await self._get_definition_by_id(instance.definition_id)
        if not definition:
            return

        sla_config = (definition.process_data or {}).get("sla_config", {})
        escalation_user_id = sla_config.get("escalation_user_id")

        # History-Eintrag
        history = ProcessHistory(
            instance_id=instance.id,
            event_type="SLA_BREACHED",
            message="SLA-Zeitlimit ueberschritten - automatische Eskalation",
            actor_type="system",
            company_id=instance.company_id,
        )
        self.session.add(history)

        # Alert fuer Eskalation
        await self.alert_service.create_alert(
            company_id=instance.company_id,
            alert_code=SLAAlertCodes.SLA_AUTO_ESCALATED,
            category=AlertCategory.WORKFLOW,
            severity=AlertSeverity.CRITICAL,
            title="SLA-Eskalation: Automatische Weiterleitung",
            message=(
                f"Workflow '{instance.business_key or instance.id}' wurde wegen "
                f"SLA-Verletzung automatisch eskaliert."
            ),
            source_type="sla_monitoring",
            source_id=str(instance.id),
            assigned_to_id=UUID(escalation_user_id) if escalation_user_id else None,
            metadata={
                "instance_id": str(instance.id),
                "business_key": instance.business_key,
                "deadline": status_result.get("deadline"),
                "auto_escalated": True,
            },
            available_actions=["acknowledge", "resolve"],
            send_email=True,
        )

        logger.warning(
            "sla_auto_escalated",
            instance_id=str(instance.id),
            escalation_user_id=escalation_user_id,
        )

    async def _get_instance(
        self,
        instance_id: UUID,
        company_id: UUID,
    ) -> Optional[ProcessInstance]:
        """Laedt Prozess-Instanz."""
        query = select(ProcessInstance).where(
            and_(
                ProcessInstance.id == instance_id,
                ProcessInstance.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _get_definition_by_key(
        self,
        key: str,
        company_id: UUID,
    ) -> Optional[ProcessDefinition]:
        """Laedt aktive Definition nach Key."""
        query = select(ProcessDefinition).where(
            and_(
                ProcessDefinition.key == key,
                ProcessDefinition.company_id == company_id,
                ProcessDefinition.is_active == True,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _get_definition_by_id(
        self,
        definition_id: UUID,
    ) -> Optional[ProcessDefinition]:
        """Laedt Definition nach ID."""
        query = select(ProcessDefinition).where(
            ProcessDefinition.id == definition_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


# =============================================================================
# Factory Function
# =============================================================================

def get_sla_service(session: AsyncSession) -> SLAService:
    """Factory function for SLAService."""
    return SLAService(session)
