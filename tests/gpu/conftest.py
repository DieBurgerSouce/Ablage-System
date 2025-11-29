"""
Pytest fixtures for GPU backend testing.

This module provides fixtures and markers for testing GPU OCR backends
on RTX 4080 (16GB VRAM).
"""

import os
import sys
from pathlib import Path
from typing import Optional, Generator
from dataclasses import dataclass

import pytest
import pytest_asyncio

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Check for CUDA/PyTorch availability
try:
    import torch
    TORCH_AVAILABLE = torch.cuda.is_available()
    if TORCH_AVAILABLE:
        GPU_NAME = torch.cuda.get_device_name(0)
        GPU_VRAM_GB = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    else:
        GPU_NAME = "No GPU"
        GPU_VRAM_GB = 0.0
except ImportError:
    TORCH_AVAILABLE = False
    GPU_NAME = "PyTorch not installed"
    GPU_VRAM_GB = 0.0


# Skip all tests in this module if GPU not available
pytestmark = pytest.mark.gpu


def pytest_collection_modifyitems(config, items):
    """Skip GPU tests if GPU not available."""
    if not TORCH_AVAILABLE:
        skip_gpu = pytest.mark.skip(reason="GPU not available")
        for item in items:
            if "gpu" in item.keywords:
                item.add_marker(skip_gpu)


@dataclass
class GPUTestContext:
    """Context information for GPU tests."""
    torch_available: bool
    cuda_available: bool
    gpu_name: str
    vram_total_gb: float
    vram_free_gb: float
    cuda_version: str
    cudnn_version: Optional[int]

    @property
    def can_run_deepseek(self) -> bool:
        """Check if DeepSeek (12GB) can run."""
        return self.vram_free_gb >= 12.0

    @property
    def can_run_got_ocr(self) -> bool:
        """Check if GOT-OCR (10GB) can run."""
        return self.vram_free_gb >= 10.0

    @property
    def can_run_surya_gpu(self) -> bool:
        """Check if SuryaGPU (8GB) can run."""
        return self.vram_free_gb >= 8.0

    @property
    def can_run_donut(self) -> bool:
        """Check if Donut (8GB) can run."""
        return self.vram_free_gb >= 8.0


@pytest.fixture(scope="session")
def gpu_context() -> GPUTestContext:
    """Provide GPU context for tests."""
    if not TORCH_AVAILABLE:
        return GPUTestContext(
            torch_available=False,
            cuda_available=False,
            gpu_name="Not available",
            vram_total_gb=0.0,
            vram_free_gb=0.0,
            cuda_version="",
            cudnn_version=None,
        )

    vram_free = (
        torch.cuda.get_device_properties(0).total_memory -
        torch.cuda.memory_allocated(0)
    ) / (1024**3)

    return GPUTestContext(
        torch_available=True,
        cuda_available=True,
        gpu_name=GPU_NAME,
        vram_total_gb=GPU_VRAM_GB,
        vram_free_gb=vram_free,
        cuda_version=torch.version.cuda or "",
        cudnn_version=torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
    )


@pytest.fixture(scope="function")
def clean_gpu_memory():
    """Clean GPU memory before and after each test."""
    if not TORCH_AVAILABLE:
        yield
        return

    # Clear before test
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    yield

    # Clear after test
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    # Force garbage collection
    import gc
    gc.collect()


@pytest.fixture(scope="function")
def gpu_memory_tracker():
    """Track GPU memory usage during test."""
    if not TORCH_AVAILABLE:
        yield None
        return

    class MemoryTracker:
        def __init__(self):
            self.start_allocated = 0.0
            self.peak_allocated = 0.0
            self.end_allocated = 0.0

        def start(self):
            torch.cuda.reset_peak_memory_stats()
            self.start_allocated = torch.cuda.memory_allocated() / (1024**3)

        def stop(self):
            self.peak_allocated = torch.cuda.max_memory_allocated() / (1024**3)
            self.end_allocated = torch.cuda.memory_allocated() / (1024**3)

        @property
        def delta(self) -> float:
            return self.end_allocated - self.start_allocated

        def verify_under_threshold(self, threshold_gb: float = 13.6):
            assert self.peak_allocated < threshold_gb, (
                f"Peak VRAM {self.peak_allocated:.2f}GB exceeded threshold {threshold_gb}GB"
            )

    tracker = MemoryTracker()
    tracker.start()
    yield tracker
    tracker.stop()


@pytest.fixture(scope="module")
def test_images_dir(tmp_path_factory) -> Path:
    """Create test images for GPU backend testing."""
    from PIL import Image, ImageDraw, ImageFont

    test_dir = tmp_path_factory.mktemp("gpu_test_images")

    # Create German text image
    german_img = Image.new('RGB', (800, 600), color='white')
    d = ImageDraw.Draw(german_img)
    d.text((10, 10), "Sehr geehrte Damen und Herren,", fill='black')
    d.text((10, 50), "Rechnung Nr. RE-2024-001", fill='black')
    d.text((10, 90), "Betrag: 1.234,56 EUR", fill='black')
    d.text((10, 130), "IBAN: DE89 3704 0044 0532 0130 00", fill='black')
    d.text((10, 170), "USt-IdNr.: DE123456789", fill='black')
    d.text((10, 210), "Müller GmbH, Größe, Überprüfung", fill='black')
    german_img.save(test_dir / "german_text.png")

    # Create simple test image
    simple_img = Image.new('RGB', (400, 200), color='white')
    d = ImageDraw.Draw(simple_img)
    d.text((10, 10), "Simple Test", fill='black')
    d.text((10, 50), "Hello World", fill='black')
    simple_img.save(test_dir / "simple_text.png")

    # Create complex layout image
    complex_img = Image.new('RGB', (1200, 800), color='white')
    d = ImageDraw.Draw(complex_img)
    # Header
    d.rectangle([0, 0, 1200, 100], fill='lightgray')
    d.text((500, 40), "INVOICE", fill='black')
    # Table-like structure
    for i, y in enumerate([150, 200, 250, 300, 350]):
        d.text((50, y), f"Item {i+1}", fill='black')
        d.text((300, y), f"Description for item {i+1}", fill='black')
        d.text((700, y), f"100,00 EUR", fill='black')
    complex_img.save(test_dir / "complex_layout.png")

    # Create handwritten-style image (simulated)
    handwritten_img = Image.new('RGB', (600, 400), color='white')
    d = ImageDraw.Draw(handwritten_img)
    d.text((10, 10), "Handwritten note", fill='darkblue')
    d.text((10, 50), "Meeting at 14:00", fill='darkblue')
    d.text((10, 90), "Call Muller", fill='darkblue')
    handwritten_img.save(test_dir / "handwritten.png")

    return test_dir


@pytest.fixture
def sample_german_invoice_text() -> str:
    """Expected text content from German invoice image."""
    return """
    Sehr geehrte Damen und Herren,
    Rechnung Nr. RE-2024-001
    Betrag: 1.234,56 EUR
    IBAN: DE89 3704 0044 0532 0130 00
    USt-IdNr.: DE123456789
    Müller GmbH, Größe, Überprüfung
    """.strip()


# OCR Backend fixtures
@pytest.fixture(scope="module")
def surya_gpu_agent():
    """Create SuryaGPU agent for testing."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    try:
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
        agent = SuryaGPUAgent()
        yield agent
        # Cleanup
        if hasattr(agent, 'cleanup'):
            import asyncio
            asyncio.get_event_loop().run_until_complete(agent.cleanup())
    except ImportError as e:
        pytest.skip(f"SuryaGPU agent not available: {e}")


@pytest.fixture(scope="module")
def donut_agent():
    """Create Donut agent for testing."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    try:
        from app.agents.ocr.donut_agent import DonutOCRAgent
        agent = DonutOCRAgent()
        yield agent
        # Cleanup
        if hasattr(agent, 'cleanup'):
            import asyncio
            asyncio.get_event_loop().run_until_complete(agent.cleanup())
    except ImportError as e:
        pytest.skip(f"Donut agent not available: {e}")


@pytest.fixture(scope="module")
def got_ocr_agent():
    """Create GOT-OCR agent for testing."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    try:
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent
        agent = GOTOCRAgent()
        yield agent
        # Cleanup
        if hasattr(agent, 'cleanup'):
            import asyncio
            asyncio.get_event_loop().run_until_complete(agent.cleanup())
    except ImportError as e:
        pytest.skip(f"GOT-OCR agent not available: {e}")


@pytest.fixture(scope="module")
def deepseek_agent():
    """Create DeepSeek agent for testing."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    # Check for BitsAndBytes (required for 4-bit quantization)
    try:
        import bitsandbytes
    except ImportError:
        pytest.skip("BitsAndBytes not available - required for DeepSeek 4-bit quantization")

    try:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        agent = DeepSeekAgent()
        yield agent
        # Cleanup
        if hasattr(agent, 'cleanup'):
            import asyncio
            asyncio.get_event_loop().run_until_complete(agent.cleanup())
    except ImportError as e:
        pytest.skip(f"DeepSeek agent not available: {e}")


@pytest.fixture
def gpu_recovery_manager():
    """Create GPU recovery manager for testing."""
    from app.core.gpu_recovery import GPURecoveryManager
    return GPURecoveryManager()


@pytest.fixture
def gpu_manager():
    """Create GPU manager for testing."""
    from app.gpu_manager import GPUManager
    return GPUManager()


# Markers for conditional skipping
@pytest.fixture
def requires_12gb_vram(gpu_context):
    """Skip test if less than 12GB VRAM available."""
    if not gpu_context.can_run_deepseek:
        pytest.skip(f"Requires 12GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available")


@pytest.fixture
def requires_10gb_vram(gpu_context):
    """Skip test if less than 10GB VRAM available."""
    if not gpu_context.can_run_got_ocr:
        pytest.skip(f"Requires 10GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available")


@pytest.fixture
def requires_8gb_vram(gpu_context):
    """Skip test if less than 8GB VRAM available."""
    if not gpu_context.can_run_surya_gpu:
        pytest.skip(f"Requires 8GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available")


# Windows skip marker for BitsAndBytes
@pytest.fixture
def skip_on_windows():
    """Skip test on Windows (BitsAndBytes compatibility)."""
    if sys.platform == "win32":
        pytest.skip("BitsAndBytes has limited Windows support - run in WSL2/Docker")
