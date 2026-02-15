"""
Reporting Services Package

Services fuer Geschaeftsfuehrung Dashboard und Reporting.
Inklusive Ad-Hoc Reporting (Feature #12).
"""

from app.services.reporting.executive_dashboard_service import (
    ExecutiveDashboardService,
    get_kpis,
    get_department_breakdown,
    get_trend,
)
from app.services.reporting.adhoc_report_service import AdHocReportService
from app.services.reporting.scheduled_report_service import ScheduledReportService

__all__ = [
    "ExecutiveDashboardService",
    "get_kpis",
    "get_department_breakdown",
    "get_trend",
    "AdHocReportService",
    "ScheduledReportService",
]
