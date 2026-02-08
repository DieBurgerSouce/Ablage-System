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
from app.workers.tasks.predictive_tasks import (
    collect_metrics_for_prediction,
    run_predictions,
    generate_predictive_alerts,
    cleanup_old_predictive_alerts,
)
from app.workers.tasks.insights_tasks import (
    generate_daily_cashflow_predictions,
    generate_cashflow_prediction,
    run_daily_fraud_scan,
    scan_company_for_fraud,
    generate_daily_skonto_recommendations,
    optimize_skonto_for_company,
    process_action_queue_timeouts,
    generate_all_daily_insights,
    check_urgent_skonto_deadlines,
)
from app.workers.tasks.fraud_detection_tasks import (
    scan_new_documents_task,
    daily_anomaly_check_task,
    iban_verification_task,
    check_expired_iban_requests_task,
    train_fraud_model_task,
    generate_fraud_statistics_task,
    FRAUD_DETECTION_BEAT_SCHEDULE,
)
from app.workers.tasks.document_tasks import (
    document_bulk_export_task,
    document_reprocess_task,
)
from app.workers.tasks.einvoice_tasks import (
    zugferd_batch_convert_task,
    zugferd_embed_task,
    einvoice_validate_task,
    EINVOICE_BEAT_SCHEDULE,
)
from app.workers.tasks.banking_psd2_tasks import (
    sync_all_bank_accounts,
    sync_single_connection,
    refresh_psd2_consents,
    check_expired_connections,
    auto_reconcile_transactions,
    reconcile_pending_batch,
    process_scheduled_payments,
    check_payment_status,
    update_connection_health,
    cleanup_old_sync_logs,
    PSD2_BANKING_BEAT_SCHEDULE,
)
from app.workers.tasks.fx_rate_tasks import (
    fetch_ecb_rates_daily,
    fetch_ecb_rates_historical,
    month_end_revaluation,
)
from app.workers.tasks.gl_posting_tasks import (
    auto_post_document_task,
    generate_trial_balance_task,
    generate_euer_task,
)
from app.workers.tasks.retention_tasks import (
    check_expiring_archives_task,
    verify_archive_integrity_task,
    process_expired_archives_task,
    generate_retention_report_task,
)
from app.workers.tasks.mtls_tasks import (
    rotate_expiring_certificates_task,
    verify_all_certificates_task,
    cleanup_revoked_certificates_task,
    sync_certificate_registry_task,
    generate_mtls_audit_report_task,
    initialize_service_certificates_task,
    revoke_certificate_task,
    get_ca_status_task,
)
from app.workers.tasks.ocr_router_training_tasks import (
    collect_and_train_task,
    evaluate_ab_test_task,
    check_all_ab_tests_task,
    generate_synthetic_data_task,
)
from app.workers.tasks.autonomous_trust_tasks import (
    process_due_proposals,
    update_trust_metrics,
    evaluate_trust_upgrades,
    cleanup_expired_proposals,
    notify_pending_proposals,
)
from app.workers.tasks.retention_enforcement_tasks import (
    enforce_retention_daily_scan,
    process_post_retention_reviews,
    generate_retention_compliance_report,
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
    # Predictive Maintenance tasks
    "collect_metrics_for_prediction",
    "run_predictions",
    "generate_predictive_alerts",
    "cleanup_old_predictive_alerts",
    # Financial Insights tasks
    "generate_daily_cashflow_predictions",
    "generate_cashflow_prediction",
    "run_daily_fraud_scan",
    "scan_company_for_fraud",
    "generate_daily_skonto_recommendations",
    "optimize_skonto_for_company",
    "process_action_queue_timeouts",
    "generate_all_daily_insights",
    "check_urgent_skonto_deadlines",
    # Fraud Detection tasks
    "scan_new_documents_task",
    "daily_anomaly_check_task",
    "iban_verification_task",
    "check_expired_iban_requests_task",
    "train_fraud_model_task",
    "generate_fraud_statistics_task",
    "FRAUD_DETECTION_BEAT_SCHEDULE",
    # Document tasks
    "document_bulk_export_task",
    "document_reprocess_task",
    # E-Invoice tasks
    "zugferd_batch_convert_task",
    "zugferd_embed_task",
    "einvoice_validate_task",
    "EINVOICE_BEAT_SCHEDULE",
    # PSD2/FinTS Banking tasks
    "sync_all_bank_accounts",
    "sync_single_connection",
    "refresh_psd2_consents",
    "check_expired_connections",
    "auto_reconcile_transactions",
    "reconcile_pending_batch",
    "process_scheduled_payments",
    "check_payment_status",
    "update_connection_health",
    "cleanup_old_sync_logs",
    "PSD2_BANKING_BEAT_SCHEDULE",
    # FX Rate tasks
    "fetch_ecb_rates_daily",
    "fetch_ecb_rates_historical",
    "month_end_revaluation",
    # GL Posting tasks
    "auto_post_document_task",
    "generate_trial_balance_task",
    "generate_euer_task",
    # Retention tasks
    "check_expiring_archives_task",
    "verify_archive_integrity_task",
    "process_expired_archives_task",
    "generate_retention_report_task",
    # mTLS tasks
    "rotate_expiring_certificates_task",
    "verify_all_certificates_task",
    "cleanup_revoked_certificates_task",
    "sync_certificate_registry_task",
    "generate_mtls_audit_report_task",
    "initialize_service_certificates_task",
    "revoke_certificate_task",
    "get_ca_status_task",
    # OCR Router Training tasks
    "collect_and_train_task",
    "evaluate_ab_test_task",
    "check_all_ab_tests_task",
    "generate_synthetic_data_task",
    # Autonomous Trust tasks
    "process_due_proposals",
    "update_trust_metrics",
    "evaluate_trust_upgrades",
    "cleanup_expired_proposals",
    "notify_pending_proposals",
    # Retention Enforcement tasks
    "enforce_retention_daily_scan",
    "process_post_retention_reviews",
    "generate_retention_compliance_report",
]
