# -*- coding: utf-8 -*-
"""Tenant Onboarding Wizard API - Geführter Setup-Prozess.

Stellt Endpoints bereit für:
- 7-Schritt Onboarding-Wizard für neue Firmen
- Fortschrittsverfolgung
- Post-Setup Checkliste
- Onboarding überspringen/zurücksetzen

Vision 2.0 - Feature #11 (Januar 2026)
"""

from typing import Optional, List, Dict

from app.core.types import JSONDict, JSONValue
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field, validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User, Company
from app.api.dependencies import get_current_active_user
from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ==================== Onboarding Steps Definition ====================


ONBOARDING_STEPS = [
    {
        "id": "company",
        "order": 1,
        "title": "Firmendaten",
        "description": "Grundlegende Firmendaten eingeben (Name, Adresse, USt-IdNr)",
        "icon": "building-2",
        "required": True,
        "help_url": "/help/articles/company-setup",
    },
    {
        "id": "industry",
        "order": 2,
        "title": "Branche & Größe",
        "description": "Branche und Unternehmensgröße für passende Benchmarks",
        "icon": "factory",
        "required": False,
        "help_url": "/help/articles/industry-selection",
    },
    {
        "id": "users",
        "order": 3,
        "title": "Benutzer einladen",
        "description": "Team-Mitglieder zur Firma einladen",
        "icon": "users",
        "required": False,
        "help_url": "/help/articles/user-invitation",
    },
    {
        "id": "datasources",
        "order": 4,
        "title": "Datenquellen",
        "description": "Email-Import, Ordner-Überwachung oder Lexware-Import einrichten",
        "icon": "database",
        "required": False,
        "help_url": "/help/articles/data-sources",
    },
    {
        "id": "ocr",
        "order": 5,
        "title": "OCR-Backend",
        "description": "OCR-Engine wählen (GPU-beschleunigt oder CPU)",
        "icon": "scan",
        "required": False,
        "help_url": "/help/articles/ocr-backends",
    },
    {
        "id": "test_document",
        "order": 6,
        "title": "Test-Dokument",
        "description": "Erstes Dokument hochladen und OCR testen",
        "icon": "file-check",
        "required": False,
        "help_url": "/help/articles/first-document",
    },
    {
        "id": "complete",
        "order": 7,
        "title": "Abschluss",
        "description": "Setup abschließen und Checkliste anzeigen",
        "icon": "check-circle",
        "required": True,
        "help_url": "/help/articles/onboarding-complete",
    },
]

# Post-Setup Checkliste
POST_SETUP_CHECKLIST = [
    {
        "id": "first_document",
        "title": "Erstes Dokument hochgeladen",
        "description": "Laden Sie Ihr erstes Dokument hoch",
        "category": "documents",
    },
    {
        "id": "first_ocr",
        "title": "Erste OCR durchgeführt",
        "description": "Lassen Sie ein Dokument mit OCR verarbeiten",
        "category": "ocr",
    },
    {
        "id": "first_entity",
        "title": "Erster Geschäftspartner angelegt",
        "description": "Legen Sie Ihren ersten Kunden oder Lieferanten an",
        "category": "entities",
    },
    {
        "id": "first_invoice",
        "title": "Erste Rechnung erfasst",
        "description": "Erfassen Sie Ihre erste Eingangs- oder Ausgangsrechnung",
        "category": "invoices",
    },
    {
        "id": "bank_connected",
        "title": "Bank verbunden",
        "description": "Verbinden Sie Ihr Bankkonto für automatischen Abgleich",
        "category": "banking",
    },
    {
        "id": "workflow_created",
        "title": "Ersten Workflow erstellt",
        "description": "Erstellen Sie einen Genehmigungsworkflow",
        "category": "workflows",
    },
]


# ==================== Schemas ====================


class OnboardingStep(BaseModel):
    """Onboarding-Schritt Schema."""

    id: str = Field(..., description="Schritt-ID")
    order: int = Field(..., description="Reihenfolge")
    title: str = Field(..., description="Titel auf Deutsch")
    description: str = Field(..., description="Beschreibung auf Deutsch")
    icon: str = Field(..., description="Icon-Name (Lucide)")
    required: bool = Field(..., description="Pflichtschritt")
    completed: bool = Field(False, description="Abgeschlossen")
    completed_at: Optional[str] = Field(None, description="Abschlusszeitpunkt (ISO)")
    help_url: Optional[str] = Field(None, description="Hilfe-URL")


class OnboardingStatus(BaseModel):
    """Onboarding-Status Schema."""

    started_at: Optional[str] = Field(None, description="Startzeitpunkt (ISO)")
    completed_at: Optional[str] = Field(None, description="Abschlusszeitpunkt (ISO)")
    skipped: bool = Field(False, description="Wurde übersprungen")
    current_step: int = Field(1, description="Aktueller Schritt (1-7)")
    total_steps: int = Field(7, description="Gesamtzahl Schritte")
    completed_steps: List[str] = Field(default_factory=list, description="Abgeschlossene Schritt-IDs")
    progress_percent: int = Field(0, description="Fortschritt in Prozent")
    is_complete: bool = Field(False, description="Vollständig abgeschlossen")
    steps: List[OnboardingStep] = Field(default_factory=list, description="Alle Schritte mit Status")


class ChecklistItem(BaseModel):
    """Checklisten-Eintrag Schema."""

    id: str = Field(..., description="Item-ID")
    title: str = Field(..., description="Titel auf Deutsch")
    description: str = Field(..., description="Beschreibung")
    category: str = Field(..., description="Kategorie")
    completed: bool = Field(False, description="Erledigt")
    completed_at: Optional[str] = Field(None, description="Erledigt am (ISO)")


class ChecklistStatus(BaseModel):
    """Checklisten-Status Schema."""

    items: List[ChecklistItem]
    completed_count: int
    total_count: int
    progress_percent: int


class UpdateStepRequest(BaseModel):
    """Request zum Aktualisieren eines Schritts."""

    step_data: Optional[JSONDict] = Field(
        None,
        description="Optionale Schritt-Daten (z.B. gewaehlte Branche)",
        max_length=50,  # SECURITY: Max 50 Keys im Dict
    )

    @validator("step_data")
    def validate_step_data(cls, v: Optional[JSONDict]) -> Optional[JSONDict]:
        """SECURITY: Validiere JSONB-Payload gegen DoS und Injection."""
        if v is None:
            return v

        # Max Größe: 10KB
        import json
        json_str = json.dumps(v)
        if len(json_str) > 10240:
            raise ValueError("step_data darf maximal 10KB gross sein")

        # Max Tiefe: 3 Ebenen
        def check_depth(obj: JSONValue, depth: int = 0) -> int:
            if depth > 3:
                raise ValueError("step_data darf maximal 3 Ebenen tief sein")
            if isinstance(obj, dict):
                if len(obj) > 50:
                    raise ValueError("Dictionaries duerfen maximal 50 Keys haben")
                return max((check_depth(v, depth + 1) for v in obj.values()), default=depth)
            if isinstance(obj, list):
                if len(obj) > 100:
                    raise ValueError("Listen duerfen maximal 100 Elemente haben")
                return max((check_depth(item, depth + 1) for item in obj), default=depth)
            return depth

        check_depth(v)

        # Erlaubte Datentypen: str, int, bool, None, list, dict
        def check_types(obj: JSONValue) -> None:
            if obj is None:
                return
            if isinstance(obj, (str, int, bool, float)):
                if isinstance(obj, str) and len(obj) > 1000:
                    raise ValueError("Strings duerfen maximal 1000 Zeichen haben")
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if not isinstance(k, str) or len(k) > 100:
                        raise ValueError("Dict-Keys müssen Strings sein (max 100 Zeichen)")
                    check_types(v)
                return
            if isinstance(obj, list):
                for item in obj:
                    check_types(item)
                return
            raise ValueError(f"Nicht erlaubter Datentyp: {type(obj).__name__}")

        check_types(v)
        return v


class SuccessResponse(BaseModel):
    """Erfolgs-Antwort."""

    success: bool
    message: str


# ==================== Helper Functions ====================


def _get_onboarding_status_from_preferences(preferences: JSONDict) -> JSONDict:
    """Extrahiert Onboarding-Status aus User/Company Preferences."""
    return preferences.get("onboarding", {})


def _build_onboarding_status(
    onboarding_data: JSONDict,
) -> OnboardingStatus:
    """Baut OnboardingStatus aus gespeicherten Daten."""
    completed_steps = onboarding_data.get("completed_steps", [])
    skipped = onboarding_data.get("skipped", False)
    started_at = onboarding_data.get("started_at")
    completed_at = onboarding_data.get("completed_at")

    # Aktuellen Schritt bestimmen
    current_step = 1
    for i, step in enumerate(ONBOARDING_STEPS):
        if step["id"] not in completed_steps:
            current_step = i + 1
            break
    else:
        current_step = len(ONBOARDING_STEPS)

    # Steps mit Status bauen
    steps = []
    for step_def in ONBOARDING_STEPS:
        step_completed = step_def["id"] in completed_steps
        step_completed_at = onboarding_data.get("step_completed_at", {}).get(step_def["id"])

        steps.append(OnboardingStep(
            id=step_def["id"],
            order=step_def["order"],
            title=step_def["title"],
            description=step_def["description"],
            icon=step_def["icon"],
            required=step_def["required"],
            completed=step_completed,
            completed_at=step_completed_at,
            help_url=step_def.get("help_url"),
        ))

    # Fortschritt berechnen
    progress = int((len(completed_steps) / len(ONBOARDING_STEPS)) * 100)

    return OnboardingStatus(
        started_at=started_at,
        completed_at=completed_at,
        skipped=skipped,
        current_step=current_step,
        total_steps=len(ONBOARDING_STEPS),
        completed_steps=completed_steps,
        progress_percent=progress,
        is_complete=len(completed_steps) == len(ONBOARDING_STEPS) or completed_at is not None,
        steps=steps,
    )


def _build_checklist_status(
    checklist_data: JSONDict,
) -> ChecklistStatus:
    """Baut ChecklistStatus aus gespeicherten Daten."""
    completed_items = checklist_data.get("completed_items", {})

    items = []
    for item_def in POST_SETUP_CHECKLIST:
        item_completed = item_def["id"] in completed_items
        item_completed_at = completed_items.get(item_def["id"])

        items.append(ChecklistItem(
            id=item_def["id"],
            title=item_def["title"],
            description=item_def["description"],
            category=item_def["category"],
            completed=item_completed,
            completed_at=item_completed_at,
        ))

    completed_count = len(completed_items)
    total_count = len(POST_SETUP_CHECKLIST)
    progress = int((completed_count / total_count) * 100) if total_count > 0 else 0

    return ChecklistStatus(
        items=items,
        completed_count=completed_count,
        total_count=total_count,
        progress_percent=progress,
    )


# ==================== Endpoints ====================


@router.get(
    "/status",
    response_model=OnboardingStatus,
    summary="Onboarding-Status abrufen",
    description="Holt den aktuellen Onboarding-Fortschritt des Benutzers.",
)
async def get_onboarding_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OnboardingStatus:
    """Holt den Onboarding-Status."""
    preferences = current_user.preferences or {}
    onboarding_data = _get_onboarding_status_from_preferences(preferences)

    # Wenn noch nicht gestartet, initialisieren
    if not onboarding_data.get("started_at"):
        onboarding_data["started_at"] = utc_now().isoformat()
        onboarding_data["completed_steps"] = []
        onboarding_data["step_completed_at"] = {}

        preferences["onboarding"] = onboarding_data
        current_user.preferences = preferences
        await db.commit()

    return _build_onboarding_status(onboarding_data)


@router.patch(
    "/step/{step_id}",
    response_model=OnboardingStatus,
    summary="Schritt abschließen",
    description="Markiert einen Onboarding-Schritt als abgeschlossen.",
)
async def complete_step(
    step_id: str = Path(..., description="Schritt-ID"),
    request: Optional[UpdateStepRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OnboardingStatus:
    """Markiert einen Schritt als abgeschlossen."""
    # Schritt validieren
    valid_step_ids = [s["id"] for s in ONBOARDING_STEPS]
    if step_id not in valid_step_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Schritt: {step_id}. Gültig: {valid_step_ids}",
        )

    preferences = current_user.preferences or {}
    onboarding_data = _get_onboarding_status_from_preferences(preferences)

    # Initialisieren falls nötig
    if "completed_steps" not in onboarding_data:
        onboarding_data["completed_steps"] = []
    if "step_completed_at" not in onboarding_data:
        onboarding_data["step_completed_at"] = {}
    if "step_data" not in onboarding_data:
        onboarding_data["step_data"] = {}

    # Schritt als erledigt markieren
    if step_id not in onboarding_data["completed_steps"]:
        onboarding_data["completed_steps"].append(step_id)
        onboarding_data["step_completed_at"][step_id] = utc_now().isoformat()

    # Schritt-Daten speichern (z.B. gewaehlte Branche)
    if request and request.step_data:
        onboarding_data["step_data"][step_id] = request.step_data

    # Prüfen ob komplett
    if len(onboarding_data["completed_steps"]) == len(ONBOARDING_STEPS):
        onboarding_data["completed_at"] = utc_now().isoformat()

    preferences["onboarding"] = onboarding_data
    current_user.preferences = preferences
    await db.commit()

    logger.info(
        "onboarding_step_completed",
        user_id=str(current_user.id),
        step_id=step_id,
    )

    return _build_onboarding_status(onboarding_data)


@router.post(
    "/skip",
    response_model=OnboardingStatus,
    summary="Onboarding überspringen",
    description="Überspringt das Onboarding für erfahrene Benutzer.",
)
async def skip_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OnboardingStatus:
    """Überspringt das Onboarding."""
    preferences = current_user.preferences or {}
    onboarding_data = _get_onboarding_status_from_preferences(preferences)

    onboarding_data["skipped"] = True
    onboarding_data["completed_at"] = utc_now().isoformat()

    preferences["onboarding"] = onboarding_data
    current_user.preferences = preferences
    await db.commit()

    logger.info(
        "onboarding_skipped",
        user_id=str(current_user.id),
    )

    return _build_onboarding_status(onboarding_data)


@router.post(
    "/reset",
    response_model=OnboardingStatus,
    summary="Onboarding zurücksetzen",
    description="Setzt das Onboarding zurück, um es erneut zu durchlaufen.",
)
async def reset_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OnboardingStatus:
    """Setzt das Onboarding zurück."""
    preferences = current_user.preferences or {}

    # Onboarding-Daten zurücksetzen
    preferences["onboarding"] = {
        "started_at": utc_now().isoformat(),
        "completed_at": None,
        "skipped": False,
        "completed_steps": [],
        "step_completed_at": {},
        "step_data": {},
    }

    current_user.preferences = preferences
    await db.commit()

    logger.info(
        "onboarding_reset",
        user_id=str(current_user.id),
    )

    return _build_onboarding_status(preferences["onboarding"])


@router.get(
    "/checklist",
    response_model=ChecklistStatus,
    summary="Post-Setup Checkliste",
    description="Holt die Checkliste für Aufgaben nach dem Onboarding.",
)
async def get_checklist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChecklistStatus:
    """Holt die Post-Setup Checkliste."""
    preferences = current_user.preferences or {}
    checklist_data = preferences.get("checklist", {})

    return _build_checklist_status(checklist_data)


@router.patch(
    "/checklist/{item_id}",
    response_model=ChecklistStatus,
    summary="Checklisten-Eintrag abhaken",
    description="Markiert einen Checklisten-Eintrag als erledigt.",
)
async def complete_checklist_item(
    item_id: str = Path(..., description="Item-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChecklistStatus:
    """Markiert Checklisten-Eintrag als erledigt."""
    # Item validieren
    valid_item_ids = [i["id"] for i in POST_SETUP_CHECKLIST]
    if item_id not in valid_item_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiges Item: {item_id}",
        )

    preferences = current_user.preferences or {}
    checklist_data = preferences.get("checklist", {})

    if "completed_items" not in checklist_data:
        checklist_data["completed_items"] = {}

    # Item als erledigt markieren
    if item_id not in checklist_data["completed_items"]:
        checklist_data["completed_items"][item_id] = utc_now().isoformat()

    preferences["checklist"] = checklist_data
    current_user.preferences = preferences
    await db.commit()

    logger.info(
        "checklist_item_completed",
        user_id=str(current_user.id),
        item_id=item_id,
    )

    return _build_checklist_status(checklist_data)


@router.get(
    "/steps",
    response_model=List[JSONDict],
    summary="Alle Onboarding-Schritte",
    description="Holt die Definition aller Onboarding-Schritte.",
)
async def get_all_steps(
    current_user: User = Depends(get_current_active_user),
) -> List[JSONDict]:
    """Holt alle Onboarding-Schritte."""
    return ONBOARDING_STEPS


@router.get(
    "/step/{step_id}",
    response_model=JSONDict,
    summary="Einzelnen Schritt abrufen",
    description="Holt Details zu einem spezifischen Onboarding-Schritt.",
)
async def get_step(
    step_id: str = Path(..., description="Schritt-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONDict:
    """Holt Details zu einem Schritt."""
    # Schritt finden
    step = None
    for s in ONBOARDING_STEPS:
        if s["id"] == step_id:
            step = s.copy()
            break

    if not step:
        raise HTTPException(
            status_code=404,
            detail=f"Schritt nicht gefunden: {step_id}",
        )

    # Status hinzufuegen
    preferences = current_user.preferences or {}
    onboarding_data = _get_onboarding_status_from_preferences(preferences)
    completed_steps = onboarding_data.get("completed_steps", [])

    step["completed"] = step_id in completed_steps
    step["completed_at"] = onboarding_data.get("step_completed_at", {}).get(step_id)
    step["data"] = onboarding_data.get("step_data", {}).get(step_id, {})

    return step


@router.get(
    "/progress",
    response_model=JSONDict,
    summary="Fortschritts-Zusammenfassung",
    description="Kompakte Fortschrittsanzeige für Dashboard-Widgets.",
)
async def get_progress_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONDict:
    """Holt kompakte Fortschritts-Zusammenfassung."""
    preferences = current_user.preferences or {}
    onboarding_data = _get_onboarding_status_from_preferences(preferences)
    checklist_data = preferences.get("checklist", {})

    onboarding_status = _build_onboarding_status(onboarding_data)
    checklist_status = _build_checklist_status(checklist_data)

    return {
        "onboarding": {
            "progress_percent": onboarding_status.progress_percent,
            "current_step": onboarding_status.current_step,
            "total_steps": onboarding_status.total_steps,
            "is_complete": onboarding_status.is_complete,
            "skipped": onboarding_status.skipped,
        },
        "checklist": {
            "completed_count": checklist_status.completed_count,
            "total_count": checklist_status.total_count,
            "progress_percent": checklist_status.progress_percent,
        },
        "needs_attention": not onboarding_status.is_complete and not onboarding_status.skipped,
    }
