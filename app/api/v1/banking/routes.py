"""
Banking API Endpoints.

Verwaltet Bankkonten und Kontoauszug-Importe:
- Bank-Konto CRUD (manuell, ohne FinTS)
- Datei-Import (MT940, CAMT.053, CSV)
- Import-Historie

Alle Antworten auf Deutsch.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

# SECURITY FIX 27-4: Rate Limiting für Banking Endpoints
from app.core.rate_limiting import limiter, get_user_identifier

# SECURITY FIX: PII leakage prevention (CWE-532)
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.security_auth import build_content_disposition

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.db.models import User
from app.services.banking.account_service import AccountService
from app.services.banking.import_service import ImportService
from app.services.banking.transaction_service import TransactionService
from app.services.banking.reconciliation_service import ReconciliationService, MatchCandidate
from app.services.banking.payment_service import PaymentService
from app.services.banking.tan_handler_service import TANHandlerService, TANMethod
from app.services.banking.cash_flow_service import CashFlowService, ForecastScenario
from app.services.banking.dunning_service import DunningService, DunningAction
from app.services.banking.aging_report_service import AgingReportService
from app.services.banking.mahn_task_service import MahnTaskService
from app.services.banking.dunning_stage_service import DunningStageConfigService
from app.services.banking.payment_automation_service import (
    PaymentAutomationService,
    get_payment_automation_service,
    PaymentPriority,
    PaymentStrategy,
    PaymentBatchStatus,
    SuggestionReason,
    PaymentSuggestion,
    PaymentBatch,
    PaymentSchedule,
    AutomationConfig,
)
from app.services.banking.models import (
    BankAccountCreate,
    BankAccountUpdate,
    BankAccountResponse,
    BankAccountWithStats,
    BankImportPreview,
    BankImportResponse,
    BankTransactionResponse,
    ImportFormat,
    ReconciliationStatus,
    SupportedFormatsResponse,
    TransactionFilter,
    TransactionStats,
    TransactionType,
    TransactionSortField,
    ReconciliationResult,
    BatchReconciliationResult,
    TransactionMatch,
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentStatus,
    PaymentType,
    DunningLevel,
    DunningStatus,
    DunningRecordResponse,
    # Mahnungswesen Schemas
    MahnTaskType,
    MahnTaskStatus,
    MahnTaskCreate,
    MahnTaskResponse,
    MahnTaskWithDunning,
    MahnTaskFilter,
    MahnTaskSnoozeRequest,
    MahnTaskCompleteRequest,
    MahnTaskBulkCompleteRequest,
    MahnTaskSummary,
    PhoneCallLogCreate,
    PhoneCallLogResponse,
    PhoneCallLogListResponse,
    PhoneCallOutcome,
    DunningActionType,
    DunningStageConfigCreate,
    DunningStageConfigUpdate,
    DunningStageConfigResponse,
    DunningStageReorderRequest,
    DunningStagesListResponse,
    CustomerDunningOverrideCreate,
    CustomerDunningOverrideUpdate,
    CustomerDunningOverrideResponse,
    MahnungHistoryResponse,
    MahnungHistoryListResponse,
    MahnstoppSetRequest,
    MahnstoppLiftRequest,
    BulkEscalateRequest,
    BulkEscalateResponse,
    BulkSendReminderRequest,
    BulkSendReminderResponse,
    B2BPauschaleClaimResponse,
    VerzugszinsenCalculation,
    ContactMethod,
    # Auto-Mahnlauf Schemas
    AutoDunningSettingsResponse,
    AutoDunningSettingsUpdate,
    AutomaticDunningAction,
)

logger = structlog.get_logger(__name__)

# ==================== Routers ====================

accounts_router = APIRouter(prefix="/banking/accounts", tags=["Banking - Konten"])
imports_router = APIRouter(prefix="/banking/import", tags=["Banking - Import"])
transactions_router = APIRouter(prefix="/banking/transactions", tags=["Banking - Transaktionen"])
reconciliation_router = APIRouter(prefix="/banking/reconciliation", tags=["Banking - Abgleich"])
payments_router = APIRouter(prefix="/banking/payments", tags=["Banking - Zahlungen"])
cashflow_router = APIRouter(prefix="/banking/cashflow", tags=["Banking - Cash-Flow"])
dunning_router = APIRouter(prefix="/banking/dunning", tags=["Banking - Mahnwesen"])
aging_router = APIRouter(prefix="/banking/aging", tags=["Banking - Altersanalyse"])
# Neue Mahnungswesen Routers
mahn_tasks_router = APIRouter(prefix="/banking/mahn-tasks", tags=["Banking - Mahnaufgaben"])
dunning_settings_router = APIRouter(prefix="/banking/settings", tags=["Banking - Mahneinstellungen"])
customer_dunning_router = APIRouter(prefix="/banking/customers", tags=["Banking - Kundeneinstellungen"])
# Phase 5.4: Payment Automation Router
payment_automation_router = APIRouter(prefix="/banking/payment-automation", tags=["Banking - Zahlungsautomation"])

# Service instances
account_service = AccountService()
import_service = ImportService()
transaction_service = TransactionService()
reconciliation_service = ReconciliationService()
payment_service = PaymentService()
tan_handler_service = TANHandlerService()
cash_flow_service = CashFlowService()
dunning_service = DunningService()
aging_report_service = AgingReportService()
# Neue Mahnungswesen Services
mahn_task_service = MahnTaskService()
dunning_stage_service = DunningStageConfigService()
# Phase 5.4: Payment Automation Service
payment_automation_service = PaymentAutomationService()


# ==================== SECURITY: File Upload Validation ====================

# Maximale Dateigröße: 10 MB
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024

# Erlaubte Dateiendungen für Bank-Imports
ALLOWED_EXTENSIONS = {".mt940", ".sta", ".xml", ".csv", ".txt", ".940", ".pdf"}

# Erlaubte Content-Types
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/csv",
    "text/xml",
    "application/xml",
    "application/pdf",
    "application/octet-stream",  # Für generische Uploads
}

# Magic-Bytes für Dateiformat-Erkennung
MAGIC_BYTES = {
    "xml": [b"<?xml", b"<Document", b"<BkToCstmrStmt"],  # CAMT.053, ZUGFeRD
    "pdf": [b"%PDF-"],
    "mt940": [b":20:", b":25:", b"\n:20:"],  # MT940 Start
}


async def validate_upload_file(
    file: UploadFile,
    max_size: int = MAX_UPLOAD_SIZE_BYTES,
) -> bytes:
    """Validiere hochgeladene Datei für Sicherheit.

    SECURITY: Prüft Dateigröße, Endung, Content-Type und Magic-Bytes.

    Args:
        file: Hochgeladene Datei
        max_size: Maximale Dateigröße in Bytes

    Returns:
        Datei-Inhalt als Bytes

    Raises:
        HTTPException: Bei Validierungsfehlern
    """
    # 1. Dateiname validieren
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dateiname fehlt.",
        )

    # Endung prüfen
    filename_lower = file.filename.lower()
    ext = None
    for allowed_ext in ALLOWED_EXTENSIONS:
        if filename_lower.endswith(allowed_ext):
            ext = allowed_ext
            break

    if not ext:
        logger.warning(
            "upload_rejected_extension",
            filename=file.filename,
            allowed=list(ALLOWED_EXTENSIONS),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dateiendung nicht erlaubt. Erlaubt: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 2. Content-Type prüfen (wenn vorhanden)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(
            "upload_rejected_content_type",
            filename=file.filename,
            content_type=file.content_type,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nicht unterstützter Dateityp.",
        )

    # 3. Dateigröße prüfen (lese in Chunks)
    content = b""
    chunk_size = 8192  # 8KB Chunks

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content += chunk

        if len(content) > max_size:
            logger.warning(
                "upload_rejected_size",
                filename=file.filename,
                max_size_mb=max_size / 1024 / 1024,
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Datei zu groß. Maximum: {max_size / 1024 / 1024:.0f} MB",
            )

    # 4. Magic-Bytes prüfen (grundlegende Validierung)
    if ext == ".xml" or ext == ".pdf":
        content_start = content[:100]  # Erste 100 Bytes

        if ext == ".pdf":
            if not any(content_start.startswith(magic) for magic in MAGIC_BYTES["pdf"]):
                logger.warning(
                    "upload_rejected_magic_bytes",
                    filename=file.filename,
                    expected="PDF",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Datei ist keine gültige PDF.",
                )

        if ext == ".xml":
            # XML muss mit <?xml oder einem Element beginnen
            if not (content_start.strip().startswith(b"<") or
                    content_start.strip().startswith(b"\xef\xbb\xbf<")):  # BOM + <
                logger.warning(
                    "upload_rejected_magic_bytes",
                    filename=file.filename,
                    expected="XML",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Datei ist kein gültiges XML.",
                )

    logger.info(
        "upload_validated",
        filename=file.filename,
        size_bytes=len(content),
        extension=ext,
    )

    return content


# ==================== Account Endpoints ====================

# SECURITY FIX 27-4: Rate-Limit für Account-Erstellung
@limiter.limit("10/minute", key_func=get_user_identifier)
@accounts_router.post(
    "",
    response_model=BankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bankkonto registrieren",
    description="Erstellt ein neues Bankkonto für manuellen Import."
)
async def create_account(
    request: Request,  # SECURITY FIX 27-4: Required for rate limiter
    data: BankAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankAccountResponse:
    """
    Registriere ein neues Bankkonto.

    Das Konto wird für manuellen Datei-Import verwendet.
    Die IBAN wird automatisch validiert (MOD-97 Prüfung).

    Hinweis: FinTS-Verbindung ist optional und erfordert
    eine Produkt-ID bei der Deutschen Kreditwirtschaft.
    """
    logger.info(
        "banking_account_create",
        user_id=str(current_user.id),
        iban_prefix=data.iban[:4] if data.iban else None,
    )

    try:
        account = await account_service.create_account(
            db=db,
            company_id=company_id,
            data=data,
        )

        logger.info(
            "banking_account_created",
            account_id=str(account.id),
            user_id=str(current_user.id),
        )

        return account

    except ValueError as e:
        logger.warning(
            "banking_account_create_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Konto konnte nicht erstellt werden. Bitte überprüfen Sie die IBAN und Kontodaten.",
        )


@accounts_router.get(
    "",
    response_model=List[BankAccountResponse],
    summary="Bankkonten auflisten",
    description="Gibt alle Bankkonten des aktuellen Benutzers zurück."
)
async def list_accounts(
    include_inactive: bool = Query(False, description="Inaktive Konten einschließen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[BankAccountResponse]:
    """Hole alle Bankkonten des Benutzers."""
    accounts = await account_service.get_accounts(
        db=db,
        company_id=company_id,
        include_inactive=include_inactive,
    )
    return accounts


@accounts_router.get(
    "/with-stats",
    response_model=List[BankAccountWithStats],
    summary="Bankkonten mit Statistiken",
    description="Gibt Bankkonten mit Transaktions- und Abgleich-Statistiken zurück."
)
async def list_accounts_with_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[BankAccountWithStats]:
    """Hole Bankkonten mit erweiterten Statistiken."""
    return await account_service.get_accounts_with_stats(
        db=db,
        company_id=company_id,
    )


@accounts_router.get(
    "/{account_id}",
    response_model=BankAccountResponse,
    summary="Bankkonto abrufen",
    description="Gibt ein einzelnes Bankkonto zurück."
)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankAccountResponse:
    """Hole ein einzelnes Bankkonto."""
    account = await account_service.get_account(
        db=db,
        company_id=company_id,
        account_id=account_id,
    )

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bankkonto nicht gefunden",
        )

    return account


@accounts_router.put(
    "/{account_id}",
    response_model=BankAccountResponse,
    summary="Bankkonto aktualisieren",
    description="Aktualisiert ein bestehendes Bankkonto."
)
async def update_account(
    account_id: UUID,
    data: BankAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankAccountResponse:
    """Aktualisiere ein Bankkonto."""
    account = await account_service.update_account(
        db=db,
        company_id=company_id,
        account_id=account_id,
        data=data,
    )

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bankkonto nicht gefunden",
        )

    logger.info(
        "banking_account_updated",
        account_id=str(account_id),
        user_id=str(current_user.id),
    )

    return account


@accounts_router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Bankkonto löschen",
    description="Löscht ein Bankkonto (Soft-Delete)."
)
async def delete_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Response:
    """
    Lösche ein Bankkonto.

    Das Konto wird nicht physisch gelöscht, sondern nur als
    gelöscht markiert (Soft-Delete). Transaktionen bleiben erhalten.
    """
    deleted = await account_service.delete_account(
        db=db,
        company_id=company_id,
        account_id=account_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bankkonto nicht gefunden",
        )

    logger.info(
        "banking_account_deleted",
        account_id=str(account_id),
        user_id=str(current_user.id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Import Endpoints ====================

@imports_router.get(
    "/formats",
    response_model=SupportedFormatsResponse,
    summary="Unterstützte Formate",
    description="Gibt alle unterstützten Import-Formate zurück."
)
async def get_supported_formats(
    current_user: User = Depends(get_current_active_user),  # X.4 SECURITY FIX: Auth required
) -> SupportedFormatsResponse:
    """
    Hole Liste aller unterstützten Import-Formate.

    **REQUIRES AUTHENTICATION**

    Unterstützt werden:
    - MT940 (SWIFT) - Universelles Bankformat
    - CAMT.053 (ISO 20022) - Modernes XML-Format
    - Bank-spezifische CSV-Formate (Sparkasse, VR, DKB, etc.)

    Args:
        current_user: Authenticated user (required)
    """
    return await import_service.get_supported_formats()


# SECURITY FIX 27-4: Rate-Limit für Import-Vorschau
@limiter.limit("30/minute", key_func=get_user_identifier)
@imports_router.post(
    "/preview",
    response_model=BankImportPreview,
    summary="Import-Vorschau",
    description="Erstellt eine Vorschau vor dem eigentlichen Import."
)
async def preview_import(
    request: Request,  # SECURITY FIX 27-4: Required for rate limiter
    file: UploadFile = File(..., description="Kontoauszug-Datei"),
    format_hint: Optional[ImportFormat] = Form(
        None,
        description="Optionales Format (sonst Auto-Erkennung)"
    ),
    current_user: User = Depends(get_current_active_user),
) -> BankImportPreview:
    """
    Erstelle Vorschau eines Kontoauszugs.

    Analysiert die Datei und gibt zurück:
    - Erkanntes Format und Konfidenz
    - Anzahl Transaktionen
    - Zeitraum (von/bis)
    - Summe Eingänge/Ausgänge
    - Erste Beispiel-Transaktionen

    Der eigentliche Import erfolgt noch nicht.
    SECURITY: Datei wird vor Verarbeitung validiert.
    """
    # SECURITY: Validiere Datei vor Verarbeitung
    content = await validate_upload_file(file)

    logger.info(
        "banking_import_preview",
        user_id=str(current_user.id),
        filename=file.filename,
        size_bytes=len(content),
    )

    try:
        preview = await import_service.preview_import(
            content=content,
            filename=file.filename,
            format_hint=format_hint,
        )

        logger.info(
            "banking_import_preview_complete",
            user_id=str(current_user.id),
            format=preview.format_detected.value if preview.format_detected else None,
            transaction_count=preview.transaction_count,
        )

        return preview

    except Exception as e:
        logger.error(
            "banking_import_preview_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datei konnte nicht analysiert werden. Bitte überprüfen Sie das Dateiformat.",
        )


# SECURITY FIX 27-4: Rate-Limit für Import - ressourcenintensiv!
@limiter.limit("20/minute", key_func=get_user_identifier)
@imports_router.post(
    "",
    response_model=BankImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kontoauszug importieren",
    description="Importiert einen Kontoauszug und erstellt Transaktionen."
)
async def import_file(
    request: Request,  # SECURITY FIX 27-4: Required for rate limiter
    file: UploadFile = File(..., description="Kontoauszug-Datei"),
    bank_account_id: Optional[UUID] = Form(
        None,
        description="Ziel-Bankkonto (optional, wird aus IBAN ermittelt)"
    ),
    format_hint: Optional[ImportFormat] = Form(
        None,
        description="Optionales Format (sonst Auto-Erkennung)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankImportResponse:
    """
    Importiere Kontoauszug in das System.

    Unterstützte Formate:
    - MT940 (SWIFT) - Universal von allen Banken
    - CAMT.053 (ISO 20022) - Modernes XML-Format
    - Bank-spezifische CSV (Sparkasse, VR, DKB, N26, etc.)

    Duplikate werden automatisch erkannt und übersprungen.
    SECURITY: Datei wird vor Verarbeitung validiert.
    """
    # SECURITY: Validiere Datei vor Verarbeitung
    content = await validate_upload_file(file)

    logger.info(
        "banking_import_start",
        user_id=str(current_user.id),
        filename=file.filename,
        size_bytes=len(content),
        bank_account_id=str(bank_account_id) if bank_account_id else None,
    )

    try:
        response, transaction_ids = await import_service.import_file(
            db=db,
            company_id=company_id,
            content=content,
            filename=file.filename,
            bank_account_id=bank_account_id,
            format_hint=format_hint,
        )

        logger.info(
            "banking_import_complete",
            user_id=str(current_user.id),
            import_id=str(response.id),
            transaction_count=response.transaction_count,
            duplicate_count=response.duplicate_count,
            error_count=response.error_count,
        )

        return response

    except ValueError as e:
        logger.warning(
            "banking_import_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import fehlgeschlagen. Bitte überprüfen Sie das Dateiformat und die Daten.",
        )
    except Exception as e:
        logger.error(
            "banking_import_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Import fehlgeschlagen. Bitte überprüfen Sie das Dateiformat.",
        )


@imports_router.get(
    "/history",
    response_model=List[BankImportResponse],
    summary="Import-Historie",
    description="Gibt die Import-Historie zurück."
)
async def get_import_history(
    bank_account_id: Optional[UUID] = Query(
        None,
        description="Filter auf Bankkonto"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[BankImportResponse]:
    """Hole Import-Historie."""
    return await import_service.get_import_history(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        limit=limit,
    )


# ==================== Transaction Endpoints ====================

@transactions_router.get(
    "",
    response_model=dict,
    summary="Transaktionen auflisten",
    description="Gibt Transaktionen mit optionaler Filterung und Paginierung zurück."
)
async def list_transactions(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    amount_min: Optional[float] = Query(None, description="Mindestbetrag"),
    amount_max: Optional[float] = Query(None, description="Höchstbetrag"),
    transaction_type: Optional[TransactionType] = Query(None, description="Transaktionstyp"),
    reconciliation_status: Optional[ReconciliationStatus] = Query(None, description="Abgleich-Status"),
    search: Optional[str] = Query(None, description="Volltextsuche"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    sort_by: TransactionSortField = Query(TransactionSortField.BOOKING_DATE, description="Sortierfeld"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sortierrichtung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Hole Transaktionen mit Filterung.

    Unterstützt Paginierung und verschiedene Filteroptionen.
    SECURITY: sort_by nutzt Enum-Whitelist zur SQL-Injection Prevention.
    """
    from decimal import Decimal

    filters = TransactionFilter(
        date_from=date_from,
        date_to=date_to,
        amount_min=Decimal(str(amount_min)) if amount_min is not None else None,
        amount_max=Decimal(str(amount_max)) if amount_max is not None else None,
        transaction_type=transaction_type,
        reconciliation_status=reconciliation_status,
        search_text=search,
    )

    transactions, total = await transaction_service.get_transactions(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        filters=filters,
        offset=(page - 1) * per_page,
        limit=per_page,
        sort_by=sort_by.value,  # SECURITY: Nur Enum-Werte erlaubt
        sort_order=sort_order,
    )

    return {
        "items": transactions,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@transactions_router.get(
    "/unmatched",
    response_model=List[BankTransactionResponse],
    summary="Unabgeglichene Transaktionen",
    description="Gibt alle unabgeglichenen Transaktionen zurück."
)
async def get_unmatched_transactions(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[BankTransactionResponse]:
    """Hole unabgeglichene Transaktionen für Reconciliation."""
    return await transaction_service.get_unmatched_transactions(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        limit=limit,
    )


@transactions_router.get(
    "/stats",
    response_model=TransactionStats,
    summary="Transaktions-Statistiken",
    description="Gibt aggregierte Statistiken zurück."
)
async def get_transaction_stats(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> TransactionStats:
    """Hole Transaktions-Statistiken."""
    return await transaction_service.get_transaction_stats(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
    )


@transactions_router.get(
    "/monthly",
    response_model=List[dict],
    summary="Monatliche Zusammenfassung",
    description="Gibt monatliche Ein-/Ausgaben der letzten Monate zurück."
)
async def get_monthly_summary(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    months: int = Query(12, ge=1, le=36, description="Anzahl Monate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """Hole monatliche Zusammenfassung."""
    return await transaction_service.get_monthly_summary(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        months=months,
    )


@transactions_router.get(
    "/counterparties",
    response_model=List[dict],
    summary="Top Geschäftspartner",
    description="Gibt die wichtigsten Geschäftspartner nach Umsatz zurück."
)
async def get_top_counterparties(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    direction: str = Query("both", pattern="^(in|out|both)$", description="Richtung"),
    limit: int = Query(10, ge=1, le=50, description="Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """Hole Top-Geschäftspartner."""
    return await transaction_service.get_top_counterparties(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        direction=direction,
        limit=limit,
    )


@transactions_router.get(
    "/{transaction_id}",
    response_model=BankTransactionResponse,
    summary="Transaktion abrufen",
    description="Gibt eine einzelne Transaktion zurück."
)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankTransactionResponse:
    """Hole einzelne Transaktion."""
    transaction = await transaction_service.get_transaction(
        db=db,
        company_id=company_id,
        transaction_id=transaction_id,
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden",
        )

    return transaction


@transactions_router.patch(
    "/{transaction_id}",
    response_model=BankTransactionResponse,
    summary="Transaktion aktualisieren",
    description="Aktualisiert Notizen, Tags oder Kategorie einer Transaktion."
)
async def update_transaction(
    transaction_id: UUID,
    notes: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankTransactionResponse:
    """Aktualisiere Transaktions-Metadaten."""
    transaction = await transaction_service.update_transaction(
        db=db,
        company_id=company_id,
        transaction_id=transaction_id,
        notes=notes,
        tags=tags,
        category=category,
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden",
        )

    logger.info(
        "transaction_updated",
        transaction_id=str(transaction_id),
        user_id=str(current_user.id),
    )

    return transaction


@transactions_router.post(
    "/{transaction_id}/reconcile",
    response_model=BankTransactionResponse,
    summary="Transaktion abgleichen",
    description="Setzt den Abgleich-Status einer Transaktion."
)
async def reconcile_transaction(
    transaction_id: UUID,
    status_value: ReconciliationStatus,
    matched_document_id: Optional[UUID] = None,
    match_confidence: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BankTransactionResponse:
    """Setze Abgleich-Status einer Transaktion."""
    transaction = await transaction_service.set_reconciliation_status(
        db=db,
        company_id=company_id,
        transaction_id=transaction_id,
        status=status_value,
        matched_document_id=matched_document_id,
        match_confidence=match_confidence,
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden",
        )

    return transaction


# ==================== Reconciliation Endpoints ====================

@reconciliation_router.get(
    "/suggestions/{transaction_id}",
    response_model=List[dict],
    summary="Match-Vorschläge",
    description="Gibt mögliche Matches für eine Transaktion zurück."
)
async def get_match_suggestions(
    transaction_id: UUID,
    limit: int = Query(5, ge=1, le=20, description="Max. Vorschläge"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """
    Finde mögliche Match-Kandidaten für eine Transaktion.

    Nutzt verschiedene Matching-Strategien:
    - IBAN + Betrag (höchste Konfidenz)
    - Rechnungsnummer im Verwendungszweck
    - Kundennummer + Betrag + Datum
    - Betrag + Datum-Nähe
    - Fuzzy Name-Matching
    """
    candidates = await reconciliation_service.find_matches(
        db=db,
        company_id=company_id,
        transaction_id=transaction_id,
        limit=limit,
    )

    return [
        {
            "document_id": str(c.document_id),
            "invoice_number": c.invoice_number,
            "invoice_date": c.invoice_date.isoformat() if c.invoice_date else None,
            "due_date": c.due_date.isoformat() if c.due_date else None,
            "gross_amount": str(c.gross_amount),
            "counterparty_name": c.counterparty_name,
            "counterparty_iban": c.counterparty_iban,
            "confidence": c.confidence,
            "match_method": c.match_method,
            "match_details": c.match_details,
        }
        for c in candidates
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@reconciliation_router.post(
    "/match/{transaction_id}",
    response_model=dict,
    summary="Manueller Abgleich",
    description="Matcht eine Transaktion manuell mit einem Dokument."
)
async def manual_match(
    request: Request,  # SECURITY FIX 28-6: Required for rate limiter
    transaction_id: UUID,
    document_id: UUID,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Manuelles Matching einer Transaktion mit einem Dokument.

    Setzt Konfidenz auf 100% (manuell bestätigt).
    """
    try:
        result = await reconciliation_service.manual_match(
            db=db,
            company_id=company_id,
            transaction_id=transaction_id,
            document_id=document_id,
            notes=notes,
        )

        logger.info(
            "manual_match_success",
            transaction_id=str(transaction_id),
            document_id=str(document_id),
            user_id=str(current_user.id),
        )

        return {
            "success": True,
            "transaction_id": str(result.transaction_id),
            "document_id": str(result.matched_document_id),
            "confidence": result.match_confidence,
            "method": result.match_method,
        }

    except ValueError as e:
        logger.warning(
            "manual_match_failed",
            transaction_id=str(transaction_id),
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Abgleich konnte nicht durchgeführt werden. Transaktion oder Dokument nicht gefunden.",
        )


@limiter.limit("60/minute", key_func=get_user_identifier)
@reconciliation_router.post(
    "/unmatch/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Abgleich aufheben",
    description="Entfernt den Abgleich von einer Transaktion."
)
async def unmatch_transaction(
    request: Request,  # SECURITY FIX 28-6: Required for rate limiter
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Response:
    """Entferne Match von einer Transaktion."""
    success = await reconciliation_service.unmatch_transaction(
        db=db,
        company_id=company_id,
        transaction_id=transaction_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden",
        )

    logger.info(
        "unmatch_success",
        transaction_id=str(transaction_id),
        user_id=str(current_user.id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@limiter.limit("60/minute", key_func=get_user_identifier)
@reconciliation_router.post(
    "/split/{transaction_id}",
    response_model=List[dict],
    summary="Transaktion aufteilen",
    description="Teilt eine Transaktion auf mehrere Dokumente auf."
)
async def split_transaction(
    request: Request,  # SECURITY FIX 28-6: Required for rate limiter
    transaction_id: UUID,
    splits: List[dict],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """
    Teile eine Transaktion auf mehrere Dokumente auf.

    Für Sammelzahlungen oder Teilzahlungen.
    Summe der Split-Beträge muss dem Transaktionsbetrag entsprechen.
    """
    try:
        results = await reconciliation_service.split_transaction(
            db=db,
            company_id=company_id,
            transaction_id=transaction_id,
            splits=splits,
        )

        logger.info(
            "split_transaction_success",
            transaction_id=str(transaction_id),
            split_count=len(splits),
            user_id=str(current_user.id),
        )

        return [
            {
                "transaction_id": str(r.transaction_id),
                "document_id": str(r.matched_document_id),
                "status": r.status.value,
                "method": r.match_method,
            }
            for r in results
        ]

    except ValueError as e:
        logger.warning(
            "split_transaction_failed",
            transaction_id=str(transaction_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aufteilung fehlgeschlagen. Bitte überprüfen Sie die Beträge und Dokumente.",
        )


# SECURITY FIX 28-6: Rate-Limit für Batch-Operationen
@limiter.limit("10/minute", key_func=get_user_identifier)
@reconciliation_router.post(
    "/batch",
    response_model=dict,
    summary="Batch-Abgleich",
    description="Führt automatischen Abgleich für ungematchte Transaktionen durch."
)
async def batch_reconcile(
    request: Request,  # SECURITY FIX 28-6: Required for rate limiter
    bank_account_id: Optional[UUID] = None,
    limit: int = Query(100, ge=1, le=500, description="Max. Transaktionen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Automatischer Batch-Abgleich.

    Verarbeitet ungematchte Transaktionen und versucht automatischen
    Abgleich. Matched nur bei hoher Konfidenz (>= 90%).
    """
    result = await reconciliation_service.batch_reconcile(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        limit=limit,
    )

    logger.info(
        "batch_reconcile_completed",
        total=result.total_processed,
        matched=result.matched_count,
        partial=result.partial_count,
        unmatched=result.unmatched_count,
        user_id=str(current_user.id),
    )

    return {
        "total_processed": result.total_processed,
        "matched_count": result.matched_count,
        "partial_count": result.partial_count,
        "unmatched_count": result.unmatched_count,
        "match_rate": (
            result.matched_count / result.total_processed * 100
            if result.total_processed > 0 else 0
        ),
    }


# SECURITY FIX 28-6: Rate-Limit für Auto-Abgleich
@limiter.limit("60/minute", key_func=get_user_identifier)
@reconciliation_router.post(
    "/auto/{transaction_id}",
    response_model=dict,
    summary="Auto-Abgleich einzeln",
    description="Versucht automatischen Abgleich für eine einzelne Transaktion."
)
async def auto_reconcile_single(
    request: Request,  # SECURITY FIX 28-6: Required for rate limiter
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Automatischer Abgleich einer einzelnen Transaktion.

    Matched nur bei hoher Konfidenz (>= 90%).
    """
    result = await reconciliation_service.auto_reconcile_transaction(
        db=db,
        company_id=company_id,
        transaction_id=transaction_id,
    )

    if result:
        return {
            "matched": True,
            "transaction_id": str(result.transaction_id),
            "document_id": str(result.matched_document_id),
            "confidence": result.match_confidence,
            "method": result.match_method,
        }
    else:
        return {
            "matched": False,
            "transaction_id": str(transaction_id),
            "message": "Kein Match mit ausreichender Konfidenz gefunden",
        }


# ==================== Payment Endpoints ====================

@limiter.limit("30/minute", key_func=get_user_identifier)
@payments_router.post(
    "",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Zahlung erstellen",
    description="Erstellt einen neuen Zahlungsauftrag (SEPA-Überweisung)."
)
async def create_payment(
    request: Request,  # SECURITY FIX 28-5: Required for rate limiter
    data: PaymentOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentOrderResponse:
    """
    Erstelle neuen Zahlungsauftrag.

    Die Zahlung wird im Status 'draft' erstellt und muss
    vor dem Versand genehmigt werden.
    """
    try:
        return await payment_service.create_payment(
            db=db,
            user_id=current_user.id,
            bank_account_id=data.bank_account_id,
            data=data,
        )
    except ValueError as e:
        logger.warning(
            "payment_create_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zahlung konnte nicht erstellt werden. Bitte überprüfen Sie die Zahlungsdaten.",
        )


@payments_router.get(
    "",
    response_model=dict,
    summary="Zahlungen auflisten",
    description="Listet alle Zahlungsaufträge des Benutzers."
)
async def list_payments(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    status_filter: Optional[PaymentStatus] = Query(None, alias="status", description="Filter auf Status"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Liste Zahlungsaufträge."""
    payments, total = await payment_service.list_payments(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        status=status_filter,
        offset=(page - 1) * per_page,
        limit=per_page,
    )

    return {
        "payments": payments,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@payments_router.get(
    "/pending",
    response_model=List[PaymentOrderResponse],
    summary="Ausstehende Zahlungen",
    description="Listet alle ausstehenden Zahlungsaufträge."
)
async def get_pending_payments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PaymentOrderResponse]:
    """Hole alle ausstehenden Zahlungen."""
    return await payment_service.get_pending_payments(
        db=db,
        user_id=current_user.id,
    )


@payments_router.get(
    "/skonto-opportunities",
    response_model=List[dict],
    summary="Skonto-Möglichkeiten",
    description="Findet Rechnungen mit Skonto-Option innerhalb der nächsten Tage."
)
async def get_skonto_opportunities(
    days_ahead: int = Query(14, ge=1, le=60, description="Tage vorausschauen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Finde Skonto-Möglichkeiten.

    Zeigt Rechnungen bei denen Skonto noch genutzt werden kann.
    """
    return await payment_service.get_skonto_opportunities(
        db=db,
        user_id=current_user.id,
        days_ahead=days_ahead,
    )


@payments_router.get(
    "/{payment_id}",
    response_model=PaymentOrderResponse,
    summary="Zahlung abrufen",
    description="Ruft Details eines Zahlungsauftrags ab."
)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentOrderResponse:
    """Hole Zahlungsauftrag."""
    payment = await payment_service.get_payment(
        db=db,
        user_id=current_user.id,
        payment_id=payment_id,
    )

    if not payment:
        raise HTTPException(status_code=404, detail="Zahlung nicht gefunden")

    return payment


@limiter.limit("30/minute", key_func=get_user_identifier)
@payments_router.post(
    "/{payment_id}/approve",
    response_model=PaymentOrderResponse,
    summary="Zahlung genehmigen",
    description="Genehmigt einen Zahlungsauftrag für den Versand."
)
async def approve_payment(
    request: Request,  # SECURITY FIX 28-5: Required for rate limiter
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentOrderResponse:
    """
    Genehmige Zahlungsauftrag.

    Setzt den Status von 'draft' auf 'approved'.
    """
    try:
        return await payment_service.approve_payment(
            db=db,
            user_id=current_user.id,
            payment_id=payment_id,
        )
    except ValueError as e:
        logger.warning(
            "payment_approve_failed",
            payment_id=str(payment_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Genehmigung fehlgeschlagen. Zahlung kann in diesem Status nicht genehmigt werden.",
        )


@limiter.limit("30/minute", key_func=get_user_identifier)
@payments_router.post(
    "/{payment_id}/cancel",
    response_model=PaymentOrderResponse,
    summary="Zahlung stornieren",
    description="Storniert einen Zahlungsauftrag."
)
async def cancel_payment(
    request: Request,  # SECURITY FIX 28-5: Required for rate limiter
    payment_id: UUID,
    reason: Optional[str] = Query(None, description="Stornierungsgrund"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentOrderResponse:
    """Storniere Zahlungsauftrag."""
    try:
        return await payment_service.cancel_payment(
            db=db,
            user_id=current_user.id,
            payment_id=payment_id,
            reason=reason,
        )
    except ValueError as e:
        logger.warning(
            "payment_cancel_failed",
            payment_id=str(payment_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stornierung fehlgeschlagen. Zahlung kann in diesem Status nicht storniert werden.",
        )


# SECURITY FIX 28-5: Rate-Limit für kritische Zahlungsaktionen
@limiter.limit("10/minute", key_func=get_user_identifier)
@payments_router.post(
    "/{payment_id}/submit",
    response_model=dict,
    summary="Zahlung senden",
    description="Sendet Zahlung an Bank (initiiert TAN-Challenge)."
)
async def submit_payment(
    request: Request,  # SECURITY FIX 28-5: Required for rate limiter
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Sende Zahlung an Bank.

    Initiiert TAN-Challenge zur Bestätigung.
    """
    try:
        return await payment_service.submit_payment(
            db=db,
            user_id=current_user.id,
            payment_id=payment_id,
        )
    except ValueError as e:
        logger.warning(
            "payment_submit_failed",
            payment_id=str(payment_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zahlung konnte nicht gesendet werden. Bitte überprüfen Sie den Status.",
        )


# SECURITY FIX 28-5: Rate-Limit für TAN-Bestätigung (Brute-Force Prevention)
@limiter.limit("5/minute", key_func=get_user_identifier)
@payments_router.post(
    "/{payment_id}/confirm-tan",
    response_model=PaymentOrderResponse,
    summary="TAN bestätigen",
    description="Bestätigt Zahlung mit TAN."
)
async def confirm_payment_tan(
    request: Request,  # SECURITY FIX 28-5: Required for rate limiter
    payment_id: UUID,
    tan: str = Query(..., min_length=6, max_length=6, description="TAN-Eingabe"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentOrderResponse:
    """
    Bestätige Zahlung mit TAN.

    Nach erfolgreicher Bestätigung wird die Zahlung ausgeführt.
    """
    try:
        return await payment_service.confirm_with_tan(
            db=db,
            user_id=current_user.id,
            payment_id=payment_id,
            tan=tan,
        )
    except ValueError as e:
        # SECURITY: Keine Details zur TAN-Validierung preisgeben (Brute-Force Prevention)
        logger.warning(
            "payment_tan_confirm_failed",
            payment_id=str(payment_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TAN-Bestätigung fehlgeschlagen. Bitte versuchen Sie es erneut.",
        )


# ==================== TAN Endpoints ====================

@payments_router.get(
    "/tan/methods",
    response_model=List[dict],
    summary="TAN-Verfahren",
    description="Listet verfügbare TAN-Verfahren."
)
async def get_tan_methods(
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole verfügbare TAN-Verfahren."""
    return tan_handler_service.get_available_methods(current_user.id)


# ==================== Cash-Flow Endpoints ====================

@cashflow_router.get(
    "/forecast",
    response_model=dict,
    summary="Cash-Flow-Prognose",
    description="Erstellt Cash-Flow-Prognose für die nächsten Tage."
)
async def get_cash_flow_forecast(
    days_ahead: int = Query(90, ge=7, le=365, description="Tage voraus"),
    scenario: str = Query("realistic", description="Szenario (optimistic/realistic/pessimistic)"),
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Erstelle Cash-Flow-Prognose.

    Basiert auf offenen Forderungen, Verbindlichkeiten und geplanten Zahlungen.
    """
    try:
        scenario_enum = ForecastScenario(scenario)
    except ValueError:
        scenario_enum = ForecastScenario.REALISTIC

    projection = await cash_flow_service.get_cash_flow_forecast(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        days_ahead=days_ahead,
        scenario=scenario_enum,
    )

    return {
        "period": {
            "start": projection.start_date.isoformat(),
            "end": projection.end_date.isoformat(),
            "scenario": scenario,
        },
        "totals": {
            "inflow": float(projection.total_inflow),
            "outflow": float(projection.total_outflow),
            "net": float(projection.net_flow),
        },
        "risk": {
            "min_balance": float(projection.min_balance),
            "min_balance_date": projection.min_balance_date.isoformat() if projection.min_balance_date else None,
            "days_negative": projection.days_negative,
        },
        "entries_count": len(projection.entries),
    }


@cashflow_router.get(
    "/summary",
    response_model=dict,
    summary="Cash-Flow-Zusammenfassung",
    description="Kurz-, mittel- und langfristige Cash-Flow-Übersicht."
)
async def get_cash_flow_summary(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Hole Cash-Flow-Zusammenfassung mit Warnungen."""
    return await cash_flow_service.get_cash_flow_summary(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
    )


@cashflow_router.get(
    "/daily",
    response_model=List[dict],
    summary="Tägliche Prognose",
    description="Tägliche Cash-Flow-Werte für Diagramme."
)
async def get_daily_forecast(
    days: int = Query(30, ge=7, le=90, description="Anzahl Tage"),
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """Hole tägliche Cash-Flow-Werte."""
    return await cash_flow_service.get_daily_forecast(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        days=days,
    )


@cashflow_router.get(
    "/scenarios",
    response_model=dict,
    summary="Szenario-Vergleich",
    description="Vergleicht optimistisches, realistisches und pessimistisches Szenario."
)
async def compare_scenarios(
    days_ahead: int = Query(90, ge=30, le=365, description="Tage voraus"),
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Vergleiche verschiedene Szenarien."""
    return await cash_flow_service.compare_scenarios(
        db=db,
        company_id=company_id,
        bank_account_id=bank_account_id,
        days_ahead=days_ahead,
    )


# ==================== Dunning (Mahnwesen) Endpoints ====================

@dunning_router.get(
    "/overdue",
    response_model=List[dict],
    summary="Überfällige Rechnungen",
    description="Listet alle überfälligen Rechnungen mit Mahnempfehlungen."
)
async def get_overdue_invoices(
    min_days: int = Query(1, ge=1, description="Mind. Tage überfällig"),
    max_days: Optional[int] = Query(None, description="Max. Tage überfällig"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """Hole überfällige Rechnungen."""
    candidates = await dunning_service.get_overdue_invoices(
        db=db,
        company_id=company_id,
        min_days_overdue=min_days,
        max_days_overdue=max_days,
    )

    return [
        {
            "document_id": str(c.document_id),
            "invoice_number": c.invoice_number,
            "creditor_name": c.creditor_name,
            "amount": float(c.amount),
            "due_date": c.due_date.isoformat(),
            "days_overdue": c.days_overdue,
            "current_level": c.current_level.name.lower(),
            "recommended_action": c.recommended_action.value,
            "accumulated_fees": float(c.accumulated_fees),
            "late_interest": float(c.late_interest),
            "total_due": float(c.total_due),
        }
        for c in candidates
    ]


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.post(
    "",
    response_model=DunningRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mahnvorgang erstellen",
    description="Startet einen neuen Mahnvorgang für eine Rechnung."
)
async def create_dunning(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    document_id: UUID,
    level: DunningLevel = Query(DunningLevel.FIRST_REMINDER, description="Mahnstufe"),
    notes: Optional[str] = Query(None, description="Notizen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningRecordResponse:
    """Erstelle neuen Mahnvorgang."""
    try:
        return await dunning_service.create_dunning(
            db=db,
            company_id=company_id,
            document_id=document_id,
            level=level,
            notes=notes,
        )
    except ValueError as e:
        logger.warning(
            "dunning_create_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnvorgang konnte nicht erstellt werden. Bitte überprüfen Sie die Rechnung.",
        )


@dunning_router.get(
    "",
    response_model=dict,
    summary="Mahnvorgänge auflisten",
    description="Listet alle Mahnvorgänge mit optionaler Filterung."
)
async def list_dunnings(
    status_filter: Optional[str] = Query(None, alias="status", description="Status-Filter (active, pending, paid, etc.)"),
    level_filter: Optional[DunningLevel] = Query(None, alias="level"),
    dunning_level: Optional[int] = Query(None, ge=0, le=5, description="Mahnstufe (0-5)"),
    mahnstopp: Optional[bool] = Query(None, description="Nur Mahnstopp-Vorgänge"),
    is_b2b: Optional[bool] = Query(None, description="B2B oder B2C Filter"),
    business_entity_id: Optional[UUID] = Query(None, description="Geschäftspartner-ID"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Liste Mahnvorgänge."""
    # Verwende dunning_level falls level_filter nicht gesetzt
    effective_level = level_filter
    if effective_level is None and dunning_level is not None:
        # Konvertiere int zu DunningLevel Enum
        try:
            effective_level = DunningLevel(dunning_level)
        except ValueError:
            pass  # Ungültige Level werden ignoriert

    # Behandle "active" als Spezialfall für alle aktiven (nicht abgeschlossenen) Mahnungen
    effective_status: Optional[DunningStatus] = None
    active_only = False
    if status_filter:
        if status_filter.lower() == "active":
            # "active" bedeutet alle nicht-abgeschlossenen Mahnungen
            active_only = True
        else:
            # Versuche als DunningStatus Enum zu parsen
            try:
                effective_status = DunningStatus(status_filter)
            except ValueError:
                pass  # Unbekannte Status werden ignoriert

    dunnings, total = await dunning_service.list_dunnings(
        db=db,
        company_id=company_id,
        status=effective_status,
        level=effective_level,
        mahnstopp=mahnstopp,
        is_b2b=is_b2b,
        business_entity_id=business_entity_id,
        active_only=active_only,
        offset=(page - 1) * per_page,
        limit=per_page,
    )

    return {
        "items": dunnings,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@dunning_router.get(
    "/stats",
    response_model=dict,
    summary="Mahnstatistiken",
    description="Aggregierte Statistiken zum Mahnwesen."
)
async def get_dunning_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Hole Mahnstatistiken."""
    return await dunning_service.get_dunning_stats(
        db=db,
        company_id=company_id,
    )


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/{dunning_id}/escalate",
    response_model=DunningRecordResponse,
    summary="Mahnvorgang eskalieren",
    description="Eskaliert Mahnvorgang zur nächsten Stufe."
)
async def escalate_dunning(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    dunning_id: UUID,
    notes: Optional[str] = Query(None, description="Notizen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningRecordResponse:
    """Eskaliere Mahnvorgang."""
    try:
        return await dunning_service.escalate_dunning(
            db=db,
            company_id=company_id,
            dunning_id=dunning_id,
            notes=notes,
        )
    except ValueError as e:
        logger.warning(
            "dunning_escalate_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnvorgang konnte nicht eskaliert werden. Bitte überprüfen Sie den Status.",
        )


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/{dunning_id}/close",
    response_model=DunningRecordResponse,
    summary="Mahnvorgang schließen",
    description="Schließt einen Mahnvorgang ab (bezahlt, storniert, abgeschrieben)."
)
async def close_dunning(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    dunning_id: UUID,
    close_status: DunningStatus = Query(..., alias="status", description="Abschluss-Status"),
    notes: Optional[str] = Query(None, description="Notizen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningRecordResponse:
    """Schließe Mahnvorgang."""
    try:
        return await dunning_service.close_dunning(
            db=db,
            company_id=company_id,
            dunning_id=dunning_id,
            status=close_status,
            notes=notes,
        )
    except ValueError as e:
        logger.warning(
            "dunning_close_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            close_status=close_status.value if close_status else None,
            **safe_error_log(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnvorgang konnte nicht abgeschlossen werden. Bitte überprüfen Sie den Status.",
        )


# SECURITY FIX 28-7: Rate-Limit für Batch-Mahnverfahren
@limiter.limit("10/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/process-automatic",
    response_model=List[dict],
    summary="Automatisches Mahnverfahren",
    description="Führt automatisches Mahnverfahren durch (optional Dry-Run)."
)
async def process_automatic_dunning(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    dry_run: bool = Query(True, description="Nur simulieren, nicht ausführen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """Führe automatisches Mahnverfahren durch."""
    return await dunning_service.process_automatic_dunning(
        db=db,
        company_id=company_id,
        dry_run=dry_run,
    )


# ==================== Mahnungswesen Erweiterte Endpoints ====================

@dunning_router.get(
    "/{dunning_id}/history",
    response_model=MahnungHistoryListResponse,
    summary="Mahnung-Historie",
    description="Gibt die Historie eines Mahnvorgangs zurück (Audit-Log)."
)
async def get_dunning_history(
    dunning_id: UUID,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MahnungHistoryListResponse:
    """Hole Mahnung-Historie (immutables Audit-Log)."""
    items, total = await dunning_service.get_history(
        db=db,
        company_id=company_id,
        dunning_record_id=dunning_id,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return MahnungHistoryListResponse(items=items, total=total)


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/{dunning_id}/mahnstopp",
    response_model=DunningRecordResponse,
    summary="Mahnstopp setzen",
    description="Setzt einen Mahnstopp (z.B. bei Reklamation)."
)
async def set_mahnstopp(
    request: Request,  # Required for rate limiter
    dunning_id: UUID,
    body: MahnstoppSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningRecordResponse:
    """Setze Mahnstopp für einen Mahnvorgang."""
    try:
        return await dunning_service.set_mahnstopp(
            db=db,
            company_id=company_id,
            dunning_id=dunning_id,
            reason=body.reason,
            until_date=body.until_date,
        )
    except ValueError as e:
        logger.warning(
            "mahnstopp_set_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnstopp konnte nicht gesetzt werden.",
        )


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.delete(
    "/{dunning_id}/mahnstopp",
    response_model=DunningRecordResponse,
    summary="Mahnstopp aufheben",
    description="Hebt einen Mahnstopp auf."
)
async def lift_mahnstopp(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    dunning_id: UUID,
    notes: Optional[str] = Query(None, description="Notizen zur Aufhebung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningRecordResponse:
    """Hebe Mahnstopp auf."""
    try:
        return await dunning_service.lift_mahnstopp(
            db=db,
            company_id=company_id,
            dunning_id=dunning_id,
            notes=notes,
        )
    except ValueError as e:
        logger.warning(
            "mahnstopp_lift_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnstopp konnte nicht aufgehoben werden.",
        )


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/{dunning_id}/b2b-pauschale",
    response_model=B2BPauschaleClaimResponse,
    summary="B2B-Pauschale beanspruchen",
    description="Beansprucht die EUR 40 Pauschale nach §288 Abs. 5 BGB."
)
async def claim_b2b_pauschale(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    dunning_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> B2BPauschaleClaimResponse:
    """Beanspruche B2B-Pauschale (EUR 40 nach BGB)."""
    try:
        return await dunning_service.claim_b2b_pauschale(
            db=db,
            company_id=company_id,
            dunning_id=dunning_id,
        )
    except ValueError as e:
        logger.warning(
            "b2b_pauschale_claim_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="B2B-Pauschale konnte nicht beansprucht werden.",
        )


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("30/minute", key_func=get_user_identifier)
@dunning_router.put(
    "/{dunning_id}/b2b-status",
    response_model=DunningRecordResponse,
    summary="B2B-Status setzen",
    description="Setzt den B2B/B2C-Status für Verzugszinsenberechnung."
)
async def set_b2b_status(
    request: Request,  # SECURITY FIX 28-7: Required for rate limiter
    dunning_id: UUID,
    is_b2b: bool = Query(..., description="True = B2B (11.27%), False = B2C (7.27%)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningRecordResponse:
    """Setze B2B/B2C-Status."""
    try:
        return await dunning_service.set_b2b_status(
            db=db,
            company_id=company_id,
            dunning_id=dunning_id,
            is_b2b=is_b2b,
        )
    except ValueError as e:
        logger.warning(
            "b2b_status_set_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="B2B-Status konnte nicht gesetzt werden.",
        )


@dunning_router.get(
    "/{dunning_id}/verzugszinsen",
    response_model=VerzugszinsenCalculation,
    summary="Verzugszinsen berechnen",
    description="Berechnet aktuelle Verzugszinsen nach BGB §286."
)
async def calculate_verzugszinsen(
    dunning_id: UUID,
    as_of_date: Optional[date] = Query(None, description="Berechnungsdatum (Standard: heute)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> VerzugszinsenCalculation:
    """Berechne Verzugszinsen für Mahnvorgang."""
    from datetime import date as date_type
    calc_date = as_of_date or date_type.today()

    # Hole Dunning Record
    dunnings, _ = await dunning_service.list_dunnings(
        db=db,
        company_id=company_id,
        offset=0,
        limit=1,
    )

    # Filter für dunning_id (vereinfacht)
    dunning = None
    dunnings_list, _ = await dunning_service.list_dunnings(
        db=db, company_id=company_id, offset=0, limit=1000
    )
    for d in dunnings_list:
        if str(d.id) == str(dunning_id):
            dunning = d
            break

    if not dunning:
        raise HTTPException(status_code=404, detail="Mahnvorgang nicht gefunden")

    if not dunning.due_date or not dunning.outstanding_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fälligkeitsdatum oder Betrag fehlt."
        )

    interest_amount = dunning_service.calculate_verzugszinsen(
        principal=dunning.outstanding_amount,
        due_date=dunning.due_date,
        as_of_date=calc_date,
        is_b2b=dunning.is_b2b,
    )

    days_overdue = (calc_date - dunning.due_date).days if calc_date > dunning.due_date else 0

    return VerzugszinsenCalculation(
        principal=dunning.outstanding_amount,
        due_date=dunning.due_date,
        as_of_date=calc_date,
        is_b2b=dunning.is_b2b,
        interest_rate=dunning_service.get_verzugszinsen_rate(dunning.is_b2b),
        days_overdue=days_overdue,
        interest_amount=interest_amount,
        total_with_interest=dunning.outstanding_amount + interest_amount,
    )


# SECURITY FIX 28-7: Rate-Limit für Mahnwesen-Operationen
@limiter.limit("60/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/{dunning_id}/phone-call",
    response_model=PhoneCallLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Telefonkontakt protokollieren",
    description="Protokolliert einen Telefonkontakt zum Mahnvorgang."
)
async def log_phone_call(
    request: Request,  # Required for rate limiter
    dunning_id: UUID,
    body: PhoneCallLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PhoneCallLogResponse:
    """Protokolliere Telefonkontakt."""
    try:
        return await mahn_task_service.log_phone_call(
            db=db,
            company_id=company_id,
            dunning_record_id=dunning_id,
            contact_name=body.contact_name,
            phone_number=body.phone_number,
            outcome=body.outcome.value,
            notes=body.notes,
            follow_up_required=body.follow_up_required,
            follow_up_date=body.follow_up_date,
            follow_up_notes=body.follow_up_notes,
        )
    except ValueError as e:
        logger.warning(
            "phone_call_log_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telefonkontakt konnte nicht protokolliert werden.",
        )


@dunning_router.get(
    "/{dunning_id}/phone-calls",
    response_model=PhoneCallLogListResponse,
    summary="Telefonkontakte abrufen",
    description="Gibt Telefonkontakte zu einem Mahnvorgang zurück (paginiert)."
)
async def get_phone_calls(
    dunning_id: UUID,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PhoneCallLogListResponse:
    """Hole Telefonkontakte zu Mahnvorgang (paginiert)."""
    items, total = await mahn_task_service.get_phone_call_history(
        db=db,
        company_id=company_id,
        dunning_record_id=dunning_id,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return PhoneCallLogListResponse(items=items, total=total)


# SECURITY FIX 28-7: Rate-Limit für Bulk-Operationen
@limiter.limit("10/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/bulk-escalate",
    response_model=BulkEscalateResponse,
    summary="Masseneskalation",
    description="Eskaliert mehrere Mahnvorgänge gleichzeitig."
)
async def bulk_escalate_dunnings(
    request: Request,  # Required for rate limiter
    body: BulkEscalateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BulkEscalateResponse:
    """Eskaliere mehrere Mahnvorgänge."""
    return await dunning_service.bulk_escalate(
        db=db,
        company_id=company_id,
        dunning_ids=body.dunning_ids,
        notes=body.notes,
    )


@dunning_router.get(
    "/with-mahnstopp",
    response_model=List[DunningRecordResponse],
    summary="Mahnvorgänge mit Mahnstopp",
    description="Listet alle Mahnvorgänge mit aktivem Mahnstopp."
)
async def get_dunnings_with_mahnstopp(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[DunningRecordResponse]:
    """Hole Mahnvorgänge mit Mahnstopp."""
    return await dunning_service.get_dunnings_with_mahnstopp(
        db=db,
        company_id=company_id,
    )


# ==================== Mahnbrief PDF Endpoints ====================


@dunning_router.get(
    "/{dunning_id}/letter/preview",
    summary="Mahnbrief-Vorschau (HTML)",
    description="Generiert eine HTML-Vorschau des Mahnbriefs für die angegebene Mahnstufe."
)
async def preview_dunning_letter(
    dunning_id: UUID,
    dunning_level: int = Query(..., ge=1, le=4, description="Mahnstufe (1-4)"),
    is_b2b: bool = Query(True, description="B2B-Kunde (9% Verzugszins) oder B2C (5%)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Generiert eine HTML-Vorschau des Mahnbriefs.

    Nützlich für:
    - Vorab-Prüfung vor PDF-Generierung
    - Anzeige im Browser

    **Mahnstufen:**
    - 1: Freundliche Zahlungserinnerung (keine Gebühr)
    - 2: 1. Mahnung (5 EUR Gebühr)
    - 3: 2. Mahnung (10 EUR Gebühr)
    - 4: Letzte Mahnung (15 EUR Gebühr)
    """
    from app.services.banking.dunning_letter_service import dunning_letter_service

    try:
        html_content = await dunning_letter_service.generate_letter(
            db=db,
            dunning_record_id=dunning_id,
            dunning_level=dunning_level,
            is_b2b=is_b2b,
            output_format="html",
        )

        return Response(
            content=html_content,
            media_type="text/html; charset=utf-8",
        )

    except ValueError as e:
        logger.warning(
            "dunning_letter_preview_failed",
            dunning_id=str(dunning_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Mahnvorgang"),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Mahnbrief"),
        )


@dunning_router.get(
    "/{dunning_id}/letter/pdf",
    summary="Mahnbrief als PDF",
    description="Generiert den Mahnbrief als PDF-Download."
)
async def download_dunning_letter_pdf(
    dunning_id: UUID,
    dunning_level: int = Query(..., ge=1, le=4, description="Mahnstufe (1-4)"),
    is_b2b: bool = Query(True, description="B2B-Kunde (9% Verzugszins) oder B2C (5%)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Generiert einen Mahnbrief als PDF.

    Der PDF-Download enthält:
    - Professionelles Brieflayout nach DIN 5008
    - BGB-konforme Verzugszinsberechnung
    - Korrekte Mahngebühren je Stufe
    - B2B-Pauschale (40 EUR) ab Stufe 2

    **Dateiname:** `mahnung_{invoice_number}_stufe{level}.pdf`
    """
    from app.services.banking.dunning_letter_service import dunning_letter_service

    try:
        # Hole Daten für Dateinamen
        data = await dunning_letter_service.prepare_letter_data(
            db=db,
            dunning_record_id=dunning_id,
            dunning_level=dunning_level,
            is_b2b=is_b2b,
        )

        pdf_content = await dunning_letter_service.generate_letter(
            db=db,
            dunning_record_id=dunning_id,
            dunning_level=dunning_level,
            is_b2b=is_b2b,
            output_format="pdf",
        )

        # Sanitize invoice number für Dateinamen
        safe_invoice_number = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in (data.invoice_number or "unknown")
        )
        filename = f"mahnung_{safe_invoice_number}_stufe{dunning_level}.pdf"

        logger.info(
            "dunning_letter_pdf_downloaded",
            dunning_id=str(dunning_id),
            dunning_level=dunning_level,
            user_id=str(current_user.id),
        )

        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": build_content_disposition(filename, "attachment"),
            },
        )

    except ValueError as e:
        logger.warning(
            "dunning_letter_pdf_failed",
            dunning_id=str(dunning_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Mahnvorgang"),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Mahnbrief"),
        )


@limiter.limit("10/minute", key_func=get_user_identifier)
@dunning_router.post(
    "/letters/batch",
    summary="Mahnbriefe im Batch generieren",
    description="Generiert mehrere Mahnbriefe als ZIP-Archiv."
)
async def batch_generate_dunning_letters(
    request: Request,  # Required for rate limiter
    dunning_ids: List[UUID] = Query(..., description="Liste der Mahnvorgang-IDs"),
    dunning_level: int = Query(..., ge=1, le=4, description="Mahnstufe für alle"),
    is_b2b: bool = Query(True, description="B2B-Kunden"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Generiert mehrere Mahnbriefe als ZIP-Archiv.

    Nützlich für:
    - Massenversand per Post
    - Archivierung
    - Batch-Verarbeitung

    **Maximale Anzahl:** 50 Mahnbriefe pro Anfrage
    """
    import io
    import zipfile
    from app.services.banking.dunning_letter_service import dunning_letter_service

    if len(dunning_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximal 50 Mahnbriefe pro Batch erlaubt.",
        )

    if len(dunning_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens eine Mahnvorgang-ID erforderlich.",
        )

    # Sammle alle Dunning Records
    records = [{"id": did, "level": dunning_level, "is_b2b": is_b2b} for did in dunning_ids]

    results = await dunning_letter_service.generate_batch_letters(
        db=db,
        dunning_records=records,
        output_format="pdf",
    )

    # ZIP erstellen
    zip_buffer = io.BytesIO()
    success_count = 0
    error_count = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for result in results:
            if result["content"] and not result["error"]:
                # Versuche invoice_number zu holen
                try:
                    data = await dunning_letter_service.prepare_letter_data(
                        db=db,
                        dunning_record_id=result["id"],
                        dunning_level=dunning_level,
                        is_b2b=is_b2b,
                    )
                    safe_name = "".join(
                        c if c.isalnum() or c in "-_" else "_"
                        for c in (data.invoice_number or str(result["id"])[:8])
                    )
                except Exception:
                    safe_name = str(result["id"])[:8]

                filename = f"mahnung_{safe_name}_stufe{dunning_level}.pdf"
                zf.writestr(filename, result["content"])
                success_count += 1
            else:
                error_count += 1

        # Fehlerprotokoll hinzufügen
        if error_count > 0:
            error_log = "Fehlgeschlagene Mahnbriefe:\n\n"
            for result in results:
                if result["error"]:
                    error_log += f"- {result['id']}: {result['error']}\n"
            zf.writestr("_fehler.txt", error_log.encode("utf-8"))

    zip_content = zip_buffer.getvalue()
    zip_buffer.close()

    logger.info(
        "dunning_letters_batch_generated",
        total=len(dunning_ids),
        success=success_count,
        errors=error_count,
        user_id=str(current_user.id),
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"mahnbriefe_stufe{dunning_level}_{timestamp}.zip"

    return Response(
        content=zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": build_content_disposition(filename, "attachment"),
        },
    )


@dunning_router.get(
    "/letter-templates",
    summary="Verfügbare Mahnbrief-Vorlagen",
    description="Listet alle verfügbaren Mahnbrief-Vorlagen mit Konfiguration."
)
async def list_dunning_letter_templates(
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Listet alle verfügbaren Mahnbrief-Vorlagen.

    Gibt für jede Mahnstufe zurück:
    - Name und Titel
    - Standardgebühr
    - Zahlungsfrist
    - Eskalationswarnung
    """
    from app.services.banking.dunning_letter_service import dunning_letter_service

    templates = []
    for level, config in dunning_letter_service.DUNNING_LEVEL_CONFIG.items():
        templates.append({
            "level": level,
            "name": config["name"],
            "title": config["title"],
            "tone": config["tone"],
            "fee": float(config["fee"]),
            "payment_days": config["payment_days"],
            "escalation_warning": config["escalation_warning"],
            "template_file": config["template"],
        })

    return templates


@dunning_router.get(
    "/interest-rates",
    summary="Aktuelle Verzugszinssätze",
    description="Gibt die aktuellen Verzugszinssätze nach BGB §288 zurück."
)
async def get_current_interest_rates(
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Gibt aktuelle Verzugszinssätze zurück.

    Berechnung nach BGB §288:
    - B2B: Basiszins + 9 Prozentpunkte
    - B2C: Basiszins + 5 Prozentpunkte

    Nutzt den BundesbankRateService für aktuelle Basiszinssätze
    mit Caching (6 Monate TTL) und Fallback.
    """
    from app.services.bundesbank_rate_service import (
        get_current_basiszins,
        get_verzugszins,
    )

    # Async-Abruf des aktuellen Basiszinses von der Bundesbank
    basiszins_data = await get_current_basiszins()
    b2b_rate = await get_verzugszins(is_b2b=True)
    b2c_rate = await get_verzugszins(is_b2b=False)

    return {
        "base_rate": float(basiszins_data.rate),
        "valid_from": basiszins_data.valid_from,
        "valid_until": basiszins_data.valid_until,
        "source": basiszins_data.source.value,
        "b2b_rate": float(b2b_rate),
        "b2c_rate": float(b2c_rate),
        "legal_basis": "BGB §288",
        "b2b_pauschale": 40.0,
        "b2b_pauschale_legal_basis": "BGB §288 Abs. 5",
        "note": "Basiszinssatz der Deutschen Bundesbank (halbjährliche Anpassung)",
        "fetched_at": basiszins_data.fetched_at,
    }


@dunning_router.get(
    "/interest-rates/history",
    summary="Historische Basiszinssätze",
    description="Gibt die historischen Basiszinssätze der Bundesbank zurück."
)
async def get_interest_rate_history(
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Gibt historische Basiszinssätze zurück.

    Die Bundesbank passt den Basiszins halbjährlich an (01.01. und 01.07.).
    """
    from app.services.bundesbank_rate_service import get_bundesbank_rate_service

    service = get_bundesbank_rate_service()
    history = await service.get_basiszins_history()

    return {
        "rates": [
            {
                "rate": float(r.rate),
                "valid_from": r.valid_from,
                "valid_until": r.valid_until,
            }
            for r in history.rates
        ],
        "last_updated": history.last_updated,
        "count": len(history.rates),
    }


@dunning_router.get(
    "/interest-rates/calculate",
    summary="Verzugszins berechnen",
    description="Berechnet Verzugszinsen für einen bestimmten Zeitraum."
)
async def calculate_interest_for_period(
    amount: float = Query(..., gt=0, description="Rechnungsbetrag in EUR"),
    days_overdue: int = Query(..., ge=0, description="Anzahl Verzugstage"),
    is_b2b: bool = Query(True, description="B2B-Geschäft (True) oder B2C (False)"),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Berechnet Verzugszinsen für einen bestimmten Betrag und Zeitraum.

    Formel: Betrag × Verzugszins × Tage / 365
    """
    from decimal import Decimal
    from app.services.bundesbank_rate_service import get_verzugszins

    verzugszins = await get_verzugszins(is_b2b=is_b2b)
    daily_rate = verzugszins / Decimal("365")
    interest_amount = Decimal(str(amount)) * daily_rate * days_overdue / Decimal("100")

    return {
        "original_amount": amount,
        "days_overdue": days_overdue,
        "is_b2b": is_b2b,
        "verzugszins_rate": float(verzugszins),
        "interest_amount": float(interest_amount.quantize(Decimal("0.01"))),
        "total_amount": float(Decimal(str(amount)) + interest_amount.quantize(Decimal("0.01"))),
        "legal_basis": "BGB §288 Abs. 2" if is_b2b else "BGB §288 Abs. 1",
    }


# ==================== Mahn-Tasks Endpoints ====================

@mahn_tasks_router.get(
    "",
    response_model=dict,
    summary="Mahnaufgaben auflisten",
    description="Listet alle Mahnaufgaben mit optionaler Filterung."
)
async def list_mahn_tasks(
    task_type: Optional[MahnTaskType] = Query(None, description="Aufgabentyp"),
    task_status: Optional[MahnTaskStatus] = Query(None, alias="status", description="Status"),
    assigned_user_id: Optional[UUID] = Query(None, description="Zugewiesener Benutzer"),
    due_date_from: Optional[date] = Query(None, description="Fällig ab"),
    due_date_to: Optional[date] = Query(None, description="Fällig bis"),
    priority: Optional[int] = Query(None, ge=1, le=5, description="Priorität"),
    include_snoozed: bool = Query(False, description="Zurückgestellte einschließen"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Liste Mahnaufgaben."""
    filters = MahnTaskFilter(
        task_type=task_type,
        status=task_status,
        assigned_user_id=assigned_user_id,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        priority=priority,
        include_snoozed=include_snoozed,
    )

    tasks, total = await mahn_task_service.list_tasks(
        db=db,
        company_id=company_id,
        filters=filters,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": tasks,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@mahn_tasks_router.get(
    "/summary",
    response_model=MahnTaskSummary,
    summary="Aufgaben-Zusammenfassung",
    description="Gibt eine Zusammenfassung aller ausstehenden Aufgaben zurück."
)
async def get_mahn_task_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MahnTaskSummary:
    """Hole Aufgaben-Zusammenfassung."""
    # F-31: Service liefert ein Dict mit anderen Keys als das MahnTaskSummary-
    # Schema (due_today/overdue/snoozed/total_pending/by_type). Hier auf die
    # Schema-Felder mappen statt das Dict roh zurueckzugeben (Response-500).
    data = await mahn_task_service.get_pending_tasks_summary(
        db=db,
        company_id=company_id,
    )
    return MahnTaskSummary(
        pending_count=data.get("total_pending", 0),
        overdue_count=data.get("overdue", 0),
        due_today_count=data.get("due_today", 0),
        snoozed_count=data.get("snoozed", 0),
        by_type=data.get("by_type", {}) or {},
        by_priority=data.get("by_priority", {}) or {},
    )


# SECURITY FIX 28-8: Rate-Limit für Mahnaufgaben-Operationen
@limiter.limit("60/minute", key_func=get_user_identifier)
@mahn_tasks_router.post(
    "",
    response_model=MahnTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mahnaufgabe erstellen",
    description="Erstellt eine neue Mahnaufgabe."
)
async def create_mahn_task(
    request: Request,  # Required for rate limiter
    body: MahnTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MahnTaskResponse:
    """Erstelle neue Mahnaufgabe."""
    try:
        return await mahn_task_service.create_task(
            db=db,
            dunning_record_id=body.dunning_record_id,
            task_type=body.task_type.value,
            due_date=body.due_date,
            assigned_user_id=body.assigned_user_id,
            priority=body.priority,
        )
    except ValueError as e:
        logger.warning(
            "mahn_task_create_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnaufgabe konnte nicht erstellt werden.",
        )


# SECURITY FIX 28-8: Rate-Limit für Mahnaufgaben-Operationen
@limiter.limit("60/minute", key_func=get_user_identifier)
@mahn_tasks_router.post(
    "/{task_id}/assign",
    response_model=MahnTaskResponse,
    summary="Aufgabe zuweisen",
    description="Weist eine Aufgabe einem Benutzer zu."
)
async def assign_mahn_task(
    request: Request,  # SECURITY FIX 28-8: Required for rate limiter
    task_id: UUID,
    assigned_user_id: UUID = Query(..., description="Zuzuweisender Benutzer"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MahnTaskResponse:
    """Weise Mahnaufgabe zu."""
    try:
        return await mahn_task_service.assign_task(
            db=db,
            company_id=company_id,
            task_id=task_id,
            assigned_user_id=assigned_user_id,
        )
    except ValueError as e:
        logger.warning(
            "mahn_task_assign_failed",
            task_id=str(task_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aufgabe konnte nicht zugewiesen werden.",
        )


# SECURITY FIX 28-8: Rate-Limit für Mahnaufgaben-Operationen
@limiter.limit("60/minute", key_func=get_user_identifier)
@mahn_tasks_router.post(
    "/{task_id}/snooze",
    response_model=MahnTaskResponse,
    summary="Aufgabe zurückstellen",
    description="Stellt eine Aufgabe zurück (max. 3x)."
)
async def snooze_mahn_task(
    request: Request,  # Required for rate limiter
    task_id: UUID,
    body: MahnTaskSnoozeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MahnTaskResponse:
    """Stelle Mahnaufgabe zurück."""
    try:
        return await mahn_task_service.snooze_task(
            db=db,
            company_id=company_id,
            task_id=task_id,
            snooze_until=body.snooze_until,
            reason=body.reason,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning(
            "mahn_task_snooze_failed",
            task_id=str(task_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Snooze fehlgeschlagen. Bitte Eingaben prüfen.",
        )


# SECURITY FIX 28-8: Rate-Limit für Mahnaufgaben-Operationen
@limiter.limit("60/minute", key_func=get_user_identifier)
@mahn_tasks_router.post(
    "/{task_id}/complete",
    response_model=MahnTaskResponse,
    summary="Aufgabe abschließen",
    description="Schließt eine Aufgabe ab."
)
async def complete_mahn_task(
    request: Request,  # Required for rate limiter
    task_id: UUID,
    body: MahnTaskCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MahnTaskResponse:
    """Schließe Mahnaufgabe ab."""
    try:
        return await mahn_task_service.complete_task(
            db=db,
            company_id=company_id,
            task_id=task_id,
            notes=body.notes,
        )
    except ValueError as e:
        logger.warning(
            "mahn_task_complete_failed",
            task_id=str(task_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aufgabe konnte nicht abgeschlossen werden.",
        )


# SECURITY FIX 28-8: Rate-Limit für Bulk-Operationen
@limiter.limit("10/minute", key_func=get_user_identifier)
@mahn_tasks_router.post(
    "/bulk-complete",
    response_model=dict,
    summary="Massenabschluss",
    description="Schließt mehrere Aufgaben gleichzeitig ab."
)
async def bulk_complete_mahn_tasks(
    request: Request,  # Required for rate limiter
    body: MahnTaskBulkCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Schließe mehrere Mahnaufgaben ab."""
    completed = 0
    failed = 0
    errors = []

    for task_id in body.task_ids:
        try:
            await mahn_task_service.complete_task(
                db=db,
                company_id=company_id,
                task_id=task_id,
                notes=body.notes,
            )
            completed += 1
        except ValueError as e:
            failed += 1
            errors.append({"task_id": str(task_id), **safe_error_log(e)})

    return {
        "total": len(request.task_ids),
        "completed": completed,
        "failed": failed,
        "errors": errors,
    }


# ==================== Dunning Settings Endpoints (Admin) ====================

@dunning_settings_router.get(
    "/dunning-stages",
    response_model=DunningStagesListResponse,
    summary="Mahnstufen abrufen",
    description="Gibt alle konfigurierten Mahnstufen zurück."
)
async def get_dunning_stages(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningStagesListResponse:
    """Hole konfigurierte Mahnstufen."""
    try:
        # F-31: DunningStageConfig/Auto-Dunning sind USER-scoped (Model hat
        # user_id, KEINE company_id-Spalte; settings liegen in User.preferences).
        # Daher die User-ID statt der Company-ID an den Service uebergeben.
        stages = await dunning_stage_service.get_stages(
            db=db,
            company_id=current_user.id,
        )

        return DunningStagesListResponse(
            stages=stages or [],  # Handle None/empty list
            interest_rate_b2b=dunning_stage_service.get_interest_rate(is_b2b=True),
            interest_rate_b2c=dunning_stage_service.get_interest_rate(is_b2b=False),
            b2b_pauschale=dunning_stage_service.get_b2b_pauschale(),
        )
    except Exception as e:
        logger.error(
            "dunning_stages_get_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Mahnstufen.",
        )


@dunning_settings_router.post(
    "/dunning-stages",
    response_model=DunningStageConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mahnstufe erstellen",
    description="Erstellt eine neue Mahnstufe."
)
async def create_dunning_stage(
    request: DunningStageConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningStageConfigResponse:
    """Erstelle neue Mahnstufe."""
    try:
        return await dunning_stage_service.create_stage(
            db=db,
            company_id=company_id,
            stage_number=request.stage_number,
            stage_name=request.stage_name,
            trigger_days_after_due=request.trigger_days_after_due,
            action_type=request.action_type.value,
            template_id=request.template_id,
            fee_amount=request.fee_amount,
        )
    except ValueError as e:
        logger.warning(
            "dunning_stage_create_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnstufe konnte nicht erstellt werden.",
        )


@dunning_settings_router.put(
    "/dunning-stages/{stage_id}",
    response_model=DunningStageConfigResponse,
    summary="Mahnstufe aktualisieren",
    description="Aktualisiert eine bestehende Mahnstufe."
)
async def update_dunning_stage(
    stage_id: UUID,
    request: DunningStageConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DunningStageConfigResponse:
    """Aktualisiere Mahnstufe."""
    try:
        return await dunning_stage_service.update_stage(
            db=db,
            company_id=company_id,
            stage_id=stage_id,
            stage_name=request.stage_name,
            trigger_days_after_due=request.trigger_days_after_due,
            action_type=request.action_type.value if request.action_type else None,
            template_id=request.template_id,
            fee_amount=request.fee_amount,
            is_active=request.is_active,
        )
    except ValueError as e:
        logger.warning(
            "dunning_stage_update_failed",
            stage_id=str(stage_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnstufe konnte nicht aktualisiert werden.",
        )


@dunning_settings_router.put(
    "/dunning-stages/reorder",
    response_model=List[DunningStageConfigResponse],
    summary="Mahnstufen neu ordnen",
    description="Ordnet die Mahnstufen neu (Drag-and-Drop)."
)
async def reorder_dunning_stages(
    request: DunningStageReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[DunningStageConfigResponse]:
    """Ordne Mahnstufen neu."""
    try:
        return await dunning_stage_service.reorder_stages(
            db=db,
            company_id=company_id,
            stage_ids=request.stage_ids,
        )
    except ValueError as e:
        logger.warning(
            "dunning_stages_reorder_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnstufen konnten nicht neu geordnet werden.",
        )


# ==================== Auto-Mahnlauf Settings Endpoints ====================

@dunning_settings_router.get(
    "/auto-dunning",
    response_model=AutoDunningSettingsResponse,
    summary="Auto-Mahnlauf-Einstellungen abrufen",
    description="Gibt die Einstellungen für den automatischen Mahnlauf zurück."
)
async def get_auto_dunning_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> AutoDunningSettingsResponse:
    """Hole Auto-Mahnlauf-Einstellungen."""
    try:
        # F-31: USER-scoped (siehe get_dunning_stages) -> User-ID uebergeben.
        return await dunning_stage_service.get_auto_dunning_settings(
            db=db,
            company_id=current_user.id,
        )
    except Exception as e:
        logger.error(
            "auto_dunning_settings_get_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Auto-Mahnlauf-Einstellungen.",
        )


@dunning_settings_router.put(
    "/auto-dunning",
    response_model=AutoDunningSettingsResponse,
    summary="Auto-Mahnlauf-Einstellungen aktualisieren",
    description="Aktualisiert die Einstellungen für den automatischen Mahnlauf."
)
async def update_auto_dunning_settings(
    request: AutoDunningSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> AutoDunningSettingsResponse:
    """Aktualisiere Auto-Mahnlauf-Einstellungen."""
    try:
        return await dunning_stage_service.update_auto_dunning_settings(
            db=db,
            company_id=company_id,
            settings=request,
        )
    except ValueError as e:
        logger.warning(
            "auto_dunning_settings_update_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auto-Mahnlauf-Einstellungen konnten nicht aktualisiert werden.",
        )


# ==================== Customer Dunning Override Endpoints ====================

@customer_dunning_router.get(
    "/{business_entity_id}/dunning-settings",
    response_model=CustomerDunningOverrideResponse,
    summary="Kundenspezifische Mahneinstellungen",
    description="Gibt kundenspezifische Mahneinstellungen zurück."
)
async def get_customer_dunning_settings(
    business_entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CustomerDunningOverrideResponse:
    """Hole kundenspezifische Mahneinstellungen."""
    override = await dunning_stage_service.get_customer_override(
        db=db,
        business_entity_id=business_entity_id,
    )

    if not override:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine kundenspezifischen Einstellungen gefunden.",
        )

    return override


@customer_dunning_router.put(
    "/{business_entity_id}/dunning-settings",
    response_model=CustomerDunningOverrideResponse,
    summary="Kundenspezifische Mahneinstellungen setzen",
    description="Setzt oder aktualisiert kundenspezifische Mahneinstellungen."
)
async def set_customer_dunning_settings(
    business_entity_id: UUID,
    request: CustomerDunningOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CustomerDunningOverrideResponse:
    """Setze kundenspezifische Mahneinstellungen."""
    try:
        return await dunning_stage_service.set_customer_override(
            db=db,
            business_entity_id=business_entity_id,
            custom_payment_terms_days=request.custom_payment_terms_days,
            max_mahn_stufe=request.max_mahn_stufe,
            preferred_contact_method=request.preferred_contact_method.value if request.preferred_contact_method else None,
            exclude_from_auto_dunning=request.exclude_from_auto_dunning,
            exclusion_reason=request.exclusion_reason,
            notes=request.notes,
        )
    except ValueError as e:
        logger.warning(
            "customer_dunning_settings_failed",
            business_entity_id=str(business_entity_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahneinstellungen konnten nicht gesetzt werden.",
        )


# ==================== Aging Report Endpoints ====================

@aging_router.get(
    "/receivables",
    response_model=dict,
    summary="Forderungs-Altersanalyse",
    description="Alterungsanalyse der offenen Forderungen."
)
async def get_receivables_aging(
    as_of_date: Optional[date] = Query(None, description="Stichtag"),
    counterparty: Optional[str] = Query(None, description="Filter auf Debitor"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Hole Forderungs-Altersanalyse."""
    report = await aging_report_service.get_receivables_aging(
        db=db,
        user_id=current_user.id,
        as_of_date=as_of_date,
        include_details=True,
        counterparty=counterparty,
    )

    return {
        "report_type": report.report_type.value,
        "as_of_date": report.as_of_date.isoformat(),
        "generated_at": report.generated_at.isoformat(),
        "summary": {
            "total_count": report.total_count,
            "total_amount": float(report.total_amount),
            "total_overdue": float(report.total_overdue),
            "average_days_overdue": report.average_days_overdue,
        },
        "buckets": [
            {
                "bucket": b.bucket.value,
                "count": b.count,
                "amount": float(b.amount),
                "percentage": round(b.percentage, 1),
            }
            for b in report.buckets
        ],
        "line_items": [
            {
                "document_id": str(i.document_id),
                "invoice_number": i.invoice_number,
                "counterparty": i.counterparty,
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "amount": float(i.amount),
                "bucket": i.bucket.value,
                "days_overdue": i.days_overdue,
            }
            for i in report.line_items[:100]  # Limit details
        ],
    }


@aging_router.get(
    "/payables",
    response_model=dict,
    summary="Verbindlichkeiten-Altersanalyse",
    description="Alterungsanalyse der offenen Verbindlichkeiten."
)
async def get_payables_aging(
    as_of_date: Optional[date] = Query(None, description="Stichtag"),
    counterparty: Optional[str] = Query(None, description="Filter auf Kreditor"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Hole Verbindlichkeiten-Altersanalyse."""
    report = await aging_report_service.get_payables_aging(
        db=db,
        user_id=current_user.id,
        as_of_date=as_of_date,
        include_details=True,
        counterparty=counterparty,
    )

    return {
        "report_type": report.report_type.value,
        "as_of_date": report.as_of_date.isoformat(),
        "generated_at": report.generated_at.isoformat(),
        "summary": {
            "total_count": report.total_count,
            "total_amount": float(report.total_amount),
            "total_overdue": float(report.total_overdue),
            "average_days_overdue": report.average_days_overdue,
        },
        "buckets": [
            {
                "bucket": b.bucket.value,
                "count": b.count,
                "amount": float(b.amount),
                "percentage": round(b.percentage, 1),
            }
            for b in report.buckets
        ],
        "line_items": [
            {
                "document_id": str(i.document_id),
                "invoice_number": i.invoice_number,
                "counterparty": i.counterparty,
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "amount": float(i.amount),
                "bucket": i.bucket.value,
                "days_overdue": i.days_overdue,
            }
            for i in report.line_items[:100]
        ],
    }


@aging_router.get(
    "/summary",
    response_model=dict,
    summary="Altersanalyse-Zusammenfassung",
    description="Kombinierte Übersicht Forderungen und Verbindlichkeiten."
)
async def get_aging_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Hole kombinierte Altersanalyse."""
    return await aging_report_service.get_aging_summary(
        db=db,
        user_id=current_user.id,
    )


@aging_router.get(
    "/top-debtors",
    response_model=List[dict],
    summary="Top-Schuldner",
    description="Die größten Schuldner nach Forderungshöhe."
)
async def get_top_debtors(
    limit: int = Query(10, ge=1, le=50, description="Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole Top-Schuldner."""
    return await aging_report_service.get_top_debtors(
        db=db,
        user_id=current_user.id,
        limit=limit,
    )


@aging_router.get(
    "/top-creditors",
    response_model=List[dict],
    summary="Top-Gläubiger",
    description="Die größten Gläubiger nach Verbindlichkeitenhöhe."
)
async def get_top_creditors(
    limit: int = Query(10, ge=1, le=50, description="Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole Top-Gläubiger."""
    return await aging_report_service.get_top_creditors(
        db=db,
        user_id=current_user.id,
        limit=limit,
    )


@aging_router.get(
    "/dso",
    response_model=dict,
    summary="Days Sales Outstanding",
    description="Berechnet die durchschnittliche Forderungslaufzeit."
)
async def calculate_dso(
    period_days: int = Query(90, ge=30, le=365, description="Betrachtungszeitraum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Berechne Days Sales Outstanding."""
    return await aging_report_service.calculate_dso(
        db=db,
        user_id=current_user.id,
        period_days=period_days,
    )


# ==================== Payment Automation Endpoints (Phase 5.4) ====================

from pydantic import BaseModel, Field


class PaymentSuggestionResponse(BaseModel):
    """Einzelner Zahlungsvorschlag."""

    invoice_id: UUID
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: float
    due_date: Optional[date] = None
    skonto_available: bool = False
    skonto_amount: Optional[float] = None
    skonto_deadline: Optional[date] = None
    priority: str
    reasons: List[str]
    recommended_payment_date: date
    savings_potential: float = 0.0


class PaymentBatchResponse(BaseModel):
    """Zahlungs-Batch Response."""

    id: UUID
    name: str
    company_id: UUID
    status: str
    total_amount: float
    payment_count: int
    created_at: datetime
    created_by_id: UUID
    approved_at: Optional[datetime] = None
    approved_by_id: Optional[UUID] = None
    executed_at: Optional[datetime] = None
    debtor_account_id: Optional[UUID] = None
    sepa_file_path: Optional[str] = None
    payment_ids: List[UUID] = []


class PaymentScheduleEntryResponse(BaseModel):
    """Einzelner Eintrag im Zahlungsplan."""

    payment_date: date
    total_amount: float
    payment_count: int
    skonto_savings: float
    invoices: List[dict]


class PaymentScheduleResponse(BaseModel):
    """Gesamter Zahlungsplan."""

    period_days: int
    strategy: str
    total_payments: int
    total_amount: float
    total_skonto_savings: float
    daily_schedule: List[PaymentScheduleEntryResponse]


class AutomationStatisticsResponse(BaseModel):
    """Statistiken zur Zahlungsautomation."""

    period_days: int
    batches_created: int
    batches_approved: int
    batches_executed: int
    total_payments: int
    total_amount: float
    skonto_savings: float
    average_batch_size: float
    approval_rate: float


class CreateBatchRequest(BaseModel):
    """Request zum Erstellen eines Zahlungs-Batches."""

    name: str = Field(..., min_length=1, max_length=200)
    invoice_ids: List[UUID] = Field(..., min_length=1)
    debtor_account_id: Optional[UUID] = None


class CreateOptimizedBatchRequest(BaseModel):
    """Request zum Erstellen eines optimierten Batches."""

    strategy: PaymentStrategy = PaymentStrategy.SKONTO_OPTIMIZED
    max_amount: Optional[float] = None
    debtor_account_id: Optional[UUID] = None


class GenerateSepaRequest(BaseModel):
    """Request zur SEPA-Dateigenerierung."""

    execution_date: Optional[date] = None


@payment_automation_router.get(
    "/suggestions",
    response_model=List[PaymentSuggestionResponse],
    summary="Zahlungsvorschläge generieren",
    description="Generiert intelligente Zahlungsvorschläge basierend auf offenen Rechnungen, "
                "Skonto-Fristen und Cashflow-Optimierung."
)
async def get_payment_suggestions(
    strategy: PaymentStrategy = Query(
        PaymentStrategy.SKONTO_OPTIMIZED,
        description="Optimierungsstrategie"
    ),
    lookahead_days: int = Query(14, ge=1, le=90, description="Vorausschau in Tagen"),
    include_overdue: bool = Query(True, description="Überfällige einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[PaymentSuggestionResponse]:
    """Generiere Zahlungsvorschläge.

    Analysiert offene Rechnungen und erstellt priorisierte Vorschläge
    basierend auf der gewählten Strategie.
    """
    suggestions = await payment_automation_service.generate_payment_suggestions(
        db=db,
        company_id=company_id,
        strategy=strategy,
        lookahead_days=lookahead_days,
        include_overdue=include_overdue,
    )

    return [
        PaymentSuggestionResponse(
            invoice_id=s.invoice_id,
            entity_id=s.entity_id,
            entity_name=s.entity_name,
            invoice_number=s.invoice_number,
            amount=float(s.payment_amount),
            due_date=s.due_date.date() if s.due_date else None,
            skonto_available=s.is_skonto_available,
            skonto_amount=float(s.skonto_amount) if s.skonto_amount else None,
            skonto_deadline=s.skonto_deadline.date() if s.skonto_deadline else None,
            priority=s.priority.value,
            reasons=[s.reason.value],
            recommended_payment_date=s.suggested_payment_date or date.today(),
            savings_potential=float(s.skonto_savings),
        )
        for s in suggestions
    ]


@payment_automation_router.get(
    "/batches",
    response_model=List[PaymentBatchResponse],
    summary="Zahlungs-Batches auflisten",
    description="Listet alle Zahlungs-Batches mit Filtermöglichkeiten auf."
)
async def list_payment_batches(
    status: Optional[PaymentBatchStatus] = Query(None, description="Nach Status filtern"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[PaymentBatchResponse]:
    """Liste alle Zahlungs-Batches."""
    batches = await payment_automation_service.list_batches(
        db=db,
        company_id=company_id,
        status=status,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return [
        PaymentBatchResponse(
            id=b.id,
            name=b.name,
            company_id=b.company_id,
            status=b.status.value,
            total_amount=float(b.total_amount),
            payment_count=b.payment_count,
            created_at=b.created_at,
            created_by_id=b.created_by_id,
            approved_at=b.approved_at,
            approved_by_id=b.approved_by_id,
            executed_at=b.executed_at,
            debtor_account_id=b.debtor_account_id,
            sepa_file_path=b.sepa_file_path,
            payment_ids=b.payment_ids,
        )
        for b in batches
    ]


@payment_automation_router.post(
    "/batches",
    response_model=PaymentBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Zahlungs-Batch erstellen",
    description="Erstellt einen neuen Zahlungs-Batch aus ausgewählten Rechnungen."
)
async def create_payment_batch(
    request: CreateBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PaymentBatchResponse:
    """Erstelle einen neuen Zahlungs-Batch."""
    # Hole Suggestions für die angegebenen Rechnungen
    suggestions = await payment_automation_service.get_suggestions_for_invoices(
        db=db,
        company_id=company_id,
        invoice_ids=request.invoice_ids,
    )

    if not suggestions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine gültigen Rechnungen für Batch gefunden.",
        )

    batch = await payment_automation_service.create_payment_batch(
        db=db,
        company_id=company_id,
        suggestions=suggestions,
        name=request.name,
        debtor_account_id=request.debtor_account_id,
        created_by_id=current_user.id,
    )

    return PaymentBatchResponse(
        id=batch.id,
        name=batch.name,
        company_id=batch.company_id,
        status=batch.status.value,
        total_amount=float(batch.total_amount),
        payment_count=batch.payment_count,
        created_at=batch.created_at,
        created_by_id=batch.created_by_id,
        approved_at=batch.approved_at,
        approved_by_id=batch.approved_by_id,
        executed_at=batch.executed_at,
        debtor_account_id=batch.debtor_account_id,
        sepa_file_path=batch.sepa_file_path,
        payment_ids=batch.payment_ids,
    )


@payment_automation_router.post(
    "/batches/optimized",
    response_model=PaymentBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Optimierten Batch erstellen",
    description="Erstellt automatisch einen optimierten Zahlungs-Batch basierend auf der Strategie."
)
async def create_optimized_batch(
    request: CreateOptimizedBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PaymentBatchResponse:
    """Erstelle einen optimierten Zahlungs-Batch."""
    max_amount = Decimal(str(request.max_amount)) if request.max_amount else None

    batch = await payment_automation_service.create_optimized_batch(
        db=db,
        company_id=company_id,
        strategy=request.strategy,
        max_amount=max_amount,
        debtor_account_id=request.debtor_account_id,
        created_by_id=current_user.id,
    )

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Zahlungen für optimierten Batch gefunden.",
        )

    return PaymentBatchResponse(
        id=batch.id,
        name=batch.name,
        company_id=batch.company_id,
        status=batch.status.value,
        total_amount=float(batch.total_amount),
        payment_count=batch.payment_count,
        created_at=batch.created_at,
        created_by_id=batch.created_by_id,
        approved_at=batch.approved_at,
        approved_by_id=batch.approved_by_id,
        executed_at=batch.executed_at,
        debtor_account_id=batch.debtor_account_id,
        sepa_file_path=batch.sepa_file_path,
        payment_ids=batch.payment_ids,
    )


@payment_automation_router.get(
    "/batches/{batch_id}",
    response_model=PaymentBatchResponse,
    summary="Batch-Details abrufen",
    description="Ruft die Details eines spezifischen Zahlungs-Batches ab."
)
async def get_payment_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PaymentBatchResponse:
    """Hole Details eines Zahlungs-Batches."""
    batch = await payment_automation_service.get_batch(
        db=db,
        batch_id=batch_id,
        company_id=company_id,
    )

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zahlungs-Batch nicht gefunden.",
        )

    return PaymentBatchResponse(
        id=batch.id,
        name=batch.name,
        company_id=batch.company_id,
        status=batch.status.value,
        total_amount=float(batch.total_amount),
        payment_count=batch.payment_count,
        created_at=batch.created_at,
        created_by_id=batch.created_by_id,
        approved_at=batch.approved_at,
        approved_by_id=batch.approved_by_id,
        executed_at=batch.executed_at,
        debtor_account_id=batch.debtor_account_id,
        sepa_file_path=batch.sepa_file_path,
        payment_ids=batch.payment_ids,
    )


@payment_automation_router.post(
    "/batches/{batch_id}/approve",
    response_model=PaymentBatchResponse,
    summary="Batch genehmigen",
    description="Genehmigt einen Zahlungs-Batch für die Ausführung."
)
async def approve_payment_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PaymentBatchResponse:
    """Genehmige einen Zahlungs-Batch."""
    batch = await payment_automation_service.get_batch(
        db=db,
        batch_id=batch_id,
        company_id=company_id,
    )

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zahlungs-Batch nicht gefunden.",
        )

    if batch.status != PaymentBatchStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch kann nicht genehmigt werden. Status: {batch.status.value}",
        )

    approved_batch = await payment_automation_service.approve_batch(
        db=db,
        batch=batch,
        approver_id=current_user.id,
    )

    return PaymentBatchResponse(
        id=approved_batch.id,
        name=approved_batch.name,
        company_id=approved_batch.company_id,
        status=approved_batch.status.value,
        total_amount=float(approved_batch.total_amount),
        payment_count=approved_batch.payment_count,
        created_at=approved_batch.created_at,
        created_by_id=approved_batch.created_by_id,
        approved_at=approved_batch.approved_at,
        approved_by_id=approved_batch.approved_by_id,
        executed_at=approved_batch.executed_at,
        debtor_account_id=approved_batch.debtor_account_id,
        sepa_file_path=approved_batch.sepa_file_path,
        payment_ids=approved_batch.payment_ids,
    )


@payment_automation_router.post(
    "/batches/{batch_id}/reject",
    response_model=PaymentBatchResponse,
    summary="Batch ablehnen",
    description="Lehnt einen Zahlungs-Batch ab."
)
async def reject_payment_batch(
    batch_id: UUID,
    reason: str = Query(..., min_length=1, max_length=500, description="Ablehnungsgrund"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PaymentBatchResponse:
    """Lehne einen Zahlungs-Batch ab."""
    batch = await payment_automation_service.get_batch(
        db=db,
        batch_id=batch_id,
        company_id=company_id,
    )

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zahlungs-Batch nicht gefunden.",
        )

    if batch.status != PaymentBatchStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch kann nicht abgelehnt werden. Status: {batch.status.value}",
        )

    rejected_batch = await payment_automation_service.reject_batch(
        db=db,
        batch=batch,
        rejector_id=current_user.id,
        reason=reason,
    )

    return PaymentBatchResponse(
        id=rejected_batch.id,
        name=rejected_batch.name,
        company_id=rejected_batch.company_id,
        status=rejected_batch.status.value,
        total_amount=float(rejected_batch.total_amount),
        payment_count=rejected_batch.payment_count,
        created_at=rejected_batch.created_at,
        created_by_id=rejected_batch.created_by_id,
        approved_at=rejected_batch.approved_at,
        approved_by_id=rejected_batch.approved_by_id,
        executed_at=rejected_batch.executed_at,
        debtor_account_id=rejected_batch.debtor_account_id,
        sepa_file_path=rejected_batch.sepa_file_path,
        payment_ids=rejected_batch.payment_ids,
    )


@payment_automation_router.post(
    "/batches/{batch_id}/sepa",
    response_model=dict,
    summary="SEPA-Datei generieren",
    description="Generiert eine SEPA pain.001 Datei für den genehmigten Batch."
)
async def generate_sepa_file(
    batch_id: UUID,
    request: GenerateSepaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Generiere SEPA-Datei für einen Batch."""
    batch = await payment_automation_service.get_batch(
        db=db,
        batch_id=batch_id,
        company_id=company_id,
    )

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zahlungs-Batch nicht gefunden.",
        )

    if batch.status != PaymentBatchStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SEPA-Datei kann nur für genehmigte Batches erstellt werden.",
        )

    sepa_content, file_name = await payment_automation_service.generate_sepa_file(
        db=db,
        batch=batch,
        execution_date=request.execution_date,
    )

    # Batch als ausgeführt markieren
    batch.status = PaymentBatchStatus.EXECUTED
    batch.executed_at = datetime.utcnow()
    batch.sepa_file_path = file_name
    await db.commit()

    return {
        "file_name": file_name,
        "content": sepa_content,
        "payment_count": batch.payment_count,
        "total_amount": float(batch.total_amount),
        "execution_date": (request.execution_date or date.today()).isoformat(),
    }


@payment_automation_router.get(
    "/schedule",
    response_model=PaymentScheduleResponse,
    summary="Zahlungsplan erstellen",
    description="Erstellt einen optimierten Zahlungsplan für die nächsten Tage."
)
async def get_payment_schedule(
    period_days: int = Query(30, ge=7, le=90, description="Planungszeitraum in Tagen"),
    strategy: PaymentStrategy = Query(
        PaymentStrategy.SKONTO_OPTIMIZED,
        description="Optimierungsstrategie"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PaymentScheduleResponse:
    """Erstelle einen Zahlungsplan."""
    schedule = await payment_automation_service.create_payment_schedule(
        db=db,
        company_id=company_id,
        period_days=period_days,
        strategy=strategy,
    )

    # F-31: create_payment_schedule() liefert die PaymentSchedule-Dataclass mit
    # Feldern entries/total_amount/total_skonto_savings (KEIN period_days/strategy/
    # total_payments/daily_schedule). Response aus den realen Feldern aufbauen;
    # period_days/strategy stammen aus den Request-Parametern.
    daily_schedule = [
        PaymentScheduleEntryResponse(
            payment_date=entry["date"],
            total_amount=float(entry.get("total_amount", 0)),
            payment_count=entry.get("payment_count", 0),
            skonto_savings=float(entry.get("skonto_savings", 0)),
            invoices=entry.get("payments", []),
        )
        for entry in schedule.entries
    ]
    return PaymentScheduleResponse(
        period_days=period_days,
        strategy=strategy.value,
        total_payments=sum(e.payment_count for e in daily_schedule),
        total_amount=float(schedule.total_amount),
        total_skonto_savings=float(schedule.total_skonto_savings),
        daily_schedule=daily_schedule,
    )


@payment_automation_router.get(
    "/statistics",
    response_model=AutomationStatisticsResponse,
    summary="Statistiken abrufen",
    description="Ruft Statistiken zur Zahlungsautomation ab."
)
async def get_automation_statistics(
    days: int = Query(30, ge=7, le=365, description="Betrachtungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> AutomationStatisticsResponse:
    """Hole Statistiken zur Zahlungsautomation."""
    stats = await payment_automation_service.get_automation_statistics(
        db=db,
        company_id=company_id,
        days=days,
    )

    # F-31: get_automation_statistics() liefert ein Dict mit invoices_paid/
    # total_paid/skonto_savings/... (KEINE batch-Kennzahlen). Auf die realen
    # Keys mappen; nicht vorhandene Batch-Felder defaulten auf 0 statt KeyError.
    return AutomationStatisticsResponse(
        period_days=stats.get("period_days", days),
        batches_created=stats.get("batches_created", 0),
        batches_approved=stats.get("batches_approved", 0),
        batches_executed=stats.get("batches_executed", 0),
        total_payments=stats.get("invoices_paid", 0),
        total_amount=float(stats.get("total_paid", 0)),
        skonto_savings=float(stats.get("skonto_savings", 0)),
        average_batch_size=float(stats.get("average_batch_size", 0)),
        approval_rate=float(stats.get("approval_rate", 0)),
    )


@payment_automation_router.get(
    "/config",
    response_model=dict,
    summary="Konfiguration abrufen",
    description="Ruft die aktuelle Automationskonfiguration ab."
)
async def get_automation_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Hole Automationskonfiguration."""
    config = await payment_automation_service.get_config(
        db=db,
        company_id=company_id,
    )

    return {
        "auto_generate_on_approval": config.auto_generate_on_approval,
        "auto_approve_threshold": float(config.auto_approve_threshold),
        "prioritize_skonto": config.prioritize_skonto,
        "skonto_alert_days": config.skonto_alert_days,
        "preferred_payment_days": config.preferred_payment_days,
        "max_batch_size": config.max_batch_size,
        "daily_limit": float(config.daily_limit),
    }


@payment_automation_router.patch(
    "/config",
    response_model=dict,
    summary="Konfiguration aktualisieren",
    description="Aktualisiert die Automationskonfiguration."
)
async def update_automation_config(
    auto_generate_on_approval: Optional[bool] = None,
    auto_approve_threshold: Optional[float] = None,
    prioritize_skonto: Optional[bool] = None,
    skonto_alert_days: Optional[int] = Query(None, ge=1, le=30),
    preferred_payment_days: Optional[List[int]] = None,
    max_batch_size: Optional[int] = Query(None, ge=1, le=200),
    daily_limit: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """Aktualisiere Automationskonfiguration."""
    updates = {}

    if auto_generate_on_approval is not None:
        updates["auto_generate_on_approval"] = auto_generate_on_approval
    if auto_approve_threshold is not None:
        updates["auto_approve_threshold"] = Decimal(str(auto_approve_threshold))
    if prioritize_skonto is not None:
        updates["prioritize_skonto"] = prioritize_skonto
    if skonto_alert_days is not None:
        updates["skonto_alert_days"] = skonto_alert_days
    if preferred_payment_days is not None:
        # Validiere Tage (1-31)
        if not all(1 <= d <= 31 for d in preferred_payment_days):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bevorzugte Zahlungstage müssen zwischen 1 und 31 liegen.",
            )
        updates["preferred_payment_days"] = preferred_payment_days
    if max_batch_size is not None:
        updates["max_batch_size"] = max_batch_size
    if daily_limit is not None:
        updates["daily_limit"] = Decimal(str(daily_limit))

    config = await payment_automation_service.update_config(
        db=db,
        company_id=company_id,
        **updates,
    )

    return {
        "auto_generate_on_approval": config.auto_generate_on_approval,
        "auto_approve_threshold": float(config.auto_approve_threshold),
        "prioritize_skonto": config.prioritize_skonto,
        "skonto_alert_days": config.skonto_alert_days,
        "preferred_payment_days": config.preferred_payment_days,
        "max_batch_size": config.max_batch_size,
        "daily_limit": float(config.daily_limit),
    }


@payment_automation_router.get(
    "/skonto-alerts",
    response_model=List[dict],
    summary="Skonto-Warnungen",
    description="Listet Rechnungen mit bald ablaufenden Skonto-Fristen auf."
)
async def get_skonto_alerts(
    days: int = Query(3, ge=1, le=14, description="Vorwarnzeit in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[dict]:
    """Hole Rechnungen mit ablaufenden Skonto-Fristen.

    Gibt Alerts mit folgenden Feldern zurück:
    - invoice_id: Rechnungs-ID
    - invoice_number: Rechnungsnummer
    - entity_id: Entity-ID (optional)
    - amount: Rechnungsbetrag
    - skonto_percentage: Skonto-Prozentsatz
    - skonto_deadline: Skonto-Frist
    - days_remaining: Verbleibende Tage
    - potential_savings: Mögliche Ersparnis
    - urgency: Dringlichkeit (critical/warning/info)
    - message: Meldung
    """
    return await payment_automation_service.get_skonto_alerts(
        db=db,
        company_id=company_id,
        days=days,
    )


# ==================== Combined Router ====================

router = APIRouter()
router.include_router(accounts_router)
router.include_router(imports_router)
router.include_router(transactions_router)
router.include_router(reconciliation_router)
router.include_router(payments_router)
router.include_router(cashflow_router)
router.include_router(dunning_router)
router.include_router(aging_router)
# Neue Mahnungswesen Routers
router.include_router(mahn_tasks_router)
router.include_router(dunning_settings_router)
router.include_router(customer_dunning_router)
# Phase 5.4: Payment Automation Router
router.include_router(payment_automation_router)
