# -*- coding: utf-8 -*-
"""
Alerts Services Package.

Enthält:
- ExtendedAlertsService: Erweiterte Alert-Typen (Cashflow, Contract, Compliance, Supplier)

Feinpoliert und durchdacht.
"""

from app.services.alerts.extended_alerts_service import (
    ExtendedAlertsService,
    ExtendedAlertCodes,
    EXTENDED_ALERT_TEMPLATES,
    CashflowAlertData,
    ContractAlertData,
    ComplianceAlertData,
    SupplierAlertData,
    get_extended_alerts_service,
)

__all__ = [
    "ExtendedAlertsService",
    "ExtendedAlertCodes",
    "EXTENDED_ALERT_TEMPLATES",
    "CashflowAlertData",
    "ContractAlertData",
    "ComplianceAlertData",
    "SupplierAlertData",
    "get_extended_alerts_service",
]
