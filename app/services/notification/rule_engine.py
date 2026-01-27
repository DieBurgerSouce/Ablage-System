"""Notification Rule Engine.

Event-basierte Regel-Auswertung fuer das Enterprise Notification System.
Wertet Regeln gegen Events aus und fuehrt Aktionen ueber BESTEHENDE Services aus.

Features:
- Komplexe Bedingungs-Auswertung (AND, OR, NOT)
- Multiple Aktions-Typen (in_app, push, email, webhook)
- Quiet Hours mit Zeitzonenunterstuetzung
- Rate Limiting pro Regel
- Event Bus Integration
"""

from __future__ import annotations

import asyncio
import logging
import operator
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import UUID
import json

import pytz
import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NotificationRule, User, UserNotification
from app.services.events.event_bus import Event, EventBus, get_event_bus

logger = structlog.get_logger(__name__)

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

RULES_EVALUATED = Counter(
    "notification_rules_evaluated_total",
    "Anzahl ausgewerteter Regeln",
    ["event_type", "matched"]
)

RULES_TRIGGERED = Counter(
    "notification_rules_triggered_total",
    "Anzahl ausgeloester Regeln",
    ["event_type", "action_type"]
)

RULE_EVALUATION_TIME = Histogram(
    "notification_rule_evaluation_seconds",
    "Zeit fuer Regel-Auswertung",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

RULES_SKIPPED_QUIET_HOURS = Counter(
    "notification_rules_skipped_quiet_hours_total",
    "Regeln wegen Quiet Hours uebersprungen"
)

RULES_SKIPPED_RATE_LIMIT = Counter(
    "notification_rules_skipped_rate_limit_total",
    "Regeln wegen Rate Limit uebersprungen"
)


# =============================================================================
# DATA CLASSES
# =============================================================================

class ActionType(str, Enum):
    """Aktionstypen fuer Notifications."""
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"
    WEBHOOK = "webhook"


@dataclass
class NotificationAction:
    """Eine auszufuehrende Notification-Aktion."""
    action_type: ActionType
    rule_id: UUID
    user_id: UUID
    event_type: str
    payload: Dict[str, Any]
    priority: str = "normal"

    # Fuer in_app
    title: Optional[str] = None
    message: Optional[str] = None
    action_url: Optional[str] = None

    # Fuer email
    email_template: Optional[str] = None
    email_subject: Optional[str] = None

    # Fuer webhook
    webhook_url: Optional[str] = None

    # Fuer push
    push_data: Optional[Dict[str, Any]] = None


@dataclass
class RuleEvaluationResult:
    """Ergebnis einer Regel-Auswertung."""
    rule_id: UUID
    rule_name: str
    matched: bool
    actions: List[NotificationAction] = field(default_factory=list)
    skipped_reason: Optional[str] = None
    evaluation_time_ms: float = 0.0


@dataclass
class EventEvaluationResult:
    """Ergebnis der Auswertung eines Events gegen alle Regeln."""
    event_id: UUID
    event_type: str
    rules_checked: int = 0
    rules_matched: int = 0
    rules_skipped: int = 0
    actions_generated: int = 0
    rule_results: List[RuleEvaluationResult] = field(default_factory=list)
    total_time_ms: float = 0.0


# =============================================================================
# CONDITION MATCHER
# =============================================================================

class RuleConditionMatcher:
    """Evaluiert komplexe Bedingungen gegen Event-Daten.

    Unterstuetzt:
    - Vergleichsoperatoren: eq, ne, gt, gte, lt, lte
    - String-Operatoren: contains, startswith, endswith, regex
    - List-Operatoren: in, not_in
    - Null-Checks: is_null, is_not_null
    - Logische Operatoren: AND, OR, NOT
    """

    # Type annotation: operator functions accept comparable types and return bool
    OPERATORS: Dict[str, Callable[[Union[str, int, float, bool, None], Union[str, int, float, bool, List, Tuple, Set, None]], bool]] = {
        "eq": operator.eq,
        "ne": operator.ne,
        "gt": operator.gt,
        "gte": operator.ge,
        "lt": operator.lt,
        "lte": operator.le,
        "contains": lambda a, b: b in str(a) if a else False,
        "startswith": lambda a, b: str(a).startswith(b) if a else False,
        "endswith": lambda a, b: str(a).endswith(b) if a else False,
        "in": lambda a, b: a in b if isinstance(b, (list, tuple, set)) else False,
        # BUG FIX: Bei ungueltigem Input False zurueckgeben (fail-safe, nicht fail-open!)
        "not_in": lambda a, b: a not in b if isinstance(b, (list, tuple, set)) else False,
        "is_null": lambda a, _: a is None,
        "is_not_null": lambda a, _: a is not None,
        "regex": lambda a, b: bool(re.match(b, str(a))) if a else False,
    }

    def match(self, conditions: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluiert Bedingungen gegen Daten.

        Args:
            conditions: Bedingungs-Definition (JSON)
            data: Event-Payload zur Pruefung

        Returns:
            True wenn Bedingungen erfuellt

        Beispiel conditions:
        {
            "operator": "AND",
            "conditions": [
                {"field": "amount", "op": "gt", "value": 1000},
                {"field": "category", "op": "eq", "value": "insurance"}
            ]
        }
        """
        if not conditions:
            return True  # Leere Bedingung = immer match

        # Top-Level Operator
        logical_op = conditions.get("operator", "AND").upper()
        condition_list = conditions.get("conditions", [])

        if not condition_list:
            # Einzelne Bedingung ohne Container
            if "field" in conditions:
                return self._evaluate_single(conditions, data)
            return True

        results = [self._evaluate_condition(c, data) for c in condition_list]

        if logical_op == "AND":
            return all(results)
        elif logical_op == "OR":
            return any(results)
        elif logical_op == "NOT":
            return not any(results)
        else:
            logger.warning("unknown_logical_operator", operator=logical_op)
            return False

    def _evaluate_condition(self, condition: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluiert eine einzelne Bedingung oder verschachtelte Gruppe."""
        if "operator" in condition and "conditions" in condition:
            # Verschachtelte Gruppe
            return self.match(condition, data)
        else:
            # Einzelne Bedingung
            return self._evaluate_single(condition, data)

    def _evaluate_single(self, condition: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluiert eine einzelne Feld-Bedingung."""
        field_path = condition.get("field", "")
        op_name = condition.get("op", "eq")
        expected = condition.get("value")

        # Nested field access: "payload.amount" -> data["payload"]["amount"]
        actual = self._get_nested_value(data, field_path)

        op_func = self.OPERATORS.get(op_name)
        if not op_func:
            logger.warning("unknown_operator", operator=op_name)
            return False

        try:
            return op_func(actual, expected)
        except (TypeError, ValueError) as e:
            logger.debug(
                "condition_evaluation_error",
                field=field_path,
                op=op_name,
                error=str(e)
            )
            return False

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Holt verschachtelten Wert aus Dict.

        Args:
            data: Source dictionary
            path: Dot-separated path (e.g., "payload.amount")

        Returns:
            Value at path or None
        """
        if not path:
            return None

        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

            if current is None:
                return None

        return current


# =============================================================================
# NOTIFICATION RULE ENGINE
# =============================================================================

class NotificationRuleEngine:
    """Event-basierte Notification Rule Engine.

    Koordiniert:
    - Regel-Auswertung gegen Events
    - Bedingungs-Matching
    - Quiet Hours / Rate Limiting
    - Delegation an bestehende Notification Services

    Thread-safe Singleton Pattern mit Double-Checked Locking.
    """

    _instance: Optional["NotificationRuleEngine"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "NotificationRuleEngine":
        """Singleton Pattern - Thread-safe mit Double-Checked Locking."""
        if cls._instance is None:
            with cls._class_lock:
                # Double-check nach Lock-Erwerb
                if cls._instance is None:
                    instance = super().__new__(cls)
                    # Initialisiere ALLE Attribute hier um Race Conditions zu vermeiden
                    instance._matcher = RuleConditionMatcher()
                    instance._event_bus = get_event_bus()
                    instance._notification_service = None
                    instance._push_service = None
                    instance._trigger_timestamps = {}
                    instance._daily_counts = {}
                    instance._rate_limit_lock = threading.Lock()  # Thread-safe Rate Limiting
                    instance._initialized = True
                    cls._instance = instance
                    logger.info("notification_rule_engine_initialized")
        return cls._instance

    def __init__(self) -> None:
        """Initialisiert die Rule Engine (no-op nach __new__)."""
        # Alle Initialisierung erfolgt in __new__ um Race Conditions zu vermeiden
        pass

    async def evaluate_event(
        self,
        db: AsyncSession,
        event: Event,
    ) -> EventEvaluationResult:
        """Evaluiert ein Event gegen alle aktiven Regeln.

        Args:
            db: Database Session
            event: Das zu evaluierende Event

        Returns:
            EventEvaluationResult mit allen Matches und Aktionen
        """
        import time
        start_time = time.perf_counter()

        result = EventEvaluationResult(
            event_id=event.event_id,
            event_type=event.event_type.value,
        )

        # Lade aktive Regeln fuer diesen Event-Typ
        rules = await self._get_active_rules(db, event.event_type.value, event.user_id)
        result.rules_checked = len(rules)

        # Evaluiere jede Regel
        for rule in rules:
            rule_start = time.perf_counter()

            rule_result = await self._evaluate_rule(rule, event)
            rule_result.evaluation_time_ms = (time.perf_counter() - rule_start) * 1000

            result.rule_results.append(rule_result)

            if rule_result.matched:
                result.rules_matched += 1
                result.actions_generated += len(rule_result.actions)
                RULES_EVALUATED.labels(event_type=event.event_type.value, matched="true").inc()
            elif rule_result.skipped_reason:
                result.rules_skipped += 1
                RULES_EVALUATED.labels(event_type=event.event_type.value, matched="skipped").inc()
            else:
                RULES_EVALUATED.labels(event_type=event.event_type.value, matched="false").inc()

        result.total_time_ms = (time.perf_counter() - start_time) * 1000
        RULE_EVALUATION_TIME.observe(result.total_time_ms / 1000)

        logger.info(
            "event_evaluated",
            event_id=str(event.event_id),
            event_type=event.event_type.value,
            rules_checked=result.rules_checked,
            rules_matched=result.rules_matched,
            actions_generated=result.actions_generated,
            time_ms=result.total_time_ms
        )

        return result

    async def _get_active_rules(
        self,
        db: AsyncSession,
        event_type: str,
        user_id: Optional[UUID] = None
    ) -> List[NotificationRule]:
        """Laedt aktive Regeln fuer einen Event-Typ.

        Args:
            db: Database Session
            event_type: Der Event-Typ (z.B. "document.ocr_completed")
            user_id: Optional: Nur Regeln dieses Users

        Returns:
            Liste aktiver NotificationRules
        """
        query = select(NotificationRule).where(
            and_(
                NotificationRule.enabled == True,
                NotificationRule.event_type == event_type
            )
        )

        if user_id:
            query = query.where(NotificationRule.user_id == user_id)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def _evaluate_rule(
        self,
        rule: NotificationRule,
        event: Event
    ) -> RuleEvaluationResult:
        """Evaluiert eine einzelne Regel gegen ein Event.

        Args:
            rule: Die zu pruefende Regel
            event: Das Event

        Returns:
            RuleEvaluationResult
        """
        result = RuleEvaluationResult(
            rule_id=rule.id,
            rule_name=rule.name,
            matched=False,
        )

        # 1. Quiet Hours pruefen
        if self._is_quiet_hours(rule):
            result.skipped_reason = "quiet_hours"
            RULES_SKIPPED_QUIET_HOURS.inc()
            return result

        # 2. Rate Limit pruefen
        if self._is_rate_limited(rule):
            result.skipped_reason = "rate_limited"
            RULES_SKIPPED_RATE_LIMIT.inc()
            return result

        # 3. Bedingungen pruefen
        event_data = self._build_event_data(event)
        conditions = rule.conditions or {}

        if not self._matcher.match(conditions, event_data):
            return result  # Keine Uebereinstimmung

        # 4. Match! Aktionen generieren
        result.matched = True
        result.actions = self._build_actions(rule, event)

        # 5. Rate Limit Tracking aktualisieren
        self._record_trigger(rule)

        return result

    def _is_quiet_hours(self, rule: NotificationRule) -> bool:
        """Prueft ob gerade Quiet Hours aktiv sind.

        Args:
            rule: Die Regel mit Quiet Hours Einstellungen

        Returns:
            True wenn in Quiet Hours
        """
        if not rule.quiet_hours_start or not rule.quiet_hours_end:
            return False

        try:
            tz = pytz.timezone(rule.timezone or "Europe/Berlin")
            now = datetime.now(tz).time()

            start = rule.quiet_hours_start
            end = rule.quiet_hours_end

            # Beruecksichtige Mitternachts-Uebergang (22:00 - 08:00)
            if start <= end:
                # Normaler Bereich (z.B. 09:00 - 17:00)
                return start <= now <= end
            else:
                # Ueber Mitternacht (z.B. 22:00 - 08:00)
                return now >= start or now <= end

        except Exception as e:
            logger.warning("quiet_hours_check_error", rule_id=str(rule.id), error=str(e))
            return False

    def _is_rate_limited(self, rule: NotificationRule) -> bool:
        """Prueft Rate Limits (cooldown + max_per_day).

        Args:
            rule: Die Regel mit Rate Limit Einstellungen

        Returns:
            True wenn Rate Limited
        """
        now = datetime.now(timezone.utc)

        # Cooldown pruefen
        if rule.cooldown_minutes and rule.cooldown_minutes > 0:
            last_trigger = self._trigger_timestamps.get(rule.id)
            if last_trigger:
                elapsed = (now - last_trigger).total_seconds() / 60
                if elapsed < rule.cooldown_minutes:
                    return True

        # Max per day pruefen
        if rule.max_per_day:
            today = now.date().isoformat()
            key = (rule.id, today)
            count = self._daily_counts.get(key, 0)
            if count >= rule.max_per_day:
                return True

        return False

    def _record_trigger(self, rule: NotificationRule) -> None:
        """Zeichnet einen Trigger fuer Rate Limiting auf."""
        now = datetime.now(timezone.utc)

        # Timestamp aktualisieren
        self._trigger_timestamps[rule.id] = now

        # Daily Count erhoehen
        today = now.date().isoformat()
        key = (rule.id, today)
        self._daily_counts[key] = self._daily_counts.get(key, 0) + 1

        # Alte Eintraege bereinigen (aelter als gestern)
        yesterday = (now - timedelta(days=1)).date().isoformat()
        self._daily_counts = {
            k: v for k, v in self._daily_counts.items()
            if k[1] >= yesterday
        }

    def _build_event_data(self, event: Event) -> Dict[str, Any]:
        """Baut evaluierbares Dict aus Event.

        Args:
            event: Das Event

        Returns:
            Dict mit allen Event-Daten
        """
        return {
            "event_id": str(event.event_id),
            "event_type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "user_id": str(event.user_id) if event.user_id else None,
            "space_id": str(event.space_id) if event.space_id else None,
            "payload": event.payload or {},
            **event.payload,  # Flatten payload fuer einfachen Zugriff
        }

    def _build_actions(
        self,
        rule: NotificationRule,
        event: Event
    ) -> List[NotificationAction]:
        """Generiert Aktionen aus Regel-Definition.

        Args:
            rule: Die gematchte Regel
            event: Das Event

        Returns:
            Liste von NotificationActions
        """
        actions_config = rule.actions or []
        if isinstance(actions_config, dict):
            actions_config = actions_config.get("actions", [])

        actions = []
        for action_def in actions_config:
            action_type_str = action_def.get("type", "in_app")
            try:
                action_type = ActionType(action_type_str)
            except ValueError:
                logger.warning(
                    "unknown_action_type",
                    rule_id=str(rule.id),
                    action_type=action_type_str
                )
                continue

            # Template-Variablen ersetzen
            rendered = self._render_action(action_def, event)

            action = NotificationAction(
                action_type=action_type,
                rule_id=rule.id,
                user_id=rule.user_id,
                event_type=event.event_type.value,
                payload=event.payload,
                priority=action_def.get("priority", rule.priority or "normal"),
                title=rendered.get("title"),
                message=rendered.get("body") or rendered.get("message"),
                action_url=rendered.get("action_url"),
                email_template=rendered.get("template"),
                email_subject=rendered.get("subject"),
                webhook_url=rendered.get("url"),
                push_data=rendered.get("data"),
            )
            actions.append(action)

        return actions

    def _render_action(
        self,
        action_def: Dict[str, Any],
        event: Event
    ) -> Dict[str, Any]:
        """Ersetzt Template-Variablen in Aktion.

        Unterstuetzt: {{event.payload.field}}, {{event.timestamp}}, etc.

        Args:
            action_def: Aktions-Definition
            event: Das Event fuer Variablen

        Returns:
            Gerenderte Aktion
        """
        result = {}
        event_data = self._build_event_data(event)

        for key, value in action_def.items():
            if isinstance(value, str):
                # Einfache Template-Ersetzung
                rendered = value
                for match in re.finditer(r"\{\{([^}]+)\}\}", value):
                    path = match.group(1).strip()
                    replacement = self._matcher._get_nested_value(event_data, path)
                    if replacement is not None:
                        rendered = rendered.replace(match.group(0), str(replacement))
                result[key] = rendered
            else:
                result[key] = value

        return result

    async def execute_actions(
        self,
        db: AsyncSession,
        actions: List[NotificationAction]
    ) -> Dict[str, int]:
        """Fuehrt Aktionen ueber bestehende Services aus.

        Args:
            db: Database Session
            actions: Liste von Aktionen

        Returns:
            Dict mit Zaehler pro Aktionstyp
        """
        # Lazy Import um Circular Dependencies zu vermeiden
        from app.services.notification_service import NotificationService
        from app.services.push_notification_service import PushNotificationService

        results = {t.value: 0 for t in ActionType}

        for action in actions:
            try:
                if action.action_type == ActionType.IN_APP:
                    try:
                        await self._execute_in_app(db, action)
                        results["in_app"] += 1
                        RULES_TRIGGERED.labels(
                            event_type=action.event_type,
                            action_type="in_app"
                        ).inc()
                    except Exception as e:
                        logger.error(
                            "in_app_action_error",
                            rule_id=str(action.rule_id),
                            error=str(e)
                        )
                        continue

                elif action.action_type == ActionType.PUSH:
                    push_service = PushNotificationService(db)
                    sent, _ = await push_service.send_to_user(
                        user_id=action.user_id,
                        title=action.title or "Benachrichtigung",
                        body=action.message or "",
                        category=action.event_type,
                        data=action.push_data
                    )
                    results["push"] += sent
                    RULES_TRIGGERED.labels(
                        event_type=action.event_type,
                        action_type="push"
                    ).inc()

                elif action.action_type == ActionType.EMAIL:
                    # Email des Users aus der DB holen
                    user_email = await self._get_user_email(db, action.user_id)
                    if user_email:
                        notification_service = NotificationService()
                        # Verwende Template aus Aktion oder fallback auf generischen Text
                        subject = action.email_subject or action.title or "Benachrichtigung"
                        body = action.message or ""

                        sent = await notification_service.email.send(
                            to_email=user_email,
                            subject=subject,
                            body=body,
                        )
                        if sent:
                            results["email"] += 1
                            RULES_TRIGGERED.labels(
                                event_type=action.event_type,
                                action_type="email"
                            ).inc()
                    else:
                        logger.warning(
                            "email_action_no_recipient",
                            rule_id=str(action.rule_id),
                            user_id=str(action.user_id)
                        )

                elif action.action_type == ActionType.WEBHOOK:
                    notification_service = NotificationService()
                    payload = {
                        "event_type": action.event_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": action.payload,
                        "title": action.title,
                        "message": action.message,
                    }
                    sent = await notification_service.webhook.send(
                        webhook_url=action.webhook_url,
                        payload=payload,
                    )
                    if sent:
                        results["webhook"] += 1
                        RULES_TRIGGERED.labels(
                            event_type=action.event_type,
                            action_type="webhook"
                        ).inc()

            except Exception as e:
                logger.error(
                    "action_execution_error",
                    action_type=action.action_type.value,
                    rule_id=str(action.rule_id),
                    error=str(e)
                )

        return results

    async def _execute_in_app(
        self,
        db: AsyncSession,
        action: NotificationAction
    ) -> None:
        """Erstellt In-App Notification in DB.

        Args:
            db: Database Session
            action: Die Aktion
        """
        notification = UserNotification(
            user_id=action.user_id,
            notification_type=action.event_type,
            title=action.title or "Benachrichtigung",
            message=action.message or "",
            action_url=action.action_url,
            is_read=False,
        )
        db.add(notification)
        await db.commit()

    async def _get_user_email(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> Optional[str]:
        """Holt die Email-Adresse eines Users aus der DB.

        Args:
            db: Database Session
            user_id: Die User-ID

        Returns:
            Email-Adresse oder None wenn nicht gefunden
        """
        user = await db.get(User, user_id)
        if user and user.email:
            return user.email
        return None

    async def update_rule_statistics(
        self,
        db: AsyncSession,
        rule_id: UUID,
        event_id: UUID
    ) -> None:
        """Aktualisiert Regel-Statistiken nach Trigger.

        Args:
            db: Database Session
            rule_id: ID der Regel
            event_id: ID des gematchten Events
        """
        from sqlalchemy import update

        stmt = (
            update(NotificationRule)
            .where(NotificationRule.id == rule_id)
            .values(
                trigger_count=NotificationRule.trigger_count + 1,
                last_triggered_at=datetime.now(timezone.utc),
                last_matched_event_id=event_id
            )
        )
        await db.execute(stmt)
        await db.commit()

    # =========================================================================
    # CRUD Operations fuer Regeln
    # =========================================================================

    async def create_rule(
        self,
        db: AsyncSession,
        user_id: UUID,
        name: str,
        event_type: str,
        conditions: Dict[str, Any],
        actions: List[Dict[str, Any]],
        **kwargs
    ) -> NotificationRule:
        """Erstellt eine neue Notification Rule.

        Args:
            db: Database Session
            user_id: Benutzer-ID
            name: Name der Regel
            event_type: Event-Typ (z.B. "document.ocr_completed")
            conditions: Bedingungs-Definition
            actions: Liste von Aktionen

        Returns:
            Erstellte NotificationRule
        """
        rule = NotificationRule(
            user_id=user_id,
            name=name,
            event_type=event_type,
            conditions=conditions,
            actions=actions,
            **kwargs
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

        logger.info(
            "notification_rule_created",
            rule_id=str(rule.id),
            user_id=str(user_id),
            event_type=event_type
        )

        return rule

    async def get_rules_for_user(
        self,
        db: AsyncSession,
        user_id: UUID,
        enabled_only: bool = False
    ) -> List[NotificationRule]:
        """Laedt alle Regeln eines Benutzers.

        Args:
            db: Database Session
            user_id: Benutzer-ID
            enabled_only: Nur aktive Regeln

        Returns:
            Liste von NotificationRules
        """
        query = select(NotificationRule).where(NotificationRule.user_id == user_id)

        if enabled_only:
            query = query.where(NotificationRule.enabled == True)

        query = query.order_by(NotificationRule.created_at.desc())

        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_rule(
        self,
        db: AsyncSession,
        rule_id: UUID,
        user_id: UUID,
        **updates
    ) -> Optional[NotificationRule]:
        """Aktualisiert eine Regel.

        Args:
            db: Database Session
            rule_id: ID der Regel
            user_id: Benutzer-ID (zur Validierung)
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierte Regel oder None
        """
        rule = await db.get(NotificationRule, rule_id)

        if not rule or rule.user_id != user_id:
            return None

        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        await db.commit()
        await db.refresh(rule)

        logger.info(
            "notification_rule_updated",
            rule_id=str(rule_id),
            updates=list(updates.keys())
        )

        return rule

    async def delete_rule(
        self,
        db: AsyncSession,
        rule_id: UUID,
        user_id: UUID
    ) -> bool:
        """Loescht eine Regel.

        Args:
            db: Database Session
            rule_id: ID der Regel
            user_id: Benutzer-ID (zur Validierung)

        Returns:
            True wenn geloescht
        """
        rule = await db.get(NotificationRule, rule_id)

        if not rule or rule.user_id != user_id:
            return False

        await db.delete(rule)
        await db.commit()

        logger.info(
            "notification_rule_deleted",
            rule_id=str(rule_id),
            user_id=str(user_id)
        )

        return True


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_rule_engine_instance: Optional[NotificationRuleEngine] = None


def get_notification_rule_engine() -> NotificationRuleEngine:
    """Factory-Funktion fuer NotificationRuleEngine Singleton.

    Returns:
        Die globale NotificationRuleEngine-Instanz
    """
    global _rule_engine_instance
    if _rule_engine_instance is None:
        _rule_engine_instance = NotificationRuleEngine()
    return _rule_engine_instance
