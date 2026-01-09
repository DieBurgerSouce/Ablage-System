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

# Enterprise Intelligence Services
from app.services.privat.property_intelligence_service import (
    PropertyIntelligenceService,
    get_property_intelligence_service,
)
from app.services.privat.vehicle_intelligence_service import (
    VehicleIntelligenceService,
    get_vehicle_intelligence_service,
)
from app.services.privat.investment_intelligence_service import (
    InvestmentIntelligenceService,
    get_investment_intelligence_service,
)
from app.services.privat.financial_health_service import (
    FinancialHealthService,
    get_financial_health_service,
)
from app.services.privat.recommendations_service import (
    RecommendationsService,
    get_recommendations_service,
)
from app.services.privat.loan_scenario_service import (
    LoanScenarioService,
    get_loan_scenario_service,
)
from app.services.privat.insurance_intelligence_service import (
    InsuranceIntelligenceService,
    get_insurance_intelligence_service,
)
from app.services.privat.kpi_orchestrator import (
    KPIOrchestrationService,
    get_kpi_orchestration_service,
)
from app.services.privat.ki_prompt_service import (
    PrivatKIPromptService,
    get_privat_ki_prompt_service,
    PropertyValueAnalysis,
    VehicleDepreciationAnalysis,
    InvestmentAdvice,
    InsuranceCheckResult,
    FinancialQAResponse,
)

# Predictive Intelligence
from app.services.privat.predictive_intelligence_service import (
    PredictiveIntelligenceService,
    get_predictive_intelligence_service,
    KPIProjection,
    EarlyWarningAlert,
    PredictiveInsightsSummary,
    TrendAnalysis,
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
    # Enterprise Intelligence Services
    "PropertyIntelligenceService",
    "get_property_intelligence_service",
    "VehicleIntelligenceService",
    "get_vehicle_intelligence_service",
    "InvestmentIntelligenceService",
    "get_investment_intelligence_service",
    "FinancialHealthService",
    "get_financial_health_service",
    "RecommendationsService",
    "get_recommendations_service",
    "LoanScenarioService",
    "get_loan_scenario_service",
    # Insurance Intelligence Wrapper
    "InsuranceIntelligenceService",
    "get_insurance_intelligence_service",
    # KPI Orchestration
    "KPIOrchestrationService",
    "get_kpi_orchestration_service",
    # KI-Prompt Service
    "PrivatKIPromptService",
    "get_privat_ki_prompt_service",
    "PropertyValueAnalysis",
    "VehicleDepreciationAnalysis",
    "InvestmentAdvice",
    "InsuranceCheckResult",
    "FinancialQAResponse",
    # Predictive Intelligence
    "PredictiveIntelligenceService",
    "get_predictive_intelligence_service",
    "KPIProjection",
    "EarlyWarningAlert",
    "PredictiveInsightsSummary",
    "TrendAnalysis",
]
