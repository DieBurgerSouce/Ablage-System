"""
Kundenportal Services (Phase 5.2).

Self-Service Portal fuer Kunden und Lieferanten.
"""

from app.services.portal.portal_auth_service import (
    PortalAuthService,
    PortalAuthError,
    PortalUserNotFoundError,
    PortalUserInactiveError,
    InvalidPortalCredentialsError,
    PortalAccountLockedError,
    get_portal_auth_service,
)
from app.services.portal.portal_invoice_service import (
    PortalInvoiceService,
    get_portal_invoice_service,
)
from app.services.portal.portal_payment_service import (
    PortalPaymentService,
    get_portal_payment_service,
)
from app.services.portal.portal_complaint_service import (
    PortalComplaintService,
    get_portal_complaint_service,
)
from app.services.portal.portal_document_service import (
    PortalDocumentService,
    get_portal_document_service,
)
from app.services.portal.portal_communication_service import (
    PortalCommunicationService,
    get_portal_communication_service,
)

__all__ = [
    # Auth
    "PortalAuthService",
    "PortalAuthError",
    "PortalUserNotFoundError",
    "PortalUserInactiveError",
    "InvalidPortalCredentialsError",
    "PortalAccountLockedError",
    "get_portal_auth_service",
    # Invoice
    "PortalInvoiceService",
    "get_portal_invoice_service",
    # Payment
    "PortalPaymentService",
    "get_portal_payment_service",
    # Complaint
    "PortalComplaintService",
    "get_portal_complaint_service",
    # Document
    "PortalDocumentService",
    "get_portal_document_service",
    # Communication
    "PortalCommunicationService",
    "get_portal_communication_service",
]
