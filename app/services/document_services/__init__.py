"""Document Services - Modulare Dokumentenverwaltung.

Split-Architektur fuer bessere Wartbarkeit und Testbarkeit:
- DocumentCRUDService: Basis-CRUD-Operationen
- DocumentGDPRService: Soft-Delete und GDPR-Konformitaet
- DocumentBatchService: Bulk-Operationen fuer mehrere Dokumente
- DocumentExportService: Export in verschiedene Formate
- DocumentFilterService: Filterung und Query-Bau
"""

from app.services.document_services.crud_service import DocumentCRUDService
from app.services.document_services.gdpr_service import DocumentGDPRService
from app.services.document_services.batch_service import DocumentBatchService
from app.services.document_services.export_service import DocumentExportService
from app.services.document_services.filter_service import DocumentFilterService

__all__ = [
    "DocumentCRUDService",
    "DocumentGDPRService",
    "DocumentBatchService",
    "DocumentExportService",
    "DocumentFilterService",
]
