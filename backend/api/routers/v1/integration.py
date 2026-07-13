from fastapi import APIRouter

from api.core.config import settings
from api.core.const import ALLOWED_MODELS
from api.core.impl import auth_backend
from api.schemas.integration import FrontendConfig


router = APIRouter(prefix='/integration', tags=['integration'])

# Order matters — first entry is the default in the frontend
_MODEL_ORDER = ['gpt-5.2-codex', 'gpt-5.4', 'gpt-5.1-codex-max']


@router.get('/frontend')
async def frontend_config() -> FrontendConfig:
    models = [m for m in _MODEL_ORDER if m in ALLOWED_MODELS]
    return FrontendConfig(
        auth_enabled=bool(auth_backend),
        key_predefined=(
            settings.BACKEND_STATIC_OAI_KEY is not None
            or settings.BACKEND_USE_PROXY_STATIC_KEY
            or settings.BACKEND_OAI_KEY_MODE == 'subscription'
        ),
        models=models,
    )
