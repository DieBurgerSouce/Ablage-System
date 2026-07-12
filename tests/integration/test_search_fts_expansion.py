# -*- coding: utf-8 -*-
"""Regressionstest F-P2-005 (Perception-Audit 2026-07-12) — SQL-Semantik.

Beweist gegen die echte Datenbank (german_text-Konfiguration, läuft im
Backend-Container), dass die OR-verknüpfte tsquery aus build_fts_expansion_
terms() ein Dokument findet, das nur EINE Schreibweise enthält — und dass
die alte AND-Verknüpfung (plainto_tsquery über die Gesamtquery) genau daran
scheiterte.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.search_service import build_fts_expansion_terms

DOKUMENT_TEXT = "Eingangsrechnung Bürohaus Müller GmbH Rechnungsnummer RE-2026-0815"

# Identisch zum COALESCE-Ausdruck in SearchService._search_fts (F-P2-005).
# WICHTIG: CAST(...)-Schreibweise statt ::-Casts — SQLAlchemy-text() parst
# ":param::cast" fehlerhaft als Bind-Param ohne letzten Buchstaben
# (bekannte ":embedding::vector"-Falle).
OR_TSQUERY_MATCH = text("""
    SELECT to_tsvector('german_text', :doc) @@ (
        CAST(COALESCE(
            (SELECT string_agg('(' || CAST(plainto_tsquery('german_text', t) AS text) || ')', ' | ')
             FROM unnest(CAST(:fts_terms AS text[])) AS t
             WHERE CAST(plainto_tsquery('german_text', t) AS text) <> ''),
            CAST(plainto_tsquery('german_text', :query) AS text)
        ) AS tsquery)
    )
""")

ALTE_AND_MATCH = text(
    "SELECT to_tsvector('german_text', :doc) @@ plainto_tsquery('german_text', :query)"
)


async def _query_scalar(sql, params) -> bool:
    # Muster wie tests/integration/test_rls_guc_persistence.py (mark.asyncio,
    # Engine pro Test auf dem Suite-Loop): koexistiert nachweislich mit den
    # asyncgen-Autouse-Fixtures der Suite — ein eigener Loop pro Test tut das
    # mit asyncpg NICHT (Session-Loop-Pollution, "Event loop is closed").
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            result = await session.execute(sql, params)
            return bool(result.scalar())
    finally:
        await engine.dispose()


async def _match(query: str, doc: str = DOKUMENT_TEXT) -> bool:
    return await _query_scalar(
        OR_TSQUERY_MATCH,
        {"doc": doc, "query": query, "fts_terms": build_fts_expansion_terms(query)},
    )


@pytest.mark.asyncio
async def test_expandierte_query_findet_dokument_mit_nur_einer_schreibweise():
    """Kernfall F-P2-005: "Müller mueller" muss ein Dokument mit nur "Müller" finden."""
    assert await _match("Müller mueller") is True, (
        "OR-Expansion greift nicht — Umlaut-Expansion würde wieder "
        "0 Treffer liefern (Regression F-P2-005)"
    )


@pytest.mark.asyncio
async def test_alte_and_verknuepfung_war_der_bug():
    """Dokumentiert den Alt-Zustand: plainto_tsquery('Müller mueller') = AND -> kein Treffer."""
    matched = await _query_scalar(
        ALTE_AND_MATCH, {"doc": DOKUMENT_TEXT, "query": "Müller mueller"}
    )
    assert matched is False, (
        "Wenn AND plötzlich matcht, wurde die german_text-Konfiguration "
        "geändert — Test und Fix F-P2-005 dann neu bewerten"
    )


@pytest.mark.asyncio
async def test_einzelwort_und_praezision_bleiben_erhalten():
    # Einzelwort trifft weiterhin
    assert await _match("Müller") is True
    assert await _match("Bürohaus") is True
    # Mehrwort-Query, deren Wörter beide vorkommen, trifft weiterhin
    assert await _match("Bürohaus Müller") is True
    # Nicht vorhandene Begriffe treffen nicht (kein False-Positive-Regen)
    assert await _match("Frachtbrief") is False


@pytest.mark.asyncio
async def test_leere_terms_fallen_auf_plainto_zurueck():
    """Stopword-only-Terme -> string_agg leer -> COALESCE-Fallback trägt."""
    matched = await _query_scalar(
        OR_TSQUERY_MATCH,
        {"doc": DOKUMENT_TEXT, "query": "Müller", "fts_terms": []},
    )
    assert matched is True
