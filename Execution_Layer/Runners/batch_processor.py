"""
Batch Processor - Multi-Document Processing
Implementiert parallele Dokumentenverarbeitung mit Concurrency-Kontrolle
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


class BatchProcessor:
    """
    Process multiple documents efficiently.

    Features:
    - Concurrency control via semaphore
    - Error isolation per document
    - Progress tracking
    - Result aggregation
    """

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._progress = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "in_progress": 0
        }

    async def process_batch(
        self,
        document_ids: List[str],
        backend: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Process documents with concurrency control.

        Args:
            document_ids: List of document UUIDs to process
            backend: Optional OCR backend override

        Returns:
            List of processing results for each document
        """
        self._progress = {
            "total": len(document_ids),
            "completed": 0,
            "failed": 0,
            "in_progress": 0,
            "started_at": datetime.utcnow().isoformat()
        }

        logger.info(
            "batch_processing_start",
            total_documents=len(document_ids),
            max_concurrent=self.max_concurrent
        )

        async def process_with_semaphore(doc_id: str) -> Dict[str, Any]:
            async with self.semaphore:
                self._progress["in_progress"] += 1
                try:
                    result = await self.process_single(doc_id, backend)

                    if result.get("status") == "success":
                        self._progress["completed"] += 1
                    else:
                        self._progress["failed"] += 1

                    return result
                finally:
                    self._progress["in_progress"] -= 1

        tasks = [process_with_semaphore(doc_id) for doc_id in document_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "document_id": document_ids[i],
                    "status": "failed",
                    "error": str(result)
                })
                self._progress["failed"] += 1
            else:
                final_results.append(result)

        self._progress["finished_at"] = datetime.utcnow().isoformat()

        logger.info(
            "batch_processing_complete",
            total=self._progress["total"],
            completed=self._progress["completed"],
            failed=self._progress["failed"]
        )

        return final_results

    async def process_single(
        self,
        doc_id: str,
        backend: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process single document through OCR pipeline.

        Args:
            doc_id: Document UUID
            backend: Optional OCR backend override

        Returns:
            Processing result with status, text, and metadata
        """
        result = {
            "document_id": doc_id,
            "status": "pending",
            "started_at": datetime.utcnow().isoformat()
        }

        try:
            # Import and use OCRProcessingAgent
            from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

            agent = OCRProcessingAgent()
            processing_result = await agent.process_document(doc_id, backend=backend)

            result.update(processing_result)
            result["status"] = processing_result.get("status", "success")

            logger.info(
                "single_document_processed",
                document_id=doc_id,
                status=result["status"]
            )

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

            logger.error(
                "single_document_failed",
                document_id=doc_id,
                error=str(e),
                exc_info=True
            )

        result["finished_at"] = datetime.utcnow().isoformat()
        return result

    def get_progress(self) -> Dict[str, Any]:
        """Get current batch processing progress."""
        return self._progress.copy()

    async def cancel_batch(self):
        """Cancel ongoing batch processing."""
        logger.warning("batch_processing_cancelled")
        # Semaphore doesn't support cancellation directly,
        # but we can set a flag for graceful shutdown
        self._progress["cancelled"] = True
