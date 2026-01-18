# Known Issues

## Active Issues

### MEDIUM: Fehlende Models

| Issue | Beschreibung |
|-------|--------------|
| **BusinessContact Model fehlt** | `app/api/v1/business_contacts.py` importiert `BusinessContact` aus `app/db/models`, aber das Model existiert NICHT in `models.py`. API-Start koennte fehlschlagen. |

### Design-Hinweise (kein Bug)

| Service | Hinweis |
|---------|---------|
| **EmailSenderMatcherService** | Kein `company_id` Filter - aber BusinessEntity ist absichtlich firmenuebergreifend (`company_presence` JSONB) |
| **duplicate_detection_service** | `company_id` ist optional, aber bei Verwendung korrekt gefiltert |
| **Banking System (user_id Design)** | Gesamtes Banking-Modul nutzt `user_id` statt `company_id` - BankAccount, BankTransaction, DunningRecord sind User-spezifisch, NICHT Company-shared. Fuer Szenarien mit geteiltem Buchhaltungsteam waere Migration auf `company_id` noetig. |
| **DunningService Document-Zugriff** | Nutzt `Document.owner_id == user_id` statt `company_id` - limitiert Cross-User-Sichtbarkeit innerhalb derselben Company |
| **ReconciliationService Document-Zugriff** | `manual_match()` und `split_transaction()` nutzen `Document.owner_id` statt `company_id` |
| **ValidationRule/ValidationSampleConfig** | Beide Models haben KEIN `company_id` - sind absichtlich System-wide Konfigurationen. Fuer echte Multi-Tenant Deployment waere Migration noetig. |

## Notes

- **MultiStepForm SessionStorage**: Fix applied for QuotaExceededError in privacy mode/large forms
- **Banking Reconciliation**: Match suggestion UI ready for backend integration

## Resolved

| Date | Issue | Fix |
|------|-------|-----|
| 2026-01-10 | MultiStepForm SessionStorage QuotaExceededError in privacy mode | Added 500KB limit check, auto-cleanup, and synchronous persistKey tracking in MultiStepForm.tsx |
| 2026-01-10 | N+1 queries in entity list endpoints causing slow page loads | Removed folder stats calculation from list endpoints, load on-demand via `/{entity_id}/folders` |
| 2026-01-10 | Entity API authentication failing with 401 errors | Added `credentials: "include"` to all fetch calls in ablage-api.ts (commit 25542547) |
| 2026-01-10 | FastAPI route ordering causing 403/422 for `/customers`, `/suppliers` | Moved static routes before dynamic `/{entity_id}` route (commit 665ca1cc) |
| 2026-01-18 | **CRITICAL** WorkflowTriggerService Multi-Tenant Bug | `_find_matching_workflows()` hat NICHT nach `company_id` gefiltert - Cross-Tenant Workflow-Trigger war moeglich | Fixed: company_id Parameter hinzugefuegt, Document wird zuerst geladen fuer company_id |
| 2026-01-18 | **CRITICAL** WorkflowTriggerService Webhook Bug | `_find_workflow_by_webhook_path()` und `handle_webhook()` hatten keine company_id Validierung | Fixed: company_id Filter und Validierung hinzugefuegt, Workflows ohne company_id werden abgelehnt |
| 2026-01-18 | **CRITICAL** WorkflowExecutionService Multi-Tenant Bug | `start_execution()` hat Workflow nur nach ID geladen, KEINE company_id Validierung | Fixed: company_id Parameter und Validierung hinzugefuegt mit Security-Logging |
| 2026-01-18 | **CRITICAL** WorkflowService Multi-Tenant Bug | `get_workflow()`, `update_workflow()`, `delete_workflow()`, `duplicate_workflow()`, `toggle_workflow()`, `validate_workflow()`, `get_workflow_stats()` hatten KEINE company_id Validierung | Fixed: company_id Parameter zu allen Methoden hinzugefuegt, API-Endpoints nutzen jetzt `get_user_company_id()` |
| 2026-01-18 | **CRITICAL** WorkflowTriggerService Manual Trigger Bug | `trigger_workflow_manually()`, `_get_workflow()`, `get_webhook_config()`, `regenerate_webhook_secret()` hatten KEINE company_id Validierung | Fixed: company_id Parameter durchgehend hinzugefuegt |
| 2026-01-18 | **CRITICAL** WorkflowExecutionService Multi-Tenant Luecken | `list_executions()`, `get_step_executions()`, `pause/resume/cancel/retry_execution()`, `_get_execution()` hatten KEINE company_id Validierung | Fixed: company_id Parameter zu allen Methoden, Subquery-Filter, Cross-Tenant Security-Logging |
| 2026-01-18 | **CRITICAL** WorkflowTriggerService Scheduled Workflows Bug | `check_scheduled_workflows()` hat ALLE Workflows aller Companies ausgefuehrt | Fixed: company_id.isnot(None) Filter, company_id wird an ExecutionService weitergegeben |
| 2026-01-18 | **CRITICAL** Workflow API Endpoints Multi-Tenant Luecken | 7 Execution-Endpoints (get_workflow_executions, get_execution, get_step_executions, pause, resume, cancel, retry) haben company_id NICHT an Service weitergegeben | Fixed: Alle Endpoints rufen jetzt get_user_company_id() auf und reichen company_id an Services |
| 2026-01-18 | **CRITICAL** instantiate_template() IDOR-Vulnerability | company_id wurde aus Request-Body (data.company_id) genommen - Angreifer konnte Workflow in fremde Company erstellen | Fixed: company_id wird aus User-Context geholt (IDOR Prevention) |
| 2026-01-18 | **CRITICAL** Statistics Endpoints Multi-Tenant Luecken | `get_overview_stats()` und `get_execution_history()` filterten nur nach user_id, NICHT company_id | Fixed: Workflow-Subquery mit company_id Filter fuer alle Execution-Abfragen |
| 2026-01-18 | **CRITICAL** TriggerService company_id Propagation | `on_document_event()` und `handle_webhook()` haben `start_execution()` OHNE company_id aufgerufen | Fixed: company_id aus Document bzw. Workflow wird jetzt an ExecutionService weitergegeben |
| 2026-01-18 | **CRITICAL** Step-Endpoints Multi-Tenant Luecken | 6 Step-Endpoints (get_workflow_steps, create_step, update_step, delete_step, reorder_steps, batch_update_steps) haben `get_workflow()` OHNE company_id aufgerufen | Fixed: Alle Endpoints rufen jetzt `get_user_company_id()` auf, company_id wird an Service-Methoden weitergegeben |
| 2026-01-18 | **CRITICAL** Template-Endpoints Multi-Tenant Luecken | `list_templates()` und `get_template()` hatten KEINE company_id Validierung | Fixed: company_id Filter hinzugefuegt, Templates sind entweder company-spezifisch oder global (NULL) |
| 2026-01-18 | **CRITICAL** ExecutionContext fehlte company_id | `ExecutionContext` Dataclass hatte KEIN `company_id` Feld - StepExecutor konnte keine Multi-Tenant Validierung durchfuehren | Fixed: company_id Feld hinzugefuegt, wird aus Workflow gesetzt bei start_execution() und resume_execution() |
| 2026-01-18 | **CRITICAL** WorkflowStepExecutor Cross-Tenant Document Actions | 10 Document-Actions (move_folder, assign_tags, assign_document_type, update_status, delete_document, assign_user, start_ocr, ai_categorization, export_document, duplicate_check) haben KEINE company_id Validierung durchgefuehrt - Cross-Tenant Document-Modifikation war moeglich | Fixed: `_validate_document_company()` Helper-Methode hinzugefuegt, alle Document-Actions validieren jetzt company_id vor Ausfuehrung |
| 2026-01-18 | **CRITICAL** EscalationService Multi-Tenant Bug | `get_rule()`, `update_rule()`, `delete_rule()` hatten KEINE company_id Validierung | Fixed: company_id Parameter zu allen 3 Methoden hinzugefuegt mit Security-Logging bei fehlgeschlagenen Zugriffen |
| 2026-01-18 | **CRITICAL** ApprovalRuleService Multi-Tenant Bug | `get_rule()`, `update_rule()`, `delete_rule()` hatten KEINE company_id Validierung | Fixed: company_id Parameter zu allen 3 Methoden hinzugefuegt, 4 API Endpoints (get, update, delete, preview) nutzen jetzt company_id aus User-Context (IDOR Prevention) |
| 2026-01-18 | **CRITICAL** FinancialGoalsService Multi-Tenant Bug (privat) | `get_goal()`, `update_goal()`, `delete_goal()`, `add_contribution()`, `get_contributions()`, `calculate_goal_progress()` hatten KEINE space_id Validierung | Fixed: space_id Parameter zu allen 6 Methoden hinzugefuegt mit Security-Logging |
| 2026-01-18 | **CRITICAL** FinancialGoalsService Multi-Tenant Bug (portfolio) | `_get_goal()`, `update_progress()`, `complete_goal()`, `get_goals_at_risk()` hatten KEINE space_id Validierung - Cross-Tenant Goal-Zugriff moeglich | Fixed: space_id Parameter zu allen 4 Methoden hinzugefuegt, API validiert bereits via space_id Query - Service-Fixes sind Defense-in-Depth |
| 2026-01-18 | **CRITICAL** PartialPaymentService IDOR Vulnerability | `get_payment_summary()`, `delete_payment()`, `reconcile_with_bank_transaction()` hatten KEINE company_id Validierung - Cross-Tenant Payment-Zugriff moeglich | Fixed: company_id Parameter REQUIRED zu allen 3 Methoden, Security-Logging bei fehlgeschlagenen Zugriffen, 2 API Endpoints aktualisiert |
| 2026-01-18 | **CRITICAL** DocumentGroupingService IDOR Vulnerability | `confirm_group()`, `split_group()` hatten KEINE owner_id Validierung, `get_review_queue()` hatte optional owner_id - Cross-Tenant Document-Group-Zugriff moeglich | Fixed: owner_id Parameter REQUIRED zu allen 3 Methoden, Security-Logging bei fehlgeschlagenen Zugriffen, 2 API Endpoints aktualisiert |
| 2026-01-18 | **MEDIUM** SkontoService Defense-in-Depth | `apply_skonto()`, `update_invoice_skonto_fields()` hatten KEINE company_id Validierung - API validiert bereits, aber kein Defense-in-Depth | Fixed: company_id Parameter REQUIRED zu beiden Methoden, and_() Filter mit Security-Logging, 2 API Endpoints aktualisiert |
| 2026-01-18 | **CRITICAL** PartialPaymentService get_payment_summary Query Bug | Innerhalb von `get_payment_summary()` war die payments_stmt Query OHNE company_id Filter - Self-Review entdeckt | Fixed: `and_()` Filter mit company_id zu PaymentTransaction Query hinzugefuegt |
| 2026-01-18 | **CRITICAL** PartialPaymentService get_partially_paid_invoices Bug | `get_partially_paid_invoices()` hat `get_payment_summary()` OHNE company_id aufgerufen - Self-Review entdeckt | Fixed: company_id Parameter wird jetzt durchgereicht |
| 2026-01-18 | **MEDIUM** groups.py confirm_group Reload Bug | Nach erfolgreicher Bestaetigung wurde Gruppe OHNE owner_id Filter neu geladen - Self-Review entdeckt | Fixed: owner_id Filter in reload-Query hinzugefuegt |
| 2026-01-18 | **MEDIUM** Unit Tests fehlten company_id | 8 Unit Tests in test_partial_payment_service.py und test_skonto_service.py riefen Methoden OHNE neue company_id Parameter auf | Fixed: company_id Parameter zu allen 8 Test-Aufrufen hinzugefuegt |
| 2026-01-18 | **CRITICAL** PartialPaymentService _get_total_paid KEIN company_id | Private Methode `_get_total_paid()` summierte PaymentTransactions OHNE company_id Filter - potentielles Cross-Tenant Data Leak bei Aggregation - 2. Self-Review entdeckt | Fixed: company_id Parameter REQUIRED, and_() Filter, beide Aufrufer (record_payment, delete_payment) aktualisiert |
| 2026-01-18 | **CRITICAL** PartialPaymentService record_payment Invoice-Query Bug | `record_payment()` lud Invoice OHNE company_id Filter - Cross-Tenant Payment-Erstellung moeglich - 2. Self-Review entdeckt | Fixed: company_id Filter in Invoice-Query, Security-Logging bei Fehlschlag |
| 2026-01-18 | **CRITICAL** PartialPaymentService delete_payment Invoice-Reload Bug | Nach Loeschung der Transaktion wurde Invoice OHNE company_id Filter neu geladen - 2. Self-Review entdeckt | Fixed: company_id Filter in Invoice-Reload-Query |
