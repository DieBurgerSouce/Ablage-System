# -*- coding: utf-8 -*-
"""
Unified OCR Backend Router - Konsolidierter Router mit ML und Regeln.

Enterprise-grade OCR backend routing mit:
- ML-basierte Vorhersage (XGBoost)
- Regelbasierter Fallback
- Automatische Fallback-Kette bei Fehlern
- Spracherkennung (vorbereitet)
- Backend-spezifische Optimierungen
- Typsicherheit mit Enums und Pydantic

Konsolidiert:
- Execution_Layer/routers/ocr_router.py
- app/agents/orchestration/ocr_router.py

Feinpoliert und durchdacht - Intelligente Backend-Auswahl für optimale Ergebnisse.
"""

import asyncio
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field
import structlog

from app.agents.base import OrchestrationAgent
from app.gpu_manager import GPUManager
from .language_detector import (
    LanguageDetector,
    LanguageDetectionResult,
    LanguageCode,
    ScriptType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS & TYPES
# =============================================================================


class BackendType(str, Enum):
    """Available OCR backend types with normalized names."""

    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA = "surya"
    SURYA_GPU = "surya_gpu"
    DONUT = "donut"  # Multilingual Transformer (100+ Sprachen, Kyrillisch)
    HYBRID = "hybrid"
    TESSERACT = "tesseract"  # Fallback

    # Legacy mapping
    JANUS_PRO = "deepseek"  # Alias

    @classmethod
    def from_string(cls, value: str) -> "BackendType":
        """Convert string to BackendType with legacy support."""
        value = value.lower().replace("-", "_")
        mappings = {
            "deepseek": cls.DEEPSEEK,
            "deepseek_janus_pro": cls.DEEPSEEK,
            "janus_pro": cls.DEEPSEEK,
            "janus": cls.DEEPSEEK,
            "got_ocr": cls.GOT_OCR,
            "got": cls.GOT_OCR,
            "got_ocr_2.0": cls.GOT_OCR,
            "surya": cls.SURYA,
            "surya_docling": cls.SURYA,
            "surya_gpu": cls.SURYA_GPU,
            "donut": cls.DONUT,
            "donut_base": cls.DONUT,
            "document_understanding": cls.DONUT,
            "hybrid": cls.HYBRID,
            "tesseract": cls.TESSERACT,
        }
        return mappings.get(value, cls.GOT_OCR)


class RoutingMethod(str, Enum):
    """How the backend was selected."""

    ML = "ml"
    RULE_BASED = "rule_based"
    USER_PREFERENCE = "user_preference"
    FALLBACK = "fallback"
    LANGUAGE_BASED = "language_based"


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class DocumentAnalysis(BaseModel):
    """Document characteristics for routing decision."""

    document_type: str = Field(default="other", description="Dokumenttyp")
    complexity: str = Field(default="medium", description="low/medium/high")
    quality_score: float = Field(default=0.8, ge=0.0, le=1.0)

    # Content flags
    has_formulas: bool = False
    has_tables: bool = False
    has_complex_layout: bool = False
    has_images: bool = False
    has_handwriting: bool = False
    has_fraktur: bool = False
    requires_image_understanding: bool = False

    # Document metadata
    languages: List[str] = Field(default_factory=lambda: ["de"])
    detected_language: Optional[str] = None
    is_scanned: bool = False
    is_structured_pdf: bool = False
    page_count: int = 1

    class Config:
        """Pydantic configuration."""

        extra = "allow"  # Allow additional fields

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Convert to metadata dict for ML model."""
        return {
            "document_type": self.document_type,
            "complexity": self.complexity,
            "quality_score": self.quality_score,
            "has_tables": self.has_tables,
            "has_images": self.has_images,
            "has_handwriting": self.has_handwriting,
            "has_fraktur": self.has_fraktur,
            "page_count": self.page_count,
        }


class SLARequirements(BaseModel):
    """SLA requirements for processing."""

    max_processing_time_seconds: int = 60
    min_accuracy: float = Field(default=0.8, ge=0.0, le=1.0)
    is_critical: bool = False
    priority: str = Field(default="normal", description="low/normal/high/critical")


class BackendCapabilities(BaseModel):
    """Backend capabilities and requirements."""

    name: str
    german_label: str
    description: str
    vram_gb: float
    supports_gpu: bool
    supports_cpu: bool
    best_for: List[str]
    languages: List[str]
    avg_speed_pages_per_sec: float
    accuracy_score: float
    max_batch_size: int = 8


class RoutingResult(BaseModel):
    """Result of routing decision."""

    backend: BackendType
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: List[BackendType] = Field(default_factory=list)
    routing_method: RoutingMethod
    model_version: Optional[str] = None
    probabilities: Optional[Dict[str, float]] = None
    fallback_chain: List[BackendType] = Field(default_factory=list)


# =============================================================================
# PROTOCOLS
# =============================================================================


class OCRBackend(Protocol):
    """Protocol for OCR backends."""

    async def ocr(self, image_bytes: bytes, **kwargs: Any) -> Dict[str, Any]:
        """Process image with OCR."""
        ...

    async def health_check(self) -> bool:
        """Check backend health."""
        ...


# =============================================================================
# UNIFIED ROUTER
# =============================================================================


class UnifiedOCRRouter(OrchestrationAgent):
    """
    Unified OCR Backend Router combining ML and rule-based selection.

    Features:
    - ML-based routing (XGBoost) when trained model available
    - Rule-based fallback with comprehensive heuristics
    - Automatic fallback chain on backend failure
    - Language-aware routing (prepared for multilingual)
    - Type-safe with Pydantic models
    - Performance tracking and feedback collection

    Routing Priority:
    1. User preference (if valid)
    2. Language-based routing (for non-German documents)
    3. ML model prediction (if enabled and trained)
    4. Rule-based selection (document characteristics)
    5. Default with fallback chain
    """

    # Backend specifications
    BACKEND_SPECS: Dict[BackendType, BackendCapabilities] = {
        BackendType.DEEPSEEK: BackendCapabilities(
            name="DeepSeek-Janus-Pro",
            german_label="DeepSeek-Janus-Pro",
            description="Beste Genauigkeit für komplexe deutsche Dokumente",
            vram_gb=12.0,
            supports_gpu=True,
            supports_cpu=False,
            best_for=["complex_layouts", "tables", "handwriting", "fraktur", "german"],
            languages=["de", "en"],
            avg_speed_pages_per_sec=2.5,
            accuracy_score=0.96,
            max_batch_size=4,
        ),
        BackendType.GOT_OCR: BackendCapabilities(
            name="GOT-OCR 2.0",
            german_label="GOT-OCR 2.0",
            description="Schnelle Verarbeitung für Standarddokumente",
            vram_gb=10.0,
            supports_gpu=True,
            supports_cpu=True,
            best_for=["formulas", "standard_text", "high_throughput", "tables"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=6.0,
            accuracy_score=0.92,
            max_batch_size=8,
        ),
        BackendType.SURYA: BackendCapabilities(
            name="Surya + Docling",
            german_label="Surya + Docling",
            description="CPU-basiert mit Layout-Analyse",
            vram_gb=0.0,
            supports_gpu=False,
            supports_cpu=True,
            best_for=["layout_preservation", "multi_language", "archival", "cpu_only"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=1.5,
            accuracy_score=0.88,
            max_batch_size=4,
        ),
        BackendType.SURYA_GPU: BackendCapabilities(
            name="Surya GPU",
            german_label="Surya GPU",
            description="GPU-beschleunigte Layout-Erkennung",
            vram_gb=4.0,
            supports_gpu=True,
            supports_cpu=False,
            best_for=["fast_layout", "batch_processing"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=4.0,
            accuracy_score=0.90,
            max_batch_size=16,
        ),
        BackendType.DONUT: BackendCapabilities(
            name="Donut",
            german_label="Donut (Multilingual)",
            description="Multilinguale Dokument-Erkennung mit Transformer (100+ Sprachen)",
            vram_gb=8.0,
            supports_gpu=True,
            supports_cpu=True,
            best_for=["multilingual", "cyrillic", "polish", "russian", "forms", "structured"],
            languages=["de", "en", "pl", "ru", "uk", "cs", "fr", "it", "es", "ja", "ko", "zh"],
            avg_speed_pages_per_sec=2.0,
            accuracy_score=0.91,
            max_batch_size=8,
        ),
        BackendType.HYBRID: BackendCapabilities(
            name="Hybrid-Modus",
            german_label="Hybrid-Modus",
            description="Maximale Genauigkeit durch Multi-Backend-Verarbeitung",
            vram_gb=12.0,
            supports_gpu=True,
            supports_cpu=True,
            best_for=["critical_documents", "maximum_accuracy"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=0.8,
            accuracy_score=0.98,
            max_batch_size=2,
        ),
        BackendType.TESSERACT: BackendCapabilities(
            name="Tesseract",
            german_label="Tesseract (Fallback)",
            description="Letzter Fallback für einfache Texte",
            vram_gb=0.0,
            supports_gpu=False,
            supports_cpu=True,
            best_for=["fallback", "simple_text"],
            languages=["de", "en"],
            avg_speed_pages_per_sec=0.5,
            accuracy_score=0.75,
            max_batch_size=1,
        ),
    }

    # Fallback chain order
    FALLBACK_ORDER = [
        BackendType.DEEPSEEK,
        BackendType.GOT_OCR,
        BackendType.DONUT,      # Multilingual Fallback
        BackendType.SURYA_GPU,
        BackendType.SURYA,
        BackendType.TESSERACT,
    ]

    def __init__(
        self,
        use_ml_routing: bool = True,
        model_dir: Optional[Path] = None,
        backends: Optional[Dict[BackendType, OCRBackend]] = None,
    ) -> None:
        """
        Initialize Unified OCR Router.

        Args:
            use_ml_routing: Enable ML-based routing
            model_dir: Directory for ML model storage
            backends: Optional dict of backend instances
        """
        super().__init__(name="unified_ocr_router")

        self.gpu_manager = GPUManager()
        self.use_ml_routing = use_ml_routing
        self.model_dir = model_dir or Path("models/ocr_router")
        self.backends = backends or {}

        # ML components (lazy loaded)
        self._ml_model = None
        self._ml_trainer = None

        # Language detector for multilingual routing
        self._language_detector = LanguageDetector()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "ml_predictions": 0,
            "rule_fallbacks": 0,
            "language_based": 0,
            "backend_selections": {b.value: 0 for b in BackendType},
            "fallback_used": 0,
        }

        # Initialize ML if enabled
        if self.use_ml_routing:
            self._init_ml_routing()

        logger.info(
            "Unified OCR Router initialisiert",
            extra={
                "use_ml": self.use_ml_routing,
                "ml_available": self._ml_model is not None,
            },
        )

    def _init_ml_routing(self) -> None:
        """Initialize ML routing components."""
        try:
            from app.agents.orchestration.ml_router_model import OCRRouterModel

            self._ml_model = OCRRouterModel(registry_path=self.model_dir)

            if self._ml_model.is_trained:
                logger.info("ML-Routing initialisiert mit trainiertem Modell")
            else:
                logger.info("ML-Routing: Modell nicht trainiert, nutze Regeln")

        except ImportError as e:
            logger.warning("ml_routing_nicht_verfuegbar", error=str(e))
            self.use_ml_routing = False
        except Exception as e:
            logger.error("ml_routing_init_fehler", error=str(e))
            self.use_ml_routing = False

    def _detect_document_language(
        self,
        analysis: DocumentAnalysis,
    ) -> Optional[LanguageDetectionResult]:
        """
        Detect language from document analysis.

        Uses detected_language field if present, otherwise returns None.
        Actual OCR text detection happens in process_with_fallback.
        """
        if analysis.detected_language:
            lang_code = LanguageCode.from_string(analysis.detected_language)
            if lang_code != LanguageCode.UNKNOWN:
                script = (
                    ScriptType.CYRILLIC
                    if self._language_detector.is_cyrillic_language(lang_code)
                    else ScriptType.LATIN
                )
                return LanguageDetectionResult(
                    primary_language=lang_code,
                    confidence=0.9,
                    script_type=script,
                    detection_method="document_metadata",
                )

        # Check explicit language list
        if analysis.languages:
            for lang in analysis.languages:
                if lang not in ("de", "en"):
                    lang_code = LanguageCode.from_string(lang)
                    if lang_code != LanguageCode.UNKNOWN:
                        script = (
                            ScriptType.CYRILLIC
                            if self._language_detector.is_cyrillic_language(lang_code)
                            else ScriptType.LATIN
                        )
                        return LanguageDetectionResult(
                            primary_language=lang_code,
                            confidence=0.8,
                            script_type=script,
                            detection_method="language_list",
                        )

        return None

    def _language_based_selection(
        self,
        lang_result: LanguageDetectionResult,
        resource_status: Dict[str, Any],
    ) -> Optional[RoutingResult]:
        """
        Select backend based on detected language.

        Prioritizes Donut for Cyrillic and non-DE/EN languages.
        """
        recommended = self._language_detector.get_recommended_backends(
            lang_result.primary_language
        )

        # Map to BackendType
        for backend_name in recommended:
            try:
                backend = BackendType.from_string(backend_name)
                if self._is_backend_available(backend, resource_status):
                    lang_name = lang_result.primary_language.value.upper()
                    return RoutingResult(
                        backend=backend,
                        reason=f"Sprache erkannt: {lang_name} ({lang_result.script_type.value})",
                        confidence=lang_result.confidence,
                        alternatives=[
                            BackendType.from_string(b)
                            for b in recommended[1:3]
                            if b != backend_name
                        ],
                        routing_method=RoutingMethod.LANGUAGE_BASED,
                        fallback_chain=self._get_fallback_chain(backend),
                    )
            except (ValueError, KeyError):
                continue

        return None

    def detect_text_language(self, text: str) -> LanguageDetectionResult:
        """
        Public method to detect language from text.

        Args:
            text: Text to analyze

        Returns:
            LanguageDetectionResult
        """
        return self._language_detector.detect(text)

    def _get_resource_status(self) -> Dict[str, Any]:
        """Get current resource availability."""
        gpu_status = self.gpu_manager.check_availability()
        return {
            "gpu_available": gpu_status.get("available", False),
            "gpu_memory_available_gb": gpu_status.get("free_memory_gb", 0),
            "queue_length": 0,  # TODO: Redis integration
        }

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Select optimal OCR backend.

        Args:
            input_data: Dict with document_metadata, sla_requirements, user_preferences

        Returns:
            RoutingResult as dict
        """
        self.validate_input(input_data, ["document_metadata"])

        # Parse input
        metadata = input_data["document_metadata"]
        if isinstance(metadata, dict):
            analysis = DocumentAnalysis(**metadata)
        else:
            analysis = metadata

        sla_data = input_data.get("sla_requirements", {})
        sla = SLARequirements(**sla_data) if sla_data else SLARequirements()

        preferences = input_data.get("user_preferences", {})

        # Update stats
        self._stats["total_requests"] += 1

        # Route
        result = await self.select_backend(analysis, sla, preferences)

        # Update stats
        self._stats["backend_selections"][result.backend.value] += 1

        self.logger.info(
            "router_backend_selected",
            backend=result.backend.value,
            reason=result.reason,
            confidence=result.confidence,
            method=result.routing_method.value,
        )

        return result.model_dump()

    async def select_backend(
        self,
        analysis: DocumentAnalysis,
        sla: Optional[SLARequirements] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> RoutingResult:
        """
        Select optimal backend for document.

        Args:
            analysis: Document analysis results
            sla: SLA requirements
            preferences: User preferences

        Returns:
            RoutingResult with selected backend and metadata
        """
        sla = sla or SLARequirements()
        preferences = preferences or {}
        resource_status = self._get_resource_status()

        # Priority 1: User preference
        if preferred := preferences.get("preferred_backend"):
            try:
                backend = BackendType.from_string(preferred)
                if self._is_backend_available(backend, resource_status):
                    return RoutingResult(
                        backend=backend,
                        reason="Benutzereinstellung",
                        confidence=1.0,
                        routing_method=RoutingMethod.USER_PREFERENCE,
                        fallback_chain=self._get_fallback_chain(backend),
                    )
            except ValueError:
                pass

        # Priority 2: Language-based routing for non-DE/EN documents
        lang_result = self._detect_document_language(analysis)
        if lang_result and lang_result.primary_language not in (
            LanguageCode.GERMAN,
            LanguageCode.ENGLISH,
            LanguageCode.UNKNOWN,
        ):
            result = self._language_based_selection(lang_result, resource_status)
            if result:
                self._stats["language_based"] += 1
                return result

        # Priority 3: ML-based routing
        if self.use_ml_routing and self._ml_model and self._ml_model.is_trained:
            try:
                result = await self._ml_selection(analysis, sla, resource_status)
                self._stats["ml_predictions"] += 1
                return result
            except Exception as e:
                logger.warning("ml_routing_fehlgeschlagen", error=str(e))
                self._stats["rule_fallbacks"] += 1

        # Priority 4: Rule-based selection
        return await self._rule_selection(analysis, sla, resource_status)

    async def _ml_selection(
        self,
        analysis: DocumentAnalysis,
        sla: SLARequirements,
        resource_status: Dict[str, Any],
    ) -> RoutingResult:
        """ML-based backend selection."""
        prediction = self._ml_model.predict(
            document_metadata=analysis.to_metadata_dict(),
            sla_requirements=sla.model_dump(),
            resource_status=resource_status,
        )

        backend = BackendType.from_string(prediction["backend"])

        # Validate backend availability
        if not self._is_backend_available(backend, resource_status):
            backend = self._find_available_fallback(backend, resource_status)

        return RoutingResult(
            backend=backend,
            reason=prediction.get("reason", "ML-Routing"),
            confidence=prediction["confidence"],
            alternatives=[
                BackendType.from_string(a["backend"])
                for a in prediction.get("alternatives", [])
            ],
            routing_method=RoutingMethod.ML,
            model_version=prediction.get("model_version"),
            probabilities=prediction.get("probabilities"),
            fallback_chain=self._get_fallback_chain(backend),
        )

    async def _rule_selection(
        self,
        analysis: DocumentAnalysis,
        sla: SLARequirements,
        resource_status: Dict[str, Any],
    ) -> RoutingResult:
        """Rule-based backend selection."""
        gpu_available = resource_status.get("gpu_available", False)

        # Rule 1: Formulas -> GOT-OCR
        if analysis.has_formulas:
            return RoutingResult(
                backend=BackendType.GOT_OCR,
                reason="Formelerkennung benötigt",
                confidence=0.95,
                alternatives=[BackendType.DEEPSEEK],
                routing_method=RoutingMethod.RULE_BASED,
                fallback_chain=self._get_fallback_chain(BackendType.GOT_OCR),
            )

        # Rule 2: Complex multimodal -> DeepSeek (if GPU)
        if analysis.has_handwriting or analysis.has_fraktur:
            if gpu_available:
                return RoutingResult(
                    backend=BackendType.DEEPSEEK,
                    reason="Handschrift/Fraktur erkannt",
                    confidence=0.95,
                    alternatives=[BackendType.HYBRID],
                    routing_method=RoutingMethod.RULE_BASED,
                    fallback_chain=self._get_fallback_chain(BackendType.DEEPSEEK),
                )

        # Rule 3: Critical documents -> Hybrid
        if sla.is_critical or analysis.document_type == "contract":
            return RoutingResult(
                backend=BackendType.HYBRID,
                reason="Kritisches Dokument - maximale Genauigkeit",
                confidence=0.98,
                alternatives=[BackendType.DEEPSEEK],
                routing_method=RoutingMethod.RULE_BASED,
                fallback_chain=self._get_fallback_chain(BackendType.HYBRID),
            )

        # Rule 4: Tables with GPU -> DeepSeek
        if analysis.has_tables and gpu_available:
            return RoutingResult(
                backend=BackendType.DEEPSEEK,
                reason="Tabellen mit GPU-Verarbeitung",
                confidence=0.90,
                alternatives=[BackendType.GOT_OCR, BackendType.HYBRID],
                routing_method=RoutingMethod.RULE_BASED,
                fallback_chain=self._get_fallback_chain(BackendType.DEEPSEEK),
            )

        # Rule 5: High complexity or low quality -> DeepSeek
        if analysis.complexity == "high" or analysis.quality_score < 0.7:
            if gpu_available:
                return RoutingResult(
                    backend=BackendType.DEEPSEEK,
                    reason="Hohe Komplexität oder niedrige Bildqualität",
                    confidence=0.85,
                    alternatives=[BackendType.HYBRID, BackendType.GOT_OCR],
                    routing_method=RoutingMethod.RULE_BASED,
                    fallback_chain=self._get_fallback_chain(BackendType.DEEPSEEK),
                )

        # Rule 6: No GPU -> Surya
        if not gpu_available:
            return RoutingResult(
                backend=BackendType.SURYA,
                reason="GPU nicht verfügbar - CPU-Fallback",
                confidence=0.7,
                alternatives=[BackendType.TESSERACT],
                routing_method=RoutingMethod.RULE_BASED,
                fallback_chain=self._get_fallback_chain(BackendType.SURYA),
            )

        # Rule 7: Fast SLA -> GOT-OCR
        if sla.max_processing_time_seconds < 10:
            return RoutingResult(
                backend=BackendType.GOT_OCR,
                reason="Schnelle Verarbeitung erforderlich",
                confidence=0.90,
                alternatives=[BackendType.SURYA_GPU],
                routing_method=RoutingMethod.RULE_BASED,
                fallback_chain=self._get_fallback_chain(BackendType.GOT_OCR),
            )

        # Default: GOT-OCR for standard documents
        return RoutingResult(
            backend=BackendType.GOT_OCR,
            reason="Standarddokument",
            confidence=0.85,
            alternatives=[BackendType.DEEPSEEK, BackendType.SURYA],
            routing_method=RoutingMethod.RULE_BASED,
            fallback_chain=self._get_fallback_chain(BackendType.GOT_OCR),
        )

    def _is_backend_available(
        self,
        backend: BackendType,
        resource_status: Dict[str, Any],
    ) -> bool:
        """Check if backend is available given current resources."""
        specs = self.BACKEND_SPECS.get(backend)
        if not specs:
            return False

        # Check GPU requirement
        if specs.vram_gb > 0 and not specs.supports_cpu:
            if not resource_status.get("gpu_available"):
                return False
            available_vram = resource_status.get("gpu_memory_available_gb", 0)
            if available_vram < specs.vram_gb * 0.8:  # 80% threshold
                return False

        return True

    def _find_available_fallback(
        self,
        primary: BackendType,
        resource_status: Dict[str, Any],
    ) -> BackendType:
        """Find first available backend in fallback chain."""
        for backend in self._get_fallback_chain(primary):
            if self._is_backend_available(backend, resource_status):
                return backend
        return BackendType.TESSERACT  # Last resort

    def _get_fallback_chain(self, primary: BackendType) -> List[BackendType]:
        """Get fallback chain starting from primary backend."""
        chain = [primary]
        for backend in self.FALLBACK_ORDER:
            if backend not in chain:
                chain.append(backend)
        return chain

    async def process_with_fallback(
        self,
        image_bytes: bytes,
        analysis: DocumentAnalysis,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process document with automatic fallback on failure.

        Args:
            image_bytes: Image data
            analysis: Document analysis
            options: Processing options

        Returns:
            OCR result with metadata
        """
        options = options or {}
        result = await self.select_backend(analysis)

        last_error = None
        for backend_type in result.fallback_chain:
            backend = self.backends.get(backend_type)
            if backend is None:
                continue

            try:
                logger.info("ocr_attempt", backend=backend_type.value)

                # Prepare options
                backend_options = self._prepare_backend_options(
                    backend_type, analysis, options
                )

                # Run OCR
                ocr_result = await backend.ocr(image_bytes, **backend_options)

                # Add metadata
                ocr_result["backend_used"] = backend_type.value
                ocr_result["fallback_attempted"] = backend_type != result.backend
                ocr_result["routing_info"] = result.model_dump()

                if backend_type != result.backend:
                    self._stats["fallback_used"] += 1

                return ocr_result

            except Exception as e:
                logger.error("backend_failed", backend=backend_type.value, error=str(e))
                last_error = e
                continue

        raise RuntimeError(f"Alle OCR-Backends fehlgeschlagen. Letzter Fehler: {last_error}")

    def _prepare_backend_options(
        self,
        backend_type: BackendType,
        analysis: DocumentAnalysis,
        user_options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare backend-specific options."""
        options = user_options.copy()

        # Language
        if analysis.languages:
            options["language"] = analysis.languages[0]

        # Backend-specific
        if backend_type == BackendType.GOT_OCR:
            if analysis.has_formulas:
                options["output_format"] = "latex"
                options["extract_formulas"] = True
            elif analysis.has_tables:
                options["output_format"] = "markdown"

        elif backend_type == BackendType.DEEPSEEK:
            options["extract_entities"] = analysis.document_type in ["invoice", "contract"]
            options["detect_layout"] = analysis.has_complex_layout
            options["extract_tables"] = analysis.has_tables
            options["extract_handwriting"] = analysis.has_handwriting

        elif backend_type in (BackendType.SURYA, BackendType.SURYA_GPU):
            options["extract_structure"] = True
            options["preserve_layout"] = analysis.has_complex_layout

        return options

    # =========================================================================
    # TRAINING & FEEDBACK
    # =========================================================================

    def collect_training_feedback(
        self,
        document_id: str,
        analysis: DocumentAnalysis,
        selected_backend: BackendType,
        processing_result: Dict[str, Any],
        sla: Optional[SLARequirements] = None,
    ) -> None:
        """Collect feedback for ML model training."""
        if not self._ml_trainer:
            return

        try:
            resource_status = self._get_resource_status()
            sla = sla or SLARequirements()

            from app.agents.orchestration.ml_trainer import TrainingSample

            sample = TrainingSample(
                sample_id=document_id,
                document_metadata=analysis.to_metadata_dict(),
                sla_requirements=sla.model_dump(),
                resource_status=resource_status,
                selected_backend=selected_backend.value,
                was_successful=processing_result.get("success", False),
                accuracy_score=processing_result.get("confidence", 0.0),
                processing_time_ms=processing_result.get("processing_time_ms", 0),
            )

            self._ml_trainer.data_buffer.add_sample(sample)

            # Record in model
            if self._ml_model:
                self._ml_model.record_feedback(
                    backend=selected_backend.value,
                    was_successful=processing_result.get("success", False),
                    accuracy=processing_result.get("confidence"),
                )

        except Exception as e:
            logger.warning("training_feedback_fehler", error=str(e))

    # =========================================================================
    # INFO & STATS
    # =========================================================================

    def get_backend_info(self, backend: BackendType) -> Optional[BackendCapabilities]:
        """Get backend capabilities."""
        return self.BACKEND_SPECS.get(backend)

    def get_available_backends(
        self,
        gpu_required: Optional[bool] = None,
    ) -> Dict[BackendType, BackendCapabilities]:
        """Get available backends with optional filtering."""
        result = {}
        resource_status = self._get_resource_status()

        for backend, specs in self.BACKEND_SPECS.items():
            requires_gpu = specs.vram_gb > 0 and not specs.supports_cpu

            if gpu_required is not None and requires_gpu != gpu_required:
                continue

            if self._is_backend_available(backend, resource_status):
                result[backend] = specs

        return result

    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        stats = dict(self._stats)

        if self._ml_model and self._ml_model.is_trained:
            stats["model_info"] = self._ml_model.get_model_info()

        return stats

    def is_ml_routing_available(self) -> bool:
        """Check if ML routing is available and ready."""
        return (
            self.use_ml_routing
            and self._ml_model is not None
            and self._ml_model.is_trained
        )

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all backends."""
        status = {
            "router": "healthy",
            "gpu_available": self._get_resource_status().get("gpu_available"),
            "ml_routing_available": self.is_ml_routing_available(),
            "backends": {},
        }

        for backend_type, backend in self.backends.items():
            if backend is None:
                status["backends"][backend_type.value] = "not_configured"
            else:
                try:
                    is_healthy = await asyncio.wait_for(
                        backend.health_check(), timeout=5.0
                    )
                    status["backends"][backend_type.value] = (
                        "healthy" if is_healthy else "unhealthy"
                    )
                except asyncio.TimeoutError:
                    status["backends"][backend_type.value] = "timeout"
                except Exception as e:
                    status["backends"][backend_type.value] = f"error: {e}"

        # Overall status
        backend_statuses = status["backends"].values()
        if all(s in ("healthy", "not_configured") for s in backend_statuses):
            status["router"] = "healthy"
        elif any(s == "healthy" for s in backend_statuses):
            status["router"] = "degraded"
        else:
            status["router"] = "unhealthy"

        return status
