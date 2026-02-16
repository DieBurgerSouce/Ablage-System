"""Document Services - Modulare Dokumentenverwaltung.

Split-Architektur für bessere Wartbarkeit und Testbarkeit:
- DocumentCRUDService: Basis-CRUD-Operationen
- DocumentGDPRService: Soft-Delete und GDPR-Konformität
- DocumentBatchService: Bulk-Operationen für mehrere Dokumente
- DocumentExportService: Export in verschiedene Formate
- DocumentFilterService: Filterung und Query-Bau
- AblageService: Kategorie-basierte Dokumentenverwaltung (Ablage-Ansicht)
- FinanceService: Jahr-basierte Finanz-Dokumentenverwaltung

Diese modularen Services sind die kanonischen Implementierungen.
Die Standalone-Dateien (document_gdpr_service.py, document_export_service.py)
sind deprecated Wrapper für Rückwärtskompatibilität.
"""

from app.services.document_services.crud_service import DocumentCRUDService
from app.services.document_services.gdpr_service import DocumentGDPRService, get_gdpr_service
from app.services.document_services.batch_service import DocumentBatchService
from app.services.document_services.export_service import DocumentExportService, get_export_service
from app.services.document_services.filter_service import DocumentFilterService
from app.services.document_services.ablage_service import AblageService, get_ablage_service
from app.services.document_services.finance_service import FinanceService, get_finance_service

__all__ = [
    "DocumentCRUDService",
    "DocumentGDPRService",
    "get_gdpr_service",
    "DocumentBatchService",
    "DocumentExportService",
    "get_export_service",
    "DocumentFilterService",
    "AblageService",
    "get_ablage_service",
    "FinanceService",
    "get_finance_service",
]
