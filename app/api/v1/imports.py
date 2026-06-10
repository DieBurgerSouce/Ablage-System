"""API Endpoints für E-Mail und Ordner Import.

Stellt REST-Endpoints bereit für:
- Email-Import-Konfigurationen
- Folder-Import-Konfigurationen
- Import-Regeln
- Import-Logs und Statistiken
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.imports import (
    EmailImportService,
    FolderImportService,
    ImportRuleService,
)
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


# --- Email Config Schemas ---

class EmailConfigCreate(BaseModel):
    """Schema für Email-Config-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255)
    imap_server: str = Field(..., min_length=1, max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    use_ssl: bool = True
    use_starttls: bool = False
    imap_folder: str = "INBOX"
    processed_folder: Optional[str] = None
    error_folder: Optional[str] = None
    sync_interval_minutes: int = Field(default=15, ge=1, le=1440)
    filter_from_addresses: Optional[List[str]] = None
    filter_subject_patterns: Optional[List[str]] = None
    filter_attachment_types: Optional[List[str]] = None
    extract_attachments_only: bool = True
    include_email_body_as_document: bool = False
    auto_classify: bool = True
    auto_ocr: bool = True
    default_folder_id: Optional[UUID] = None
    company_id: Optional[UUID] = None


class EmailConfigUpdate(BaseModel):
    """Schema für Email-Config-Update."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    imap_server: Optional[str] = Field(None, min_length=1, max_length=255)
    imap_port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    use_ssl: Optional[bool] = None
    use_starttls: Optional[bool] = None
    imap_folder: Optional[str] = None
    processed_folder: Optional[str] = None
    error_folder: Optional[str] = None
    sync_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    filter_from_addresses: Optional[List[str]] = None
    filter_subject_patterns: Optional[List[str]] = None
    filter_attachment_types: Optional[List[str]] = None
    extract_attachments_only: Optional[bool] = None
    include_email_body_as_document: Optional[bool] = None
    auto_classify: Optional[bool] = None
    auto_ocr: Optional[bool] = None
    default_folder_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class EmailConfigResponse(BaseModel):
    """Schema für Email-Config-Response."""
    id: UUID
    name: str
    imap_server: str
    imap_port: int
    use_ssl: bool
    use_starttls: bool
    imap_folder: str
    processed_folder: Optional[str]
    error_folder: Optional[str]
    sync_interval_minutes: int
    filter_from_addresses: List[str]
    filter_subject_patterns: List[str]
    filter_attachment_types: List[str]
    extract_attachments_only: bool
    include_email_body_as_document: bool
    auto_classify: bool
    auto_ocr: bool
    default_folder_id: Optional[UUID]
    company_id: Optional[UUID]
    is_active: bool
    connection_status: str
    last_sync_at: Optional[datetime]
    total_emails_processed: int
    total_documents_created: int
    last_error: Optional[str]
    error_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailConfigListResponse(BaseModel):
    """Schema für Email-Config-Liste."""
    id: UUID
    name: str
    imap_server: str
    imap_folder: str
    is_active: bool
    connection_status: str
    last_sync_at: Optional[datetime]
    total_documents_created: int


# --- Folder Config Schemas ---

class FolderConfigCreate(BaseModel):
    """Schema für Folder-Config-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255)
    watch_path: str = Field(..., min_length=1, max_length=1000)
    is_network_path: bool = False
    network_credentials: Optional[str] = None
    recursive: bool = False
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    move_after_processing: bool = True
    processed_subfolder: str = "processed"
    error_subfolder: str = "error"
    delete_after_processing: bool = False
    auto_classify: bool = True
    auto_ocr: bool = True
    default_folder_id: Optional[UUID] = None
    preserve_filename: bool = True
    poll_interval_seconds: int = Field(default=60, ge=10, le=3600)
    company_id: Optional[UUID] = None


class FolderConfigUpdate(BaseModel):
    """Schema für Folder-Config-Update."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    watch_path: Optional[str] = Field(None, min_length=1, max_length=1000)
    is_network_path: Optional[bool] = None
    network_credentials: Optional[str] = None
    recursive: Optional[bool] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    move_after_processing: Optional[bool] = None
    processed_subfolder: Optional[str] = None
    error_subfolder: Optional[str] = None
    delete_after_processing: Optional[bool] = None
    auto_classify: Optional[bool] = None
    auto_ocr: Optional[bool] = None
    default_folder_id: Optional[UUID] = None
    preserve_filename: Optional[bool] = None
    poll_interval_seconds: Optional[int] = Field(None, ge=10, le=3600)
    is_active: Optional[bool] = None


class FolderConfigResponse(BaseModel):
    """Schema für Folder-Config-Response."""
    id: UUID
    name: str
    watch_path: str
    is_network_path: bool
    recursive: bool
    include_patterns: List[str]
    exclude_patterns: List[str]
    move_after_processing: bool
    processed_subfolder: str
    error_subfolder: str
    delete_after_processing: bool
    auto_classify: bool
    auto_ocr: bool
    default_folder_id: Optional[UUID]
    preserve_filename: bool
    poll_interval_seconds: int
    company_id: Optional[UUID]
    is_active: bool
    watcher_status: str
    last_poll_at: Optional[datetime]
    files_processed_today: int
    total_files_processed: int
    total_documents_created: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FolderConfigListResponse(BaseModel):
    """Schema für Folder-Config-Liste."""
    id: UUID
    name: str
    watch_path: str
    is_active: bool
    watcher_status: str
    last_poll_at: Optional[datetime]
    total_documents_created: int


# --- Import Rule Schemas ---

class RuleConditionSchema(BaseModel):
    """Schema für eine einzelne Regel-Bedingung."""
    field: str
    operator: str
    value: Optional[str] = None


class RuleConditionsSchema(BaseModel):
    """Schema für Bedingungs-Struktur."""
    operator: str = "AND"
    rules: List[RuleConditionSchema]


class RuleCreate(BaseModel):
    """Schema für Regel-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: int = Field(default=100, ge=1, le=1000)
    conditions: dict = Field(default_factory=dict)
    actions: dict = Field(default_factory=dict)
    applies_to_email_configs: Optional[List[UUID]] = None
    applies_to_folder_configs: Optional[List[UUID]] = None
    applies_to_all: bool = False
    is_active: bool = True


class RuleUpdate(BaseModel):
    """Schema für Regel-Update."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=1000)
    conditions: Optional[dict] = None
    actions: Optional[dict] = None
    applies_to_email_configs: Optional[List[UUID]] = None
    applies_to_folder_configs: Optional[List[UUID]] = None
    applies_to_all: Optional[bool] = None
    is_active: Optional[bool] = None


class RuleResponse(BaseModel):
    """Schema für Regel-Response."""
    id: UUID
    name: str
    description: Optional[str]
    priority: int
    applies_to_email_configs: List[str]
    applies_to_folder_configs: List[str]
    applies_to_all: bool
    conditions: dict
    actions: dict
    is_active: bool
    match_count: int
    last_matched_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RuleListResponse(BaseModel):
    """Schema für Regel-Liste."""
    id: UUID
    name: str
    priority: int
    is_active: bool
    match_count: int
    last_matched_at: Optional[datetime]
    applies_to_all: bool


class RuleReorderRequest(BaseModel):
    """Schema für Regel-Umordnung."""
    priorities: List[dict]  # [{"rule_id": UUID, "priority": int}, ...]


class RuleTestRequest(BaseModel):
    """Schema für Regel-Test."""
    metadata: dict
    source_type: str = "email"


# --- Import Log Schemas ---

class ImportLogResponse(BaseModel):
    """Schema für Import-Log-Response."""
    id: UUID
    user_id: UUID
    source_type: str
    email_config_id: Optional[UUID]
    folder_config_id: Optional[UUID]
    batch_id: UUID
    email_from: Optional[str]
    email_subject: Optional[str]
    email_date: Optional[datetime]
    original_path: Optional[str]
    original_filename: Optional[str]
    status: str
    document_id: Optional[UUID]
    file_hash: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    matched_rule_id: Optional[UUID]
    applied_actions: dict
    error_message: Optional[str]
    error_code: Optional[str]
    retry_count: int
    started_at: datetime
    completed_at: Optional[datetime]
    processing_duration_ms: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class ImportStatsResponse(BaseModel):
    """Schema für Import-Statistiken."""
    total_imports: int
    successful_imports: int
    failed_imports: int
    skipped_imports: int
    documents_created: int
    avg_processing_time_ms: float
    imports_by_source: dict
    imports_by_day: List[dict]


class ImportRunResponse(BaseModel):
    """Ein Import-Lauf (alle ImportLogs eines batch_id zusammengefasst).

    Liefert die Daten für die Live-Status-Anzeige im Frontend: pro Lauf
    Anzahl Einträge, davon OK/Fehler, Status und Zeitfenster.
    """
    batch_id: UUID
    source_type: str
    config_id: Optional[UUID]
    total: int
    completed: int
    failed: int
    skipped: int
    pending: int
    documents_created: int
    is_running: bool
    started_at: datetime
    last_update: Optional[datetime]


# =============================================================================
# Email Config Endpoints
# =============================================================================


@router.get("/email/configs", response_model=List[EmailConfigListResponse])
async def list_email_configs(
    company_id: Optional[UUID] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listet alle Email-Import-Konfigurationen des Benutzers."""
    service = EmailImportService(db)
    configs = await service.list_configs(
        user_id=current_user.id,
        company_id=company_id,
        active_only=active_only,
    )
    return configs


@router.post("/email/configs", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_email_config(
    config: EmailConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine neue Email-Import-Konfiguration."""
    service = EmailImportService(db)

    try:
        config_id = await service.create_config(
            user_id=current_user.id,
            **config.model_dump(),
        )
        return {"id": config_id, "message": "Konfiguration erstellt"}
    except Exception as e:
        logger.error("email_config_create_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Import")
        )


@router.get("/email/configs/{config_id}", response_model=EmailConfigResponse)
async def get_email_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt eine Email-Import-Konfiguration."""
    service = EmailImportService(db)
    config = await service.get_config(config_id, current_user.id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    return config


@router.put("/email/configs/{config_id}")
async def update_email_config(
    config_id: UUID,
    updates: EmailConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktualisiert eine Email-Import-Konfiguration."""
    service = EmailImportService(db)

    update_data = updates.model_dump(exclude_unset=True)
    success = await service.update_config(
        config_id=config_id,
        user_id=current_user.id,
        **update_data,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    return {"message": "Konfiguration aktualisiert"}


@router.delete("/email/configs/{config_id}")
async def delete_email_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Löscht eine Email-Import-Konfiguration."""
    service = EmailImportService(db)
    success = await service.delete_config(config_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    return {"message": "Konfiguration gelöscht"}


@router.post("/email/configs/{config_id}/test")
async def test_email_connection(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Testet die IMAP-Verbindung einer Konfiguration."""
    service = EmailImportService(db)
    result = await service.test_connection(config_id, current_user.id)
    return result


@router.post("/email/configs/{config_id}/sync")
async def sync_email_config(
    config_id: UUID,
    max_emails: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Führt manuellen Email-Sync durch."""
    service = EmailImportService(db)
    result = await service.sync_emails(
        config_id=config_id,
        user_id=current_user.id,
        max_emails=max_emails,
    )

    return {
        "emails_processed": result.emails_processed,
        "attachments_extracted": result.attachments_extracted,
        "documents_created": result.documents_created,
        "duplicates_skipped": result.duplicates_skipped,
        "errors": result.errors,
        "created_document_ids": [str(d) for d in result.created_document_ids],
    }


# =============================================================================
# Folder Config Endpoints
# =============================================================================


@router.get("/folder/configs", response_model=List[FolderConfigListResponse])
async def list_folder_configs(
    company_id: Optional[UUID] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listet alle Folder-Import-Konfigurationen des Benutzers."""
    service = FolderImportService(db)
    configs = await service.list_configs(
        user_id=current_user.id,
        company_id=company_id,
        active_only=active_only,
    )
    return configs


@router.post("/folder/configs", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_folder_config(
    config: FolderConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine neue Folder-Import-Konfiguration."""
    service = FolderImportService(db)

    try:
        config_id = await service.create_config(
            user_id=current_user.id,
            **config.model_dump(),
        )
        return {"id": config_id, "message": "Konfiguration erstellt"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Import")
        )
    except Exception as e:
        logger.error("folder_config_create_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Import")
        )


@router.get("/folder/configs/{config_id}", response_model=FolderConfigResponse)
async def get_folder_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt eine Folder-Import-Konfiguration."""
    service = FolderImportService(db)
    config = await service.get_config(config_id, current_user.id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    return config


@router.put("/folder/configs/{config_id}")
async def update_folder_config(
    config_id: UUID,
    updates: FolderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktualisiert eine Folder-Import-Konfiguration."""
    service = FolderImportService(db)

    try:
        update_data = updates.model_dump(exclude_unset=True)
        success = await service.update_config(
            config_id=config_id,
            user_id=current_user.id,
            **update_data,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konfiguration nicht gefunden"
            )

        return {"message": "Konfiguration aktualisiert"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Import")
        )


@router.delete("/folder/configs/{config_id}")
async def delete_folder_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Löscht eine Folder-Import-Konfiguration."""
    service = FolderImportService(db)
    success = await service.delete_config(config_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    return {"message": "Konfiguration gelöscht"}


@router.post("/folder/configs/{config_id}/start")
async def start_folder_watcher(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Startet den Folder-Watcher."""
    service = FolderImportService(db)
    result = await service.start_watcher(config_id, current_user.id)
    return result


@router.post("/folder/configs/{config_id}/stop")
async def stop_folder_watcher(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stoppt den Folder-Watcher."""
    service = FolderImportService(db)
    result = await service.stop_watcher(config_id, current_user.id)
    return result


@router.post("/folder/configs/{config_id}/poll")
async def poll_folder(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Führt manuellen Folder-Scan durch."""
    service = FolderImportService(db)
    result = await service.poll_folder(config_id, current_user.id)

    return {
        "files_processed": result.files_processed,
        "documents_created": result.documents_created,
        "duplicates_skipped": result.duplicates_skipped,
        "files_moved": result.files_moved,
        "errors": result.errors,
        "created_document_ids": [str(d) for d in result.created_document_ids],
    }


# =============================================================================
# Import Rules Endpoints
# =============================================================================


@router.get("/rules", response_model=List[RuleListResponse])
async def list_import_rules(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listet alle Import-Regeln des Benutzers."""
    service = ImportRuleService(db)
    rules = await service.list_rules(
        user_id=current_user.id,
        active_only=active_only,
    )
    return rules


@router.post("/rules", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_import_rule(
    rule: RuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine neue Import-Regel."""
    service = ImportRuleService(db)

    try:
        rule_id = await service.create_rule(
            user_id=current_user.id,
            **rule.model_dump(),
        )
        return {"id": rule_id, "message": "Regel erstellt"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Import")
        )


@router.get("/rules/{rule_id}", response_model=RuleResponse)
async def get_import_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt eine Import-Regel."""
    service = ImportRuleService(db)
    rule = await service.get_rule(rule_id, current_user.id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden"
        )

    return rule


@router.put("/rules/{rule_id}")
async def update_import_rule(
    rule_id: UUID,
    updates: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktualisiert eine Import-Regel."""
    service = ImportRuleService(db)

    try:
        update_data = updates.model_dump(exclude_unset=True)
        success = await service.update_rule(
            rule_id=rule_id,
            user_id=current_user.id,
            **update_data,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regel nicht gefunden"
            )

        return {"message": "Regel aktualisiert"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Import")
        )


@router.delete("/rules/{rule_id}")
async def delete_import_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Löscht eine Import-Regel."""
    service = ImportRuleService(db)
    success = await service.delete_rule(rule_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden"
        )

    return {"message": "Regel gelöscht"}


@router.post("/rules/reorder")
async def reorder_import_rules(
    request: RuleReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ändert die Prioritaeten mehrerer Regeln."""
    service = ImportRuleService(db)

    priorities = [
        (UUID(p["rule_id"]), int(p["priority"]))
        for p in request.priorities
    ]

    success = await service.reorder_rules(
        user_id=current_user.id,
        rule_priorities=priorities,
    )

    return {"message": "Prioritaeten aktualisiert"}


@router.post("/rules/{rule_id}/test")
async def test_import_rule(
    rule_id: UUID,
    request: RuleTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Testet eine einzelne Regel gegen Test-Metadaten."""
    service = ImportRuleService(db)
    result = await service.test_rule(
        rule_id=rule_id,
        user_id=current_user.id,
        test_metadata=request.metadata,
    )
    return result


@router.post("/rules/test-all")
async def test_all_import_rules(
    request: RuleTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Testet alle Regeln gegen Test-Metadaten."""
    service = ImportRuleService(db)
    result = await service.test_all_rules(
        user_id=current_user.id,
        test_metadata=request.metadata,
        source_type=request.source_type,
    )
    return result


@router.get("/rules/schema/fields")
async def get_rule_fields(
    current_user: User = Depends(get_current_user),
):
    """Gibt verfügbare Bedingungs-Felder zurück."""
    return ImportRuleService.get_available_fields()


@router.get("/rules/schema/operators")
async def get_rule_operators(
    current_user: User = Depends(get_current_user),
):
    """Gibt verfügbare Operatoren zurück."""
    return ImportRuleService.get_available_operators()


@router.get("/rules/schema/actions")
async def get_rule_actions(
    current_user: User = Depends(get_current_user),
):
    """Gibt verfügbare Aktionen zurück."""
    return ImportRuleService.get_available_actions()


# =============================================================================
# Import Logs Endpoints
# =============================================================================


@router.get("/logs", response_model=List[ImportLogResponse])
async def list_import_logs(
    source_type: Optional[str] = Query(None, pattern="^(email|folder)$"),
    config_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, pattern="^(pending|processing|completed|failed|skipped)$"),
    page: int = Query(default=1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(default=50, ge=1, le=500, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listet Import-Logs mit Filtern."""
    from sqlalchemy import select
    from app.db.models import ImportLog

    query = select(ImportLog).where(ImportLog.user_id == current_user.id)

    if source_type:
        query = query.where(ImportLog.source_type == source_type)

    if config_id:
        if source_type == "email":
            query = query.where(ImportLog.email_config_id == config_id)
        elif source_type == "folder":
            query = query.where(ImportLog.folder_config_id == config_id)

    if status_filter:
        query = query.where(ImportLog.status == status_filter)

    query = query.order_by(ImportLog.started_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    return logs


@router.get("/runs", response_model=List[ImportRunResponse])
async def list_import_runs(
    source_type: Optional[str] = Query(None, pattern="^(email|folder)$"),
    config_id: Optional[UUID] = None,
    limit: int = Query(default=20, ge=1, le=100, description="Anzahl der letzten Läufe"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ImportRunResponse]:
    """Listet die letzten Import-Läufe (gruppiert nach batch_id).

    Grundlage für die Live-Status-Anzeige: Statt Einzel-Logs liefert dieser
    Endpoint pro Lauf eine Zusammenfassung (N E-Mails, k OK, m Fehler). Das
    Frontend pollt ihn, solange ``is_running`` für einen Lauf true ist.
    """
    from sqlalchemy import select, func, case, String
    from app.db.models import ImportLog

    completed_expr = func.count(case((ImportLog.status == "completed", 1)))
    failed_expr = func.count(case((ImportLog.status == "failed", 1)))
    skipped_expr = func.count(case((ImportLog.status == "skipped", 1)))
    pending_expr = func.count(
        case((ImportLog.status.in_(("pending", "processing")), 1))
    )
    docs_expr = func.count(case((ImportLog.document_id.isnot(None), 1)))
    # PostgreSQL kennt kein min(uuid); source_type/config_id sind pro batch_id
    # konstant -> als String aggregieren und in der Response zurueckcasten.
    config_id_text = func.min(
        func.cast(
            func.coalesce(ImportLog.email_config_id, ImportLog.folder_config_id),
            String,
        )
    )

    query = (
        select(
            ImportLog.batch_id.label("batch_id"),
            func.min(ImportLog.source_type).label("source_type"),
            config_id_text.label("config_id"),
            func.count().label("total"),
            completed_expr.label("completed"),
            failed_expr.label("failed"),
            skipped_expr.label("skipped"),
            pending_expr.label("pending"),
            docs_expr.label("documents_created"),
            func.min(ImportLog.started_at).label("started_at"),
            func.max(
                func.coalesce(ImportLog.completed_at, ImportLog.started_at)
            ).label("last_update"),
        )
        .where(ImportLog.user_id == current_user.id)
        .group_by(ImportLog.batch_id)
    )

    if source_type:
        query = query.where(ImportLog.source_type == source_type)
    if config_id:
        query = query.where(
            (ImportLog.email_config_id == config_id)
            | (ImportLog.folder_config_id == config_id)
        )

    query = query.order_by(func.min(ImportLog.started_at).desc()).limit(limit)

    rows = (await db.execute(query)).all()

    return [
        ImportRunResponse(
            batch_id=row.batch_id,
            source_type=row.source_type,
            config_id=UUID(row.config_id) if row.config_id else None,
            total=row.total,
            completed=row.completed,
            failed=row.failed,
            skipped=row.skipped,
            pending=row.pending,
            documents_created=row.documents_created,
            is_running=row.pending > 0,
            started_at=row.started_at,
            last_update=row.last_update,
        )
        for row in rows
    ]


@router.get("/logs/{log_id}", response_model=ImportLogResponse)
async def get_import_log(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt Details eines Import-Logs."""
    from sqlalchemy import select
    from app.db.models import ImportLog

    result = await db.execute(
        select(ImportLog).where(
            ImportLog.id == log_id,
            ImportLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log nicht gefunden"
        )

    return log


@router.post("/logs/{log_id}/retry")
async def retry_failed_import(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Wiederholt einen fehlgeschlagenen Import."""
    from sqlalchemy import select
    from app.db.models import ImportLog

    result = await db.execute(
        select(ImportLog).where(
            ImportLog.id == log_id,
            ImportLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log nicht gefunden"
        )

    if log.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur fehlgeschlagene Imports können wiederholt werden"
        )

    # Retry-Logik (wird über Celery Task implementiert)
    from app.workers.tasks.import_tasks import retry_import_task

    retry_import_task.delay(str(log_id))

    log.retry_count += 1
    log.status = "pending"
    await db.commit()

    return {"message": "Import wird wiederholt", "retry_count": log.retry_count}


@router.get("/logs/stats", response_model=ImportStatsResponse)
async def get_import_stats(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt Import-Statistiken."""
    from sqlalchemy import select, func
    from datetime import timedelta
    from app.db.models import ImportLog

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Basis-Query
    base_query = select(ImportLog).where(
        ImportLog.user_id == current_user.id,
        ImportLog.started_at >= start_date,
    )

    # Gesamtanzahl
    total_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total_imports = total_result.scalar() or 0

    # Nach Status
    status_counts = {}
    for status_value in ["completed", "failed", "skipped"]:
        count_result = await db.execute(
            select(func.count()).where(
                ImportLog.user_id == current_user.id,
                ImportLog.started_at >= start_date,
                ImportLog.status == status_value,
            )
        )
        status_counts[status_value] = count_result.scalar() or 0

    # Dokumente erstellt
    docs_result = await db.execute(
        select(func.count()).where(
            ImportLog.user_id == current_user.id,
            ImportLog.started_at >= start_date,
            ImportLog.document_id.isnot(None),
        )
    )
    documents_created = docs_result.scalar() or 0

    # Durchschnittliche Verarbeitungszeit
    avg_result = await db.execute(
        select(func.avg(ImportLog.processing_duration_ms)).where(
            ImportLog.user_id == current_user.id,
            ImportLog.started_at >= start_date,
            ImportLog.processing_duration_ms.isnot(None),
        )
    )
    avg_processing_time = avg_result.scalar() or 0

    # Nach Quelle
    source_counts = {}
    for source in ["email", "folder"]:
        count_result = await db.execute(
            select(func.count()).where(
                ImportLog.user_id == current_user.id,
                ImportLog.started_at >= start_date,
                ImportLog.source_type == source,
            )
        )
        source_counts[source] = count_result.scalar() or 0

    # Imports nach Tag für Chart-Daten (letzte 30 Tage)
    imports_by_day_result = await db.execute(
        select(
            func.date(ImportLog.started_at).label("date"),
            func.count().label("count"),
            func.count().filter(ImportLog.status == "completed").label("successful"),
            func.count().filter(ImportLog.status == "failed").label("failed"),
        )
        .where(
            ImportLog.user_id == current_user.id,
            ImportLog.started_at >= start_date,
        )
        .group_by(func.date(ImportLog.started_at))
        .order_by(func.date(ImportLog.started_at))
    )
    imports_by_day = [
        {
            "date": str(row.date),
            "count": row.count,
            "successful": row.successful,
            "failed": row.failed,
        }
        for row in imports_by_day_result.all()
    ]

    return {
        "total_imports": total_imports,
        "successful_imports": status_counts.get("completed", 0),
        "failed_imports": status_counts.get("failed", 0),
        "skipped_imports": status_counts.get("skipped", 0),
        "documents_created": documents_created,
        "avg_processing_time_ms": float(avg_processing_time),
        "imports_by_source": source_counts,
        "imports_by_day": imports_by_day,
    }
