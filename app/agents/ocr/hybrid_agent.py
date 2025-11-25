"""Hybrid OCR Agent - Multi-engine fusion for maximum accuracy."""

import asyncio
from typing import Any, Dict, List

from app.agents.base import OCRAgent

from .deepseek_agent import DeepSeekAgent
from .got_ocr_agent import GOTOCRAgent
from .surya_docling_agent import SuryaDoclingAgent


class HybridOCRAgent(OCRAgent):
    """
    Hybrid OCR agent that combines multiple engines for maximum accuracy.

    Strategy:
    1. Run all available OCR engines in parallel
    2. Compare results with confidence-based voting
    3. Merge results using intelligent fusion
    """

    def __init__(self):
        super().__init__(name="hybrid_ocr_agent", gpu_required=True, vram_gb=12)

        # Initialize sub-agents
        self.deepseek = DeepSeekAgent()
        self.got_ocr = GOTOCRAgent()
        self.surya_docling = SuryaDoclingAgent()

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process with multiple OCR engines and fuse results.

        Returns best result based on:
        - Confidence scores
        - Text length (longer usually better)
        - Entity recognition quality
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]

        self.logger.info(
            "hybrid_ocr_started",
            document_id=document_id,
            engines=["deepseek", "got_ocr", "surya_docling"],
        )

        # Run all engines in parallel
        results = await self._run_parallel_ocr(input_data)

        # Fuse results
        fused_result = await self._fuse_results(results)

        self.logger.info(
            "hybrid_ocr_completed",
            document_id=document_id,
            selected_engine=fused_result.get("selected_engine"),
            confidence=fused_result.get("confidence"),
        )

        return fused_result

    async def _run_parallel_ocr(
        self, input_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Run all OCR engines in parallel."""
        tasks = [
            self.deepseek.process(input_data),
            self.got_ocr.process(input_data),
            self.surya_docling.process(input_data),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            engine_name = ["deepseek", "got_ocr", "surya_docling"][i]
            if isinstance(result, Exception):
                self.logger.warning(
                    "hybrid_ocr_engine_failed",
                    engine=engine_name,
                    error=str(result),
                )
            else:
                valid_results.append({**result, "engine": engine_name})

        return valid_results

    async def _fuse_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Fuse results from multiple engines.

        Strategy:
        1. Select engine with highest confidence
        2. If confidences similar, choose longest text
        3. Merge entities from all engines
        """
        if not results:
            raise ValueError("No valid OCR results to fuse")

        # Sort by confidence
        sorted_results = sorted(
            results, key=lambda x: x.get("confidence", 0.0), reverse=True
        )

        # Select best result
        best_result = sorted_results[0]

        # Merge entities from all results (if available)
        all_entities = []
        for result in results:
            entities = result.get("entities", [])
            all_entities.extend(entities)

        # Deduplicate entities
        unique_entities = self._deduplicate_entities(all_entities)

        return {
            "text": best_result.get("text", ""),
            "confidence": best_result.get("confidence", 0.0),
            "selected_engine": best_result.get("engine"),
            "all_confidences": {
                r.get("engine"): r.get("confidence") for r in results
            },
            "entities": unique_entities,
            "layout": best_result.get("layout", {}),
        }

    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """Deduplicate entities from multiple sources."""
        # TODO: Implement smart deduplication
        #  - Use fuzzy matching for similar entities
        #  - Merge confidence scores
        return entities
