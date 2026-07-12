# -*- coding: utf-8 -*-
"""Regressionstest F-P2-005 (Perception-Audit 2026-07-12).

Die Umlaut-/Kompositum-Expansion wurde in der Volltextsuche via
plainto_tsquery(:query) mit UND verknuepft (z. B. „Müller mueller" ->
'mull' & 'muell') -> ein Dokument mit nur „Müller" wurde NICHT gefunden.
Fix: _search_fts baut die tsquery als OR ueber die Einzelterme
(Gesamtquery als AND-Gruppe + jedes Wort als OR-Alternative).

DB-frei: eine Fake-Session faengt die an execute() uebergebenen Parameter ab
und wir pruefen die `fts_terms`-Liste.
"""
import asyncio

from app.services.search_service import SearchService


class _FakeResult:
    def scalar(self):
        return 0

    class _Scalars:
        @staticmethod
        def all():
            return []

    def scalars(self):
        return self._Scalars()

    @staticmethod
    def __iter__():
        return iter([])

    def fetchall(self):
        return []


class _CapturingSession:
    def __init__(self):
        self.params: list[dict] = []

    async def execute(self, statement, params=None, *args, **kwargs):
        if isinstance(params, dict):
            self.params.append(params)
        return _FakeResult()


def _run(coro):
    # Frischer Loop pro Aufruf: robust gegen von pytest-asyncio geschlossene Loops
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _fts_terms_for(query: str):
    svc = SearchService()
    session = _CapturingSession()
    try:
        _run(
            svc._search_fts(
                session,
                query,
                user_id=None,
                filters=None,
                page=1,
                per_page=10,
                highlight=False,
                company_id=None,
            )
        )
    except Exception:
        # Wir interessieren uns nur fuer die an execute() gebauten Parameter,
        # nicht fuer das (Fake-)Ergebnis-Handling.
        pass
    for p in session.params:
        if "fts_terms" in p:
            return p["fts_terms"]
    return None


def test_fts_terms_enthalten_gesamtquery_und_einzelwoerter():
    terms = _fts_terms_for("Müller mueller")
    assert terms is not None, "_search_fts muss fts_terms an execute() uebergeben."
    # Gesamtquery als AND-Gruppe + jedes Einzelwort als OR-Alternative
    assert "Müller mueller" in terms
    assert "Müller" in terms
    assert "mueller" in terms


def test_fts_terms_dedupliziert_einzelwort():
    # Einwort-Query: Gesamtquery == Einzelwort -> nur einmal enthalten
    terms = _fts_terms_for("Müller")
    assert terms is not None
    assert terms.count("Müller") == 1


def test_fts_terms_keine_leeren():
    terms = _fts_terms_for("  Rechnung   Müller  ")
    assert terms is not None
    assert all(t and t.strip() for t in terms)
