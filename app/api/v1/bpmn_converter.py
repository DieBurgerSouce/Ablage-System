# -*- coding: utf-8 -*-
"""BPMN 2.0 Import/Export API Endpoints.

Endpunkte fuer:
- Import: BPMN 2.0 XML importieren und Workflow erstellen
- Export: Workflow als BPMN 2.0 XML exportieren
- Validate: BPMN 2.0 XML validieren ohne Import
- Preview: BPMN Diagramm als SVG vorschauen

Kompatibel mit:
- Camunda Modeler
- Activiti
- jBPM
- Flowable
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail
from app.db.models import User, Workflow
from app.services.workflow.bpmn_converter import (
    BPMNConverter,
    ValidationResult,
    WorkflowDefinition,
    get_bpmn_converter,
)
from app.services.workflow.workflow_service import WorkflowService

router = APIRouter(prefix="/bpmn-converter", tags=["BPMN 2.0 Converter"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class BPMNImportRequest(BaseModel):
    """Request fuer BPMN Import via JSON Body."""
    bpmn_xml: str = Field(..., min_length=100, description="BPMN 2.0 XML Content")
    name: Optional[str] = Field(None, max_length=255, description="Optionaler Workflow-Name")
    description: Optional[str] = Field(None, description="Optionale Beschreibung")
    activate: bool = Field(False, description="Workflow direkt aktivieren")


class BPMNExportRequest(BaseModel):
    """Request fuer BPMN Export aus internem Format."""
    nodes: List[JSONDict] = Field(..., description="ReactFlow Nodes")
    edges: List[JSONDict] = Field(..., description="ReactFlow Edges")
    name: str = Field(..., min_length=1, max_length=255, description="Workflow-Name")
    trigger_type: str = Field("manual", description="Trigger-Typ")
    trigger_config: Optional[JSONDict] = Field(None, description="Trigger-Konfiguration")


class BPMNValidateRequest(BaseModel):
    """Request fuer BPMN Validierung."""
    bpmn_xml: str = Field(..., min_length=100, description="BPMN 2.0 XML Content")


class ValidationErrorResponse(BaseModel):
    """Validierungsfehler in Response."""
    code: str
    message: str
    element_id: Optional[str] = None


class ValidationResultResponse(BaseModel):
    """Response fuer Validierung."""
    valid: bool
    errors: List[ValidationErrorResponse]
    warnings: List[ValidationErrorResponse]


class WorkflowImportResponse(BaseModel):
    """Response nach erfolgreichem Import."""
    id: UUID
    name: str
    description: Optional[str] = None
    trigger_type: str
    is_active: bool
    node_count: int
    edge_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BPMNExportResponse(BaseModel):
    """Response mit BPMN XML."""
    bpmn_xml: str
    workflow_id: str
    workflow_name: str
    process_count: int
    exported_at: datetime


class BPMNPreviewResponse(BaseModel):
    """Response fuer BPMN Preview."""
    workflow_id: str
    preview_available: bool
    message: str


# =============================================================================
# Import Endpoints
# =============================================================================

@router.post(
    "/import",
    response_model=WorkflowImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="BPMN 2.0 XML importieren"
)
async def import_bpmn(
    request: BPMNImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> WorkflowImportResponse:
    """Importiert BPMN 2.0 XML und erstellt einen Workflow.

    Der BPMN-Inhalt wird geparst und in das interne Workflow-Format
    konvertiert. Der resultierende Workflow kann anschliessend im
    Visual Workflow Builder bearbeitet werden.

    Unterstuetzt werden:
    - Start/End Events
    - User Tasks, Service Tasks, Script Tasks
    - Exclusive, Parallel, Inclusive Gateways
    - Sequence Flows mit Conditions
    - Timer Events
    """
    converter = get_bpmn_converter()
    workflow_service = WorkflowService(db)

    try:
        # BPMN validieren
        validation_result = converter.validate(request.bpmn_xml)
        if not validation_result.valid:
            error_messages = [f"{e.code}: {e.message}" for e in validation_result.errors]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Ungueltiges BPMN-Format",
                    "errors": error_messages,
                }
            )

        # BPMN zu internem Format konvertieren
        nodes, edges = converter.convert_to_internal(request.bpmn_xml)

        # Workflow-Definition parsen fuer Metadaten
        workflow_def = converter.import_bpmn(request.bpmn_xml)

        # Workflow-Name bestimmen
        workflow_name = request.name or workflow_def.name or "Importierter BPMN Workflow"

        # Workflow in DB erstellen
        workflow = await workflow_service.create_workflow(
            user_id=current_user.id,
            name=workflow_name,
            trigger_type=workflow_def.trigger_type,
            trigger_config=workflow_def.trigger_config,
            nodes=nodes,
            edges=edges,
            description=request.description or workflow_def.description,
            company_id=current_user.company_id,
            variables=workflow_def.variables,
        )

        # Optional aktivieren
        if request.activate:
            workflow = await workflow_service.toggle_workflow(
                workflow_id=workflow.id,
                user_id=current_user.id,
                company_id=current_user.company_id,
            )

        return WorkflowImportResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            trigger_type=workflow.trigger_type,
            is_active=workflow.is_active,
            node_count=len(nodes),
            edge_count=len(edges),
            created_at=workflow.created_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "BPMN-Import")
        )


@router.post(
    "/import/file",
    response_model=WorkflowImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="BPMN-Datei hochladen und importieren"
)
async def import_bpmn_file(
    file: UploadFile = File(..., description="BPMN 2.0 XML Datei (.bpmn, .xml)"),
    name: Optional[str] = Query(None, max_length=255, description="Optionaler Workflow-Name"),
    activate: bool = Query(False, description="Workflow direkt aktivieren"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> WorkflowImportResponse:
    """Importiert eine BPMN 2.0 XML Datei und erstellt einen Workflow.

    Akzeptierte Dateiformate:
    - .bpmn (BPMN 2.0 XML)
    - .xml (BPMN 2.0 XML)

    Maximale Dateigroesse: 5 MB
    """
    # Dateiformat pruefen
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dateiname erforderlich"
        )

    allowed_extensions = {".bpmn", ".xml"}
    file_ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiges Dateiformat. Erlaubt: {', '.join(allowed_extensions)}"
        )

    # Content-Type pruefen (optional)
    allowed_content_types = {
        "application/xml",
        "text/xml",
        "application/octet-stream",
    }

    # Dateiinhalt lesen (mit Groessenbegrenzung)
    max_size = 5 * 1024 * 1024  # 5 MB
    content = await file.read()

    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Datei zu gross. Maximum: {max_size // 1024 // 1024} MB"
        )

    try:
        bpmn_xml = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datei muss UTF-8 kodiert sein"
        )

    # Import durchfuehren
    request = BPMNImportRequest(
        bpmn_xml=bpmn_xml,
        name=name,
        activate=activate,
    )

    return await import_bpmn(request=request, db=db, current_user=current_user)


# =============================================================================
# Export Endpoints
# =============================================================================

@router.get(
    "/export/{workflow_id}",
    response_class=Response,
    summary="Workflow als BPMN 2.0 XML exportieren"
)
async def export_bpmn(
    workflow_id: UUID,
    download: bool = Query(False, description="Als Datei-Download"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Response:
    """Exportiert einen Workflow als BPMN 2.0 XML.

    Der Workflow wird aus dem internen Format in standardkonformes
    BPMN 2.0 XML konvertiert, das in Camunda Modeler, Activiti,
    jBPM oder Flowable importiert werden kann.

    Bei download=true wird die Datei als Download angeboten.
    """
    workflow_service = WorkflowService(db)
    converter = get_bpmn_converter()

    # Workflow laden
    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=current_user.company_id,
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden"
        )

    try:
        # Zu BPMN konvertieren
        bpmn_xml = converter.convert_from_internal(
            nodes=workflow.nodes or [],
            edges=workflow.edges or [],
            workflow_id=str(workflow.id),
            workflow_name=workflow.name,
            trigger_type=workflow.trigger_type,
            trigger_config=workflow.trigger_config,
        )

        # Response erstellen
        media_type = "application/xml"
        headers = {}

        if download:
            # Sicherer Dateiname
            safe_name = "".join(c for c in workflow.name if c.isalnum() or c in " -_")[:50]
            filename = f"{safe_name}.bpmn"
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        return Response(
            content=bpmn_xml,
            media_type=media_type,
            headers=headers,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "BPMN-Export")
        )


@router.post(
    "/export/from-internal",
    response_model=BPMNExportResponse,
    summary="Internes Format zu BPMN 2.0 exportieren"
)
async def export_from_internal(
    request: BPMNExportRequest,
    current_user: User = Depends(get_current_active_user)
) -> BPMNExportResponse:
    """Konvertiert internes ReactFlow-Format direkt zu BPMN 2.0 XML.

    Nuetzlich fuer:
    - Vorschau vor dem Speichern
    - Export von nicht gespeicherten Workflows
    - Integration mit anderen Tools
    """
    converter = get_bpmn_converter()

    try:
        bpmn_xml = converter.convert_from_internal(
            nodes=request.nodes,
            edges=request.edges,
            workflow_id=f"workflow_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            workflow_name=request.name,
            trigger_type=request.trigger_type,
            trigger_config=request.trigger_config,
        )

        # Prozesse zaehlen
        workflow_def = converter.import_bpmn(bpmn_xml)

        return BPMNExportResponse(
            bpmn_xml=bpmn_xml,
            workflow_id=workflow_def.id,
            workflow_name=workflow_def.name,
            process_count=len(workflow_def.processes),
            exported_at=datetime.now(timezone.utc),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "BPMN-Export")
        )


# =============================================================================
# Validation Endpoints
# =============================================================================

@router.post(
    "/validate",
    response_model=ValidationResultResponse,
    summary="BPMN 2.0 XML validieren"
)
async def validate_bpmn(
    request: BPMNValidateRequest,
    current_user: User = Depends(get_current_active_user)
) -> ValidationResultResponse:
    """Validiert BPMN 2.0 XML ohne zu importieren.

    Prueft:
    - XML-Syntax
    - BPMN 2.0 Schema-Konformitaet
    - Semantische Regeln (Start/End Events, Erreichbarkeit)

    Gibt Fehler und Warnungen zurueck.
    """
    converter = get_bpmn_converter()

    result = converter.validate(request.bpmn_xml)

    return ValidationResultResponse(
        valid=result.valid,
        errors=[
            ValidationErrorResponse(
                code=e.code,
                message=e.message,
                element_id=e.element_id,
            )
            for e in result.errors
        ],
        warnings=[
            ValidationErrorResponse(
                code=w.code,
                message=w.message,
                element_id=w.element_id,
            )
            for w in result.warnings
        ],
    )


@router.post(
    "/validate/file",
    response_model=ValidationResultResponse,
    summary="BPMN-Datei validieren"
)
async def validate_bpmn_file(
    file: UploadFile = File(..., description="BPMN 2.0 XML Datei"),
    current_user: User = Depends(get_current_active_user)
) -> ValidationResultResponse:
    """Validiert eine BPMN 2.0 XML Datei ohne zu importieren.

    Nuetzlich fuer:
    - Vorab-Pruefung vor Import
    - Qualitaetssicherung
    - CI/CD Integration
    """
    # Datei lesen
    max_size = 5 * 1024 * 1024
    content = await file.read()

    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Datei zu gross. Maximum: {max_size // 1024 // 1024} MB"
        )

    try:
        bpmn_xml = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datei muss UTF-8 kodiert sein"
        )

    request = BPMNValidateRequest(bpmn_xml=bpmn_xml)
    return await validate_bpmn(request=request, current_user=current_user)


# =============================================================================
# Preview Endpoints
# =============================================================================

@router.get(
    "/preview/{workflow_id}",
    response_model=BPMNPreviewResponse,
    summary="BPMN-Diagramm Vorschau"
)
async def preview_bpmn(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> BPMNPreviewResponse:
    """Gibt Informationen zur BPMN-Diagramm-Vorschau zurueck.

    Hinweis: SVG-Rendering erfordert einen externen BPMN-Renderer.
    Diese Funktion gibt Metadaten zurueck und verweist auf die
    Export-Funktion fuer den XML-Download.
    """
    workflow_service = WorkflowService(db)

    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=current_user.company_id,
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden"
        )

    return BPMNPreviewResponse(
        workflow_id=str(workflow_id),
        preview_available=False,
        message=(
            "SVG-Vorschau nicht verfuegbar. "
            "Verwenden Sie /export/{workflow_id}?download=true "
            "um das BPMN-XML herunterzuladen und in einem BPMN-Viewer anzuzeigen."
        ),
    )


# =============================================================================
# Utility Endpoints
# =============================================================================

@router.get(
    "/supported-elements",
    summary="Unterstuetzte BPMN-Elemente auflisten"
)
async def list_supported_elements(
    current_user: User = Depends(get_current_active_user)
) -> JSONDict:
    """Listet alle unterstuetzten BPMN 2.0 Elemente auf.

    Nuetzlich fuer:
    - Dokumentation
    - Client-Validierung
    - Kompatibilitaetspruefung
    """
    return {
        "events": {
            "supported": [
                {"type": "startEvent", "description": "Start-Event"},
                {"type": "endEvent", "description": "End-Event"},
                {"type": "intermediateCatchEvent", "description": "Intermediate Catch Event (Timer, Message)"},
                {"type": "intermediateThrowEvent", "description": "Intermediate Throw Event"},
                {"type": "boundaryEvent", "description": "Boundary Event (Timer, Error)"},
            ],
            "event_definitions": [
                {"type": "timerEventDefinition", "description": "Timer (Date, Duration, Cycle)"},
                {"type": "messageEventDefinition", "description": "Message"},
                {"type": "signalEventDefinition", "description": "Signal"},
                {"type": "errorEventDefinition", "description": "Error"},
            ],
        },
        "tasks": {
            "supported": [
                {"type": "userTask", "description": "User Task (Manuelle Aufgabe)"},
                {"type": "serviceTask", "description": "Service Task (Automatisierte Aufgabe)"},
                {"type": "scriptTask", "description": "Script Task (Skript-Ausfuehrung)"},
                {"type": "manualTask", "description": "Manual Task"},
                {"type": "sendTask", "description": "Send Task (Benachrichtigung)"},
                {"type": "receiveTask", "description": "Receive Task"},
                {"type": "businessRuleTask", "description": "Business Rule Task"},
            ],
        },
        "gateways": {
            "supported": [
                {"type": "exclusiveGateway", "description": "Exclusive Gateway (XOR)"},
                {"type": "parallelGateway", "description": "Parallel Gateway (AND)"},
                {"type": "inclusiveGateway", "description": "Inclusive Gateway (OR)"},
                {"type": "eventBasedGateway", "description": "Event-Based Gateway"},
            ],
        },
        "flows": {
            "supported": [
                {"type": "sequenceFlow", "description": "Sequence Flow (Verbindung)"},
            ],
            "features": [
                "conditionExpression",
                "defaultFlow",
            ],
        },
        "compatibility": {
            "modelers": [
                "Camunda Modeler",
                "Activiti Designer",
                "jBPM Designer",
                "Flowable Modeler",
            ],
            "bpmn_version": "2.0",
            "namespace": "http://www.omg.org/spec/BPMN/20100524/MODEL",
        },
    }
