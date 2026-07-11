"""Regressionstests: pgvector-Casts duerfen Bind-Params nicht verschlucken.

Gefunden durch den Go-Live-Such-Benchmark (AP-5, 2026-07-11): SQLAlchemy
parst ``:embedding::vector`` NICHT als Bind-Parameter (der Lookahead des
Bind-Tokenizers scheitert am direkt folgenden ``::``) -> asyncpg bekommt
das rohe ``:embedding`` -> PostgresSyntaxError. Betroffen waren die
whole-doc-Suche (/api/v1/search/semantic), find_similar_documents,
embed_document UND der naechtliche 04:15-Batch-Embed-Beat.

Korrekt ist ``CAST(:embedding AS vector)``.
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.unit]

# Muster: benannter Bind-Param direkt gefolgt von ::-Cast (kaputt unter text())
_BROKEN_CAST = re.compile(r":\w+::")

_APP_ROOT = Path(__file__).resolve().parents[3] / "app"
_AFFECTED_FILES = [
    _APP_ROOT / "services" / "semantic_search_service.py",
    _APP_ROOT / "workers" / "tasks" / "semantic_search_tasks.py",
]


@pytest.mark.parametrize("path", _AFFECTED_FILES, ids=lambda p: p.name)
def test_kein_unbound_param_cast_muster_mehr(path: Path):
    """Quelltext-Wache: ':param::' darf in den betroffenen Dateien nie zurueckkehren."""
    source = path.read_text(encoding="utf-8")
    hits = [
        f"Zeile {i + 1}: {line.strip()}"
        for i, line in enumerate(source.splitlines())
        if _BROKEN_CAST.search(line)
    ]
    assert hits == [], (
        "SQLAlchemy-Falle ':param::cast' gefunden (Bind wird nicht erkannt, "
        "asyncpg-SyntaxError). CAST(:param AS vector) verwenden:\n" + "\n".join(hits)
    )


@pytest.mark.asyncio
async def test_semantic_search_bindet_das_embedding(monkeypatch):
    """Behavioral: der an die Session gereichte TextClause kennt 'embedding'."""
    from app.services.semantic_search_service import SemanticSearchService

    service = SemanticSearchService()

    embedding_service = MagicMock()
    embedding_service.generate_query_embedding_cached = AsyncMock(
        return_value=[0.1, 0.2, 0.3]
    )
    monkeypatch.setattr(
        service, "_get_embedding_service", MagicMock(return_value=embedding_service)
    )

    execute_result = MagicMock()
    execute_result.fetchall = MagicMock(return_value=[])
    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result)

    await service.semantic_search(
        query="testquery",
        session=session,
        user_id=uuid4(),
        rerank=False,
    )

    clause, params = session.execute.await_args.args
    assert "embedding" in params
    # TextClause muss den Param als Bind erkannt haben, sonst geht das rohe
    # ':embedding' an asyncpg (genau der Live-Fehler des Benchmarks).
    assert "embedding" in clause._bindparams
