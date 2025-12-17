"""
Banking API Endpoints.

Verwaltet Bankkonten und Kontoauszug-Importe:
- Bank-Konto CRUD (manuell, ohne FinTS)
- Datei-Import (MT940, CAMT.053, CSV)
- Import-Historie

Alle Antworten auf Deutsch.
"""

from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
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


# ==================== SECURITY: File Upload Validation ====================

# Maximale Dateigroesse: 10 MB
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024

# Erlaubte Dateiendungen fuer Bank-Imports
ALLOWED_EXTENSIONS = {".mt940", ".sta", ".xml", ".csv", ".txt", ".940", ".pdf"}

# Erlaubte Content-Types
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/csv",
    "text/xml",
    "application/xml",
    "application/pdf",
    "application/octet-stream",  # Fuer generische Uploads
}

# Magic-Bytes fuer Dateiformat-Erkennung
MAGIC_BYTES = {
    "xml": [b"<?xml", b"<Document", b"<BkToCstmrStmt"],  # CAMT.053, ZUGFeRD
    "pdf": [b"%PDF-"],
    "mt940": [b":20:", b":25:", b"\n:20:"],  # MT940 Start
}


async def validate_upload_file(
    file: UploadFile,
    max_size: int = MAX_UPLOAD_SIZE_BYTES,
) -> bytes:
    """Validiere hochgeladene Datei fuer Sicherheit.

    SECURITY: Prueft Dateigroesse, Endung, Content-Type und Magic-Bytes.

    Args:
        file: Hochgeladene Datei
        max_size: Maximale Dateigroesse in Bytes

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

    # Endung pruefen
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

    # 2. Content-Type pruefen (wenn vorhanden)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(
            "upload_rejected_content_type",
            filename=file.filename,
            content_type=file.content_type,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nicht unterstuetzter Dateityp.",
        )

    # 3. Dateigroesse pruefen (lese in Chunks)
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
                detail=f"Datei zu gross. Maximum: {max_size / 1024 / 1024:.0f} MB",
            )

    # 4. Magic-Bytes pruefen (grundlegende Validierung)
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
                    detail="Datei ist keine gueltige PDF.",
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
                    detail="Datei ist kein gueltiges XML.",
                )

    logger.info(
        "upload_validated",
        filename=file.filename,
        size_bytes=len(content),
        extension=ext,
    )

    return content


# ==================== Account Endpoints ====================

@accounts_router.post(
    "",
    response_model=BankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bankkonto registrieren",
    description="Erstellt ein neues Bankkonto fuer manuellen Import."
)
async def create_account(
    data: BankAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BankAccountResponse:
    """
    Registriere ein neues Bankkonto.

    Das Konto wird fuer manuellen Datei-Import verwendet.
    Die IBAN wird automatisch validiert (MOD-97 Pruefung).

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
            user_id=current_user.id,
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Konto konnte nicht erstellt werden. Bitte ueberpruefen Sie die IBAN und Kontodaten.",
        )


@accounts_router.get(
    "",
    response_model=List[BankAccountResponse],
    summary="Bankkonten auflisten",
    description="Gibt alle Bankkonten des aktuellen Benutzers zurueck."
)
async def list_accounts(
    include_inactive: bool = Query(False, description="Inaktive Konten einschliessen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[BankAccountResponse]:
    """Hole alle Bankkonten des Benutzers."""
    accounts = await account_service.get_accounts(
        db=db,
        user_id=current_user.id,
        include_inactive=include_inactive,
    )
    return accounts


@accounts_router.get(
    "/with-stats",
    response_model=List[BankAccountWithStats],
    summary="Bankkonten mit Statistiken",
    description="Gibt Bankkonten mit Transaktions- und Abgleich-Statistiken zurueck."
)
async def list_accounts_with_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[BankAccountWithStats]:
    """Hole Bankkonten mit erweiterten Statistiken."""
    return await account_service.get_accounts_with_stats(
        db=db,
        user_id=current_user.id,
    )


@accounts_router.get(
    "/{account_id}",
    response_model=BankAccountResponse,
    summary="Bankkonto abrufen",
    description="Gibt ein einzelnes Bankkonto zurueck."
)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BankAccountResponse:
    """Hole ein einzelnes Bankkonto."""
    account = await account_service.get_account(
        db=db,
        user_id=current_user.id,
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
) -> BankAccountResponse:
    """Aktualisiere ein Bankkonto."""
    account = await account_service.update_account(
        db=db,
        user_id=current_user.id,
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
    summary="Bankkonto loeschen",
    description="Loescht ein Bankkonto (Soft-Delete)."
)
async def delete_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Loesche ein Bankkonto.

    Das Konto wird nicht physisch geloescht, sondern nur als
    geloescht markiert (Soft-Delete). Transaktionen bleiben erhalten.
    """
    deleted = await account_service.delete_account(
        db=db,
        user_id=current_user.id,
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


# ==================== Import Endpoints ====================

@imports_router.get(
    "/formats",
    response_model=SupportedFormatsResponse,
    summary="Unterstuetzte Formate",
    description="Gibt alle unterstuetzten Import-Formate zurueck."
)
async def get_supported_formats() -> SupportedFormatsResponse:
    """
    Hole Liste aller unterstuetzten Import-Formate.

    Unterstuetzt werden:
    - MT940 (SWIFT) - Universelles Bankformat
    - CAMT.053 (ISO 20022) - Modernes XML-Format
    - Bank-spezifische CSV-Formate (Sparkasse, VR, DKB, etc.)
    """
    return await import_service.get_supported_formats()


@imports_router.post(
    "/preview",
    response_model=BankImportPreview,
    summary="Import-Vorschau",
    description="Erstellt eine Vorschau vor dem eigentlichen Import."
)
async def preview_import(
    file: UploadFile = File(..., description="Kontoauszug-Datei"),
    format_hint: Optional[ImportFormat] = Form(
        None,
        description="Optionales Format (sonst Auto-Erkennung)"
    ),
    current_user: User = Depends(get_current_active_user),
) -> BankImportPreview:
    """
    Erstelle Vorschau eines Kontoauszugs.

    Analysiert die Datei und gibt zurueck:
    - Erkanntes Format und Konfidenz
    - Anzahl Transaktionen
    - Zeitraum (von/bis)
    - Summe Eingaenge/Ausgaenge
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
            error=str(e),
            exc_info=True,
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datei konnte nicht analysiert werden. Bitte ueberpruefen Sie das Dateiformat.",
        )


@imports_router.post(
    "",
    response_model=BankImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kontoauszug importieren",
    description="Importiert einen Kontoauszug und erstellt Transaktionen."
)
async def import_file(
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
) -> BankImportResponse:
    """
    Importiere Kontoauszug in das System.

    Unterstuetzte Formate:
    - MT940 (SWIFT) - Universal von allen Banken
    - CAMT.053 (ISO 20022) - Modernes XML-Format
    - Bank-spezifische CSV (Sparkasse, VR, DKB, N26, etc.)

    Duplikate werden automatisch erkannt und uebersprungen.
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
            user_id=current_user.id,
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import fehlgeschlagen. Bitte ueberpruefen Sie das Dateiformat und die Daten.",
        )
    except Exception as e:
        logger.error(
            "banking_import_error",
            user_id=str(current_user.id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Import fehlgeschlagen. Bitte ueberpruefen Sie das Dateiformat.",
        )


@imports_router.get(
    "/history",
    response_model=List[BankImportResponse],
    summary="Import-Historie",
    description="Gibt die Import-Historie zurueck."
)
async def get_import_history(
    bank_account_id: Optional[UUID] = Query(
        None,
        description="Filter auf Bankkonto"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[BankImportResponse]:
    """Hole Import-Historie."""
    return await import_service.get_import_history(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        limit=limit,
    )


# ==================== Transaction Endpoints ====================

@transactions_router.get(
    "",
    response_model=dict,
    summary="Transaktionen auflisten",
    description="Gibt Transaktionen mit optionaler Filterung und Paginierung zurueck."
)
async def list_transactions(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    amount_min: Optional[float] = Query(None, description="Mindestbetrag"),
    amount_max: Optional[float] = Query(None, description="Hoechstbetrag"),
    transaction_type: Optional[TransactionType] = Query(None, description="Transaktionstyp"),
    reconciliation_status: Optional[ReconciliationStatus] = Query(None, description="Abgleich-Status"),
    search: Optional[str] = Query(None, description="Volltextsuche"),
    offset: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=200, description="Limit"),
    sort_by: TransactionSortField = Query(TransactionSortField.BOOKING_DATE, description="Sortierfeld"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sortierrichtung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Hole Transaktionen mit Filterung.

    Unterstuetzt Paginierung und verschiedene Filteroptionen.
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
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        filters=filters,
        offset=offset,
        limit=limit,
        sort_by=sort_by.value,  # SECURITY: Nur Enum-Werte erlaubt
        sort_order=sort_order,
    )

    return {
        "items": transactions,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@transactions_router.get(
    "/unmatched",
    response_model=List[BankTransactionResponse],
    summary="Unabgeglichene Transaktionen",
    description="Gibt alle unabgeglichenen Transaktionen zurueck."
)
async def get_unmatched_transactions(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[BankTransactionResponse]:
    """Hole unabgeglichene Transaktionen fuer Reconciliation."""
    return await transaction_service.get_unmatched_transactions(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        limit=limit,
    )


@transactions_router.get(
    "/stats",
    response_model=TransactionStats,
    summary="Transaktions-Statistiken",
    description="Gibt aggregierte Statistiken zurueck."
)
async def get_transaction_stats(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TransactionStats:
    """Hole Transaktions-Statistiken."""
    return await transaction_service.get_transaction_stats(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
    )


@transactions_router.get(
    "/monthly",
    response_model=List[dict],
    summary="Monatliche Zusammenfassung",
    description="Gibt monatliche Ein-/Ausgaben der letzten Monate zurueck."
)
async def get_monthly_summary(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    months: int = Query(12, ge=1, le=36, description="Anzahl Monate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole monatliche Zusammenfassung."""
    return await transaction_service.get_monthly_summary(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        months=months,
    )


@transactions_router.get(
    "/counterparties",
    response_model=List[dict],
    summary="Top Geschaeftspartner",
    description="Gibt die wichtigsten Geschaeftspartner nach Umsatz zurueck."
)
async def get_top_counterparties(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    direction: str = Query("both", regex="^(in|out|both)$", description="Richtung"),
    limit: int = Query(10, ge=1, le=50, description="Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole Top-Geschaeftspartner."""
    return await transaction_service.get_top_counterparties(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        direction=direction,
        limit=limit,
    )


@transactions_router.get(
    "/{transaction_id}",
    response_model=BankTransactionResponse,
    summary="Transaktion abrufen",
    description="Gibt eine einzelne Transaktion zurueck."
)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BankTransactionResponse:
    """Hole einzelne Transaktion."""
    transaction = await transaction_service.get_transaction(
        db=db,
        user_id=current_user.id,
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
) -> BankTransactionResponse:
    """Aktualisiere Transaktions-Metadaten."""
    transaction = await transaction_service.update_transaction(
        db=db,
        user_id=current_user.id,
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
) -> BankTransactionResponse:
    """Setze Abgleich-Status einer Transaktion."""
    transaction = await transaction_service.set_reconciliation_status(
        db=db,
        user_id=current_user.id,
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
    summary="Match-Vorschlaege",
    description="Gibt moegliche Matches fuer eine Transaktion zurueck."
)
async def get_match_suggestions(
    transaction_id: UUID,
    limit: int = Query(5, ge=1, le=20, description="Max. Vorschlaege"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Finde moegliche Match-Kandidaten fuer eine Transaktion.

    Nutzt verschiedene Matching-Strategien:
    - IBAN + Betrag (hoechste Konfidenz)
    - Rechnungsnummer im Verwendungszweck
    - Kundennummer + Betrag + Datum
    - Betrag + Datum-Naehe
    - Fuzzy Name-Matching
    """
    candidates = await reconciliation_service.find_matches(
        db=db,
        user_id=current_user.id,
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


@reconciliation_router.post(
    "/match/{transaction_id}",
    response_model=dict,
    summary="Manueller Abgleich",
    description="Matcht eine Transaktion manuell mit einem Dokument."
)
async def manual_match(
    transaction_id: UUID,
    document_id: UUID,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Manuelles Matching einer Transaktion mit einem Dokument.

    Setzt Konfidenz auf 100% (manuell bestaetigt).
    """
    try:
        result = await reconciliation_service.manual_match(
            db=db,
            user_id=current_user.id,
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Abgleich konnte nicht durchgefuehrt werden. Transaktion oder Dokument nicht gefunden.",
        )


@reconciliation_router.post(
    "/unmatch/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Abgleich aufheben",
    description="Entfernt den Abgleich von einer Transaktion."
)
async def unmatch_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Entferne Match von einer Transaktion."""
    success = await reconciliation_service.unmatch_transaction(
        db=db,
        user_id=current_user.id,
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


@reconciliation_router.post(
    "/split/{transaction_id}",
    response_model=List[dict],
    summary="Transaktion aufteilen",
    description="Teilt eine Transaktion auf mehrere Dokumente auf."
)
async def split_transaction(
    transaction_id: UUID,
    splits: List[dict],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Teile eine Transaktion auf mehrere Dokumente auf.

    Fuer Sammelzahlungen oder Teilzahlungen.
    Summe der Split-Betraege muss dem Transaktionsbetrag entsprechen.
    """
    try:
        results = await reconciliation_service.split_transaction(
            db=db,
            user_id=current_user.id,
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aufteilung fehlgeschlagen. Bitte ueberpruefen Sie die Betraege und Dokumente.",
        )


@reconciliation_router.post(
    "/batch",
    response_model=dict,
    summary="Batch-Abgleich",
    description="Fuehrt automatischen Abgleich fuer ungematchte Transaktionen durch."
)
async def batch_reconcile(
    bank_account_id: Optional[UUID] = None,
    limit: int = Query(100, ge=1, le=500, description="Max. Transaktionen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Automatischer Batch-Abgleich.

    Verarbeitet ungematchte Transaktionen und versucht automatischen
    Abgleich. Matched nur bei hoher Konfidenz (>= 90%).
    """
    result = await reconciliation_service.batch_reconcile(
        db=db,
        user_id=current_user.id,
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


@reconciliation_router.post(
    "/auto/{transaction_id}",
    response_model=dict,
    summary="Auto-Abgleich einzeln",
    description="Versucht automatischen Abgleich fuer eine einzelne Transaktion."
)
async def auto_reconcile_single(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Automatischer Abgleich einer einzelnen Transaktion.

    Matched nur bei hoher Konfidenz (>= 90%).
    """
    result = await reconciliation_service.auto_reconcile_transaction(
        db=db,
        user_id=current_user.id,
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

@payments_router.post(
    "",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Zahlung erstellen",
    description="Erstellt einen neuen Zahlungsauftrag (SEPA-Ueberweisung)."
)
async def create_payment(
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zahlung konnte nicht erstellt werden. Bitte ueberpruefen Sie die Zahlungsdaten.",
        )


@payments_router.get(
    "",
    response_model=dict,
    summary="Zahlungen auflisten",
    description="Listet alle Zahlungsauftraege des Benutzers."
)
async def list_payments(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    status_filter: Optional[PaymentStatus] = Query(None, alias="status", description="Filter auf Status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Liste Zahlungsauftraege."""
    payments, total = await payment_service.list_payments(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        status=status_filter,
        offset=offset,
        limit=limit,
    )

    return {
        "payments": payments,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@payments_router.get(
    "/pending",
    response_model=List[PaymentOrderResponse],
    summary="Ausstehende Zahlungen",
    description="Listet alle ausstehenden Zahlungsauftraege."
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
    summary="Skonto-Moeglichkeiten",
    description="Findet Rechnungen mit Skonto-Option innerhalb der naechsten Tage."
)
async def get_skonto_opportunities(
    days_ahead: int = Query(14, ge=1, le=60, description="Tage vorausschauen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Finde Skonto-Moeglichkeiten.

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


@payments_router.post(
    "/{payment_id}/approve",
    response_model=PaymentOrderResponse,
    summary="Zahlung genehmigen",
    description="Genehmigt einen Zahlungsauftrag fuer den Versand."
)
async def approve_payment(
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Genehmigung fehlgeschlagen. Zahlung kann in diesem Status nicht genehmigt werden.",
        )


@payments_router.post(
    "/{payment_id}/cancel",
    response_model=PaymentOrderResponse,
    summary="Zahlung stornieren",
    description="Storniert einen Zahlungsauftrag."
)
async def cancel_payment(
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stornierung fehlgeschlagen. Zahlung kann in diesem Status nicht storniert werden.",
        )


@payments_router.post(
    "/{payment_id}/submit",
    response_model=dict,
    summary="Zahlung senden",
    description="Sendet Zahlung an Bank (initiiert TAN-Challenge)."
)
async def submit_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Sende Zahlung an Bank.

    Initiiert TAN-Challenge zur Bestaetigung.
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zahlung konnte nicht gesendet werden. Bitte ueberpruefen Sie den Status.",
        )


@payments_router.post(
    "/{payment_id}/confirm-tan",
    response_model=PaymentOrderResponse,
    summary="TAN bestaetigen",
    description="Bestaetigt Zahlung mit TAN."
)
async def confirm_payment_tan(
    payment_id: UUID,
    tan: str = Query(..., min_length=6, max_length=6, description="TAN-Eingabe"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentOrderResponse:
    """
    Bestaetige Zahlung mit TAN.

    Nach erfolgreicher Bestaetigung wird die Zahlung ausgefuehrt.
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
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TAN-Bestaetigung fehlgeschlagen. Bitte versuchen Sie es erneut.",
        )


# ==================== TAN Endpoints ====================

@payments_router.get(
    "/tan/methods",
    response_model=List[dict],
    summary="TAN-Verfahren",
    description="Listet verfuegbare TAN-Verfahren."
)
async def get_tan_methods(
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole verfuegbare TAN-Verfahren."""
    return tan_handler_service.get_available_methods(current_user.id)


# ==================== Cash-Flow Endpoints ====================

@cashflow_router.get(
    "/forecast",
    response_model=dict,
    summary="Cash-Flow-Prognose",
    description="Erstellt Cash-Flow-Prognose fuer die naechsten Tage."
)
async def get_cash_flow_forecast(
    days_ahead: int = Query(90, ge=7, le=365, description="Tage voraus"),
    scenario: str = Query("realistic", description="Szenario (optimistic/realistic/pessimistic)"),
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
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
        user_id=current_user.id,
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
    description="Kurz-, mittel- und langfristige Cash-Flow-Uebersicht."
)
async def get_cash_flow_summary(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Hole Cash-Flow-Zusammenfassung mit Warnungen."""
    return await cash_flow_service.get_cash_flow_summary(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
    )


@cashflow_router.get(
    "/daily",
    response_model=List[dict],
    summary="Taegliche Prognose",
    description="Taegliche Cash-Flow-Werte fuer Diagramme."
)
async def get_daily_forecast(
    days: int = Query(30, ge=7, le=90, description="Anzahl Tage"),
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole taegliche Cash-Flow-Werte."""
    return await cash_flow_service.get_daily_forecast(
        db=db,
        user_id=current_user.id,
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
) -> dict:
    """Vergleiche verschiedene Szenarien."""
    return await cash_flow_service.compare_scenarios(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        days_ahead=days_ahead,
    )


# ==================== Dunning (Mahnwesen) Endpoints ====================

@dunning_router.get(
    "/overdue",
    response_model=List[dict],
    summary="Ueberfaellige Rechnungen",
    description="Listet alle ueberfaelligen Rechnungen mit Mahnempfehlungen."
)
async def get_overdue_invoices(
    min_days: int = Query(1, ge=1, description="Mind. Tage ueberfaellig"),
    max_days: Optional[int] = Query(None, description="Max. Tage ueberfaellig"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole ueberfaellige Rechnungen."""
    candidates = await dunning_service.get_overdue_invoices(
        db=db,
        user_id=current_user.id,
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


@dunning_router.post(
    "",
    response_model=DunningRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mahnvorgang erstellen",
    description="Startet einen neuen Mahnvorgang fuer eine Rechnung."
)
async def create_dunning(
    document_id: UUID,
    level: DunningLevel = Query(DunningLevel.FIRST_REMINDER, description="Mahnstufe"),
    notes: Optional[str] = Query(None, description="Notizen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DunningRecordResponse:
    """Erstelle neuen Mahnvorgang."""
    try:
        return await dunning_service.create_dunning(
            db=db,
            user_id=current_user.id,
            document_id=document_id,
            level=level,
            notes=notes,
        )
    except ValueError as e:
        logger.warning(
            "dunning_create_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnvorgang konnte nicht erstellt werden. Bitte ueberpruefen Sie die Rechnung.",
        )


@dunning_router.get(
    "",
    response_model=dict,
    summary="Mahnvorgaenge auflisten",
    description="Listet alle Mahnvorgaenge mit optionaler Filterung."
)
async def list_dunnings(
    status_filter: Optional[DunningStatus] = Query(None, alias="status"),
    level_filter: Optional[DunningLevel] = Query(None, alias="level"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Liste Mahnvorgaenge."""
    dunnings, total = await dunning_service.list_dunnings(
        db=db,
        user_id=current_user.id,
        status=status_filter,
        level=level_filter,
        offset=offset,
        limit=limit,
    )

    return {
        "items": dunnings,
        "total": total,
        "offset": offset,
        "limit": limit,
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
) -> dict:
    """Hole Mahnstatistiken."""
    return await dunning_service.get_dunning_stats(
        db=db,
        user_id=current_user.id,
    )


@dunning_router.post(
    "/{dunning_id}/escalate",
    response_model=DunningRecordResponse,
    summary="Mahnvorgang eskalieren",
    description="Eskaliert Mahnvorgang zur naechsten Stufe."
)
async def escalate_dunning(
    dunning_id: UUID,
    notes: Optional[str] = Query(None, description="Notizen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DunningRecordResponse:
    """Eskaliere Mahnvorgang."""
    try:
        return await dunning_service.escalate_dunning(
            db=db,
            user_id=current_user.id,
            dunning_id=dunning_id,
            notes=notes,
        )
    except ValueError as e:
        logger.warning(
            "dunning_escalate_failed",
            dunning_id=str(dunning_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnvorgang konnte nicht eskaliert werden. Bitte ueberpruefen Sie den Status.",
        )


@dunning_router.post(
    "/{dunning_id}/close",
    response_model=DunningRecordResponse,
    summary="Mahnvorgang schliessen",
    description="Schliesst einen Mahnvorgang ab (bezahlt, storniert, abgeschrieben)."
)
async def close_dunning(
    dunning_id: UUID,
    close_status: DunningStatus = Query(..., alias="status", description="Abschluss-Status"),
    notes: Optional[str] = Query(None, description="Notizen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DunningRecordResponse:
    """Schliesse Mahnvorgang."""
    try:
        return await dunning_service.close_dunning(
            db=db,
            user_id=current_user.id,
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
            error=str(e),
        )
        # SECURITY: Generische Fehlermeldung - keine internen Details exponieren
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahnvorgang konnte nicht abgeschlossen werden. Bitte ueberpruefen Sie den Status.",
        )


@dunning_router.post(
    "/process-automatic",
    response_model=List[dict],
    summary="Automatisches Mahnverfahren",
    description="Fuehrt automatisches Mahnverfahren durch (optional Dry-Run)."
)
async def process_automatic_dunning(
    dry_run: bool = Query(True, description="Nur simulieren, nicht ausfuehren"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Fuehre automatisches Mahnverfahren durch."""
    return await dunning_service.process_automatic_dunning(
        db=db,
        user_id=current_user.id,
        dry_run=dry_run,
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
    description="Kombinierte Uebersicht Forderungen und Verbindlichkeiten."
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
    description="Die groessten Schuldner nach Forderungshoehe."
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
    summary="Top-Glaeubiger",
    description="Die groessten Glaeubiger nach Verbindlichkeitenhoehe."
)
async def get_top_creditors(
    limit: int = Query(10, ge=1, le=50, description="Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """Hole Top-Glaeubiger."""
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
