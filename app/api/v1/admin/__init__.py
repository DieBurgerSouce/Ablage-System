"""
Admin API v1 - Administration Endpoints.

Provides administrative functionality for:
- User management (CRUD, roles, password reset)
- Role-Based Access Control (RBAC) management
- System status (GPU, queue, health monitoring)
- Job management (cancel, retry, queue clearing)
- Rate limit management (overrides, usage stats)
- Audit log viewing and export

All endpoints require appropriate permissions (RBAC).
"""

from fastapi import APIRouter

from app.api.v1.admin.users import router as users_router
from app.api.v1.admin.roles import router as roles_router
from app.api.v1.admin.system import router as system_router
from app.api.v1.admin.jobs import router as jobs_router
from app.api.v1.admin.rate_limits import router as rate_limits_router
from app.api.v1.admin.audit import router as audit_router
from app.api.v1.admin.incidents import router as incidents_router
from app.api.v1.admin.extraction import router as extraction_router
from app.api.v1.admin.company import router as company_router
from app.api.v1.admin.tags import router as tags_router
from app.api.v1.admin.queues import router as queues_router
from app.api.v1.admin.dlq import router as dlq_router
from app.api.v1.admin.erp import router as erp_router
from app.api.v1.admin.automation_config import router as automation_config_router
from app.api.v1.feature_toggles import router as feature_toggles_router

# Main admin router
router = APIRouter(prefix="/admin", tags=["Administration"])

# Include sub-routers
router.include_router(users_router)
router.include_router(roles_router)
router.include_router(system_router)
router.include_router(jobs_router)
router.include_router(rate_limits_router)
router.include_router(audit_router)
router.include_router(incidents_router)
router.include_router(extraction_router)
router.include_router(company_router)
router.include_router(tags_router)
router.include_router(queues_router)
router.include_router(dlq_router)
router.include_router(erp_router)
router.include_router(automation_config_router)
router.include_router(feature_toggles_router)

__all__ = ["router"]
