# F-31 Rest-Roadmap (offene GET-500-Endpunkte, Design-abhaengig)

Stand 2026-06-19. Die systematischen Cluster (Company-Resolution, role, enum, date_trunc,
Company-Objekt .id, diverse AttributeErrors) sind gefixt (192 -> ~Restzahl). Der hier
dokumentierte Rest erfordert per-case-/Designarbeit (KEINE mechanischen Codemods) und ist
aus 5 parallelen Read-only-Investigations-Agents praezise belegt.

## A) Echte Feature-Luecken (Service-Methode fehlt -> konservativ: 501 ODER minimaler Stub)
- /banking/enhanced/reconciliation/pending, /aggregated/balance, /aggregated/transactions:
  EnhancedFinTSService.get_pending_reconciliations / get_aggregated_balance / get_aggregated_transactions FEHLEN.
- /financial-insights/fraud/alerts (FraudEarlyWarningService.get_alerts fehlt),
  /skonto/recommendations (SkontoOptimizer.get_recommendations fehlt).
- /contracts/benchmarks/categories (ContractBenchmarkService.get_available_categories fehlt),
  /contracts/costs/optimization (get_all_optimization_suggestions fehlt).
- /handelsregister/monitoring/status,/alerts,/entities (Service-Methoden fehlen).
- /xai/stats (DecisionExplainer.get_stats fehlt), /daily-insights/config (get_generator_configs fehlt),
  /zero-touch/pending-review (get_pending_reviews fehlt), /orchestration/insights/stats (get_statistics fehlt).
- /process-mining/flow-diagram (discover_process fehlt), /variants (get_variants fehlt; vorhanden: discover_process_variants).
- /routing/model/info (RoutingPredictor model_version/last_trained/... Attribute fehlen).

## B) Router<->Service-Datenvertrag veraltet (Dict-Subscript auf Dataclass) -> Response-Mapping neu
- /financial-insights/cashflow/predict, /fraud/scan, /skonto/optimize, /summary:
  Services liefern Dataclasses (CashflowPrediction/FraudScanResult/OptimizationResult), Router subskribiert dict-artig
  mit veralteten Keys. Response-Mapping auf reale Dataclass-Felder umschreiben (oder Schemas anpassen).
- /orchestration/insights/rules: InsightRule-Dataclass hat rule_id/entity_types/condition/generate; Endpoint erwartet
  name/description/entity_type/insight_type/priority/is_enabled. _rule_engine._rules nutzen + Mapping anpassen.
- /log-analytics/dashboard: Service-Dict-Keys != DashboardDataResponse (metric->metric_name, current/previous_value, error/warning_count).

## C) Saubere Signatur-/Rename-Fixes (noch offen, exakt belegt)
- finance/liquidity/forecast|bottlenecks|waterfall|anomalies (app/api/v1/finance.py): Handler `user_id=`-kwarg +
  `company_id=getattr(current_user,'company_id',None)`; Fix: Param `company_id: UUID = Depends(get_user_company_id_dep)` +
  Aufruf auf `company_id=company_id` umstellen (user_id-kwarg entfernen). 4 Endpunkte, ein Muster.
- /admin/extraction/stats (admin/extraction.py:240-250): asyncio.new_event_loop im async-Handler -> await _async_generate_stats().
- /admin/roles: permission_service.py:511 selectinload(Role.users) [erledigt].
- /banking/settings/auto-dunning + /dunning-stages (routes.py:3121/2976): company_id=company_id -> current_user.id;
  dunning_stage_service: DunningStageConfig.company_id -> user_id.
- /banking/mahn-tasks/summary (mahn_task_service.py:213): Dict-Keys an MahnTaskSummary-Schema angleichen.
- /banking/payment-automation/schedule+statistics (routes.py:3948/3986): Response-Aufbau auf reale
  PaymentSchedule.entries / stats-Keys (skonto-statistics) umschreiben.
- /calendar-sync/export.ics + /preview: CalendarService.get_all_deadlines(start_date/end_date) statt get_deadlines/days_ahead.
- /bpmn/tasks: TaskService.get_user_tasks -> selectinload(ProcessTask.instance).
- /smart-escalation/recommend: func.cast(..., Integer=False) -> cast(..., Integer) (import cast); team-workload:
  ValidationQueueItem-Import pruefen (Modell aus models_ocr_validation hat reviewed_by_id; ein abweichendes Modell ist Ursache).
- /entities/cross-company: all_companies vor die Schleife hochziehen (UnboundLocalError).
- /groups + /groups/queue/review: DocumentGroupListResponse(groups=...) / ValidationQueueResponse(total_pending/groups_pending/relationships_pending).
- /privat/life-events(+stats): current_user["id"]/["company_id"] -> current_user.id + get_user_company_id_dep.
- /privacy/budget: Helper get_company_id(user) -> (db,user) mit get_user_company_id.
- /steuerberater/packages: service.list_packages(company_id,status) ohne db/page-kwargs; total=len(packages).
- /dashboard-widgets/cash-flow-forecast(+chart): cash_flow_forecast_service _get_current_balance ueber BankAccount-Join (company_id) statt BankTransaction.user_id/is_deleted.
- /templates: TemplateEngineService mkdir in try/except OSError.
- /notifications/system: NotificationType aus app.db.models_entity_business importieren (Alias-Kollision models.py:1418).
- /dashboards: Raw-SQL "SELECT role FROM users" -> Rollenquelle/RBAC (kurzfristig user_role="viewer" defaulten).

## D) SHARED-FILE (separat reviewen)
- CrossDBJSON (models_base.py): impl=JSON -> .astext/.contains() JSONB-untauglich; betrifft digital-twin + extracted_data/export.
  Konservativ pro-Endpoint: cast(col, JSONB). Breit: CrossDBJSON.impl=JSONB.
- models_entity_business.py: ContractStatus ohne values_callable (lowercase DB-Labels) -> InvalidTextRepresentation
  (contracts/summary,deadlines). Fix: SQLAlchemyEnum(ContractStatus, values_callable=lambda e:[m.value for m in e]).
- core/redis_state.py: get_client()-Methode fehlt (nlq/* x4).
