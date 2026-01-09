# -*- coding: utf-8 -*-
"""Workflow-Automation Services.

Dieses Modul stellt Services fuer die Workflow-Automatisierung bereit:
- WorkflowService: CRUD fuer Workflows + Templates
- WorkflowExecutionService: Workflow-Ausfuehrung + Lifecycle
- WorkflowStepExecutor: Einzelschritt-Ausfuehrung (20+ Actions)
- WorkflowTriggerService: Trigger-Handling (Events, Schedule, Webhook)
- WorkflowEngineService: Regel-basierte Entity-Evaluation
- ConditionEvaluator: Wiederverwendet ImportRuleService-Logik
- PREBUILT_TEMPLATES: Vordefinierte Workflow-Templates
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

__all__ = [
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
]
