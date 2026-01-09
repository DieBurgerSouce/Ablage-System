"""KPI Calculation Services fuer Enterprise Features.

Dieses Modul enthaelt die KPI-Berechnungs-Services:
- PropertyKPIService: Immobilien-KPIs
- VehicleKPIService: Fahrzeug-KPIs
- InsuranceKPIService: Versicherungs-KPIs
- LoanKPIService: Kredit-KPIs
"""

from app.services.kpi.property_kpi_service import (
    PropertyKPIService,
    PropertyKPIResult,
)
from app.services.kpi.vehicle_kpi_service import (
    VehicleKPIService,
    VehicleKPIResult,
)
from app.services.kpi.insurance_kpi_service import (
    InsuranceKPIService,
    InsuranceGapResult,
)
from app.services.kpi.loan_kpi_service import (
    LoanKPIService,
    AmortizationSchedule,
    ExtraPaymentImpact,
)

__all__ = [
    "PropertyKPIService",
    "PropertyKPIResult",
    "VehicleKPIService",
    "VehicleKPIResult",
    "InsuranceKPIService",
    "InsuranceGapResult",
    "LoanKPIService",
    "AmortizationSchedule",
    "ExtraPaymentImpact",
]
