"""RAG Intelligence Layer API.

Enthält alle API-Endpoints für:
- RAG Search (Chunk-basierte Suche)
- Document Chunking
- Chat Sessions
- Customer Cards (Phase 5)
- Batch Jobs
"""

from app.api.v1.rag.router import router

__all__ = ["router"]
