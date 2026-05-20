# -*- coding: utf-8 -*-
"""
Unit Tests für Batch Prefetcher Service.

Testet:
- Asynchrones Prefetching
- Queue-Management
- Preprocessing-Pipeline
- Adaptive Queue-Sizing
- Error Handling

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class TestBatchPrefetcherInit:
    """Tests für BatchPrefetcher Initialisierung."""

    def test_init_default_settings(self):
        """Test Initialisierung mit Default-Einstellungen."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher()

        assert prefetcher._max_queue_size >= 2
        assert prefetcher._worker_count == 4
        assert prefetcher._enable_preprocessing is True
        assert prefetcher._prefetch_running is False

    def test_init_custom_settings(self):
        """Test Initialisierung mit benutzerdefinierten Einstellungen."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher(
            max_queue_size=20,
            worker_count=8,
            enable_preprocessing=False
        )

        assert prefetcher._max_queue_size == 20
        assert prefetcher._worker_count == 8
        assert prefetcher._enable_preprocessing is False

    def test_init_with_custom_preprocess_fn(self):
        """Test Initialisierung mit benutzerdefinierter Preprocessing-Funktion."""
        from app.services.batch_prefetcher import BatchPrefetcher

        def custom_preprocess(content: bytes, path: str) -> Dict[str, Any]:
            return {"custom": True, "size": len(content)}

        prefetcher = BatchPrefetcher(preprocess_fn=custom_preprocess)

        assert prefetcher._preprocess_fn is not None


class TestAdaptiveQueueSize:
    """Tests für adaptive Queue-Größen-Berechnung."""

    def test_adaptive_queue_size_respects_limits(self):
        """Test dass adaptive Queue-Größe innerhalb der Limits bleibt."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher()

        assert prefetcher._max_queue_size >= BatchPrefetcher.MIN_QUEUE_SIZE
        assert prefetcher._max_queue_size <= BatchPrefetcher.MAX_QUEUE_SIZE_LIMIT

    @patch("psutil.virtual_memory")
    def test_adaptive_queue_size_with_low_memory(self, mock_memory):
        """Test adaptive Queue-Größe bei wenig RAM."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Simuliere 500MB verfügbares RAM
        mock_memory.return_value = Mock(available=500 * 1024 * 1024)

        prefetcher = BatchPrefetcher()

        # Mit 500MB und 25% Budget = 125MB, bei 10MB pro Doc = 12 Docs
        # Aber mindestens MIN_QUEUE_SIZE
        assert prefetcher._max_queue_size >= BatchPrefetcher.MIN_QUEUE_SIZE

    @patch("psutil.virtual_memory")
    def test_adaptive_queue_size_with_high_memory(self, mock_memory):
        """Test adaptive Queue-Größe bei viel RAM."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Simuliere 32GB verfügbares RAM
        mock_memory.return_value = Mock(available=32 * 1024**3)

        prefetcher = BatchPrefetcher()

        # Sollte durch MAX_QUEUE_SIZE_LIMIT begrenzt sein
        assert prefetcher._max_queue_size <= BatchPrefetcher.MAX_QUEUE_SIZE_LIMIT


class TestPrefetchedDocument:
    """Tests für PrefetchedDocument Dataclass."""

    def test_prefetched_document_creation(self):
        """Test Erstellung eines PrefetchedDocument."""
        from app.services.batch_prefetcher import PrefetchedDocument

        doc = PrefetchedDocument(
            file_path="/test/file.pdf",
            file_name="file.pdf",
            file_size_bytes=1024 * 1024,  # 1MB
            content=b"test content",
            is_preprocessed=True,
            preprocess_result={"type": "pdf"},
        )

        assert doc.file_path == "/test/file.pdf"
        assert doc.file_name == "file.pdf"
        assert doc.file_size_mb == 1.0
        assert doc.is_preprocessed is True
        assert doc.error is None

    def test_prefetched_document_with_error(self):
        """Test PrefetchedDocument mit Fehler."""
        from app.services.batch_prefetcher import PrefetchedDocument

        doc = PrefetchedDocument(
            file_path="/missing/file.pdf",
            file_name="file.pdf",
            file_size_bytes=0,
            content=b"",
            error="Datei nicht gefunden",
        )

        assert doc.error is not None
        assert "nicht gefunden" in doc.error


class TestPrefetchStats:
    """Tests für PrefetchStats."""

    def test_prefetch_stats_initial(self):
        """Test initiale PrefetchStats."""
        from app.services.batch_prefetcher import PrefetchStats

        stats = PrefetchStats()

        assert stats.total_prefetched == 0
        assert stats.total_errors == 0
        assert stats.cache_hits == 0

    def test_prefetch_stats_to_dict(self):
        """Test PrefetchStats Serialisierung."""
        from app.services.batch_prefetcher import PrefetchStats

        stats = PrefetchStats(
            total_prefetched=100,
            total_preprocessed=90,
            total_errors=5,
            total_bytes_loaded=10 * 1024 * 1024,
            cache_hits=80,
            cache_misses=20,
            avg_prefetch_time_ms=15.5,
            queue_high_water_mark=8,
        )

        result = stats.to_dict()

        assert result["total_prefetched"] == 100
        assert result["total_mb_loaded"] == 10.0
        assert result["hit_rate"] == 0.8  # 80 / (80 + 20)


class TestPrefetchSingle:
    """Tests für Einzeldatei-Prefetching."""

    def test_prefetch_single_text_file(self):
        """Test Prefetching einer Textdatei."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher(enable_preprocessing=False)

        # Erstelle temporäre Datei
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("Test content for prefetching")
            temp_path = f.name

        try:
            doc = prefetcher._prefetch_single(temp_path)

            assert doc.file_path == temp_path
            assert doc.file_size_bytes > 0
            assert b"Test content" in doc.content
            assert doc.error is None
        finally:
            Path(temp_path).unlink()

    def test_prefetch_single_missing_file(self):
        """Test Prefetching einer nicht existierenden Datei."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher()
        doc = prefetcher._prefetch_single("/nonexistent/file.pdf")

        assert doc.error is not None
        assert "nicht gefunden" in doc.error
        assert doc.file_size_bytes == 0


class TestPreprocessing:
    """Tests für Preprocessing-Funktionen."""

    def test_preprocess_pdf_valid(self):
        """Test PDF-Preprocessing mit gültigem Header."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher()

        # Simuliere minimalen PDF-Header
        pdf_content = b"%PDF-1.4\n/Type /Page\n/Type /Page\n"

        result = prefetcher._preprocess_pdf(pdf_content, "test.pdf")

        assert result is not None
        assert result["type"] == "pdf"
        assert result["valid"] is True
        assert result["estimated_pages"] >= 1

    def test_preprocess_pdf_invalid(self):
        """Test PDF-Preprocessing mit ungültigem Header."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher()

        # Keine PDF-Signatur
        invalid_content = b"This is not a PDF"

        result = prefetcher._preprocess_pdf(invalid_content, "test.pdf")

        assert result is not None
        assert result["valid"] is False

    def test_preprocess_image_png(self):
        """Test Bild-Preprocessing mit PNG."""
        from app.services.batch_prefetcher import BatchPrefetcher

        try:
            from PIL import Image
            import io

            prefetcher = BatchPrefetcher()

            # Erstelle minimales PNG
            img = Image.new("RGB", (100, 100), color="red")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            png_content = buffer.getvalue()

            result = prefetcher._preprocess_image(png_content, "test.png")

            assert result is not None
            assert result["type"] == "image"
            assert result["format"] == "PNG"
            assert result["width"] == 100
            assert result["height"] == 100

        except ImportError:
            pytest.skip("PIL not available")

    def test_custom_preprocessing_function(self):
        """Test benutzerdefinierte Preprocessing-Funktion."""
        from app.services.batch_prefetcher import BatchPrefetcher

        custom_results = []

        def custom_preprocess(content: bytes, path: str) -> Dict[str, Any]:
            result = {"custom": True, "path": path, "size": len(content)}
            custom_results.append(result)
            return result

        prefetcher = BatchPrefetcher(preprocess_fn=custom_preprocess)

        # Erstelle temporäre Datei
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("Custom preprocess test")
            temp_path = f.name

        try:
            doc = prefetcher._prefetch_single(temp_path)

            assert doc.is_preprocessed is True
            assert doc.preprocess_result is not None
            assert doc.preprocess_result["custom"] is True
        finally:
            Path(temp_path).unlink()


class TestAsyncPrefetching:
    """Tests für asynchrones Prefetching."""

    @pytest.mark.asyncio
    async def test_start_prefetching(self):
        """Test Starten des Prefetching."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Erstelle temporäre Dateien
        temp_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Content {i}")
                temp_files.append(f.name)

        try:
            prefetcher = BatchPrefetcher(max_queue_size=10)
            await prefetcher.start_prefetching(temp_files)

            # Warte kurz auf Prefetching
            await asyncio.sleep(0.2)

            status = prefetcher.get_queue_status()
            assert status["prefetch_running"] or status["prefetch_complete"]

            prefetcher.cleanup()
        finally:
            for path in temp_files:
                Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_documents_generator(self):
        """Test async Generator für Dokumente."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Erstelle temporäre Dateien
        temp_files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Document content {i}")
                temp_files.append(f.name)

        try:
            prefetcher = BatchPrefetcher(
                max_queue_size=10,
                enable_preprocessing=False
            )
            await prefetcher.start_prefetching(temp_files)

            docs_received = []
            async for doc in prefetcher.get_documents():
                docs_received.append(doc)

            assert len(docs_received) == 5
            assert all(doc.error is None for doc in docs_received)

            prefetcher.cleanup()
        finally:
            for path in temp_files:
                Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_prefetch_stats_tracking(self):
        """Test Statistik-Tracking während Prefetching."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Erstelle temporäre Dateien
        temp_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Stats test {i}" * 100)
                temp_files.append(f.name)

        try:
            prefetcher = BatchPrefetcher(
                max_queue_size=10,
                enable_preprocessing=False
            )
            await prefetcher.start_prefetching(temp_files)

            # Konsumiere alle Dokumente
            docs = []
            async for doc in prefetcher.get_documents():
                docs.append(doc)

            stats = prefetcher.get_stats()

            assert stats["total_prefetched"] == 3
            assert stats["total_bytes_loaded"] > 0
            assert stats["total_errors"] == 0

            prefetcher.cleanup()
        finally:
            for path in temp_files:
                Path(path).unlink(missing_ok=True)


class TestQueueManagement:
    """Tests für Queue-Management."""

    @pytest.mark.asyncio
    async def test_queue_not_exceed_max_size(self):
        """Test dass Queue nicht über max_queue_size wächst."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Erstelle mehr Dateien als Queue-Größe
        temp_files = []
        for i in range(20):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Queue test {i}")
                temp_files.append(f.name)

        try:
            prefetcher = BatchPrefetcher(
                max_queue_size=5,  # Kleine Queue
                enable_preprocessing=False
            )
            await prefetcher.start_prefetching(temp_files)

            # Warte kurz
            await asyncio.sleep(0.3)

            # Queue sollte nie größer als max_queue_size sein
            status = prefetcher.get_queue_status()
            assert status["queue_length"] <= 5

            # High Water Mark sollte <= max_queue_size sein
            stats = prefetcher.get_stats()
            assert stats["queue_high_water_mark"] <= 5

            prefetcher.clear()
        finally:
            for path in temp_files:
                Path(path).unlink(missing_ok=True)

    def test_clear_queue(self):
        """Test Queue-Clearing."""
        from app.services.batch_prefetcher import BatchPrefetcher

        prefetcher = BatchPrefetcher()
        prefetcher.clear()

        status = prefetcher.get_queue_status()
        assert status["queue_length"] == 0
        assert status["prefetch_running"] is False


class TestConvenienceFunctions:
    """Tests für Convenience-Funktionen."""

    def test_get_batch_prefetcher_singleton(self):
        """Test Singleton-Pattern für BatchPrefetcher."""
        from app.services.batch_prefetcher import get_batch_prefetcher

        # Reset global
        import app.services.batch_prefetcher as module
        module._batch_prefetcher = None

        prefetcher1 = get_batch_prefetcher()
        prefetcher2 = get_batch_prefetcher()

        assert prefetcher1 is prefetcher2

        # Cleanup
        prefetcher1.cleanup()
        module._batch_prefetcher = None

    @pytest.mark.asyncio
    async def test_prefetch_documents_convenience(self):
        """Test prefetch_documents Convenience-Funktion."""
        from app.services.batch_prefetcher import prefetch_documents

        # Reset global
        import app.services.batch_prefetcher as module
        module._batch_prefetcher = None

        # Erstelle temporäre Dateien
        temp_files = []
        for i in range(2):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Convenience test {i}")
                temp_files.append(f.name)

        try:
            prefetcher = await prefetch_documents(temp_files)

            assert prefetcher is not None
            assert prefetcher._prefetch_running or prefetcher._prefetch_complete.is_set()

            prefetcher.cleanup()
            module._batch_prefetcher = None
        finally:
            for path in temp_files:
                Path(path).unlink(missing_ok=True)


class TestErrorHandling:
    """Tests für Error Handling."""

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_files(self):
        """Test Prefetching mit Mix aus gültigen und ungültigen Dateien."""
        from app.services.batch_prefetcher import BatchPrefetcher

        # Erstelle nur gültige Dateien
        temp_files = []
        for i in range(2):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Valid {i}")
                temp_files.append(f.name)

        # Füge ungültige Pfade hinzu
        invalid_files = ["/nonexistent/file1.txt", "/nonexistent/file2.txt"]
        all_files = temp_files + invalid_files

        try:
            prefetcher = BatchPrefetcher(
                max_queue_size=10,
                enable_preprocessing=False
            )
            await prefetcher.start_prefetching(all_files)

            docs = []
            async for doc in prefetcher.get_documents():
                docs.append(doc)

            # Alle Dateien sollten verarbeitet worden sein
            assert len(docs) == 4

            # 2 gültige, 2 mit Fehler
            valid_docs = [d for d in docs if d.error is None]
            error_docs = [d for d in docs if d.error is not None]

            assert len(valid_docs) == 2
            assert len(error_docs) == 2

            prefetcher.cleanup()
        finally:
            for path in temp_files:
                Path(path).unlink(missing_ok=True)
