# -*- coding: utf-8 -*-
"""Dashboard Services Package.

Enterprise Dashboard-Widgets fuer Business Intelligence:
- Cash-Flow Forecast (30/60/90 Tage Prognose)
- Supplier Performance (Lieferanten-Metriken)
- Customer Lifetime Value (Kundenwert-Analyse)
- Period Comparison (YoY/MoM/QoQ Analytics)
- Dashboard Sharing (Persistente Freigaben mit Audit-Trail)
"""

from .cash_flow_forecast_service import (
    CashFlowForecastService,
    get_cash_flow_forecast_service,
)
from .supplier_performance_service import (
    SupplierPerformanceService,
    get_supplier_performance_service,
)
from .customer_ltv_service import (
    CustomerLTVService,
    get_customer_ltv_service,
)
from .period_comparison_service import (
    PeriodComparisonService,
    ComparisonPeriod,
    PeriodMetrics,
    PeriodComparison,
)
from .sharing_service import (
    DashboardSharingService,
    get_sharing_service,
)

__all__ = [
    "CashFlowForecastService",
    "get_cash_flow_forecast_service",
    "SupplierPerformanceService",
    "get_supplier_performance_service",
    "CustomerLTVService",
    "get_customer_ltv_service",
    "PeriodComparisonService",
    "ComparisonPeriod",
    "PeriodMetrics",
    "PeriodComparison",
    "DashboardSharingService",
    "get_sharing_service",
]
