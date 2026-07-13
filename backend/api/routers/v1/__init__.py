from fastapi import APIRouter

from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .github_audit import router as github_audit_router
from .integration import router as integration_router
from .jobs import router as jobs_router
from .permalink import router as permalink_router


router = APIRouter(prefix='/v1')
router.include_router(jobs_router)
router.include_router(integration_router)
router.include_router(auth_router)
router.include_router(permalink_router)
router.include_router(dashboard_router)
router.include_router(github_audit_router)
