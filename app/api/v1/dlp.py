"""
DLP (Data Loss Prevention) API Endpoints.

Ermoeglicht die Verwaltung von DLP-Policies und Zugriffspruefungen.

Endpoints:
- GET  /dlp/policies         - Alle Policies auflisten
- POST /dlp/policies         - Neue Policy erstellen
- GET  /dlp/policies/{id}    - Policy abrufen
- PATCH /dlp/policies/{id}   - Policy aktualisieren
- DELETE /dlp/policies/{id}  - Policy loeschen
- POST /dlp/check            - Zugriffspruefung durchfuehren
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

from app.api.deps import get_current_user, get_db, require_admin
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
    """Request fuer Zugriffspruefung."""
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
        description="Zu pruefende Typen (None = alle)"
    )


class ScanResponse(BaseModel):
    """Response fuer Sensitive-Data-Scan."""
    has_sensitive_data: bool
    findings: dict[SensitiveDataType, int] = Field(
        default_factory=dict,
        description="Gefundene Typen mit Anzahl"
    )
    summary: str


class PolicyListResponse(BaseModel):
    """Response fuer Policy-Liste."""
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
    description="Gibt alle konfigurierten DLP-Policies zurueck. Erfordert Admin-Rolle."
)
async def list_policies(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyListResponse:
    """Listet alle DLP-Policies auf (Multi-Tenant isoliert)."""
    # SECURITY: company_id aus User fuer Multi-Tenant Isolation
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
async def create_policy(
    request: PolicyCreateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DLPPolicy:
    """Erstellt eine neue DLP-Policy (Multi-Tenant isoliert, persistiert in DB)."""
    # SECURITY: company_id aus User fuer Multi-Tenant Isolation
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss einer Firma zugeordnet sein"
        )

    dlp_service = get_dlp_service(db, company_id)

    try:
        policy = DLPPolicy(**request.model_dump())
        await dlp_service.add_policy(policy)
        return policy
    except DLPServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get(
    "/policies/{policy_id}",
    response_model=DLPPolicy,
    summary="DLP-Policy abrufen",
    description="Gibt eine spezifische DLP-Policy zurueck. Erfordert Admin-Rolle."
)
async def get_policy(
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
async def update_policy(
    policy_id: str,
    request: PolicyUpdateRequest,
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
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        return await dlp_service.update_policy(policy_id, updates)
    except DLPServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete(
    "/policies/{policy_id}",
    response_model=SuccessResponse,
    summary="DLP-Policy loeschen",
    description="Loescht eine DLP-Policy. Erfordert Admin-Rolle."
)
async def delete_policy(
    policy_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    """Loescht eine DLP-Policy (Multi-Tenant isoliert)."""
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss einer Firma zugeordnet sein"
        )

    dlp_service = get_dlp_service(db, company_id)

    # Pruefen ob Policy existiert
    policies = await dlp_service.get_policies()
    if not any(p.id == policy_id for p in policies):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id}' nicht gefunden"
        )

    await dlp_service.delete_policy(policy_id)
    return SuccessResponse(message=f"Policy '{policy_id}' wurde geloescht")


@router.post(
    "/check",
    response_model=DLPCheckResult,
    summary="Zugriffspruefung durchfuehren",
    description="Prueft ob eine Aktion auf einem Dokument erlaubt ist."
)
async def check_access(
    request: AccessCheckRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DLPCheckResult:
    """
    Prueft Zugriffsberechtigung basierend auf DLP-Policies.

    SECURITY:
    - Multi-Tenant: Dokument muss zur gleichen Company gehoeren wie User!
    - Audit-Log wird in DB persistiert
    """
    from sqlalchemy import select, and_
    from app.db.models import Document

    # SECURITY: company_id aus User
    user_company_id = getattr(current_user, 'company_id', None)

    # Dokument laden MIT company_id Validierung (Multi-Tenant Security!)
    query = select(Document).where(Document.id == request.document_id)

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

    # DLP-Pruefung durchfuehren
    check_result = await dlp_service.check_access(
        user=current_user,
        document=document,
        action_type=request.action_type,
    )

    # Client-Info fuer Audit
    ip_address, user_agent = _get_client_info(http_request)

    # Logging (jetzt mit DB-Persistenz!)
    await dlp_service.log_dlp_event(
        user_id=current_user.id,
        document_id=request.document_id,
        action=request.action_type,
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
async def scan_sensitive_data(
    request: ScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Scannt Text auf sensible Daten (Multi-Tenant isoliert)."""
    company_id = getattr(current_user, 'company_id', None)
    dlp_service = get_dlp_service(db, company_id)

    findings = dlp_service.detect_sensitive_data(
        text=request.text,
        types=request.types,
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
    summary="Verfuegbare Typen sensibler Daten",
    description="Gibt alle Typen sensibler Daten zurueck, die erkannt werden koennen."
)
async def get_sensitive_data_types(
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """Gibt verfuegbare Typen sensibler Daten zurueck."""
    return [t.value for t in SensitiveDataType]


@router.post(
    "/seed-defaults",
    response_model=SuccessResponse,
    summary="Standard-Policies erstellen",
    description="Erstellt Standard-DLP-Policies falls noch keine existieren. Erfordert Admin-Rolle."
)
async def seed_default_policies(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    """Erstellt Standard-Policies fuer die Company des Benutzers."""
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
