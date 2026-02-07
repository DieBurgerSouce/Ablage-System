"""
Portal API Routes (Phase 5.2).

Kundenportal Self-Service API.
"""

from fastapi import APIRouter

from app.api.v1.portal.auth import router as auth_router
from app.api.v1.portal.invoices import router as invoices_router
from app.api.v1.portal.payments import router as payments_router
from app.api.v1.portal.complaints import router as complaints_router
from app.api.v1.portal.documents import router as documents_router
from app.api.v1.portal.messages import router as messages_router

router = APIRouter(prefix="/portal", tags=["Kundenportal"])

router.include_router(auth_router)
router.include_router(invoices_router)
router.include_router(payments_router)
router.include_router(complaints_router)
router.include_router(documents_router)
router.include_router(messages_router)

__all__ = ["router"]
