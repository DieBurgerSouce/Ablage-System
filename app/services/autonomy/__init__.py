# -*- coding: utf-8 -*-
"""
Autonomy Framework Services.

Enterprise Feature: Zero-Touch Operations Framework.

Module:
- autonomy_level: Autonomie-Level System (CONSERVATIVE → ZERO_TOUCH)
- action_queue: Warteschlange für KI-vorgeschlagene Aktionen
- confidence_router: Confidence-basiertes Routing
"""

from app.services.autonomy.autonomy_level import (
    ActionCategory,
    AutonomyDecision,
    AutonomyLevel,
    can_auto_execute,
)

from app.services.autonomy.action_queue import (
    ActionApprovalQueue,
    ActionPriority,
    ActionStatus,
    QueuedActionData,
    QueueStats,
    get_action_queue,
)

from app.services.autonomy.confidence_router import (
    ActionContext,
    ActionExecutor,
    ConfidenceRouter,
    RoutingDecision,
    RoutingResult,
    get_confidence_router,
)

__all__ = [
    # Autonomy Level
    "ActionCategory",
    "AutonomyDecision",
    "AutonomyLevel",
    "can_auto_execute",
    # Action Queue
    "ActionApprovalQueue",
    "ActionPriority",
    "ActionStatus",
    "QueuedActionData",
    "QueueStats",
    "get_action_queue",
    # Confidence Router
    "ActionContext",
    "ActionExecutor",
    "ConfidenceRouter",
    "RoutingDecision",
    "RoutingResult",
    "get_confidence_router",
]
