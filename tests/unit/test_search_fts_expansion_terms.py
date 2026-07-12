# -*- coding: utf-8 -*-
"""Regressionstest F-P2-005 (Perception-Audit 2026-07-12) — Term-Builder.

Die Umlaut-/Kompositum-Expansion erzeugte Queries wie "Müller mueller";
plainto_tsquery verknüpfte die Wörter mit AND -> ein Dokument mit nur einer
Schreibweise wurde NICHT gefunden (0 Treffer trotz vorhandenem Dokument).
build_fts_expansion_terms() liefert die Terme, die die SQL-Seite mit OR
verknüpft: Gesamtquery (Präzision) + Einzelwörter (Recall).
"""
from app.services.search_service import build_fts_expansion_terms


def test_expansion_query_liefert_gesamtquery_plus_einzelwoerter():
    assert build_fts_expansion_terms("Müller mueller") == [
        "Müller mueller",
        "Müller",
        "mueller",
    ]


def test_einzelwort_bleibt_einzelner_term():
    assert build_fts_expansion_terms("Bürohaus") == ["Bürohaus"]


def test_dedupliziert_case_insensitiv_unter_erhalt_der_reihenfolge():
    assert build_fts_expansion_terms("Müller müller MÜLLER") == [
        "Müller müller MÜLLER",
        "Müller",
    ]


def test_whitespace_wird_getrimmt():
    assert build_fts_expansion_terms("  Müller   mueller  ") == [
        "Müller   mueller",
        "Müller",
        "mueller",
    ]


def test_leere_query_liefert_leere_liste():
    # SQL-Seite fällt dann via COALESCE auf plainto_tsquery(:query) zurück
    assert build_fts_expansion_terms("") == []
    assert build_fts_expansion_terms("   ") == []
