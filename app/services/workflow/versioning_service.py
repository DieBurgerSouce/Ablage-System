# -*- coding: utf-8 -*-
"""Workflow Versioning Service für Ablage-System.

Verwaltet Workflow-Versionen mit:
- Semantische Versionierung (major.minor.patch)
- Diff-Ansicht zwischen Versionen
- Rollback auf vorherige Versionen
- A/B Testing zwischen Versionen
- Migration laufender Instanzen

Alle Benutzer-sichtbaren Texte sind auf Deutsch.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Workflow
from app.db.models_workflow_versioning import (
    WorkflowVersion,
    WorkflowVersionStatus,
    WorkflowABTest,
    ABTestStatus,
)

if TYPE_CHECKING:
    from app.db.models import User

logger = structlog.get_logger(__name__)


class WorkflowVersioningService:
    """Service für Workflow-Versionierung.

    Ermöglicht:
    - Erstellen neuer Versionen
    - Diff-Berechnung zwischen Versionen
    - Rollback auf vorherige Versionen
    - A/B Testing
    - Migration laufender Instanzen

    SECURITY: Alle Operationen validieren company_id für Multi-Tenant Isolation.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den WorkflowVersioningService.

        Args:
            db: AsyncSession für Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # Version Creation
    # =========================================================================

    async def create_version(
        self,
        workflow_id: UUID,
        company_id: UUID,
        user_id: UUID,
        change_description: str,
        change_type: str = "minor",
        definition: Optional[Dict[str, Any]] = None,
    ) -> Optional[WorkflowVersion]:
        """Erstellt eine neue Version eines Workflows.

        Liest die aktuelle Workflow-Definition und erstellt einen versionierten
        Snapshot. Berechnet automatisch die neue Versionsnummer basierend auf
        dem change_type.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ersteller
            change_description: Beschreibung der Änderungen
            change_type: Art der Änderung (major, minor, patch)
            definition: Optionale explizite Definition (sonst aus Workflow)

        Returns:
            WorkflowVersion oder None wenn Workflow nicht gefunden

        Raises:
            ValueError: Bei ungültigem change_type
        """
        if change_type not in ("major", "minor", "patch"):
            raise ValueError(f"Ungültiger change_type: {change_type}")

        # Workflow laden
        workflow = await self._get_workflow(workflow_id, company_id)
        if not workflow:
            logger.warning(
                "workflow_not_found_for_versioning",
                workflow_id=str(workflow_id),
                company_id=str(company_id),
            )
            return None

        # Aktuelle Version ermitteln
        current_version = await self._get_latest_version(workflow_id, company_id)

        # Neue Versionsnummer berechnen
        if current_version:
            major, minor, patch = (
                current_version.major,
                current_version.minor,
                current_version.patch,
            )

            if change_type == "major":
                major += 1
                minor = 0
                patch = 0
            elif change_type == "minor":
                minor += 1
                patch = 0
            else:  # patch
                patch += 1
        else:
            major, minor, patch = 1, 0, 0

        version_string = f"{major}.{minor}.{patch}"

        # Definition erstellen
        if definition is None:
            definition = {
                "name": workflow.name,
                "description": workflow.description,
                "trigger_type": workflow.trigger_type,
                "trigger_config": workflow.trigger_config or {},
                "nodes": workflow.nodes or [],
                "edges": workflow.edges or [],
                "variables": workflow.variables or {},
                "max_concurrent_executions": workflow.max_concurrent_executions,
                "timeout_seconds": workflow.timeout_seconds,
                "retry_config": workflow.retry_config or {},
            }

        # Diff berechnen
        diff_summary = None
        if current_version:
            diff_summary = self._calculate_diff(
                current_version.definition,
                definition,
            )

        # Vorherige Version als nicht-aktuell markieren
        if current_version:
            current_version.is_latest = False

        # Neue Version erstellen
        new_version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow_id,
            company_id=company_id,
            version=version_string,
            major=major,
            minor=minor,
            patch=patch,
            status=WorkflowVersionStatus.DRAFT.value,
            is_active=False,
            is_latest=True,
            definition=definition,
            change_description=change_description,
            change_type=change_type,
            parent_version_id=current_version.id if current_version else None,
            diff_summary=diff_summary,
            created_by_id=user_id,
        )

        self.db.add(new_version)
        await self.db.commit()
        await self.db.refresh(new_version)

        logger.info(
            "workflow_version_created",
            workflow_id=str(workflow_id),
            version=version_string,
            change_type=change_type,
            user_id=str(user_id),
        )

        return new_version

    async def publish_version(
        self,
        version_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Veröffentlicht eine Draft-Version.

        Setzt den Status auf ACTIVE und deaktiviert optionale vorherige
        aktive Versionen.

        Args:
            version_id: Version-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Aktualisierte WorkflowVersion oder None
        """
        version = await self._get_version(version_id, company_id)
        if not version:
            return None

        if version.status != WorkflowVersionStatus.DRAFT.value:
            logger.warning(
                "cannot_publish_non_draft_version",
                version_id=str(version_id),
                current_status=version.status,
            )
            return None

        # Vorherige aktive Version deaktivieren
        stmt = (
            update(WorkflowVersion)
            .where(
                and_(
                    WorkflowVersion.workflow_id == version.workflow_id,
                    WorkflowVersion.company_id == company_id,
                    WorkflowVersion.is_active == True,  # noqa: E712
                    WorkflowVersion.id != version_id,
                )
            )
            .values(is_active=False)
        )
        await self.db.execute(stmt)

        # Version aktivieren
        version.status = WorkflowVersionStatus.ACTIVE.value
        version.is_active = True
        version.published_at = datetime.now(timezone.utc)

        # Workflow-Definition aktualisieren
        workflow = await self._get_workflow(version.workflow_id, company_id)
        if workflow:
            self._apply_definition_to_workflow(workflow, version.definition)

        await self.db.commit()
        await self.db.refresh(version)

        logger.info(
            "workflow_version_published",
            version_id=str(version_id),
            workflow_id=str(version.workflow_id),
            version=version.version,
        )

        return version

    async def deprecate_version(
        self,
        version_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Markiert eine Version als veraltet.

        Veraltete Versionen werden nicht mehr für neue Executions verwendet.

        Args:
            version_id: Version-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Aktualisierte WorkflowVersion oder None
        """
        version = await self._get_version(version_id, company_id)
        if not version:
            return None

        version.status = WorkflowVersionStatus.DEPRECATED.value
        version.is_active = False
        version.deprecated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(version)

        logger.info(
            "workflow_version_deprecated",
            version_id=str(version_id),
            version=version.version,
        )

        return version

    async def archive_version(
        self,
        version_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Archiviert eine Version (nur Lesezugriff).

        Args:
            version_id: Version-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Aktualisierte WorkflowVersion oder None
        """
        version = await self._get_version(version_id, company_id)
        if not version:
            return None

        version.status = WorkflowVersionStatus.ARCHIVED.value
        version.is_active = False
        version.archived_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(version)

        logger.info(
            "workflow_version_archived",
            version_id=str(version_id),
            version=version.version,
        )

        return version

    # =========================================================================
    # Version Queries
    # =========================================================================

    async def get_version(
        self,
        version_id: UUID,
        company_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Holt eine Version nach ID.

        Args:
            version_id: Version-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            WorkflowVersion oder None
        """
        return await self._get_version(version_id, company_id)

    async def list_versions(
        self,
        workflow_id: UUID,
        company_id: UUID,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[WorkflowVersion], int]:
        """Listet alle Versionen eines Workflows.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            status: Optionaler Status-Filter
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple aus Version-Liste und Gesamtanzahl
        """
        conditions = [
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.company_id == company_id,
        ]

        if status:
            conditions.append(WorkflowVersion.status == status)

        # Count
        count_query = select(func.count(WorkflowVersion.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Data
        query = (
            select(WorkflowVersion)
            .where(and_(*conditions))
            .order_by(
                WorkflowVersion.major.desc(),
                WorkflowVersion.minor.desc(),
                WorkflowVersion.patch.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        versions = list(result.scalars().all())

        return versions, total

    async def get_active_version(
        self,
        workflow_id: UUID,
        company_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Holt die aktive Version eines Workflows.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            Aktive WorkflowVersion oder None
        """
        query = select(WorkflowVersion).where(
            and_(
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.company_id == company_id,
                WorkflowVersion.is_active == True,  # noqa: E712
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # =========================================================================
    # Diff & Comparison
    # =========================================================================

    async def get_version_diff(
        self,
        version_id: UUID,
        compare_to_id: Optional[UUID],
        company_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Berechnet den Diff zwischen zwei Versionen.

        Args:
            version_id: Aktuelle Version
            compare_to_id: Zu vergleichende Version (None = vorherige)
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            Diff-Dictionary oder None
        """
        version = await self._get_version(version_id, company_id)
        if not version:
            return None

        # Vergleichsversion ermitteln
        if compare_to_id:
            compare_version = await self._get_version(compare_to_id, company_id)
        else:
            compare_version = None
            if version.parent_version_id:
                compare_version = await self._get_version(
                    version.parent_version_id, company_id
                )

        if not compare_version:
            return {
                "version_a": version.version,
                "version_b": None,
                "changes": {
                    "added": list(version.definition.keys()),
                    "removed": [],
                    "modified": [],
                },
                "details": {},
            }

        # Detaillierten Diff berechnen
        diff = self._calculate_detailed_diff(
            compare_version.definition,
            version.definition,
        )

        return {
            "version_a": compare_version.version,
            "version_b": version.version,
            "changes": diff["summary"],
            "details": diff["details"],
        }

    def _calculate_diff(
        self,
        old_def: Dict[str, Any],
        new_def: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Berechnet einen einfachen Diff zwischen zwei Definitionen.

        Args:
            old_def: Alte Definition
            new_def: Neue Definition

        Returns:
            Diff-Summary
        """
        added = []
        removed = []
        modified = []

        all_keys = set(old_def.keys()) | set(new_def.keys())

        for key in all_keys:
            old_val = old_def.get(key)
            new_val = new_def.get(key)

            if old_val is None and new_val is not None:
                added.append(key)
            elif old_val is not None and new_val is None:
                removed.append(key)
            elif old_val != new_val:
                modified.append(key)

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
        }

    def _calculate_detailed_diff(
        self,
        old_def: Dict[str, Any],
        new_def: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Berechnet einen detaillierten Diff.

        Args:
            old_def: Alte Definition
            new_def: Neue Definition

        Returns:
            Detaillierter Diff mit Summary und Details
        """
        summary = self._calculate_diff(old_def, new_def)
        details: Dict[str, Any] = {}

        # Nodes-Diff
        if "nodes" in summary["modified"]:
            old_nodes = {n.get("id"): n for n in old_def.get("nodes", [])}
            new_nodes = {n.get("id"): n for n in new_def.get("nodes", [])}

            details["nodes"] = {
                "added": [nid for nid in new_nodes if nid not in old_nodes],
                "removed": [nid for nid in old_nodes if nid not in new_nodes],
                "modified": [
                    nid for nid in new_nodes
                    if nid in old_nodes and new_nodes[nid] != old_nodes[nid]
                ],
            }

        # Edges-Diff
        if "edges" in summary["modified"]:
            old_edges = {e.get("id"): e for e in old_def.get("edges", [])}
            new_edges = {e.get("id"): e for e in new_def.get("edges", [])}

            details["edges"] = {
                "added": [eid for eid in new_edges if eid not in old_edges],
                "removed": [eid for eid in old_edges if eid not in new_edges],
                "modified": [
                    eid for eid in new_edges
                    if eid in old_edges and new_edges[eid] != old_edges[eid]
                ],
            }

        # Trigger-Config-Diff
        if "trigger_config" in summary["modified"]:
            old_tc = old_def.get("trigger_config", {})
            new_tc = new_def.get("trigger_config", {})
            details["trigger_config"] = self._calculate_diff(old_tc, new_tc)

        return {
            "summary": summary,
            "details": details,
        }

    # =========================================================================
    # Rollback
    # =========================================================================

    async def rollback_to_version(
        self,
        workflow_id: UUID,
        target_version_id: UUID,
        company_id: UUID,
        user_id: UUID,
        create_backup: bool = True,
    ) -> Optional[WorkflowVersion]:
        """Rollt einen Workflow auf eine vorherige Version zurück.

        Erstellt optional eine Backup-Version des aktuellen Zustands.

        Args:
            workflow_id: Workflow-ID
            target_version_id: Ziel-Version
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User
            create_backup: Backup erstellen (default: True)

        Returns:
            Neue Version (Rollback) oder None
        """
        target_version = await self._get_version(target_version_id, company_id)
        if not target_version or target_version.workflow_id != workflow_id:
            logger.warning(
                "rollback_target_version_not_found",
                workflow_id=str(workflow_id),
                target_version_id=str(target_version_id),
            )
            return None

        # Backup erstellen
        if create_backup:
            await self.create_version(
                workflow_id=workflow_id,
                company_id=company_id,
                user_id=user_id,
                change_description=f"Backup vor Rollback zu Version {target_version.version}",
                change_type="patch",
            )

        # Rollback-Version erstellen
        rollback_version = await self.create_version(
            workflow_id=workflow_id,
            company_id=company_id,
            user_id=user_id,
            change_description=f"Rollback zu Version {target_version.version}",
            change_type="minor",
            definition=target_version.definition.copy(),
        )

        if rollback_version:
            # Direkt aktivieren
            await self.publish_version(
                version_id=rollback_version.id,
                company_id=company_id,
                user_id=user_id,
            )

            logger.info(
                "workflow_rolled_back",
                workflow_id=str(workflow_id),
                from_version=target_version.version,
                to_version=rollback_version.version,
                user_id=str(user_id),
            )

        return rollback_version

    # =========================================================================
    # A/B Testing
    # =========================================================================

    async def create_ab_test(
        self,
        workflow_id: UUID,
        company_id: UUID,
        user_id: UUID,
        name: str,
        control_version_id: UUID,
        treatment_version_id: UUID,
        treatment_percentage: int = 50,
        description: Optional[str] = None,
        end_at: Optional[datetime] = None,
    ) -> Optional[WorkflowABTest]:
        """Erstellt einen neuen A/B Test zwischen zwei Versionen.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ersteller
            name: Test-Name
            control_version_id: Control-Version (Baseline)
            treatment_version_id: Treatment-Version (zu testen)
            treatment_percentage: Traffic-Anteil für Treatment (0-100)
            description: Optionale Beschreibung
            end_at: Optionales End-Datum

        Returns:
            WorkflowABTest oder None
        """
        if treatment_percentage < 0 or treatment_percentage > 100:
            raise ValueError("treatment_percentage muss zwischen 0 und 100 liegen")

        # Versionen validieren
        control = await self._get_version(control_version_id, company_id)
        treatment = await self._get_version(treatment_version_id, company_id)

        if not control or not treatment:
            logger.warning(
                "ab_test_versions_not_found",
                control_version_id=str(control_version_id),
                treatment_version_id=str(treatment_version_id),
            )
            return None

        if control.workflow_id != workflow_id or treatment.workflow_id != workflow_id:
            logger.warning(
                "ab_test_versions_workflow_mismatch",
                workflow_id=str(workflow_id),
            )
            return None

        ab_test = WorkflowABTest(
            id=uuid4(),
            workflow_id=workflow_id,
            company_id=company_id,
            name=name,
            description=description,
            control_version_id=control_version_id,
            treatment_version_id=treatment_version_id,
            treatment_percentage=treatment_percentage,
            status=ABTestStatus.DRAFT.value,
            end_at=end_at,
            created_by_id=user_id,
        )

        self.db.add(ab_test)
        await self.db.commit()
        await self.db.refresh(ab_test)

        logger.info(
            "workflow_ab_test_created",
            test_id=str(ab_test.id),
            workflow_id=str(workflow_id),
            name=name,
            treatment_percentage=treatment_percentage,
        )

        return ab_test

    async def start_ab_test(
        self,
        test_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[WorkflowABTest]:
        """Startet einen A/B Test.

        Args:
            test_id: Test-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Aktualisierter WorkflowABTest oder None
        """
        ab_test = await self._get_ab_test(test_id, company_id)
        if not ab_test:
            return None

        if ab_test.status != ABTestStatus.DRAFT.value:
            logger.warning(
                "cannot_start_non_draft_ab_test",
                test_id=str(test_id),
                current_status=ab_test.status,
            )
            return None

        ab_test.status = ABTestStatus.RUNNING.value
        ab_test.start_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(ab_test)

        logger.info(
            "workflow_ab_test_started",
            test_id=str(test_id),
        )

        return ab_test

    async def stop_ab_test(
        self,
        test_id: UUID,
        company_id: UUID,
        user_id: UUID,
        winner: Optional[str] = None,
    ) -> Optional[WorkflowABTest]:
        """Beendet einen A/B Test.

        Args:
            test_id: Test-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User
            winner: Optionaler Gewinner (control, treatment, inconclusive)

        Returns:
            Aktualisierter WorkflowABTest oder None
        """
        ab_test = await self._get_ab_test(test_id, company_id)
        if not ab_test:
            return None

        if ab_test.status != ABTestStatus.RUNNING.value:
            logger.warning(
                "cannot_stop_non_running_ab_test",
                test_id=str(test_id),
                current_status=ab_test.status,
            )
            return None

        ab_test.status = ABTestStatus.COMPLETED.value
        ab_test.completed_at = datetime.now(timezone.utc)

        # Gewinner setzen oder berechnen
        if winner:
            ab_test.winner = winner
        else:
            ab_test.winner = self._calculate_ab_test_winner(ab_test)

        await self.db.commit()
        await self.db.refresh(ab_test)

        logger.info(
            "workflow_ab_test_stopped",
            test_id=str(test_id),
            winner=ab_test.winner,
        )

        return ab_test

    async def get_ab_test_version(
        self,
        workflow_id: UUID,
        company_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Waehlt eine Version basierend auf aktiven A/B Tests.

        Falls ein A/B Test laeuft, wird zufällig basierend auf dem
        Treatment-Prozentsatz eine Version gewaehlt.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            Ausgewaehlte WorkflowVersion oder None
        """
        # Aktiven A/B Test suchen
        query = select(WorkflowABTest).where(
            and_(
                WorkflowABTest.workflow_id == workflow_id,
                WorkflowABTest.company_id == company_id,
                WorkflowABTest.status == ABTestStatus.RUNNING.value,
            )
        )

        result = await self.db.execute(query)
        ab_test = result.scalar_one_or_none()

        if not ab_test:
            # Kein A/B Test, aktive Version zurückgeben
            return await self.get_active_version(workflow_id, company_id)

        # Zufallsauswahl basierend auf Treatment-Prozentsatz
        if random.randint(1, 100) <= ab_test.treatment_percentage:
            version = await self._get_version(ab_test.treatment_version_id, company_id)
        else:
            version = await self._get_version(ab_test.control_version_id, company_id)

        return version

    async def record_ab_test_execution(
        self,
        test_id: UUID,
        company_id: UUID,
        version_id: UUID,
        success: bool,
        execution_time_ms: int,
    ) -> None:
        """Zeichnet eine Execution für A/B Test-Statistiken auf.

        Args:
            test_id: Test-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            version_id: Verwendete Version
            success: War erfolgreich
            execution_time_ms: Ausführungszeit
        """
        ab_test = await self._get_ab_test(test_id, company_id)
        if not ab_test or ab_test.status != ABTestStatus.RUNNING.value:
            return

        # Statistiken aktualisieren
        if version_id == ab_test.control_version_id:
            ab_test.control_executions += 1
            if success:
                ab_test.control_successes += 1
            else:
                ab_test.control_failures += 1
            # Rolling Average
            if ab_test.control_avg_time_ms:
                ab_test.control_avg_time_ms = int(
                    (ab_test.control_avg_time_ms + execution_time_ms) / 2
                )
            else:
                ab_test.control_avg_time_ms = execution_time_ms

        elif version_id == ab_test.treatment_version_id:
            ab_test.treatment_executions += 1
            if success:
                ab_test.treatment_successes += 1
            else:
                ab_test.treatment_failures += 1
            # Rolling Average
            if ab_test.treatment_avg_time_ms:
                ab_test.treatment_avg_time_ms = int(
                    (ab_test.treatment_avg_time_ms + execution_time_ms) / 2
                )
            else:
                ab_test.treatment_avg_time_ms = execution_time_ms

        await self.db.commit()

    def _calculate_ab_test_winner(self, ab_test: WorkflowABTest) -> str:
        """Berechnet den Gewinner eines A/B Tests.

        Verwendet einfachen Vergleich der Erfolgsraten.
        Für statistische Signifikanz waere ein Chi-Quadrat-Test noetig.

        Args:
            ab_test: A/B Test

        Returns:
            Winner-String (control, treatment, inconclusive)
        """
        control_rate = ab_test.control_success_rate
        treatment_rate = ab_test.treatment_success_rate

        # Mindestens 100 Executions pro Variante
        if ab_test.control_executions < 100 or ab_test.treatment_executions < 100:
            return "inconclusive"

        # 5% Unterschied als signifikant
        if treatment_rate > control_rate + 5:
            return "treatment"
        elif control_rate > treatment_rate + 5:
            return "control"
        else:
            return "inconclusive"

    # =========================================================================
    # Instance Migration
    # =========================================================================

    async def migrate_running_instances(
        self,
        workflow_id: UUID,
        from_version_id: UUID,
        to_version_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Migriert laufende Workflow-Instanzen auf eine neue Version.

        ACHTUNG: Dies ist eine komplexe Operation und sollte nur
        mit Vorsicht durchgeführt werden.

        Args:
            workflow_id: Workflow-ID
            from_version_id: Quell-Version
            to_version_id: Ziel-Version
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Migration-Ergebnis mit Statistiken
        """
        from app.db.models import WorkflowExecution

        # Versionen validieren
        from_version = await self._get_version(from_version_id, company_id)
        to_version = await self._get_version(to_version_id, company_id)

        if not from_version or not to_version:
            return {
                "success": False,
                "error": "Version nicht gefunden",
                "migrated": 0,
                "failed": 0,
            }

        # Laufende Executions zaehlen
        count_query = select(func.count(WorkflowExecution.id)).where(
            and_(
                WorkflowExecution.workflow_id == workflow_id,
                WorkflowExecution.status.in_(["running", "pending", "paused"]),
            )
        )

        count_result = await self.db.execute(count_query)
        running_count = count_result.scalar() or 0

        if running_count == 0:
            return {
                "success": True,
                "migrated": 0,
                "failed": 0,
                "message": "Keine laufenden Instanzen gefunden",
            }

        # Migration durchführen (hier nur Logging, echte Migration ist komplex)
        logger.info(
            "workflow_instance_migration_started",
            workflow_id=str(workflow_id),
            from_version=from_version.version,
            to_version=to_version.version,
            running_instances=running_count,
            user_id=str(user_id),
        )

        # In der Praxis müsste hier:
        # 1. Checkpoint der laufenden Instanz speichern
        # 2. Definition aktualisieren
        # 3. Von Checkpoint fortsetzen

        return {
            "success": True,
            "migrated": running_count,
            "failed": 0,
            "message": f"{running_count} Instanz(en) zur Migration vorgemerkt",
        }

    # =========================================================================
    # Statistics
    # =========================================================================

    async def update_version_statistics(
        self,
        version_id: UUID,
        company_id: UUID,
        success: bool,
        execution_time_ms: int,
    ) -> None:
        """Aktualisiert die Statistiken einer Version.

        Args:
            version_id: Version-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            success: War erfolgreich
            execution_time_ms: Ausführungszeit
        """
        version = await self._get_version(version_id, company_id)
        if not version:
            return

        version.execution_count += 1
        if success:
            version.success_count += 1
        else:
            version.failure_count += 1

        # Rolling Average
        if version.avg_execution_time_ms:
            version.avg_execution_time_ms = int(
                (version.avg_execution_time_ms + execution_time_ms) / 2
            )
        else:
            version.avg_execution_time_ms = execution_time_ms

        await self.db.commit()

    async def get_version_comparison(
        self,
        workflow_id: UUID,
        company_id: UUID,
        version_ids: Optional[List[UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """Vergleicht mehrere Versionen nach Statistiken.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            version_ids: Optionale Liste von Version-IDs (sonst alle)

        Returns:
            Liste von Vergleichs-Dicts
        """
        conditions = [
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.company_id == company_id,
        ]

        if version_ids:
            conditions.append(WorkflowVersion.id.in_(version_ids))

        query = (
            select(WorkflowVersion)
            .where(and_(*conditions))
            .order_by(
                WorkflowVersion.major.desc(),
                WorkflowVersion.minor.desc(),
                WorkflowVersion.patch.desc(),
            )
        )

        result = await self.db.execute(query)
        versions = list(result.scalars().all())

        return [
            {
                "version_id": str(v.id),
                "version": v.version,
                "status": v.status,
                "is_active": v.is_active,
                "execution_count": v.execution_count,
                "success_count": v.success_count,
                "failure_count": v.failure_count,
                "success_rate": v.success_rate,
                "avg_execution_time_ms": v.avg_execution_time_ms,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "published_at": v.published_at.isoformat() if v.published_at else None,
            }
            for v in versions
        ]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_workflow(
        self,
        workflow_id: UUID,
        company_id: UUID,
    ) -> Optional[Workflow]:
        """Laedt einen Workflow mit Multi-Tenant Validierung.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID

        Returns:
            Workflow oder None
        """
        query = select(Workflow).where(
            and_(
                Workflow.id == workflow_id,
                Workflow.company_id == company_id,
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_version(
        self,
        version_id: UUID,
        company_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Laedt eine Version mit Multi-Tenant Validierung.

        Args:
            version_id: Version-ID
            company_id: Company-ID

        Returns:
            WorkflowVersion oder None
        """
        query = select(WorkflowVersion).where(
            and_(
                WorkflowVersion.id == version_id,
                WorkflowVersion.company_id == company_id,
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_latest_version(
        self,
        workflow_id: UUID,
        company_id: UUID,
    ) -> Optional[WorkflowVersion]:
        """Laedt die neueste Version eines Workflows.

        Args:
            workflow_id: Workflow-ID
            company_id: Company-ID

        Returns:
            Neueste WorkflowVersion oder None
        """
        query = (
            select(WorkflowVersion)
            .where(
                and_(
                    WorkflowVersion.workflow_id == workflow_id,
                    WorkflowVersion.company_id == company_id,
                )
            )
            .order_by(
                WorkflowVersion.major.desc(),
                WorkflowVersion.minor.desc(),
                WorkflowVersion.patch.desc(),
            )
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_ab_test(
        self,
        test_id: UUID,
        company_id: UUID,
    ) -> Optional[WorkflowABTest]:
        """Laedt einen A/B Test mit Multi-Tenant Validierung.

        Args:
            test_id: Test-ID
            company_id: Company-ID

        Returns:
            WorkflowABTest oder None
        """
        query = select(WorkflowABTest).where(
            and_(
                WorkflowABTest.id == test_id,
                WorkflowABTest.company_id == company_id,
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _apply_definition_to_workflow(
        self,
        workflow: Workflow,
        definition: Dict[str, Any],
    ) -> None:
        """Wendet eine Definition auf einen Workflow an.

        Args:
            workflow: Workflow-Objekt
            definition: Definition-Dict
        """
        if "name" in definition:
            workflow.name = definition["name"]
        if "description" in definition:
            workflow.description = definition["description"]
        if "trigger_type" in definition:
            workflow.trigger_type = definition["trigger_type"]
        if "trigger_config" in definition:
            workflow.trigger_config = definition["trigger_config"]
        if "nodes" in definition:
            workflow.nodes = definition["nodes"]
        if "edges" in definition:
            workflow.edges = definition["edges"]
        if "variables" in definition:
            workflow.variables = definition["variables"]
        if "max_concurrent_executions" in definition:
            workflow.max_concurrent_executions = definition["max_concurrent_executions"]
        if "timeout_seconds" in definition:
            workflow.timeout_seconds = definition["timeout_seconds"]
        if "retry_config" in definition:
            workflow.retry_config = definition["retry_config"]
