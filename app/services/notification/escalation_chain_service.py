# -*- coding: utf-8 -*-
"""
Notification Escalation Chain Service.

Verwaltet zeitbasierte Eskalationsketten fuer Benachrichtigungen:
- Level 1: In-App -> 1h Email
- Level 2: + Slack nach 4h
- Level 3: + SMS nach 8h (Critical only)

Features:
- Vordefinierte Eskalationsketten (standard, urgent, approval)
- Automatische Zeitbasierte Eskalation via Celery Beat
- Eskalationsaufloesung bei Benutzeraktion
- Audit-Logging fuer Compliance

Feinpoliert und durchdacht - Keine verpassten Benachrichtigungen mehr.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class EscalationPreset(str, Enum):
    """Vordefinierte Eskalationspresets."""
    STANDARD = "standard"
    URGENT = "urgent"
    RELAXED = "relaxed"


class EscalationChannel(str, Enum):
    """Verfuegbare Eskalationskanaele."""
    IN_APP = "in_app"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    SMS = "sms"
    PUSH = "push"


class EscalationStatus(str, Enum):
    """Status einer Eskalation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    AUTO_RESOLVED = "auto_resolved"
    CANCELLED = "cancelled"


# =============================================================================
# Datenstrukturen
# =============================================================================


@dataclass
class EscalationLevel:
    """Eine Stufe in der Eskalationskette."""
    level: int
    channel: str
    delay_minutes: int
    recipients: List[str]
    message_template: Optional[str] = None

    def __post_init__(self) -> None:
        """Validierung nach Initialisierung."""
        if self.level < 1:
            raise ValueError("Level muss >= 1 sein")
        if self.delay_minutes < 0:
            raise ValueError("Delay muss >= 0 sein")


@dataclass
class EscalationChain:
    """Vollstaendige Eskalationskette."""
    id: str
    name: str
    description: str
    levels: List[EscalationLevel]
    max_escalation_level: int
    auto_resolve_after_hours: Optional[int] = None

    def __post_init__(self) -> None:
        """Validierung nach Initialisierung."""
        if not self.levels:
            raise ValueError("Eskalationskette muss mindestens ein Level haben")
        if self.max_escalation_level < 1:
            raise ValueError("max_escalation_level muss >= 1 sein")
        if self.max_escalation_level > len(self.levels):
            raise ValueError("max_escalation_level > Anzahl Levels")


@dataclass
class EscalationState:
    """Aktueller Zustand einer Eskalation."""
    notification_id: str
    user_id: str
    chain_id: str
    current_level: int
    status: EscalationStatus
    created_at: datetime
    next_escalation_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None


# =============================================================================
# Vordefinierte Eskalationsketten
# =============================================================================


PRESET_CHAINS: Dict[str, EscalationChain] = {
    "standard": EscalationChain(
        id="standard",
        name="Standard-Eskalation",
        description="In-App -> 1h Email -> 4h Slack",
        levels=[
            EscalationLevel(
                level=1,
                channel=EscalationChannel.IN_APP.value,
                delay_minutes=0,
                recipients=["user"],
            ),
            EscalationLevel(
                level=2,
                channel=EscalationChannel.EMAIL.value,
                delay_minutes=60,
                recipients=["user"],
                message_template="Sie haben eine ungelesene Benachrichtigung: {title}",
            ),
            EscalationLevel(
                level=3,
                channel=EscalationChannel.SLACK.value,
                delay_minutes=240,
                recipients=["user"],
                message_template="ESKALATION: {title}",
            ),
        ],
        max_escalation_level=3,
        auto_resolve_after_hours=24,
    ),
    "urgent": EscalationChain(
        id="urgent",
        name="Dringende Eskalation",
        description="In-App+Email -> 30min Slack -> 2h SMS",
        levels=[
            EscalationLevel(
                level=1,
                channel=EscalationChannel.IN_APP.value,
                delay_minutes=0,
                recipients=["user"],
            ),
            EscalationLevel(
                level=1,
                channel=EscalationChannel.EMAIL.value,
                delay_minutes=0,
                recipients=["user"],
            ),
            EscalationLevel(
                level=2,
                channel=EscalationChannel.SLACK.value,
                delay_minutes=30,
                recipients=["user"],
                message_template="DRINGEND: {title}",
            ),
            EscalationLevel(
                level=3,
                channel=EscalationChannel.SMS.value,
                delay_minutes=120,
                recipients=["user"],
                message_template="KRITISCH: {title}",
            ),
        ],
        max_escalation_level=3,
        auto_resolve_after_hours=8,
    ),
    "approval": EscalationChain(
        id="approval",
        name="Genehmigungsworkflow",
        description="In-App -> 24h Email -> 72h Manager",
        levels=[
            EscalationLevel(
                level=1,
                channel=EscalationChannel.IN_APP.value,
                delay_minutes=0,
                recipients=["user"],
            ),
            EscalationLevel(
                level=2,
                channel=EscalationChannel.EMAIL.value,
                delay_minutes=1440,  # 24h
                recipients=["user"],
                message_template="Erinnerung: Genehmigung ausstehend - {title}",
            ),
            EscalationLevel(
                level=3,
                channel=EscalationChannel.EMAIL.value,
                delay_minutes=4320,  # 72h
                recipients=["manager"],
                message_template="Eskalation an Manager: {title}",
            ),
        ],
        max_escalation_level=3,
        auto_resolve_after_hours=168,  # 1 Woche
    ),
}


# =============================================================================
# Escalation Chain Service
# =============================================================================


class NotificationEscalationService:
    """
    Verwaltet zeitbasierte Benachrichtigungs-Eskalationen.

    Verwendung:
        service = NotificationEscalationService(db)
        escalation_id = await service.create_escalation(
            notification_id=notification.id,
            chain_name="standard",
            user_id=user.id,
        )

        # Periodisch via Celery Beat aufrufen:
        escalated = await service.check_escalations()
    """

    PRESET_CHAINS: Dict[str, EscalationChain] = PRESET_CHAINS

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialisiert den Service.

        Args:
            db: AsyncSession fuer DB-Operationen
        """
        self.db = db
        self._active_escalations: Dict[str, EscalationState] = {}

    async def create_escalation(
        self,
        notification_id: uuid.UUID,
        chain_name: str,
        user_id: uuid.UUID,
    ) -> str:
        """
        Startet eine Eskalationskette fuer eine Benachrichtigung.

        Args:
            notification_id: ID der Benachrichtigung
            chain_name: Name der Preset-Chain ("standard", "urgent", "approval")
            user_id: Benutzer-ID

        Returns:
            Eskalations-ID

        Raises:
            ValueError: Wenn Chain nicht existiert
        """
        if chain_name not in self.PRESET_CHAINS:
            raise ValueError(f"Unbekannte Eskalationskette: {chain_name}")

        chain = self.PRESET_CHAINS[chain_name]
        escalation_id = str(uuid.uuid4())

        # Naechste Eskalationsstufe berechnen (Level 2, da Level 1 sofort)
        next_level = 2 if len(chain.levels) > 1 else None
        next_escalation_at = None

        if next_level:
            delay_level = next((lv for lv in chain.levels if lv.level == next_level), None)
            if delay_level:
                next_escalation_at = datetime.now(timezone.utc) + timedelta(
                    minutes=delay_level.delay_minutes
                )

        state = EscalationState(
            notification_id=str(notification_id),
            user_id=str(user_id),
            chain_id=chain.id,
            current_level=1,
            status=EscalationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            next_escalation_at=next_escalation_at,
        )

        self._active_escalations[escalation_id] = state

        logger.info(
            "escalation_created",
            escalation_id=escalation_id,
            notification_id=str(notification_id),
            chain_name=chain_name,
            user_id=str(user_id),
            next_escalation_at=next_escalation_at.isoformat() if next_escalation_at else None,
        )

        return escalation_id

    async def check_escalations(self) -> List[Dict[str, str]]:
        """
        Prueft alle aktiven Eskalationen und fuehrt faellige Eskalationsstufen aus.

        Wird periodisch von Celery Beat aufgerufen.

        Returns:
            Liste der eskalierten Benachrichtigungen mit Details
        """
        now = datetime.now(timezone.utc)
        escalated = []

        for escalation_id, state in list(self._active_escalations.items()):
            # Nur pending oder in_progress pruefen
            if state.status not in (EscalationStatus.PENDING, EscalationStatus.IN_PROGRESS):
                continue

            # Auto-Resolve Check
            chain = self.PRESET_CHAINS.get(state.chain_id)
            if chain and chain.auto_resolve_after_hours:
                auto_resolve_at = state.created_at + timedelta(hours=chain.auto_resolve_after_hours)
                if now >= auto_resolve_at:
                    await self._auto_resolve_escalation(escalation_id, state)
                    continue

            # Naechste Eskalationsstufe faellig?
            if state.next_escalation_at and now >= state.next_escalation_at:
                result = await self._escalate_to_next_level(escalation_id, state)
                if result:
                    escalated.append(result)

        logger.info(
            "escalations_checked",
            total_active=len(self._active_escalations),
            escalated_count=len(escalated),
        )

        return escalated

    async def resolve_escalation(self, notification_id: uuid.UUID) -> bool:
        """
        Loest eine Eskalation auf (z.B. wenn Benutzer die Benachrichtigung liest).

        Args:
            notification_id: Benachrichtigungs-ID

        Returns:
            True wenn Eskalation aufgeloest wurde
        """
        escalation_id = self._find_escalation_by_notification(notification_id)
        if not escalation_id:
            return False

        state = self._active_escalations[escalation_id]
        state.status = EscalationStatus.RESOLVED
        state.resolved_at = datetime.now(timezone.utc)
        state.resolution_reason = "user_acknowledged"

        logger.info(
            "escalation_resolved",
            escalation_id=escalation_id,
            notification_id=str(notification_id),
            current_level=state.current_level,
        )

        # Aus aktiven Eskalationen entfernen
        del self._active_escalations[escalation_id]

        return True

    async def get_active_escalations(self, user_id: uuid.UUID) -> List[Dict[str, str]]:
        """
        Gibt alle aktiven Eskalationen fuer einen Benutzer zurueck.

        Args:
            user_id: Benutzer-ID

        Returns:
            Liste der aktiven Eskalationen
        """
        user_escalations = []

        for escalation_id, state in self._active_escalations.items():
            if state.user_id != str(user_id):
                continue

            if state.status not in (EscalationStatus.PENDING, EscalationStatus.IN_PROGRESS):
                continue

            chain = self.PRESET_CHAINS.get(state.chain_id)

            user_escalations.append({
                "escalation_id": escalation_id,
                "notification_id": state.notification_id,
                "chain_name": chain.name if chain else state.chain_id,
                "current_level": state.current_level,
                "max_level": chain.max_escalation_level if chain else 3,
                "status": state.status.value,
                "created_at": state.created_at.isoformat(),
                "next_escalation_at": state.next_escalation_at.isoformat() if state.next_escalation_at else None,
            })

        return user_escalations

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _find_escalation_by_notification(self, notification_id: uuid.UUID) -> Optional[str]:
        """Findet Eskalations-ID anhand Benachrichtigungs-ID."""
        for escalation_id, state in self._active_escalations.items():
            if state.notification_id == str(notification_id):
                return escalation_id
        return None

    async def _escalate_to_next_level(
        self,
        escalation_id: str,
        state: EscalationState,
    ) -> Optional[Dict[str, str]]:
        """
        Eskaliert zur naechsten Stufe.

        Args:
            escalation_id: Eskalations-ID
            state: Aktueller State

        Returns:
            Details der Eskalation oder None
        """
        chain = self.PRESET_CHAINS.get(state.chain_id)
        if not chain:
            logger.error("escalation_chain_not_found", chain_id=state.chain_id)
            return None

        # Naechstes Level
        next_level = state.current_level + 1
        if next_level > chain.max_escalation_level:
            # Maximales Level erreicht
            state.status = EscalationStatus.AUTO_RESOLVED
            state.resolved_at = datetime.now(timezone.utc)
            state.resolution_reason = "max_level_reached"
            del self._active_escalations[escalation_id]
            return None

        # Level-Config finden
        level_config = next((lv for lv in chain.levels if lv.level == next_level), None)
        if not level_config:
            logger.error(
                "escalation_level_config_not_found",
                chain_id=state.chain_id,
                level=next_level,
            )
            return None

        # State aktualisieren
        state.current_level = next_level
        state.status = EscalationStatus.IN_PROGRESS

        # Naechste Eskalation planen
        if next_level < chain.max_escalation_level:
            next_level_config = next((lv for lv in chain.levels if lv.level == next_level + 1), None)
            if next_level_config:
                state.next_escalation_at = datetime.now(timezone.utc) + timedelta(
                    minutes=next_level_config.delay_minutes
                )
        else:
            state.next_escalation_at = None

        logger.warning(
            "notification_escalated",
            escalation_id=escalation_id,
            notification_id=state.notification_id,
            level=next_level,
            channel=level_config.channel,
            user_id=state.user_id,
        )

        return {
            "escalation_id": escalation_id,
            "notification_id": state.notification_id,
            "user_id": state.user_id,
            "level": next_level,
            "channel": level_config.channel,
            "message_template": level_config.message_template or "",
        }

    async def _auto_resolve_escalation(
        self,
        escalation_id: str,
        state: EscalationState,
    ) -> None:
        """
        Loest Eskalation automatisch auf (Zeitlimit erreicht).

        Args:
            escalation_id: Eskalations-ID
            state: State
        """
        state.status = EscalationStatus.AUTO_RESOLVED
        state.resolved_at = datetime.now(timezone.utc)
        state.resolution_reason = "auto_resolve_timeout"

        logger.info(
            "escalation_auto_resolved",
            escalation_id=escalation_id,
            notification_id=state.notification_id,
            user_id=state.user_id,
        )

        del self._active_escalations[escalation_id]


# =============================================================================
# Factory
# =============================================================================


_escalation_service: Optional[NotificationEscalationService] = None


def get_escalation_service(db: AsyncSession) -> NotificationEscalationService:
    """
    Factory fuer NotificationEscalationService.

    Args:
        db: AsyncSession

    Returns:
        NotificationEscalationService Instanz
    """
    global _escalation_service
    if _escalation_service is None:
        _escalation_service = NotificationEscalationService(db)
    else:
        _escalation_service.db = db
    return _escalation_service
