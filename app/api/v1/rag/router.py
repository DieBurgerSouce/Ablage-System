"""RAG API Router - Zentrale Route-Konfiguration.

Bindet alle RAG-Submodule zusammen:
- /search - RAG-basierte Suche
- /chunks - Document Chunking
- /chat - Chat Sessions
- /ws - WebSocket für Real-time Chat
- /customers - Customer Cards (Phase 5)
- /jobs - Batch Jobs
- legacy: /customer-cards, /models, /health, /bi/*, /ai/* (B6-Fix)
"""

from fastapi import APIRouter

from app.api.v1.rag.search import router as search_router
from app.api.v1.rag.chunks import router as chunks_router
from app.api.v1.rag.chat import router as chat_router
from app.api.v1.rag.chat_ws import router as chat_ws_router
from app.api.v1.rag.jobs import router as jobs_router
from app.api.v1.rag.customers import router as customers_router
from app.api.v1.rag.legacy import router as legacy_router

router = APIRouter(prefix="/rag", tags=["rag"])

# Sub-Router einbinden
router.include_router(search_router)
router.include_router(chunks_router)
router.include_router(chat_router)
router.include_router(chat_ws_router)
router.include_router(jobs_router)
router.include_router(customers_router)
# BUGFIX (2026-06-12, B6): Endpoints aus dem frueher durch dieses Package
# geshadowten app/api/v1/rag.py (ai/bi/customer-cards/models/health).
router.include_router(legacy_router)
