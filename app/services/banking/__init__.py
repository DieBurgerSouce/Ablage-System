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
from .liquidity_forecast_service import (
    LiquidityForecastService,
    LiquidityForecastResult,
    RollingForecast,
    LiquidityBottleneck,
    LiquidityRiskLevel,
    PaymentAnomaly,
    AnomalyType,
    WaterfallChartData,
    ConfidenceInterval,
    ForecastConfidence,
    get_liquidity_forecast_service,
)
from .payment_automation_service import (
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
from .smart_reconciliation_service import (
    SmartReconciliationService,
    get_smart_reconciliation_service,
    ReconciliationStrategy,
    ReconciliationAction,
    ReconciliationMatch,
    ReconciliationResult as SmartReconciliationResult,
)
from .proactive_dunning_service import (
    ProactiveDunningService,
    get_proactive_dunning_service,
    DunningLevel as ProactiveDunningLevel,
    DunningAction as ProactiveDunningAction,
    DunningDecision,
    PaymentHistory,
    DunningProcessResult,
)
# Phase 6: PSD2/FinTS Banking Integration
from .psd2_integration_service import PSD2IntegrationService
from .account_connection_service import AccountConnectionService
from .auto_transaction_import_service import AutoTransactionImportService
from .payment_initiation_service import PaymentInitiationService
from .auto_reconciliation_service import AutoReconciliationService

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
    # Phase 6: Liquidity Forecasting (Januar 2026)
    "LiquidityForecastService",
    "LiquidityForecastResult",
    "RollingForecast",
    "LiquidityBottleneck",
    "LiquidityRiskLevel",
    "PaymentAnomaly",
    "AnomalyType",
    "WaterfallChartData",
    "ConfidenceInterval",
    "ForecastConfidence",
    "get_liquidity_forecast_service",
    # Phase 5.4: Payment Automation (Januar 2026)
    "PaymentAutomationService",
    "get_payment_automation_service",
    "PaymentPriority",
    "PaymentStrategy",
    "PaymentBatchStatus",
    "SuggestionReason",
    "PaymentSuggestion",
    "PaymentBatch",
    "PaymentSchedule",
    "AutomationConfig",
    # Vision 2026: Smart Reconciliation
    "SmartReconciliationService",
    "get_smart_reconciliation_service",
    "ReconciliationStrategy",
    "ReconciliationAction",
    "ReconciliationMatch",
    "SmartReconciliationResult",
    # Vision 2026: Proactive Dunning
    "ProactiveDunningService",
    "get_proactive_dunning_service",
    "ProactiveDunningLevel",
    "ProactiveDunningAction",
    "DunningDecision",
    "PaymentHistory",
    "DunningProcessResult",
    # Phase 6: PSD2/FinTS Banking Integration
    "PSD2IntegrationService",
    "AccountConnectionService",
    "AutoTransactionImportService",
    "PaymentInitiationService",
    "AutoReconciliationService",
]
