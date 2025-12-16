"""
Vector Search Services Package.

Parallele Vector-DB-Infrastruktur fuer A/B Testing:
- QdrantService: Qdrant Vector-DB Integration
- EmbeddingFactory: Multi-Model Embedding Generation (E5-Large, Jina-DE)
- RerankerService: BGE-Reranker Cross-Encoder
- VectorSearchOrchestrator: Unified Interface mit A/B Testing

Feinpoliert und durchdacht - Enterprise-grade Vector Search.
"""

from app.services.vector.qdrant_service import QdrantService, get_qdrant_service
from app.services.vector.embedding_factory import EmbeddingFactory, get_embedding_factory
from app.services.vector.reranker_service import RerankerService, get_reranker_service
from app.services.vector.vector_orchestrator import VectorSearchOrchestrator, get_vector_orchestrator

__all__ = [
    # Services
    "QdrantService",
    "EmbeddingFactory",
    "RerankerService",
    "VectorSearchOrchestrator",
    # Factory Functions
    "get_qdrant_service",
    "get_embedding_factory",
    "get_reranker_service",
    "get_vector_orchestrator",
]
