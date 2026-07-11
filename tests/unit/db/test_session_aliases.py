"""Regressionswache: Worker-Session-Aliase muessen Bypass-Semantik haben.

Die Aliase ``async_session_factory``/``async_session_maker`` existieren laut
Kommentar in session.py ausschliesslich fuer Celery-Tasks ("backwards
compatibility with Celery tasks"); kein einziger app/api-Pfad nutzt sie
(Grep-Inventar 2026-07-11, docs/reviews/2026-07_rls_274_design.md §4).

Nach den Migrationen 272-274 liefern kontextlose Sessions auf den
RLS-Kerntabellen 0 Zeilen (Reads) bzw. Ablehnung (documents-INSERT) — jeder
Task, der die Aliase kontextlos nutzte, war still kaputt (Muster
active_learning_tasks). Die Aliase zeigen deshalb auf
``get_worker_session_context`` (F-16). Die API-Dependency ``get_async_session``
bleibt bewusst OHNE Bypass (Warnung im Docstring von
get_worker_session_context).
"""

import pytest

pytestmark = [pytest.mark.unit]


def test_worker_aliase_zeigen_auf_worker_kontext():
    from app.db.session import (
        async_session_factory,
        async_session_maker,
        get_worker_session_context,
    )

    assert async_session_factory is get_worker_session_context
    assert async_session_maker is get_worker_session_context


def test_api_dependency_bleibt_ohne_bypass():
    """get_async_session (FastAPI-Dependency) darf NICHT auf den Bypass zeigen."""
    from app.db.session import get_async_session, get_worker_session_context

    assert get_async_session is not get_worker_session_context
