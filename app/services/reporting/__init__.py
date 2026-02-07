"""
Reporting Services Package

Services fuer Geschaeftsfuehrung Dashboard und Reporting.
"""

from app.services.reporting.executive_dashboard_service import (
    ExecutiveDashboardService,
    get_kpis,
    get_department_breakdown,
    get_trend,
)

__all__ = [
    "ExecutiveDashboardService",
    "get_kpis",
    "get_department_breakdown",
    "get_trend",
]
