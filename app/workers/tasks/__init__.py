"""Celery tasks for async processing."""

import logging

_import_logger = logging.getLogger(__name__)

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
)
from app.workers.tasks.entity_linking_tasks import (
    link_all_documents_task,
    link_single_document_task,
    post_lexware_import_linking_task,
    generate_linking_statistics_task,
    reprocess_low_confidence_documents_task,
    on_ocr_completed_link_entity,
    on_entity_imported_check_documents,
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
)
from app.workers.tasks.document_tasks import (
    document_bulk_export_task,
    document_reprocess_task,
)
from app.workers.tasks.einvoice_tasks import (
    zugferd_batch_convert_task,
    zugferd_embed_task,
    einvoice_validate_task,
    # H2: ZUGFeRD/XRechnung Enhancement Tasks
    parse_einvoice_task,
    generate_zugferd_task,
    generate_xrechnung_task,
    batch_validate_einvoices_task,
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
from app.workers.tasks.vault_refresh_task import (
    refresh_vault_secrets,
)
from app.workers.tasks.proactive_assistant_tasks import (
    generate_daily_hints_task,
    generate_weekly_optimization_hints_task,
    check_expiring_hints_task,
    send_hint_notifications_task,
    calculate_hint_statistics_task,
)
from app.workers.tasks.ki_pipeline_tasks import (
    process_extraction_confidence_task,
    update_learning_profiles_task,
    run_cross_document_matching_task,
    generate_document_summary_task,
    batch_generate_summaries_task,
    recalculate_confidence_with_learning_task,
    extract_with_confidence_task,
    learn_from_corrections_batch_task,
    detect_cross_doc_discrepancies_task,
    retrain_learning_profiles_task,
    check_price_deviations_task,
)
from app.workers.tasks.annotation_tasks import (
    process_mention_notifications_task,
    check_overdue_comment_tasks_task,
    cleanup_orphaned_annotations_task,
    cleanup_resolved_annotations_task,
)
from app.workers.tasks.smart_dashboard_tasks import (
    refresh_kpis_task,
    calculate_daily_trends_task,
    cleanup_completed_trackers_task,
)
from app.workers.tasks.adhoc_report_tasks import (
    execute_report_async_task,
    export_report_async_task,
    run_scheduled_reports_task,
    send_scheduled_report_email_task,
    cleanup_old_report_exports_task,
)
from app.workers.tasks.approval_enhanced_tasks import (
    check_approval_timeouts_task,
    calculate_approval_sla_task,
    run_auto_matching_task,
    run_batch_auto_matching_task,
    run_auto_filing_task,
)
from app.workers.tasks.approval_escalation_tasks import (
    check_approval_timeouts_task as check_approval_timeouts_extended_task,
    activate_substitutions_task,
    record_sla_metrics_task,
    generate_sla_report_task,
)
from app.workers.tasks.auto_filing_tasks import (
    auto_file_new_documents_task,
    train_filing_model_task,
    auto_match_documents_task,
    batch_match_documents_task,
)
from app.workers.tasks.german_finance_tasks import (
    calculate_monthly_ust_task,
    generate_monthly_bwa_task,
    update_cashflow_forecast_task,
    check_liquidity_warnings_task,
    compare_forecast_accuracy_task,
)
from app.workers.tasks.webhook_inbound_tasks import (
    process_inbound_webhook,
)
from app.workers.tasks.semantic_search_tasks import (
    embed_document_task,
    batch_embed_documents_task,
    reindex_embeddings_task,
)
from app.workers.tasks.approval_tasks import (
    # M2: Approval Matrix Tasks
    check_overdue_approvals_task,
    deactivate_expired_substitutions_task,
    send_approval_reminder_task,
)
from app.workers.tasks.barcode_tasks import (
    detect_barcodes_task,
)
from app.workers.tasks.lifecycle_tasks import (
    daily_retention_scan_task,
    monthly_lifecycle_report_task,
    auto_archive_task,
    destruction_protocol_task,
)
from app.workers.tasks.duplicate_detection_tasks import (
    batch_scan_duplicates_task,
    check_document_duplicates_task,
    cleanup_stale_duplicate_flags_task,
)
from app.workers.tasks.folder_import_rule_tasks import (
    poll_folder_imports_task,
    apply_rules_to_pending_imports_task,
    scan_import_folder_task,
)

# --- Partition Maintenance Tasks (Phase 1.2: Table Partitioning) ---
try:
    from app.workers.tasks.partition_maintenance import (
        ensure_partitions_task,
        archive_old_partitions_task,
        update_partition_stats_task,
        partition_health_check_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

# --- Batch 4: Include-only modules (missing from __init__.py) ---
try:
    from app.workers.tasks.backup_tasks import (
        backup_full_task, backup_postgres_task, backup_redis_task, apply_retention_task,
        sync_to_remote_task, update_backup_metrics_task, archive_audit_logs_monthly_task,
        verify_audit_archives_task, get_audit_archive_statistics_task, backup_restore_test_task,
        get_restore_test_history_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.cleanup_tasks import (
        cleanup_soft_deleted_documents, cleanup_orphaned_files, cleanup_expired_cache,
        cleanup_search_analytics, cleanup_expired_sessions, cleanup_expired_verification_tokens,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.gdpr_tasks import (
        process_deletion_requests, check_retention_compliance, send_breach_notification,
        generate_compliance_report,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.ml_tasks import (
        run_drift_detection, update_ml_metrics, check_experiment_completion,
        trigger_model_retrain, generate_ml_report, check_drift_and_respond,
        generate_monthly_drift_report, apply_ab_test_winners, detect_concept_drift,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.dlq_management_tasks import (
        check_dlq_health, cleanup_old_dlq_tasks, alert_on_critical_dlq_count,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.document_intelligence_tasks import (
        detect_document_groups, batch_detect_groups_by_folder, extract_entities_from_document,
        batch_extract_entities, run_document_intelligence_pipeline, update_intelligence_metrics,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.extraction_tasks import (
        reprocess_all_documents_structured_extraction, reprocess_single_document,
        generate_extraction_stats, quick_classify_document, reprocess_quick_classification,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.rag_tasks import (
        chunk_document, batch_chunk_documents, regenerate_chunk_embeddings,
        run_rag_batch_job, get_rag_statistics, scheduled_chunk_new_documents,
        sync_customer_cards_scheduled,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.monitoring_tasks import (
        worker_health_check_task, cleanup_stuck_tasks, check_queue_backpressure,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.surya_improvement_tasks import (
        run_surya_benchmark, check_surya_retraining_conditions, export_surya_training_dataset,
        run_surya_german_finetuning, evaluate_surya_model, deploy_surya_model,
        evaluate_surya_ab_test, rollback_surya_model, process_surya_corrections,
        update_surya_metrics, generate_surya_improvement_report,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.export_tasks import (
        batch_export_task, check_scheduled_exports, run_scheduled_export_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.privat_tasks import (
        send_deadline_reminders, check_emergency_access_requests, cleanup_expired_access,
        generate_deadline_report, cleanup_orphaned_privat_files, calculate_property_kpis,
        calculate_vehicle_tco, analyze_insurance_coverage, generate_loan_amortization,
        run_finance_analytics, daily_kpi_recalculation, recalculate_property_intelligence,
        recalculate_all_property_intelligence, recalculate_vehicle_intelligence,
        recalculate_all_vehicle_intelligence, recalculate_investment_intelligence,
        calculate_financial_health, generate_smart_recommendations,
        daily_intelligence_recalculation, orchestrate_all_kpis, recalculate_entity_kpi,
        update_privat_metrics, create_monthly_portfolio_snapshot, recalculate_financial_goals,
        check_goals_at_risk, record_kpi_history,
        generate_predictive_alerts as privat_generate_predictive_alerts,
        cleanup_old_projections, get_predictive_insights_summary,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.orchestration_tasks import (
        process_pending_orchestration_actions, emit_system_event,
        check_and_emit_threshold_events, get_orchestration_metrics, cleanup_old_decisions,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.orchestration_extended_tasks import (
        check_entity_health_degradation, apply_health_action, detect_seasonal_patterns,
        process_pending_investigations, start_fraud_investigation,
        escalate_overdue_approvals_extended, assign_deputy_approvers,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.workflow_tasks import (
        execute_workflow_async, execute_workflow_step, check_scheduled_workflows,
        cleanup_old_workflow_executions, process_delayed_step, generate_workflow_report,
        on_document_created, on_document_processed, on_document_failed,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.collaboration_tasks import (
        process_hourly_digests, process_daily_digests, process_weekly_digests,
        check_overdue_tasks, escalate_overdue_tasks, cleanup_old_digest_entries,
        send_task_due_soon_reminders,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.mlops_tasks import (
        check_retraining_threshold, run_retraining, evaluate_model,
        rollback_if_degraded, cleanup_old_versions, get_stats,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.sla_tasks import (
        check_all_slas, send_sla_warning, escalate_overdue_workflows, generate_sla_report,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.liquidity_tasks import (
        check_liquidity_alerts_task, detect_large_outflows_task, generate_liquidity_summary_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.push_notification_tasks import (
        cleanup_expired_push_subscriptions_task, push_subscription_health_check_task,
        cleanup_notification_history_task, generate_push_statistics_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.escalation_tasks import (
        advance_pending_escalations_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

# --- Batch 4: Previously orphaned modules ---
try:
    from app.workers.tasks.ai_conversation_tasks import (
        process_ai_message, execute_ai_action,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.ai_ethics_tasks import (
        generate_bias_report, update_fairness_metrics,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.audit_chain_tasks import (
        verify_integrity, build_merkle_tree,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.banking_tasks import (
        process_bank_import, auto_reconcile, parse_transaction_references,
        update_account_balances, check_overdue_payments, process_automatic_dunning,
        update_cash_flow_forecasts, send_skonto_alerts, cleanup_tan_challenges,
        daily_mahnlauf, reactivate_snoozed_tasks, send_pre_due_reminders,
        check_expired_mahnstopp, generate_dunning_daily_report, fints_sync_all_accounts,
        fints_refresh_balances, execute_pending_sepa_transfers, update_bundesbank_basiszins,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.calendar_sync_task import (
        sync_all_calendars, sync_single_calendar,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.cashflow_prediction_tasks import (
        update_daily_forecast, evaluate_prediction_accuracy, generate_cashflow_alerts,
        warm_forecast_cache, update_entity_profiles, check_liquidity_alerts,
        calculate_daily_forecast_v2,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.ceo_dashboard_tasks import (
        create_daily_snapshot, detect_anomalies,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.chain_intelligence_tasks import (
        scan_chain_gaps_task, detect_orphan_documents_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.compliance_autopilot_tasks import (
        run_daily_scan, prepare_audit_report, run_gdpr_check,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.contract_tasks import (
        send_contract_deadline_reminders_task, check_expiring_contracts_task,
        auto_renew_contracts_task, generate_contract_report_task,
        check_renewal_option_expiry_task, check_overdue_milestones_task,
        check_contract_renewal_deadlines_task, extract_contract_dates_task,
        send_contract_renewal_reminder_task, schedule_contract_reminders_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.contract_v2_tasks import (
        extract_contract_dates_v2_task, check_upcoming_deadlines_v2_task,
        generate_ical_export_task, update_contract_statistics_task,
        check_expired_contracts_v2_task, complete_contract_deadline_task,
        check_auto_renewals_task, link_document_to_contract_task,
        extract_contract_clauses_task, extract_all_contract_clauses_task,
        compare_contract_to_benchmark_task, update_contract_benchmarks_task,
        process_scheduled_cancellations_task, check_cancellation_deadlines_task,
        analyze_contract_costs_task, generate_contract_cost_report_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.customer_detection_tasks import (
        detect_contacts_task, batch_detect_contacts_task, reprocess_all_documents_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.datev_connect_tasks import (
        refresh_all_datev_tokens, sync_datev_stammdaten, sync_all_datev_stammdaten,
        push_datev_buchungsstapel, upload_pending_datev_belege,
        datev_gobd_compliance_check, datev_auto_festschreibung, sync_datev_kontenplan,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.enrichment_tasks import (
        enrich_entity,
        cleanup_expired_cache as enrichment_cleanup_expired_cache,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.erp_sync_tasks import (
        scheduled_sync_all, test_connection, notify_conflicts,
        cleanup_old_history,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.event_sourcing_tasks import (
        create_snapshots, archive_old_events,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.extended_alerts_tasks import (
        check_cashflow_alerts_task, check_contract_alerts_task, check_compliance_alerts_task,
        create_supplier_insolvency_alert_task, create_supplier_ownership_change_alert_task,
        run_all_extended_alerts_checks_task, cleanup_old_extended_alerts_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.gobd_compliance_tasks import (
        verify_audit_chain_task, batch_integrity_check_task,
        generate_chain_statistics_task as gobd_generate_chain_statistics_task,
        check_retention_warnings_task, check_breach_deadlines_task, daily_breach_report_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.hygiene_tasks import (
        run_full_hygiene_scan, check_entity_after_document, auto_apply_corrections,
        check_inactive_entities,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.import_tasks import (
        retry_import_task, cleanup_old_import_logs, reset_daily_folder_stats,
        check_email_connection_health,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.knowledge_graph_tasks import (
        build_graph_incremental,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.lexware_sync_tasks import (
        sync_customers_task, sync_suppliers_task, sync_invoices_task, full_sync_task,
        process_offline_queue_task, handle_webhook_task, sync_single_customer_task,
        sync_single_supplier_task, update_payment_status_task, push_entity_to_lexware_task,
        sync_all_entities, health_check_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.life_event_tasks import (
        detect_life_events,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.nlq_tasks import (
        cleanup_old_logs as nlq_cleanup_old_logs,
        warm_cache as nlq_warm_cache,
        analyze_query_patterns, retry_failed_queries,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.ocr_template_tasks import (
        scan_template_candidates_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.odoo_tasks import (
        push_all_risk_scores, retry_failed_syncs,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.shipment_tasks import (
        refresh_active_shipments, refresh_single_shipment, check_delayed_shipments,
        generate_shipment_statistics,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.smart_inbox_tasks import (
        aggregate_inbox_items, recalculate_priorities, train_behavior_model,
        cleanup_completed_items,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.tax_package_tasks import (
        generate_monthly_packages, generate_quarterly_packages, auto_send_ready_packages,
        send_missing_documents_reminders, cleanup_expired_packages, generate_datev_for_package,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.template_tasks import (
        render_template_batch, render_template_single, cleanup_temp_files,
        cleanup_old_template_versions, collect_template_stats,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.thumbnail_tasks import (
        generate_thumbnail_task, batch_generate_thumbnails_task, regenerate_missing_thumbnails_task,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

try:
    from app.workers.tasks.zero_touch_tasks import (
        process_document_zero_touch, process_pending_documents, recalculate_thresholds,
        generate_zero_touch_statistics,
    )
except ImportError as _exc:
    _import_logger.warning("Optional task module nicht geladen: %s", _exc)

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
    # Entity Linking tasks
    "link_all_documents_task",
    "link_single_document_task",
    "post_lexware_import_linking_task",
    "generate_linking_statistics_task",
    "reprocess_low_confidence_documents_task",
    "on_ocr_completed_link_entity",
    "on_entity_imported_check_documents",
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
    # Document tasks
    "document_bulk_export_task",
    "document_reprocess_task",
    # E-Invoice tasks
    "zugferd_batch_convert_task",
    "zugferd_embed_task",
    "einvoice_validate_task",
    # H2: ZUGFeRD/XRechnung Enhancement Tasks
    "parse_einvoice_task",
    "generate_zugferd_task",
    "generate_xrechnung_task",
    "batch_validate_einvoices_task",
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
    # Vault tasks
    "refresh_vault_secrets",
    # Proactive Assistant tasks
    "generate_daily_hints_task",
    "generate_weekly_optimization_hints_task",
    "check_expiring_hints_task",
    "send_hint_notifications_task",
    "calculate_hint_statistics_task",
    # KI-Pipeline tasks
    "process_extraction_confidence_task",
    "update_learning_profiles_task",
    "run_cross_document_matching_task",
    "generate_document_summary_task",
    "batch_generate_summaries_task",
    "recalculate_confidence_with_learning_task",
    "extract_with_confidence_task",
    "learn_from_corrections_batch_task",
    "detect_cross_doc_discrepancies_task",
    "retrain_learning_profiles_task",
    "check_price_deviations_task",
    # Annotation tasks
    "process_mention_notifications_task",
    "check_overdue_comment_tasks_task",
    "cleanup_orphaned_annotations_task",
    "cleanup_resolved_annotations_task",
    # Smart Dashboard tasks
    "refresh_kpis_task",
    "calculate_daily_trends_task",
    "cleanup_completed_trackers_task",
    # Ad-Hoc Reporting tasks
    "execute_report_async_task",
    "export_report_async_task",
    "run_scheduled_reports_task",
    "send_scheduled_report_email_task",
    "cleanup_old_report_exports_task",
    # Approval Enhanced + Automation 2.0 tasks
    "check_approval_timeouts_task",
    "calculate_approval_sla_task",
    "run_auto_matching_task",
    "run_batch_auto_matching_task",
    "run_auto_filing_task",
    # Approval Escalation & SLA tasks (Feature #3)
    "check_approval_timeouts_extended_task",
    "activate_substitutions_task",
    "record_sla_metrics_task",
    "generate_sla_report_task",
    # Auto-Filing & Auto-Matching tasks (Feature #7)
    "auto_file_new_documents_task",
    "train_filing_model_task",
    "auto_match_documents_task",
    "batch_match_documents_task",
    # Deutsche Finanz-Feature tasks (Feature #11)
    "calculate_monthly_ust_task",
    "generate_monthly_bwa_task",
    "update_cashflow_forecast_task",
    "check_liquidity_warnings_task",
    "compare_forecast_accuracy_task",
    # Inbound Webhook tasks
    "process_inbound_webhook",
    # Semantic Search tasks
    "embed_document_task",
    "batch_embed_documents_task",
    "reindex_embeddings_task",
    # M2: Approval Matrix Tasks
    "check_overdue_approvals_task",
    "deactivate_expired_substitutions_task",
    "send_approval_reminder_task",
    # M5: Barcode Detection tasks (Batch 1 gap)
    "detect_barcodes_task",
    # M1: Lifecycle tasks (Batch 1 gap)
    "daily_retention_scan_task",
    "monthly_lifecycle_report_task",
    "auto_archive_task",
    "destruction_protocol_task",
    # Phase 4.1: Duplicate Detection tasks
    "batch_scan_duplicates_task",
    "check_document_duplicates_task",
    "cleanup_stale_duplicate_flags_task",
    # Phase 3.1: Folder Import Rule tasks
    "poll_folder_imports_task",
    "apply_rules_to_pending_imports_task",
    "scan_import_folder_task",
    # Phase 1.2: Partition Maintenance tasks
    "ensure_partitions_task",
    "archive_old_partitions_task",
    "update_partition_stats_task",
    "partition_health_check_task",
    # Batch 4: Include-only modules (Group B)
    # Backup tasks
    "backup_full_task",
    "backup_postgres_task",
    "backup_redis_task",
    "apply_retention_task",
    "sync_to_remote_task",
    "update_backup_metrics_task",
    "archive_audit_logs_monthly_task",
    "verify_audit_archives_task",
    "get_audit_archive_statistics_task",
    "backup_restore_test_task",
    "get_restore_test_history_task",
    # Cleanup tasks
    "cleanup_soft_deleted_documents",
    "cleanup_orphaned_files",
    "cleanup_expired_cache",
    "cleanup_search_analytics",
    "cleanup_expired_sessions",
    "cleanup_expired_verification_tokens",
    # GDPR tasks
    "process_deletion_requests",
    "check_retention_compliance",
    "send_breach_notification",
    "generate_compliance_report",
    # ML tasks
    "run_drift_detection",
    "update_ml_metrics",
    "check_experiment_completion",
    "trigger_model_retrain",
    "generate_ml_report",
    "check_drift_and_respond",
    "generate_monthly_drift_report",
    "apply_ab_test_winners",
    "detect_concept_drift",
    # DLQ Management tasks
    "check_dlq_health",
    "cleanup_old_dlq_tasks",
    "alert_on_critical_dlq_count",
    # Document Intelligence tasks
    "detect_document_groups",
    "batch_detect_groups_by_folder",
    "extract_entities_from_document",
    "batch_extract_entities",
    "run_document_intelligence_pipeline",
    "update_intelligence_metrics",
    # Extraction tasks
    "reprocess_all_documents_structured_extraction",
    "reprocess_single_document",
    "generate_extraction_stats",
    "quick_classify_document",
    "reprocess_quick_classification",
    # RAG tasks
    "chunk_document",
    "batch_chunk_documents",
    "regenerate_chunk_embeddings",
    "run_rag_batch_job",
    "get_rag_statistics",
    "scheduled_chunk_new_documents",
    "sync_customer_cards_scheduled",
    # Monitoring tasks
    "worker_health_check_task",
    "cleanup_stuck_tasks",
    "check_queue_backpressure",
    # Surya Improvement tasks
    "run_surya_benchmark",
    "check_surya_retraining_conditions",
    "export_surya_training_dataset",
    "run_surya_german_finetuning",
    "evaluate_surya_model",
    "deploy_surya_model",
    "evaluate_surya_ab_test",
    "rollback_surya_model",
    "process_surya_corrections",
    "update_surya_metrics",
    "generate_surya_improvement_report",
    # Export tasks
    "batch_export_task",
    "check_scheduled_exports",
    "run_scheduled_export_task",
    # Privat tasks
    "send_deadline_reminders",
    "check_emergency_access_requests",
    "cleanup_expired_access",
    "generate_deadline_report",
    "cleanup_orphaned_privat_files",
    "calculate_property_kpis",
    "calculate_vehicle_tco",
    "analyze_insurance_coverage",
    "generate_loan_amortization",
    "run_finance_analytics",
    "daily_kpi_recalculation",
    "recalculate_property_intelligence",
    "recalculate_all_property_intelligence",
    "recalculate_vehicle_intelligence",
    "recalculate_all_vehicle_intelligence",
    "recalculate_investment_intelligence",
    "calculate_financial_health",
    "generate_smart_recommendations",
    "daily_intelligence_recalculation",
    "orchestrate_all_kpis",
    "recalculate_entity_kpi",
    "update_privat_metrics",
    "create_monthly_portfolio_snapshot",
    "recalculate_financial_goals",
    "check_goals_at_risk",
    "record_kpi_history",
    "privat_generate_predictive_alerts",
    "cleanup_old_projections",
    "get_predictive_insights_summary",
    # Orchestration tasks
    "process_pending_orchestration_actions",
    "emit_system_event",
    "check_and_emit_threshold_events",
    "get_orchestration_metrics",
    "cleanup_old_decisions",
    # Orchestration Extended tasks
    "check_entity_health_degradation",
    "apply_health_action",
    "detect_seasonal_patterns",
    "process_pending_investigations",
    "start_fraud_investigation",
    "escalate_overdue_approvals_extended",
    "assign_deputy_approvers",
    # Workflow tasks
    "execute_workflow_async",
    "execute_workflow_step",
    "check_scheduled_workflows",
    "cleanup_old_workflow_executions",
    "process_delayed_step",
    "generate_workflow_report",
    "on_document_created",
    "on_document_processed",
    "on_document_failed",
    # Collaboration tasks
    "process_hourly_digests",
    "process_daily_digests",
    "process_weekly_digests",
    "check_overdue_tasks",
    "escalate_overdue_tasks",
    "cleanup_old_digest_entries",
    "send_task_due_soon_reminders",
    # MLOps tasks
    "check_retraining_threshold",
    "run_retraining",
    "evaluate_model",
    "rollback_if_degraded",
    "cleanup_old_versions",
    "get_stats",
    # SLA tasks
    "check_all_slas",
    "send_sla_warning",
    "escalate_overdue_workflows",
    "generate_sla_report",
    # Liquidity tasks
    "check_liquidity_alerts_task",
    "detect_large_outflows_task",
    "generate_liquidity_summary_task",
    # Push Notification tasks
    "cleanup_expired_push_subscriptions_task",
    "push_subscription_health_check_task",
    "cleanup_notification_history_task",
    "generate_push_statistics_task",
    # Escalation tasks
    "advance_pending_escalations_task",
    # Batch 4: Previously orphaned modules (Group A)
    # AI Conversation tasks
    "process_ai_message",
    "execute_ai_action",
    # AI Ethics tasks
    "generate_bias_report",
    "update_fairness_metrics",
    # Audit Chain tasks
    "verify_integrity",
    "build_merkle_tree",
    # Banking tasks
    "process_bank_import",
    "auto_reconcile",
    "parse_transaction_references",
    "update_account_balances",
    "check_overdue_payments",
    "process_automatic_dunning",
    "update_cash_flow_forecasts",
    "send_skonto_alerts",
    "cleanup_tan_challenges",
    "daily_mahnlauf",
    "reactivate_snoozed_tasks",
    "send_pre_due_reminders",
    "check_expired_mahnstopp",
    "generate_dunning_daily_report",
    "fints_sync_all_accounts",
    "fints_refresh_balances",
    "execute_pending_sepa_transfers",
    "update_bundesbank_basiszins",
    # Calendar Sync tasks
    "sync_all_calendars",
    "sync_single_calendar",
    # Cashflow Prediction tasks
    "update_daily_forecast",
    "evaluate_prediction_accuracy",
    "generate_cashflow_alerts",
    "warm_forecast_cache",
    "update_entity_profiles",
    "check_liquidity_alerts",
    "calculate_daily_forecast_v2",
    # CEO Dashboard tasks
    "create_daily_snapshot",
    "detect_anomalies",
    # Chain Intelligence tasks
    "scan_chain_gaps_task",
    "detect_orphan_documents_task",
    # Compliance Autopilot tasks
    "run_daily_scan",
    "prepare_audit_report",
    "run_gdpr_check",
    # Contract tasks
    "send_contract_deadline_reminders_task",
    "check_expiring_contracts_task",
    "auto_renew_contracts_task",
    "generate_contract_report_task",
    "check_renewal_option_expiry_task",
    "check_overdue_milestones_task",
    "check_contract_renewal_deadlines_task",
    "extract_contract_dates_task",
    "send_contract_renewal_reminder_task",
    "schedule_contract_reminders_task",
    # Contract V2 tasks
    "extract_contract_dates_v2_task",
    "check_upcoming_deadlines_v2_task",
    "generate_ical_export_task",
    "update_contract_statistics_task",
    "check_expired_contracts_v2_task",
    "complete_contract_deadline_task",
    "check_auto_renewals_task",
    "link_document_to_contract_task",
    "extract_contract_clauses_task",
    "extract_all_contract_clauses_task",
    "compare_contract_to_benchmark_task",
    "update_contract_benchmarks_task",
    "process_scheduled_cancellations_task",
    "check_cancellation_deadlines_task",
    "analyze_contract_costs_task",
    "generate_contract_cost_report_task",
    # Customer Detection tasks
    "detect_contacts_task",
    "batch_detect_contacts_task",
    "reprocess_all_documents_task",
    # DATEV Connect tasks
    "refresh_all_datev_tokens",
    "sync_datev_stammdaten",
    "sync_all_datev_stammdaten",
    "push_datev_buchungsstapel",
    "upload_pending_datev_belege",
    "datev_gobd_compliance_check",
    "datev_auto_festschreibung",
    "sync_datev_kontenplan",
    # Enrichment tasks
    "enrich_entity",
    "enrichment_cleanup_expired_cache",
    # ERP Sync tasks
    "scheduled_sync_all",
    "test_connection",
    "notify_conflicts",
    "cleanup_old_history",
    # Event Sourcing tasks
    "create_snapshots",
    "archive_old_events",
    # Extended Alerts tasks
    "check_cashflow_alerts_task",
    "check_contract_alerts_task",
    "check_compliance_alerts_task",
    "create_supplier_insolvency_alert_task",
    "create_supplier_ownership_change_alert_task",
    "run_all_extended_alerts_checks_task",
    "cleanup_old_extended_alerts_task",
    # GoBD Compliance tasks
    "verify_audit_chain_task",
    "batch_integrity_check_task",
    "gobd_generate_chain_statistics_task",
    "check_retention_warnings_task",
    "check_breach_deadlines_task",
    "daily_breach_report_task",
    # Hygiene tasks
    "run_full_hygiene_scan",
    "check_entity_after_document",
    "auto_apply_corrections",
    "check_inactive_entities",
    # Import tasks
    "retry_import_task",
    "cleanup_old_import_logs",
    "reset_daily_folder_stats",
    "check_email_connection_health",
    # Knowledge Graph tasks
    "build_graph_incremental",
    # Lexware Sync tasks
    "sync_customers_task",
    "sync_suppliers_task",
    "sync_invoices_task",
    "full_sync_task",
    "process_offline_queue_task",
    "handle_webhook_task",
    "sync_single_customer_task",
    "sync_single_supplier_task",
    "update_payment_status_task",
    "push_entity_to_lexware_task",
    "sync_all_entities",
    "health_check_task",
    # Life Event tasks
    "detect_life_events",
    # NLQ tasks
    "nlq_cleanup_old_logs",
    "nlq_warm_cache",
    "analyze_query_patterns",
    "retry_failed_queries",
    # OCR Template tasks
    "scan_template_candidates_task",
    # Odoo tasks
    "push_all_risk_scores",
    "retry_failed_syncs",
    # Shipment tasks
    "refresh_active_shipments",
    "refresh_single_shipment",
    "check_delayed_shipments",
    "generate_shipment_statistics",
    # Smart Inbox tasks
    "aggregate_inbox_items",
    "recalculate_priorities",
    "train_behavior_model",
    "cleanup_completed_items",
    # Tax Package tasks
    "generate_monthly_packages",
    "generate_quarterly_packages",
    "auto_send_ready_packages",
    "send_missing_documents_reminders",
    "cleanup_expired_packages",
    "generate_datev_for_package",
    # Template tasks
    "render_template_batch",
    "render_template_single",
    "cleanup_temp_files",
    "cleanup_old_template_versions",
    "collect_template_stats",
    # Thumbnail tasks
    "generate_thumbnail_task",
    "batch_generate_thumbnails_task",
    "regenerate_missing_thumbnails_task",
    # Zero Touch tasks
    "process_document_zero_touch",
    "process_pending_documents",
    "recalculate_thresholds",
    "generate_zero_touch_statistics",
]
