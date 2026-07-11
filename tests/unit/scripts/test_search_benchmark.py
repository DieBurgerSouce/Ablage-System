"""Tests fuer scripts/search_benchmark.py (AP-5 Go-Live-Runbook, DoD 6).

Reine Funktionen ohne App-/DB-Imports: Perzentil-Berechnung (nearest-rank),
Default-Query-Set (30 Queries, Kategorien-Mix 10/10/5/5), Report-Format.
"""

import os
import sys

import pytest

pytestmark = [pytest.mark.unit]


def _locate_scripts_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "..", "scripts"),
        "/app/scripts",
        os.path.join(os.getcwd(), "scripts"),
    ]
    for base in candidates:
        path = os.path.abspath(os.path.join(base, "search_benchmark.py"))
        if os.path.isfile(path):
            return os.path.dirname(path)
    return ""


_SCRIPTS_DIR = _locate_scripts_dir()

if not _SCRIPTS_DIR:
    pytest.skip(
        "search_benchmark.py nicht auffindbar - scripts/ ist in dieser "
        "Umgebung nicht gemountet (Infra-Setup, kein Test-Drift).",
        allow_module_level=True,
    )

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from search_benchmark import (  # noqa: E402
    DEFAULT_QUERIES,
    QueryTiming,
    format_report,
    percentile,
)


# =============================================================================
# percentile (nearest-rank)
# =============================================================================


def test_percentile_median_von_1_bis_10():
    assert percentile(50, list(range(1, 11))) == 5


def test_percentile_p95_von_1_bis_10():
    assert percentile(95, list(range(1, 11))) == 10


def test_percentile_einzelwert():
    assert percentile(95, [42.0]) == 42.0


def test_percentile_unsortierte_eingabe():
    assert percentile(50, [9, 1, 5, 3, 7]) == 5


def test_percentile_leere_liste_wirft():
    with pytest.raises(ValueError):
        percentile(95, [])


# =============================================================================
# DEFAULT_QUERIES (30 Queries, Kategorien-Mix aus dem Runbook)
# =============================================================================


def test_query_set_hat_30_eintraege():
    assert len(DEFAULT_QUERIES) == 30


def test_query_set_kategorien_mix():
    counts = {}
    for category, _text in DEFAULT_QUERIES:
        counts[category] = counts.get(category, 0) + 1
    assert counts == {
        "belegnr": 10,
        "lieferant_kunde": 10,
        "freitext": 5,
        "semantisch": 5,
    }


def test_query_texte_nicht_leer_und_eindeutig():
    texts = [text for _c, text in DEFAULT_QUERIES]
    assert all(t.strip() for t in texts)
    assert len(set(texts)) == len(texts)


# =============================================================================
# format_report
# =============================================================================


def test_report_enthaelt_p50_p95_und_ziel_bewertung():
    timings = [
        QueryTiming(endpoint="semantic", category="belegnr", query="q1", ms=120.0, results=3),
        QueryTiming(endpoint="semantic", category="freitext", query="q2", ms=480.0, results=1),
        QueryTiming(endpoint="rag_hybrid", category="belegnr", query="q1", ms=200.0, results=5),
    ]
    report = format_report(timings, p95_limit_ms=10_000)

    assert "P50" in report and "P95" in report
    assert "semantic" in report and "rag_hybrid" in report
    assert "PASS" in report  # 480 ms < 10 s Limit


def test_report_fail_bei_limit_ueberschreitung():
    timings = [
        QueryTiming(endpoint="semantic", category="belegnr", query="q", ms=12_000.0, results=0),
    ]
    report = format_report(timings, p95_limit_ms=10_000)
    assert "FAIL" in report
