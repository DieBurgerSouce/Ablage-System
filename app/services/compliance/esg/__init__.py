"""
ESG-Reporting Services (Phase 7.4).

Environmental, Social, Governance Nachhaltigkeitsberichterstattung.
"""

from app.services.compliance.esg.esg_service import (
    ESGService,
    get_esg_service,
)
from app.services.compliance.esg.carbon_calculator import (
    CarbonCalculator,
    get_carbon_calculator,
)
from app.services.compliance.esg.supplier_sustainability import (
    SupplierSustainabilityService,
    get_supplier_sustainability_service,
)
from app.services.compliance.esg.report_generator import (
    ESGReportGenerator,
    get_esg_report_generator,
)
from app.services.compliance.esg.certification_tracker import (
    CertificationTracker,
    get_certification_tracker,
)

__all__ = [
    # Main Service
    "ESGService",
    "get_esg_service",
    # Carbon Calculator
    "CarbonCalculator",
    "get_carbon_calculator",
    # Supplier Sustainability
    "SupplierSustainabilityService",
    "get_supplier_sustainability_service",
    # Report Generator
    "ESGReportGenerator",
    "get_esg_report_generator",
    # Certification Tracker
    "CertificationTracker",
    "get_certification_tracker",
]
