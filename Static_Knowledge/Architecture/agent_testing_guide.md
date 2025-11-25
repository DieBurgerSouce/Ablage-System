# Agent Testing Guide - Comprehensive Testing Strategies
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Test Types](#test-types)
3. [Unit Testing Agents](#unit-testing-agents)
4. [Integration Testing](#integration-testing)
5. [E2E Testing](#e2e-testing)
6. [GPU Testing Strategies](#gpu-testing-strategies)
7. [Hook Testing](#hook-testing)
8. [Skill Testing](#skill-testing)
9. [Performance Testing](#performance-testing)
10. [Test Data Management](#test-data-management)
11. [CI/CD Integration](#cicd-integration)

---

## Testing Philosophy

### Testing Pyramid für Agents

```
                    ┌─────────┐
                    │  E2E    │  Few, Critical Workflows
                    │  Tests  │  (5%)
                    └─────────┘
                ┌──────────────────┐
                │   Integration    │  Agent Interactions
                │      Tests       │  (15%)
                └──────────────────┘
          ┌─────────────────────────────┐
          │        Unit Tests            │  Individual Components
          │  (Agents, Sub-Agents,        │  (80%)
          │   Skills, Hooks)             │
          └─────────────────────────────┘
```

### Testing Principles

1. **Fast**: Unit tests should run in milliseconds
2. **Isolated**: Each test independent, no shared state
3. **Repeatable**: Same input = same output, every time
4. **Self-Validating**: Clear pass/fail, no manual inspection
5. **Timely**: Written alongside (or before) production code

---

## Test Types

### 1. Unit Tests

**Purpose:** Test individual components in isolation

**Target:** Single agent, sub-agent, skill, or hook

**Mocking:** Mock all external dependencies

**Example:**
```python
# Test single agent method
async def test_ocr_agent_backend_selection():
    agent = OCRProcessingAgent()
    backend = agent._select_backend({"complexity_score": 8})
    assert backend == "deepseek"
```

### 2. Integration Tests

**Purpose:** Test interactions between components

**Target:** Multiple agents, agent + sub-agents, agent + hooks

**Mocking:** Mock only external services (DB, Redis, MinIO)

**Example:**
```python
# Test agent with hooks
async def test_agent_with_hooks():
    agent = OCRProcessingAgent()
    agent.register_hook(HookTrigger.POST_PROCESS, MetricsHook())

    result = await agent.process_task(task)

    # Verify hook executed
    assert metrics_collected
```

### 3. E2E Tests

**Purpose:** Test complete workflows end-to-end

**Target:** Full document processing pipeline

**Mocking:** Minimal mocking (only external APIs)

**Example:**
```python
# Test full document processing
async def test_complete_ocr_pipeline():
    # Upload document
    doc = upload_document("invoice.pdf")

    # Process
    result = process_document(doc.id)

    # Verify
    assert result.extracted_text
    assert result.validation.passed
```

---

## Unit Testing Agents

### Test Structure

```python
# tests/unit/agents/test_ocr_processing_agent.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent
from Execution_Layer.Sub_Agents.ocr_backend_agent import OCRBackendAgent


class TestOCRProcessingAgent:
    """Test suite for OCRProcessingAgent."""

    @pytest.fixture
    async def agent(self):
        """Create agent instance for testing."""
        agent = OCRProcessingAgent()
        await agent.initialize()
        yield agent
        await agent.shutdown()

    @pytest.fixture
    def mock_gpu_manager(self):
        """Mock GPU manager."""
        with patch('app.gpu_manager.GPUManager') as mock:
            mock_instance = Mock()
            mock_instance.is_available.return_value = True
            mock_instance.get_status.return_value = {
                "available": True,
                "free_vram_gb": 14.0,
                "vram_usage_percent": 12.5
            }
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_classifier(self):
        """Mock document classifier."""
        with patch('app.services.document_classifier.DocumentClassifier') as mock:
            mock_instance = AsyncMock()
            mock_instance.classify.return_value = {
                "document_type": "rechnung",
                "complexity_score": 5,
                "has_handwriting": False,
                "has_fraktur": False
            }
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent.status == AgentStatus.READY
        assert agent.agent_id == "ocr_processing_agent"
        assert agent.metrics["tasks_completed"] == 0

    @pytest.mark.asyncio
    async def test_backend_selection_simple_invoice(
        self,
        agent,
        mock_gpu_manager,
        mock_classifier
    ):
        """Test backend selection for simple invoice."""
        # Setup
        task = {
            "document_id": "doc_123",
            "image_path": "/path/to/invoice.pdf"
        }

        # Execute
        result = await agent.process_task(task)

        # Verify
        assert result["success"] is True
        assert result["backend_used"] == "got_ocr"  # Simple invoice
        assert result["selection_reason"] == "simple_invoice_fast_processing"

    @pytest.mark.asyncio
    async def test_backend_selection_complex_document(
        self,
        agent,
        mock_gpu_manager,
        mock_classifier
    ):
        """Test backend selection for complex document."""
        # Setup: Mock complex classification
        mock_classifier.classify.return_value = {
            "document_type": "vertrag",
            "complexity_score": 8,
            "has_handwriting": True,
            "has_fraktur": False
        }

        task = {
            "document_id": "doc_456",
            "image_path": "/path/to/contract.pdf"
        }

        # Execute
        result = await agent.process_task(task)

        # Verify
        assert result["success"] is True
        assert result["backend_used"] == "deepseek"  # Complex document
        assert "handwriting" in result["selection_reason"].lower()

    @pytest.mark.asyncio
    async def test_gpu_fallback_when_unavailable(
        self,
        agent,
        mock_gpu_manager,
        mock_classifier
    ):
        """Test fallback to CPU when GPU unavailable."""
        # Setup: Mock GPU unavailable
        mock_gpu_manager.is_available.return_value = False
        mock_gpu_manager.get_status.return_value = {
            "available": False
        }

        task = {
            "document_id": "doc_789",
            "image_path": "/path/to/document.pdf"
        }

        # Execute
        result = await agent.process_task(task)

        # Verify
        assert result["success"] is True
        assert result["backend_used"] == "surya"  # CPU fallback
        assert result["selection_reason"] == "gpu_not_available"

    @pytest.mark.asyncio
    async def test_metrics_updated_on_success(self, agent):
        """Test metrics are updated after successful processing."""
        # Setup
        with patch.object(agent, '_do_process_task', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {
                "success": True,
                "backend_used": "got_ocr",
                "processing_time_ms": 1234
            }

            task = {"document_id": "doc_123"}

            # Execute
            await agent.process_task(task)

            # Verify
            assert agent.metrics["tasks_completed"] == 1
            assert agent.metrics["tasks_failed"] == 0
            assert agent.metrics["total_processing_time_ms"] >= 1234

    @pytest.mark.asyncio
    async def test_metrics_updated_on_failure(self, agent):
        """Test metrics are updated after failure."""
        # Setup
        with patch.object(agent, '_do_process_task', new_callable=AsyncMock) as mock_process:
            mock_process.side_effect = RuntimeError("Processing failed")

            task = {"document_id": "doc_456"}

            # Execute & Verify
            with pytest.raises(RuntimeError, match="Processing failed"):
                await agent.process_task(task)

            assert agent.metrics["tasks_completed"] == 0
            assert agent.metrics["tasks_failed"] == 1

    @pytest.mark.asyncio
    async def test_agent_shutdown_cleanup(self, agent):
        """Test agent cleanup on shutdown."""
        # Execute
        await agent.shutdown()

        # Verify
        assert agent.status == AgentStatus.STOPPED
```

### Testing Sub-Agents

```python
# tests/unit/sub_agents/test_validation_sub_agent.py
import pytest
from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent


class TestValidationSubAgent:
    """Test suite for ValidationSubAgent."""

    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return ValidationSubAgent()

    @pytest.mark.asyncio
    async def test_validate_german_text_with_umlauts(self, validator):
        """Test validation of correct German text."""
        result = await validator.validate_german_text(
            text="Müller GmbH, 10.000,00 €",
            check_umlauts=True,
            check_currency=True
        )

        assert result["is_valid"] is True
        assert result["umlaut_accuracy"] == 1.0
        assert result["currency_format_correct"] is True
        assert len(result["warnings"]) == 0

    @pytest.mark.asyncio
    async def test_validate_german_text_missing_umlauts(self, validator):
        """Test detection of missing umlauts."""
        result = await validator.validate_german_text(
            text="Muller GmbH",  # Missing ü
            check_umlauts=True
        )

        assert result["is_valid"] is False
        assert result["umlaut_accuracy"] < 1.0
        assert len(result["warnings"]) > 0
        assert any("umlaut" in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_validate_currency_format(self, validator):
        """Test German currency format validation."""
        # Correct format
        result = await validator.validate_german_text(
            text="Betrag: 1.234,56 €",
            check_currency=True
        )
        assert result["currency_format_correct"] is True

        # Incorrect format (English)
        result = await validator.validate_german_text(
            text="Amount: 1,234.56 €",
            check_currency=True
        )
        assert result["currency_format_correct"] is False

    @pytest.mark.asyncio
    async def test_validate_date_format(self, validator):
        """Test German date format validation."""
        # Correct format (DD.MM.YYYY)
        result = await validator.validate_german_text(
            text="Datum: 23.01.2025",
            check_dates=True
        )
        assert len(result["dates_found"]) == 1
        assert result["dates_found"][0] == "23.01.2025"

        # Incorrect format (MM/DD/YYYY)
        result = await validator.validate_german_text(
            text="Date: 01/23/2025",
            check_dates=True
        )
        assert len(result["dates_found"]) == 0
```

---

## Integration Testing

### Testing Agent Interactions

```python
# tests/integration/test_agent_pipeline.py
import pytest
from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent
from Execution_Layer.Agents.document_classifier_agent import DocumentClassifierAgent
from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ocr_pipeline_with_classification():
    """Test OCR pipeline with document classification."""
    # Setup
    classifier = DocumentClassifierAgent()
    await classifier.initialize()

    ocr_agent = OCRProcessingAgent()
    await ocr_agent.initialize()

    validator = ValidationSubAgent()

    # Classify document
    classification = await classifier.process_task({
        "document_id": "doc_123",
        "image_path": "tests/fixtures/invoice_sample.pdf"
    })

    # Process with OCR
    ocr_result = await ocr_agent.process_task({
        "document_id": "doc_123",
        "image_path": "tests/fixtures/invoice_sample.pdf",
        "classification": classification
    })

    # Validate result
    validation = await validator.validate_german_text(
        ocr_result["extracted_text"]
    )

    # Verify
    assert classification["document_type"] == "rechnung"
    assert ocr_result["success"] is True
    assert ocr_result["extracted_text"]
    assert validation["is_valid"] is True

    # Cleanup
    await classifier.shutdown()
    await ocr_agent.shutdown()
```

### Testing with Hooks

```python
# tests/integration/test_agent_with_hooks.py
import pytest
from Execution_Layer.Agents.simple_task_agent import SimpleTaskAgent
from Execution_Layer.Hooks.logging_hook import LoggingHook
from Execution_Layer.Hooks.metrics_hook import MetricsHook
from Execution_Layer.Hooks.base_hook import HookTrigger


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_with_multiple_hooks():
    """Test agent execution with multiple hooks."""
    # Setup
    agent = SimpleTaskAgent()
    await agent.initialize()

    # Register hooks
    logging_hook = LoggingHook()
    metrics_hook = MetricsHook()

    agent.register_hook(HookTrigger.PRE_PROCESS, logging_hook)
    agent.register_hook(HookTrigger.POST_PROCESS, logging_hook)
    agent.register_hook(HookTrigger.POST_PROCESS, metrics_hook)

    # Process task
    result = await agent.process_task({
        "input_data": "test",
        "operation": "uppercase"
    })

    # Verify task result
    assert result["success"] is True
    assert result["output_data"] == "TEST"

    # Verify hooks executed
    assert logging_hook.execution_count == 2  # PRE + POST
    assert metrics_hook.execution_count == 1  # POST only

    # Cleanup
    await agent.shutdown()
```

---

## GPU Testing Strategies

### GPU Availability Tests

```python
# tests/gpu/test_gpu_batch_processing.py
import pytest
import torch


@pytest.mark.gpu
@pytest.mark.skipif(
    not torch.cuda.is_available(),
    reason="GPU not available"
)
class TestGPUBatchProcessing:
    """GPU-specific tests (only run when GPU available)."""

    @pytest.mark.asyncio
    async def test_batch_processing_within_vram_limits(self):
        """Test batch processing stays within VRAM limits."""
        from Execution_Layer.Agents.batch_processing_agent import GPUBatchProcessor

        # Setup
        agent = GPUBatchProcessor()
        await agent.initialize()

        # Create large batch
        items = [f"document_{i}.pdf" for i in range(100)]

        # Reset peak memory stats
        torch.cuda.reset_peak_memory_stats()

        # Process
        result = await agent.process_task({
            "items": items,
            "batch_size": 32
        })

        # Check VRAM usage
        peak_memory_gb = torch.cuda.max_memory_allocated() / 1024**3

        # Verify
        assert result["success"] is True
        assert peak_memory_gb < 13.6  # 85% of 16GB
        assert len(result["results"]) == 100

        await agent.shutdown()

    @pytest.mark.asyncio
    async def test_oom_recovery(self):
        """Test automatic batch size reduction on OOM."""
        from Execution_Layer.Agents.batch_processing_agent import GPUBatchProcessor

        # Setup
        agent = GPUBatchProcessor()
        await agent.initialize()

        # Simulate OOM with very large batch
        with patch.object(agent, '_process_single_batch') as mock_process:
            # First call raises OOM
            mock_process.side_effect = [
                torch.cuda.OutOfMemoryError(),
                [Mock()] * 16,  # Retry with smaller batch succeeds
                [Mock()] * 16
            ]

            items = [f"doc_{i}" for i in range(32)]

            # Process (should retry with smaller batch)
            result = await agent.process_task({
                "items": items,
                "batch_size": 32
            })

            # Verify batch size was reduced
            assert agent.optimal_batch_size == 16  # Halved from 32

        await agent.shutdown()

    @pytest.mark.asyncio
    async def test_gpu_cache_clearing(self):
        """Test GPU cache is cleared between batches."""
        from app.gpu_manager import GPUManager

        gpu = GPUManager()

        # Allocate some memory
        tensor = torch.randn(1000, 1000, device='cuda')
        allocated_before = torch.cuda.memory_allocated()

        # Clear cache
        gpu.clear_cache()

        # Delete tensor and clear again
        del tensor
        gpu.clear_cache()

        allocated_after = torch.cuda.memory_allocated()

        # Verify memory freed
        assert allocated_after < allocated_before
```

### GPU Fallback Tests

```python
@pytest.mark.asyncio
async def test_cpu_fallback_when_gpu_unavailable():
    """Test fallback to CPU when GPU unavailable."""
    from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

    agent = OCRProcessingAgent()
    await agent.initialize()

    # Mock GPU unavailable
    with patch('app.gpu_manager.GPUManager.is_available', return_value=False):
        result = await agent.process_task({
            "document_id": "doc_123",
            "image_path": "/path/to/doc.pdf"
        })

        # Should use CPU backend (surya)
        assert result["backend_used"] == "surya"
        assert result["success"] is True

    await agent.shutdown()
```

---

## Performance Testing

### Load Testing

```python
# tests/performance/test_agent_load.py
import pytest
import asyncio
from datetime import datetime


@pytest.mark.performance
@pytest.mark.asyncio
async def test_agent_concurrent_load():
    """Test agent performance under concurrent load."""
    from Execution_Layer.Agents.simple_task_agent import SimpleTaskAgent

    agent = SimpleTaskAgent()
    await agent.initialize()

    # Create concurrent tasks
    num_tasks = 100
    tasks = [
        agent.process_task({"input_data": f"test_{i}", "operation": "uppercase"})
        for i in range(num_tasks)
    ]

    # Execute concurrently
    start = datetime.utcnow()
    results = await asyncio.gather(*tasks)
    duration = (datetime.utcnow() - start).total_seconds()

    # Verify
    assert len(results) == num_tasks
    assert all(r["success"] for r in results)

    # Performance assertions
    avg_time_per_task = duration / num_tasks
    assert avg_time_per_task < 0.1  # Less than 100ms per task

    print(f"Processed {num_tasks} tasks in {duration:.2f}s")
    print(f"Average time per task: {avg_time_per_task*1000:.2f}ms")

    await agent.shutdown()


@pytest.mark.performance
@pytest.mark.asyncio
async def test_batch_processing_throughput():
    """Test batch processing throughput."""
    from Execution_Layer.Agents.batch_processing_agent import BatchProcessingAgent

    agent = BatchProcessingAgent(default_batch_size=32)
    await agent.initialize()

    # Large dataset
    num_items = 1000
    items = [f"item_{i}" for i in range(num_items)]

    # Process
    start = datetime.utcnow()
    result = await agent.process_task({
        "items": items,
        "batch_size": 32,
        "parallel_batches": 2
    })
    duration = (datetime.utcnow() - start).total_seconds()

    # Verify
    assert result["success"] is True
    assert len(result["results"]) == num_items

    # Performance metrics
    throughput = num_items / duration
    print(f"Processed {num_items} items in {duration:.2f}s")
    print(f"Throughput: {throughput:.2f} items/sec")

    # Assert minimum throughput
    assert throughput > 100  # At least 100 items/sec

    await agent.shutdown()
```

### Memory Leak Detection

```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_memory_leak_detection():
    """Test for memory leaks in repeated processing."""
    import psutil
    import os

    from Execution_Layer.Agents.simple_task_agent import SimpleTaskAgent

    agent = SimpleTaskAgent()
    await agent.initialize()

    process = psutil.Process(os.getpid())

    # Baseline memory
    baseline_memory_mb = process.memory_info().rss / 1024**2

    # Process many tasks
    for i in range(1000):
        await agent.process_task({
            "input_data": f"test_{i}",
            "operation": "uppercase"
        })

    # Final memory
    final_memory_mb = process.memory_info().rss / 1024**2

    memory_increase_mb = final_memory_mb - baseline_memory_mb

    print(f"Baseline memory: {baseline_memory_mb:.2f} MB")
    print(f"Final memory: {final_memory_mb:.2f} MB")
    print(f"Memory increase: {memory_increase_mb:.2f} MB")

    # Assert memory increase is reasonable
    assert memory_increase_mb < 100  # Less than 100MB increase

    await agent.shutdown()
```

---

## Test Data Management

### Test Fixtures

```python
# tests/fixtures/documents.py
import pytest
from pathlib import Path


@pytest.fixture
def sample_invoice_pdf():
    """Sample German invoice PDF for testing."""
    fixture_path = Path("tests/fixtures/sample_invoice_de.pdf")
    assert fixture_path.exists(), "Sample invoice not found"
    return str(fixture_path)


@pytest.fixture
def sample_contract_pdf():
    """Sample German contract PDF for testing."""
    fixture_path = Path("tests/fixtures/sample_contract_de.pdf")
    assert fixture_path.exists(), "Sample contract not found"
    return str(fixture_path)


@pytest.fixture
def sample_ocr_text():
    """Sample OCR text with German content."""
    return """
Rechnung

Rechnungsnummer: RE-2025-00123
Rechnungsdatum: 23.01.2025

Müller GmbH & Co. KG
Hauptstraße 123
10115 Berlin

Artikel:
- Produkt A: 1.000,00 €
- Produkt B: 2.500,00 €

Nettobetrag: 3.500,00 €
MwSt. 19%: 665,00 €
Bruttobetrag: 4.165,00 €
"""


@pytest.fixture
def mock_classification():
    """Mock document classification result."""
    return {
        "document_type": "rechnung",
        "complexity_score": 5,
        "has_tables": True,
        "has_handwriting": False,
        "has_fraktur": False,
        "text_density": 0.7,
        "image_quality": 0.9,
        "confidence": 0.95
    }
```

### Test Data Generation

```python
# tests/utils/test_data_generator.py
from typing import List, Dict, Any
from datetime import datetime, timedelta
import random


class TestDataGenerator:
    """Generate test data for agent testing."""

    @staticmethod
    def generate_document_batch(count: int = 100) -> List[Dict[str, Any]]:
        """Generate batch of test documents."""
        documents = []

        for i in range(count):
            doc = {
                "document_id": f"doc_{i:06d}",
                "filename": f"document_{i}.pdf",
                "document_type": random.choice([
                    "rechnung", "vertrag", "brief", "formular"
                ]),
                "pages": random.randint(1, 10),
                "upload_date": (
                    datetime.utcnow() - timedelta(days=random.randint(0, 365))
                ).isoformat()
            }
            documents.append(doc)

        return documents

    @staticmethod
    def generate_ocr_tasks(count: int = 50) -> List[Dict[str, Any]]:
        """Generate batch of OCR tasks."""
        tasks = []

        for i in range(count):
            task = {
                "id": f"task_{i:06d}",
                "type": "ocr_processing",
                "document_id": f"doc_{i:06d}",
                "image_path": f"/tmp/test_{i}.pdf",
                "backend": random.choice(["auto", "deepseek", "got_ocr", "surya"]),
                "priority": random.choice(["low", "normal", "high"])
            }
            tasks.append(task)

        return tasks
```

---

## CI/CD Integration

### pytest Configuration

```ini
# pytest.ini
[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (slower, more dependencies)
    e2e: End-to-end tests (slow, full system)
    gpu: GPU-dependent tests (skip if GPU unavailable)
    performance: Performance/load tests
    slow: Slow tests (skip in quick runs)

# Coverage
addopts =
    --verbose
    --strict-markers
    --cov=Execution_Layer
    --cov=app
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
    -ra

# Asyncio
asyncio_mode = auto

# Timeout
timeout = 300
```

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test Agents

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: |
          pytest tests/unit -m unit -v --cov

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: unit-tests

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run integration tests
        run: |
          pytest tests/integration -m integration -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost/test
          REDIS_URL: redis://localhost:6379

  gpu-tests:
    name: GPU Tests
    runs-on: [self-hosted, gpu]
    needs: unit-tests

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run GPU tests
        run: |
          pytest tests/gpu -m gpu -v

      - name: Check GPU status
        run: nvidia-smi
```

---

**Document Status:** ✅ **COMPLETE**

Comprehensive testing guide mit:
- ✅ Test Pyramid & Philosophy
- ✅ Unit Testing (Agents, Sub-Agents, Hooks)
- ✅ Integration Testing
- ✅ GPU Testing Strategies
- ✅ Performance Testing
- ✅ Test Data Management
- ✅ CI/CD Integration
