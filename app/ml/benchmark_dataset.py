# -*- coding: utf-8 -*-
"""
Benchmark Dataset Management für OCR-Qualitätsmessung.

Ermöglicht:
- Verwaltung von Ground-Truth-Annotationen
- Benchmark-Samples mit Metadaten
- Backend-Evaluierung gegen Ground-Truth
- Aggregierte Qualitätsreports

Feinpoliert und durchdacht - Wissenschaftliche Qualitätsbewertung.
"""

import json
import threading
import uuid
from app.core.safe_errors import safe_error_detail, safe_error_log
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import structlog

from app.ml.quality_metrics import (

    OCRQualityCalculator,
    OCRQualityMetrics,
    get_quality_calculator,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class DocumentType(str, Enum):
    """Dokumenttypen für Benchmarks."""
    INVOICE = "invoice"          # Rechnung
    CONTRACT = "contract"        # Vertrag
    LETTER = "letter"            # Brief
    FRAKTUR = "fraktur"          # Historische Frakturschrift
    TABLE = "table"              # Tabellen-Dokument
    FORM = "form"                # Formular
    HANDWRITTEN = "handwritten"  # Handschrift
    MIXED = "mixed"              # Gemischter Inhalt
    OTHER = "other"


class Difficulty(str, Enum):
    """Schwierigkeitsgrad des Samples."""
    EASY = "easy"       # Klarer Druck, gute Qualität
    MEDIUM = "medium"   # Normale Qualität
    HARD = "hard"       # Schlechte Qualität, Artefakte, Fraktur


class Language(str, Enum):
    """Sprache des Dokuments."""
    DE = "de"                # Modernes Deutsch
    DE_FRAKTUR = "de-fraktur"  # Deutsches Fraktur
    DE_SWISS = "de-swiss"    # Schweizer Deutsch
    DE_AUSTRIAN = "de-at"    # Österreichisches Deutsch
    EN = "en"                # Englisch
    MIXED = "mixed"          # Mehrsprachig


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BenchmarkSample:
    """
    Ein einzelnes Benchmark-Sample mit Ground-Truth.

    Attributes:
        id: Eindeutige Sample-ID
        image_path: Pfad zum Dokumentbild (relativ zum Benchmark-Verzeichnis)
        ground_truth_text: Der korrekte Text (Ground-Truth)
        document_type: Typ des Dokuments
        language: Sprache
        difficulty: Schwierigkeitsgrad
        has_fraktur: Enthält Frakturschrift
        has_handwriting: Enthält Handschrift
        has_tables: Enthält Tabellen
        expected_umlauts: Erwartete Umlaute im Text
        expected_entities: Erwartete Entitäten (IBAN, Datum, etc.)
        metadata: Zusätzliche Metadaten
        created_at: Erstellungszeitpunkt
    """
    id: str
    image_path: str
    ground_truth_text: str

    document_type: DocumentType = DocumentType.OTHER
    language: Language = Language.DE
    difficulty: Difficulty = Difficulty.MEDIUM

    has_fraktur: bool = False
    has_handwriting: bool = False
    has_tables: bool = False

    expected_umlauts: List[str] = field(default_factory=list)
    expected_entities: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für JSON-Serialisierung."""
        return {
            "id": self.id,
            "image_path": self.image_path,
            "ground_truth_text": self.ground_truth_text,
            "document_type": self.document_type.value,
            "language": self.language.value,
            "difficulty": self.difficulty.value,
            "has_fraktur": self.has_fraktur,
            "has_handwriting": self.has_handwriting,
            "has_tables": self.has_tables,
            "expected_umlauts": self.expected_umlauts,
            "expected_entities": self.expected_entities,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkSample":
        """Erstelle Sample aus Dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        return cls(
            id=data["id"],
            image_path=data["image_path"],
            ground_truth_text=data["ground_truth_text"],
            document_type=DocumentType(data.get("document_type", "other")),
            language=Language(data.get("language", "de")),
            difficulty=Difficulty(data.get("difficulty", "medium")),
            has_fraktur=data.get("has_fraktur", False),
            has_handwriting=data.get("has_handwriting", False),
            has_tables=data.get("has_tables", False),
            expected_umlauts=data.get("expected_umlauts", []),
            expected_entities=data.get("expected_entities", {}),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


@dataclass
class BenchmarkResult:
    """Ergebnis der Backend-Evaluierung für ein Sample."""
    sample_id: str
    backend_name: str
    ocr_output: str
    metrics: OCRQualityMetrics
    processing_time_ms: float
    success: bool
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "sample_id": self.sample_id,
            "backend_name": self.backend_name,
            "ocr_output": self.ocr_output[:500] + "..." if len(self.ocr_output) > 500 else self.ocr_output,
            "metrics": self.metrics.to_dict(),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "success": self.success,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BenchmarkReport:
    """Aggregierter Benchmark-Report für ein Backend."""
    backend_name: str
    total_samples: int
    successful_samples: int
    failed_samples: int

    # Aggregierte Metriken
    avg_cer: float
    avg_wer: float
    avg_umlaut_accuracy: float
    avg_processing_time_ms: float

    # Beste/Schlechteste
    min_cer: float
    max_cer: float
    min_wer: float
    max_wer: float

    # Nach Schwierigkeit
    metrics_by_difficulty: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Nach Dokumenttyp
    metrics_by_type: Dict[str, Dict[str, float]] = field(default_factory=dict)

    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "backend_name": self.backend_name,
            "total_samples": self.total_samples,
            "successful_samples": self.successful_samples,
            "failed_samples": self.failed_samples,
            "avg_cer": round(self.avg_cer, 4),
            "avg_wer": round(self.avg_wer, 4),
            "avg_umlaut_accuracy": round(self.avg_umlaut_accuracy, 4),
            "avg_processing_time_ms": round(self.avg_processing_time_ms, 2),
            "min_cer": round(self.min_cer, 4),
            "max_cer": round(self.max_cer, 4),
            "min_wer": round(self.min_wer, 4),
            "max_wer": round(self.max_wer, 4),
            "metrics_by_difficulty": self.metrics_by_difficulty,
            "metrics_by_type": self.metrics_by_type,
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# Benchmark Dataset Manager
# =============================================================================


class BenchmarkDataset:
    """
    Manager für OCR Benchmark Datasets.

    Features:
    - Sample-Verwaltung mit Persistenz
    - Filterung nach Typ, Schwierigkeit, Sprache
    - Backend-Evaluierung
    - Aggregierte Reports
    """

    SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        base_path: Optional[Path] = None,
        auto_save: bool = True,
    ) -> None:
        """
        Initialisiere Benchmark Dataset.

        Args:
            base_path: Basis-Pfad für Benchmark-Daten
            auto_save: Automatisch speichern bei Änderungen
        """
        self.base_path = base_path or Path("data/benchmarks")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.auto_save = auto_save

        self._samples: Dict[str, BenchmarkSample] = {}
        self._results: Dict[str, List[BenchmarkResult]] = {}  # sample_id -> results
        self._lock = threading.Lock()

        self._quality_calculator = get_quality_calculator()

        # Lade existierende Samples
        self._load_samples()

        logger.info(
            "BenchmarkDataset initialisiert",
            base_path=str(self.base_path),
            sample_count=len(self._samples),
        )

    # -------------------------------------------------------------------------
    # Sample Management
    # -------------------------------------------------------------------------

    def add_sample(
        self,
        image_path: str,
        ground_truth: str,
        document_type: str = "other",
        language: str = "de",
        difficulty: str = "medium",
        has_fraktur: bool = False,
        has_handwriting: bool = False,
        has_tables: bool = False,
        expected_umlauts: Optional[List[str]] = None,
        expected_entities: Optional[Dict[str, List[str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        sample_id: Optional[str] = None,
    ) -> BenchmarkSample:
        """
        Füge neues Benchmark-Sample hinzu.

        Args:
            image_path: Pfad zum Bild (relativ oder absolut)
            ground_truth: Der korrekte Text
            document_type: Dokumenttyp (invoice, contract, etc.)
            language: Sprache (de, de-fraktur, etc.)
            difficulty: Schwierigkeit (easy, medium, hard)
            has_fraktur: Enthält Fraktur
            has_handwriting: Enthält Handschrift
            has_tables: Enthält Tabellen
            expected_umlauts: Liste erwarteter Umlaute
            expected_entities: Dictionary mit Entitätstyp -> Werten
            metadata: Zusätzliche Metadaten
            sample_id: Optionale Sample-ID

        Returns:
            Das erstellte BenchmarkSample
        """
        if sample_id is None:
            sample_id = f"sample_{uuid.uuid4().hex[:8]}"

        # Auto-detect umlauts if not provided
        if expected_umlauts is None:
            expected_umlauts = [
                c for c in ground_truth if c in "äöüÄÖÜß"
            ]

        sample = BenchmarkSample(
            id=sample_id,
            image_path=image_path,
            ground_truth_text=ground_truth,
            document_type=DocumentType(document_type),
            language=Language(language),
            difficulty=Difficulty(difficulty),
            has_fraktur=has_fraktur,
            has_handwriting=has_handwriting,
            has_tables=has_tables,
            expected_umlauts=expected_umlauts,
            expected_entities=expected_entities or {},
            metadata=metadata or {},
        )

        with self._lock:
            self._samples[sample_id] = sample

        if self.auto_save:
            self._save_sample(sample)

        logger.info("benchmark_sample_hinzugefuegt", sample_id=sample_id)
        return sample

    def get_sample(self, sample_id: str) -> Optional[BenchmarkSample]:
        """Hole Sample nach ID."""
        return self._samples.get(sample_id)

    def remove_sample(self, sample_id: str) -> bool:
        """Entferne Sample."""
        with self._lock:
            if sample_id in self._samples:
                del self._samples[sample_id]

                # Lösche auch Datei
                sample_file = self._get_sample_path(sample_id)
                if sample_file.exists():
                    sample_file.unlink()

                logger.info("benchmark_sample_entfernt", sample_id=sample_id)
                return True
        return False

    def get_samples(
        self,
        document_type: Optional[str] = None,
        language: Optional[str] = None,
        difficulty: Optional[str] = None,
        has_fraktur: Optional[bool] = None,
        has_tables: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> Iterator[BenchmarkSample]:
        """
        Hole gefilterte Samples.

        Args:
            document_type: Filter nach Dokumenttyp
            language: Filter nach Sprache
            difficulty: Filter nach Schwierigkeit
            has_fraktur: Filter nach Fraktur
            has_tables: Filter nach Tabellen
            limit: Maximale Anzahl

        Yields:
            Gefilterte BenchmarkSamples
        """
        count = 0

        for sample in self._samples.values():
            # Apply filters
            if document_type and sample.document_type.value != document_type:
                continue
            if language and sample.language.value != language:
                continue
            if difficulty and sample.difficulty.value != difficulty:
                continue
            if has_fraktur is not None and sample.has_fraktur != has_fraktur:
                continue
            if has_tables is not None and sample.has_tables != has_tables:
                continue

            yield sample
            count += 1

            if limit and count >= limit:
                break

    def list_samples(self) -> List[BenchmarkSample]:
        """Liste alle Samples."""
        return list(self._samples.values())

    @property
    def sample_count(self) -> int:
        """Anzahl der Samples."""
        return len(self._samples)

    # -------------------------------------------------------------------------
    # Backend Evaluation
    # -------------------------------------------------------------------------

    def evaluate_backend(
        self,
        backend_name: str,
        process_func: Callable[[str], str],
        sample_filter: Optional[Dict[str, Any]] = None,
    ) -> List[BenchmarkResult]:
        """
        Evaluiere OCR-Backend gegen Benchmark-Samples.

        Args:
            backend_name: Name des Backends
            process_func: Funktion die Bildpfad -> OCR-Text umwandelt
            sample_filter: Optional Filter für Samples

        Returns:
            Liste von BenchmarkResults
        """
        import time

        results: List[BenchmarkResult] = []

        # Get filtered samples
        filter_kwargs = sample_filter or {}
        samples = list(self.get_samples(**filter_kwargs))

        if not samples:
            logger.warning("keine_samples_für_evaluierung")
            return results

        logger.info(
            "backend_evaluierung_gestartet",
            backend=backend_name,
            sample_count=len(samples),
        )

        for sample in samples:
            start_time = time.time()
            success = True
            error_message = None
            ocr_output = ""

            try:
                # Full path
                image_path = self.base_path / sample.image_path
                if not image_path.exists():
                    image_path = Path(sample.image_path)

                ocr_output = process_func(str(image_path))

            except Exception as e:
                success = False
                error_message = safe_error_detail(e, "Benchmark")
                logger.error(
                    "ocr_evaluierung_fehlgeschlagen",
                    sample_id=sample.id,
                    **safe_error_log(e),
                )

            processing_time_ms = (time.time() - start_time) * 1000

            # Calculate metrics
            if success and ocr_output:
                metrics = self._quality_calculator.calculate_full_metrics(
                    sample.ground_truth_text,
                    ocr_output,
                )
            else:
                # Dummy metrics for failed samples
                metrics = OCRQualityMetrics(
                    cer=1.0,
                    wer=1.0,
                    char_accuracy=0.0,
                    word_accuracy=0.0,
                    levenshtein_distance=len(sample.ground_truth_text),
                    insertions=0,
                    deletions=len(sample.ground_truth_text),
                    substitutions=0,
                )

            result = BenchmarkResult(
                sample_id=sample.id,
                backend_name=backend_name,
                ocr_output=ocr_output,
                metrics=metrics,
                processing_time_ms=processing_time_ms,
                success=success,
                error_message=error_message,
            )

            results.append(result)

            # Store result
            with self._lock:
                if sample.id not in self._results:
                    self._results[sample.id] = []
                self._results[sample.id].append(result)

        logger.info(
            "backend_evaluierung_abgeschlossen",
            backend=backend_name,
            erfolg=sum(1 for r in results if r.success),
            fehler=sum(1 for r in results if not r.success),
        )

        return results

    def generate_report(
        self,
        backend_name: str,
        results: Optional[List[BenchmarkResult]] = None,
    ) -> BenchmarkReport:
        """
        Generiere aggregierten Report für ein Backend.

        Args:
            backend_name: Backend-Name
            results: Optional vorberechnete Results

        Returns:
            BenchmarkReport mit aggregierten Metriken
        """
        if results is None:
            # Sammle alle Results für dieses Backend
            results = []
            for sample_results in self._results.values():
                for r in sample_results:
                    if r.backend_name == backend_name:
                        results.append(r)

        if not results:
            return BenchmarkReport(
                backend_name=backend_name,
                total_samples=0,
                successful_samples=0,
                failed_samples=0,
                avg_cer=0.0,
                avg_wer=0.0,
                avg_umlaut_accuracy=0.0,
                avg_processing_time_ms=0.0,
                min_cer=0.0,
                max_cer=0.0,
                min_wer=0.0,
                max_wer=0.0,
            )

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        # Aggregierte Metriken nur für erfolgreiche
        if successful:
            cers = [r.metrics.cer for r in successful]
            wers = [r.metrics.wer for r in successful]
            umlaut_accs = [r.metrics.umlaut_accuracy for r in successful]
            times = [r.processing_time_ms for r in successful]

            avg_cer = sum(cers) / len(cers)
            avg_wer = sum(wers) / len(wers)
            avg_umlaut = sum(umlaut_accs) / len(umlaut_accs)
            avg_time = sum(times) / len(times)
            min_cer = min(cers)
            max_cer = max(cers)
            min_wer = min(wers)
            max_wer = max(wers)
        else:
            avg_cer = avg_wer = avg_umlaut = avg_time = 0.0
            min_cer = max_cer = min_wer = max_wer = 0.0

        # Nach Schwierigkeit gruppieren
        metrics_by_difficulty: Dict[str, Dict[str, float]] = {}
        for diff in Difficulty:
            diff_results = [
                r for r in successful
                if self._samples.get(r.sample_id, BenchmarkSample(
                    id="", image_path="", ground_truth_text=""
                )).difficulty == diff
            ]
            if diff_results:
                metrics_by_difficulty[diff.value] = {
                    "avg_cer": sum(r.metrics.cer for r in diff_results) / len(diff_results),
                    "avg_wer": sum(r.metrics.wer for r in diff_results) / len(diff_results),
                    "sample_count": len(diff_results),
                }

        # Nach Dokumenttyp gruppieren
        metrics_by_type: Dict[str, Dict[str, float]] = {}
        for doc_type in DocumentType:
            type_results = [
                r for r in successful
                if self._samples.get(r.sample_id, BenchmarkSample(
                    id="", image_path="", ground_truth_text=""
                )).document_type == doc_type
            ]
            if type_results:
                metrics_by_type[doc_type.value] = {
                    "avg_cer": sum(r.metrics.cer for r in type_results) / len(type_results),
                    "avg_wer": sum(r.metrics.wer for r in type_results) / len(type_results),
                    "sample_count": len(type_results),
                }

        return BenchmarkReport(
            backend_name=backend_name,
            total_samples=len(results),
            successful_samples=len(successful),
            failed_samples=len(failed),
            avg_cer=avg_cer,
            avg_wer=avg_wer,
            avg_umlaut_accuracy=avg_umlaut,
            avg_processing_time_ms=avg_time,
            min_cer=min_cer,
            max_cer=max_cer,
            min_wer=min_wer,
            max_wer=max_wer,
            metrics_by_difficulty=metrics_by_difficulty,
            metrics_by_type=metrics_by_type,
        )

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _get_sample_path(self, sample_id: str) -> Path:
        """Hole Pfad für Sample-JSON."""
        return self.base_path / "samples" / f"{sample_id}.json"

    def _save_sample(self, sample: BenchmarkSample) -> None:
        """Speichere einzelnes Sample."""
        samples_dir = self.base_path / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)

        filepath = self._get_sample_path(sample.id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sample.to_dict(), f, indent=2, ensure_ascii=False)

    def _load_samples(self) -> None:
        """Lade alle gespeicherten Samples."""
        samples_dir = self.base_path / "samples"
        if not samples_dir.exists():
            return

        for filepath in samples_dir.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sample = BenchmarkSample.from_dict(data)
                self._samples[sample.id] = sample
            except Exception as e:
                logger.warning(
                    "sample_laden_fehlgeschlagen",
                    filepath=str(filepath),
                    **safe_error_log(e),
                )

    def save_all(self) -> None:
        """Speichere alle Samples."""
        for sample in self._samples.values():
            self._save_sample(sample)
        logger.info("alle_samples_gespeichert", count=len(self._samples))

    def export_results(self, filepath: Path) -> None:
        """Exportiere alle Ergebnisse als JSON."""
        export_data = {
            "schema_version": self.SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(),
            "sample_count": len(self._samples),
            "results": {},
        }

        for sample_id, results in self._results.items():
            export_data["results"][sample_id] = [r.to_dict() for r in results]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info("ergebnisse_exportiert", filepath=str(filepath))

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """Hole Dataset-Statistiken."""
        stats = {
            "total_samples": len(self._samples),
            "by_type": {},
            "by_difficulty": {},
            "by_language": {},
            "with_fraktur": 0,
            "with_tables": 0,
            "with_handwriting": 0,
        }

        for sample in self._samples.values():
            # By type
            type_key = sample.document_type.value
            stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

            # By difficulty
            diff_key = sample.difficulty.value
            stats["by_difficulty"][diff_key] = stats["by_difficulty"].get(diff_key, 0) + 1

            # By language
            lang_key = sample.language.value
            stats["by_language"][lang_key] = stats["by_language"].get(lang_key, 0) + 1

            # Flags
            if sample.has_fraktur:
                stats["with_fraktur"] += 1
            if sample.has_tables:
                stats["with_tables"] += 1
            if sample.has_handwriting:
                stats["with_handwriting"] += 1

        return stats


# =============================================================================
# Singleton
# =============================================================================

_benchmark_dataset: Optional[BenchmarkDataset] = None
_benchmark_lock = threading.Lock()


def get_benchmark_dataset() -> BenchmarkDataset:
    """Hole globale BenchmarkDataset-Instanz (thread-safe)."""
    global _benchmark_dataset
    if _benchmark_dataset is not None:
        return _benchmark_dataset
    with _benchmark_lock:
        if _benchmark_dataset is None:
            _benchmark_dataset = BenchmarkDataset()
    return _benchmark_dataset
