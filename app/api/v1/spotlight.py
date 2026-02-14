# -*- coding: utf-8 -*-
"""
Spotlight-Schnellsuche API.

Einzelner Endpunkt fuer die Cmd+K Spotlight-Suche.
Kombiniert Autocomplete, Dokumentsuche und Entity-Matching.
Ziel: <200ms Antwortzeit.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_detail
from app.db.models import User
from app.services.spotlight_service import (
    SpotlightResponse,
    get_spotlight_service,
)

router = APIRouter(prefix="/spotlight", tags=["spotlight"])


@router.get("", response_model=SpotlightResponse)
@limiter.limit("200/minute", key_func=get_user_identifier)
async def spotlight_search(
    request: Request,
    q: str = Query(
        "",
        max_length=200,
        description="Suchbegriff fuer Spotlight-Schnellsuche",
    ),
    limit: int = Query(
        8,
        ge=1,
        le=20,
        description="Maximale Anzahl Ergebnisse pro Kategorie",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SpotlightResponse:
    """
    Spotlight-Schnellsuche fuer Cmd+K Dialog.

    Gibt kombinierte Ergebnisse zurueck:
    - Navigation/Autocomplete Vorschlaege
    - Dokument-Treffer (Top N)
    - Entity-Matches (Kunden/Lieferanten)

    Bei leerem oder kurzem Query werden nur Navigations-Items zurueckgegeben.

    Args:
        request: FastAPI Request (fuer Rate Limiting)
        q: Suchbegriff
        limit: Maximale Anzahl Ergebnisse pro Kategorie
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        SpotlightResponse mit kombinierten Ergebnissen
    """
    try:
        service = get_spotlight_service()

        return await service.search(
            db=db,
            query=q,
            user_id=current_user.id,
            company_id=current_user.company_id,
            limit=limit,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Spotlight-Suche"),
        )
