"""BPMN 2.0 Process Engine Services.

Enterprise-Grade Workflow Engine für das Ablage-System.

Services:
- BPMNParserService: BPMN 2.0 XML Parser/Generator
- ProcessDefinitionService: Prozess-Definitionen verwalten
- ProcessExecutionService: Prozess-Instanzen ausführen
- ProcessTaskService: User Tasks verwalten
- TimerService: Timer Events verarbeiten

Verwendung:
    from app.services.bpmn import (
        get_process_definition_service,
        get_process_execution_service,
        get_task_service,
    )

    async def example(db: AsyncSession, user_id: UUID):
        definition_service = get_process_definition_service(db)
        execution_service = get_process_execution_service(db)
        task_service = get_task_service(db)

        # Prozess deployen
        definition = await definition_service.deploy(
            key="invoice-approval",
            name="Rechnungsfreigabe",
            bpmn_xml=xml_content,
            company_id=company_id
        )

        # Prozess starten
        instance = await execution_service.start(
            definition_key="invoice-approval",
            variables={"invoice_id": str(invoice_id), "amount": 1500.00},
            business_key=f"INV-{invoice_id}",
            company_id=company_id,
            started_by_id=user_id
        )

        # Task bearbeiten
        tasks = await task_service.get_user_tasks(user_id, company_id)
        await task_service.complete(task_id, user_id, {"approved": True})
"""

from app.services.bpmn.process_definition_service import (
    ProcessDefinitionService,
    get_process_definition_service,
)
from app.services.bpmn.process_execution_service import (
    ProcessExecutionService,
    get_process_execution_service,
)
from app.services.bpmn.task_service import (
    ProcessTaskService,
    get_task_service,
)
from app.services.bpmn.bpmn_parser import (
    BPMNParser,
    BPMNElement,
    BPMNProcess,
)
from app.services.bpmn.timer_service import (
    TimerService,
    get_timer_service,
)
from app.services.bpmn.workflow_templates import (
    get_workflow_template,
    list_workflow_templates,
    INVOICE_APPROVAL_WORKFLOW,
    DUNNING_PROCESS_WORKFLOW,
    CUSTOMER_ONBOARDING_WORKFLOW,
    DOCUMENT_CLASSIFICATION_WORKFLOW,
)
from app.services.bpmn.invoice_tasks import (
    auto_approve_invoice,
    book_invoice,
    calculate_approval_level,
)
from app.services.bpmn.dunning_tasks import (
    send_payment_reminder,
    send_first_dunning,
    send_second_dunning,
    send_final_dunning,
    transfer_to_collection,
    check_payment_received,
    close_dunning_case,
    calculate_dunning_deadline,
)
from app.services.bpmn.onboarding_tasks import (
    verify_customer_data,
    check_credit_rating,
    setup_customer_account,
    send_welcome_package,
    assign_account_manager,
    complete_onboarding,
    calculate_onboarding_priority,
)
from app.services.bpmn.document_tasks import (
    extract_document_text,
    classify_document,
    extract_entities,
    match_business_entity,
    route_to_folder,
    trigger_workflow,
    complete_classification,
    get_document_type_display_name,
)
from app.services.bpmn.sla_service import (
    SLAService,
    get_sla_service,
    SLAStatus,
    SLAAlertThreshold,
)
from app.services.bpmn.approval_service import (
    ParallelApprovalService,
    get_parallel_approval_service,
    ConsensusType,
    ApprovalDecision,
    ParallelApprovalStatus,
)
from app.services.bpmn.workflow_analytics_service import (
    WorkflowAnalyticsService,
    get_workflow_analytics_service,
)

__all__ = [
    # Services
    "ProcessDefinitionService",
    "ProcessExecutionService",
    "ProcessTaskService",
    "TimerService",
    "SLAService",
    "ParallelApprovalService",
    "WorkflowAnalyticsService",
    # Factory Functions
    "get_process_definition_service",
    "get_process_execution_service",
    "get_task_service",
    "get_timer_service",
    "get_sla_service",
    "get_parallel_approval_service",
    "get_workflow_analytics_service",
    # SLA Enums
    "SLAStatus",
    "SLAAlertThreshold",
    # Approval Enums
    "ConsensusType",
    "ApprovalDecision",
    "ParallelApprovalStatus",
    # Parser
    "BPMNParser",
    "BPMNElement",
    "BPMNProcess",
    # Workflow Templates
    "get_workflow_template",
    "list_workflow_templates",
    "INVOICE_APPROVAL_WORKFLOW",
    "DUNNING_PROCESS_WORKFLOW",
    "CUSTOMER_ONBOARDING_WORKFLOW",
    "DOCUMENT_CLASSIFICATION_WORKFLOW",
    # Invoice Tasks
    "auto_approve_invoice",
    "book_invoice",
    "calculate_approval_level",
    # Dunning Tasks
    "send_payment_reminder",
    "send_first_dunning",
    "send_second_dunning",
    "send_final_dunning",
    "transfer_to_collection",
    "check_payment_received",
    "close_dunning_case",
    "calculate_dunning_deadline",
    # Onboarding Tasks
    "verify_customer_data",
    "check_credit_rating",
    "setup_customer_account",
    "send_welcome_package",
    "assign_account_manager",
    "complete_onboarding",
    "calculate_onboarding_priority",
    # Document Tasks
    "extract_document_text",
    "classify_document",
    "extract_entities",
    "match_business_entity",
    "route_to_folder",
    "trigger_workflow",
    "complete_classification",
    "get_document_type_display_name",
]
