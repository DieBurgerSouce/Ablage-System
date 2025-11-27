"""Batch Processing Service with GPU optimization."""

import asyncio
import structlog
from typing import List, Dict, Any, Optional
from pathlib import Path
import torch
import time
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger(__name__)


class BatchProcessor:
    """Optimized batch processing for multiple documents."""

    def __init__(self, backend_manager, max_batch_size: int = 32):
        """
        Initialize batch processor.

        Args:
            backend_manager: Backend manager for OCR processing
            max_batch_size: Maximum documents to process in parallel
        """
        self.backend_manager = backend_manager
        self.max_batch_size = max_batch_size
        self.optimal_batch_size = self._calculate_optimal_batch_size()

        # Thread pool for parallel I/O operations
        self.executor = ThreadPoolExecutor(max_workers=4)

        logger.info("batch_processor_initialized", optimal_batch_size=self.optimal_batch_size)

    def _calculate_optimal_batch_size(self) -> int:
        """Calculate optimal batch size based on available resources."""
        if torch.cuda.is_available():
            # GPU available - use memory-based calculation
            total_memory = torch.cuda.get_device_properties(0).total_memory
            allocated = torch.cuda.memory_allocated()
            available = total_memory - allocated

            # Estimate ~500MB per document for GPU processing
            memory_per_doc_mb = 500
            estimated_batch = int(available * 0.7 / (memory_per_doc_mb * 1024**2))

            # Limit to reasonable range
            optimal = min(max(estimated_batch, 2), self.max_batch_size)
            logger.info("gpu_batch_optimization", optimal_batch_size=optimal, available_gb=round(available/1024**3, 1))
            return optimal
        else:
            # CPU only - conservative batch size
            import psutil
            cpu_count = psutil.cpu_count(logical=False) or 1
            return min(cpu_count, 4)

    async def process_batch(
        self,
        file_paths: List[str],
        backend: str = "auto",
        language: str = "de",
        progress_callback: Optional[callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process multiple documents in optimized batches.

        Args:
            file_paths: List of document paths to process
            backend: OCR backend to use ("auto" for automatic selection)
            language: Target language for OCR
            progress_callback: Optional callback for progress updates
            **kwargs: Additional backend-specific parameters

        Returns:
            Batch processing results with statistics
        """
        start_time = time.time()
        total_docs = len(file_paths)
        results = []
        errors = []

        logger.info("batch_processing_started", total_documents=total_docs)

        # Process in optimized chunks
        for i in range(0, total_docs, self.optimal_batch_size):
            chunk = file_paths[i:i + self.optimal_batch_size]
            chunk_size = len(chunk)

            logger.info("processing_chunk", chunk_number=i//self.optimal_batch_size + 1, chunk_size=chunk_size)

            # Clear GPU cache before chunk
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Process chunk in parallel
            try:
                chunk_results = await self._process_chunk_parallel(
                    chunk,
                    backend,
                    language,
                    **kwargs
                )
                results.extend(chunk_results)

                # Progress callback
                if progress_callback:
                    progress = len(results) / total_docs
                    await progress_callback({
                        "progress": progress,
                        "processed": len(results),
                        "total": total_docs,
                        "current_chunk": i//self.optimal_batch_size + 1
                    })

            except torch.cuda.OutOfMemoryError as e:
                logger.warning("gpu_oom_reducing_batch", chunk_number=i//self.optimal_batch_size + 1, new_batch_size=max(1, self.optimal_batch_size // 2))
                # Reduce batch size and retry
                self.optimal_batch_size = max(1, self.optimal_batch_size // 2)

                # Process chunk serially as fallback
                for file_path in chunk:
                    try:
                        result = await self._process_single(file_path, backend, language, **kwargs)
                        results.append(result)
                    except Exception as e:
                        logger.error("single_file_processing_failed", file_path=file_path, error=str(e))
                        errors.append({"file": file_path, "error": str(e)})

            except Exception as e:
                logger.error("chunk_processing_failed", error=str(e))
                # Process remaining documents individually
                for file_path in chunk:
                    try:
                        result = await self._process_single(file_path, backend, language, **kwargs)
                        results.append(result)
                    except Exception as e2:
                        errors.append({"file": file_path, "error": str(e2)})

        # Calculate statistics
        processing_time = time.time() - start_time
        successful = len(results)
        failed = len(errors)

        # GPU memory stats
        gpu_stats = None
        if torch.cuda.is_available():
            gpu_stats = {
                "peak_memory_gb": torch.cuda.max_memory_allocated() / 1024**3,
                "current_memory_gb": torch.cuda.memory_allocated() / 1024**3
            }
            torch.cuda.empty_cache()

        return {
            "success": True,
            "total": total_docs,
            "successful": successful,
            "failed": failed,
            "processing_time": processing_time,
            "avg_time_per_doc": processing_time / total_docs if total_docs > 0 else 0,
            "optimal_batch_size": self.optimal_batch_size,
            "gpu_stats": gpu_stats,
            "results": results,
            "errors": errors
        }

    async def _process_chunk_parallel(
        self,
        file_paths: List[str],
        backend: str,
        language: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Process a chunk of documents in parallel."""
        # Use asyncio.gather for true parallel processing
        tasks = []
        for file_path in file_paths:
            task = self._process_single(file_path, backend, language, **kwargs)
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("parallel_processing_failed", file_path=file_paths[i], error=str(result))
                processed_results.append({
                    "success": False,
                    "file": file_paths[i],
                    "error": str(result)
                })
            else:
                processed_results.append(result)

        return processed_results

    async def _process_single(
        self,
        file_path: str,
        backend: str,
        language: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Process a single document."""
        try:
            # Auto-select backend if needed
            if backend == "auto":
                backend = await self.backend_manager.select_backend(
                    file_path,
                    language=language,
                    prefer_gpu=torch.cuda.is_available()
                )

            # Process with selected backend
            result = await self.backend_manager.process_with_backend(
                backend,
                file_path,
                language=language,
                **kwargs
            )

            # Add file info to result
            result["file"] = file_path
            result["file_name"] = Path(file_path).name

            return result

        except Exception as e:
            logger.error("document_processing_error", file_path=file_path, error=str(e))
            return {
                "success": False,
                "file": file_path,
                "file_name": Path(file_path).name,
                "error": str(e)
            }

    async def process_directory(
        self,
        directory: str,
        pattern: str = "*.pdf",
        recursive: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process all matching files in a directory.

        Args:
            directory: Directory path to process
            pattern: File pattern to match (e.g., "*.pdf", "*.png")
            recursive: Whether to search subdirectories
            **kwargs: Processing parameters

        Returns:
            Batch processing results
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise ValueError(f"Directory not found: {directory}")

        # Find all matching files
        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))

        if not files:
            return {
                "success": False,
                "message": f"No files matching {pattern} found in {directory}",
                "total": 0
            }

        logger.info("files_found", count=len(files), pattern=pattern)

        # Convert to string paths
        file_paths = [str(f) for f in files]

        # Process batch
        return await self.process_batch(file_paths, **kwargs)

    def cleanup(self):
        """Clean up resources."""
        self.executor.shutdown(wait=True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("batch_processor_cleaned_up")