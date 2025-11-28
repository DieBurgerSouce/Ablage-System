"""Celery tasks for async processing."""

from app.workers.tasks.ocr_tasks import (
    process_document_task,
    batch_process_task,
    validate_german_text_task,
    extract_metadata_task,
    cleanup_task,
    update_system_metrics,
)
from app.workers.tasks.embedding_tasks import (
    generate_document_embedding,
    batch_generate_embeddings,
    regenerate_all_embeddings,
    check_embedding_coverage,
)

__all__ = [
    # OCR tasks
    "process_document_task",
    "batch_process_task",
    "validate_german_text_task",
    "extract_metadata_task",
    "cleanup_task",
    "update_system_metrics",
    # Embedding tasks
    "generate_document_embedding",
    "batch_generate_embeddings",
    "regenerate_all_embeddings",
    "check_embedding_coverage",
]
