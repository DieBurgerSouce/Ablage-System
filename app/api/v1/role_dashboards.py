# -*- coding: utf-8 -*-
"""
Rollen-basierte Dashboard API.

Endpunkte:
  GET /api/v1/dashboards/role              - Automatische Rollenerkennung
  GET /api/v1/dashboards/role/buchhaltung  - Buchhaltungs-Dashboard
  GET /api/v1/dashboards/role/management   - Management-Dashboard
  GET /api/v1/dashboards/role/sachbearbeitung - Sachbearbeitungs-Dashboard
  GET /api/v1/dashboards/role/admin        - Admin-Dashboard (nur Admins)

Alle Endpunkte verwenden einen 5-Minuten-Cache (TTL) um teure Aggregationen
zu vermeiden. Der Cache-Key ist company_id + role-Typ.

Feinpoliert und durchdacht - Phase 5.3: Rollen-basierte Dashboard APIs.
"""

import asyncio
import hashlib
import time
from typing import Dict, Optional, Tuple
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_log
from app.core.types import JSONDict
from app.db.models import User
from app.middleware.company_context import get_current_company_id
from app.services.role_dashboard_service import RoleDashboardService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboards/role", tags=["Rollen-Dashboards"])


# =============================================================================
# Einfacher In-Process-Cache (TTL 5 Minuten)
# =============================================================================

_CACHE_TTL_SECONDS: int = 300

# { cache_key: (timestamp, data) }
_cache: Dict[str, Tuple[float, JSONDict]] = {}
_cache_lock = asyncio.Lock()


def _cache_key(company_id: UUID, role_type: str) -> str:
    raw = f"{company_id}:{role_type}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _get_cached(key: str) -> Optional[JSONDict]:
    async with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.monotonic() - ts > _CACHE_TTL_SECONDS:
            del _cache[key]
            return None
        return data


async def _set_cached(key: str, data: JSONDict) -> None:
    async with _cache_lock:
        _cache[key] = (time.monotonic(), data)


# =============================================================================
# Rollen-Erkennung
# =============================================================================

_ROLE_BUCHHALTUNG = frozenset({"buchhaltung", "accountant", "buchhalter", "finance"})
_ROLE_MANAGEMENT = frozenset({"management", "manager", "ceo", "cfo", "geschaeftsfuehrung", "direktor"})
_ROLE_SACHBEARBEITUNG = frozenset({"sachbearbeitung", "sachbearbeiter", "clerk", "operator", "mitarbeiter"})


def _detect_role(user: User) -> str:
    """
    Bestimmt den Dashboard-Typ anhand der Benutzerrollen.

    Reihenfolge (absteigend nach Prioritaet):
    1. Superuser -> admin
    2. Rollenname in Rolle-Sets -> buchhaltung / management / sachbearbeitung
    3. Fallback -> sachbearbeitung
    """
    if user.is_superuser:
        return "admin"

    user_role_names = frozenset(
        r.name.lower() for r in (user.roles or [])
    )

    if user_role_names & _ROLE_MANAGEMENT:
        return "management"
    if user_role_names & _ROLE_BUCHHALTUNG:
        return "buchhaltung"
    if user_role_names & _ROLE_SACHBEARBEITUNG:
        return "sachbearbeitung"

    return "sachbearbeitung"


# =============================================================================
# Service-Fabrik (Singleton per Request reicht)
# =============================================================================

def _get_service() -> RoleDashboardService:
    return RoleDashboardService()


# =============================================================================
# Hilfsfunktion: Company-ID validiert holen
# =============================================================================

def _require_company_id(company_id: Optional[UUID]) -> UUID:
    """Wirft HTTP 400, wenn kein Company-Kontext gesetzt ist."""
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie zuerst eine Firma aus.",
        )
    return company_id


# =============================================================================
# GET /dashboards/role  - Automatische Rollenerkennung
# =============================================================================


@router.get(
    "",
    response_model=JSONDict,
    summary="Rollen-Dashboard (automatisch)",
    description=(
        "Erkennt die Rolle des eingeloggten Benutzers und gibt das passende "
        "Dashboard-Aggregat zurueck. Ergebnis wird 5 Minuten gecacht."
    ),
)
async def get_role_dashboard_auto(
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Automatische Dashboard-Auswahl basierend auf Benutzerrolle.

    **Rollenzuordnung:**
    - Superuser -> Admin-Dashboard
    - management / ceo / cfo -> Management-Dashboard
    - buchhaltung / accountant -> Buchhaltungs-Dashboard
    - sachbearbeitung / mitarbeiter -> Sachbearbeitungs-Dashboard (Standard)
    """
    cid = _require_company_id(company_id)
    detected = _detect_role(current_user)

    logger.info(
        "role_dashboard.auto_detect",
        user_id=str(current_user.id),
        company_id=str(cid),
        detected_role=detected,
    )

    return await _dispatch(detected, cid, current_user, db)


# =============================================================================
# GET /dashboards/role/buchhaltung
# =============================================================================


@router.get(
    "/buchhaltung",
    response_model=JSONDict,
    summary="Buchhaltungs-Dashboard",
    description=(
        "Aggregierte Kennzahlen fuer Buchhaltungs-Mitarbeiter: "
        "Offene Rechnungen, DATEV-Export-Status, Mahnwesen, Skonto-Fristen."
    ),
)
async def get_buchhaltung_dashboard(
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Buchhaltungs-Dashboard mit Rechnungs- und DATEV-Metriken."""
    cid = _require_company_id(company_id)
    return await _dispatch("buchhaltung", cid, current_user, db)


# =============================================================================
# GET /dashboards/role/management
# =============================================================================


@router.get(
    "/management",
    response_model=JSONDict,
    summary="Management-Dashboard",
    description=(
        "Executive KPIs fuer Management: Umsatz, Offene Posten, "
        "Cashflow-Prognose (30/60/90 Tage), Dokumenten-Uebersicht."
    ),
)
async def get_management_dashboard(
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Management-Dashboard mit KPIs und Cashflow-Prognose."""
    cid = _require_company_id(company_id)
    return await _dispatch("management", cid, current_user, db)


# =============================================================================
# GET /dashboards/role/sachbearbeitung
# =============================================================================


@router.get(
    "/sachbearbeitung",
    response_model=JSONDict,
    summary="Sachbearbeitungs-Dashboard",
    description=(
        "Operative Metriken fuer Sachbearbeiter: OCR-Queue, "
        "unkategorisierte Dokumente, Korrekturen, letzte Uploads."
    ),
)
async def get_sachbearbeitung_dashboard(
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Sachbearbeitungs-Dashboard mit OCR-Queue und Upload-Status."""
    cid = _require_company_id(company_id)
    return await _dispatch("sachbearbeitung", cid, current_user, db)


# =============================================================================
# GET /dashboards/role/admin
# =============================================================================


@router.get(
    "/admin",
    response_model=JSONDict,
    summary="Admin-Dashboard",
    description=(
        "System-Metriken und Verwaltungsdaten fuer Administratoren: "
        "CPU/RAM/Disk/GPU, Audit-Log-Zusammenfassung, Integrations-Status, "
        "Feature-Flags, Nutzeraktivitaet. Nur fuer Superuser zugaenglich."
    ),
)
async def get_admin_dashboard(
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Admin-Dashboard mit System-Health und Verwaltungsmetriken.

    **Zugriff:** Nur Superuser.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren haben Zugriff auf das Admin-Dashboard.",
        )

    cid = _require_company_id(company_id)
    return await _dispatch("admin", cid, current_user, db)


# =============================================================================
# Interne Dispatch-Funktion mit Cache
# =============================================================================


async def _dispatch(
    role_type: str,
    company_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> JSONDict:
    """
    Laedt Dashboard-Daten aus Cache oder berechnet sie neu.

    Args:
        role_type: "buchhaltung" | "management" | "sachbearbeitung" | "admin"
        company_id: Aktuelle Company-ID
        current_user: Eingeloggter Benutzer (fuer Logging)
        db: Async-Datenbank-Session

    Returns:
        Dashboard-Dict (JSON-serialisierbar)

    Raises:
        HTTPException 500: Bei unerwarteten Service-Fehlern
    """
    key = _cache_key(company_id, role_type)
    cached = await _get_cached(key)
    if cached is not None:
        logger.debug(
            "role_dashboard.cache_hit",
            user_id=str(current_user.id),
            company_id=str(company_id),
            role_type=role_type,
        )
        return cached

    logger.info(
        "role_dashboard.compute",
        user_id=str(current_user.id),
        company_id=str(company_id),
        role_type=role_type,
    )

    service = _get_service()
    try:
        if role_type == "buchhaltung":
            data: Dict[str, object] = await service.get_buchhaltung_dashboard(company_id, db)
        elif role_type == "management":
            data = await service.get_management_dashboard(company_id, db)
        elif role_type == "sachbearbeitung":
            data = await service.get_sachbearbeitung_dashboard(company_id, db)
        elif role_type == "admin":
            data = await service.get_admin_dashboard(company_id, db)
        else:
            raise ValueError(f"Unbekannter Dashboard-Typ: {role_type}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "role_dashboard.compute_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            role_type=role_type,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Laden des {role_type.capitalize()}-Dashboards.",
        )

    # Daten sind JSON-serialisierbar (Dict[str, object] -> JSONDict)
    # Wir casten explizit fuer den Cache-Store
    json_data: JSONDict = data  # type: ignore[assignment]
    await _set_cached(key, json_data)
    return json_data
