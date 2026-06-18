"""
Document Template API Endpoints

Endpoints for managing document templates including:
- CRUD operations for templates
- Document generation from templates
- Template snippets management
- Template preview and validation
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.security_auth import build_content_disposition
from app.api.schemas.document_template import (
    # Template schemas
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateListResponse,
    TemplateBriefResponse,
    # Generation schemas
    GenerateDocumentRequest,
    PreviewRequest,
    GeneratedDocumentResponse,
    GeneratedDocumentListResponse,
    # Snippet schemas
    SnippetCreate,
    SnippetUpdate,
    SnippetResponse,
    # Other schemas
    CategorySummary,
    # Enums
    TemplateCategoryEnum,
)
from app.services.document_template_service import DocumentTemplateService
from app.db.models import User, Company, DocumentTemplate, GeneratedDocument, TemplateSnippet

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/document-templates", tags=["Dokumentvorlagen"])


# =============================================================================
# Helper Functions
# =============================================================================

def _template_to_response(template: DocumentTemplate) -> TemplateResponse:
    """Convert a template model to a response schema."""
    return TemplateResponse(
        id=template.id,
        company_id=template.company_id,
        name=template.name,
        code=template.code,
        description=template.description,
        category=TemplateCategoryEnum(template.category.value),
        content=template.content,
        header_content=template.header_content,
        footer_content=template.footer_content,
        css_styles=template.css_styles,
        page_size=template.page_size,
        orientation=template.orientation,
        margins=template.margins or {"top": 20, "right": 15, "bottom": 20, "left": 15},
        output_format=template.output_format,
        variables=template.variables or [],
        version=template.version,
        is_latest=template.is_latest,
        is_active=template.is_active,
        is_default=template.is_default,
        usage_count=template.usage_count,
        last_used_at=template.last_used_at,
        tags=template.tags or [],
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_id=template.created_by_id,
    )


def _template_to_brief(template: DocumentTemplate) -> TemplateBriefResponse:
    """Convert a template model to a brief response schema."""
    return TemplateBriefResponse(
        id=template.id,
        name=template.name,
        code=template.code,
        description=template.description,
        category=TemplateCategoryEnum(template.category.value),
        output_format=template.output_format,
        version=template.version,
        is_default=template.is_default,
        usage_count=template.usage_count,
        variable_count=len(template.variables or []),
    )


def _generated_to_response(doc: GeneratedDocument) -> GeneratedDocumentResponse:
    """Convert a generated document model to a response schema."""
    return GeneratedDocumentResponse(
        id=doc.id,
        company_id=doc.company_id,
        template_id=doc.template_id,
        title=doc.title,
        filename=doc.filename,
        storage_path=doc.storage_path,
        file_size=doc.file_size,
        variable_values=doc.variable_values or {},
        template_version=doc.template_version,
        linked_entity_id=doc.linked_entity_id,
        linked_document_id=doc.linked_document_id,
        is_finalized=doc.is_finalized,
        is_sent=doc.is_sent,
        sent_at=doc.sent_at,
        sent_to=doc.sent_to or [],
        created_at=doc.created_at,
        created_by_id=doc.created_by_id,
    )


def _snippet_to_response(snippet: TemplateSnippet) -> SnippetResponse:
    """Convert a snippet model to a response schema."""
    return SnippetResponse(
        id=snippet.id,
        company_id=snippet.company_id,
        name=snippet.name,
        code=snippet.code,
        description=snippet.description,
        category=snippet.category,
        content=snippet.content,
        is_active=snippet.is_active,
        created_at=snippet.created_at,
        updated_at=snippet.updated_at,
    )


# =============================================================================
# Template CRUD Endpoints
# =============================================================================

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> TemplateResponse:
    """
    Erstelle eine neue Dokumentvorlage.

    Erstellt eine Vorlage mit:
    - Jinja2-Syntax für Platzhalter
    - Variablen-Schema für Formular-Generierung
    - Optionalem Header/Footer
    """
    service = DocumentTemplateService(db)

    template = await service.create_template(
        company_id=company.id,
        user_id=current_user.id,
        name=data.name,
        code=data.code,
        content=data.content,
        category=data.category,
        description=data.description,
        header_content=data.header_content,
        footer_content=data.footer_content,
        css_styles=data.css_styles,
        page_size=data.page_size,
        orientation=data.orientation,
        margins=data.margins,
        output_format=data.output_format,
        variables=[v.model_dump() for v in data.variables],
        tags=data.tags,
        is_default=data.is_default,
    )

    logger.info(
        "template_created",
        template_id=str(template.id),
        code=template.code,
        category=template.category.value,
    )

    return _template_to_response(template)


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    category: Optional[TemplateCategoryEnum] = Query(None, description="Filter nach Kategorie"),
    search: Optional[str] = Query(None, max_length=200, description="Suche in Name, Code, Beschreibung"),
    include_inactive: bool = Query(False, description="Inaktive Vorlagen einschließen"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> TemplateListResponse:
    """
    Liste aller Dokumentvorlagen mit Filteroptionen.

    Filter:
    - category: Vorlagen-Kategorie
    - search: Volltextsuche
    - include_inactive: Auch inaktive Vorlagen
    """
    service = DocumentTemplateService(db)

    templates, total = await service.list_templates(
        company_id=company.id,
        category=category,
        search=search,
        include_inactive=include_inactive,
        offset=(page - 1) * per_page,
        limit=per_page,
    )

    return TemplateListResponse(
        items=[_template_to_response(t) for t in templates],
        total=total,
        offset=(page - 1) * per_page,
        limit=per_page,
    )


@router.get("/categories", response_model=List[CategorySummary])
async def get_category_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[CategorySummary]:
    """
    Zusammenfassung der Vorlagen pro Kategorie.

    Liefert Anzahl und Default-Vorlage pro Kategorie.
    """
    service = DocumentTemplateService(db)
    summary = await service.get_category_summary(company_id=company.id)

    return [
        CategorySummary(
            category=TemplateCategoryEnum(s["category"]),
            count=s["count"],
            default_template_id=s.get("default_template_id"),
            default_template_name=s.get("default_template_name"),
        )
        for s in summary
    ]


@router.get("/brief", response_model=List[TemplateBriefResponse])
async def list_templates_brief(
    category: Optional[TemplateCategoryEnum] = Query(None, description="Filter nach Kategorie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[TemplateBriefResponse]:
    """
    Kurzliste der Vorlagen (ohne Content).

    Optimiert für Dropdown-Auswahl und schnelles Laden.
    """
    service = DocumentTemplateService(db)

    templates, _ = await service.list_templates(
        company_id=company.id,
        category=category,
        include_inactive=False,
        offset=0,
        limit=500,  # Alle aktiven Vorlagen
    )

    return [_template_to_brief(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> TemplateResponse:
    """
    Vorlage mit allen Details abrufen.
    """
    service = DocumentTemplateService(db)
    template = await service.get_template(
        template_id=template_id,
        company_id=company.id,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorlage nicht gefunden",
        )

    return _template_to_response(template)


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> TemplateResponse:
    """
    Vorlage aktualisieren.

    Bei create_new_version=true wird eine neue Version erstellt,
    sonst wird die bestehende Vorlage aktualisiert.
    """
    service = DocumentTemplateService(db)

    # Prepare updates
    updates = data.model_dump(exclude_unset=True)
    create_new_version = updates.pop("create_new_version", False)

    # Convert variables if present
    if "variables" in updates and updates["variables"]:
        updates["variables"] = [v.model_dump() if hasattr(v, "model_dump") else v for v in updates["variables"]]

    template = await service.update_template(
        template_id=template_id,
        company_id=company.id,
        create_new_version=create_new_version,
        **updates,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorlage nicht gefunden",
        )

    logger.info(
        "template_updated",
        template_id=str(template.id),
        new_version=create_new_version,
        version=template.version,
    )

    return _template_to_response(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> None:
    """
    Vorlage deaktivieren (Soft-Delete).

    Setzt is_active=False statt physischem Löschen.
    """
    service = DocumentTemplateService(db)

    success = await service.delete_template(
        template_id=template_id,
        company_id=company.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorlage nicht gefunden",
        )


# =============================================================================
# Document Generation Endpoints
# =============================================================================

@router.post("/{template_id}/preview")
async def preview_template(
    template_id: UUID,
    data: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Vorschau einer Vorlage mit Variablen.

    Rendert die Vorlage ohne sie zu speichern.
    """
    service = DocumentTemplateService(db)

    template = await service.get_template(
        template_id=template_id,
        company_id=company.id,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorlage nicht gefunden",
        )

    try:
        html = await service.render_template(
            template=template,
            variables=data.variables,
        )
        return {
            "html": html,
            "template_id": str(template_id),
            "template_name": template.name,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokumentvorlage"),
        )


@router.post("/{template_id}/validate")
async def validate_variables(
    template_id: UUID,
    data: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Validiere Variablen gegen Vorlage.

    Prüft ob alle erforderlichen Variablen vorhanden sind.
    """
    service = DocumentTemplateService(db)

    template = await service.get_template(
        template_id=template_id,
        company_id=company.id,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorlage nicht gefunden",
        )

    is_valid, errors = service.validate_variables(
        template=template,
        variables=data.variables,
    )

    return {
        "valid": is_valid,
        "errors": errors,
        "template_id": str(template_id),
        "required_variables": [
            v.get("name") for v in template.variables
            if v.get("required", False)
        ],
    }


@router.post("/generate", response_model=GeneratedDocumentResponse, status_code=status.HTTP_201_CREATED)
async def generate_document(
    data: GenerateDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> GeneratedDocumentResponse:
    """
    Generiere ein Dokument aus einer Vorlage.

    Erstellt das Dokument und speichert es optional im Storage.
    """
    service = DocumentTemplateService(db)

    template = await service.get_template(
        template_id=data.template_id,
        company_id=company.id,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorlage nicht gefunden",
        )

    try:
        generated = await service.generate_document(
            template=template,
            title=data.title,
            variables=data.variables,
            company_id=company.id,
            user_id=current_user.id,
            linked_entity_id=data.linked_entity_id,
            linked_document_id=data.linked_document_id,
            save_to_storage=data.save_to_storage,
        )

        logger.info(
            "document_generated",
            generated_id=str(generated.id),
            template_code=template.code,
            title=data.title,
        )

        return _generated_to_response(generated)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokumentvorlage"),
        )


@router.get("/generated", response_model=GeneratedDocumentListResponse)
async def list_generated_documents(
    template_id: Optional[UUID] = Query(None, description="Filter nach Vorlage"),
    entity_id: Optional[UUID] = Query(None, description="Filter nach verknüpfter Entity"),
    search: Optional[str] = Query(None, max_length=200, description="Suche in Titel, Dateiname"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> GeneratedDocumentListResponse:
    """
    Liste aller generierten Dokumente.
    """
    service = DocumentTemplateService(db)

    docs, total = await service.list_generated_documents(
        company_id=company.id,
        template_id=template_id,
        entity_id=entity_id,
        search=search,
        offset=(page - 1) * per_page,
        limit=per_page,
    )

    return GeneratedDocumentListResponse(
        items=[_generated_to_response(d) for d in docs],
        total=total,
        offset=(page - 1) * per_page,
        limit=per_page,
    )


@router.get("/generated/{document_id}", response_model=GeneratedDocumentResponse)
async def get_generated_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> GeneratedDocumentResponse:
    """
    Generiertes Dokument abrufen.
    """
    service = DocumentTemplateService(db)
    doc = await service.get_generated_document(
        document_id=document_id,
        company_id=company.id,
    )

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generiertes Dokument nicht gefunden",
        )

    return _generated_to_response(doc)


@router.get("/generated/{document_id}/download")
async def download_generated_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> Response:
    """
    Generiertes Dokument herunterladen.
    """
    service = DocumentTemplateService(db)
    doc = await service.get_generated_document(
        document_id=document_id,
        company_id=company.id,
    )

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generiertes Dokument nicht gefunden",
        )

    if not doc.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument wurde nicht gespeichert",
        )

    # Get file from storage
    from app.services.storage_service import get_storage_service
    storage = get_storage_service()

    try:
        content = await storage.get_file(doc.storage_path)

        # Determine content type
        content_type = "application/pdf"
        if doc.filename.endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif doc.filename.endswith(".html"):
            content_type = "text/html"

        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": build_content_disposition(doc.filename, "attachment"),
            },
        )
    except Exception as e:
        logger.error("document_download_failed", document_id=str(document_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dokument konnte nicht heruntergeladen werden",
        )


# =============================================================================
# Snippet Endpoints
# =============================================================================

@router.post("/snippets", response_model=SnippetResponse, status_code=status.HTTP_201_CREATED)
async def create_snippet(
    data: SnippetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SnippetResponse:
    """
    Erstelle einen neuen Textbaustein.

    Textbausteine können in Vorlagen wiederverwendet werden.
    """
    service = DocumentTemplateService(db)

    snippet = await service.create_snippet(
        company_id=company.id,
        name=data.name,
        code=data.code,
        content=data.content,
        description=data.description,
        category=data.category,
    )

    logger.info(
        "snippet_created",
        snippet_id=str(snippet.id),
        code=snippet.code,
    )

    return _snippet_to_response(snippet)


@router.get("/snippets", response_model=List[SnippetResponse])
async def list_snippets(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    search: Optional[str] = Query(None, max_length=200, description="Suche in Name, Code"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[SnippetResponse]:
    """
    Liste aller Textbausteine.
    """
    service = DocumentTemplateService(db)

    snippets = await service.list_snippets(
        company_id=company.id,
        category=category,
        search=search,
    )

    return [_snippet_to_response(s) for s in snippets]


@router.get("/snippets/{snippet_id}", response_model=SnippetResponse)
async def get_snippet(
    snippet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SnippetResponse:
    """
    Textbaustein abrufen.
    """
    service = DocumentTemplateService(db)
    snippet = await service.get_snippet(
        snippet_id=snippet_id,
        company_id=company.id,
    )

    if not snippet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Textbaustein nicht gefunden",
        )

    return _snippet_to_response(snippet)


@router.patch("/snippets/{snippet_id}", response_model=SnippetResponse)
async def update_snippet(
    snippet_id: UUID,
    data: SnippetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SnippetResponse:
    """
    Textbaustein aktualisieren.
    """
    service = DocumentTemplateService(db)

    updates = data.model_dump(exclude_unset=True)
    snippet = await service.update_snippet(
        snippet_id=snippet_id,
        company_id=company.id,
        **updates,
    )

    if not snippet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Textbaustein nicht gefunden",
        )

    return _snippet_to_response(snippet)


@router.delete("/snippets/{snippet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snippet(
    snippet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> None:
    """
    Textbaustein deaktivieren.
    """
    service = DocumentTemplateService(db)

    success = await service.delete_snippet(
        snippet_id=snippet_id,
        company_id=company.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Textbaustein nicht gefunden",
        )
