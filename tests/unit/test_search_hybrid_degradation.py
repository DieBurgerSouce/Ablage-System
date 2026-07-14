# -*- coding: utf-8 -*-
"""Regressionstest F-P2-004 (Perception-Audit 2026-07-12).

Ein GPU-Fehler in der semantischen Suche (z. B. Dtype-Mismatch fp16/fp32
nach ressourcen-knappem Neustart: "mat1 and mat2 must have the same dtype")
oder im Reranker riss die gesamte Hybrid-Suche auf HTTP 500. Die Suche muss
stattdessen auf die deterministische FTS (reines Postgres) degradieren.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.db.schemas import DocumentType, ProcessingStatus, SearchResultItem
from app.services.search_service import SearchService


def _run(coro):
    # Frischer Loop pro Aufruf statt pytest.mark.asyncio: der session-scoped
    # event_loop der Suite ist gegen Test-Pollution empfindlich (siehe
    # _repair_global_event_loop in tests/conftest.py); diese Tests brauchen
    # keinerlei geteilte Loop-Ressourcen.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _item(name: str) -> SearchResultItem:
    now = datetime.now(timezone.utc)
    return SearchResultItem(
        document_id=uuid.uuid4(),
        filename=f"{name}.pdf",
        original_filename=f"{name}.pdf",
        document_type=DocumentType.INVOICE,
        status=ProcessingStatus.COMPLETED,
        created_at=now,
        updated_at=now,
        file_size=1234,
        score=0.9,
        owner_id=uuid.uuid4(),
    )


def test_semantik_fehler_degradiert_auf_fts_statt_500():
    svc = SearchService()
    fts_items = [_item("eingangsrechnung-buerohaus-mueller")]

    async def fake_fts(db, query, user_id, filters, page, per_page, highlight, company_id=None):
        return fts_items, len(fts_items)

    async def kaputte_semantik(db, query, user_id, filters, page, per_page, threshold, company_id=None):
        raise RuntimeError("mat1 and mat2 must have the same dtype")

    svc._search_fts = fake_fts  # type: ignore[method-assign]
    svc._search_semantic = kaputte_semantik  # type: ignore[method-assign]

    results, total = _run(svc._search_hybrid(
        db=None,
        query="Müller",
        user_id=uuid.uuid4(),
        filters=None,
        page=1,
        per_page=10,
        highlight=False,
        threshold=0.5,
        rerank=False,
        company_id=None,
    ))

    assert total == 1
    assert [r.original_filename for r in results] == [
        "eingangsrechnung-buerohaus-mueller.pdf"
    ], "FTS-Treffer müssen die Semantik-Störung überleben (F-P2-004)"


def test_reranker_fehler_faellt_auf_rrf_sortierung_zurueck():
    svc = SearchService()
    svc._rerank_enabled = True
    fts_items = [_item("doc-a"), _item("doc-b")]

    async def fake_fts(db, query, user_id, filters, page, per_page, highlight, company_id=None):
        return list(fts_items), len(fts_items)

    async def fake_semantik(db, query, user_id, filters, page, per_page, threshold, company_id=None):
        return [], 0

    async def kaputter_reranker(query, candidates, top_k):
        raise RuntimeError("CUDA out of memory")

    svc._search_fts = fake_fts  # type: ignore[method-assign]
    svc._search_semantic = fake_semantik  # type: ignore[method-assign]
    svc._rerank_results = kaputter_reranker  # type: ignore[method-assign]

    results, total = _run(svc._search_hybrid(
        db=None,
        query="Müller",
        user_id=uuid.uuid4(),
        filters=None,
        page=1,
        per_page=10,
        highlight=False,
        threshold=0.5,
        rerank=True,
        company_id=None,
    ))

    assert total == 2
    assert [r.original_filename for r in results] == ["doc-a.pdf", "doc-b.pdf"], (
        "Reranker-Fehler muss auf RRF-Reihenfolge zurückfallen (F-P2-004)"
    )
