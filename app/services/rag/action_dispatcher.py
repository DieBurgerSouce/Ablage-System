"""Action Dispatcher fuer RAG Agent Tool-Calls.

Parst LLM-Antworten auf Tool-Call JSON-Bloecke,
validiert Parameter und dispatcht an AIActionService.
"""

from datetime import datetime, timezone
from typing import Optional, Dict
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.rag.tool_registry import ToolCall, ToolDefinition, get_tool_registry
from app.services.rag.ai_action_service import (
    get_ai_action_service,
    AIActionService,
)
from app.api.schemas.rag import (
    AIActionType,
    AIActionRequest,
    AIActionResult,
    AIActionStatus,
    AIActionAutonomyLevel,
)
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# TOOL NAME -> ACTION TYPE MAPPING
# =============================================================================

TOOL_TO_ACTION_MAP: Dict[str, AIActionType] = {
    "search_documents": AIActionType.SEARCH_DOCUMENTS,
    "get_invoice_status": AIActionType.ANALYZE_ENTITY,
    "filter_documents": AIActionType.SEARCH_DOCUMENTS,
    "get_entity_summary": AIActionType.ANALYZE_ENTITY,
    "move_document": AIActionType.CATEGORIZE_DOCUMENT,  # Closest match
    "tag_document": AIActionType.TAG_DOCUMENT,
    "categorize_document": AIActionType.CATEGORIZE_DOCUMENT,
    "create_reminder": AIActionType.CREATE_REMINDER,
    "get_daily_agenda": AIActionType.GET_DAILY_AGENDA,
    "compare_expenses": AIActionType.COMPARE_EXPENSES,
    "get_skonto_opportunities": AIActionType.GET_SKONTO,
    "get_overdue_invoices": AIActionType.SEARCH_DOCUMENTS,
    "book_invoice": AIActionType.BOOK_INVOICE,
    "approve_document": AIActionType.APPROVE_VALIDATION,
}


# =============================================================================
# ACTION DISPATCHER
# =============================================================================

class ActionDispatcher:
    """Dispatcht Tool-Calls an AIActionService."""

    def __init__(
        self,
        ai_action_service: Optional[AIActionService] = None
    ) -> None:
        """Initialisiert den Action Dispatcher.

        Args:
            ai_action_service: Optional AIActionService Instanz
        """
        self._ai_action_service = ai_action_service or get_ai_action_service()
        self._tool_registry = get_tool_registry()

    async def dispatch(
        self,
        tool_call: ToolCall,
        user: User,
        db: AsyncSession,
        context_id: Optional[UUID] = None
    ) -> AIActionResult:
        """Dispatcht einen Tool-Call.

        Args:
            tool_call: Geparster Tool-Call
            user: Aktueller User
            db: Database Session
            context_id: Optional Kontext-ID (Document-ID)

        Returns:
            AIActionResult mit Status und Details
        """
        start_time = datetime.now(timezone.utc)

        logger.info(
            "dispatching_tool_call",
            tool_name=tool_call.tool_name,
            user_id=str(user.id),
            params_count=len(tool_call.parameters)
        )

        try:
            # 1. Tool-Definition holen
            tool_def = self._tool_registry.get_tool(tool_call.tool_name)
            if not tool_def:
                return AIActionResult(
                    action_id=uuid4(),
                    action_type=AIActionType.SEARCH_DOCUMENTS,  # Fallback
                    status=AIActionStatus.FAILED,
                    message=f"Unbekanntes Tool: {tool_call.tool_name}",
                    execution_time_ms=self._elapsed_ms(start_time)
                )

            # 2. Permission-Check
            user_level = self._get_user_level(user)
            if not self._check_permission(tool_def.permission_level, user_level):
                return AIActionResult(
                    action_id=uuid4(),
                    action_type=TOOL_TO_ACTION_MAP.get(tool_call.tool_name, AIActionType.SEARCH_DOCUMENTS),
                    status=AIActionStatus.FAILED,
                    message="Keine Berechtigung fuer diese Aktion.",
                    execution_time_ms=self._elapsed_ms(start_time)
                )

            # 3. Parameter validieren
            validation_error = self._validate_parameters(tool_def, tool_call.parameters)
            if validation_error:
                return AIActionResult(
                    action_id=uuid4(),
                    action_type=TOOL_TO_ACTION_MAP.get(tool_call.tool_name, AIActionType.SEARCH_DOCUMENTS),
                    status=AIActionStatus.FAILED,
                    message=f"Ungueltige Parameter: {validation_error}",
                    execution_time_ms=self._elapsed_ms(start_time)
                )

            # 4. AIActionRequest erstellen
            action_type = TOOL_TO_ACTION_MAP.get(tool_call.tool_name)
            if not action_type:
                return AIActionResult(
                    action_id=uuid4(),
                    action_type=AIActionType.SEARCH_DOCUMENTS,
                    status=AIActionStatus.FAILED,
                    message=f"Kein Action-Mapping fuer Tool: {tool_call.tool_name}",
                    execution_time_ms=self._elapsed_ms(start_time)
                )

            action_request = AIActionRequest(
                action_type=action_type,
                context_id=context_id,
                parameters=tool_call.parameters,
                auto_execute=not tool_def.requires_confirmation
            )

            # 5. An AIActionService dispatchen
            result = await self._ai_action_service.execute_action(
                db=db,
                user=user,
                request=action_request
            )

            # 6. Audit Log
            logger.info(
                "tool_call_dispatched",
                tool_name=tool_call.tool_name,
                action_type=action_type.value,
                status=result.status.value,
                user_id=str(user.id),
                execution_time_ms=result.execution_time_ms
            )

            return result

        except Exception as e:
            logger.error(
                "tool_call_dispatch_failed",
                tool_name=tool_call.tool_name,
                user_id=str(user.id),
                **safe_error_log(e)
            )

            return AIActionResult(
                action_id=uuid4(),
                action_type=TOOL_TO_ACTION_MAP.get(
                    tool_call.tool_name,
                    AIActionType.SEARCH_DOCUMENTS
                ),
                status=AIActionStatus.FAILED,
                message=safe_error_detail(e, "Tool-Ausfuehrung"),
                execution_time_ms=self._elapsed_ms(start_time)
            )

    async def confirm_action(
        self,
        action_id: UUID,
        user: User,
        db: AsyncSession
    ) -> AIActionResult:
        """Bestaetigt eine ausstehende Aktion.

        Args:
            action_id: ID der Aktion
            user: Aktueller User
            db: Database Session

        Returns:
            AIActionResult
        """
        return await self._ai_action_service.confirm_action(
            db=db,
            user=user,
            action_id=action_id,
            confirmed=True
        )

    async def reject_action(
        self,
        action_id: UUID,
        user: User,
        db: AsyncSession
    ) -> AIActionResult:
        """Lehnt eine ausstehende Aktion ab.

        Args:
            action_id: ID der Aktion
            user: Aktueller User
            db: Database Session

        Returns:
            AIActionResult
        """
        return await self._ai_action_service.confirm_action(
            db=db,
            user=user,
            action_id=action_id,
            confirmed=False
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_user_level(self, user: User) -> str:
        """Bestimmt User-Level.

        Args:
            user: User Objekt

        Returns:
            viewer, editor, oder admin
        """
        autonomy_level = self._ai_action_service.get_autonomy_level(user)

        if autonomy_level == AIActionAutonomyLevel.ADMIN:
            return "admin"
        elif autonomy_level == AIActionAutonomyLevel.EDITOR:
            return "editor"
        else:
            return "viewer"

    def _check_permission(self, required_level: str, user_level: str) -> bool:
        """Prueft ob User-Level ausreicht.

        Args:
            required_level: Erforderliches Level
            user_level: User Level

        Returns:
            True wenn berechtigt
        """
        level_hierarchy = {
            "viewer": 1,
            "editor": 2,
            "admin": 3
        }

        required = level_hierarchy.get(required_level, 1)
        user = level_hierarchy.get(user_level, 1)

        return user >= required

    def _validate_parameters(
        self,
        tool_def: ToolDefinition,
        parameters: Dict[str, object]
    ) -> Optional[str]:
        """Validiert Tool-Parameter.

        Args:
            tool_def: Tool-Definition
            parameters: Uebergebene Parameter

        Returns:
            Fehlermeldung oder None
        """
        # Check required parameters
        for param in tool_def.parameters:
            if param.required and param.name not in parameters:
                return f"Erforderlicher Parameter fehlt: {param.name}"

        # Type validation (basic)
        for param_name, param_value in parameters.items():
            # Find param definition
            param_def = next(
                (p for p in tool_def.parameters if p.name == param_name),
                None
            )

            if not param_def:
                logger.warning(
                    "unknown_parameter",
                    param_name=param_name,
                    tool_name=tool_def.name
                )
                continue

            # Basic type check
            if param_def.type.value == "string" and not isinstance(param_value, str):
                return f"Parameter {param_name} muss ein String sein"
            elif param_def.type.value == "integer" and not isinstance(param_value, int):
                return f"Parameter {param_name} muss eine Zahl sein"
            elif param_def.type.value == "boolean" and not isinstance(param_value, bool):
                return f"Parameter {param_name} muss true/false sein"
            elif param_def.type.value == "array" and not isinstance(param_value, list):
                return f"Parameter {param_name} muss eine Liste sein"

        return None

    def _elapsed_ms(self, start_time: datetime) -> int:
        """Berechnet verstrichene Zeit in Millisekunden.

        Args:
            start_time: Start-Zeit

        Returns:
            Millisekunden
        """
        delta = datetime.now(timezone.utc) - start_time
        return int(delta.total_seconds() * 1000)


# =============================================================================
# SINGLETON
# =============================================================================

_action_dispatcher: Optional[ActionDispatcher] = None


def get_action_dispatcher() -> ActionDispatcher:
    """Gibt Action Dispatcher Singleton zurueck.

    Returns:
        ActionDispatcher Instanz
    """
    global _action_dispatcher
    if _action_dispatcher is None:
        _action_dispatcher = ActionDispatcher()
    return _action_dispatcher
