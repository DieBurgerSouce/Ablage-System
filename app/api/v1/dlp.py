"""
DLP (Data Loss Prevention) API Endpoints.

Ermöglicht die Verwaltung von DLP-Policies und Zugriffsprüfungen.

Endpoints:
- GET  /dlp/policies         - Alle Policies auflisten
- POST /dlp/policies         - Neue Policy erstellen
- GET  /dlp/policies/{id}    - Policy abrufen
- PATCH /dlp/policies/{id}   - Policy aktualisieren
- DELETE /dlp/policies/{id}  - Policy löschen
- POST /dlp/check            - Zugriffsprüfung durchführen
- POST /dlp/scan             - Text auf sensible Daten scannen

SECURITY:
- Alle Endpoints erfordern Admin-Rolle (ausser /check und /scan)
- Sensible Daten werden nicht geloggt
- Multi-Tenant Isolation via company_id (KRITISCH!)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, require_admin
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User, Document
from app.services.dlp import (
    DLPService,
    DLPServiceError,
    DLPPolicy,
    DLPCheckResult,
    DLPAction,
    SensitiveDataType,
    get_dlp_service,
)
from app.core.rate_limiting import limiter, get_user_identifier

router = APIRouter(prefix="/dlp", tags=["DLP"])


def _get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extrahiert IP-Adresse und User-Agent aus Request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent", "")[:255]  # Max 255 chars
    return ip_address, user_agent


# ==================== Request/Response Schemas ====================

class PolicyCreateRequest(BaseModel):
    """Request zum Erstellen einer neuen Policy."""
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    enabled: bool = True
    allowed_roles: list[str] = Field(default=["admin"])
    blocked_roles: list[str] = Field(default=[])
    time_restrictions: Optional[dict] = None
    document_types: list[str] = Field(default=["all"])
    tags_required: list[str] = Field(default=[])
    tags_blocked: list[str] = Field(default=[])
    action: DLPAction = DLPAction.ALLOW
    require_watermark: bool = False
    watermark_config: Optional[dict] = None
    notify_admin: bool = False
    notify_user: bool = False
    log_access: bool = True


class PolicyUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Policy."""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    allowed_roles: Optional[list[str]] = None
    blocked_roles: Optional[list[str]] = None
    time_restrictions: Optional[dict] = None
    document_types: Optional[list[str]] = None
    tags_required: Optional[list[str]] = None
    tags_blocked: Optional[list[str]] = None
    action: Optional[DLPAction] = None
    require_watermark: Optional[bool] = None
    watermark_config: Optional[dict] = None
    notify_admin: Optional[bool] = None
    notify_user: Optional[bool] = None
    log_access: Optional[bool] = None


class AccessCheckRequest(BaseModel):
    """Request für Zugriffsprüfung."""
    document_id: UUID
    action_type: str = Field(
        default="download",
        description="Art der Aktion: download, view, print, export"
    )


class ScanRequest(BaseModel):
    """Request zum Scannen auf sensible Daten."""
    text: str = Field(..., max_length=100000)
    types: Optional[list[SensitiveDataType]] = Field(
        default=None,
        description="Zu prüfende Typen (None = alle)"
    )


class ScanResponse(BaseModel):
    """Response für Sensitive-Data-Scan."""
    has_sensitive_data: bool
    findings: dict[SensitiveDataType, int] = Field(
        default_factory=dict,
        description="Gefundene Typen mit Anzahl"
    )
    summary: str


class PolicyListResponse(BaseModel):
    """Response für Policy-Liste."""
    policies: list[DLPPolicy]
    total: int


class SuccessResponse(BaseModel):
    """Standard-Erfolgs-Response."""
    success: bool = True
    message: str


# ==================== Endpoints ====================

@router.get(
    "/policies",
    response_model=PolicyListResponse,
    summary="Alle DLP-Policies auflisten",
    description="Gibt alle konfigurierten DLP-Policies zurück. Erfordert Admin-Rolle."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def list_policies(
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyListResponse:
    """Listet alle DLP-Policies auf (Multi-Tenant isoliert)."""
    # SECURITY: company_id aus User für Multi-Tenant Isolation
    company_id = getattr(current_user, 'company_id', None)
    dlp_service = get_dlp_service(db, company_id)
    policies = await dlp_service.get_policies()
    return PolicyListResponse(policies=policies, total=len(policies))


@router.post(
    "/policies",
    response_model=DLPPolicy,
    status_code=status.HTTP_201_CREATED,
    summary="Neue DLP-Policy erstellen",
    description="Erstellt eine neue DLP-Policy. Erfordert Admin-Rolle."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def create_policy(
    request: Request,
    body: PolicyCreateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DLPPolicy:
    """Erstellt eine neue DLP-Policy (Multi-Tenant isoliert, persistiert in DB)."""
    # SECURITY: company_id aus User für Multi-Tenant Isolation
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss einer Firma zugeordnet sein"
        )

    dlp_service = get_dlp_service(db, company_id)

    try:
        policy = DLPPolicy(**body.model_dump())
        await dlp_service.add_policy(policy)
        return policy
    except DLPServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_detail(e, "Policy-Erstellung")
        )


@router.get(
    "/policies/{policy_id}",
    response_model=DLPPolicy,
    summary="DLP-Policy abrufen",
    description="Gibt eine spezifische DLP-Policy zurück. Erfordert Admin-Rolle."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_policy(
    request: Request,
    policy_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DLPPolicy:
    """Ruft eine DLP-Policy ab (Multi-Tenant isoliert)."""
    company_id = getattr(current_user, 'company_id', None)
    dlp_service = get_dlp_service(db, company_id)
    policies = await dlp_service.get_policies()

    for policy in policies:
        if policy.id == policy_id:
            return policy

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Policy '{policy_id}' nicht gefunden"
    )


@router.patch(
    "/policies/{policy_id}",
    response_model=DLPPolicy,
    summary="DLP-Policy aktualisieren",
    description="Aktualisiert eine bestehende DLP-Policy. Erfordert Admin-Rolle."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def update_policy(
    request: Request,
    policy_id: str,
    body: PolicyUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DLPPolicy:
    """Aktualisiert eine DLP-Policy (Multi-Tenant isoliert)."""
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss einer Firma zugeordnet sein"
        )

    dlp_service = get_dlp_service(db, company_id)

    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        return await dlp_service.update_policy(policy_id, updates)
    except DLPServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Policy-Aktualisierung")
        )


@router.delete(
    "/policies/{policy_id}",
    response_model=SuccessResponse,
    summary="DLP-Policy löschen",
    description="Löscht eine DLP-Policy. Erfordert Admin-Rolle."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def delete_policy(
    request: Request,
    policy_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    """Löscht eine DLP-Policy (Multi-Tenant isoliert)."""
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss einer Firma zugeordnet sein"
        )

    dlp_service = get_dlp_service(db, company_id)

    # Prüfen ob Policy existiert
    policies = await dlp_service.get_policies()
    if not any(p.id == policy_id for p in policies):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id}' nicht gefunden"
        )

    await dlp_service.delete_policy(policy_id)
    return SuccessResponse(message=f"Policy '{policy_id}' wurde gelöscht")


@router.post(
    "/check",
    response_model=DLPCheckResult,
    summary="Zugriffsprüfung durchführen",
    description="Prüft ob eine Aktion auf einem Dokument erlaubt ist."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def check_access(
    body: AccessCheckRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DLPCheckResult:
    """
    Prüft Zugriffsberechtigung basierend auf DLP-Policies.

    SECURITY:
    - Multi-Tenant: Dokument muss zur gleichen Company gehoeren wie User!
    - Audit-Log wird in DB persistiert
    """
    from sqlalchemy import select, and_
    from app.db.models import Document

    # SECURITY: company_id aus User
    user_company_id = getattr(current_user, 'company_id', None)

    # Dokument laden MIT company_id Validierung (Multi-Tenant Security!)
    query = select(Document).where(Document.id == body.document_id)

    # KRITISCH: Wenn User einer Company zugeordnet ist, NUR Dokumente dieser Company!
    if user_company_id:
        query = query.where(Document.company_id == user_company_id)

    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # DLP-Service mit company_id initialisieren
    dlp_service = get_dlp_service(db, user_company_id)

    # DLP-Prüfung durchführen
    check_result = await dlp_service.check_access(
        user=current_user,
        document=document,
        action_type=body.action_type,
    )

    # Client-Info für Audit
    ip_address, user_agent = _get_client_info(request)

    # Logging (jetzt mit DB-Persistenz!)
    await dlp_service.log_dlp_event(
        user_id=current_user.id,
        document_id=body.document_id,
        action=body.action_type,
        result=check_result,
        company_id=user_company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return check_result


@router.post(
    "/scan",
    response_model=ScanResponse,
    summary="Text auf sensible Daten scannen",
    description=(
        "Scannt einen Text auf sensible Daten wie Kreditkartennummern, IBANs, etc. "
        "WICHTIG: Der Text wird nicht gespeichert oder geloggt."
    )
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def scan_sensitive_data(
    request: Request,
    body: ScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Scannt Text auf sensible Daten (Multi-Tenant isoliert)."""
    company_id = getattr(current_user, 'company_id', None)
    dlp_service = get_dlp_service(db, company_id)

    findings = dlp_service.detect_sensitive_data(
        text=body.text,
        types=body.types,
    )

    has_sensitive = len(findings) > 0
    total_findings = sum(findings.values())

    # Summary generieren
    if not has_sensitive:
        summary = "Keine sensiblen Daten gefunden."
    else:
        types_found = ", ".join([t.value for t in findings.keys()])
        summary = f"{total_findings} potentiell sensible Datenpunkt(e) gefunden: {types_found}"

    return ScanResponse(
        has_sensitive_data=has_sensitive,
        findings=findings,
        summary=summary,
    )


@router.get(
    "/sensitive-data-types",
    response_model=list[str],
    summary="Verfügbare Typen sensibler Daten",
    description="Gibt alle Typen sensibler Daten zurück, die erkannt werden können."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_sensitive_data_types(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """Gibt verfügbare Typen sensibler Daten zurück."""
    return [t.value for t in SensitiveDataType]


@router.post(
    "/seed-defaults",
    response_model=SuccessResponse,
    summary="Standard-Policies erstellen",
    description="Erstellt Standard-DLP-Policies falls noch keine existieren. Erfordert Admin-Rolle."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def seed_default_policies(
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    """Erstellt Standard-Policies für die Company des Benutzers."""
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss einer Firma zugeordnet sein"
        )

    dlp_service = get_dlp_service(db, company_id)
    created = await dlp_service.seed_default_policies()

    if created > 0:
        return SuccessResponse(message=f"{created} Standard-Policies wurden erstellt")
    else:
        return SuccessResponse(message="Policies existieren bereits - keine neuen erstellt")
