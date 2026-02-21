# -*- coding: utf-8 -*-
"""AI Chat API - Eingebetteter KI-Assistent Endpunkte.

Stellt REST-API-Endpunkte für den eingebetteten KI-Assistenten bereit:
- POST /api/v1/ai-chat/message              : Nachricht senden, KI-Antwort erhalten
- GET  /api/v1/ai-chat/sessions             : Chat-Sessions des Benutzers auflisten
- GET  /api/v1/ai-chat/sessions/{session_id}: Einzelne Session mit Verlauf abrufen
- DELETE /api/v1/ai-chat/sessions/{session_id}: Session löschen

Feinpoliert und durchdacht - Enterprise AI Chat API.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.middleware.company_context import require_company
from app.services.ai_chat_service import (
    AIChatService,
    DataAttachment,
    get_ai_chat_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ai-chat", tags=["AI Chat"])

# Maximale Nachrichtenlänge für API-Eingabe
_MAX_MESSAGE_LENGTH = 10_000
_MAX_SESSION_ID_LENGTH = 100


# =============================================================================
# Pydantic Schemas
# =============================================================================


class SendMessageRequest(BaseModel):
    """Anfrage zum Senden einer Chat-Nachricht."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_MESSAGE_LENGTH,
        description="Chat-Nachricht des Benutzers (max. 10.000 Zeichen)",
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=_MAX_SESSION_ID_LENGTH,
        description="Session-ID für Gesprächskontinuität (neue Session wenn leer)",
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        """Bereinigt die Nachricht von führenden/trailing Leerzeichen.

        Args:
            v: Eingabe-Nachricht

        Returns:
            Bereinigte Nachricht
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("Die Nachricht darf nicht leer sein.")
        return stripped

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiert die Session-ID auf erlaubte Zeichen.

        Args:
            v: Session-ID oder None

        Returns:
            Validierte Session-ID oder None
        """
        if v is None:
            return None
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', v):
            raise ValueError("Session-ID enthält ungültige Zeichen.")
        return v


class DataAttachmentResponse(BaseModel):
    """Daten-Anhang in der KI-Antwort."""

    attachment_type: str = Field(description="Typ: 'invoices', 'documents', 'entities', 'stats'")
    title: str = Field(description="Titel des Anhangs")
    data: List[Dict[str, object]] = Field(description="Anhang-Daten als Liste")

    model_config = {"from_attributes": True}


class SendMessageResponse(BaseModel):
    """Antwort auf eine Chat-Nachricht."""

    session_id: str = Field(description="Session-ID für Folgeanfragen")
    message: str = Field(description="KI-Antwort auf Deutsch")
    thinking: Optional[str] = Field(
        default=None,
        description="Chain-of-Thought (nur wenn aktiviert)",
    )
    attachments: List[DataAttachmentResponse] = Field(
        default_factory=list,
        description="Optionale Daten-Anhänge (Rechnungen, Dokumente, etc.)",
    )
    model_used: str = Field(description="Verwendetes KI-Modell")
    generation_time_ms: int = Field(description="Antwortzeit in Millisekunden")
    tokens_used: int = Field(description="Verwendete Output-Token")

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    """Einzelne Nachricht im Chat-Verlauf."""

    role: str = Field(description="Rolle: 'user' oder 'assistant'")
    content: str = Field(description="Nachrichteninhalt")
    timestamp: str = Field(description="ISO-Zeitstempel der Nachricht")

    model_config = {"from_attributes": True}


class ChatSessionSummaryResponse(BaseModel):
    """Kurzübersicht einer Chat-Session."""

    session_id: str = Field(description="Eindeutige Session-ID")
    title: str = Field(description="Session-Titel (aus erster Nachricht)")
    message_count: int = Field(description="Anzahl Nachrichten in der Session")
    created_at: str = Field(description="ISO-Zeitstempel der Erstellung")
    updated_at: str = Field(description="ISO-Zeitstempel der letzten Aktivität")

    model_config = {"from_attributes": True}


class ChatSessionDetailResponse(BaseModel):
    """Detaillierte Chat-Session mit vollem Verlauf."""

    session_id: str
    title: str
    message_count: int
    messages: List[ChatMessageResponse]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DeleteSessionResponse(BaseModel):
    """Antwort nach dem Löschen einer Session."""

    success: bool
    message: str


# =============================================================================
# API Endpunkte
# =============================================================================


@router.post(
    "/message",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Nachricht an KI-Assistenten senden",
    description=(
        "Sendet eine Nachricht an den eingebetteten KI-Assistenten und erhält "
        "eine kontextsensitive Antwort auf Deutsch. "
        "Der Assistent hat Zugriff auf Rechnungen, Dokumente und Geschäftspartner."
    ),
)
async def send_message(
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
    service: AIChatService = Depends(get_ai_chat_service),
) -> SendMessageResponse:
    """Sendet eine Nachricht an den KI-Assistenten.

    Der Assistent:
    - Erkennt automatisch den Kontext (Rechnungen, Dokumente, Compliance)
    - Lädt relevante Unternehmensdaten für kontextuelle Antworten
    - Antwortet ausschließlich auf Deutsch
    - Schützt PII (keine vollständigen IBANs oder Kundennummern)

    Args:
        request: Nachrichten-Anfrage mit optionaler Session-ID
        db: Datenbank-Session
        current_user: Eingeloggter Benutzer
        company: Aktive Firma (aus Middleware)
        service: AI Chat Service

    Returns:
        KI-Antwort mit optionalen Daten-Anhängen
    """
    try:
        chat_response = await service.process_message(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
            message=request.message,
            session_id=request.session_id,
        )

        # Attachments umwandeln
        attachment_responses = [
            DataAttachmentResponse(
                attachment_type=att.attachment_type,
                title=att.title,
                data=att.data,
            )
            for att in chat_response.attachments
        ]

        return SendMessageResponse(
            session_id=chat_response.session_id,
            message=chat_response.message,
            thinking=chat_response.thinking,
            attachments=attachment_responses,
            model_used=chat_response.model_used,
            generation_time_ms=chat_response.generation_time_ms,
            tokens_used=chat_response.tokens_used,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "ai_chat_nachricht_api_fehler",
            **safe_error_log(exc),
            company_id=str(company.id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Die Nachricht konnte nicht verarbeitet werden. Bitte versuchen Sie es erneut.",
        )


@router.get(
    "/sessions",
    response_model=List[ChatSessionSummaryResponse],
    summary="Chat-Sessions auflisten",
    description="Gibt alle Chat-Sessions des aktuellen Benutzers zurück, neueste zuerst.",
)
async def list_sessions(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximale Anzahl Sessions",
    ),
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
    service: AIChatService = Depends(get_ai_chat_service),
) -> List[ChatSessionSummaryResponse]:
    """Listet Chat-Sessions des Benutzers auf.

    Gibt Sessions sortiert nach letzter Aktivität zurück (neueste zuerst).
    Sessions sind auf den aktuellen Benutzer und die aktive Firma beschränkt.

    Args:
        limit: Maximale Anzahl zurückgegebener Sessions
        current_user: Eingeloggter Benutzer
        company: Aktive Firma
        service: AI Chat Service

    Returns:
        Liste von Session-Zusammenfassungen (ohne Nachrichteninhalte)
    """
    sessions = service.get_sessions(
        company_id=company.id,
        user_id=current_user.id,
        limit=limit,
    )

    return [
        ChatSessionSummaryResponse(
            session_id=s.session_id,
            title=s.title,
            message_count=s.message_count,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
    summary="Chat-Session mit Verlauf abrufen",
    description="Gibt eine einzelne Chat-Session mit dem vollständigen Nachrichtenverlauf zurück.",
)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
    service: AIChatService = Depends(get_ai_chat_service),
) -> ChatSessionDetailResponse:
    """Gibt eine Chat-Session mit vollständigem Verlauf zurück.

    Erzwingt Mandantenisolierung: Nur eigene Sessions sind zugänglich.

    Args:
        session_id: Session-ID
        current_user: Eingeloggter Benutzer
        company: Aktive Firma (Sicherheitsprüfung)
        service: AI Chat Service

    Returns:
        Session mit Nachrichten-Verlauf (System-Prompt ausgeblendet)

    Raises:
        HTTPException 404: Wenn Session nicht gefunden oder kein Zugriff
    """
    # Eingabe-Validierung
    import re
    if not session_id or not re.match(r'^[a-zA-Z0-9_\-]+$', session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Session-ID.",
        )

    session = service.get_session(
        session_id=session_id,
        company_id=company.id,
        user_id=current_user.id,
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat-Session nicht gefunden.",
        )

    # System-Prompt aus dem Verlauf entfernen (intern, nicht für Frontend)
    visible_messages = [
        ChatMessageResponse(
            role=m.role,
            content=m.content,
            timestamp=m.timestamp.isoformat(),
        )
        for m in session.messages
        if m.role != "system"
    ]

    return ChatSessionDetailResponse(
        session_id=session.session_id,
        title=session.title,
        message_count=session.message_count,
        messages=visible_messages,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=DeleteSessionResponse,
    summary="Chat-Session löschen",
    description="Löscht eine Chat-Session und den gesamten Nachrichtenverlauf (DSGVO).",
)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
    service: AIChatService = Depends(get_ai_chat_service),
) -> DeleteSessionResponse:
    """Löscht eine Chat-Session.

    Ermöglicht Benutzern das Löschen ihres Chatverlaufs (DSGVO Art. 17).
    Nur eigene Sessions können gelöscht werden.

    Args:
        session_id: Session-ID
        current_user: Eingeloggter Benutzer
        company: Aktive Firma (Sicherheitsprüfung)
        service: AI Chat Service

    Returns:
        Bestätigung der Löschung

    Raises:
        HTTPException 404: Wenn Session nicht gefunden
    """
    import re
    if not session_id or not re.match(r'^[a-zA-Z0-9_\-]+$', session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Session-ID.",
        )

    deleted = service.delete_session(
        session_id=session_id,
        company_id=company.id,
        user_id=current_user.id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat-Session nicht gefunden.",
        )

    logger.info(
        "ai_chat_session_geloescht",
        session_id=session_id,
        company_id=str(company.id),
        user_id=str(current_user.id),
    )

    return DeleteSessionResponse(
        success=True,
        message="Chat-Session wurde erfolgreich gelöscht.",
    )
