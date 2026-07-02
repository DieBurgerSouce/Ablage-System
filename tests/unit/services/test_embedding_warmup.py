# -*- coding: utf-8 -*-
"""Unit-Tests fuer W2.1: Query-Embedding-Modell-Warmup (Cold-Start-Fix).

Testet ``warmup_query_embedding_model`` und ``EmbeddingService.warmup_async``:
- Im Test-Kontext (settings.TESTING) wird das Vorwaermen uebersprungen
  (kein echtes ML-Modell laden -> OOM-Vermeidung im Unit-Lauf).
- Bei deaktiviertem Flag wird ebenfalls uebersprungen.
- Im Nicht-Test-Fall wird der Modell-Load ausgeloest (gemockt).

Feinpoliert und durchdacht - Embedding-Warmup Tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import embedding_service as es_mod
from app.services.embedding_service import (
    EmbeddingService,
    warmup_query_embedding_model,
)

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_warmup_skipped_when_testing(monkeypatch):
    """settings.TESTING=True -> Warmup uebersprungen, kein Service angefasst."""
    monkeypatch.setattr(es_mod.settings, "TESTING", True, raising=False)
    monkeypatch.setattr(es_mod.settings, "EMBEDDING_WARMUP_ENABLED", True, raising=False)

    with patch.object(es_mod, "get_embedding_service") as mock_get:
        result = await warmup_query_embedding_model()

    assert result is False
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_warmup_skipped_when_disabled(monkeypatch):
    """EMBEDDING_WARMUP_ENABLED=False -> Warmup uebersprungen."""
    monkeypatch.setattr(es_mod.settings, "TESTING", False, raising=False)
    monkeypatch.setattr(es_mod.settings, "EMBEDDING_WARMUP_ENABLED", False, raising=False)

    with patch.object(es_mod, "get_embedding_service") as mock_get:
        result = await warmup_query_embedding_model()

    assert result is False
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_warmup_loads_model_when_enabled(monkeypatch):
    """Nicht-Test + aktiviert -> Modell-Warmup wird ausgeloest (gemockt)."""
    monkeypatch.setattr(es_mod.settings, "TESTING", False, raising=False)
    monkeypatch.setattr(es_mod.settings, "EMBEDDING_WARMUP_ENABLED", True, raising=False)

    fake_service = MagicMock()
    fake_service.warmup_async = AsyncMock()

    with patch.object(es_mod, "get_embedding_service", return_value=fake_service):
        result = await warmup_query_embedding_model()

    assert result is True
    fake_service.warmup_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_warmup_failure_is_isolated(monkeypatch):
    """Fehler beim Vorwaermen wird geschluckt (Startup nicht gefaehrden)."""
    monkeypatch.setattr(es_mod.settings, "TESTING", False, raising=False)
    monkeypatch.setattr(es_mod.settings, "EMBEDDING_WARMUP_ENABLED", True, raising=False)

    fake_service = MagicMock()
    fake_service.warmup_async = AsyncMock(side_effect=RuntimeError("modell kaputt"))

    with patch.object(es_mod, "get_embedding_service", return_value=fake_service):
        result = await warmup_query_embedding_model()

    assert result is False


@pytest.mark.asyncio
async def test_warmup_async_ensures_model_and_encodes():
    """warmup_async() laedt das Modell und fuehrt genau einen Encode aus."""
    svc = EmbeddingService()  # Singleton
    fake_model = MagicMock()
    original_model = svc._model
    try:
        with patch.object(svc, "_ensure_model_loaded") as mock_ensure:
            svc._model = fake_model
            await svc.warmup_async()
        mock_ensure.assert_called_once()
        fake_model.encode.assert_called_once()
    finally:
        # Singleton-Zustand nicht fuer andere Tests verunreinigen
        svc._model = original_model
