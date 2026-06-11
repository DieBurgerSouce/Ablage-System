# Archivierte Tests & entfernte Stub-Tests

Dieser Ordner enthaelt aus der aktiven Suite entfernte Tests. Er wird von
pytest mitgesammelt, sofern Dateien dem `test_*.py`-Muster folgen — neue
Ablagen hier daher bewusst NICHT nach diesem Muster benennen oder mit
Modul-Level-Skip versehen.

## Bestand

- `e2e/`, `e2e-complete/`: historische E2E-Versuche (CI-verwaist)
- `manual/`: manuelle Debug-Skripte

## Entfernte Stub-Tests (W1-042, 2026-06-12, Branch fix/w2-tests)

62 Test-Stubs mit `@pytest.mark.skip(reason="stub - nicht implementiert")`
und leerem `pass`-Koerper wurden aus der aktiven Suite GELOESCHT (nicht
verschoben — es gab keinen Testcode, nur Absichts-Deklarationen). Sie
blaehten die Skip-Statistik auf und suggerierten Coverage, die nie existierte.

Wer eines dieser Szenarien implementieren will, findet die vollstaendige
Liste hier (Datei -> Klasse::Test):

### tests/unit/api/ (59)

- test_agents_api.py: TestAgentExecuteRequestValidation::test_valid_request, TestBatchProcessRequestValidation::test_valid_batch_request
- test_ai_conversations_api.py: TestListConversations::test_filter_by_is_starred, TestListConversations::test_filter_by_is_active, TestListConversations::test_search_in_title, TestGetConversationBySession::test_returns_404_if_not_found
- test_api_keys.py: TestAPIKeyPermissions::test_admin_permission_grants_all, TestAPIKeySecurity::test_full_key_never_stored
- test_communication_hub_api.py (15): TestMultiTenantSecurity::test_403_when_no_company_selected, TestMultiTenantSecurity::test_validates_entity_belongs_to_company, TestInputValidation::test_validates_timeline_limit_range, TestInputValidation::test_validates_documents_limit_range, TestInputValidation::test_validates_sections_format, TestPhoneNoteCRUD::test_create_phone_note_validates_call_type, TestPhoneNoteCRUD::test_create_phone_note_validates_direction, TestPhoneNoteCRUD::test_update_phone_note_requires_ownership, TestPhoneNoteCRUD::test_delete_phone_note_requires_ownership, TestResponseFormat::test_hub_response_contains_all_sections, TestResponseFormat::test_timeline_items_have_required_fields, TestResponseFormat::test_decimal_amounts_serialized_as_float, TestErrorResponses::test_entity_not_found_returns_empty_hub, TestErrorResponses::test_partial_failure_still_returns_data, TestErrorResponses::test_error_messages_are_german
- test_favorites.py: TestRemoveFavorite::test_remove_favorite_success, TestRemoveFavorite::test_remove_favorite_not_found, TestUpdateFavorite::test_update_favorite_note, TestUpdateFavorite::test_update_favorite_priority
- test_gdpr.py: TestGDPRSecurity::test_user_can_only_access_own_data
- test_holding_api.py: TestHoldingAPI::test_compare_companies_invalid_metric
- test_partial_payment_api.py (15): TestRecordPartialPayment::test_record_payment_sets_is_partial_payment_flag, TestRecordPartialPayment::test_record_payment_optional_notes, TestRecordPartialPayment::test_record_payment_default_date_is_now, TestRecordPartialPayment::test_record_payment_triggers_risk_recalc, TestRecordPartialPayment::test_record_payment_not_found_raises_404, TestRecordPartialPayment::test_record_payment_no_company_raises_400, TestGetInvoicePayments::test_get_payments_not_found_raises_404, TestDeletePartialPayment::test_delete_payment_triggers_risk_recalc, TestDeletePartialPayment::test_delete_payment_not_found_raises_400, TestDeletePartialPayment::test_delete_payment_invoice_not_found_raises_404, TestPaymentMultiTenantSecurity::test_record_payment_checks_document_owner, TestPaymentMultiTenantSecurity::test_get_payments_checks_document_owner, TestPaymentMultiTenantSecurity::test_delete_payment_checks_document_owner, TestPaymentGermanErrorMessages::test_delete_error_message_is_german, TestPaymentEdgeCases::test_delete_last_payment_resets_status
- test_predictive_cashflow_api.py: TestPredictiveCashFlowAPI::test_get_liquidity_forecast_days_validation
- test_skonto_api.py (11): TestGetInvoiceSkonto::test_get_skonto_not_found_raises_404, TestSetInvoiceSkonto::test_set_skonto_not_found_raises_404, TestApplyInvoiceSkonto::test_apply_skonto_with_force_apply, TestApplyInvoiceSkonto::test_apply_skonto_sets_skonto_used, TestApplyInvoiceSkonto::test_apply_skonto_sets_status_paid, TestApplyInvoiceSkonto::test_apply_skonto_triggers_risk_recalc, TestApplyInvoiceSkonto::test_apply_skonto_not_found_raises_404, TestUpcomingSkontoDeadlines::test_upcoming_returns_sorted_by_urgency, TestSkontoMultiTenantSecurity::test_get_skonto_checks_document_owner, TestSkontoMultiTenantSecurity::test_set_skonto_checks_document_owner, TestSkontoMultiTenantSecurity::test_apply_skonto_checks_document_owner
- test_tunes.py: TestTunesGermanLocalization::test_error_messages_are_german

### sonstige (5)

- tests/unit/services/banking/test_reconciliation_service.py: TestMatchingStrategies::test_confidence_hierarchy, TestConfidenceCalculation::test_date_proximity_calculation
- tests/unit/test_safe_module_loader.py: TestBPMNRegistrationLock::test_registration_starts_unlocked
- tests/unit/workers/test_celery_app.py: TestGPUMemoryManagement::test_clear_gpu_cache_called_after_task, TestGPUMemoryManagement::test_gpu_oom_detection

Hinweis: Mehrere Stubs betrafen Multi-Tenant-/Ownership-Checks (skonto,
partial_payment, communication_hub). Diese Szenarien sind sicherheitsrelevant
und sollten bei der naechsten Tenant-Haertungswelle (W1-014) als ECHTE Tests
implementiert werden.
