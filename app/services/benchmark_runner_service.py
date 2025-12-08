# -*- coding: utf-8 -*-
"""
Benchmark Runner Service für Ablage-System OCR.

Orchestriert OCR-Benchmarks für Training Samples mit:
- 4-Way Backend-Vergleich (DeepSeek, GOT-OCR, Surya GPU, Surya CPU)
- CER/WER/Umlaut-Metriken gegen Ground Truth
- Performance-Tracking (Verarbeitungszeit, GPU-Speicher)
- Batch-Processing für große Stichproben

Feinpoliert und durchdacht - Enterprise-grade OCR Benchmarking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import asyncio
import time

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRTrainingSample,
    OCRBackendBenchmark,
    TrainingSampleStatus,
)
from app.db.schemas import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BackendComparisonResponse,
)
from app.ml.quality_metrics import OCRQualityCalculator, OCRQualityMetrics
from app.agents.base import OCRResult

logger = structlog.get_logger(__name__)


# =============================================================================
# Backend Configuration
# =============================================================================

@dataclass
class BackendConfig:
    """Konfiguration für ein OCR Backend."""
    name: str
    display_name: str
    requires_gpu: bool
    vram_gb: float
    agent_class: Optional[str] = None
    enabled: bool = True


# Verfügbare OCR Backends
AVAILABLE_BACKENDS: Dict[str, BackendConfig] = {
    "deepseek-janus-pro": BackendConfig(
        name="deepseek-janus-pro",
        display_name="DeepSeek-Janus-Pro",
        requires_gpu=True,
        vram_gb=12.0,
        agent_class="DeepSeekAgent",
    ),
    "got-ocr-2.0": BackendConfig(
        name="got-ocr-2.0",
        display_name="GOT-OCR 2.0",
        requires_gpu=True,
        vram_gb=10.0,
        agent_class="GOTOCRAgent",
    ),
    "surya-gpu": BackendConfig(
        name="surya-gpu",
        display_name="Surya GPU",
        requires_gpu=True,
        vram_gb=4.0,
        agent_class="SuryaGPUAgent",
    ),
    "surya": BackendConfig(
        name="surya",
        display_name="Surya (CPU)",
        requires_gpu=False,
        vram_gb=0.0,
        agent_class="SuryaDoclingAgent",
    ),
    "qwen-ocr": BackendConfig(
        name="qwen-ocr",
        display_name="Qwen2.5-VL-7B",
        requires_gpu=True,
        vram_gb=14.0,
        agent_class="QwenOCRAgent",
    ),
    "chandra-ocr": BackendConfig(
        name="chandra-ocr",
        display_name="Chandra OCR (9B)",
        requires_gpu=True,
        vram_gb=15.0,
        agent_class="ChandraOCRAgent",
    ),
    "olmocr-2": BackendConfig(
        name="olmocr-2",
        display_name="OlmOCR-2 (7B)",
        requires_gpu=True,
        vram_gb=14.0,
        agent_class="OlmOCRAgent",
    ),
    "paddle-ocr-v5": BackendConfig(
        name="paddle-ocr-v5",
        display_name="PaddleOCR PP-OCRv5",
        requires_gpu=False,
        vram_gb=0.0,
        agent_class="PaddleOCRAgent",
    ),
    "doctr": BackendConfig(
        name="doctr",
        display_name="docTR (CPU)",
        requires_gpu=False,
        vram_gb=0.0,
        agent_class="DocTRAgent",
    ),
}

DEFAULT_BACKENDS = ["deepseek-janus-pro", "chandra-ocr", "olmocr-2", "got-ocr-2.0", "surya-gpu", "surya", "qwen-ocr", "paddle-ocr-v5", "doctr"]


@dataclass
class BenchmarkResult:
    """Ergebnis eines einzelnen Benchmark-Laufs."""
    backend_name: str
    success: bool
    raw_text: Optional[str] = None
    confidence: Optional[float] = None
    cer: Optional[float] = None
    wer: Optional[float] = None
    umlaut_accuracy: Optional[float] = None
    capitalization_accuracy: Optional[float] = None
    processing_time_ms: int = 0
    gpu_memory_mb: Optional[int] = None
    insertions: int = 0
    deletions: int = 0
    substitutions: int = 0
    error_patterns: Dict[str, Any] = field(default_factory=dict)
    field_accuracies: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


class BenchmarkRunnerService:
    """
    Service für OCR Benchmark-Ausführung.

    Orchestriert Benchmarks über alle OCR Backends und berechnet
    Qualitätsmetriken gegen Ground Truth.
    """

    def __init__(self):
        """Initialisiere Benchmark Runner."""
        self.quality_calculator = OCRQualityCalculator()
        self._agents: Dict[str, Any] = {}
        self._agents_initialized = False

        logger.info(
            "benchmark_runner_initialized",
            available_backends=list(AVAILABLE_BACKENDS.keys())
        )

    async def _ensure_agents(self) -> None:
        """Lazy-Loading der OCR Agents."""
        if self._agents_initialized:
            return

        try:
            # Surya (CPU) - immer verfügbar
            from app.agents.ocr import SuryaDoclingAgent
            self._agents["surya"] = SuryaDoclingAgent()
        except ImportError as e:
            logger.warning("surya_agent_not_available", error=str(e))

        try:
            # PaddleOCR PP-OCRv5 (CPU) - immer verfügbar
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent
            self._agents["paddle-ocr-v5"] = PaddleOCRAgent()
        except ImportError as e:
            logger.warning("paddle_ocr_agent_not_available", error=str(e))

        try:
            # docTR (CPU) - deutsches Modell von Mindee
            from app.agents.ocr.doctr_agent import DocTRAgent
            self._agents["doctr"] = DocTRAgent()
        except ImportError as e:
            logger.warning("doctr_agent_not_available", error=str(e))

        try:
            import torch
            if torch.cuda.is_available():
                # GPU-basierte Agents
                try:
                    from app.agents.ocr import DeepSeekAgent
                    self._agents["deepseek-janus-pro"] = DeepSeekAgent()
                except ImportError as e:
                    logger.warning("deepseek_agent_not_available", error=str(e))

                try:
                    from app.agents.ocr import GOTOCRAgent
                    self._agents["got-ocr-2.0"] = GOTOCRAgent()
                except ImportError as e:
                    logger.warning("got_ocr_agent_not_available", error=str(e))

                try:
                    from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
                    self._agents["surya-gpu"] = SuryaGPUAgent()
                except ImportError as e:
                    logger.warning("surya_gpu_agent_not_available", error=str(e))

                try:
                    from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent
                    self._agents["qwen-ocr"] = QwenOCRAgent()
                except ImportError as e:
                    logger.warning("qwen_ocr_agent_not_available", error=str(e))

                try:
                    from app.agents.ocr.chandra_agent import ChandraOCRAgent
                    self._agents["chandra-ocr"] = ChandraOCRAgent()
                except ImportError as e:
                    logger.warning("chandra_ocr_agent_not_available", error=str(e))

                try:
                    from app.agents.ocr.olmocr_agent import OlmOCRAgent
                    self._agents["olmocr-2"] = OlmOCRAgent()
                except ImportError as e:
                    logger.warning("olmocr_agent_not_available", error=str(e))
        except ImportError:
            logger.warning("pytorch_not_available")

        self._agents_initialized = True
        logger.info(
            "ocr_agents_loaded",
            loaded_agents=list(self._agents.keys())
        )

    # =========================================================================
    # BENCHMARK EXECUTION
    # =========================================================================

    async def run_benchmark(
        self,
        db: AsyncSession,
        request: BenchmarkRunRequest
    ) -> BenchmarkRunResponse:
        """
        Führt einen Benchmark für ausgewählte Samples aus.

        Args:
            db: Datenbank-Session
            request: Benchmark-Anfrage mit Sample-IDs und Backends

        Returns:
            BenchmarkRunResponse mit Ergebnissen
        """
        await self._ensure_agents()

        start_time = time.time()
        backends = request.backends or DEFAULT_BACKENDS
        results_by_sample: Dict[str, List[BenchmarkResult]] = {}
        total_processed = 0
        total_failed = 0

        logger.info(
            "benchmark_run_started",
            sample_count=len(request.sample_ids),
            backends=backends
        )

        for sample_id in request.sample_ids:
            # Lade Sample mit Ground Truth
            sample = await self._get_sample(db, sample_id)
            if not sample:
                logger.warning(
                    "benchmark_sample_not_found",
                    sample_id=str(sample_id)[:8]
                )
                continue

            if not sample.ground_truth_text:
                logger.warning(
                    "benchmark_sample_no_ground_truth",
                    sample_id=str(sample_id)[:8]
                )
                continue

            # Benchmark für jeden Backend
            sample_results: List[BenchmarkResult] = []
            for backend_name in backends:
                result = await self._run_single_benchmark(
                    sample=sample,
                    backend_name=backend_name,
                    force_reprocess=request.force_reprocess
                )
                sample_results.append(result)

                # Speichere Ergebnis in DB
                await self._save_benchmark_result(db, sample, result)

                if result.success:
                    total_processed += 1
                else:
                    total_failed += 1

            results_by_sample[str(sample_id)] = sample_results

        await db.commit()

        total_time = int((time.time() - start_time) * 1000)

        logger.info(
            "benchmark_run_completed",
            total_processed=total_processed,
            total_failed=total_failed,
            total_time_ms=total_time
        )

        return BenchmarkRunResponse(
            success=True,
            samples_processed=total_processed,
            samples_failed=total_failed,
            backends_used=backends,
            total_time_ms=total_time,
        )

    async def _run_single_benchmark(
        self,
        sample: OCRTrainingSample,
        backend_name: str,
        force_reprocess: bool = False
    ) -> BenchmarkResult:
        """
        Führt einen einzelnen Benchmark für ein Sample/Backend aus.
        """
        start_time = time.time()

        # Check if agent available
        if backend_name not in self._agents:
            return BenchmarkResult(
                backend_name=backend_name,
                success=False,
                error=f"Backend '{backend_name}' nicht verfügbar"
            )

        agent = self._agents[backend_name]

        try:
            # Lade Bild
            image_path = Path(sample.file_path)
            if not image_path.exists():
                return BenchmarkResult(
                    backend_name=backend_name,
                    success=False,
                    error=f"Datei nicht gefunden: {sample.file_path}"
                )

            # GPU Speicher vor Verarbeitung (wenn verfügbar)
            gpu_memory_before = self._get_gpu_memory()

            # OCR ausführen
            ocr_result = await agent.execute(
                input_data={
                    "image_path": str(image_path),
                    "document_id": str(sample.id),
                },
                context={"backend": backend_name}
            )

            # GPU Speicher nach Verarbeitung
            gpu_memory_after = self._get_gpu_memory()
            gpu_memory_used = None
            if gpu_memory_before is not None and gpu_memory_after is not None:
                gpu_memory_used = gpu_memory_after - gpu_memory_before

            processing_time = int((time.time() - start_time) * 1000)

            # Extrahiere Text aus Result
            extracted_text = self._extract_text_from_result(ocr_result)

            if not extracted_text:
                return BenchmarkResult(
                    backend_name=backend_name,
                    success=False,
                    processing_time_ms=processing_time,
                    error="Kein Text extrahiert"
                )

            # Berechne Qualitätsmetriken gegen Ground Truth
            metrics = self.quality_calculator.calculate_full_metrics(
                reference=sample.ground_truth_text,
                hypothesis=extracted_text
            )

            # Analysiere Fehler-Patterns
            error_patterns = self._analyze_error_patterns(
                sample.ground_truth_text,
                extracted_text,
                metrics
            )

            # Feld-spezifische Genauigkeit (wenn Felder definiert)
            field_accuracies = {}
            if sample.extracted_fields:
                field_accuracies = self._calculate_field_accuracies(
                    sample.extracted_fields,
                    extracted_text
                )

            return BenchmarkResult(
                backend_name=backend_name,
                success=True,
                raw_text=extracted_text,
                confidence=ocr_result.get("confidence", 0.0) if isinstance(ocr_result, dict) else 0.0,
                cer=metrics.cer,
                wer=metrics.wer,
                umlaut_accuracy=metrics.umlaut_accuracy,
                capitalization_accuracy=metrics.capitalization_accuracy,
                processing_time_ms=processing_time,
                gpu_memory_mb=gpu_memory_used,
                insertions=metrics.insertions,
                deletions=metrics.deletions,
                substitutions=metrics.substitutions,
                error_patterns=error_patterns,
                field_accuracies=field_accuracies,
            )

        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            logger.error(
                "benchmark_backend_failed",
                backend=backend_name,
                sample_id=str(sample.id)[:8],
                error=str(e),
                exc_info=True
            )
            return BenchmarkResult(
                backend_name=backend_name,
                success=False,
                processing_time_ms=processing_time,
                error=str(e)
            )

    async def _save_benchmark_result(
        self,
        db: AsyncSession,
        sample: OCRTrainingSample,
        result: BenchmarkResult
    ) -> None:
        """Speichert Benchmark-Ergebnis in der Datenbank."""
        benchmark = OCRBackendBenchmark(
            training_sample_id=sample.id,
            backend_name=result.backend_name,
            backend_version=None,  # Könnte aus Agent extrahiert werden
            raw_text=result.raw_text,
            confidence_score=result.confidence,
            cer=result.cer,
            wer=result.wer,
            umlaut_accuracy=result.umlaut_accuracy,
            capitalization_accuracy=result.capitalization_accuracy,
            field_accuracies=result.field_accuracies if result.field_accuracies else None,
            error_patterns=result.error_patterns if result.error_patterns else None,
            insertions=result.insertions,
            deletions=result.deletions,
            substitutions=result.substitutions,
            processing_time_ms=result.processing_time_ms,
            gpu_memory_mb=result.gpu_memory_mb,
        )

        db.add(benchmark)

    # =========================================================================
    # COMPARISON & ANALYTICS
    # =========================================================================

    async def get_backend_comparison(
        self,
        db: AsyncSession,
        sample_ids: Optional[List[UUID]] = None,
        languages: Optional[List[str]] = None,
        document_types: Optional[List[str]] = None
    ) -> BackendComparisonResponse:
        """
        Vergleicht alle Backends anhand von Benchmark-Ergebnissen.

        Args:
            db: Datenbank-Session
            sample_ids: Optional - nur diese Samples berücksichtigen
            languages: Optional - Filter nach Sprache
            document_types: Optional - Filter nach Dokumenttyp

        Returns:
            BackendComparisonResponse mit aggregierten Metriken
        """
        # Build query with filters
        query = select(OCRBackendBenchmark)

        if sample_ids:
            query = query.where(
                OCRBackendBenchmark.training_sample_id.in_(sample_ids)
            )

        # Join with samples for filtering
        if languages or document_types:
            query = query.join(OCRTrainingSample)
            if languages:
                query = query.where(
                    OCRTrainingSample.language.in_(languages)
                )
            if document_types:
                query = query.where(
                    OCRTrainingSample.document_type.in_(document_types)
                )

        result = await db.execute(query)
        benchmarks = list(result.scalars().all())

        # Aggregiere pro Backend
        backend_metrics: Dict[str, Dict[str, Any]] = {}
        for benchmark in benchmarks:
            backend = benchmark.backend_name
            if backend not in backend_metrics:
                backend_metrics[backend] = {
                    "samples": 0,
                    "cer_sum": 0.0,
                    "wer_sum": 0.0,
                    "umlaut_sum": 0.0,
                    "time_sum": 0,
                    "cer_values": [],
                    "wer_values": [],
                }

            metrics = backend_metrics[backend]
            metrics["samples"] += 1

            if benchmark.cer is not None:
                metrics["cer_sum"] += benchmark.cer
                metrics["cer_values"].append(benchmark.cer)
            if benchmark.wer is not None:
                metrics["wer_sum"] += benchmark.wer
                metrics["wer_values"].append(benchmark.wer)
            if benchmark.umlaut_accuracy is not None:
                metrics["umlaut_sum"] += benchmark.umlaut_accuracy
            if benchmark.processing_time_ms is not None:
                metrics["time_sum"] += benchmark.processing_time_ms

        # Berechne Durchschnitte und finde besten
        comparison_data: Dict[str, Dict[str, Any]] = {}
        best_backend = None
        best_cer = float("inf")

        for backend, metrics in backend_metrics.items():
            count = metrics["samples"]
            if count == 0:
                continue

            avg_cer = metrics["cer_sum"] / count if metrics["cer_values"] else None
            avg_wer = metrics["wer_sum"] / count if metrics["wer_values"] else None
            avg_umlaut = metrics["umlaut_sum"] / count
            avg_time = metrics["time_sum"] / count

            # Percentile für CER
            cer_values = sorted(metrics["cer_values"])
            p50_cer = self._percentile(cer_values, 50)
            p90_cer = self._percentile(cer_values, 90)
            p95_cer = self._percentile(cer_values, 95)

            comparison_data[backend] = {
                "samples_processed": count,
                "avg_cer": round(avg_cer, 4) if avg_cer else None,
                "avg_wer": round(avg_wer, 4) if avg_wer else None,
                "avg_umlaut_accuracy": round(avg_umlaut, 4),
                "avg_processing_time_ms": int(avg_time),
                "p50_cer": round(p50_cer, 4) if p50_cer else None,
                "p90_cer": round(p90_cer, 4) if p90_cer else None,
                "p95_cer": round(p95_cer, 4) if p95_cer else None,
            }

            if avg_cer and avg_cer < best_cer:
                best_cer = avg_cer
                best_backend = backend

        return BackendComparisonResponse(
            backends=comparison_data,
            best_backend=best_backend,
            sample_count=len(set(b.training_sample_id for b in benchmarks)),
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_gpu_memory(self) -> Optional[int]:
        """Holt aktuellen GPU-Speicherverbrauch in MB."""
        try:
            import torch
            if torch.cuda.is_available():
                return int(torch.cuda.memory_allocated() / 1024 / 1024)
        except ImportError:
            pass
        return None

    def _extract_text_from_result(self, result: Any) -> Optional[str]:
        """Extrahiert Text aus verschiedenen Result-Formaten.

        Handles multiple result formats:
        - Wrapped format from agent.execute(): {"result": {...}, "metadata": {...}}
        - Direct result format: {"text": "...", ...}
        - String result
        - OCRResult object with .text attribute
        """
        if isinstance(result, dict):
            # Check for wrapped format from agent.execute()
            if "result" in result and isinstance(result["result"], dict):
                inner_result = result["result"]
                if "text" in inner_result:
                    return inner_result["text"]
                if "extracted_text" in inner_result:
                    return inner_result["extracted_text"]
                if "content" in inner_result:
                    return inner_result["content"]
                if "full_text" in inner_result:
                    return inner_result["full_text"]

            # Standard-Dict Format (direct result)
            if "text" in result:
                return result["text"]
            if "extracted_text" in result:
                return result["extracted_text"]
            if "content" in result:
                return result["content"]
            if "full_text" in result:
                return result["full_text"]

        if isinstance(result, str):
            return result

        # OCRResult Objekt
        if hasattr(result, "text"):
            return result.text

        return None

    def _analyze_error_patterns(
        self,
        ground_truth: str,
        hypothesis: str,
        metrics: OCRQualityMetrics
    ) -> Dict[str, Any]:
        """Analysiert typische Fehler-Patterns."""
        patterns = {
            "umlaut_errors": [],
            "number_errors": 0,
            "punctuation_errors": 0,
            "case_errors": 0,
            "common_substitutions": {},
        }

        # Umlaut-Fehler
        for umlaut in "äöüÄÖÜß":
            gt_count = ground_truth.count(umlaut)
            hyp_count = hypothesis.count(umlaut)
            if gt_count != hyp_count:
                patterns["umlaut_errors"].append({
                    "char": umlaut,
                    "expected": gt_count,
                    "found": hyp_count,
                })

        # Zahlen-Fehler (grobe Schätzung)
        import re
        gt_numbers = set(re.findall(r"\d+", ground_truth))
        hyp_numbers = set(re.findall(r"\d+", hypothesis))
        patterns["number_errors"] = len(gt_numbers.symmetric_difference(hyp_numbers))

        return patterns

    def _calculate_field_accuracies(
        self,
        extracted_fields: Dict[str, str],
        ocr_text: str
    ) -> Dict[str, float]:
        """Berechnet Genauigkeit für extrahierte Felder."""
        accuracies = {}
        for field_name, expected_value in extracted_fields.items():
            if expected_value:
                # Simple contains check
                if expected_value.lower() in ocr_text.lower():
                    accuracies[field_name] = 1.0
                else:
                    # Partial match
                    words = expected_value.split()
                    matched = sum(1 for w in words if w.lower() in ocr_text.lower())
                    accuracies[field_name] = matched / len(words) if words else 0.0

        return accuracies

    def _percentile(self, sorted_values: List[float], p: int) -> Optional[float]:
        """Berechnet Percentile für sortierte Liste."""
        if not sorted_values:
            return None
        k = (len(sorted_values) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_values) else f
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    async def _get_sample(
        self,
        db: AsyncSession,
        sample_id: UUID
    ) -> Optional[OCRTrainingSample]:
        """Holt ein Training Sample."""
        result = await db.execute(
            select(OCRTrainingSample)
            .where(OCRTrainingSample.id == sample_id)
        )
        return result.scalar_one_or_none()

    def get_available_backends(self) -> List[Dict[str, Any]]:
        """Gibt Liste der verfügbaren Backends zurück."""
        backends = []
        for name, config in AVAILABLE_BACKENDS.items():
            backends.append({
                "name": config.name,
                "display_name": config.display_name,
                "requires_gpu": config.requires_gpu,
                "vram_gb": config.vram_gb,
                "available": name in self._agents,
            })
        return backends


# Singleton
_benchmark_runner_service: Optional[BenchmarkRunnerService] = None


def get_benchmark_runner_service() -> BenchmarkRunnerService:
    """Gibt BenchmarkRunnerService-Singleton zurück."""
    global _benchmark_runner_service
    if _benchmark_runner_service is None:
        _benchmark_runner_service = BenchmarkRunnerService()
    return _benchmark_runner_service
