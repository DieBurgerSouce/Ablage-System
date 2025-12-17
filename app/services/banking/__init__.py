"""Banking Integration Services for Ablage-System.

Provides:
- Multi-format bank statement import (MT940, CAMT.053, CSV)
- Transaction reconciliation with invoices
- SEPA payment creation and submission
- Cash flow forecasting
- Dunning/Mahnwesen management
"""

from .models import (
    # Enums
    BankAccountType,
    ImportFormat,
    TransactionType,
    ReconciliationStatus,
    PaymentStatus,
    PaymentType,
    DunningLevel,
    DunningStatus,
    CashFlowDirection,
    CashFlowStatus,
    # Schemas
    BankAccountCreate,
    BankAccountUpdate,
    BankAccountResponse,
    BankAccountWithStats,
    BankImportCreate,
    BankImportPreview,
    BankImportResponse,
    BankTransactionResponse,
    TransactionMatch,
    ReconciliationResult,
    PaymentOrderCreate,
    PaymentOrderResponse,
    DunningRecordResponse,
    CashFlowEntryResponse,
    CashFlowForecast,
    SupportedFormatsResponse,
    TransactionFilter,
    TransactionStats,
)
from .account_service import AccountService
from .import_service import ImportService
from .transaction_service import TransactionService
from .reference_parser import ReferenceParser, parse_reference_text
from .reconciliation_service import ReconciliationService
from .payment_service import PaymentService
from .tan_handler_service import TANHandlerService, TANMethod
from .cash_flow_service import CashFlowService, ForecastScenario, ForecastPeriod
from .dunning_service import DunningService, DunningConfig, DunningAction
from .aging_report_service import AgingReportService, AgingBucket, ReportType

__all__ = [
    # Enums
    "BankAccountType",
    "ImportFormat",
    "TransactionType",
    "ReconciliationStatus",
    "PaymentStatus",
    "PaymentType",
    "DunningLevel",
    "DunningStatus",
    "CashFlowDirection",
    "CashFlowStatus",
    # Schemas
    "BankAccountCreate",
    "BankAccountUpdate",
    "BankAccountResponse",
    "BankAccountWithStats",
    "BankImportCreate",
    "BankImportPreview",
    "BankImportResponse",
    "BankTransactionResponse",
    "TransactionMatch",
    "ReconciliationResult",
    "PaymentOrderCreate",
    "PaymentOrderResponse",
    "DunningRecordResponse",
    "CashFlowEntryResponse",
    "CashFlowForecast",
    "SupportedFormatsResponse",
    # Services
    "AccountService",
    "ImportService",
    "TransactionService",
    "ReferenceParser",
    "parse_reference_text",
    "ReconciliationService",
    "PaymentService",
    "TANHandlerService",
    "TANMethod",
    # Phase 5: Cash-Flow & Mahnwesen
    "CashFlowService",
    "ForecastScenario",
    "ForecastPeriod",
    "DunningService",
    "DunningConfig",
    "DunningAction",
    "AgingReportService",
    "AgingBucket",
    "ReportType",
    # Filter & Stats
    "TransactionFilter",
    "TransactionStats",
]
