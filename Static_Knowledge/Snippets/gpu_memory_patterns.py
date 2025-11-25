"""
GPU Memory Management Patterns
Reusable code snippets for RTX 4080 VRAM optimization
"""

import torch
from contextlib import contextmanager
from typing import Callable, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Pattern 1: GPU Memory Guard (Context Manager)
# ============================================================================

@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6, auto_cleanup: bool = True):
    """
    Context manager to ensure GPU memory stays below threshold.

    Args:
        threshold_gb: Max VRAM usage (default: 13.6GB = 85% of 16GB)
        auto_cleanup: Automatically clear cache if threshold exceeded

    Usage:
        with gpu_memory_guard(threshold_gb=13.6):
            result = model.process_batch(images)
    """
    initial_memory = 0
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        initial_memory = torch.cuda.memory_allocated()

    try:
        yield
    finally:
        if torch.cuda.is_available():
            current_memory_gb = torch.cuda.memory_allocated() / (1024 ** 3)
            peak_memory_gb = torch.cuda.max_memory_allocated() / (1024 ** 3)

            if peak_memory_gb > threshold_gb:
                logger.warning(
                    "gpu_memory_exceeded_threshold",
                    peak_memory_gb=round(peak_memory_gb, 2),
                    threshold_gb=threshold_gb,
                    auto_cleanup=auto_cleanup
                )

                if auto_cleanup:
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    logger.info("gpu_cache_cleared")


# ============================================================================
# Pattern 2: Dynamic Batch Sizing with OOM Recovery
# ============================================================================

async def process_with_dynamic_batch_size(
    items: list,
    process_fn: Callable,
    initial_batch_size: int = 32,
    min_batch_size: int = 1,
    reduction_factor: float = 0.5
) -> list:
    """
    Process items with automatic batch size reduction on OOM.

    Args:
        items: List of items to process
        process_fn: Async function to process batch
        initial_batch_size: Starting batch size
        min_batch_size: Minimum batch size before giving up
        reduction_factor: Factor to reduce batch size (0.5 = 50%)

    Returns:
        List of processed results

    Usage:
        async def process_batch(images):
            return model(images)

        results = await process_with_dynamic_batch_size(
            images,
            process_batch,
            initial_batch_size=32
        )
    """
    batch_size = initial_batch_size
    results = []
    i = 0

    while i < len(items):
        batch = items[i:i + batch_size]

        try:
            batch_results = await process_fn(batch)
            results.extend(batch_results)
            i += batch_size

            logger.debug(
                "batch_processed",
                batch_size=batch_size,
                progress=f"{i}/{len(items)}"
            )

        except torch.cuda.OutOfMemoryError as e:
            if batch_size <= min_batch_size:
                logger.error("oom_min_batch_size_reached", batch_size=batch_size)
                raise RuntimeError(
                    f"OOM even with minimum batch size {min_batch_size}"
                ) from e

            # Reduce batch size and retry
            new_batch_size = max(min_batch_size, int(batch_size * reduction_factor))
            logger.warning(
                "oom_reducing_batch_size",
                old_batch_size=batch_size,
                new_batch_size=new_batch_size
            )

            torch.cuda.empty_cache()
            batch_size = new_batch_size
            # Don't increment i, retry same batch with smaller size

    return results


# ============================================================================
# Pattern 3: GPU Memory Profiler Decorator
# ============================================================================

def profile_gpu_memory(log_level: str = "debug"):
    """
    Decorator to profile GPU memory usage of a function.

    Usage:
        @profile_gpu_memory(log_level="info")
        async def process_document(doc_id):
            # ... processing ...
            return result
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            if not torch.cuda.is_available():
                return await func(*args, **kwargs)

            torch.cuda.reset_peak_memory_stats()
            initial_allocated = torch.cuda.memory_allocated()
            initial_reserved = torch.cuda.memory_reserved()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                final_allocated = torch.cuda.memory_allocated()
                final_reserved = torch.cuda.memory_reserved()
                peak_allocated = torch.cuda.max_memory_allocated()

                memory_stats = {
                    "function": func.__name__,
                    "initial_allocated_mb": initial_allocated / (1024 ** 2),
                    "final_allocated_mb": final_allocated / (1024 ** 2),
                    "peak_allocated_mb": peak_allocated / (1024 ** 2),
                    "allocated_delta_mb": (final_allocated - initial_allocated) / (1024 ** 2),
                    "reserved_delta_mb": (final_reserved - initial_reserved) / (1024 ** 2)
                }

                log_fn = getattr(logger, log_level)
                log_fn("gpu_memory_profile", **memory_stats)

        return wrapper
    return decorator


# ============================================================================
# Pattern 4: Model Loading with VRAM Check
# ============================================================================

def load_model_with_vram_check(
    model_loader: Callable,
    required_vram_gb: float,
    model_name: str
) -> torch.nn.Module:
    """
    Load model with VRAM availability check.

    Args:
        model_loader: Function that loads and returns the model
        required_vram_gb: Minimum VRAM required (GB)
        model_name: Name for logging

    Returns:
        Loaded model on GPU or CPU

    Raises:
        RuntimeError: If GPU required but unavailable

    Usage:
        def load_deepseek():
            return DeepSeekModel.from_pretrained(...)

        model = load_model_with_vram_check(
            load_deepseek,
            required_vram_gb=12.0,
            model_name="deepseek-janus-pro"
        )
    """
    if not torch.cuda.is_available():
        logger.warning(
            "gpu_unavailable_for_model",
            model=model_name,
            required_vram_gb=required_vram_gb
        )
        raise RuntimeError(f"GPU required for {model_name} but not available")

    # Check available VRAM
    total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    allocated_vram_gb = torch.cuda.memory_allocated() / (1024 ** 3)
    available_vram_gb = total_vram_gb - allocated_vram_gb

    if available_vram_gb < required_vram_gb:
        logger.error(
            "insufficient_vram",
            model=model_name,
            required_gb=required_vram_gb,
            available_gb=round(available_vram_gb, 2),
            total_gb=round(total_vram_gb, 2)
        )
        raise RuntimeError(
            f"Insufficient VRAM for {model_name}: "
            f"need {required_vram_gb}GB, have {available_vram_gb:.2f}GB"
        )

    logger.info(
        "loading_model",
        model=model_name,
        required_vram_gb=required_vram_gb,
        available_vram_gb=round(available_vram_gb, 2)
    )

    # Load model
    model = model_loader()
    model = model.cuda()
    model.eval()

    # Warm-up: compile CUDA kernels
    with torch.no_grad():
        dummy_input = torch.randn(1, 3, 224, 224).cuda()
        _ = model(dummy_input)

    actual_vram_gb = torch.cuda.memory_allocated() / (1024 ** 3)
    logger.info(
        "model_loaded",
        model=model_name,
        actual_vram_gb=round(actual_vram_gb, 2)
    )

    return model


# ============================================================================
# Pattern 5: GPU Fallback Wrapper
# ============================================================================

async def process_with_gpu_fallback(
    process_gpu_fn: Callable,
    process_cpu_fn: Callable,
    *args,
    **kwargs
) -> Any:
    """
    Try GPU processing, fallback to CPU on OOM.

    Args:
        process_gpu_fn: Async function for GPU processing
        process_cpu_fn: Async function for CPU processing
        *args, **kwargs: Arguments passed to both functions

    Returns:
        Processing result with metadata

    Usage:
        result = await process_with_gpu_fallback(
            process_gpu_fn=deepseek.process,
            process_cpu_fn=surya.process,
            document_id="abc123"
        )
    """
    try:
        result = await process_gpu_fn(*args, **kwargs)
        result.metadata = getattr(result, 'metadata', {})
        result.metadata['backend_used'] = 'gpu'
        result.metadata['fallback_used'] = False
        return result

    except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
        logger.warning(
            "gpu_processing_failed_falling_back_to_cpu",
            error=str(e),
            error_type=type(e).__name__
        )

        # Clear GPU cache before CPU processing
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        # CPU fallback
        result = await process_cpu_fn(*args, **kwargs)
        result.metadata = getattr(result, 'metadata', {})
        result.metadata['backend_used'] = 'cpu'
        result.metadata['fallback_used'] = True
        result.metadata['fallback_reason'] = 'gpu_oom'

        return result


# ============================================================================
# Pattern 6: Batch Processing with Memory Monitoring
# ============================================================================

class GPUBatchProcessor:
    """
    Intelligent batch processor with VRAM monitoring.

    Automatically adjusts batch size based on available memory.
    """

    def __init__(
        self,
        max_batch_size: int = 32,
        vram_safety_margin: float = 0.15  # 15%
    ):
        self.max_batch_size = max_batch_size
        self.vram_safety_margin = vram_safety_margin
        self.optimal_batch_size = self._find_optimal_batch_size()

    def _find_optimal_batch_size(self) -> int:
        """Calculate optimal batch size based on available VRAM."""
        if not torch.cuda.is_available():
            return 1

        total_memory = torch.cuda.get_device_properties(0).total_memory
        allocated = torch.cuda.memory_allocated()
        available = total_memory - allocated

        # Apply safety margin
        usable = available * (1 - self.vram_safety_margin)

        # Heuristic: ~500MB per image for DeepSeek
        estimated_per_item = 500 * (1024 ** 2)
        estimated_batch = int(usable / estimated_per_item)

        optimal = min(estimated_batch, self.max_batch_size)

        logger.info(
            "calculated_optimal_batch_size",
            optimal_batch_size=optimal,
            available_vram_gb=available / (1024 ** 3),
            safety_margin=self.vram_safety_margin
        )

        return max(1, optimal)

    async def process_batches(
        self,
        items: list,
        process_fn: Callable
    ) -> list:
        """Process items in optimal batches with OOM recovery."""
        return await process_with_dynamic_batch_size(
            items,
            process_fn,
            initial_batch_size=self.optimal_batch_size,
            min_batch_size=1,
            reduction_factor=0.5
        )


# ============================================================================
# Usage Examples
# ============================================================================

if __name__ == "__main__":
    # Example 1: Memory guard
    async def example_memory_guard():
        with gpu_memory_guard(threshold_gb=13.6):
            # Your GPU-intensive code here
            images = torch.randn(32, 3, 224, 224).cuda()
            results = model(images)

    # Example 2: Dynamic batch sizing
    async def example_dynamic_batching():
        images = load_images(100)

        async def process_batch(batch):
            return model(torch.stack(batch).cuda())

        results = await process_with_dynamic_batch_size(
            images,
            process_batch,
            initial_batch_size=32
        )

    # Example 3: GPU fallback
    async def example_gpu_fallback():
        async def gpu_process(doc_id):
            return await deepseek.process(doc_id)

        async def cpu_process(doc_id):
            return await surya.process(doc_id)

        result = await process_with_gpu_fallback(
            gpu_process,
            cpu_process,
            doc_id="abc123"
        )

    # Example 4: Batch processor
    async def example_batch_processor():
        processor = GPUBatchProcessor(max_batch_size=32)

        images = load_images(1000)
        results = await processor.process_batches(images, model.process)
