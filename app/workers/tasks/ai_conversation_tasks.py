# -*- coding: utf-8 -*-
"""
AI Conversation Celery Tasks.

Asynchrone Verarbeitung von KI-Konversationsnachrichten und Aktionen.
Nutzt FinanceAssistantService fuer die eigentliche KI-Verarbeitung.

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from celery import shared_task
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    name="ai_conversations.process_message",
    queue="ai",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def process_ai_message(
    self,
    conversation_id: str,
    message_id: str,
    user_id: str,
    company_id: Optional[str] = None,
    content: str = "",
) -> dict:
    """
    Verarbeitet eine Benutzer-Nachricht mit dem KI-Assistenten.

    Args:
        conversation_id: UUID der Konversation
        message_id: UUID der Benutzer-Nachricht
        user_id: UUID des Benutzers
        company_id: UUID der Company (optional)
        content: Nachrichteninhalt

    Returns:
        Dict mit Verarbeitungsergebnis
    """
    import asyncio

    task_id = self.request.id or str(uuid.uuid4())

    logger.info(
        "process_ai_message_started",
        task_id=task_id,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
    )

    async def _process():
        from app.services.ai.finance_assistant_service import (
            FinanceAssistantService,
            AssistantContext,
        )
        from app.db.models_ai_conversation import (
            AIConversation,
            AIConversationMessage,
            AIMessageRole,
        )
        from app.db.models import User

        async with get_async_session_context() as db:
            # Lade Benutzer und Konversation
            user = await db.get(User, uuid.UUID(user_id))
            conversation = await db.get(AIConversation, uuid.UUID(conversation_id))

            if not user or not conversation:
                logger.warning(
                    "process_ai_message_invalid_refs",
                    task_id=task_id,
                    user_found=user is not None,
                    conversation_found=conversation is not None,
                )
                return {
                    "status": "error",
                    "error": "Benutzer oder Konversation nicht gefunden",
                }

            # Erstelle Kontext
            context = AssistantContext(
                user_id=user.id,
                user_role=user.role or "user",
                company_id=uuid.UUID(company_id) if company_id else None,
                session_id=conversation.session_id or str(conversation.id),
            )

            # Verarbeite Nachricht
            service = FinanceAssistantService(db=db)

            try:
                response = await service.process_message(
                    message=content,
                    context=context,
                    persist=True,
                )

                # Speichere Assistenten-Antwort
                assistant_message = AIConversationMessage(
                    id=uuid.uuid4(),
                    conversation_id=conversation.id,
                    role=AIMessageRole.ASSISTANT.value,
                    content=response.message,
                    intent=response.intent.value if response.intent else None,
                    confidence=response.confidence,
                    search_results_count=response.result_count,
                    actions_proposed=len(response.actions) if response.actions else None,
                    processing_time_ms=response.processing_time_ms,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(assistant_message)

                # Update Konversation
                conversation.message_count += 1
                conversation.last_message_at = datetime.now(timezone.utc)

                await db.commit()

                logger.info(
                    "process_ai_message_completed",
                    task_id=task_id,
                    conversation_id=conversation_id,
                    response_intent=response.intent.value if response.intent else None,
                    success=response.success,
                )

                return {
                    "status": "success",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "response_id": str(assistant_message.id),
                    "intent": response.intent.value if response.intent else None,
                    "success": response.success,
                }

            except Exception as e:
                logger.error(
                    "process_ai_message_service_error",
                    task_id=task_id,
                    conversation_id=conversation_id,
                    error_type=type(e).__name__,
                )
                return {
                    "status": "error",
                    "error": str(e),
                }

    return asyncio.run(_process())


@celery_app.task(
    bind=True,
    name="ai_conversations.execute_action",
    queue="ai",
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def execute_ai_action(
    self,
    action_id: str,
    conversation_id: str,
    user_id: str,
    company_id: Optional[str] = None,
) -> dict:
    """
    Fuehrt eine bestaetigte KI-Aktion aus.

    Args:
        action_id: UUID der Aktion
        conversation_id: UUID der Konversation
        user_id: UUID des Benutzers
        company_id: UUID der Company (optional)

    Returns:
        Dict mit Ausfuehrungsergebnis
    """
    import asyncio

    task_id = self.request.id or str(uuid.uuid4())

    logger.info(
        "execute_ai_action_started",
        task_id=task_id,
        action_id=action_id,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    async def _execute():
        from app.services.ai.finance_assistant_service import (
            FinanceAssistantService,
            AssistantContext,
            ActionProposal,
            ActionType,
        )
        from app.db.models_ai_conversation import (
            AIConversationAction,
            AIActionStatus,
        )
        from app.db.models import User

        async with get_async_session_context() as db:
            # Lade Benutzer und Aktion
            user = await db.get(User, uuid.UUID(user_id))
            action = await db.get(AIConversationAction, uuid.UUID(action_id))

            if not user or not action:
                logger.warning(
                    "execute_ai_action_invalid_refs",
                    task_id=task_id,
                    user_found=user is not None,
                    action_found=action is not None,
                )
                return {
                    "status": "error",
                    "error": "Benutzer oder Aktion nicht gefunden",
                }

            # Erstelle Kontext
            context = AssistantContext(
                user_id=user.id,
                user_role=user.role or "user",
                company_id=uuid.UUID(company_id) if company_id else action.company_id,
            )

            # Erstelle ActionProposal aus DB-Action
            try:
                action_type = ActionType(action.action_type)
            except ValueError:
                logger.warning(
                    "execute_ai_action_invalid_type",
                    task_id=task_id,
                    action_type=action.action_type,
                )
                # Markiere als fehlgeschlagen
                action.status = AIActionStatus.FAILED.value
                action.error_message = f"Unbekannter Aktionstyp: {action.action_type}"
                await db.commit()
                return {
                    "status": "error",
                    "error": f"Unbekannter Aktionstyp: {action.action_type}",
                }

            proposal = ActionProposal(
                action_type=action_type,
                description=action.description or "",
                parameters=action.parameters or {},
                requires_confirmation=action.requires_confirmation,
            )

            # Fuehre Aktion aus
            service = FinanceAssistantService(db=db)

            try:
                result = await service.execute_action(
                    action=proposal,
                    context=context,
                    action_id=uuid.UUID(action_id),
                )

                logger.info(
                    "execute_ai_action_completed",
                    task_id=task_id,
                    action_id=action_id,
                    success=result.success,
                )

                return {
                    "status": "success" if result.success else "failed",
                    "action_id": action_id,
                    "message": result.message,
                    "result_count": result.result_count,
                }

            except Exception as e:
                # Markiere Aktion als fehlgeschlagen
                action.status = AIActionStatus.FAILED.value
                action.error_message = str(e)
                await db.commit()

                logger.error(
                    "execute_ai_action_service_error",
                    task_id=task_id,
                    action_id=action_id,
                    error_type=type(e).__name__,
                )
                return {
                    "status": "error",
                    "error": str(e),
                }

    return asyncio.run(_execute())
