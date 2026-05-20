# -*- coding: utf-8 -*-
"""
Insights Services - Proaktive Warnungen und Analysen.

Vision 2026 Q4: Proactive Insights System.

Module:
- daily_insights_engine: Batch-generierte tägliche Insights
- cashflow_predictor: ML-basierte Cashflow-Prognose (7-90 Tage)
- fraud_early_warning: Proaktive Betrugserkennung
- skonto_optimizer: KI-basierte Skonto-Zahlungsempfehlungen
- supplier_risk_monitor: Lieferanten-Risikoüberwachung
"""

from app.services.insights.daily_insights_engine import (
    DailyInsightsEngine,
    get_daily_insights_engine,
    DailyInsight,
    DailyInsightType,
    InsightSeverity,
    InsightStatus,
    InsightGenerationResult,
    InsightGeneratorConfig,
    BaseInsightGenerator,
    CashflowWarningGenerator,
    ContractExpiringGenerator,
    SkontoDeadlineGenerator,
    PaymentRiskGenerator,
    UnusualPatternGenerator,
    ComplianceReminderGenerator,
    OverdueInvoiceGenerator,
)

from app.services.insights.cashflow_predictor import (
    CashflowPredictor,
    get_cashflow_predictor,
    CashflowPrediction,
    CashflowDataPoint,
    CashflowTrend,
    RiskLevel as CashflowRiskLevel,
    PredictionConfidence,
    RecurringPayment,
    PendingInvoice,
)

from app.services.insights.fraud_early_warning import (
    FraudEarlyWarningService,
    get_fraud_early_warning_service,
    FraudAlert,
    FraudAlertType,
    FraudSeverity,
    FraudStatus,
    FraudIndicator,
    FraudScanResult,
)

from app.services.insights.skonto_optimizer import (
    SkontoOptimizer,
    get_skonto_optimizer,
    PaymentRecommendation,
    OptimizationResult,
    SkontoInvoice,
    RecommendationType,
    LiquidityImpact,
)

from app.services.insights.supplier_risk_monitor import (
    SupplierRiskMonitor,
    get_supplier_risk_monitor,
    SupplierRiskProfile,
    SupplierRiskLevel,
    RiskFactor,
    RiskFactorType,
    MonitoringAlert,
    HandelsregisterInfo,
    DataSource,
)

__all__ = [
    # Daily Insights Engine
    "DailyInsightsEngine",
    "get_daily_insights_engine",
    "DailyInsight",
    "InsightGenerationResult",
    "InsightGeneratorConfig",
    "DailyInsightType",
    "InsightSeverity",
    "InsightStatus",
    "BaseInsightGenerator",
    "CashflowWarningGenerator",
    "ContractExpiringGenerator",
    "SkontoDeadlineGenerator",
    "PaymentRiskGenerator",
    "UnusualPatternGenerator",
    "ComplianceReminderGenerator",
    "OverdueInvoiceGenerator",
    # Cashflow Predictor
    "CashflowPredictor",
    "get_cashflow_predictor",
    "CashflowPrediction",
    "CashflowDataPoint",
    "CashflowTrend",
    "CashflowRiskLevel",
    "PredictionConfidence",
    "RecurringPayment",
    "PendingInvoice",
    # Fraud Early Warning
    "FraudEarlyWarningService",
    "get_fraud_early_warning_service",
    "FraudAlert",
    "FraudAlertType",
    "FraudSeverity",
    "FraudStatus",
    "FraudIndicator",
    "FraudScanResult",
    # Skonto Optimizer
    "SkontoOptimizer",
    "get_skonto_optimizer",
    "PaymentRecommendation",
    "OptimizationResult",
    "SkontoInvoice",
    "RecommendationType",
    "LiquidityImpact",
    # Supplier Risk Monitor
    "SupplierRiskMonitor",
    "get_supplier_risk_monitor",
    "SupplierRiskProfile",
    "SupplierRiskLevel",
    "RiskFactor",
    "RiskFactorType",
    "MonitoringAlert",
    "HandelsregisterInfo",
    "DataSource",
]
