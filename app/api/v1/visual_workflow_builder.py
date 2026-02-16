# -*- coding: utf-8 -*-
"""Visual Workflow Builder API Endpoints.

API für den No-Code Workflow-Editor.

Endpoints:
- GET /visual-builder/blocks - Verfügbare Blocks
- GET /visual-builder/categories - Block-Kategorien
- GET /visual-builder/templates - Workflow-Templates
- POST /visual-builder/create - Workflow aus visuellem Editor erstellen
- PUT /visual-builder/{workflow_id} - Workflow aktualisieren
- POST /visual-builder/simulate - Workflow simulieren (Dry-Run)
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.core.types import JSONDict, JSONValue

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator, validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.api.v1.workflows import get_user_company_id
from app.core.jsonb_validators import validate_jsonb_payload
from app.db.models import User
from app.services.workflow.visual_workflow_builder_service import (
    VisualWorkflowBuilderService,
    BlockType,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/visual-builder", tags=["visual-workflow-builder"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class BlockDefinitionResponse(BaseModel):
    """Block-Definition für Frontend."""

    id: str
    type: str
    label: str
    description: str
    category: str
    icon: str
    config_schema: JSONDict
    inputs: List[str]
    outputs: List[str]


class CategoryResponse(BaseModel):
    """Block-Kategorie."""

    id: str
    label: str
    description: str


class TemplateResponse(BaseModel):
    """Workflow-Template."""

    id: str
    name: str
    description: str
    category: str
    blocks: List[JSONDict]
    edges: List[JSONDict]


class VisualBlockCreate(BaseModel):
    """Block im visuellen Editor."""

    id: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=100)
    label: Optional[str] = Field(None, max_length=255)
    config: JSONDict = Field(default_factory=dict)
    position_x: float = 0.0
    position_y: float = 0.0

    @validator("config")
    def validate_config(cls, v: JSONDict) -> JSONDict:
        """SECURITY: Validiere Block-Config gegen DoS und Injection (CWE-20)."""
        if not v:
            return v

        import json
        json_str = json.dumps(v)

        # Max Größe: 50KB pro Block-Config
        if len(json_str) > 51200:
            raise ValueError("config darf maximal 50KB gross sein")

        # Max 100 Keys
        if len(v) > 100:
            raise ValueError("config darf maximal 100 Keys haben")

        # Max Tiefe: 5 Ebenen (Workflows können komplex sein)
        def check_depth(obj: JSONValue, depth: int = 0) -> int:
            if depth > 5:
                raise ValueError("config darf maximal 5 Ebenen tief sein")
            if isinstance(obj, dict):
                return max((check_depth(val, depth + 1) for val in obj.values()), default=depth)
            if isinstance(obj, list):
                return max((check_depth(item, depth + 1) for item in obj), default=depth)
            return depth

        check_depth(v)

        # Nur erlaubte Datentypen
        def check_types(obj: JSONValue) -> None:
            if obj is None:
                return
            if isinstance(obj, (str, int, bool, float)):
                if isinstance(obj, str) and len(obj) > 5000:
                    raise ValueError("Strings duerfen maximal 5000 Zeichen haben")
                return
            if isinstance(obj, dict):
                for k, val in obj.items():
                    if not isinstance(k, str) or len(k) > 100:
                        raise ValueError("Dict-Keys müssen Strings sein (max 100 Zeichen)")
                    check_types(val)
                return
            if isinstance(obj, list):
                if len(obj) > 500:
                    raise ValueError("Listen duerfen maximal 500 Elemente haben")
                for item in obj:
                    check_types(item)
                return
            raise ValueError(f"Nicht erlaubter Datentyp: {type(obj).__name__}")

        check_types(v)
        return v


class VisualEdgeCreate(BaseModel):
    """Verbindung im visuellen Editor."""

    id: Optional[str] = Field(None, max_length=200)  # SECURITY: Max length
    source_id: str = Field(..., min_length=1, max_length=100)
    target_id: str = Field(..., min_length=1, max_length=100)
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    label: Optional[str] = None


class VisualWorkflowCreate(BaseModel):
    """Workflow aus visuellem Editor."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    blocks: List[VisualBlockCreate]
    edges: List[VisualEdgeCreate]
    variables: Optional[JSONDict] = None

    @model_validator(mode="after")
    def validate_blocks_and_edges(self) -> "VisualWorkflowCreate":
        """Validiert Blocks und Edges."""
        if not self.blocks:
            raise ValueError("Mindestens ein Block erforderlich")

        # Block-IDs sammeln
        block_ids = {b.id for b in self.blocks}

        # Edges prüfen
        for edge in self.edges:
            if edge.source_id not in block_ids:
                raise ValueError(f"Unbekannter Quell-Block: {edge.source_id}")
            if edge.target_id not in block_ids:
                raise ValueError(f"Unbekannter Ziel-Block: {edge.target_id}")

        return self


class VisualWorkflowUpdate(BaseModel):
    """Update eines visuellen Workflows."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    blocks: List[VisualBlockCreate]
    edges: List[VisualEdgeCreate]


class SimulationRequest(BaseModel):
    """Anfrage für Workflow-Simulation."""

    blocks: List[VisualBlockCreate]
    edges: List[VisualEdgeCreate]
    test_data: JSONDict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_test_data(self) -> "SimulationRequest":
        """Validiert Test-Daten."""
        if self.test_data:
            validate_jsonb_payload(self.test_data, max_depth=5)
        return self


class SimulationResponse(BaseModel):
    """Ergebnis der Workflow-Simulation."""

    success: bool
    execution_path: List[str]
    simulated_outputs: JSONDict
    warnings: List[str]
    errors: List[str]
    duration_estimate_seconds: int


class WorkflowCreatedResponse(BaseModel):
    """Antwort bei Workflow-Erstellung."""

    workflow_id: str
    name: str
    message: str
    validation_errors: List[str]


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/blocks",
    response_model=List[BlockDefinitionResponse],
    summary="Verfügbare Blocks abrufen",
)
async def get_available_blocks(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[BlockDefinitionResponse]:
    """Gibt alle verfügbaren Workflow-Blocks zurück.

    Diese Blocks können im visuellen Editor per Drag&Drop verwendet werden.
    """
    service = VisualWorkflowBuilderService(db)
    blocks = service.get_available_blocks(category=category)

    return [BlockDefinitionResponse(**block) for block in blocks]


@router.get(
    "/categories",
    response_model=List[CategoryResponse],
    summary="Block-Kategorien abrufen",
)
async def get_block_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CategoryResponse]:
    """Gibt alle Block-Kategorien zurück."""
    service = VisualWorkflowBuilderService(db)
    categories = service.get_block_categories()

    return [CategoryResponse(**cat) for cat in categories]


@router.get(
    "/templates",
    response_model=List[TemplateResponse],
    summary="Workflow-Templates abrufen",
)
async def get_workflow_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TemplateResponse]:
    """Gibt vordefinierte Workflow-Templates zurück.

    Diese Templates können als Startpunkt für eigene Workflows verwendet werden.
    """
    service = VisualWorkflowBuilderService(db)
    templates = service.get_workflow_templates()

    return [TemplateResponse(**template) for template in templates]


@router.post(
    "/create",
    response_model=WorkflowCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Workflow aus visuellem Editor erstellen",
)
async def create_visual_workflow(
    data: VisualWorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowCreatedResponse:
    """Erstellt einen Workflow aus der visuellen Editor-Definition.

    Der Workflow wird validiert und bei Erfolg erstellt.
    Validierungsfehler werden in der Antwort zurückgegeben.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = VisualWorkflowBuilderService(db)

    # Blocks und Edges konvertieren
    blocks = [
        {
            "id": b.id,
            "type": b.type,
            "label": b.label,
            "config": b.config,
            "position_x": b.position_x,
            "position_y": b.position_y,
        }
        for b in data.blocks
    ]

    edges = [
        {
            "id": e.id or f"{e.source_id}-{e.target_id}",
            "source_id": e.source_id,
            "target_id": e.target_id,
            "source_handle": e.source_handle,
            "target_handle": e.target_handle,
            "label": e.label,
        }
        for e in data.edges
    ]

    # Workflow erstellen
    workflow_id, errors = await service.create_workflow_from_visual(
        user_id=current_user.id,
        company_id=company_id,
        name=data.name,
        blocks=blocks,
        edges=edges,
        description=data.description,
        variables=data.variables,
    )

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Workflow-Validierung fehlgeschlagen",
                "errors": errors,
            },
        )

    return WorkflowCreatedResponse(
        workflow_id=str(workflow_id),
        name=data.name,
        message="Workflow erfolgreich erstellt",
        validation_errors=[],
    )


@router.put(
    "/{workflow_id}",
    response_model=WorkflowCreatedResponse,
    summary="Workflow aktualisieren",
)
async def update_visual_workflow(
    workflow_id: UUID,
    data: VisualWorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowCreatedResponse:
    """Aktualisiert einen Workflow aus dem visuellen Editor."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = VisualWorkflowBuilderService(db)

    blocks = [
        {
            "id": b.id,
            "type": b.type,
            "label": b.label,
            "config": b.config,
            "position_x": b.position_x,
            "position_y": b.position_y,
        }
        for b in data.blocks
    ]

    edges = [
        {
            "id": e.id or f"{e.source_id}-{e.target_id}",
            "source_id": e.source_id,
            "target_id": e.target_id,
            "source_handle": e.source_handle,
            "target_handle": e.target_handle,
            "label": e.label,
        }
        for e in data.edges
    ]

    success, errors = await service.update_workflow_from_visual(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
        blocks=blocks,
        edges=edges,
        name=data.name,
        description=data.description,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Workflow-Update fehlgeschlagen",
                "errors": errors,
            },
        )

    return WorkflowCreatedResponse(
        workflow_id=str(workflow_id),
        name=data.name or "Aktualisiert",
        message="Workflow erfolgreich aktualisiert",
        validation_errors=[],
    )


@router.post(
    "/simulate",
    response_model=SimulationResponse,
    summary="Workflow simulieren (Dry-Run)",
)
async def simulate_workflow(
    data: SimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SimulationResponse:
    """Simuliert einen Workflow ohne ihn zu erstellen.

    Nuetzlich um den Ausführungspfad zu visualisieren
    und potenzielle Probleme zu erkennen.
    """
    service = VisualWorkflowBuilderService(db)

    blocks = [
        {
            "id": b.id,
            "type": b.type,
            "label": b.label,
            "config": b.config,
            "position_x": b.position_x,
            "position_y": b.position_y,
        }
        for b in data.blocks
    ]

    edges = [
        {
            "id": e.id or f"{e.source_id}-{e.target_id}",
            "source_id": e.source_id,
            "target_id": e.target_id,
            "source_handle": e.source_handle,
            "target_handle": e.target_handle,
        }
        for e in data.edges
    ]

    result = await service.simulate_workflow(
        blocks=blocks,
        edges=edges,
        test_data=data.test_data,
    )

    return SimulationResponse(
        success=result.success,
        execution_path=result.execution_path,
        simulated_outputs=result.simulated_outputs,
        warnings=result.warnings,
        errors=result.errors,
        duration_estimate_seconds=result.duration_estimate_seconds,
    )
