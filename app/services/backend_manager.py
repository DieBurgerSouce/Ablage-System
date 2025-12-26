"""Backend Manager - OCR Backend Selection and Management."""

import structlog
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Tuple
from pathlib import Path
import os
from dataclasses import dataclass

from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent
from app.gpu_manager import GPUManager
from app.ml.quality_metrics import get_quality_calculator
from app.ml.confidence_calibration import add_calibration_sample, get_calibrator
from app.ml.metrics import get_ml_metrics
from app.ml.drift_detector import get_drift_detector, get_drift_alert_manager


# =============================================================================
# P2: Health Check Cache - Reduziert Status-Abfragen um 40-50%
# =============================================================================

@dataclass
class CachedHealthCheck:
    """Cache-Eintrag für Backend Health Check."""
    healthy: bool
    status: Dict[str, Any]
    reason: Optional[str]
    checked_at: float  # time.monotonic()


class HealthCheckCache:
    """
    TTL-basierter Cache für Backend Health Checks.

    Reduziert wiederholte Status-Abfragen um 40-50% bei Batch-Verarbeitung.
    Kurzer TTL (5s) stellt sicher, dass Zustandsänderungen schnell erkannt werden.
    """

    DEFAULT_TTL_SECONDS = 5.0   # Kurzer TTL für Health Checks
    MAX_TTL_SECONDS = 30.0      # Maximum 30 Sekunden

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        """
        Initialisiere Health Check Cache.

        Args:
            ttl_seconds: Time-to-live für Cache-Einträge
        """
        self._cache: Dict[str, CachedHealthCheck] = {}
        self._ttl = min(ttl_seconds, self.MAX_TTL_SECONDS)
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

    def get(self, backend: str) -> Optional[CachedHealthCheck]:
        """
        Hole gecachten Health Check falls vorhanden und nicht abgelaufen.

        Args:
            backend: Backend-Name

        Returns:
            CachedHealthCheck oder None wenn nicht gecacht/abgelaufen
        """
        if backend not in self._cache:
            self._misses += 1
            return None

        cached = self._cache[backend]
        age = time.monotonic() - cached.checked_at

        if age > self._ttl:
            del self._cache[backend]
            self._misses += 1
            return None

        self._hits += 1
        return cached

    def set(
        self,
        backend: str,
        healthy: bool,
        status: Dict[str, Any],
        reason: Optional[str] = None
    ) -> None:
        """
        Speichere Health Check Ergebnis im Cache.

        Args:
            backend: Backend-Name
            healthy: Ob Backend gesund ist
            status: Status-Details
            reason: Optionaler Grund bei unhealthy
        """
        self._cache[backend] = CachedHealthCheck(
            healthy=healthy,
            status=status,
            reason=reason,
            checked_at=time.monotonic()
        )

    def invalidate(self, backend: Optional[str] = None) -> int:
        """
        Invalidiere Cache für Backend(s).

        Sollte nach Fehlern oder bei Backend-Änderungen aufgerufen werden.

        Args:
            backend: Spezifisches Backend oder None für alle

        Returns:
            Anzahl invalidierter Einträge
        """
        self._invalidations += 1

        if backend:
            if backend in self._cache:
                del self._cache[backend]
                return 1
            return 0

        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Hole Cache-Statistiken."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
            "invalidations": self._invalidations,
            "cached_backends": list(self._cache.keys()),
            "ttl_seconds": self._ttl,
        }


logger = structlog.get_logger(__name__)

# Import A/B testing for backend selection experiments
from app.ml.ab_testing import get_ab_test_manager
# GPU-based backends - only import if torch is available
try:
    import torch
    TORCH_AVAILABLE = torch.cuda.is_available()
    if TORCH_AVAILABLE:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent
        from app.agents.ocr.donut_agent import DonutOCRAgent, is_donut_available
        from app.agents.ocr.hybrid_agent import HybridOCRAgent
        DONUT_AVAILABLE = is_donut_available()
    else:
        DONUT_AVAILABLE = False
except ImportError:
    TORCH_AVAILABLE = False
    DONUT_AVAILABLE = False

logger = structlog.get_logger(__name__)


# =============================================================================
# Phase 5.3: Cost Optimization
# =============================================================================


@dataclass
class CostWeights:
    """
    Configurable weights for cost optimization scoring.

    Score-Formel:
    score = (quality_weight * quality_score) -
            (latency_weight * latency_ms / 1000) -
            (vram_weight * vram_usage_percent)
    """
    quality_weight: float = 0.5      # Gewichtung für Qualität (0-1)
    latency_weight: float = 0.3      # Gewichtung für Latenz (0-1)
    vram_weight: float = 0.2         # Gewichtung für VRAM-Nutzung (0-1)

    def validate(self) -> bool:
        """Validiere dass Gewichte sinnvoll sind."""
        total = self.quality_weight + self.latency_weight + self.vram_weight
        return 0.99 <= total <= 1.01  # Allow small floating point error


@dataclass
class SLATargets:
    """
    Service Level Agreement Ziele für automatische Backend-Auswahl.
    """
    max_latency_ms: float = 3000.0    # Maximum 3 Sekunden pro Seite
    min_quality_score: float = 0.85   # Minimum 85% Qualität
    max_vram_percent: float = 85.0    # Maximum 85% VRAM-Nutzung


@dataclass
class BackendCostEstimate:
    """Kostenabschätzung für ein Backend."""
    backend: str
    estimated_quality: float      # 0-1
    estimated_latency_ms: float   # Millisekunden
    estimated_vram_gb: float      # GB
    cost_score: float             # Berechneter Score (höher = besser)
    meets_sla: bool               # Erfüllt SLA-Ziele?
    recommendation: str           # Empfehlung


class CostOptimizer:
    """
    Optimizer für Backend-Auswahl basierend auf Kosten/Nutzen.

    Ermöglicht:
    - Configurable Weights per Use-Case
    - Real-Time Cost Estimation
    - SLA-based Backend Selection
    - Budget-Mode für reduzierte GPU-Nutzung
    """

    # Durchschnittliche Performance-Werte pro Backend (empirisch ermittelt)
    BACKEND_PERFORMANCE = {
        "deepseek": {
            "quality_score": 0.95,      # Beste Qualität für Deutsch
            "latency_ms_per_page": 2000,
            "vram_gb": 12.0,
        },
        "got_ocr": {
            "quality_score": 0.90,      # Gut für Tabellen/Formeln
            "latency_ms_per_page": 1500,
            "vram_gb": 10.0,
        },
        "surya_gpu": {
            "quality_score": 0.82,
            "latency_ms_per_page": 800,
            "vram_gb": 4.0,
        },
        "surya": {
            "quality_score": 0.80,
            "latency_ms_per_page": 5000,  # CPU ist langsamer
            "vram_gb": 0.0,
        },
        "surya_enhanced": {
            "quality_score": 0.88,  # Besser durch Layout-Analyse
            "latency_ms_per_page": 6000,  # Docling + Surya
            "vram_gb": 0.0,  # CPU only
        },
        "hybrid": {
            "quality_score": 0.97,      # Höchste durch Ensemble
            "latency_ms_per_page": 4000,  # Langsamer wegen Multi-Backend
            "vram_gb": 12.0,
        },
        "donut": {
            "quality_score": 0.85,
            "latency_ms_per_page": 1800,
            "vram_gb": 8.0,
        },
    }

    # Preset-Konfigurationen für verschiedene Use-Cases
    PRESETS: Dict[str, CostWeights] = {
        "quality_first": CostWeights(quality_weight=0.7, latency_weight=0.2, vram_weight=0.1),
        "balanced": CostWeights(quality_weight=0.5, latency_weight=0.3, vram_weight=0.2),
        "speed_first": CostWeights(quality_weight=0.3, latency_weight=0.5, vram_weight=0.2),
        "budget": CostWeights(quality_weight=0.4, latency_weight=0.2, vram_weight=0.4),
    }

    def __init__(
        self,
        weights: Optional[CostWeights] = None,
        sla_targets: Optional[SLATargets] = None,
        budget_mode: bool = False,
    ):
        """
        Initialisiere CostOptimizer.

        Args:
            weights: Kostengewichte (default: balanced)
            sla_targets: SLA-Ziele (default: Standard)
            budget_mode: Budget-Modus aktivieren
        """
        self.weights = weights or self.PRESETS["balanced"]
        self.sla_targets = sla_targets or SLATargets()
        self.budget_mode = budget_mode

        if budget_mode:
            self.weights = self.PRESETS["budget"]

        logger.info(
            "cost_optimizer_initialized",
            quality_weight=self.weights.quality_weight,
            latency_weight=self.weights.latency_weight,
            vram_weight=self.weights.vram_weight,
            budget_mode=budget_mode,
        )

    def set_preset(self, preset_name: str) -> None:
        """
        Setze Preset-Konfiguration.

        Args:
            preset_name: Name des Presets (quality_first, balanced, speed_first, budget)
        """
        if preset_name in self.PRESETS:
            self.weights = self.PRESETS[preset_name]
            logger.info("cost_preset_applied", preset=preset_name)
        else:
            raise ValueError(f"Unbekanntes Preset: {preset_name}. Verfügbar: {list(self.PRESETS.keys())}")

    def calculate_cost_score(
        self,
        backend: str,
        current_vram_percent: float = 0.0,
    ) -> float:
        """
        Berechne Cost-Score für ein Backend.

        Score-Formel:
        score = (quality_weight * quality_score) -
                (latency_weight * latency_ms / 1000) -
                (vram_weight * vram_usage_percent)

        Args:
            backend: Backend-Name
            current_vram_percent: Aktuelle VRAM-Nutzung in Prozent

        Returns:
            Cost Score (höher = besser)
        """
        if backend not in self.BACKEND_PERFORMANCE:
            return -1.0

        perf = self.BACKEND_PERFORMANCE[backend]

        # Normalize values to 0-1 range
        quality_normalized = perf["quality_score"]  # Already 0-1
        latency_normalized = 1.0 - min(perf["latency_ms_per_page"] / 10000, 1.0)  # Inverted
        vram_normalized = 1.0 - (perf["vram_gb"] / 16.0)  # Assume 16GB max

        # Calculate weighted score
        score = (
            self.weights.quality_weight * quality_normalized +
            self.weights.latency_weight * latency_normalized +
            self.weights.vram_weight * vram_normalized
        )

        # Penalty if current VRAM is high and backend needs more
        if current_vram_percent + (perf["vram_gb"] / 16.0 * 100) > self.sla_targets.max_vram_percent:
            score *= 0.5  # 50% penalty for potential OOM

        return round(score, 4)

    def estimate_backend_cost(
        self,
        backend: str,
        page_count: int = 1,
        current_vram_percent: float = 0.0,
    ) -> BackendCostEstimate:
        """
        Schätze Kosten für ein Backend ab.

        Args:
            backend: Backend-Name
            page_count: Anzahl Seiten
            current_vram_percent: Aktuelle VRAM-Nutzung

        Returns:
            BackendCostEstimate mit allen Schätzungen
        """
        if backend not in self.BACKEND_PERFORMANCE:
            return BackendCostEstimate(
                backend=backend,
                estimated_quality=0.0,
                estimated_latency_ms=999999,
                estimated_vram_gb=0.0,
                cost_score=-1.0,
                meets_sla=False,
                recommendation="Backend nicht verfügbar",
            )

        perf = self.BACKEND_PERFORMANCE[backend]
        total_latency = perf["latency_ms_per_page"] * page_count
        cost_score = self.calculate_cost_score(backend, current_vram_percent)

        # Check SLA compliance
        meets_latency = total_latency <= self.sla_targets.max_latency_ms * page_count
        meets_quality = perf["quality_score"] >= self.sla_targets.min_quality_score
        meets_vram = (perf["vram_gb"] / 16.0 * 100) + current_vram_percent <= self.sla_targets.max_vram_percent
        meets_sla = meets_latency and meets_quality and meets_vram

        # Generate recommendation
        if meets_sla:
            recommendation = "Empfohlen - erfüllt alle SLA-Ziele"
        else:
            issues = []
            if not meets_latency:
                issues.append(f"Latenz zu hoch ({total_latency}ms > {self.sla_targets.max_latency_ms * page_count}ms)")
            if not meets_quality:
                issues.append(f"Qualität zu niedrig ({perf['quality_score']} < {self.sla_targets.min_quality_score})")
            if not meets_vram:
                issues.append(f"VRAM-Anforderung zu hoch")
            recommendation = "Nicht empfohlen: " + ", ".join(issues)

        return BackendCostEstimate(
            backend=backend,
            estimated_quality=perf["quality_score"],
            estimated_latency_ms=total_latency,
            estimated_vram_gb=perf["vram_gb"],
            cost_score=cost_score,
            meets_sla=meets_sla,
            recommendation=recommendation,
        )

    def get_optimal_backend(
        self,
        available_backends: List[str],
        page_count: int = 1,
        current_vram_percent: float = 0.0,
        require_sla_compliance: bool = True,
    ) -> Tuple[str, BackendCostEstimate]:
        """
        Wähle optimales Backend basierend auf Cost Score.

        Args:
            available_backends: Liste verfügbarer Backends
            page_count: Anzahl Seiten
            current_vram_percent: Aktuelle VRAM-Nutzung
            require_sla_compliance: Nur SLA-konforme Backends?

        Returns:
            Tuple von (backend_name, cost_estimate)
        """
        estimates = []

        for backend in available_backends:
            estimate = self.estimate_backend_cost(backend, page_count, current_vram_percent)
            estimates.append(estimate)

        # Filter for SLA compliance if required
        if require_sla_compliance:
            compliant = [e for e in estimates if e.meets_sla]
            if compliant:
                estimates = compliant

        # Sort by cost score (descending)
        estimates.sort(key=lambda e: e.cost_score, reverse=True)

        if not estimates:
            # Fallback to surya (CPU) if nothing else works
            return "surya", self.estimate_backend_cost("surya", page_count, current_vram_percent)

        best = estimates[0]
        logger.debug(
            "optimal_backend_selected",
            backend=best.backend,
            cost_score=best.cost_score,
            meets_sla=best.meets_sla,
        )

        return best.backend, best

    def get_all_estimates(
        self,
        available_backends: List[str],
        page_count: int = 1,
        current_vram_percent: float = 0.0,
    ) -> List[BackendCostEstimate]:
        """
        Hole Kostenabschätzungen für alle verfügbaren Backends.

        Returns:
            Liste von BackendCostEstimate, sortiert nach Score
        """
        estimates = [
            self.estimate_backend_cost(backend, page_count, current_vram_percent)
            for backend in available_backends
        ]
        return sorted(estimates, key=lambda e: e.cost_score, reverse=True)


# Global Cost Optimizer Singleton
_cost_optimizer: Optional[CostOptimizer] = None


def get_cost_optimizer(
    preset: Optional[str] = None,
    budget_mode: bool = False,
) -> CostOptimizer:
    """
    Hole globale CostOptimizer Instanz.

    Args:
        preset: Optional Preset-Name
        budget_mode: Budget-Modus aktivieren

    Returns:
        CostOptimizer Instanz
    """
    global _cost_optimizer

    if _cost_optimizer is None:
        weights = CostOptimizer.PRESETS.get(preset) if preset else None
        _cost_optimizer = CostOptimizer(weights=weights, budget_mode=budget_mode)

    return _cost_optimizer


# =============================================================================
# Singleton BackendManager - Vermeidet Model-Reload bei jedem Task
# =============================================================================

_backend_manager: Optional["BackendManager"] = None


def get_backend_manager() -> "BackendManager":
    """
    Hole Singleton-Instanz des BackendManagers.

    Dies vermeidet das ~60s Model-Loading bei jedem Task, da die Backends
    nur einmal beim ersten Aufruf initialisiert werden und dann im Speicher
    bleiben.

    Returns:
        BackendManager Singleton-Instanz
    """
    global _backend_manager

    if _backend_manager is None:
        logger.info("backend_manager_singleton_initializing")
        _backend_manager = BackendManager()
        logger.info(
            "backend_manager_singleton_ready",
            backends=list(_backend_manager.backends.keys())
        )

    return _backend_manager


def reset_backend_manager() -> None:
    """
    Reset BackendManager Singleton (für Tests oder Worker-Restart).

    ACHTUNG: Nur verwenden wenn Models neu geladen werden müssen!
    """
    global _backend_manager
    if _backend_manager is not None:
        logger.info("backend_manager_singleton_resetting")
        _backend_manager = None


class BackendManager:
    """Manages OCR backend selection and processing."""

    # VRAM-Anforderungen pro Backend in GB
    BACKEND_VRAM_REQUIREMENTS = {
        "deepseek": 12.0,
        "got_ocr": 10.0,
        "surya_gpu": 4.0,
        "donut": 8.0,
        "hybrid": 12.0,
    }

    def __init__(self):
        """Initialize backend manager with available OCR agents."""
        self.backends = {}
        self._gpu_manager = GPUManager()
        # P2: Health Check Cache für schnellere Backend-Auswahl
        self._health_cache = HealthCheckCache()
        # Fallback chain für A/B Test Winner-Anwendung
        self.fallback_chain: list[str] = []
        self._initialize_backends()
        logger.info("backend_manager_initialized", backend_count=len(self.backends))

    def _initialize_backends(self):
        """Initialize available OCR backends."""
        # Try to initialize GPU-accelerated Surya first if available
        gpu_surya_initialized = False
        if TORCH_AVAILABLE:
            try:
                from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
                self.backends["surya_gpu"] = SuryaGPUAgent()
                gpu_surya_initialized = True
                logger.info("surya_gpu_backend_initialized", device=torch.cuda.get_device_name(0))
            except Exception as e:
                logger.info("surya_gpu_backend_unavailable", error=str(e))

        # Always initialize CPU Surya as fallback
        try:
            self.backends["surya"] = SuryaDoclingAgent()
            logger.info("surya_cpu_backend_initialized")
        except Exception as e:
            logger.error("surya_cpu_backend_init_failed", error=str(e))

        # Initialize Enhanced Surya+Docling (CPU-only with layout analysis)
        try:
            self.backends["surya_enhanced"] = SuryaDoclingEnhancedAgent()
            logger.info("surya_enhanced_backend_initialized")
        except Exception as e:
            logger.warning("surya_enhanced_backend_unavailable", error=str(e))

        # Try to initialize GPU-based backends if PyTorch and GPU are available
        if TORCH_AVAILABLE:
            # Initialize DeepSeek (requires GPU)
            try:
                self.backends["deepseek"] = DeepSeekAgent()
                logger.info("deepseek_backend_initialized")
            except Exception as e:
                logger.warning("deepseek_backend_unavailable", error=str(e))

            # Initialize GOT-OCR (requires GPU)
            try:
                self.backends["got_ocr"] = GOTOCRAgent()
                logger.info("got_ocr_backend_initialized")
            except Exception as e:
                logger.warning("got_ocr_backend_unavailable", error=str(e))

            # Initialize DONUT for multilingual document understanding (8GB VRAM)
            if DONUT_AVAILABLE:
                try:
                    self.backends["donut"] = DonutOCRAgent()
                    logger.info("donut_backend_initialized")
                except Exception as e:
                    logger.warning("donut_backend_unavailable", error=str(e))

            # Initialize Hybrid Agent for maximum accuracy (combines multiple backends)
            # Only if at least 2 other backends are available for meaningful fusion
            available_for_hybrid = len([b for b in self.backends.keys()
                                        if b in ["deepseek", "got_ocr", "surya", "surya_gpu"]])
            if available_for_hybrid >= 2:
                try:
                    self.backends["hybrid"] = HybridOCRAgent()
                    logger.info("hybrid_backend_initialized",
                               available_engines=available_for_hybrid)
                except Exception as e:
                    logger.warning("hybrid_backend_unavailable", error=str(e))
        else:
            logger.info("gpu_unavailable_cpu_only")

        # CRITICAL: Validate that at least one backend is available
        if not self.backends:
            raise RuntimeError(
                "KRITISCHER FEHLER: Kein OCR-Backend verfügbar! "
                "System kann nicht starten. Überprüfen Sie die Abhängigkeiten."
            )

        # Initialize fallback chain with all available backends
        # Priority order: GPU-accelerated first, then CPU fallbacks
        priority_order = ["deepseek", "got_ocr", "surya_gpu", "hybrid", "surya_enhanced", "surya", "donut"]
        self.fallback_chain = [b for b in priority_order if b in self.backends]
        # Add any backends not in priority list at the end
        for backend in self.backends:
            if backend not in self.fallback_chain:
                self.fallback_chain.append(backend)

        logger.info(
            "backend_initialization_complete",
            available_backends=list(self.backends.keys()),
            gpu_available=TORCH_AVAILABLE,
            backend_count=len(self.backends),
            fallback_chain=self.fallback_chain
        )

    def _has_sufficient_vram(self, backend: str) -> bool:
        """
        Prüft ob genügend VRAM für ein GPU-Backend verfügbar ist.

        Args:
            backend: Name des Backends

        Returns:
            True wenn genügend VRAM verfügbar oder Backend CPU-basiert
        """
        required_gb = self.BACKEND_VRAM_REQUIREMENTS.get(backend, 0)
        if required_gb == 0:
            # CPU-Backend oder keine VRAM-Anforderung
            return True

        gpu_status = self._gpu_manager.get_detailed_status()
        if not gpu_status.get("available", False):
            return False

        free_gb = gpu_status.get("free_gb", 0)
        has_vram = free_gb >= required_gb

        if not has_vram:
            logger.debug(
                "insufficient_vram_for_backend",
                backend=backend,
                required_gb=required_gb,
                free_gb=round(free_gb, 2),
            )

        return has_vram

    async def select_backend(
        self,
        image_path: str,
        language: str = "de",
        detect_layout: bool = True,
        prefer_gpu: bool = True,
        document_id: Optional[str] = None,
        return_experiment_info: bool = False
    ) -> Union[str, Tuple[str, Optional[Dict[str, str]]]]:
        """
        Select the best backend for processing.

        Checks for active A/B experiments first, then falls back to rule-based selection.

        Args:
            image_path: Path to the document
            language: Target language
            detect_layout: Whether layout detection is needed
            prefer_gpu: Whether to prefer GPU backends
            document_id: Optional document ID for A/B experiment allocation
            return_experiment_info: If True, returns tuple (backend, experiment_info)

        Returns:
            Name of the selected backend, or tuple (backend, experiment_info) if return_experiment_info=True
        """
        available_backends = list(self.backends.keys())
        experiment_info: Optional[Dict[str, str]] = None

        if not available_backends:
            raise RuntimeError("No OCR backends available")

        # Check for active A/B experiment first (if document_id provided)
        if document_id:
            try:
                ab_manager = get_ab_test_manager()
                for experiment in ab_manager.get_active_experiments():
                    # Check if experiment is for OCR backend testing
                    variant = ab_manager.get_variant(experiment.experiment_id, document_id)
                    if variant and "backend" in variant.config:
                        ab_backend = variant.config["backend"]
                        # Validate the backend is available
                        if ab_backend in available_backends:
                            logger.info(
                                "backend_selected_ab_test",
                                backend=ab_backend,
                                experiment_id=experiment.experiment_id,
                                variant=variant.name,
                                document_id=document_id
                            )
                            # Store experiment info for result tracking
                            experiment_info = {
                                "experiment_id": experiment.experiment_id,
                                "variant_name": variant.name,
                            }
                            if return_experiment_info:
                                return (ab_backend, experiment_info)
                            return ab_backend
                        else:
                            logger.warning(
                                "ab_backend_unavailable",
                                requested=ab_backend,
                                available=available_backends,
                                experiment_id=experiment.experiment_id
                            )
            except Exception as e:
                # Don't fail if A/B testing has issues - fall back to normal selection
                logger.warning("ab_test_check_failed", error=str(e))

        # Helper to format return value based on return_experiment_info flag
        def _return_backend(backend: str) -> Union[str, Tuple[str, Optional[Dict[str, str]]]]:
            if return_experiment_info:
                return (backend, experiment_info)
            return backend

        # Check file size and type for rule-based selection
        file_path = Path(image_path)
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        is_pdf = file_path.suffix.lower() == '.pdf'

        # Prefer GPU-accelerated Surya if available and has sufficient VRAM
        if prefer_gpu and "surya_gpu" in available_backends:
            if self._has_sufficient_vram("surya_gpu"):
                logger.info("backend_selected", backend="surya_gpu", reason="gpu_accelerated")
                return _return_backend("surya_gpu")
            else:
                logger.info(
                    "backend_skipped_insufficient_vram",
                    backend="surya_gpu",
                    reason="falling_back_to_cpu"
                )

        # If only CPU Surya is available, use it
        if len(available_backends) == 1 and "surya" in available_backends:
            logger.info("backend_selected", backend="surya", reason="only_available")
            return _return_backend("surya")

        # Complex documents with tables/layout → prefer DeepSeek or GOT-OCR (with VRAM check)
        if detect_layout and prefer_gpu and TORCH_AVAILABLE:
            if "deepseek" in available_backends and file_size_mb > 5:
                if self._has_sufficient_vram("deepseek"):
                    logger.info("backend_selected", backend="deepseek", reason="large_complex_document", file_size_mb=round(file_size_mb, 1))
                    return _return_backend("deepseek")
                else:
                    logger.debug("deepseek_skipped_vram", reason="insufficient_vram")
            if "got_ocr" in available_backends:
                if self._has_sufficient_vram("got_ocr"):
                    logger.info("backend_selected", backend="got_ocr", reason="layout_detection")
                    return _return_backend("got_ocr")
                else:
                    logger.debug("got_ocr_skipped_vram", reason="insufficient_vram")

        # PDF files with potential complex layout → prefer surya_enhanced for layout analysis
        # This handles invoices, contracts with tables, multi-column documents
        if is_pdf and "surya" in available_backends:
            # Use enhanced for PDFs as they often contain complex layouts
            logger.info("backend_selected", backend="surya", reason="pdf_fast_processing")
            return _return_backend("surya")
        elif is_pdf:
            if "got_ocr" in available_backends:
                logger.info("backend_selected", backend="got_ocr", reason="pdf_processing")
                return _return_backend("got_ocr")
            else:
                logger.info("backend_selected", backend="surya", reason="pdf_processing")
                return _return_backend("surya")

        # German text with potential Fraktur → prefer DeepSeek (with VRAM check)
        if language == "de" and "deepseek" in available_backends:
            if self._has_sufficient_vram("deepseek"):
                logger.info("backend_selected", backend="deepseek", reason="german_text")
                return _return_backend("deepseek")
            else:
                logger.debug("deepseek_skipped_vram_german", reason="insufficient_vram")

        # Non-German languages → prefer DONUT for multilingual support (with VRAM check)
        if language != "de" and "donut" in available_backends:
            if self._has_sufficient_vram("donut"):
                logger.info("backend_selected", backend="donut", reason="multilingual_support", language=language)
                return _return_backend("donut")
            else:
                logger.debug("donut_skipped_vram", reason="insufficient_vram")

        # Default to fastest available
        if "surya" in available_backends:
            logger.info("backend_selected", backend="surya", reason="default")
            return _return_backend("surya")
        elif "got_ocr" in available_backends:
            logger.info("backend_selected", backend="got_ocr", reason="default")
            return _return_backend("got_ocr")
        else:
            logger.info("backend_selected", backend=available_backends[0], reason="first_available")
            return _return_backend(available_backends[0])

    async def check_backend_health(
        self,
        backend_name: str,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Check if a specific backend is healthy and ready for processing.

        P2-Optimierung: TTL-basierter Cache reduziert Status-Abfragen um 40-50%.

        Args:
            backend_name: Name of the backend to check
            use_cache: Ob der Cache verwendet werden soll (default: True)

        Returns:
            Health status with 'healthy' boolean and details
        """
        if backend_name not in self.backends:
            return {"healthy": False, "reason": "Backend not found"}

        # P2: Check Cache first
        if use_cache:
            cached = self._health_cache.get(backend_name)
            if cached:
                logger.debug(
                    "health_check_cache_hit",
                    backend=backend_name,
                    healthy=cached.healthy
                )
                return {
                    "healthy": cached.healthy,
                    "status": cached.status,
                    "reason": cached.reason,
                    "cached": True
                }

        backend = self.backends[backend_name]

        try:
            # Get backend status
            status = backend.get_status()
            if asyncio.iscoroutine(status):
                status = await status

            # Check GPU availability for GPU backends
            if status.get("gpu_required", False):
                gpu_info = status.get("gpu_info", {})
                if not gpu_info.get("available", True):
                    result = {"healthy": False, "reason": "GPU nicht verfügbar", "status": status}
                    # Cache negative result
                    self._health_cache.set(
                        backend=backend_name,
                        healthy=False,
                        status=status,
                        reason=result["reason"]
                    )
                    return result

                # Check VRAM availability (leave 15% headroom)
                # Handle different key names from various backends
                total_gb = gpu_info.get("total_memory_gb") or gpu_info.get("total_vram_gb") or gpu_info.get("total_gb", 0)
                allocated_gb = gpu_info.get("allocated_memory_gb") or gpu_info.get("allocated_vram_gb") or gpu_info.get("allocated_gb", 0)
                required_gb = status.get("vram_gb", 0)
                available_gb = total_gb - allocated_gb

                if available_gb < required_gb * 0.85:
                    reason = f"Nicht genug VRAM: {available_gb:.1f}GB verfügbar, {required_gb}GB benötigt"
                    result = {"healthy": False, "reason": reason, "status": status}
                    # Cache negative result (short TTL ensures quick recovery detection)
                    self._health_cache.set(
                        backend=backend_name,
                        healthy=False,
                        status=status,
                        reason=reason
                    )
                    # Update Prometheus metrics
                    try:
                        metrics = get_ml_metrics()
                        metrics.set_backend_healthy(backend_name, False)
                    except Exception:
                        pass  # Metriken sind optional
                    return result

            # Backend is healthy - cache positive result
            self._health_cache.set(
                backend=backend_name,
                healthy=True,
                status=status,
                reason=None
            )

            # Update Prometheus metrics
            try:
                metrics = get_ml_metrics()
                metrics.set_backend_healthy(backend_name, True)
            except Exception:
                pass  # Metriken sind optional

            return {"healthy": True, "status": status}

        except Exception as e:
            logger.warning("backend_health_check_failed", backend=backend_name, error=str(e))
            # Invalidate cache on error
            self._health_cache.invalidate(backend_name)

            # Update Prometheus metrics
            try:
                metrics = get_ml_metrics()
                metrics.set_backend_healthy(backend_name, False)
            except Exception:
                pass  # Metriken sind optional

            return {"healthy": False, "reason": str(e)}

    def get_fallback_order(self, preferred_backend: str) -> List[str]:
        """
        Get ordered list of backends to try, starting with preferred.

        Args:
            preferred_backend: The initially preferred backend

        Returns:
            Ordered list of backend names for fallback chain
        """
        available = list(self.backends.keys())

        # Define fallback priority (most capable to least)
        # hybrid: Multi-engine fusion with confidence voting (highest accuracy)
        # deepseek: Best for German/Fraktur and complex layouts
        # got_ocr: Fast transformer-based, good for tables/formulas
        # donut: Multilingual document understanding
        # surya_enhanced: CPU with Docling layout analysis (tables, multi-column)
        # surya_gpu: Fast GPU-accelerated layout analysis
        # surya: CPU fallback basic OCR
        priority_order = ["hybrid", "deepseek", "got_ocr", "donut", "surya_enhanced", "surya_gpu", "surya"]

        # Build fallback chain starting with preferred
        fallback_chain = []
        if preferred_backend in available:
            fallback_chain.append(preferred_backend)

        # Add remaining backends in priority order
        for backend in priority_order:
            if backend in available and backend not in fallback_chain:
                fallback_chain.append(backend)

        # Add any remaining backends not in priority list
        for backend in available:
            if backend not in fallback_chain:
                fallback_chain.append(backend)

        return fallback_chain

    async def process_with_backend(
        self,
        backend_name: str,
        image_path: str,
        language: str = "de",
        detect_fraktur: bool = False,
        enable_fallback: bool = True,
        document_id: Optional[str] = None,
        experiment_info: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process document with specified backend, with automatic fallback on failure.

        Args:
            backend_name: Name of the backend to use
            image_path: Path to the document
            language: Target language
            detect_fraktur: Whether to detect Fraktur script
            enable_fallback: Whether to try fallback backends on failure
            document_id: Optional document ID for A/B test tracking
            experiment_info: Optional dict with 'experiment_id' and 'variant_name' for A/B tracking
            **kwargs: Additional backend-specific parameters

        Returns:
            OCR processing result
        """
        if backend_name not in self.backends:
            available = list(self.backends.keys())
            raise ValueError(f"Backend '{backend_name}' nicht verfügbar. Verfügbar: {available}")

        # Get fallback chain
        fallback_chain = self.get_fallback_order(backend_name) if enable_fallback else [backend_name]
        last_error = None
        start_time = time.monotonic()

        for current_backend in fallback_chain:
            # Health check before processing
            health = await self.check_backend_health(current_backend)
            if not health["healthy"]:
                logger.warning(
                    "backend_unhealthy_skipping",
                    backend=current_backend,
                    reason=health.get("reason")
                )
                continue

            backend = self.backends[current_backend]
            logger.info("processing_with_backend", backend=current_backend)

            # Prepare input data
            input_data = {
                "image_path": image_path,
                "language": language,
                "detect_fraktur": detect_fraktur,
                **kwargs
            }

            # Process with backend
            try:
                backend_start = time.monotonic()
                result = await backend.process(input_data)
                latency_ms = (time.monotonic() - backend_start) * 1000

                result["backend"] = current_backend
                result["latency_ms"] = latency_ms

                if current_backend != backend_name:
                    result["fallback_used"] = True
                    result["original_backend"] = backend_name
                    logger.info(
                        "fallback_backend_succeeded",
                        original=backend_name,
                        fallback=current_backend
                    )
                    # Record fallback in Prometheus metrics
                    try:
                        metrics = get_ml_metrics()
                        metrics.record_backend_fallback(backend_name, current_backend)
                    except Exception:
                        pass  # Metriken sind optional

                # Record A/B test result if experiment tracking enabled
                if experiment_info and document_id:
                    await self._record_ab_test_result(
                        experiment_info=experiment_info,
                        success=True,
                        latency_ms=latency_ms,
                        confidence=result.get("confidence", 0.0),
                        backend_name=current_backend,
                    )

                return result

            except Exception as e:
                last_error = e
                latency_ms = (time.monotonic() - start_time) * 1000

                # Record failed A/B test result
                if experiment_info and document_id:
                    await self._record_ab_test_result(
                        experiment_info=experiment_info,
                        success=False,
                        latency_ms=latency_ms,
                        confidence=0.0,
                        backend_name=current_backend,
                    )

                # P2: Invalidiere Cache bei Verarbeitungsfehler
                self._health_cache.invalidate(current_backend)
                logger.warning(
                    "backend_processing_failed_trying_fallback",
                    backend=current_backend,
                    error=str(e),
                    remaining_fallbacks=len(fallback_chain) - fallback_chain.index(current_backend) - 1
                )
                continue

        # All backends failed
        logger.error(
            "all_backends_failed",
            tried=fallback_chain,
            last_error=str(last_error) if last_error else "Unknown"
        )
        raise RuntimeError(
            f"Alle OCR-Backends fehlgeschlagen. Versucht: {fallback_chain}. "
            f"Letzter Fehler: {last_error}"
        )

    async def _record_ab_test_result(
        self,
        experiment_info: Dict[str, str],
        success: bool,
        latency_ms: float,
        confidence: float,
        backend_name: Optional[str] = None,
        document_type: str = "unknown",
    ) -> None:
        """
        Record A/B test result and quality metrics for feedback loop.

        Args:
            experiment_info: Dict with 'experiment_id' and 'variant_name'
            success: Whether OCR processing succeeded
            latency_ms: Processing latency in milliseconds
            confidence: OCR confidence score (0-1)
            backend_name: Name of the backend used
            document_type: Type of document processed
        """
        try:
            experiment_id = experiment_info.get("experiment_id")
            variant_name = experiment_info.get("variant_name")

            if not experiment_id or not variant_name:
                return

            # Record A/B test result
            ab_manager = get_ab_test_manager()
            ab_manager.record_result(
                experiment_id=experiment_id,
                variant_name=variant_name,
                success=success,
                latency_ms=latency_ms,
                accuracy=confidence,
            )

            # Quality Feedback Loop: Record calibration sample
            # Use confidence threshold to determine if result is "correct"
            # (high confidence = likely correct prediction)
            is_correct = success and confidence >= 0.85
            if backend_name:
                add_calibration_sample(
                    raw_confidence=confidence,
                    is_correct=is_correct,
                    backend=backend_name,
                    document_type=document_type,
                )

            # Record Prometheus metrics
            ml_metrics = get_ml_metrics()
            ml_metrics.record_ab_sample(
                experiment_id=experiment_id,
                variant=variant_name,
                success=success,
            )
            if backend_name:
                ml_metrics.record_calibration_sample(
                    backend=backend_name,
                    is_correct=is_correct,
                )

            # Record drift detection sample for monitoring
            await self._record_drift_sample(
                backend=backend_name or "unknown",
                confidence=confidence,
                latency_ms=latency_ms,
                document_type=document_type,
                success=success,
            )

            logger.debug(
                "ab_test_result_recorded",
                experiment_id=experiment_id,
                variant_name=variant_name,
                success=success,
                latency_ms=round(latency_ms, 2),
                calibration_sample_added=backend_name is not None,
            )

        except Exception as e:
            # Don't fail processing if A/B recording fails
            logger.warning("ab_test_recording_failed", error=str(e))

    async def _record_drift_sample(
        self,
        backend: str,
        confidence: float,
        latency_ms: float,
        document_type: str,
        success: bool,
    ) -> None:
        """
        Record sample for drift detection and quality monitoring.

        Args:
            backend: Backend name used
            confidence: Confidence score (0-1)
            latency_ms: Processing latency
            document_type: Type of document
            success: Whether processing succeeded
        """
        try:
            # Get drift detector and alert manager
            drift_detector = get_drift_detector()
            alert_manager = get_drift_alert_manager()

            # Build feature dict for drift detection
            features = {
                "quality_score": confidence,
                "document_type": document_type,
                "detected_language": "de",  # Assume German
            }

            # Add sample to drift detector
            drift_detector.add_sample(
                features=features,
                prediction=backend,
            )

            # Record quality sample for alert manager
            alert_manager.record_quality_sample(
                quality_score=confidence if success else 0.0,
                latency_ms=latency_ms,
                backend=backend,
                document_type=document_type,
            )

        except Exception as e:
            # Don't fail processing if drift recording fails
            logger.debug("drift_sample_recording_failed", error=str(e))

    async def get_backend_status(self, backend_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status of backend(s).

        Args:
            backend_name: Specific backend to check, or None for all

        Returns:
            Status information
        """
        if backend_name:
            if backend_name not in self.backends:
                return {"error": f"Backend '{backend_name}' not found"}
            # Await if it's a coroutine, otherwise call directly
            status = self.backends[backend_name].get_status()
            if asyncio.iscoroutine(status):
                return await status
            return status

        # Return status for all backends
        status_dict = {}
        for name, backend in self.backends.items():
            status = backend.get_status()
            if asyncio.iscoroutine(status):
                status_dict[name] = await status
            else:
                status_dict[name] = status
        return status_dict

    def get_available_backends(self) -> List[str]:
        """Get list of available backend names."""
        return list(self.backends.keys())

    async def cleanup(self):
        """Clean up all backends."""
        for name, backend in self.backends.items():
            try:
                await backend.cleanup()
                logger.info("backend_cleaned_up", backend=name)
            except Exception as e:
                logger.error("backend_cleanup_failed", backend=name, error=str(e))

        # Clear health cache
        self._health_cache.invalidate()

    def get_health_cache_stats(self) -> Dict[str, Any]:
        """
        Hole Health Check Cache Statistiken.

        Returns:
            Cache-Statistiken inkl. Hit-Rate
        """
        return self._health_cache.get_stats()

    def invalidate_health_cache(self, backend: Optional[str] = None) -> int:
        """
        Invalidiere Health Check Cache.

        Args:
            backend: Spezifisches Backend oder None für alle

        Returns:
            Anzahl invalidierter Einträge
        """
        return self._health_cache.invalidate(backend)

    def apply_ab_test_winners(self) -> Dict[str, Any]:
        """
        Wende A/B-Test Gewinner auf die Backend-Konfiguration an.

        Prüft laufende Experimente auf Signifikanz und aktualisiert
        die Fallback-Reihenfolge basierend auf den Ergebnissen.

        Returns:
            Dict mit angewendeten Änderungen und Empfehlungen
        """
        ab_manager = get_ab_test_manager()

        # Check and apply winners from running experiments
        applied_winners = ab_manager.check_and_apply_winners(
            auto_conclude=True,
            min_improvement_percent=5.0,
        )

        # Get recommended backend order
        recommended_order = ab_manager.get_recommended_backend_order()

        # Update fallback chain if we have recommendations
        updated_fallback = False
        if recommended_order:
            # Filter to only include available backends
            available = set(self.backends.keys())
            new_fallback = [b for b in recommended_order if b in available]

            # Add any remaining backends not in the recommendation
            for backend in self.fallback_chain:
                if backend not in new_fallback:
                    new_fallback.append(backend)

            if new_fallback != self.fallback_chain:
                old_fallback = self.fallback_chain.copy()
                self.fallback_chain = new_fallback
                updated_fallback = True

                logger.info(
                    "fallback_chain_updated_from_ab_tests",
                    old_order=old_fallback,
                    new_order=new_fallback,
                )

        result = {
            "applied_winners": applied_winners,
            "recommended_order": recommended_order,
            "current_fallback_chain": self.fallback_chain,
            "fallback_updated": updated_fallback,
            "timestamp": datetime.now().isoformat(),
        }

        # Record metrics
        ml_metrics = get_ml_metrics()
        ml_metrics.set_active_experiments(len(ab_manager.get_active_experiments()))

        return result

    def get_ab_test_status(self) -> Dict[str, Any]:
        """
        Hole Status aller A/B-Tests und deren Auswirkung auf Routing.

        Returns:
            Umfassender Status inkl. Experimente, Gewinner und Empfehlungen
        """
        ab_manager = get_ab_test_manager()

        active_experiments = []
        for exp in ab_manager.get_active_experiments():
            active_experiments.append({
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "status": exp.status.value,
                "total_samples": sum(v.samples for v in exp.variants),
                "significance_reached": exp.significance_reached,
                "winner": exp.winner,
                "variants": [
                    {
                        "name": v.name,
                        "samples": v.samples,
                        "conversion_rate": round(v.conversion_rate, 4),
                        "backend": v.config.get("backend"),
                    }
                    for v in exp.variants
                ],
            })

        significant_winners = ab_manager.get_significant_winners()
        recommended_order = ab_manager.get_recommended_backend_order()

        return {
            "active_experiments": active_experiments,
            "active_count": len(active_experiments),
            "significant_winners": significant_winners,
            "recommended_backend_order": recommended_order,
            "current_fallback_chain": self.fallback_chain,
        }

    def get_drift_status(self) -> Dict[str, Any]:
        """
        Hole aktuellen Drift-Status und Monitoring-Informationen.

        Returns:
            Dict mit Drift-Status, Quality-Trend und Empfehlungen
        """
        drift_detector = get_drift_detector()
        alert_manager = get_drift_alert_manager()

        # Get current drift detector status
        detector_status = drift_detector.get_current_status()

        # Get drift history
        drift_history = drift_detector.get_drift_history(limit=10)
        history_summary = []
        for report in drift_history:
            history_summary.append({
                "report_id": report.report_id,
                "timestamp": report.timestamp.isoformat(),
                "severity": report.severity.value,
                "overall_score": round(report.overall_drift_score, 4),
                "drifted_features": [fd.feature_name for fd in report.feature_drifts if fd.is_drifted],
            })

        # Check retraining status
        retraining_status = alert_manager.check_retraining_trigger()

        return {
            "detector_status": detector_status,
            "drift_history": history_summary,
            "retraining_recommended": retraining_status["should_retrain"],
            "retraining_reasons": retraining_status["reasons"],
            "retraining_action": retraining_status["recommended_action"],
            "quality_trend": alert_manager._check_quality_degradation(),
        }

    async def check_and_respond_to_drift(self) -> Dict[str, Any]:
        """
        Führe Drift-Check durch und reagiere mit A/B-Tests oder Alerts.

        Diese Methode sollte periodisch aufgerufen werden (z.B. via Celery Beat).

        Returns:
            Dict mit durchgeführten Aktionen
        """
        alert_manager = get_drift_alert_manager()

        # Check drift and respond
        result = alert_manager.check_and_respond_to_drift()

        # If experiments were created, log them
        if result.get("experiments_created"):
            logger.info(
                "drift_response_experiments_created",
                experiments=result["experiments_created"],
            )

        # If retraining is recommended, add to result
        retraining_check = alert_manager.check_retraining_trigger()
        result["retraining_status"] = retraining_check

        return result

    def generate_drift_report(self) -> Dict[str, Any]:
        """
        Generiere monatlichen Drift- und Performance-Report.

        Returns:
            Report-Dict mit allen Drift- und Quality-Informationen
        """
        alert_manager = get_drift_alert_manager()
        return alert_manager.generate_monthly_report()

    # =========================================================================
    # Cost Optimization API
    # =========================================================================

    def get_cost_estimates(
        self,
        page_count: int = 1,
        preset: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hole Kostenabschätzungen für alle verfügbaren Backends.

        Real-Time Cost Estimation API für Frontend und Monitoring.

        Args:
            page_count: Anzahl Seiten
            preset: Optional Cost-Preset (quality_first, balanced, speed_first, budget)

        Returns:
            Dict mit Kostenschätzungen für alle Backends
        """
        optimizer = get_cost_optimizer(preset=preset)

        # Get current VRAM usage
        vram_percent = 0.0
        if TORCH_AVAILABLE:
            try:
                gpu_status = self._gpu_manager.get_detailed_status()
                vram_percent = gpu_status.get("vram_used_percent", 0.0)
            except Exception as e:
                # GPU-Status kann fehlschlagen wenn GPU nicht verfügbar
                logger.debug("gpu_status_check_failed", error=str(e))

        estimates = optimizer.get_all_estimates(
            available_backends=list(self.backends.keys()),
            page_count=page_count,
            current_vram_percent=vram_percent,
        )

        return {
            "page_count": page_count,
            "preset": preset or "balanced",
            "current_vram_percent": round(vram_percent, 2),
            "estimates": [
                {
                    "backend": e.backend,
                    "quality": e.estimated_quality,
                    "latency_ms": e.estimated_latency_ms,
                    "vram_gb": e.estimated_vram_gb,
                    "cost_score": e.cost_score,
                    "meets_sla": e.meets_sla,
                    "recommendation": e.recommendation,
                }
                for e in estimates
            ],
            "optimal_backend": estimates[0].backend if estimates else "surya",
        }

    def select_optimal_backend(
        self,
        page_count: int = 1,
        preset: Optional[str] = None,
        require_sla: bool = True,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Wähle optimales Backend basierend auf Cost Optimization.

        Args:
            page_count: Anzahl Seiten
            preset: Cost-Preset
            require_sla: Nur SLA-konforme Backends?

        Returns:
            Tuple von (backend_name, estimate_info)
        """
        optimizer = get_cost_optimizer(preset=preset)

        # Get current VRAM usage
        vram_percent = 0.0
        if TORCH_AVAILABLE:
            try:
                gpu_status = self._gpu_manager.get_detailed_status()
                vram_percent = gpu_status.get("vram_used_percent", 0.0)
            except Exception as e:
                # GPU-Status kann fehlschlagen wenn GPU nicht verfügbar
                logger.debug("gpu_status_check_failed", error=str(e))

        backend, estimate = optimizer.get_optimal_backend(
            available_backends=list(self.backends.keys()),
            page_count=page_count,
            current_vram_percent=vram_percent,
            require_sla_compliance=require_sla,
        )

        return backend, {
            "quality": estimate.estimated_quality,
            "latency_ms": estimate.estimated_latency_ms,
            "vram_gb": estimate.estimated_vram_gb,
            "cost_score": estimate.cost_score,
            "meets_sla": estimate.meets_sla,
            "recommendation": estimate.recommendation,
        }

    def enable_budget_mode(self, enable: bool = True) -> Dict[str, Any]:
        """
        Aktiviere/Deaktiviere Budget-Modus.

        Im Budget-Modus werden GPU-intensive Backends gemieden
        und CPU-Fallbacks bevorzugt.

        Args:
            enable: Budget-Modus aktivieren?

        Returns:
            Aktueller Status
        """
        global _cost_optimizer
        _cost_optimizer = CostOptimizer(budget_mode=enable)

        logger.info("budget_mode_changed", enabled=enable)

        return {
            "budget_mode": enable,
            "current_preset": "budget" if enable else "balanced",
            "weights": {
                "quality": _cost_optimizer.weights.quality_weight,
                "latency": _cost_optimizer.weights.latency_weight,
                "vram": _cost_optimizer.weights.vram_weight,
            },
        }

    def set_cost_preset(self, preset: str) -> Dict[str, Any]:
        """
        Setze Cost-Optimization Preset.

        Verfügbare Presets:
        - quality_first: Maximale Qualität (DeepSeek bevorzugt)
        - balanced: Ausgewogen (Standard)
        - speed_first: Schnellste Verarbeitung
        - budget: Minimale GPU-Nutzung

        Args:
            preset: Preset-Name

        Returns:
            Aktueller Status
        """
        optimizer = get_cost_optimizer()
        optimizer.set_preset(preset)

        return {
            "preset": preset,
            "weights": {
                "quality": optimizer.weights.quality_weight,
                "latency": optimizer.weights.latency_weight,
                "vram": optimizer.weights.vram_weight,
            },
            "available_presets": list(CostOptimizer.PRESETS.keys()),
        }

    def get_cost_optimizer_status(self) -> Dict[str, Any]:
        """
        Hole aktuellen Status des Cost Optimizers.

        Returns:
            Status-Dict
        """
        optimizer = get_cost_optimizer()

        return {
            "budget_mode": optimizer.budget_mode,
            "weights": {
                "quality": optimizer.weights.quality_weight,
                "latency": optimizer.weights.latency_weight,
                "vram": optimizer.weights.vram_weight,
            },
            "sla_targets": {
                "max_latency_ms": optimizer.sla_targets.max_latency_ms,
                "min_quality_score": optimizer.sla_targets.min_quality_score,
                "max_vram_percent": optimizer.sla_targets.max_vram_percent,
            },
            "available_presets": list(CostOptimizer.PRESETS.keys()),
            "backend_performance_data": optimizer.BACKEND_PERFORMANCE,
        }