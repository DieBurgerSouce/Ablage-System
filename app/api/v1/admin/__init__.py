"""
Admin API v1 - Administration Endpoints.

Provides administrative functionality for:
- User management (CRUD, roles, password reset)
- System status (GPU, queue, health monitoring)
- Job management (cancel, retry, queue clearing)
- Rate limit management (overrides, usage stats)
- Audit log viewing and export

All endpoints require superuser/admin authentication.
"""

from fastapi import APIRouter

from app.api.v1.admin.users import router as users_router
from app.api.v1.admin.system import router as system_router
from app.api.v1.admin.jobs import router as jobs_router
from app.api.v1.admin.rate_limits import router as rate_limits_router
from app.api.v1.admin.audit import router as audit_router

# Main admin router
router = APIRouter(prefix="/admin", tags=["Administration"])

# Include sub-routers
router.include_router(users_router)
router.include_router(system_router)
router.include_router(jobs_router)
router.include_router(rate_limits_router)
router.include_router(audit_router)

__all__ = ["router"]
