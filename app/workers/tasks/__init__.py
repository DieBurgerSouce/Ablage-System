"""
Celery Tasks for Multi-Agent System.

Task modules:
- ocr_tasks: OCR processing tasks (GPU/CPU, batch)
- monitoring_tasks: Health checks, metrics collection
- cleanup_tasks: Temporary file cleanup, cache eviction
- backup_tasks: Database backup, restore
"""

__all__ = [
    "process_document_gpu",
    "process_document_cpu",
    "batch_process_documents",
    "health_check_task",
    "cleanup_temp_files",
    "backup_database",
]
