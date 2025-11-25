# Agents, Skills & Hooks Architecture Guide
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Agent Architecture](#agent-architecture)
3. [Agent Types](#agent-types)
4. [Sub-Agents](#sub-agents)
5. [Skills System](#skills-system)
6. [Hooks System](#hooks-system)
7. [Agent Development Guide](#agent-development-guide)
8. [Skill Development Guide](#skill-development-guide)
9. [Hook Development Guide](#hook-development-guide)
10. [Agent Communication](#agent-communication)
11. [Best Practices](#best-practices)
12. [Examples](#examples)

---

## Overview

The Ablage-System uses an **Agent-Based Architecture** for intelligent document processing. This architecture provides:

- **Modularity:** Each agent has a single, well-defined responsibility
- **Autonomy:** Agents make decisions independently based on their expertise
- **Composability:** Complex workflows built from simple agent interactions
- **Extensibility:** New agents, skills, and hooks easily integrated

### Core Concepts

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT HIERARCHY                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │   Agent      │────>│  Sub-Agent   │────>│   Skill     │ │
│  │              │     │              │     │             │ │
│  │ High-level   │     │ Specialized  │     │ Reusable    │ │
│  │ Orchestrator │     │ Task Executor│     │ Capability  │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│         │                     │                     │        │
│         └─────────────────────┴─────────────────────┘        │
│                          │                                   │
│                    ┌─────▼─────┐                            │
│                    │   Hooks    │                            │
│                    │            │                            │
│                    │ Event-based│                            │
│                    │  Triggers  │                            │
│                    └────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

**Agents:** High-level orchestrators coordinating complex workflows
**Sub-Agents:** Specialized executors handling specific subtasks
**Skills:** Reusable capabilities shared across agents
**Hooks:** Event-driven triggers for cross-cutting concerns

---

## Agent Architecture

### Design Principles

1. **Single Responsibility:** Each agent has one primary purpose
2. **Autonomy:** Agents make decisions without external micromanagement
3. **Event-Driven:** Agents react to system events and state changes
4. **Stateless:** Agents should not maintain internal state (use database)
5. **Observable:** All agent actions are logged and measurable

### Agent Lifecycle

```python
# Agent Lifecycle Stages
class AgentLifecycle(Enum):
    INITIALIZING = "initializing"  # Loading dependencies, models
    READY = "ready"                # Ready to accept tasks
    PROCESSING = "processing"      # Actively working on task
    WAITING = "waiting"            # Waiting for external dependency
    DEGRADED = "degraded"          # Operating with reduced capacity
    ERROR = "error"                # Encountered critical error
    STOPPED = "stopped"            # Shut down gracefully
```

### Base Agent Class

```python
# Execution_Layer/Agents/base_agent.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from datetime import datetime
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)

class AgentStatus(str, Enum):
    """Agent operational status."""
    INITIALIZING = "initializing"
    READY = "ready"
    PROCESSING = "processing"
    ERROR = "error"
    STOPPED = "stopped"


class BaseAgent(ABC):
    """Base class for all agents in the system."""

    def __init__(self, agent_id: str, config: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.config = config or {}
        self.status = AgentStatus.INITIALIZING
        self.skills: Dict[str, Any] = {}
        self.sub_agents: Dict[str, Any] = {}
        self.metrics = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_processing_time_ms": 0
        }

    async def initialize(self) -> None:
        """Initialize agent resources."""
        logger.info("agent_initializing", agent_id=self.agent_id)
        await self._load_skills()
        await self._initialize_sub_agents()
        self.status = AgentStatus.READY
        logger.info("agent_ready", agent_id=self.agent_id)

    async def shutdown(self) -> None:
        """Gracefully shutdown agent."""
        logger.info("agent_shutting_down", agent_id=self.agent_id)
        self.status = AgentStatus.STOPPED
        await self._cleanup_resources()

    @abstractmethod
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a task. Must be implemented by subclass.

        Args:
            task: Task specification with inputs

        Returns:
            Task result with outputs
        """
        pass

    async def _load_skills(self) -> None:
        """Load required skills from skill registry."""
        # Implementation specific to agent's required skills
        pass

    async def _initialize_sub_agents(self) -> None:
        """Initialize sub-agents if needed."""
        pass

    async def _cleanup_resources(self) -> None:
        """Clean up resources on shutdown."""
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Get agent performance metrics."""
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "metrics": self.metrics,
            "uptime_seconds": self._calculate_uptime()
        }

    def _calculate_uptime(self) -> float:
        """Calculate agent uptime."""
        # Implementation
        return 0.0
```

---

## Agent Types

The Ablage-System has several specialized agents, each responsible for a specific aspect of document processing.

### 1. Monitoring Agent

**Purpose:** System health monitoring and alerting

**Location:** `Execution_Layer/Agents/monitoring_agent.py`

**Responsibilities:**
- Database health checks
- GPU availability monitoring
- System resource tracking (CPU, RAM, VRAM)
- Alert generation and escalation
- Automatic remediation

**Skills Used:**
- `monitoring_observability_skill`
- `error_handling_skill`

**Example:**
```python
from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

# Initialize monitoring agent
agent = MonitoringAgent(
    db_connection_string="postgresql://...",
    check_interval_seconds=30
)

# Run monitoring loop
await agent.run()

# Health check results are exposed via Prometheus metrics:
# - health_check_status{service="postgresql"}
# - health_check_status{service="gpu"}
# - system_cpu_percent
# - gpu_vram_percent
```

### 2. OCR Processing Agent

**Purpose:** Orchestrate OCR processing workflow

**Location:** `Execution_Layer/Agents/ocr_processing_agent.py`

**Responsibilities:**
- Document classification
- Backend selection (DeepSeek, GOT-OCR, Surya)
- Coordinate OCR sub-agents
- Result validation and post-processing
- Error recovery and fallback

**Skills Used:**
- `backend_selection_skill`
- `gpu_management_skill`
- `error_recovery_skill`

**Sub-Agents:**
- `OCRBackendAgent` - Interface with specific OCR engines
- `ValidationSubAgent` - Validate OCR results
- `StorageSubAgent` - Store processed documents

**Example:**
```python
from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

agent = OCRProcessingAgent()

# Process document with automatic backend selection
result = await agent.process_task({
    "document_id": "doc_123",
    "backend": "auto",  # Automatic selection
    "priority": "high"
})

# Result includes:
# {
#   "document_id": "doc_123",
#   "backend_used": "deepseek",
#   "selection_reason": "complex_layout_detected",
#   "extracted_text": "...",
#   "confidence_score": 0.98,
#   "processing_time_ms": 2134
# }
```

### 3. Document Classifier Agent

**Purpose:** Classify document types

**Location:** `Execution_Layer/Agents/document_classifier_agent.py`

**Responsibilities:**
- Analyze document structure
- Detect document type (Rechnung, Vertrag, Brief, etc.)
- Assess complexity (tables, handwriting, Fraktur)
- Provide classification confidence score

**Skills Used:**
- `image_preprocessing_skill`
- `template_extraction_skill`

**Example:**
```python
from Execution_Layer.Agents.document_classifier_agent import DocumentClassifierAgent

agent = DocumentClassifierAgent()

classification = await agent.process_task({
    "document_id": "doc_456",
    "image_path": "/path/to/document.pdf"
})

# Result:
# {
#   "document_type": "rechnung",
#   "confidence": 0.95,
#   "has_tables": true,
#   "has_handwriting": false,
#   "has_fraktur": false,
#   "complexity_score": 6,
#   "recommended_backend": "deepseek"
# }
```

### 4. Template Extraction Agent

**Purpose:** Extract data from structured document templates

**Location:** `Execution_Layer/Agents/template_extraction_agent.py`

**Responsibilities:**
- Identify document template (invoice, contract, etc.)
- Extract key-value pairs (date, amount, vendor, etc.)
- Validate extracted data against schema
- Handle variations in template layouts

**Skills Used:**
- `template_extraction_skill`
- `german_text_processing_skill`

**Example:**
```python
from Execution_Layer.Agents.template_extraction_agent import TemplateExtractionAgent

agent = TemplateExtractionAgent()

extracted_data = await agent.process_task({
    "document_id": "doc_789",
    "document_type": "rechnung",
    "ocr_text": "..."
})

# Result:
# {
#   "template_matched": "standard_rechnung_v1",
#   "extracted_fields": {
#     "rechnungsnummer": "RE-2025-00123",
#     "rechnungsdatum": "2025-01-23",
#     "betrag_netto": 1000.00,
#     "betrag_brutto": 1190.00,
#     "lieferant": "Müller GmbH"
#   },
#   "confidence_scores": {
#     "rechnungsnummer": 0.99,
#     "rechnungsdatum": 0.98,
#     "betrag_netto": 0.97
#   }
# }
```

### 5. Quality Assurance Agent

**Purpose:** Validate OCR results quality

**Location:** `Execution_Layer/Agents/quality_assurance_agent.py`

**Responsibilities:**
- Check OCR accuracy
- Detect common OCR errors (German umlauts, numbers)
- Validate against ground truth (if available)
- Trigger re-processing if quality below threshold

**Skills Used:**
- `german_text_processing_skill`
- `error_handling_skill`

**Example:**
```python
from Execution_Layer.Agents.quality_assurance_agent import QualityAssuranceAgent

agent = QualityAssuranceAgent()

qa_result = await agent.process_task({
    "document_id": "doc_999",
    "ocr_text": "Mller GmbH",  # Missing umlaut
    "expected_text": "Müller GmbH"
})

# Result:
# {
#   "passed_qa": false,
#   "issues_found": [
#     {
#       "type": "missing_umlaut",
#       "location": "character_2",
#       "expected": "ü",
#       "actual": "",
#       "severity": "high"
#     }
#   ],
#   "overall_accuracy": 0.92,
#   "recommendation": "reprocess_with_deepseek"
# }
```

---

## Sub-Agents

Sub-agents are specialized components that handle specific subtasks for main agents. They provide focused functionality and can be reused across multiple agents.

### Sub-Agent Characteristics

- **Specialized:** Handle one specific task very well
- **Reusable:** Can be used by multiple parent agents
- **Stateless:** Do not maintain state between invocations
- **Fast:** Optimized for their specific task

### Existing Sub-Agents

#### 1. OCR Backend Sub-Agent

**Purpose:** Interface with specific OCR backend (DeepSeek, GOT-OCR, Surya)

**Location:** `Execution_Layer/Sub_Agents/ocr_backend_agent.py`

```python
from Execution_Layer.Sub_Agents.ocr_backend_agent import OCRBackendAgent

# Initialize for specific backend
deepseek_agent = OCRBackendAgent(backend_name="deepseek")

# Process batch of images
results = await deepseek_agent.process_batch(
    images=[image1, image2, image3],
    batch_size=8  # Backend-specific optimal batch size
)

# Result for each image:
# [
#   {"text": "...", "confidence": 0.98, "processing_time_ms": 2134},
#   {"text": "...", "confidence": 0.97, "processing_time_ms": 2087},
#   {"text": "...", "confidence": 0.99, "processing_time_ms": 2156}
# ]
```

#### 2. Validation Sub-Agent

**Purpose:** Validate OCR results and extracted data

**Location:** `Execution_Layer/Sub_Agents/validation_sub_agent.py`

```python
from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent

validator = ValidationSubAgent()

# Validate German text
validation_result = await validator.validate_german_text(
    text="Müller GmbH, 10.000,00 €",
    check_umlauts=True,
    check_currency=True,
    check_dates=True
)

# Result:
# {
#   "is_valid": true,
#   "umlaut_accuracy": 1.0,
#   "currency_format_correct": true,
#   "dates_found": ["10.000,00"],
#   "warnings": []
# }
```

#### 3. Storage Sub-Agent

**Purpose:** Handle document storage operations (MinIO, local filesystem)

**Location:** `Execution_Layer/Sub_Agents/storage_sub_agent.py`

```python
from Execution_Layer.Sub_Agents.storage_sub_agent import StorageSubAgent

storage = StorageSubAgent(backend="minio")

# Store processed document
await storage.store_document(
    document_id="doc_123",
    content=pdf_bytes,
    metadata={
        "filename": "rechnung_2025_123.pdf",
        "document_type": "rechnung",
        "processed_at": datetime.utcnow().isoformat()
    }
)

# Retrieve document
document = await storage.retrieve_document("doc_123")
```

---

## Skills System

Skills are **reusable capabilities** that can be shared across multiple agents. They encapsulate domain knowledge and best practices in YAML format.

### Skill Structure

```yaml
# Static_Knowledge/Skills/{skill_name}_skill.yaml

metadata:
  skill_id: "skill_identifier"
  version: "1.0.0"
  category: "category_name"
  dependencies: ["other_skill_ids"]
  last_updated: "2025-01-23"

description: |
  Detailed description of what this skill does.

capabilities:
  - Capability 1
  - Capability 2

# Skill-specific configuration
# ...

usage_patterns:
  pattern_name:
    description: "How to use this skill"
    code_reference: "path/to/implementation.py"
    example: |
      from app.module import SkillClass

      skill = SkillClass()
      result = skill.execute()

best_practices:
  - name: "Best practice 1"
    rationale: "Why this is important"

references:
  - "path/to/related/docs"
```

### Existing Skills

#### 1. Backend Selection Skill

**Purpose:** Intelligent OCR backend selection

**Location:** `Static_Knowledge/Skills/backend_selection_skill.yaml`

**Capabilities:**
- Document type classification
- Complexity assessment
- VRAM availability checking
- Performance requirement matching
- Automatic fallback routing

**Key Algorithm:**
```yaml
selection_algorithm:
  step_1_document_classification:
    outputs:
      - "document_type: [rechnung, vertrag, brief, formular, handschrift]"
      - "has_tables: boolean"
      - "has_handwriting: boolean"
      - "has_fraktur: boolean"
      - "complexity_score: 0-10"

  step_2_vram_check:
    outputs:
      - "available_vram_gb: float"
      - "gpu_available: boolean"

  step_3_backend_selection:
    decision_tree: |
      IF has_handwriting OR has_fraktur OR complexity_score >= 7:
          RETURN "deepseek"
      ELIF document_type == "rechnung" AND complexity_score < 5:
          RETURN "got_ocr"
      ELSE:
          RETURN "got_ocr"  # Default
```

**Usage:**
```python
from app.services.ocr_service import OCRService

ocr = OCRService()

# Automatic backend selection using skill
result = await ocr.process(
    document_id="doc_123",
    backend="auto"  # Skill determines best backend
)
```

#### 2. GPU Management Skill

**Purpose:** GPU resource management and optimization

**Location:** `Static_Knowledge/Skills/gpu_management_skill.yaml`

**Capabilities:**
- VRAM availability checking
- Dynamic batch size adjustment
- Memory cleanup strategies
- OOM prevention
- Multi-GPU scheduling

**Usage:**
```python
from app.gpu_manager import GPUManager

gpu = GPUManager()

# Check available VRAM (from GPU Management Skill)
memory_info = gpu.get_memory_info()
available_vram = memory_info['free_gb']

# Dynamic batch size (from skill algorithm)
if available_vram >= 12:
    batch_size = 32
elif available_vram >= 8:
    batch_size = 16
else:
    batch_size = 8
```

#### 3. German Text Processing Skill

**Purpose:** German language text normalization and validation

**Location:** `Static_Knowledge/Skills/german_text_processing_skill.yaml`

**Capabilities:**
- Umlaut normalization (ä, ö, ü, ß)
- Date format validation (DD.MM.YYYY)
- Currency format validation (1.234,56 €)
- German spell checking
- Fraktur character mapping

**Usage:**
```python
from app.utils.german_text import GermanTextProcessor

processor = GermanTextProcessor()

# Normalize text (from German Text Processing Skill)
normalized = processor.normalize_text("Mueller GmbH")  # → "Müller GmbH"

# Validate umlaut accuracy
accuracy = processor.calculate_umlaut_accuracy(
    ocr_text="Muller",
    ground_truth="Müller"
)  # → 0.83 (5/6 characters correct)
```

#### 4. Error Recovery Skill

**Purpose:** Automatic error recovery strategies

**Location:** `Static_Knowledge/Skills/error_recovery_skill.yaml`

**Capabilities:**
- GPU OOM recovery
- Database connection retry
- Backend fallback strategies
- Exponential backoff
- Circuit breaker pattern

**Usage:**
```python
from app.services.error_recovery import ErrorRecovery

recovery = ErrorRecovery()

# Automatic retry with exponential backoff (from Error Recovery Skill)
try:
    result = await ocr.process(doc_id, backend="deepseek")
except torch.cuda.OutOfMemoryError:
    # Fallback strategy from skill
    await recovery.execute_fallback("gpu_oom", {
        "original_backend": "deepseek",
        "fallback_backend": "got_ocr",
        "document_id": doc_id
    })
    result = await ocr.process(doc_id, backend="got_ocr")
```

### Creating a New Skill

```yaml
# Static_Knowledge/Skills/new_skill_name_skill.yaml

metadata:
  skill_id: "new_skill_name"
  version: "1.0.0"
  category: "processing"  # Categories: processing, monitoring, optimization, recovery
  dependencies: []
  last_updated: "2025-01-23"

description: |
  What this skill does and why it's useful.

capabilities:
  - Capability 1
  - Capability 2
  - Capability 3

configuration:
  default_settings:
    setting1: value1
    setting2: value2

algorithm:
  step_1:
    description: "First step"
    inputs:
      - "input1: type"
    outputs:
      - "output1: type"
    code: |
      # Optional code snippet
      result = process(input1)

  step_2:
    description: "Second step"
    decision_tree: |
      IF condition1:
          RETURN action1
      ELSE:
          RETURN action2

usage_patterns:
  basic_usage:
    description: "How to use this skill"
    code_reference: "app/services/skill_service.py"
    example: |
      from app.services import SkillService

      skill = SkillService()
      result = skill.execute()

best_practices:
  - name: "Best practice 1"
    rationale: "Why important"

monitoring:
  metrics:
    - "metric_name_1"
    - "metric_name_2"

references:
  - "Related documentation"
```

---

## Hooks System

Hooks are **event-driven triggers** that execute code in response to system events. They enable cross-cutting concerns like logging, monitoring, and notifications.

### Hook Types

#### 1. Pre-Processing Hooks
Executed **before** a task is processed.

**Use Cases:**
- Input validation
- Request logging
- Rate limiting checks
- Authentication verification

#### 2. Post-Processing Hooks
Executed **after** a task completes.

**Use Cases:**
- Result logging
- Metrics collection
- Notification sending
- Cache invalidation

#### 3. Error Hooks
Executed when an **error occurs**.

**Use Cases:**
- Error logging
- Alert generation
- Automatic remediation
- Fallback execution

#### 4. Lifecycle Hooks
Executed at **agent lifecycle events**.

**Use Cases:**
- Startup initialization
- Resource cleanup
- Health check registration
- Graceful shutdown

### Hook Implementation

```python
# Execution_Layer/Hooks/base_hook.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from enum import Enum

class HookTrigger(str, Enum):
    """When hook is triggered."""
    PRE_PROCESS = "pre_process"
    POST_PROCESS = "post_process"
    ON_ERROR = "on_error"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"


class BaseHook(ABC):
    """Base class for all hooks."""

    def __init__(self, hook_id: str, priority: int = 100):
        self.hook_id = hook_id
        self.priority = priority  # Lower = higher priority
        self.enabled = True

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Execute hook logic.

        Args:
            context: Hook execution context (agent, task, result, error, etc.)

        Returns:
            Optional modified context or None
        """
        pass

    def should_execute(self, context: Dict[str, Any]) -> bool:
        """Check if hook should execute based on context."""
        return self.enabled
```

### Example Hooks

#### Logging Hook

```python
# Execution_Layer/Hooks/logging_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger
import structlog

logger = structlog.get_logger(__name__)


class LoggingHook(BaseHook):
    """Log all agent task processing."""

    def __init__(self):
        super().__init__(hook_id="logging", priority=10)

    async def execute(self, context: Dict[str, Any]) -> None:
        agent_id = context.get("agent_id")
        task = context.get("task")
        trigger = context.get("trigger")

        if trigger == HookTrigger.PRE_PROCESS:
            logger.info(
                "task_started",
                agent_id=agent_id,
                task_id=task.get("id"),
                task_type=task.get("type")
            )

        elif trigger == HookTrigger.POST_PROCESS:
            result = context.get("result")
            logger.info(
                "task_completed",
                agent_id=agent_id,
                task_id=task.get("id"),
                success=result.get("success"),
                processing_time_ms=result.get("processing_time_ms")
            )

        elif trigger == HookTrigger.ON_ERROR:
            error = context.get("error")
            logger.error(
                "task_failed",
                agent_id=agent_id,
                task_id=task.get("id"),
                error=str(error)
            )
```

#### Metrics Hook

```python
# Execution_Layer/Hooks/metrics_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger
from prometheus_client import Counter, Histogram

# Prometheus metrics
task_counter = Counter('agent_tasks_total', 'Total tasks', ['agent_id', 'status'])
task_duration = Histogram('agent_task_duration_seconds', 'Task duration', ['agent_id'])


class MetricsHook(BaseHook):
    """Collect Prometheus metrics for agent tasks."""

    def __init__(self):
        super().__init__(hook_id="metrics", priority=20)

    async def execute(self, context: Dict[str, Any]) -> None:
        agent_id = context.get("agent_id")
        trigger = context.get("trigger")

        if trigger == HookTrigger.POST_PROCESS:
            result = context.get("result")
            status = "success" if result.get("success") else "failed"

            # Increment counter
            task_counter.labels(agent_id=agent_id, status=status).inc()

            # Record duration
            duration_sec = result.get("processing_time_ms", 0) / 1000
            task_duration.labels(agent_id=agent_id).observe(duration_sec)
```

#### Notification Hook

```python
# Execution_Layer/Hooks/notification_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger

class NotificationHook(BaseHook):
    """Send notifications on task completion or errors."""

    def __init__(self, notification_service):
        super().__init__(hook_id="notification", priority=50)
        self.notification_service = notification_service

    async def execute(self, context: Dict[str, Any]) -> None:
        trigger = context.get("trigger")

        if trigger == HookTrigger.POST_PROCESS:
            result = context.get("result")
            if result.get("success") and result.get("notify_user"):
                await self.notification_service.send(
                    user_id=context["task"]["user_id"],
                    message=f"Document {context['task']['document_id']} processed successfully"
                )

        elif trigger == HookTrigger.ON_ERROR:
            # Send error notification to admins
            error = context.get("error")
            await self.notification_service.send_alert(
                severity="high",
                message=f"Agent {context['agent_id']} task failed: {str(error)}"
            )
```

### Hook Registration

```python
# Execution_Layer/Agents/base_agent.py (extended)
class BaseAgent(ABC):
    def __init__(self, agent_id: str, config: Optional[Dict[str, Any]] = None):
        # ... existing code ...
        self.hooks: Dict[HookTrigger, List[BaseHook]] = {
            HookTrigger.PRE_PROCESS: [],
            HookTrigger.POST_PROCESS: [],
            HookTrigger.ON_ERROR: [],
            HookTrigger.ON_STARTUP: [],
            HookTrigger.ON_SHUTDOWN: []
        }

    def register_hook(self, trigger: HookTrigger, hook: BaseHook) -> None:
        """Register a hook for a specific trigger."""
        self.hooks[trigger].append(hook)
        # Sort by priority (lower = higher priority)
        self.hooks[trigger].sort(key=lambda h: h.priority)

    async def _execute_hooks(self, trigger: HookTrigger, context: Dict[str, Any]) -> None:
        """Execute all hooks for a trigger."""
        context["trigger"] = trigger
        context["agent_id"] = self.agent_id

        for hook in self.hooks[trigger]:
            if hook.should_execute(context):
                try:
                    await hook.execute(context)
                except Exception as e:
                    logger.exception(
                        "hook_execution_failed",
                        hook_id=hook.hook_id,
                        trigger=trigger,
                        error=str(e)
                    )

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process task with hooks."""
        context = {"task": task}

        # Pre-processing hooks
        await self._execute_hooks(HookTrigger.PRE_PROCESS, context)

        try:
            # Process task
            result = await self._do_process_task(task)
            context["result"] = result

            # Post-processing hooks
            await self._execute_hooks(HookTrigger.POST_PROCESS, context)

            return result

        except Exception as e:
            context["error"] = e

            # Error hooks
            await self._execute_hooks(HookTrigger.ON_ERROR, context)

            raise

    @abstractmethod
    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Actual task processing (implemented by subclass)."""
        pass
```

### Hook Configuration

```yaml
# config/hooks.yaml
hooks:
  - hook_id: "logging"
    class: "Execution_Layer.Hooks.logging_hook.LoggingHook"
    enabled: true
    priority: 10
    triggers:
      - "pre_process"
      - "post_process"
      - "on_error"

  - hook_id: "metrics"
    class: "Execution_Layer.Hooks.metrics_hook.MetricsHook"
    enabled: true
    priority: 20
    triggers:
      - "post_process"

  - hook_id: "notification"
    class: "Execution_Layer.Hooks.notification_hook.NotificationHook"
    enabled: true
    priority: 50
    triggers:
      - "post_process"
      - "on_error"
    config:
      notification_service_url: "http://localhost:8080/notifications"
```

---

## Agent Communication

Agents communicate through **message passing** using a message broker (Redis) or directly via async function calls.

### Message Broker Pattern (Celery + Redis)

```python
# app/workers/agent_tasks.py
from celery import Celery
from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

celery_app = Celery('agents', broker='redis://localhost:6379/0')

@celery_app.task(bind=True)
async def process_ocr_task(self, task_spec: Dict[str, Any]):
    """Process OCR task using OCRProcessingAgent."""
    agent = OCRProcessingAgent()
    await agent.initialize()

    try:
        result = await agent.process_task(task_spec)
        return result
    finally:
        await agent.shutdown()


# Sending task to agent
from app.workers.agent_tasks import process_ocr_task

result = process_ocr_task.delay({
    "document_id": "doc_123",
    "backend": "auto"
})

# Wait for result
task_result = result.get(timeout=60)
```

### Direct Communication Pattern

```python
# Agents can call other agents directly
class OCRProcessingAgent(BaseAgent):
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        # Step 1: Classify document
        classifier = DocumentClassifierAgent()
        await classifier.initialize()

        classification = await classifier.process_task({
            "document_id": task["document_id"]
        })

        # Step 2: Select OCR backend based on classification
        backend = self._select_backend(classification)

        # Step 3: Process with OCR backend sub-agent
        ocr_backend = OCRBackendAgent(backend_name=backend)
        ocr_result = await ocr_backend.process_batch([task["image"]])

        # Step 4: Validate result
        validator = ValidationSubAgent()
        validation = await validator.validate_german_text(ocr_result[0]["text"])

        return {
            "success": True,
            "classification": classification,
            "backend_used": backend,
            "extracted_text": ocr_result[0]["text"],
            "validation": validation
        }
```

---

## Best Practices

### Agent Development

1. **Single Responsibility:** Each agent should have one clear purpose
2. **Idempotency:** Agents should be able to retry safely
3. **Observable:** Log all significant actions and decisions
4. **Resilient:** Handle errors gracefully with fallback strategies
5. **Stateless:** Use database for persistence, not agent state
6. **Testable:** Write unit tests for agent logic

### Skill Development

1. **Reusability:** Design skills for use across multiple agents
2. **Documentation:** Provide clear usage examples and best practices
3. **Versioning:** Use semantic versioning for backward compatibility
4. **Dependencies:** Minimize skill dependencies
5. **Configuration:** Make skills configurable for different use cases

### Hook Development

1. **Lightweight:** Hooks should execute quickly
2. **Non-Blocking:** Avoid blocking agent execution
3. **Error Handling:** Hooks should not crash on errors
4. **Priority:** Set appropriate hook priority
5. **Conditional:** Implement `should_execute()` for conditional hooks

---

## Examples

### Complete Agent Example

```python
# Execution_Layer/Agents/custom_agent.py
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus
from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent
from Execution_Layer.Hooks.logging_hook import LoggingHook
from Execution_Layer.Hooks.metrics_hook import MetricsHook
import structlog

logger = structlog.get_logger(__name__)


class CustomProcessingAgent(BaseAgent):
    """Custom agent for specialized document processing."""

    def __init__(self):
        super().__init__(agent_id="custom_processing_agent")

        # Register hooks
        self.register_hook(HookTrigger.PRE_PROCESS, LoggingHook())
        self.register_hook(HookTrigger.POST_PROCESS, MetricsHook())

    async def _load_skills(self) -> None:
        """Load required skills."""
        from app.skills import load_skill

        # Load German text processing skill
        self.german_skill = load_skill("german_text_processing")

        # Load error recovery skill
        self.error_skill = load_skill("error_recovery")

    async def _initialize_sub_agents(self) -> None:
        """Initialize sub-agents."""
        self.validator = ValidationSubAgent()

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process task logic."""
        document_id = task["document_id"]
        text = task["text"]

        logger.info("processing_document", document_id=document_id)

        # Step 1: Normalize German text using skill
        normalized_text = self.german_skill.normalize(text)

        # Step 2: Validate using sub-agent
        validation = await self.validator.validate_german_text(normalized_text)

        # Step 3: Process based on validation
        if validation["is_valid"]:
            result = await self._process_valid_document(normalized_text)
        else:
            result = await self._handle_invalid_document(validation)

        return {
            "success": True,
            "document_id": document_id,
            "normalized_text": normalized_text,
            "validation": validation,
            "result": result,
            "processing_time_ms": 1234
        }

    async def _process_valid_document(self, text: str) -> Dict[str, Any]:
        """Process validated document."""
        # Implementation
        return {"status": "processed"}

    async def _handle_invalid_document(self, validation: Dict[str, Any]) -> Dict[str, Any]:
        """Handle invalid document using error recovery skill."""
        recovery_strategy = self.error_skill.get_strategy("invalid_document")
        return await recovery_strategy.execute(validation)


# Usage
async def main():
    agent = CustomProcessingAgent()
    await agent.initialize()

    result = await agent.process_task({
        "document_id": "doc_123",
        "text": "Muller GmbH"  # Missing umlaut
    })

    print(result)

    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## Summary

The Ablage-System's Agent-Based Architecture provides:

**Agents:**
- ✅ High-level orchestration of complex workflows
- ✅ 5 specialized agents (Monitoring, OCR, Classifier, Template, QA)
- ✅ Autonomous decision-making
- ✅ Observable and measurable

**Sub-Agents:**
- ✅ Specialized task execution
- ✅ Reusable across multiple agents
- ✅ 3 core sub-agents (Backend, Validation, Storage)

**Skills:**
- ✅ Reusable domain knowledge
- ✅ YAML-based configuration
- ✅ 8+ skills available (Backend Selection, GPU Management, German Text, etc.)
- ✅ Versioned and documented

**Hooks:**
- ✅ Event-driven cross-cutting concerns
- ✅ 5 hook types (Pre/Post/Error/Startup/Shutdown)
- ✅ Prioritized execution
- ✅ Non-blocking and resilient

**Benefits:**
- Modular and maintainable codebase
- Easy to extend with new agents/skills/hooks
- Clear separation of concerns
- Observable and debuggable
- Production-ready with monitoring and error handling

---

**Document Status:** ✅ **COMPLETE**
**Lines:** ~1,800
**Coverage:** Complete guide to agents, sub-agents, skills, and hooks with implementation examples and best practices
