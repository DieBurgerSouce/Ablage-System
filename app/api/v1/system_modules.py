# -*- coding: utf-8 -*-
"""System-Modul-Status API (Odoo-Neuausrichtung 2026).

Liefert dem Frontend, welche optionalen Module aktiv bzw. eingefroren sind
(Sektions-Gating in der Sidebar/Navigation). Der Endpoint selbst wird in
``app/main.py`` IMMER registriert — er ist nie Teil eines Freeze-Moduls.

Hintergrund und Modul-Keys: ``app/core/module_registry.py``.
"""

from typing import List

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.core.module_registry import get_module_status
from app.db.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/system", tags=["System"])


class ModuleStatusResponse(BaseModel):
    """Aktiv-/Frozen-Status der optionalen Module."""

    active: List[str] = Field(
        default_factory=list,
        description="Aktive optionale Module (Modul-Keys)",
    )
    frozen: List[str] = Field(
        default_factory=list,
        description="Eingefrorene Module (Odoo übernimmt diese Domänen)",
    )


@router.get(
    "/modules",
    response_model=ModuleStatusResponse,
    summary="Modul-Status (aktiv/eingefroren)",
)
async def get_modules(
    current_user: User = Depends(get_current_user),
) -> ModuleStatusResponse:
    """Gibt aktive und eingefrorene optionale Module zurück.

    Eingefrorene Module sind backend-seitig deaktiviert (Router nicht
    registriert → 404); das Frontend blendet die zugehörigen Sektionen aus.
    """
    status = get_module_status()
    return ModuleStatusResponse(active=status["active"], frozen=status["frozen"])
