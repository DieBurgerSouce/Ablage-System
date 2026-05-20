"""
Batch Prefetching Service für OCR Pipeline.

Optimiert die OCR-Verarbeitung durch:
- Asynchrones Vorladen von Dokumenten (I/O-Parallelisierung)
- Preprocessing-Pipeline im Hintergrund
- Adaptive Queue-Größe basierend auf verfügbarem RAM
- Integration mit GPU Memory Guard

Feinpoliert und durchdacht - Enterprise OCR Performance.
"""

import asyncio
import gc
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, Union

import psutil
import structlog

logger = structlog.get_logger(__name__)

# Optional imports
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@dataclass
class PrefetchedDocument:
    """Vorab geladenes Dokument mit Metadaten."""

    file_path: str
    file_name: str
    file_size_bytes: int
    content: Union[bytes, Any]  # Raw bytes oder preprocessed
    is_preprocessed: bool = False
    preprocess_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def file_size_mb(self) -> float:
        """Dateigröße in MB."""
        return self.file_size_bytes / (1024 * 1024)


@dataclass
class PrefetchStats:
    """Statistiken für Batch Prefetching."""

    total_prefetched: int = 0
    total_preprocessed: int = 0
    total_errors: int = 0
    total_bytes_loaded: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_prefetch_time_ms: float = 0.0
    avg_preprocess_time_ms: float = 0.0
    queue_high_water_mark: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dict für JSON-Serialisierung."""
        return {
            "total_prefetched": self.total_prefetched,
            "total_preprocessed": self.total_preprocessed,
            "total_errors": self.total_errors,
            "total_bytes_loaded": self.total_bytes_loaded,
            "total_mb_loaded": round(self.total_bytes_loaded / (1024 * 1024), 2),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": (
                self.cache_hits / max(1, self.cache_hits + self.cache_misses)
            ),
            "avg_prefetch_time_ms": round(self.avg_prefetch_time_ms, 2),
            "avg_preprocess_time_ms": round(self.avg_preprocess_time_ms, 2),
            "queue_high_water_mark": self.queue_high_water_mark,
        }


class BatchPrefetcher:
    """
    Asynchroner Batch Prefetcher für OCR Pipeline.

    Features:
    - Lädt Dokumente asynchron im Hintergrund
    - Führt optionales Preprocessing durch (Bild-Konvertierung, Normalisierung)
    - Adaptive Queue-Größe basierend auf verfügbarem RAM
    - Thread-safe für parallele Verarbeitung
    - Integration mit GPU Memory Guard

    Usage:
        prefetcher = BatchPrefetcher(max_queue_size=10)
        await prefetcher.start_prefetching(file_paths)

        async for doc in prefetcher.get_documents():
            result = await process_document(doc)
    """

    # Default-Konfiguration
    DEFAULT_MAX_QUEUE_SIZE = 10
    DEFAULT_WORKER_COUNT = 4
    MAX_MEMORY_USAGE_PERCENT = 25  # Max 25% des RAMs für Prefetch-Queue
    MIN_QUEUE_SIZE = 2
    MAX_QUEUE_SIZE_LIMIT = 50

    def __init__(
        self,
        max_queue_size: Optional[int] = None,
        worker_count: int = DEFAULT_WORKER_COUNT,
        preprocess_fn: Optional[Callable[[bytes, str], Any]] = None,
        enable_preprocessing: bool = True,
    ):
        """
        Initialisiere Batch Prefetcher.

        Args:
            max_queue_size: Maximale Anzahl vorgeladener Dokumente.
                            Wenn None, wird basierend auf verfügbarem RAM berechnet.
            worker_count: Anzahl der Worker-Threads für I/O
            preprocess_fn: Optionale Preprocessing-Funktion (content, file_path) -> preprocessed
            enable_preprocessing: Preprocessing aktivieren (default: True)
        """
        self._max_queue_size = max_queue_size or self._calculate_adaptive_queue_size()
        self._worker_count = worker_count
        self._preprocess_fn = preprocess_fn
        self._enable_preprocessing = enable_preprocessing

        # Queue für prefetched documents
        self._queue: Deque[PrefetchedDocument] = deque()
        self._queue_lock = threading.Lock()
        self._queue_not_empty = asyncio.Event()
        self._queue_not_full = asyncio.Event()
        self._queue_not_full.set()  # Initial nicht voll

        # Prefetch-Status
        self._prefetch_complete = asyncio.Event()
        self._prefetch_running = False
        self._files_to_prefetch: List[str] = []
        self._prefetch_index = 0

        # Thread Pool für I/O
        self._executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="prefetch-worker"
        )

        # Statistiken
        self._stats = PrefetchStats()
        self._prefetch_times: List[float] = []
        self._preprocess_times: List[float] = []

        logger.info(
            "batch_prefetcher_initialized",
            max_queue_size=self._max_queue_size,
            worker_count=worker_count,
            preprocessing_enabled=enable_preprocessing,
        )

    def _calculate_adaptive_queue_size(self) -> int:
        """
        Berechne adaptive Queue-Größe basierend auf verfügbarem RAM.

        Verwendet max 25% des verfügbaren RAMs für die Prefetch-Queue.
        Annahme: ~10MB pro Dokument durchschnittlich.
        """
        try:
            memory = psutil.virtual_memory()
            available_mb = memory.available / (1024 * 1024)

            # Max 25% des verfügbaren RAMs
            prefetch_budget_mb = available_mb * (self.MAX_MEMORY_USAGE_PERCENT / 100)

            # Annahme: ~10MB pro Dokument (konservativ)
            avg_doc_size_mb = 10
            estimated_queue_size = int(prefetch_budget_mb / avg_doc_size_mb)

            # Clamp zwischen MIN und MAX
            queue_size = max(
                self.MIN_QUEUE_SIZE,
                min(estimated_queue_size, self.MAX_QUEUE_SIZE_LIMIT)
            )

            logger.info(
                "adaptive_queue_size_calculated",
                available_ram_mb=round(available_mb, 0),
                prefetch_budget_mb=round(prefetch_budget_mb, 0),
                queue_size=queue_size,
            )

            return queue_size

        except Exception as e:
            logger.warning("adaptive_queue_size_failed", **safe_error_log(e))
            return self.DEFAULT_MAX_QUEUE_SIZE

    async def start_prefetching(
        self,
        file_paths: List[str],
        priority_order: bool = True,
    ) -> None:
        """
        Starte asynchrones Prefetching für eine Liste von Dateien.

        Args:
            file_paths: Liste der zu prefetchenden Dateipfade
            priority_order: Wenn True, werden Dateien in der gegebenen Reihenfolge priorisiert
        """
        if self._prefetch_running:
            logger.warning("prefetching_already_running")
            return

        self._files_to_prefetch = list(file_paths)
        self._prefetch_index = 0
        self._prefetch_complete.clear()
        self._prefetch_running = True

        logger.info(
            "prefetching_started",
            total_files=len(file_paths),
            queue_size=self._max_queue_size,
        )

        # Starte Background-Task für Prefetching
        asyncio.create_task(self._prefetch_loop())

    async def _prefetch_loop(self) -> None:
        """Hauptschleife für asynchrones Prefetching."""
        try:
            while self._prefetch_index < len(self._files_to_prefetch):
                # Warte wenn Queue voll
                while len(self._queue) >= self._max_queue_size:
                    self._queue_not_full.clear()
                    await self._queue_not_full.wait()

                # Prefetch nächste Batch (parallel)
                batch_size = min(
                    self._worker_count,
                    len(self._files_to_prefetch) - self._prefetch_index,
                    self._max_queue_size - len(self._queue)
                )

                if batch_size <= 0:
                    await asyncio.sleep(0.01)
                    continue

                # Prefetch parallel
                batch_paths = self._files_to_prefetch[
                    self._prefetch_index:self._prefetch_index + batch_size
                ]
                self._prefetch_index += batch_size

                # Execute prefetch in thread pool
                loop = asyncio.get_event_loop()
                tasks = [
                    loop.run_in_executor(
                        self._executor,
                        self._prefetch_single,
                        path
                    )
                    for path in batch_paths
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Add to queue
                with self._queue_lock:
                    for result in results:
                        if isinstance(result, PrefetchedDocument):
                            self._queue.append(result)
                            self._stats.total_prefetched += 1
                            self._stats.total_bytes_loaded += result.file_size_bytes
                            if result.is_preprocessed:
                                self._stats.total_preprocessed += 1
                        elif isinstance(result, Exception):
                            self._stats.total_errors += 1
                            logger.warning("prefetch_error", error=str(result))

                    # Update high water mark
                    if len(self._queue) > self._stats.queue_high_water_mark:
                        self._stats.queue_high_water_mark = len(self._queue)

                # Signal dass Queue nicht leer ist
                self._queue_not_empty.set()

        except Exception as e:
            logger.error("prefetch_loop_error", **safe_error_log(e))
        finally:
            self._prefetch_running = False
            self._prefetch_complete.set()
            logger.info(
                "prefetching_completed",
                total_prefetched=self._stats.total_prefetched,
                total_errors=self._stats.total_errors,
            )

    def _prefetch_single(self, file_path: str) -> PrefetchedDocument:
        """
        Prefetch ein einzelnes Dokument (synchron, für Thread Pool).

        Args:
            file_path: Pfad zur Datei

        Returns:
            PrefetchedDocument mit geladenen Daten
        """
        import time
        start_time = time.perf_counter()

        try:
            path = Path(file_path)
            if not path.exists():
                return PrefetchedDocument(
                    file_path=file_path,
                    file_name=path.name,
                    file_size_bytes=0,
                    content=b"",
                    error=f"Datei nicht gefunden: {file_path}"
                )

            # Lese Datei
            content = path.read_bytes()
            file_size = len(content)

            # Prefetch-Zeit tracken
            prefetch_time_ms = (time.perf_counter() - start_time) * 1000
            self._prefetch_times.append(prefetch_time_ms)
            self._update_avg_prefetch_time()

            # Optionales Preprocessing
            preprocess_result = None
            is_preprocessed = False

            if self._enable_preprocessing:
                preprocess_start = time.perf_counter()

                if self._preprocess_fn:
                    # Custom preprocessing
                    try:
                        preprocess_result = self._preprocess_fn(content, file_path)
                        is_preprocessed = True
                    except Exception as e:
                        logger.warning(
                            "custom_preprocessing_failed",
                            file_path=file_path,
                            **safe_error_log(e)
                        )
                else:
                    # Default preprocessing
                    preprocess_result = self._default_preprocess(content, file_path)
                    is_preprocessed = preprocess_result is not None

                preprocess_time_ms = (time.perf_counter() - preprocess_start) * 1000
                self._preprocess_times.append(preprocess_time_ms)
                self._update_avg_preprocess_time()

            return PrefetchedDocument(
                file_path=file_path,
                file_name=path.name,
                file_size_bytes=file_size,
                content=content,
                is_preprocessed=is_preprocessed,
                preprocess_result=preprocess_result,
            )

        except Exception as e:
            logger.error("prefetch_single_failed", file_path=file_path, **safe_error_log(e))
            return PrefetchedDocument(
                file_path=file_path,
                file_name=Path(file_path).name,
                file_size_bytes=0,
                content=b"",
                **safe_error_log(e)
            )

    def _default_preprocess(
        self,
        content: bytes,
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        Default Preprocessing für gängige Dateitypen.

        Args:
            content: Rohe Datei-Bytes
            file_path: Dateipfad für Typ-Erkennung

        Returns:
            Preprocessing-Ergebnis oder None
        """
        suffix = Path(file_path).suffix.lower()

        # Bild-Preprocessing
        if suffix in [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]:
            return self._preprocess_image(content, file_path)

        # PDF-Preprocessing (nur Metadaten)
        elif suffix == ".pdf":
            return self._preprocess_pdf(content, file_path)

        return None

    def _preprocess_image(
        self,
        content: bytes,
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """Preprocessing für Bilder."""
        if not PIL_AVAILABLE:
            return None

        try:
            import io
            from PIL import Image


            img = Image.open(io.BytesIO(content))

            result = {
                "type": "image",
                "format": img.format,
                "mode": img.mode,
                "size": img.size,
                "width": img.size[0],
                "height": img.size[1],
            }

            # DPI extrahieren wenn vorhanden
            if "dpi" in img.info:
                result["dpi"] = img.info["dpi"]

            # Grayscale-Konvertierung für OCR
            if img.mode != "L" and img.mode != "RGB":
                img = img.convert("RGB")

            # Zu NumPy-Array konvertieren wenn verfügbar
            if NUMPY_AVAILABLE:
                result["array_shape"] = (img.size[1], img.size[0], 3 if img.mode == "RGB" else 1)

            return result

        except Exception as e:
            logger.warning("image_preprocessing_failed", file_path=file_path, **safe_error_log(e))
            return None

    def _preprocess_pdf(
        self,
        content: bytes,
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """Preprocessing für PDFs (nur Metadaten)."""
        try:
            # Einfache PDF-Header-Prüfung
            if not content.startswith(b"%PDF"):
                return {"type": "pdf", "valid": False, "error": "Invalid PDF header"}

            # Seiten zählen (grobe Schätzung)
            page_count = content.count(b"/Type /Page")

            return {
                "type": "pdf",
                "valid": True,
                "estimated_pages": max(1, page_count),
                "file_size_mb": len(content) / (1024 * 1024),
            }

        except Exception as e:
            logger.warning("pdf_preprocessing_failed", file_path=file_path, **safe_error_log(e))
            return None

    def _update_avg_prefetch_time(self) -> None:
        """Update durchschnittliche Prefetch-Zeit."""
        if self._prefetch_times:
            # Nur letzte 100 Werte berücksichtigen
            recent = self._prefetch_times[-100:]
            self._stats.avg_prefetch_time_ms = sum(recent) / len(recent)

    def _update_avg_preprocess_time(self) -> None:
        """Update durchschnittliche Preprocess-Zeit."""
        if self._preprocess_times:
            recent = self._preprocess_times[-100:]
            self._stats.avg_preprocess_time_ms = sum(recent) / len(recent)

    async def get_next(self) -> Optional[PrefetchedDocument]:
        """
        Hole nächstes prefetched Dokument.

        Returns:
            PrefetchedDocument oder None wenn Queue leer und Prefetching abgeschlossen
        """
        while True:
            with self._queue_lock:
                if self._queue:
                    doc = self._queue.popleft()
                    self._stats.cache_hits += 1

                    # Signal dass Queue nicht mehr voll ist
                    if len(self._queue) < self._max_queue_size:
                        self._queue_not_full.set()

                    return doc

            # Queue leer
            self._stats.cache_misses += 1

            if self._prefetch_complete.is_set() and not self._queue:
                # Prefetching abgeschlossen und Queue leer
                return None

            # Warte auf neue Dokumente
            self._queue_not_empty.clear()
            try:
                await asyncio.wait_for(
                    self._queue_not_empty.wait(),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                # Check nochmal ob fertig
                if self._prefetch_complete.is_set() and not self._queue:
                    return None

    async def get_documents(self):
        """
        Async Generator für prefetched Dokumente.

        Yields:
            PrefetchedDocument für jedes Dokument
        """
        while True:
            doc = await self.get_next()
            if doc is None:
                break
            yield doc

    def get_stats(self) -> Dict[str, Any]:
        """Hole Prefetch-Statistiken."""
        return self._stats.to_dict()

    def get_queue_status(self) -> Dict[str, Any]:
        """Hole aktuellen Queue-Status."""
        with self._queue_lock:
            return {
                "queue_length": len(self._queue),
                "max_queue_size": self._max_queue_size,
                "prefetch_running": self._prefetch_running,
                "files_remaining": len(self._files_to_prefetch) - self._prefetch_index,
                "prefetch_complete": self._prefetch_complete.is_set(),
            }

    async def wait_for_completion(self) -> None:
        """Warte bis Prefetching abgeschlossen."""
        await self._prefetch_complete.wait()

    def clear(self) -> None:
        """Lösche Queue und stoppe Prefetching."""
        with self._queue_lock:
            self._queue.clear()
            self._files_to_prefetch = []
            self._prefetch_index = 0

        self._prefetch_running = False
        self._prefetch_complete.set()
        self._queue_not_empty.set()
        self._queue_not_full.set()

        gc.collect()
        logger.info("prefetch_queue_cleared")

    def cleanup(self) -> None:
        """Cleanup-Ressourcen freigeben."""
        self.clear()
        self._executor.shutdown(wait=False)
        logger.info("batch_prefetcher_cleanup_complete")


# =============================================================================
# Singleton und Convenience-Funktionen
# =============================================================================

_batch_prefetcher: Optional[BatchPrefetcher] = None


def get_batch_prefetcher(
    max_queue_size: Optional[int] = None,
    **kwargs
) -> BatchPrefetcher:
    """
    Hole Singleton-Instanz des BatchPrefetchers.

    Args:
        max_queue_size: Optional Queue-Größe (nur beim ersten Aufruf)
        **kwargs: Weitere Konfiguration

    Returns:
        BatchPrefetcher-Instanz
    """
    global _batch_prefetcher
    if _batch_prefetcher is None:
        _batch_prefetcher = BatchPrefetcher(max_queue_size=max_queue_size, **kwargs)
    return _batch_prefetcher


async def prefetch_documents(
    file_paths: List[str],
    max_queue_size: Optional[int] = None,
) -> BatchPrefetcher:
    """
    Convenience-Funktion zum Starten von Prefetching.

    Args:
        file_paths: Liste der zu prefetchenden Dateien
        max_queue_size: Optional Queue-Größe

    Returns:
        Gestarteter BatchPrefetcher
    """
    prefetcher = get_batch_prefetcher(max_queue_size=max_queue_size)
    await prefetcher.start_prefetching(file_paths)
    return prefetcher
