"""Chaos Engineering Tests - GPU-Fehlerszenarien.

Simuliert GPU-Ausfaelle, OOM-Errors, CUDA-Fehler und testet
automatisches CPU-Fallback-Verhalten.
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# Mock-Exceptions fuer fehlende Packages
class CUDAOutOfMemoryError(RuntimeError):
    """Mock CUDA OOM Error."""
    pass


class CUDAError(RuntimeError):
    """Mock CUDA Error."""
    pass


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_gpu_oom_simulation(mock_gpu):
    """Testet Behandlung von GPU Out-of-Memory Fehlern.

    Szenario: GPU-Speicher ist erschoepft waehrend OCR-Verarbeitung.
    Erwartung: OOM wird erkannt und automatisch auf CPU umgeschaltet.
    """
    # Arrange: Mock torch.cuda (sys.modules-Patch fuer fehlende torch-Installation)
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    with patch.dict("sys.modules", {"torch": mock_torch, "torch.cuda": mock_torch.cuda}):
        mock_model = MagicMock()

        # Erst GPU-OOM, dann CPU-Erfolg
        call_count = {"count": 0}

        def process_with_oom(*args, **kwargs):
            """Simuliert GPU-OOM beim ersten Aufruf."""
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise CUDAOutOfMemoryError("CUDA out of memory")
            # CPU-Fallback erfolgreich
            return {"text": "Extrahierter Text", "backend": "cpu"}

        mock_model.process = MagicMock(side_effect=process_with_oom)

        # Act: Simuliere OCR mit OOM-Handling
        async def process_with_fallback(model, image_path: str) -> Dict[str, Any]:
            """Verarbeitet Bild mit GPU-OOM-Fallback."""
            try:
                result = model.process(image_path, device="cuda")
                return result
            except CUDAOutOfMemoryError as e:
                print(f"GPU-OOM erkannt: {e}")
                print("Wechsle zu CPU-Verarbeitung...")
                # CPU-Fallback
                result = model.process(image_path, device="cpu")
                return result

        result = await process_with_fallback(mock_model, "test.pdf")

        # Assert: CPU-Fallback wurde verwendet
        assert result["backend"] == "cpu", "Sollte auf CPU gefallen sein"
        assert call_count["count"] == 2, "Sollte GPU dann CPU versuchen"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_cuda_device_unavailable(mock_gpu):
    """Testet Behandlung wenn CUDA-Device nicht verfuegbar ist.

    Szenario: torch.cuda.is_available() gibt False zurueck.
    Erwartung: System verwendet automatisch CPU-Backend.
    """
    # Arrange: CUDA nicht verfuegbar (sys.modules-Patch fuer fehlende torch-Installation)
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False
    with patch.dict("sys.modules", {"torch": mock_torch, "torch.cuda": mock_torch.cuda}):

        # Act: Simuliere Device-Auswahl
        async def select_device() -> str:
            """Waehlt GPU oder CPU basierend auf Verfuegbarkeit."""
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
            except (ImportError, Exception) as e:
                print(f"CUDA-Pruefung fehlgeschlagen: {e}")

            print("GPU nicht verfuegbar, verwende CPU")
            return "cpu"

        device = await select_device()

        # Assert: CPU wurde gewaehlt
        assert device == "cpu", "Sollte CPU waehlen wenn GPU nicht verfuegbar"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_model_load_failure():
    """Testet Behandlung von Model-Ladefehlern.

    Szenario: OCR-Model kann nicht geladen werden (corrupt, missing).
    Erwartung: Fehler wird erkannt, Alternative wird geladen.
    """
    # Arrange: Mock Model-Loader
    mock_loader = MagicMock()

    call_count = {"count": 0}

    def load_with_failure(model_name: str):
        """Simuliert Model-Load-Fehler."""
        call_count["count"] += 1
        if model_name == "deepseek-janus-pro":
            raise RuntimeError("Fehler beim Laden des Models: Datei beschaedigt")
        # Fallback-Model
        mock_model = MagicMock()
        mock_model.name = model_name
        return mock_model

    mock_loader.load_model = MagicMock(side_effect=load_with_failure)

    # Act: Simuliere Model-Auswahl mit Fallback
    async def load_ocr_model(loader, preferred: str, fallback: str) -> Any:
        """Laedt OCR-Model mit Fallback."""
        try:
            model = loader.load_model(preferred)
            print(f"Model geladen: {preferred}")
            return model
        except RuntimeError as e:
            print(f"Fehler beim Laden von {preferred}: {e}")
            print(f"Lade Fallback-Model: {fallback}")
            model = loader.load_model(fallback)
            return model

    model = await load_ocr_model(
        mock_loader,
        preferred="deepseek-janus-pro",
        fallback="surya-ocr"
    )

    # Assert: Fallback-Model wurde geladen
    assert model.name == "surya-ocr", "Sollte Fallback-Model laden"
    assert call_count["count"] == 2, "Sollte beide Models versuchen"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_gpu_memory_threshold_exceeded(mock_gpu):
    """Testet Behandlung wenn GPU-Speicher-Schwellwert ueberschritten wird.

    Szenario: VRAM-Nutzung >85% (13.6GB von 16GB).
    Erwartung: Batch-Size wird reduziert oder CPU-Fallback aktiviert.
    """
    # Arrange: GPU-Speicher bei 90%
    mock_gpu.memory_allocated.return_value = int(16 * 1024**3 * 0.9)  # 14.4GB

    # Act: Simuliere Speicher-Pruefung und Anpassung
    async def adjust_batch_size(gpu, current_batch: int = 32) -> int:
        """Passt Batch-Size basierend auf GPU-Speicher an."""
        allocated = gpu.memory_allocated()
        total = gpu.memory_total()
        usage_percent = (allocated / total) * 100

        print(f"GPU-Speicher: {usage_percent:.1f}% belegt")

        if usage_percent > 85:
            print("Schwellwert ueberschritten, reduziere Batch-Size")
            # Halbiere Batch-Size
            new_batch = max(1, current_batch // 2)
            return new_batch

        return current_batch

    new_batch_size = await adjust_batch_size(mock_gpu, current_batch=32)

    # Assert: Batch-Size wurde reduziert
    assert new_batch_size == 16, "Batch-Size sollte halbiert werden"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_graceful_cpu_fallback_on_oom():
    """Testet vollstaendiges Fallback-Szenario von GPU zu CPU.

    Szenario: GPU-Verarbeitung schlaegt mit OOM fehl, CPU uebernimmt.
    Erwartung: Nahtloser Wechsel ohne Datenverlust.
    """
    # Arrange: Mock OCR-Service
    class MockOCRService:
        """Mock OCR-Service mit GPU/CPU-Unterstuetzung."""

        def __init__(self):
            self.attempts: List[str] = []

        async def process_document(
            self,
            doc_id: str,
            prefer_gpu: bool = True
        ) -> Dict[str, Any]:
            """Verarbeitet Dokument mit GPU-Fallback."""
            if prefer_gpu:
                self.attempts.append("gpu")
                try:
                    return await self._process_gpu(doc_id)
                except CUDAOutOfMemoryError:
                    print("GPU-OOM, wechsle zu CPU...")
                    self.attempts.append("cpu-fallback")
                    return await self._process_cpu(doc_id)
            else:
                self.attempts.append("cpu")
                return await self._process_cpu(doc_id)

        async def _process_gpu(self, doc_id: str) -> Dict[str, Any]:
            """GPU-Verarbeitung (wirft OOM)."""
            raise CUDAOutOfMemoryError("CUDA out of memory")

        async def _process_cpu(self, doc_id: str) -> Dict[str, Any]:
            """CPU-Verarbeitung (erfolgreich)."""
            return {
                "doc_id": doc_id,
                "text": "Rechnung Nr. 12345",
                "backend": "cpu",
                "success": True
            }

    service = MockOCRService()

    # Act: Verarbeite Dokument
    result = await service.process_document("doc-123", prefer_gpu=True)

    # Assert: CPU-Fallback war erfolgreich
    assert result["success"] is True, "Verarbeitung sollte erfolgreich sein"
    assert result["backend"] == "cpu", "Sollte CPU-Backend verwenden"
    assert service.attempts == ["gpu", "cpu-fallback"], "Sollte GPU dann CPU versuchen"
    assert "Rechnung" in result["text"], "Text sollte extrahiert werden"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_concurrent_gpu_requests_throttling():
    """Testet Drosselung von gleichzeitigen GPU-Anfragen.

    Szenario: Zu viele parallele GPU-Requests fuehren zu Resource-Contention.
    Erwartung: Request-Queue limitiert parallele GPU-Nutzung.
    """
    # Arrange: Mock GPU-Ressourcen-Manager
    class GPUResourceManager:
        """Verwaltet GPU-Ressourcen mit Semaphore."""

        def __init__(self, max_concurrent: int = 2):
            self.semaphore = asyncio.Semaphore(max_concurrent)
            self.active_tasks = 0
            self.max_active = 0

        async def process_with_limit(self, task_id: str) -> Dict[str, Any]:
            """Verarbeitet Task mit Concurrency-Limit."""
            async with self.semaphore:
                self.active_tasks += 1
                self.max_active = max(self.max_active, self.active_tasks)

                # Simuliere GPU-Arbeit
                await asyncio.sleep(0.1)

                self.active_tasks -= 1
                return {"task_id": task_id, "status": "completed"}

    manager = GPUResourceManager(max_concurrent=2)

    # Act: Starte 10 parallele Tasks
    tasks = [
        manager.process_with_limit(f"task-{i}")
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)

    # Assert: Maximal 2 gleichzeitige Tasks
    assert len(results) == 10, "Alle Tasks sollten abgeschlossen sein"
    assert manager.max_active <= 2, "Maximal 2 parallele GPU-Tasks erlaubt"
    assert all(r["status"] == "completed" for r in results), "Alle Tasks erfolgreich"
