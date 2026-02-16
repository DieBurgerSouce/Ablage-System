# -*- coding: utf-8 -*-
"""Workflow-Automation Services.

Dieses Modul stellt Services für die Workflow-Automatisierung bereit:
- WorkflowService: CRUD für Workflows + Templates
- WorkflowExecutionService: Workflow-Ausführung + Lifecycle
- WorkflowStepExecutor: Einzelschritt-Ausführung (20+ Actions)
- WorkflowTriggerService: Trigger-Handling (Events, Schedule, Webhook)
- WorkflowEngineService: Regel-basierte Entity-Evaluation
- ConditionEvaluator: Wiederverwendet ImportRuleService-Logik
- BPMNConverter: BPMN 2.0 Import/Export
- PREBUILT_TEMPLATES: Vordefinierte Workflow-Templates
- WorkflowVersioningService: Semantische Versionierung + A/B Testing
- SagaService: Saga-Pattern für verteilte Transaktionen + Compensation
"""

from app.services.workflow.workflow_service import WorkflowService
from app.services.workflow.workflow_execution_service import (
    WorkflowExecutionService,
    ExecutionContext,
    ExecutionStatus,
)
from app.services.workflow.workflow_step_executor import (
    WorkflowStepExecutor,
    StepResult,
)
from app.services.workflow.workflow_trigger_service import WorkflowTriggerService
from app.services.workflow.workflow_engine_service import (
    WorkflowEngineService,
    WorkflowCondition,
    WorkflowAction,
)
from app.services.workflow.condition_evaluator import ConditionEvaluator
from app.services.workflow.workflow_templates import (
    PREBUILT_TEMPLATES,
    seed_workflow_templates,
)
from app.services.workflow.bpmn_converter import (
    BPMNConverter,
    BPMNParser,
    BPMNExporter,
    BPMNValidator,
    WorkflowDefinition,
    ProcessDefinition,
    TaskDefinition,
    GatewayDefinition,
    EventDefinition,
    FlowDefinition,
    ValidationResult,
    TaskType,
    GatewayType,
    EventType,
    get_bpmn_converter,
    get_bpmn_parser,
    get_bpmn_exporter,
    get_bpmn_validator,
)
from app.services.workflow.versioning_service import WorkflowVersioningService
from app.services.workflow.saga_service import SagaService, StepHandlerRegistry

__all__ = [
    # Workflow Services
    "WorkflowService",
    "WorkflowExecutionService",
    "ExecutionContext",
    "ExecutionStatus",
    "WorkflowStepExecutor",
    "StepResult",
    "WorkflowTriggerService",
    "WorkflowEngineService",
    "WorkflowCondition",
    "WorkflowAction",
    "ConditionEvaluator",
    "PREBUILT_TEMPLATES",
    "seed_workflow_templates",
    # BPMN Converter
    "BPMNConverter",
    "BPMNParser",
    "BPMNExporter",
    "BPMNValidator",
    "WorkflowDefinition",
    "ProcessDefinition",
    "TaskDefinition",
    "GatewayDefinition",
    "EventDefinition",
    "FlowDefinition",
    "ValidationResult",
    "TaskType",
    "GatewayType",
    "EventType",
    "get_bpmn_converter",
    "get_bpmn_parser",
    "get_bpmn_exporter",
    "get_bpmn_validator",
    # Versioning & Saga
    "WorkflowVersioningService",
    "SagaService",
    "StepHandlerRegistry",
]
