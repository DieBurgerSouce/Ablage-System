# -*- coding: utf-8 -*-
"""Regressionstest F-P2-001 (Perception-Audit 2026-07-12).

Scope-Entscheid „firmenweit teilen": Das LESEN von Dokumenten (Liste + Detail)
ist company-scoped — jedes Firmenmitglied sieht/oeffnet die Firmendokumente,
nicht nur eigene Uploads. Ohne company_id bleibt es (Fallback) owner-scoped.
Schreiboperationen (update/delete) bleiben owner-geschuetzt.

DB-frei: eine Fake-Session faengt die vom Service gebaute SELECT-Query ab und
wir pruefen deren WHERE-Klausel.
"""
import asyncio
import inspect
from uuid import uuid4

from app.services.document_service import DocumentService


class _FakeResult:
    def __init__(self, scalar_value=0):
        self._scalar = scalar_value

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return None

    class _Scalars:
        @staticmethod
        def all():
            return []

    def scalars(self):
        return self._Scalars()


class _CapturingSession:
    """Faengt alle executes ab und kompiliert die Statements zu SQL-Strings."""

    def __init__(self):
        self.sqls: list[str] = []

    async def execute(self, statement, *args, **kwargs):
        try:
            self.sqls.append(str(statement.compile(compile_kwargs={"literal_binds": False})))
        except Exception:
            self.sqls.append(str(statement))
        # count-Query braucht einen Skalar, List-Query eine leere Menge
        return _FakeResult(scalar_value=0)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _where_clauses(sqls: list[str]) -> str:
    """Nur die WHERE-Teile zusammenfassen (owner_id kommt auch als SELECT-Spalte
    vor — die Zugriffsbedingung steht aber im WHERE)."""
    parts = []
    for raw in sqls:
        s = " ".join(raw.split())  # Newlines/Mehrfach-Whitespace normalisieren
        idx = s.upper().find(" WHERE ")
        if idx != -1:
            parts.append(s[idx + 7:])
    return " ".join(parts)


def test_list_documents_company_scoped():
    """Mit company_id filtert list_documents auf company_id (nicht owner_id)."""
    svc = DocumentService()
    session = _CapturingSession()
    _run(svc.list_documents(session, user_id=uuid4(), company_id=uuid4()))
    where = _where_clauses(session.sqls)
    assert "company_id" in where, "Liste muss company_id-scoped sein (F-P2-001)."
    assert "owner_id" not in where, (
        "Firmenweite Liste darf NICHT zusaetzlich auf owner_id einschraenken — "
        "sonst sieht der Prokurist die Belege der Kollegen nicht (F-P2-001)."
    )


def test_list_documents_owner_fallback_without_company():
    """Ohne company_id bleibt list_documents owner-scoped (Sicherheits-Fallback)."""
    svc = DocumentService()
    session = _CapturingSession()
    _run(svc.list_documents(session, user_id=uuid4(), company_id=None))
    where = _where_clauses(session.sqls)
    assert "owner_id" in where, "Ohne company_id muss owner-scoped bleiben."


def test_get_document_company_scoped():
    """Mit company_id oeffnet get_document firmenweit (company_id-Praedikat)."""
    svc = DocumentService()
    session = _CapturingSession()
    _run(svc.get_document(session, document_id=uuid4(), user_id=uuid4(), company_id=uuid4()))
    where = _where_clauses(session.sqls)
    assert "company_id" in where and "owner_id" not in where, (
        "get_document muss mit company_id firmenweit lesen (F-P2-001)."
    )


def test_service_methods_accept_company_id():
    """get_document / list_documents muessen den company_id-Parameter fuehren."""
    svc = DocumentService()
    for name in ("get_document", "list_documents"):
        sig = inspect.signature(getattr(svc, name))
        assert "company_id" in sig.parameters, (
            f"{name} muss company_id akzeptieren (F-P2-001 firmenweite Sichtbarkeit)."
        )
