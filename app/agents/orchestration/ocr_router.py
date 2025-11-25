"""
OCR Backend Router - Intelligent backend selection.

Selects the optimal OCR backend based on:
- Document characteristics (type, complexity, quality)
- Resource availability (GPU, queue lengths)
- Performance requirements (SLA, throughput)
- Historical performance data
"""

from typing import Any, Dict

from app.agents.base import OrchestrationAgent
from app.gpu_manager import GPUManager


class OCRBackendRouter(OrchestrationAgent):
    """
    Intelligent OCR backend router.

    Uses rule-based and optionally ML-based routing to select
    the best OCR backend for each document.
    """

    # Backend characteristics
    BACKEND_CAPABILITIES = {
        "deepseek": {
            "best_for": ["complex_layouts", "tables", "handwriting", "fraktur"],
            "vram_gb": 12,
            "avg_speed_pages_per_sec": 2.5,
            "accuracy_score": 0.96,
            "languages": ["de", "en", "multi"],
        },
        "got_ocr": {
            "best_for": ["standard_text", "high_throughput", "clean_scans"],
            "vram_gb": 10,
            "avg_speed_pages_per_sec": 6.0,
            "accuracy_score": 0.92,
            "languages": ["de", "en", "multi"],
        },
        "surya": {
            "best_for": ["layout_preservation", "archival", "cpu_only"],
            "vram_gb": 0,
            "avg_speed_pages_per_sec": 1.5,
            "accuracy_score": 0.88,
            "languages": ["de", "en", "multi"],
        },
        "hybrid": {
            "best_for": ["critical_documents", "maximum_accuracy"],
            "vram_gb": 12,
            "avg_speed_pages_per_sec": 0.8,  # Slowest (runs all backends)
            "accuracy_score": 0.98,
            "languages": ["de", "en", "multi"],
        },
    }

    def __init__(self, use_ml_routing: bool = False):
        super().__init__(name="ocr_backend_router")
        self.gpu_manager = GPUManager()
        self.use_ml_routing = use_ml_routing
        self.ml_model = None  # TODO: Load ML model if use_ml_routing=True

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Select optimal OCR backend.

        Input:
            document_metadata: dict - Classification and quality info
            sla_requirements: dict - Optional SLA constraints
            user_preferences: dict - Optional user preferences

        Returns:
            backend: str - Selected backend name
            reason: str - Selection reason
            alternatives: list - Alternative backends (ranked)
            confidence: float - Confidence in selection
        """
        self.validate_input(input_data, ["document_metadata"])

        metadata = input_data["document_metadata"]
        sla = input_data.get("sla_requirements", {})
        preferences = input_data.get("user_preferences", {})

        self.logger.info(
            "router_selecting_backend",
            document_type=metadata.get("document_type"),
            complexity=metadata.get("complexity"),
            has_tables=metadata.get("has_tables"),
        )

        # Rule-based selection
        if not self.use_ml_routing:
            result = await self._rule_based_selection(metadata, sla, preferences)
        else:
            result = await self._ml_based_selection(metadata, sla, preferences)

        self.logger.info(
            "router_backend_selected",
            backend=result["backend"],
            reason=result["reason"],
            confidence=result["confidence"],
        )

        return result

    async def _rule_based_selection(
        self,
        metadata: Dict[str, Any],
        sla: Dict[str, Any],
        preferences: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Rule-based backend selection."""
        # Priority 1: User preference (if valid)
        if preferences.get("preferred_backend") in self.BACKEND_CAPABILITIES:
            return {
                "backend": preferences["preferred_backend"],
                "reason": "user_preference",
                "confidence": 1.0,
                "alternatives": [],
            }

        # Priority 2: Document characteristics
        if metadata.get("has_tables"):
            return {
                "backend": "deepseek",
                "reason": "complex_layout_with_tables",
                "confidence": 0.95,
                "alternatives": ["hybrid"],
            }

        if metadata.get("has_handwriting"):
            return {
                "backend": "deepseek",
                "reason": "handwriting_detected",
                "confidence": 0.9,
                "alternatives": ["hybrid"],
            }

        if metadata.get("document_type") == "contract":
            # Critical documents -> highest accuracy
            return {
                "backend": "hybrid",
                "reason": "critical_document_type",
                "confidence": 0.98,
                "alternatives": ["deepseek"],
            }

        # Priority 3: Quality and complexity
        complexity = metadata.get("complexity", "medium")
        quality_score = metadata.get("quality_score", 0.8)

        if complexity == "high" or quality_score < 0.7:
            return {
                "backend": "deepseek",
                "reason": "high_complexity_or_low_quality",
                "confidence": 0.85,
                "alternatives": ["hybrid", "got_ocr"],
            }

        # Priority 4: Resource availability
        gpu_status = self.gpu_manager.check_availability()
        if not gpu_status.get("available"):
            return {
                "backend": "surya",
                "reason": "gpu_unavailable",
                "confidence": 0.7,
                "alternatives": [],
            }

        # Priority 5: SLA requirements
        if sla.get("max_processing_time_seconds", 999) < 10:
            # Need fast processing
            return {
                "backend": "got_ocr",
                "reason": "fast_sla_requirement",
                "confidence": 0.9,
                "alternatives": ["surya"],
            }

        # Priority 6: Queue load balancing
        # TODO: Check queue lengths
        # queue_lengths = await self.get_queue_lengths()
        # if queue_lengths.get("deepseek", 0) > 100:
        #     return "got_ocr"  # Load balancing

        # Default: GOT-OCR for standard documents
        return {
            "backend": "got_ocr",
            "reason": "standard_document",
            "confidence": 0.85,
            "alternatives": ["deepseek", "surya"],
        }

    async def _ml_based_selection(
        self,
        metadata: Dict[str, Any],
        sla: Dict[str, Any],
        preferences: Dict[str, Any],
    ) -> Dict[str, Any]:
        """ML-based backend selection."""
        # TODO: Implement ML-based routing
        #  Features:
        #  - Document type (one-hot encoded)
        #  - Complexity score
        #  - Quality score
        #  - Has tables/handwriting (boolean)
        #  - Historical performance per backend
        #  - Current queue lengths
        #  - GPU availability
        #
        #  Model: RandomForest or XGBoost classifier
        #  Target: Best backend for this document type/characteristics
        #
        #  Training data: Collect from historical results with user feedback

        # Fallback to rule-based
        return await self._rule_based_selection(metadata, sla, preferences)

    def get_backend_info(self, backend: str) -> Dict[str, Any]:
        """Get backend capabilities and characteristics."""
        return self.BACKEND_CAPABILITIES.get(backend, {})

    def rank_backends_by_speed(self) -> list[str]:
        """Rank backends by processing speed."""
        backends = list(self.BACKEND_CAPABILITIES.keys())
        return sorted(
            backends,
            key=lambda b: self.BACKEND_CAPABILITIES[b]["avg_speed_pages_per_sec"],
            reverse=True,
        )

    def rank_backends_by_accuracy(self) -> list[str]:
        """Rank backends by accuracy score."""
        backends = list(self.BACKEND_CAPABILITIES.keys())
        return sorted(
            backends,
            key=lambda b: self.BACKEND_CAPABILITIES[b]["accuracy_score"],
            reverse=True,
        )
