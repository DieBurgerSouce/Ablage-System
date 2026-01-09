"""Privat-Modul Services.

Dieses Modul bietet Services fuer das persoenliche Dokumentenmanagement:
- SpaceService: Verwaltung privater Bereiche
- FolderService: Ordnerstruktur-Verwaltung
- DocumentService: Dokument-CRUD mit Verschluesselung
- PropertyService: Immobilienverwaltung
- VehicleService: Fahrzeugverwaltung
- InsuranceService: Versicherungsverwaltung
- LoanService: Kreditverwaltung
- InvestmentService: Geldanlagen-Verwaltung
- DeadlineService: Fristenmanagement + iCal
- EmergencyService: Notfallzugriff
- AccessService: Zugriffsberechtigungen
- EncryptionService: Extra-Verschluesselung

Enterprise KPI-Berechnungs-Services:
- PropertyCalculationService: Mietrendite, ROI, Wertsteigerung
- VehicleCalculationService: TCO, Abschreibung, Verbrauch
- InsuranceAnalysisService: Deckungsluecken, Kuendigungsfristen
- LoanAmortizationService: Tilgungsplan, Zinsersparnis

Enterprise Analytics-Services:
- FinanceAnalyticsService: Trends, YoY-Vergleiche, Prognosen
"""

from app.services.privat.space_service import PrivatSpaceService
from app.services.privat.folder_service import PrivatFolderService
from app.services.privat.document_service import PrivatDocumentService
from app.services.privat.property_service import PrivatPropertyService
from app.services.privat.vehicle_service import PrivatVehicleService
from app.services.privat.insurance_service import PrivatInsuranceService
from app.services.privat.loan_service import PrivatLoanService
from app.services.privat.investment_service import PrivatInvestmentService
from app.services.privat.deadline_service import PrivatDeadlineService
from app.services.privat.emergency_service import PrivatEmergencyService
from app.services.privat.access_service import PrivatAccessService
from app.services.privat.encryption_service import PrivatEncryptionService

# Enterprise KPI-Services
from app.services.privat.property_calculation_service import (
    PropertyCalculationService,
    get_property_calculation_service,
)
from app.services.privat.vehicle_calculation_service import (
    VehicleCalculationService,
    get_vehicle_calculation_service,
)
from app.services.privat.insurance_analysis_service import (
    InsuranceAnalysisService,
    get_insurance_analysis_service,
)
from app.services.privat.loan_amortization_service import (
    LoanAmortizationService,
    get_loan_amortization_service,
)
from app.services.privat.finance_analytics_service import (
    FinanceAnalyticsService,
    get_finance_analytics_service,
)

__all__ = [
    "PrivatSpaceService",
    "PrivatFolderService",
    "PrivatDocumentService",
    "PrivatPropertyService",
    "PrivatVehicleService",
    "PrivatInsuranceService",
    "PrivatLoanService",
    "PrivatInvestmentService",
    "PrivatDeadlineService",
    "PrivatEmergencyService",
    "PrivatAccessService",
    "PrivatEncryptionService",
    # Enterprise KPI-Services
    "PropertyCalculationService",
    "get_property_calculation_service",
    "VehicleCalculationService",
    "get_vehicle_calculation_service",
    "InsuranceAnalysisService",
    "get_insurance_analysis_service",
    "LoanAmortizationService",
    "get_loan_amortization_service",
    # Enterprise Analytics-Services
    "FinanceAnalyticsService",
    "get_finance_analytics_service",
]
