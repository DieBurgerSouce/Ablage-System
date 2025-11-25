# Agent Implementation Patterns
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Pattern 1: Simple Task Agent](#pattern-1-simple-task-agent)
3. [Pattern 2: Multi-Step Pipeline Agent](#pattern-2-multi-step-pipeline-agent)
4. [Pattern 3: Fallback Agent](#pattern-3-fallback-agent)
5. [Pattern 4: Batch Processing Agent](#pattern-4-batch-processing-agent)
6. [Pattern 5: Event-Driven Agent](#pattern-5-event-driven-agent)
7. [Pattern 6: Coordinating Agent](#pattern-6-coordinating-agent)
8. [Pattern 7: Monitoring Agent](#pattern-7-monitoring-agent)
9. [Complete Implementation Examples](#complete-implementation-examples)

---

## Overview

Dieses Dokument enthält **konkrete, lauffähige Implementierungsmuster** für verschiedene Agent-Typen im Ablage-System. Jedes Pattern ist vollständig implementiert und kann direkt verwendet werden.

### Pattern-Kategorien

```
┌────────────────────────────────────────────────────────────┐
│                  AGENT PATTERNS                             │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Simple Task     Multi-Step     Fallback     Batch         │
│  ┌─────────┐    ┌─────────┐    ┌────────┐   ┌─────────┐  │
│  │ Input   │    │ Step 1  │    │Primary │   │ Item 1  │  │
│  │    ↓    │    │    ↓    │    │   ↓    │   │ Item 2  │  │
│  │ Process │    │ Step 2  │    │ Error? │   │ Item 3  │  │
│  │    ↓    │    │    ↓    │    │   ↓    │   │   ...   │  │
│  │ Output  │    │ Step 3  │    │Fallback│   │ Batch   │  │
│  └─────────┘    └─────────┘    └────────┘   └─────────┘  │
│                                                             │
│  Event-Driven   Coordinating    Monitoring                 │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │ Event 1 │    │ Agent A │    │ Check 1 │                │
│  │ Event 2 │───>│ Agent B │    │ Check 2 │                │
│  │ Event 3 │    │ Agent C │    │ Check 3 │                │
│  └─────────┘    └─────────┘    └─────────┘                │
└────────────────────────────────────────────────────────────┘
```

---

## Pattern 1: Simple Task Agent

**Use Case:** Einfache Aufgabe mit einem Input und einem Output

**Wann verwenden:**
- Single-purpose Funktionalität
- Keine komplexe Orchestrierung erforderlich
- Klare Input → Process → Output Struktur

### Vollständige Implementierung

```python
# Execution_Layer/Agents/simple_task_agent.py
from typing import Any, Dict, Optional
from datetime import datetime
import structlog
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus

logger = structlog.get_logger(__name__)


class SimpleTaskAgent(BaseAgent):
    """
    Simple Task Agent Pattern

    Verarbeitet eine einzelne Aufgabe mit klarem Input/Output.
    Ideal für einfache Transformationen oder Validierungen.
    """

    def __init__(
        self,
        agent_id: str = "simple_task_agent",
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id=agent_id, config=config)
        self.start_time = datetime.utcnow()

    async def initialize(self) -> None:
        """Initialize agent resources."""
        logger.info("simple_agent_initializing", agent_id=self.agent_id)

        # Load any required skills
        await self._load_skills()

        # Mark as ready
        self.status = AgentStatus.READY
        logger.info("simple_agent_ready", agent_id=self.agent_id)

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process task logic.

        Args:
            task: {
                "input_data": Any,
                "operation": str  # Optional: specify operation type
            }

        Returns:
            {
                "success": bool,
                "output_data": Any,
                "processing_time_ms": int,
                "metadata": Dict
            }
        """
        start = datetime.utcnow()

        try:
            # Extract input
            input_data = task.get("input_data")
            operation = task.get("operation", "default")

            logger.info(
                "processing_task",
                agent_id=self.agent_id,
                operation=operation,
                input_type=type(input_data).__name__
            )

            # Process based on operation
            output_data = await self._execute_operation(operation, input_data)

            # Update metrics
            self.metrics["tasks_completed"] += 1

            # Calculate processing time
            processing_time_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            self.metrics["total_processing_time_ms"] += processing_time_ms

            return {
                "success": True,
                "output_data": output_data,
                "processing_time_ms": processing_time_ms,
                "metadata": {
                    "agent_id": self.agent_id,
                    "operation": operation,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.exception(
                "task_processing_failed",
                agent_id=self.agent_id,
                error=str(e)
            )
            raise

    async def _execute_operation(
        self,
        operation: str,
        input_data: Any
    ) -> Any:
        """
        Execute specific operation on input data.

        Override this method in subclasses for custom operations.
        """
        if operation == "uppercase":
            return str(input_data).upper()
        elif operation == "lowercase":
            return str(input_data).lower()
        elif operation == "reverse":
            return str(input_data)[::-1]
        else:
            # Default: return input unchanged
            return input_data

    async def _cleanup_resources(self) -> None:
        """Clean up resources on shutdown."""
        logger.info(
            "simple_agent_shutdown",
            agent_id=self.agent_id,
            tasks_completed=self.metrics["tasks_completed"],
            tasks_failed=self.metrics["tasks_failed"]
        )

    def _calculate_uptime(self) -> float:
        """Calculate agent uptime in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Example Usage
async def example_simple_agent():
    """Example of using SimpleTaskAgent."""

    # Initialize agent
    agent = SimpleTaskAgent()
    await agent.initialize()

    # Process different operations
    tasks = [
        {"input_data": "hello world", "operation": "uppercase"},
        {"input_data": "HELLO WORLD", "operation": "lowercase"},
        {"input_data": "hello", "operation": "reverse"},
    ]

    for task in tasks:
        result = await agent.process_task(task)
        print(f"Operation: {task['operation']}")
        print(f"Input: {task['input_data']}")
        print(f"Output: {result['output_data']}")
        print(f"Time: {result['processing_time_ms']}ms")
        print("---")

    # Get metrics
    metrics = agent.get_metrics()
    print(f"Agent Metrics: {metrics}")

    # Shutdown
    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_simple_agent())
```

### Tests für Simple Task Agent

```python
# tests/unit/agents/test_simple_task_agent.py
import pytest
from Execution_Layer.Agents.simple_task_agent import SimpleTaskAgent


@pytest.mark.asyncio
async def test_simple_agent_uppercase():
    """Test uppercase operation."""
    agent = SimpleTaskAgent()
    await agent.initialize()

    result = await agent.process_task({
        "input_data": "hello",
        "operation": "uppercase"
    })

    assert result["success"] is True
    assert result["output_data"] == "HELLO"
    assert result["processing_time_ms"] > 0

    await agent.shutdown()


@pytest.mark.asyncio
async def test_simple_agent_metrics():
    """Test agent metrics tracking."""
    agent = SimpleTaskAgent()
    await agent.initialize()

    # Process multiple tasks
    for i in range(5):
        await agent.process_task({
            "input_data": f"test_{i}",
            "operation": "uppercase"
        })

    metrics = agent.get_metrics()
    assert metrics["metrics"]["tasks_completed"] == 5
    assert metrics["metrics"]["tasks_failed"] == 0

    await agent.shutdown()
```

---

## Pattern 2: Multi-Step Pipeline Agent

**Use Case:** Mehrstufige Verarbeitung mit mehreren Sub-Tasks

**Wann verwenden:**
- Komplexe Workflows mit mehreren Schritten
- Jeder Schritt hat klare Input/Output Beziehung
- Fehler in einem Schritt sollten gesamte Pipeline stoppen

### Vollständige Implementierung

```python
# Execution_Layer/Agents/pipeline_agent.py
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime
from enum import Enum
import structlog
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus

logger = structlog.get_logger(__name__)


class PipelineStepStatus(str, Enum):
    """Status eines Pipeline-Schritts."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStep:
    """Definition eines Pipeline-Schritts."""

    def __init__(
        self,
        step_id: str,
        name: str,
        processor: Callable[[Any], Awaitable[Any]],
        optional: bool = False,
        retry_count: int = 0
    ):
        self.step_id = step_id
        self.name = name
        self.processor = processor
        self.optional = optional
        self.retry_count = retry_count
        self.status = PipelineStepStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.processing_time_ms: int = 0


class MultiStepPipelineAgent(BaseAgent):
    """
    Multi-Step Pipeline Agent Pattern

    Führt eine Sequenz von Verarbeitungsschritten aus.
    Jeder Schritt erhält den Output des vorherigen Schritts.
    """

    def __init__(
        self,
        agent_id: str = "pipeline_agent",
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id=agent_id, config=config)
        self.pipeline_steps: List[PipelineStep] = []
        self.start_time = datetime.utcnow()

    def add_step(
        self,
        step_id: str,
        name: str,
        processor: Callable[[Any], Awaitable[Any]],
        optional: bool = False,
        retry_count: int = 0
    ) -> None:
        """
        Füge einen Verarbeitungsschritt zur Pipeline hinzu.

        Args:
            step_id: Eindeutige ID des Schritts
            name: Lesbarer Name
            processor: Async Funktion die Daten verarbeitet
            optional: Schritt kann fehlschlagen ohne Pipeline zu stoppen
            retry_count: Anzahl der Wiederholungen bei Fehler
        """
        step = PipelineStep(
            step_id=step_id,
            name=name,
            processor=processor,
            optional=optional,
            retry_count=retry_count
        )
        self.pipeline_steps.append(step)

        logger.info(
            "pipeline_step_added",
            agent_id=self.agent_id,
            step_id=step_id,
            step_name=name,
            optional=optional
        )

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führe Pipeline-Schritte sequenziell aus.

        Args:
            task: {
                "input_data": Any,
                "skip_steps": List[str]  # Optional: zu überspringende Schritte
            }

        Returns:
            {
                "success": bool,
                "final_output": Any,
                "step_results": List[Dict],
                "total_processing_time_ms": int
            }
        """
        start = datetime.utcnow()
        skip_steps = task.get("skip_steps", [])
        current_data = task.get("input_data")

        step_results = []

        logger.info(
            "pipeline_started",
            agent_id=self.agent_id,
            total_steps=len(self.pipeline_steps),
            skip_steps=skip_steps
        )

        try:
            for step in self.pipeline_steps:
                # Skip if requested
                if step.step_id in skip_steps:
                    step.status = PipelineStepStatus.SKIPPED
                    step_results.append(self._step_to_dict(step))
                    logger.info(
                        "pipeline_step_skipped",
                        agent_id=self.agent_id,
                        step_id=step.step_id
                    )
                    continue

                # Execute step
                step_start = datetime.utcnow()
                step.status = PipelineStepStatus.RUNNING

                logger.info(
                    "pipeline_step_started",
                    agent_id=self.agent_id,
                    step_id=step.step_id,
                    step_name=step.name
                )

                try:
                    # Execute with retry logic
                    for attempt in range(step.retry_count + 1):
                        try:
                            current_data = await step.processor(current_data)
                            step.result = current_data
                            step.status = PipelineStepStatus.COMPLETED
                            break
                        except Exception as e:
                            if attempt < step.retry_count:
                                logger.warning(
                                    "pipeline_step_retry",
                                    agent_id=self.agent_id,
                                    step_id=step.step_id,
                                    attempt=attempt + 1,
                                    error=str(e)
                                )
                            else:
                                raise

                    step.processing_time_ms = int(
                        (datetime.utcnow() - step_start).total_seconds() * 1000
                    )

                    logger.info(
                        "pipeline_step_completed",
                        agent_id=self.agent_id,
                        step_id=step.step_id,
                        processing_time_ms=step.processing_time_ms
                    )

                except Exception as e:
                    step.status = PipelineStepStatus.FAILED
                    step.error = str(e)

                    logger.error(
                        "pipeline_step_failed",
                        agent_id=self.agent_id,
                        step_id=step.step_id,
                        error=str(e),
                        optional=step.optional
                    )

                    # Fail entire pipeline if step is not optional
                    if not step.optional:
                        raise

                step_results.append(self._step_to_dict(step))

            # Calculate total processing time
            total_processing_time_ms = int(
                (datetime.utcnow() - start).total_seconds() * 1000
            )

            # Update metrics
            self.metrics["tasks_completed"] += 1
            self.metrics["total_processing_time_ms"] += total_processing_time_ms

            logger.info(
                "pipeline_completed",
                agent_id=self.agent_id,
                total_processing_time_ms=total_processing_time_ms
            )

            return {
                "success": True,
                "final_output": current_data,
                "step_results": step_results,
                "total_processing_time_ms": total_processing_time_ms
            }

        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.exception(
                "pipeline_failed",
                agent_id=self.agent_id,
                error=str(e)
            )

            return {
                "success": False,
                "final_output": None,
                "step_results": step_results,
                "error": str(e),
                "total_processing_time_ms": int(
                    (datetime.utcnow() - start).total_seconds() * 1000
                )
            }

    def _step_to_dict(self, step: PipelineStep) -> Dict[str, Any]:
        """Convert pipeline step to dict."""
        return {
            "step_id": step.step_id,
            "name": step.name,
            "status": step.status.value,
            "processing_time_ms": step.processing_time_ms,
            "error": step.error
        }

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            "agent_id": self.agent_id,
            "total_steps": len(self.pipeline_steps),
            "steps": [self._step_to_dict(step) for step in self.pipeline_steps]
        }

    def _calculate_uptime(self) -> float:
        """Calculate agent uptime."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Example Usage
async def example_pipeline_agent():
    """Example of using MultiStepPipelineAgent."""

    # Define processing functions
    async def step1_normalize(data: str) -> str:
        """Normalize text to uppercase."""
        return data.upper()

    async def step2_add_prefix(data: str) -> str:
        """Add prefix to text."""
        return f"PROCESSED: {data}"

    async def step3_validate(data: str) -> str:
        """Validate text length."""
        if len(data) < 5:
            raise ValueError("Text too short")
        return data

    # Create agent
    agent = MultiStepPipelineAgent(agent_id="example_pipeline")
    await agent.initialize()

    # Define pipeline
    agent.add_step("step1", "Normalize", step1_normalize)
    agent.add_step("step2", "Add Prefix", step2_add_prefix)
    agent.add_step("step3", "Validate", step3_validate, optional=True)

    # Process task
    result = await agent.process_task({
        "input_data": "hello world"
    })

    print(f"Success: {result['success']}")
    print(f"Final Output: {result['final_output']}")
    print(f"Total Time: {result['total_processing_time_ms']}ms")
    print("\nStep Results:")
    for step_result in result["step_results"]:
        print(f"  - {step_result['name']}: {step_result['status']} ({step_result['processing_time_ms']}ms)")

    # Get pipeline status
    status = agent.get_pipeline_status()
    print(f"\nPipeline Status: {status}")

    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_pipeline_agent())
```

### OCR Pipeline Agent Beispiel

```python
# Execution_Layer/Agents/ocr_pipeline_agent.py
from Execution_Layer.Agents.pipeline_agent import MultiStepPipelineAgent
from Execution_Layer.Sub_Agents.ocr_backend_agent import OCRBackendAgent
from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent
from app.utils.german_text import GermanTextProcessor


class OCRPipelineAgent(MultiStepPipelineAgent):
    """
    Spezialisierter Pipeline Agent für OCR-Verarbeitung.
    """

    def __init__(self):
        super().__init__(agent_id="ocr_pipeline_agent")

        # Sub-Agents
        self.ocr_backend = OCRBackendAgent(backend_name="got_ocr")
        self.validator = ValidationSubAgent()
        self.german_processor = GermanTextProcessor()

    async def initialize(self) -> None:
        """Initialize OCR pipeline."""
        await super().initialize()

        # Define OCR pipeline
        self.add_step(
            "preprocess",
            "Image Preprocessing",
            self._preprocess_image
        )

        self.add_step(
            "ocr_extraction",
            "OCR Text Extraction",
            self._extract_text
        )

        self.add_step(
            "text_normalization",
            "German Text Normalization",
            self._normalize_german_text
        )

        self.add_step(
            "validation",
            "Quality Validation",
            self._validate_text,
            optional=True  # Optional validation
        )

    async def _preprocess_image(self, image_path: str) -> Any:
        """Preprocess image for OCR."""
        # Image preprocessing logic
        return image_path

    async def _extract_text(self, image_path: str) -> str:
        """Extract text using OCR."""
        result = await self.ocr_backend.process_batch([image_path])
        return result[0]["text"]

    async def _normalize_german_text(self, text: str) -> str:
        """Normalize German text."""
        return self.german_processor.normalize_text(text)

    async def _validate_text(self, text: str) -> str:
        """Validate text quality."""
        validation = await self.validator.validate_german_text(text)
        if not validation["is_valid"]:
            raise ValueError(f"Validation failed: {validation['warnings']}")
        return text
```

---

## Pattern 3: Fallback Agent

**Use Case:** Agent mit Fallback-Strategien bei Fehlern

**Wann verwenden:**
- Mehrere alternative Verarbeitungsmethoden verfügbar
- Primäre Methode kann fehlschlagen (z.B. GPU OOM)
- Graceful degradation erwünscht

### Vollständige Implementierung

```python
# Execution_Layer/Agents/fallback_agent.py
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime
from enum import Enum
import structlog
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus

logger = structlog.get_logger(__name__)


class FallbackStrategy:
    """Definition einer Fallback-Strategie."""

    def __init__(
        self,
        strategy_id: str,
        name: str,
        processor: Callable[[Any], Awaitable[Any]],
        priority: int = 100,  # Lower = higher priority
        conditions: Optional[List[str]] = None
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.processor = processor
        self.priority = priority
        self.conditions = conditions or []
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0


class FallbackAgent(BaseAgent):
    """
    Fallback Agent Pattern

    Versucht primäre Verarbeitungsmethode, fällt bei Fehler
    auf alternative Methoden zurück.
    """

    def __init__(
        self,
        agent_id: str = "fallback_agent",
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id=agent_id, config=config)
        self.strategies: List[FallbackStrategy] = []
        self.start_time = datetime.utcnow()

    def add_strategy(
        self,
        strategy_id: str,
        name: str,
        processor: Callable[[Any], Awaitable[Any]],
        priority: int = 100,
        conditions: Optional[List[str]] = None
    ) -> None:
        """
        Füge eine Fallback-Strategie hinzu.

        Args:
            strategy_id: Eindeutige ID
            name: Lesbarer Name
            processor: Async Funktion für Verarbeitung
            priority: Priorität (niedrigerer Wert = höhere Priorität)
            conditions: Bedingungen wann diese Strategie verwendet werden soll
        """
        strategy = FallbackStrategy(
            strategy_id=strategy_id,
            name=name,
            processor=processor,
            priority=priority,
            conditions=conditions
        )
        self.strategies.append(strategy)

        # Sort by priority
        self.strategies.sort(key=lambda s: s.priority)

        logger.info(
            "fallback_strategy_added",
            agent_id=self.agent_id,
            strategy_id=strategy_id,
            priority=priority
        )

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Versuche Strategien in Prioritäts-Reihenfolge.

        Args:
            task: {
                "input_data": Any,
                "force_strategy": Optional[str]  # Force specific strategy
            }

        Returns:
            {
                "success": bool,
                "output_data": Any,
                "strategy_used": str,
                "attempts": List[Dict],
                "processing_time_ms": int
            }
        """
        start = datetime.utcnow()
        input_data = task.get("input_data")
        force_strategy = task.get("force_strategy")

        attempts = []
        last_error = None

        # Determine strategies to try
        if force_strategy:
            strategies_to_try = [
                s for s in self.strategies if s.strategy_id == force_strategy
            ]
        else:
            strategies_to_try = self.strategies

        logger.info(
            "fallback_processing_started",
            agent_id=self.agent_id,
            strategies_available=len(strategies_to_try)
        )

        # Try each strategy
        for strategy in strategies_to_try:
            attempt_start = datetime.utcnow()
            strategy.execution_count += 1

            logger.info(
                "trying_fallback_strategy",
                agent_id=self.agent_id,
                strategy_id=strategy.strategy_id,
                strategy_name=strategy.name,
                attempt_number=len(attempts) + 1
            )

            try:
                # Execute strategy
                output_data = await strategy.processor(input_data)

                # Success!
                strategy.success_count += 1

                attempt_time_ms = int(
                    (datetime.utcnow() - attempt_start).total_seconds() * 1000
                )

                attempts.append({
                    "strategy_id": strategy.strategy_id,
                    "strategy_name": strategy.name,
                    "success": True,
                    "processing_time_ms": attempt_time_ms
                })

                total_time_ms = int(
                    (datetime.utcnow() - start).total_seconds() * 1000
                )

                self.metrics["tasks_completed"] += 1
                self.metrics["total_processing_time_ms"] += total_time_ms

                logger.info(
                    "fallback_strategy_succeeded",
                    agent_id=self.agent_id,
                    strategy_id=strategy.strategy_id,
                    total_attempts=len(attempts),
                    total_time_ms=total_time_ms
                )

                return {
                    "success": True,
                    "output_data": output_data,
                    "strategy_used": strategy.strategy_id,
                    "strategy_name": strategy.name,
                    "attempts": attempts,
                    "processing_time_ms": total_time_ms
                }

            except Exception as e:
                strategy.failure_count += 1
                last_error = e

                attempt_time_ms = int(
                    (datetime.utcnow() - attempt_start).total_seconds() * 1000
                )

                attempts.append({
                    "strategy_id": strategy.strategy_id,
                    "strategy_name": strategy.name,
                    "success": False,
                    "error": str(e),
                    "processing_time_ms": attempt_time_ms
                })

                logger.warning(
                    "fallback_strategy_failed",
                    agent_id=self.agent_id,
                    strategy_id=strategy.strategy_id,
                    error=str(e)
                )

                # Continue to next strategy
                continue

        # All strategies failed
        total_time_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        self.metrics["tasks_failed"] += 1

        logger.error(
            "all_fallback_strategies_failed",
            agent_id=self.agent_id,
            total_attempts=len(attempts),
            last_error=str(last_error)
        )

        return {
            "success": False,
            "output_data": None,
            "strategy_used": None,
            "attempts": attempts,
            "error": f"All strategies failed. Last error: {str(last_error)}",
            "processing_time_ms": total_time_ms
        }

    def get_strategy_stats(self) -> Dict[str, Any]:
        """Get statistics for all strategies."""
        return {
            "agent_id": self.agent_id,
            "strategies": [
                {
                    "strategy_id": s.strategy_id,
                    "name": s.name,
                    "priority": s.priority,
                    "execution_count": s.execution_count,
                    "success_count": s.success_count,
                    "failure_count": s.failure_count,
                    "success_rate": (
                        s.success_count / s.execution_count
                        if s.execution_count > 0 else 0
                    )
                }
                for s in self.strategies
            ]
        }

    def _calculate_uptime(self) -> float:
        """Calculate agent uptime."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Example Usage: OCR Fallback Agent
async def example_ocr_fallback_agent():
    """Example of OCR processing with fallback strategies."""

    # Simulated OCR processors
    async def deepseek_ocr(image_path: str) -> str:
        """DeepSeek OCR (high quality, GPU required)."""
        # Simulate GPU check
        import random
        if random.random() < 0.3:  # 30% chance of GPU OOM
            raise RuntimeError("GPU out of memory")
        return f"DeepSeek result for {image_path}"

    async def got_ocr(image_path: str) -> str:
        """GOT-OCR (medium quality, less VRAM)."""
        import random
        if random.random() < 0.1:  # 10% chance of failure
            raise RuntimeError("GOT-OCR processing error")
        return f"GOT-OCR result for {image_path}"

    async def tesseract_ocr(image_path: str) -> str:
        """Tesseract OCR (fallback, CPU only)."""
        # Always works
        return f"Tesseract result for {image_path}"

    # Create fallback agent
    agent = FallbackAgent(agent_id="ocr_fallback_agent")
    await agent.initialize()

    # Add strategies in priority order
    agent.add_strategy(
        "deepseek",
        "DeepSeek-Janus-Pro (GPU)",
        deepseek_ocr,
        priority=10  # Highest priority
    )

    agent.add_strategy(
        "got_ocr",
        "GOT-OCR 2.0 (GPU)",
        got_ocr,
        priority=20
    )

    agent.add_strategy(
        "tesseract",
        "Tesseract (CPU)",
        tesseract_ocr,
        priority=30  # Lowest priority (last resort)
    )

    # Process document
    result = await agent.process_task({
        "input_data": "/path/to/document.pdf"
    })

    print(f"Success: {result['success']}")
    print(f"Strategy Used: {result['strategy_name']}")
    print(f"Total Attempts: {len(result['attempts'])}")
    print(f"Total Time: {result['processing_time_ms']}ms")

    print("\nAttempt Details:")
    for i, attempt in enumerate(result["attempts"], 1):
        status = "✓" if attempt["success"] else "✗"
        print(f"  {i}. {status} {attempt['strategy_name']} ({attempt['processing_time_ms']}ms)")
        if not attempt["success"]:
            print(f"     Error: {attempt['error']}")

    # Get strategy statistics
    stats = agent.get_strategy_stats()
    print(f"\nStrategy Statistics:")
    for strategy in stats["strategies"]:
        print(f"  {strategy['name']}:")
        print(f"    Executions: {strategy['execution_count']}")
        print(f"    Success Rate: {strategy['success_rate']:.2%}")

    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_ocr_fallback_agent())
```

---

## Pattern 4: Batch Processing Agent

**Use Case:** Effiziente Verarbeitung großer Mengen ähnlicher Tasks

**Wann verwenden:**
- Große Anzahl ähnlicher Dokumente
- GPU Batch-Processing für bessere Performance
- Optimierung der Ressourcennutzung

### Vollständige Implementierung

```python
# Execution_Layer/Agents/batch_processing_agent.py
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass
import asyncio
import structlog
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus

logger = structlog.get_logger(__name__)


@dataclass
class BatchItem:
    """Ein Element in einem Batch."""
    item_id: str
    data: Any
    status: str = "pending"  # pending, processing, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None
    processing_time_ms: int = 0


class BatchProcessingAgent(BaseAgent):
    """
    Batch Processing Agent Pattern

    Verarbeitet Items in optimierten Batches für bessere Performance.
    Besonders nützlich für GPU-beschleunigte Operationen.
    """

    def __init__(
        self,
        agent_id: str = "batch_processing_agent",
        config: Optional[Dict[str, Any]] = None,
        default_batch_size: int = 32,
        max_batch_size: int = 64
    ):
        super().__init__(agent_id=agent_id, config=config)
        self.default_batch_size = default_batch_size
        self.max_batch_size = max_batch_size
        self.optimal_batch_size = default_batch_size
        self.start_time = datetime.utcnow()

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verarbeite Items in Batches.

        Args:
            task: {
                "items": List[Any],
                "batch_size": Optional[int],  # Override default
                "parallel_batches": Optional[int]  # Process multiple batches in parallel
            }

        Returns:
            {
                "success": bool,
                "results": List[Any],
                "batch_stats": Dict,
                "total_processing_time_ms": int
            }
        """
        start = datetime.utcnow()

        items = task.get("items", [])
        batch_size = task.get("batch_size", self.optimal_batch_size)
        parallel_batches = task.get("parallel_batches", 1)

        # Ensure batch size is within limits
        batch_size = min(batch_size, self.max_batch_size)

        logger.info(
            "batch_processing_started",
            agent_id=self.agent_id,
            total_items=len(items),
            batch_size=batch_size,
            estimated_batches=(len(items) + batch_size - 1) // batch_size
        )

        # Create batch items
        batch_items = [
            BatchItem(item_id=f"item_{i}", data=item)
            for i, item in enumerate(items)
        ]

        # Split into batches
        batches = [
            batch_items[i:i + batch_size]
            for i in range(0, len(batch_items), batch_size)
        ]

        # Process batches
        try:
            if parallel_batches > 1:
                # Process multiple batches in parallel
                results = await self._process_batches_parallel(
                    batches,
                    parallel_batches
                )
            else:
                # Process batches sequentially
                results = await self._process_batches_sequential(batches)

            # Collect statistics
            batch_stats = self._calculate_batch_stats(batch_items)

            total_time_ms = int(
                (datetime.utcnow() - start).total_seconds() * 1000
            )

            self.metrics["tasks_completed"] += 1
            self.metrics["total_processing_time_ms"] += total_time_ms

            logger.info(
                "batch_processing_completed",
                agent_id=self.agent_id,
                total_items=len(items),
                successful_items=batch_stats["successful_items"],
                failed_items=batch_stats["failed_items"],
                total_time_ms=total_time_ms,
                avg_time_per_item_ms=batch_stats["avg_time_per_item_ms"]
            )

            return {
                "success": True,
                "results": results,
                "batch_stats": batch_stats,
                "total_processing_time_ms": total_time_ms
            }

        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.exception(
                "batch_processing_failed",
                agent_id=self.agent_id,
                error=str(e)
            )
            raise

    async def _process_batches_sequential(
        self,
        batches: List[List[BatchItem]]
    ) -> List[Any]:
        """Process batches sequentially."""
        all_results = []

        for batch_idx, batch in enumerate(batches, 1):
            logger.info(
                "processing_batch",
                agent_id=self.agent_id,
                batch_number=batch_idx,
                total_batches=len(batches),
                batch_size=len(batch)
            )

            batch_results = await self._process_single_batch(batch)
            all_results.extend(batch_results)

        return all_results

    async def _process_batches_parallel(
        self,
        batches: List[List[BatchItem]],
        max_parallel: int
    ) -> List[Any]:
        """Process multiple batches in parallel."""
        all_results = []

        # Process batches in chunks of max_parallel
        for chunk_start in range(0, len(batches), max_parallel):
            chunk_end = min(chunk_start + max_parallel, len(batches))
            batch_chunk = batches[chunk_start:chunk_end]

            logger.info(
                "processing_batch_chunk",
                agent_id=self.agent_id,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                parallel_batches=len(batch_chunk)
            )

            # Process batches in parallel
            chunk_results = await asyncio.gather(*[
                self._process_single_batch(batch)
                for batch in batch_chunk
            ])

            # Flatten results
            for batch_results in chunk_results:
                all_results.extend(batch_results)

        return all_results

    async def _process_single_batch(
        self,
        batch: List[BatchItem]
    ) -> List[Any]:
        """
        Process a single batch of items.

        Override this method for custom batch processing logic.
        """
        results = []

        for item in batch:
            item_start = datetime.utcnow()
            item.status = "processing"

            try:
                # Process item (override this in subclass)
                result = await self._process_item(item.data)

                item.status = "completed"
                item.result = result
                results.append(result)

            except Exception as e:
                item.status = "failed"
                item.error = str(e)
                results.append(None)

                logger.warning(
                    "batch_item_failed",
                    agent_id=self.agent_id,
                    item_id=item.item_id,
                    error=str(e)
                )

            item.processing_time_ms = int(
                (datetime.utcnow() - item_start).total_seconds() * 1000
            )

        return results

    async def _process_item(self, data: Any) -> Any:
        """
        Process a single item.

        Override this method in subclass for custom processing.
        """
        # Default: return data unchanged
        return data

    def _calculate_batch_stats(
        self,
        batch_items: List[BatchItem]
    ) -> Dict[str, Any]:
        """Calculate batch processing statistics."""
        successful = [i for i in batch_items if i.status == "completed"]
        failed = [i for i in batch_items if i.status == "failed"]

        total_time = sum(i.processing_time_ms for i in batch_items)
        avg_time = total_time / len(batch_items) if batch_items else 0

        return {
            "total_items": len(batch_items),
            "successful_items": len(successful),
            "failed_items": len(failed),
            "success_rate": len(successful) / len(batch_items) if batch_items else 0,
            "total_processing_time_ms": total_time,
            "avg_time_per_item_ms": avg_time,
            "min_time_ms": min((i.processing_time_ms for i in batch_items), default=0),
            "max_time_ms": max((i.processing_time_ms for i in batch_items), default=0)
        }

    def _calculate_uptime(self) -> float:
        """Calculate agent uptime."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Example: GPU Batch Processing Agent
class GPUBatchProcessor(BatchProcessingAgent):
    """
    GPU-optimized batch processing agent.
    Dynamically adjusts batch size based on available VRAM.
    """

    def __init__(self):
        super().__init__(
            agent_id="gpu_batch_processor",
            default_batch_size=32,
            max_batch_size=64
        )
        self.gpu_available = False

    async def initialize(self) -> None:
        """Initialize GPU resources."""
        await super().initialize()

        # Check GPU availability
        try:
            import torch
            self.gpu_available = torch.cuda.is_available()

            if self.gpu_available:
                # Determine optimal batch size based on VRAM
                total_vram = torch.cuda.get_device_properties(0).total_memory
                available_vram = total_vram - torch.cuda.memory_allocated()

                # Heuristic: ~500MB per item
                estimated_batch = int(available_vram * 0.7 / (500 * 1024**2))
                self.optimal_batch_size = min(
                    estimated_batch,
                    self.max_batch_size
                )

                logger.info(
                    "gpu_batch_size_determined",
                    agent_id=self.agent_id,
                    optimal_batch_size=self.optimal_batch_size,
                    available_vram_gb=available_vram / 1024**3
                )
        except ImportError:
            logger.warning(
                "pytorch_not_available",
                agent_id=self.agent_id
            )

    async def _process_single_batch(
        self,
        batch: List[BatchItem]
    ) -> List[Any]:
        """Process batch with GPU acceleration."""
        if not self.gpu_available:
            # Fallback to CPU processing
            return await super()._process_single_batch(batch)

        try:
            import torch

            # Simulate GPU batch processing
            with torch.cuda.device(0):
                # Check VRAM before processing
                current_vram = torch.cuda.memory_allocated() / 1024**3
                threshold_vram = 13.6  # 85% of 16GB

                if current_vram > threshold_vram:
                    logger.warning(
                        "gpu_vram_high",
                        agent_id=self.agent_id,
                        current_vram_gb=current_vram
                    )
                    torch.cuda.empty_cache()

                # Process batch
                results = await super()._process_single_batch(batch)

                return results

        except torch.cuda.OutOfMemoryError:
            logger.error(
                "gpu_oom",
                agent_id=self.agent_id,
                batch_size=len(batch)
            )

            # Reduce batch size for future batches
            self.optimal_batch_size = max(1, self.optimal_batch_size // 2)

            logger.info(
                "batch_size_reduced",
                agent_id=self.agent_id,
                new_batch_size=self.optimal_batch_size
            )

            # Retry with smaller batch
            if len(batch) > 1:
                mid = len(batch) // 2
                results1 = await self._process_single_batch(batch[:mid])
                results2 = await self._process_single_batch(batch[mid:])
                return results1 + results2
            else:
                raise


# Example Usage
async def example_batch_processing():
    """Example of batch processing with GPU optimization."""

    # Create sample items
    items = [f"document_{i}.pdf" for i in range(100)]

    # Create GPU batch processor
    agent = GPUBatchProcessor()
    await agent.initialize()

    # Process items in batches
    result = await agent.process_task({
        "items": items,
        "batch_size": 32,
        "parallel_batches": 2  # Process 2 batches in parallel
    })

    print(f"Success: {result['success']}")
    print(f"Total Time: {result['total_processing_time_ms']}ms")
    print(f"\nBatch Statistics:")
    stats = result["batch_stats"]
    print(f"  Total Items: {stats['total_items']}")
    print(f"  Successful: {stats['successful_items']}")
    print(f"  Failed: {stats['failed_items']}")
    print(f"  Success Rate: {stats['success_rate']:.2%}")
    print(f"  Avg Time per Item: {stats['avg_time_per_item_ms']:.2f}ms")
    print(f"  Min Time: {stats['min_time_ms']}ms")
    print(f"  Max Time: {stats['max_time_ms']}ms")

    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_batch_processing())
```

---

**Fortsetzung folgt mit Patterns 5-7 und weiteren Beispielen...**

Das Dokument wird zu lang. Soll ich:
1. Den Rest der Patterns in separaten Abschnitten hinzufügen?
2. Oder direkt mit den anderen Files fortfahren (skill_catalog.md, etc.)?
