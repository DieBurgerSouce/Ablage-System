"""
OCR Backend Router - Intelligent backend selection.

Enterprise-grade OCR backend routing with ML-based selection:
- Document characteristics analysis (type, complexity, quality)
- Resource availability monitoring (GPU, queue lengths)
- Performance requirements matching (SLA, throughput)
- ML model for optimal backend prediction
- Historical performance tracking
- Self-learning from user corrections (feedback loop)

Feinpoliert und durchdacht - Intelligente Backend-Auswahl für optimale Ergebnisse.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import structlog

from app.agents.base import OrchestrationAgent
from app.gpu_manager import GPUManager

logger = structlog.get_logger(__name__)

# Cache for learned weights
_learned_weights_cache: Optional[Dict[str, Any]] = None
_learned_weights_cache_time: Optional[datetime] = None
_LEARNED_WEIGHTS_CACHE_TTL_SECONDS = 300  # 5 minutes


class OCRBackendRouter(OrchestrationAgent):
    """
    Intelligent OCR backend router with ML support.

    Uses rule-based selection by default, with optional ML-based routing
    for enterprise deployments. The ML model learns from processing results
    to continuously improve backend selection.

    Routing Priorities:
    1. User preference (if valid backend)
    2. ML model prediction (if enabled and trained)
    3. Document characteristic rules
    4. Resource availability constraints
    5. SLA requirements
    6. Default backend selection
    """

    # Backend characteristics and capabilities
    BACKEND_CAPABILITIES = {
        "deepseek": {
            "best_for": ["complex_layouts", "tables", "handwriting", "fraktur"],
            "vram_gb": 12,
            "avg_speed_pages_per_sec": 2.5,
            "accuracy_score": 0.96,
            "languages": ["de", "en", "multi"],
            "german_label": "DeepSeek-Janus-Pro",
            "description": "Beste Genauigkeit für komplexe deutsche Dokumente",
        },
        "got_ocr": {
            "best_for": ["standard_text", "high_throughput", "clean_scans"],
            "vram_gb": 10,
            "avg_speed_pages_per_sec": 6.0,
            "accuracy_score": 0.92,
            "languages": ["de", "en", "multi"],
            "german_label": "GOT-OCR 2.0",
            "description": "Schnelle Verarbeitung für Standarddokumente",
        },
        "surya": {
            "best_for": ["layout_preservation", "archival", "cpu_only"],
            "vram_gb": 0,
            "avg_speed_pages_per_sec": 1.5,
            "accuracy_score": 0.88,
            "languages": ["de", "en", "multi"],
            "german_label": "Surya + Docling",
            "description": "CPU-basiert mit Layout-Analyse",
        },
        "surya_gpu": {
            "best_for": ["fast_layout", "batch_processing"],
            "vram_gb": 4,
            "avg_speed_pages_per_sec": 4.0,
            "accuracy_score": 0.90,
            "languages": ["de", "en", "multi"],
            "german_label": "Surya GPU",
            "description": "GPU-beschleunigte Layout-Erkennung",
        },
        "hybrid": {
            "best_for": ["critical_documents", "maximum_accuracy"],
            "vram_gb": 12,
            "avg_speed_pages_per_sec": 0.8,  # Slowest (runs all backends)
            "accuracy_score": 0.98,
            "languages": ["de", "en", "multi"],
            "german_label": "Hybrid-Modus",
            "description": "Maximale Genauigkeit durch Multi-Backend-Verarbeitung",
        },
    }

    # Default model directory
    DEFAULT_MODEL_DIR = Path("models/ocr_router")

    def __init__(
        self,
        use_ml_routing: bool = False,
        model_dir: Optional[Path] = None,
        auto_train: bool = True,
    ) -> None:
        """
        Initialize OCR Backend Router.

        Args:
            use_ml_routing: Enable ML-based routing (requires trained model)
            model_dir: Directory for ML model storage
            auto_train: Automatically train model when data is available
        """
        super().__init__(name="ocr_backend_router")
        self.gpu_manager = GPUManager()
        self.use_ml_routing = use_ml_routing
        self.auto_train = auto_train
        self.model_dir = model_dir or self.DEFAULT_MODEL_DIR

        # ML components (lazy loaded)
        self._ml_model = None
        self._ml_trainer = None

        # Performance tracking
        self._routing_stats = {
            "total_requests": 0,
            "ml_predictions": 0,
            "rule_fallbacks": 0,
            "backend_selections": {b: 0 for b in self.BACKEND_CAPABILITIES},
        }

        # Load ML model if routing enabled
        if self.use_ml_routing:
            self._init_ml_routing()

    def _init_ml_routing(self) -> None:
        """Initialize ML routing components."""
        try:
            from app.agents.orchestration.ml_router_model import OCRRouterModel
            from app.agents.orchestration.ml_trainer import MLRouterTrainer

            self._ml_trainer = MLRouterTrainer(model_dir=self.model_dir)
            self._ml_model = self._ml_trainer.model

            if self._ml_model and self._ml_model.is_trained:
                logger.info("ML-Routing initialisiert mit trainiertem Modell")
            else:
                logger.info("ML-Routing initialisiert - Modell wird trainiert wenn Daten verfügbar")

        except ImportError as e:
            logger.warning("ml_routing_nicht_verfuegbar", error=str(e))
            self.use_ml_routing = False
        except Exception as e:
            logger.error("ml_routing_init_fehler", error=str(e))
            self.use_ml_routing = False

    def _get_resource_status(self) -> Dict[str, Any]:
        """Get current resource availability status (sync, without queue lengths)."""
        gpu_status = self.gpu_manager.check_availability()

        return {
            "gpu_available": gpu_status.get("available", False),
            "gpu_memory_available_gb": gpu_status.get("free_memory_gb", 0),
            "queue_length": 0,  # Use _get_resource_status_async for queue lengths
            "queue_lengths": {},
        }

    async def _get_resource_status_async(self) -> Dict[str, Any]:
        """Get current resource availability with queue lengths from Redis."""
        gpu_status = self.gpu_manager.check_availability()

        # Get queue lengths from Redis for load balancing
        queue_length = 0
        queue_lengths = {}
        try:
            from app.core.redis_state import get_redis
            redis_manager = await get_redis()
            queue_lengths = await redis_manager.get_queue_lengths()
            queue_length = sum(queue_lengths.values())
        except Exception as e:
            logger.warning("queue_length_fetch_failed", error=str(e))

        return {
            "gpu_available": gpu_status.get("available", False),
            "gpu_memory_available_gb": gpu_status.get("free_memory_gb", 0),
            "queue_length": queue_length,
            "queue_lengths": queue_lengths,
        }

    async def _check_load_balancing(
        self,
        resource_status: Dict[str, Any],
        metadata: Dict[str, Any],
        sla: Dict[str, Any],
        preferences: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Check if load balancing should override normal backend selection.

        Returns a routing result if load balancing is needed, None otherwise.

        Load balancing triggers:
        - Queue length > high threshold: Switch to faster backend
        - Queue length > critical threshold: Use CPU fallback
        - GPU unavailable but GPU backend preferred: Use CPU fallback

        Args:
            resource_status: Current resource status with queue lengths
            metadata: Document classification results
            sla: SLA requirements
            preferences: User preferences

        Returns:
            Routing result dict if load balancing triggered, None otherwise
        """
        from app.core.config import settings

        # Skip if load balancing is disabled
        if not settings.LOAD_BALANCING_ENABLED:
            return None

        # Skip if user has strong preference
        if preferences.get("preferred_backend") in self.BACKEND_CAPABILITIES:
            return None

        queue_length = resource_status.get("queue_length", 0)
        queue_lengths = resource_status.get("queue_lengths", {})
        gpu_available = resource_status.get("gpu_available", False)

        # Critical threshold: Too many jobs queued, use CPU fallback
        if queue_length >= settings.QUEUE_LENGTH_THRESHOLD_CRITICAL:
            logger.warning(
                "load_balancing_critical",
                queue_length=queue_length,
                threshold=settings.QUEUE_LENGTH_THRESHOLD_CRITICAL,
                action="cpu_fallback"
            )
            return {
                "backend": "surya",
                "reason": f"queue_overload_critical ({queue_length} jobs)",
                "confidence": 0.7,
                "alternatives": [],
                "routing_method": "load_balancing",
                "load_balanced": True,
            }

        # High threshold: OCR queues overloaded, switch to faster backend
        ocr_high_queue = queue_lengths.get("ocr_high", 0)
        ocr_normal_queue = queue_lengths.get("ocr_normal", 0)
        total_ocr_queue = ocr_high_queue + ocr_normal_queue

        if total_ocr_queue >= settings.QUEUE_LENGTH_THRESHOLD_HIGH:
            # Prefer got_ocr for faster throughput when queues are high
            if gpu_available:
                logger.info(
                    "load_balancing_high",
                    ocr_queue_length=total_ocr_queue,
                    threshold=settings.QUEUE_LENGTH_THRESHOLD_HIGH,
                    action="switch_to_fast_gpu"
                )
                return {
                    "backend": "got_ocr",
                    "reason": f"queue_overload_high ({total_ocr_queue} OCR jobs)",
                    "confidence": 0.8,
                    "alternatives": ["surya_gpu", "surya"],
                    "routing_method": "load_balancing",
                    "load_balanced": True,
                }
            else:
                logger.info(
                    "load_balancing_high_cpu",
                    ocr_queue_length=total_ocr_queue,
                    threshold=settings.QUEUE_LENGTH_THRESHOLD_HIGH,
                    action="switch_to_cpu"
                )
                return {
                    "backend": "surya",
                    "reason": f"queue_overload_high_no_gpu ({total_ocr_queue} OCR jobs)",
                    "confidence": 0.7,
                    "alternatives": [],
                    "routing_method": "load_balancing",
                    "load_balanced": True,
                }

        # No load balancing needed
        return None

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
            routing_method: str - "ml" or "rule_based"
        """
        self.validate_input(input_data, ["document_metadata"])

        metadata = input_data["document_metadata"]
        sla = input_data.get("sla_requirements", {})
        preferences = input_data.get("user_preferences", {})

        # Update stats
        self._routing_stats["total_requests"] += 1

        self.logger.info(
            "router_selecting_backend",
            document_type=metadata.get("document_type"),
            complexity=metadata.get("complexity"),
            has_tables=metadata.get("has_tables"),
            use_ml=self.use_ml_routing,
        )

        # Get resource status with queue lengths (async)
        resource_status = await self._get_resource_status_async()

        # Check for load balancing before ML/rule-based selection
        load_balanced_result = await self._check_load_balancing(
            resource_status, metadata, sla, preferences
        )
        if load_balanced_result:
            self._routing_stats["backend_selections"][load_balanced_result["backend"]] += 1
            return load_balanced_result

        # Try ML-based selection first if enabled
        result = None
        if self.use_ml_routing and self._ml_model and self._ml_model.is_trained:
            try:
                result = await self._ml_based_selection(
                    metadata, sla, preferences, resource_status
                )
                self._routing_stats["ml_predictions"] += 1
            except Exception as e:
                logger.warning("ml_routing_failed_fallback", error=str(e))
                self._routing_stats["rule_fallbacks"] += 1

        # Fallback to rule-based selection
        if result is None:
            result = await self._rule_based_selection(metadata, sla, preferences)
            result["routing_method"] = "rule_based"

        # Update backend selection stats
        backend = result["backend"]
        if backend in self._routing_stats["backend_selections"]:
            self._routing_stats["backend_selections"][backend] += 1

        self.logger.info(
            "router_backend_selected",
            backend=result["backend"],
            reason=result["reason"],
            confidence=result["confidence"],
            method=result.get("routing_method", "rule_based"),
        )

        return result

    async def _rule_based_selection(
        self,
        metadata: Dict[str, Any],
        sla: Dict[str, Any],
        preferences: Dict[str, Any],
        use_learned_weights: bool = True,
    ) -> Dict[str, Any]:
        """
        Rule-based backend selection with learned weight adjustments.

        Combines static rules with dynamic learning from user corrections.
        """
        # Priority 1: User preference (if valid)
        if preferences.get("preferred_backend") in self.BACKEND_CAPABILITIES:
            return {
                "backend": preferences["preferred_backend"],
                "reason": "user_preference",
                "confidence": 1.0,
                "alternatives": [],
            }

        # Get learned weights for adjustment (if enabled)
        learned_weights: Dict[str, float] = {}
        if use_learned_weights:
            try:
                learned_weights = await self.get_learned_backend_weights()
            except Exception as e:
                logger.debug("learned_weights_not_applied", error=str(e))

        def apply_weight(backend: str, base_confidence: float) -> float:
            """Apply learned weight to confidence score."""
            if not learned_weights:
                return base_confidence
            weight = learned_weights.get(backend, 1.0)
            # Weight adjusts confidence: >1.0 increases, <1.0 decreases
            return min(base_confidence * weight, 1.0)

        def select_best_backend(candidates: list[str], base_confidences: Dict[str, float], reason: str) -> Dict[str, Any]:
            """Select best backend from candidates using learned weights."""
            if not candidates:
                return {"backend": "got_ocr", "reason": reason, "confidence": 0.5, "alternatives": []}

            if not learned_weights:
                # No learning data - use first candidate
                return {
                    "backend": candidates[0],
                    "reason": reason,
                    "confidence": base_confidences.get(candidates[0], 0.8),
                    "alternatives": candidates[1:],
                }

            # Score candidates with learned weights
            scored = []
            for backend in candidates:
                base_conf = base_confidences.get(backend, 0.8)
                weighted_conf = apply_weight(backend, base_conf)
                scored.append((backend, weighted_conf))

            # Sort by weighted confidence
            scored.sort(key=lambda x: x[1], reverse=True)

            return {
                "backend": scored[0][0],
                "reason": f"{reason}_with_learning",
                "confidence": scored[0][1],
                "alternatives": [s[0] for s in scored[1:]],
                "learned_weights_applied": True,
            }

        # Priority 2: Document characteristics
        if metadata.get("has_tables"):
            return select_best_backend(
                ["deepseek", "hybrid", "got_ocr"],
                {"deepseek": 0.95, "hybrid": 0.90, "got_ocr": 0.75},
                "complex_layout_with_tables",
            )

        if metadata.get("has_handwriting"):
            return select_best_backend(
                ["deepseek", "hybrid"],
                {"deepseek": 0.90, "hybrid": 0.85},
                "handwriting_detected",
            )

        if metadata.get("document_type") == "contract":
            # Critical documents -> highest accuracy
            return select_best_backend(
                ["hybrid", "deepseek"],
                {"hybrid": 0.98, "deepseek": 0.95},
                "critical_document_type",
            )

        # Priority 3: Quality and complexity
        complexity = metadata.get("complexity", "medium")
        quality_score = metadata.get("quality_score", 0.8)

        if complexity == "high" or quality_score < 0.7:
            return select_best_backend(
                ["deepseek", "hybrid", "got_ocr"],
                {"deepseek": 0.85, "hybrid": 0.80, "got_ocr": 0.70},
                "high_complexity_or_low_quality",
            )

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
            # Need fast processing - select fastest with learning adjustment
            return select_best_backend(
                ["got_ocr", "surya_gpu", "surya"],
                {"got_ocr": 0.90, "surya_gpu": 0.85, "surya": 0.70},
                "fast_sla_requirement",
            )

        # Priority 6: Default selection with learning
        # For standard documents, use learned weights to pick best option
        return select_best_backend(
            ["got_ocr", "deepseek", "surya_gpu", "surya"],
            {"got_ocr": 0.85, "deepseek": 0.80, "surya_gpu": 0.75, "surya": 0.65},
            "standard_document",
        )

    async def _ml_based_selection(
        self,
        metadata: Dict[str, Any],
        sla: Dict[str, Any],
        preferences: Dict[str, Any],
        resource_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        ML-based backend selection using trained XGBoost model.

        Features used:
        - Document type (one-hot encoded)
        - Complexity score
        - Quality score
        - Has tables/handwriting/fraktur (boolean)
        - GPU availability
        - Queue length
        - SLA requirements

        Args:
            metadata: Document classification results
            sla: SLA requirements
            preferences: User preferences
            resource_status: Current resource availability

        Returns:
            Selection result with backend, confidence, and alternatives
        """
        if not self._ml_model or not self._ml_model.is_trained:
            raise RuntimeError("ML-Modell nicht verfügbar oder nicht trainiert")

        # Check for user preference override
        if preferences.get("preferred_backend") in self.BACKEND_CAPABILITIES:
            return {
                "backend": preferences["preferred_backend"],
                "reason": "Benutzereinstellung",
                "confidence": 1.0,
                "alternatives": [],
                "routing_method": "user_preference",
            }

        # Get ML prediction
        prediction = self._ml_model.predict(
            document_metadata=metadata,
            sla_requirements=sla,
            resource_status=resource_status,
        )

        # Validate backend is available
        backend = prediction["backend"]
        if backend not in self.BACKEND_CAPABILITIES:
            backend = "got_ocr"  # Safe default

        # Check resource constraints
        backend_requirements = self.BACKEND_CAPABILITIES[backend]
        resource_status = resource_status or self._get_resource_status()

        if backend_requirements["vram_gb"] > 0:
            # Check GPU availability for GPU backends
            if not resource_status.get("gpu_available"):
                # GPU not available, use CPU fallback
                logger.info("gpu_unavailable_fallback", original_backend=backend, fallback_backend="surya")
                backend = "surya"
                prediction["reason"] = "GPU nicht verfügbar - CPU-Fallback"
                prediction["confidence"] *= 0.8

        return {
            "backend": backend,
            "reason": prediction.get("reason", "ML-Routing"),
            "confidence": prediction["confidence"],
            "alternatives": [a["backend"] for a in prediction.get("alternatives", [])],
            "routing_method": "ml",
            "model_version": prediction.get("model_version"),
            "probabilities": prediction.get("probabilities"),
        }

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

    def collect_training_feedback(
        self,
        document_id: str,
        document_metadata: Dict[str, Any],
        selected_backend: str,
        processing_result: Dict[str, Any],
        sla_requirements: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Collect training feedback from processing result.

        Called after document processing to collect data for ML model training.

        Args:
            document_id: Document identifier
            document_metadata: Document classification info
            selected_backend: Backend that was used
            processing_result: Processing result with accuracy/success
            sla_requirements: SLA constraints that were used
        """
        if not self._ml_trainer:
            return

        try:
            resource_status = self._get_resource_status()

            self._ml_trainer.collect_training_sample(
                document_id=document_id,
                document_metadata=document_metadata,
                sla_requirements=sla_requirements,
                resource_status=resource_status,
                selected_backend=selected_backend,
                processing_result=processing_result,
            )

            # Record feedback for model improvement
            if self._ml_model:
                self._ml_model.record_feedback(
                    backend=selected_backend,
                    was_successful=processing_result.get("success", False),
                    accuracy=processing_result.get("confidence"),
                )

        except Exception as e:
            logger.warning("training_feedback_collection_failed", error=str(e))

    async def train_model(self, force: bool = False) -> Dict[str, Any]:
        """
        Train or retrain the ML model.

        Args:
            force: Force training even if not due

        Returns:
            Training result metrics
        """
        if not self._ml_trainer:
            return {
                "status": "unavailable",
                "message": "ML-Trainer nicht initialisiert",
            }

        result = await self._ml_trainer.train_model(force=force)

        # Update current model reference
        if result.get("status") == "success":
            self._ml_model = self._ml_trainer.model

        return result

    def generate_bootstrap_data(self, num_samples: int = 1000) -> None:
        """
        Generate synthetic training data for initial model bootstrap.

        Useful when no historical data is available yet.

        Args:
            num_samples: Number of synthetic samples to generate
        """
        if not self._ml_trainer:
            logger.warning("ML-Trainer nicht verfügbar für Bootstrap-Daten")
            return

        self._ml_trainer.generate_synthetic_training_data(num_samples)
        logger.info("bootstrap_data_generated", num_samples=num_samples)

    def get_routing_stats(self) -> Dict[str, Any]:
        """
        Get routing statistics.

        Returns:
            Statistics including total requests, ML predictions, and backend distribution
        """
        stats = dict(self._routing_stats)

        # Add ML-specific stats if available
        if self._ml_trainer:
            stats["training_status"] = self._ml_trainer.get_training_status()

        if self._ml_model and self._ml_model.is_trained:
            stats["model_info"] = self._ml_model.get_model_info()

        return stats

    def get_backend_recommendations(
        self,
        document_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get backend recommendations for a document without making final selection.

        Useful for UI display or debugging.

        Args:
            document_metadata: Document classification info

        Returns:
            Recommendations with scores for each backend
        """
        recommendations = {}

        for backend, capabilities in self.BACKEND_CAPABILITIES.items():
            score = 0.5  # Base score

            # Document type matching
            doc_type = document_metadata.get("document_type", "other")
            if doc_type == "contract" and backend == "hybrid":
                score += 0.3
            elif doc_type == "invoice" and backend in ["deepseek", "got_ocr"]:
                score += 0.2

            # Complexity matching
            complexity = document_metadata.get("complexity", "medium")
            if complexity == "high" and backend in ["deepseek", "hybrid"]:
                score += 0.2
            elif complexity == "low" and backend in ["got_ocr", "surya"]:
                score += 0.1

            # Feature matching
            if document_metadata.get("has_tables"):
                if "tables" in capabilities["best_for"]:
                    score += 0.2
            if document_metadata.get("has_handwriting"):
                if "handwriting" in capabilities["best_for"]:
                    score += 0.3
            if document_metadata.get("has_fraktur"):
                if "fraktur" in capabilities["best_for"]:
                    score += 0.4

            # Quality matching
            quality = document_metadata.get("quality_score", 0.8)
            if quality < 0.6:
                if capabilities["accuracy_score"] > 0.94:
                    score += 0.2
            elif quality > 0.9:
                if capabilities["avg_speed_pages_per_sec"] > 3:
                    score += 0.1

            recommendations[backend] = {
                "score": min(score, 1.0),
                "german_label": capabilities["german_label"],
                "description": capabilities["description"],
                "estimated_speed": capabilities["avg_speed_pages_per_sec"],
                "estimated_accuracy": capabilities["accuracy_score"],
                "gpu_required": capabilities["vram_gb"] > 0,
            }

        # Sort by score
        sorted_backends = sorted(
            recommendations.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )

        return {
            "recommendations": dict(sorted_backends),
            "best_backend": sorted_backends[0][0] if sorted_backends else "got_ocr",
        }

    def is_ml_routing_available(self) -> bool:
        """Check if ML routing is available and ready."""
        return (
            self.use_ml_routing and
            self._ml_model is not None and
            self._ml_model.is_trained
        )

    async def get_learned_backend_weights(
        self,
        force_refresh: bool = False,
    ) -> Dict[str, float]:
        """
        Get learned backend weights from feedback learning service.

        Uses cached weights with 5-minute TTL to avoid excessive database queries.
        Weights are derived from user corrections and benchmark results.

        Args:
            force_refresh: Force fetching fresh weights from database

        Returns:
            Dictionary mapping backend names to weight scores (0.0 - 2.0)
            Higher weights indicate better historical performance.
        """
        global _learned_weights_cache, _learned_weights_cache_time

        # Check cache validity
        now = datetime.now(timezone.utc)
        if (
            not force_refresh
            and _learned_weights_cache is not None
            and _learned_weights_cache_time is not None
        ):
            age_seconds = (now - _learned_weights_cache_time).total_seconds()
            if age_seconds < _LEARNED_WEIGHTS_CACHE_TTL_SECONDS:
                return _learned_weights_cache.get("weights", {})

        # Fetch fresh weights from feedback learning service
        try:
            from app.services.feedback_learning_service import get_feedback_learning_service
            from app.db.session import get_async_session_context

            async with get_async_session_context() as session:
                feedback_service = await get_feedback_learning_service(session)
                learned_weights = await feedback_service.get_learned_weights(
                    force_refresh=force_refresh
                )

                # Update cache
                _learned_weights_cache = {
                    "weights": learned_weights.weights,
                    "confidence": learned_weights.confidence,
                    "samples_analyzed": learned_weights.samples_analyzed,
                }
                _learned_weights_cache_time = now

                logger.debug(
                    "learned_weights_fetched",
                    weights=learned_weights.weights,
                    confidence=learned_weights.confidence,
                )

                return learned_weights.weights

        except Exception as e:
            logger.warning("learned_weights_fetch_failed", error=str(e))
            # Return neutral weights on error
            return {
                "deepseek": 1.0,
                "got_ocr": 1.0,
                "surya": 1.0,
                "surya_gpu": 1.0,
            }

    async def get_backend_recommendation_with_learning(
        self,
        document_metadata: Dict[str, Any],
        use_learned_weights: bool = True,
    ) -> Dict[str, Any]:
        """
        Get backend recommendations with learned weight adjustments.

        Combines rule-based scoring with learned weights from user feedback.

        Args:
            document_metadata: Document classification info
            use_learned_weights: Apply learned weights to scores

        Returns:
            Recommendations with adjusted scores based on learning
        """
        # Get base recommendations
        recommendations = self.get_backend_recommendations(document_metadata)

        if not use_learned_weights:
            return recommendations

        # Apply learned weights
        try:
            learned_weights = await self.get_learned_backend_weights()

            if learned_weights:
                for backend, rec in recommendations["recommendations"].items():
                    weight = learned_weights.get(backend, 1.0)
                    # Apply weight adjustment (neutral at 1.0)
                    adjusted_score = rec["score"] * weight
                    rec["score"] = min(adjusted_score, 1.0)
                    rec["learned_weight"] = weight

                # Re-sort by adjusted scores
                sorted_recs = sorted(
                    recommendations["recommendations"].items(),
                    key=lambda x: x[1]["score"],
                    reverse=True,
                )
                recommendations["recommendations"] = dict(sorted_recs)
                recommendations["best_backend"] = sorted_recs[0][0] if sorted_recs else "got_ocr"
                recommendations["learning_applied"] = True

        except Exception as e:
            logger.warning("learned_weight_application_failed", error=str(e))
            recommendations["learning_applied"] = False

        return recommendations

    def get_available_backends(
        self,
        gpu_required: Optional[bool] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get available backends with optional filtering.

        Args:
            gpu_required: Filter by GPU requirement (None = all)

        Returns:
            Dictionary of available backends with their info
        """
        backends = {}

        for name, capabilities in self.BACKEND_CAPABILITIES.items():
            requires_gpu = capabilities["vram_gb"] > 0

            if gpu_required is None or requires_gpu == gpu_required:
                backends[name] = {
                    "german_label": capabilities["german_label"],
                    "description": capabilities["description"],
                    "requires_gpu": requires_gpu,
                    "vram_gb": capabilities["vram_gb"],
                    "avg_speed": capabilities["avg_speed_pages_per_sec"],
                    "accuracy": capabilities["accuracy_score"],
                    "best_for": capabilities["best_for"],
                }

        return backends
