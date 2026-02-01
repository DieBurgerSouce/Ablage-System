# -*- coding: utf-8 -*-
"""Dashboard Services Package.

Enterprise Dashboard-Widgets fuer Business Intelligence:
- Cash-Flow Forecast (30/60/90 Tage Prognose)
- Supplier Performance (Lieferanten-Metriken)
- Customer Lifetime Value (Kundenwert-Analyse)
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

__all__ = [
    "CashFlowForecastService",
    "get_cash_flow_forecast_service",
    "SupplierPerformanceService",
    "get_supplier_performance_service",
    "CustomerLTVService",
    "get_customer_ltv_service",
]
