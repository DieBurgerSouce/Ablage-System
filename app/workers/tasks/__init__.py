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
from app.workers.tasks.training_tasks import (
    run_benchmark_batch,
    run_scheduled_benchmarks,
    generate_daily_stats,
    process_feedback_queue,
    update_learned_weights,
    populate_training_batch,
    generate_training_report,
    CELERY_BEAT_TRAINING_SCHEDULE,
)
from app.workers.tasks.notification_tasks import (
    send_daily_digest,
    send_weekly_digest,
    cleanup_old_notifications,
)
from app.workers.tasks.report_tasks import (
    execute_scheduled_reports,
    generate_report_async,
    send_report_email,
    cleanup_old_executions,
    cleanup_expired_downloads,
    cancel_execution,
    REPORT_BEAT_SCHEDULE,
)
from app.workers.tasks.entity_linking_tasks import (
    link_all_documents_task,
    link_single_document_task,
    post_lexware_import_linking_task,
    generate_linking_statistics_task,
    reprocess_low_confidence_documents_task,
    on_ocr_completed_link_entity,
    on_entity_imported_check_documents,
    ENTITY_LINKING_BEAT_SCHEDULE,
)
from app.workers.tasks.risk_scoring_tasks import (
    calculate_all_risk_scores_task,
    calculate_single_risk_score_task,
    on_invoice_updated_recalculate,
    check_high_risk_entities_task,
    generate_risk_statistics_task,
)
from app.workers.tasks.chain_tasks import (
    auto_link_document_task,
    auto_link_all_documents_task,
    check_chain_discrepancies_task,
    on_ocr_completed_auto_link,
    generate_chain_statistics_task,
    CHAIN_BEAT_SCHEDULE,
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
    # Training tasks
    "run_benchmark_batch",
    "run_scheduled_benchmarks",
    "generate_daily_stats",
    "process_feedback_queue",
    "update_learned_weights",
    "populate_training_batch",
    "generate_training_report",
    "CELERY_BEAT_TRAINING_SCHEDULE",
    # Notification tasks
    "send_daily_digest",
    "send_weekly_digest",
    "cleanup_old_notifications",
    # Report tasks
    "execute_scheduled_reports",
    "generate_report_async",
    "send_report_email",
    "cleanup_old_executions",
    "cleanup_expired_downloads",
    "cancel_execution",
    "REPORT_BEAT_SCHEDULE",
    # Entity Linking tasks
    "link_all_documents_task",
    "link_single_document_task",
    "post_lexware_import_linking_task",
    "generate_linking_statistics_task",
    "reprocess_low_confidence_documents_task",
    "on_ocr_completed_link_entity",
    "on_entity_imported_check_documents",
    "ENTITY_LINKING_BEAT_SCHEDULE",
    # Risk Scoring tasks
    "calculate_all_risk_scores_task",
    "calculate_single_risk_score_task",
    "on_invoice_updated_recalculate",
    "check_high_risk_entities_task",
    "generate_risk_statistics_task",
    # Document Chain tasks
    "auto_link_document_task",
    "auto_link_all_documents_task",
    "check_chain_discrepancies_task",
    "on_ocr_completed_auto_link",
    "generate_chain_statistics_task",
    "CHAIN_BEAT_SCHEDULE",
]
