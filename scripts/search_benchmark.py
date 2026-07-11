# -*- coding: utf-8 -*-
"""Such-Benchmark, 30 Queries (AP-5, Go-Live-Runbook DoD 6).

Misst die Suchlatenz auf SERVICE-Ebene im backend-Container — also im selben
Prozess-Setup wie die API (Query-Embeddings auf CPU, M-35), aber OHNE den
HTTP-/Auth-/Rate-Limit-Overhead. Bewusste Entscheidung: der Endpoint
``/api/v1/search/semantic`` ist auf 20/min limitiert (semantic_search.py:53);
ein HTTP-Benchmark muesste kuenstlich drosseln und misst dann Wartezeit statt
Suchzeit. Der HTTP-Anteil liegt im einstelligen ms-Bereich und ist fuer das
DoD-Ziel (P95 < 10 s, Ziel < 2 s) irrelevant.

Gemessen werden je Query zwei Pfade:
- ``semantic``   — SemanticSearchService.semantic_search (whole-doc, pgvector)
- ``rag_hybrid`` — RAGSearchService.hybrid_search (Chunks, RRF Vektor+FTS)

Aufruf im Backend-Container (scripts/ ist read-only gemountet):

    docker compose exec backend python scripts/search_benchmark.py
    docker compose exec backend python scripts/search_benchmark.py --user-email ben@firmenich.de
    docker compose exec backend python scripts/search_benchmark.py --queries-file /app/docs/qa-reports/queries.json

Protokoll geht nach stdout UND (falls beschreibbar) nach
``docs/qa-reports/<datum>-suche-benchmark.md``.

Feinpoliert und durchdacht.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# WICHTIG: Auf Modul-Ebene NUR Stdlib importieren (Unit-Tests der reinen
# Funktionen laufen ohne App-Umgebung); App-Imports lazy im Ausfuehrungspfad.

# sys.path-Bootstrap: Beim Direktaufruf "python scripts/search_benchmark.py"
# ist sys.path[0] das scripts/-Verzeichnis — Projekt-Root ergaenzen, damit
# "app.*" ohne PYTHONPATH importierbar ist (Muster: create_admin.py).
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# Query-Set (Runbook AP-5: 10x Belegnr., 10x Lieferant/Kunde, 5x Freitext,
# 5x semantisch). Ueberschreibbar via --queries-file (JSON: [[kategorie, text]]).
# =============================================================================

DEFAULT_QUERIES: List[Tuple[str, str]] = [
    # --- Belegnummern / Referenzen (10) ---
    ("belegnr", "RE/26-27/00012"),
    ("belegnr", "Rechnung 10756"),
    ("belegnr", "Lieferschein 88123"),
    ("belegnr", "Bestellung 4711"),
    ("belegnr", "Gutschrift 2024-091"),
    ("belegnr", "Auftragsbestaetigung AB-2025-1042"),
    ("belegnr", "Rechnungsnummer 2023-4471"),
    ("belegnr", "Wareneingang WE 2022 Maerz"),
    ("belegnr", "Storno 17052"),
    ("belegnr", "Beleg 906088"),
    # --- Lieferant / Kunde (10) ---
    ("lieferant_kunde", "Rechnungen von DPD"),
    ("lieferant_kunde", "Telekom Rechnung"),
    ("lieferant_kunde", "Sparkasse Kontoauszug"),
    ("lieferant_kunde", "Rechnung Verpackungsgrosshandel"),
    ("lieferant_kunde", "Lieferant Klingenstahl"),
    ("lieferant_kunde", "Kunde Hofladen Meyer"),
    ("lieferant_kunde", "Stadtwerke Abrechnung"),
    ("lieferant_kunde", "Versicherung Beitragsrechnung"),
    ("lieferant_kunde", "Werbeagentur Rechnung 2025"),
    ("lieferant_kunde", "Spedition Frachtrechnung"),
    # --- Freitext (5) ---
    ("freitext", "Spargelmesser Edelstahl 16cm"),
    ("freitext", "Mietvertrag Lagerhalle"),
    ("freitext", "Wartungsvertrag Verpackungsmaschine"),
    ("freitext", "Skonto 2 Prozent 14 Tage"),
    ("freitext", "Retoure beschaedigte Ware"),
    # --- Semantisch (5) ---
    ("semantisch", "Was haben wir zuletzt fuer Buerobedarf ausgegeben?"),
    ("semantisch", "Unterlagen zur Reparatur des Gabelstaplers"),
    ("semantisch", "Vertraege die dieses Jahr auslaufen"),
    ("semantisch", "Teuerste Eingangsrechnung im Fruehjahr"),
    ("semantisch", "Nachweis ueber die Entsorgungsgebuehren"),
]


def percentile(p: float, values: Sequence[float]) -> float:
    """Nearest-Rank-Perzentil (deterministisch, keine Interpolation).

    Raises:
        ValueError: bei leerer Eingabe.
    """
    if not values:
        raise ValueError("percentile() braucht mindestens einen Wert")
    ordered = sorted(values)
    rank = max(1, math.ceil((p / 100.0) * len(ordered)))
    return ordered[rank - 1]


@dataclass
class QueryTiming:
    """Eine Messung: ein Query gegen einen Suchpfad."""

    endpoint: str
    category: str
    query: str
    ms: float
    results: int
    error: Optional[str] = None


def format_report(timings: List[QueryTiming], *, p95_limit_ms: float) -> str:
    """Baut das Mess-Protokoll (Markdown) aus den Einzelmessungen."""
    lines: List[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# Such-Benchmark (DoD 6, Go-Live-Runbook AP-5)")
    lines.append("")
    lines.append(
        f"Stand: {stamp} · Service-Ebene im backend-Container · "
        f"Limit: P95 < {p95_limit_ms / 1000:.0f} s (Ziel < 2 s)"
    )
    lines.append("")

    endpoints = sorted({t.endpoint for t in timings})
    overall_ok = True
    lines.append("| Pfad | Queries | P50 (ms) | P95 (ms) | Max (ms) | Fehler | Status |")
    lines.append("|---|---|---|---|---|---|---|")
    for endpoint in endpoints:
        rows = [t for t in timings if t.endpoint == endpoint]
        ok_rows = [t.ms for t in rows if t.error is None]
        errors = sum(1 for t in rows if t.error is not None)
        if ok_rows:
            p50 = percentile(50, ok_rows)
            p95 = percentile(95, ok_rows)
            mx = max(ok_rows)
            ok = p95 <= p95_limit_ms and errors == 0
        else:
            p50 = p95 = mx = float("nan")
            ok = False
        overall_ok = overall_ok and ok
        lines.append(
            f"| {endpoint} | {len(rows)} | {p50:.0f} | {p95:.0f} | {mx:.0f} "
            f"| {errors} | {'PASS' if ok else 'FAIL'} |"
        )
    lines.append("")
    lines.append(f"**GESAMT: {'PASS' if overall_ok else 'FAIL'}**")

    slow = sorted(
        (t for t in timings if t.error is None), key=lambda t: t.ms, reverse=True
    )[:5]
    if slow:
        lines.append("")
        lines.append("Langsamste Messungen:")
        for t in slow:
            lines.append(
                f"- {t.ms:.0f} ms · {t.endpoint} · [{t.category}] {t.query!r} "
                f"({t.results} Treffer)"
            )
    failed = [t for t in timings if t.error is not None]
    if failed:
        lines.append("")
        lines.append("Fehlgeschlagene Messungen:")
        for t in failed:
            lines.append(f"- {t.endpoint} · {t.query!r}: {t.error}")
    return "\n".join(lines)


# =============================================================================
# Orchestrierung (lazy App-Imports)
# =============================================================================


def _load_queries(path: Optional[str]) -> List[Tuple[str, str]]:
    if not path:
        return list(DEFAULT_QUERIES)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(str(c), str(t)) for c, t in raw]


async def _resolve_user_id(db: Any, email: Optional[str]) -> Optional[Any]:
    from sqlalchemy import select

    from app.db.models import User

    if email:
        stmt = select(User).where(User.email == email)
    else:
        stmt = (
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.is_superuser.desc(), User.created_at.asc())
            .limit(1)
        )
    user = (await db.execute(stmt)).scalars().first()
    return user.id if user else None


async def _measure(
    db: Any, user_id: Any, queries: List[Tuple[str, str]]
) -> List[QueryTiming]:
    from app.services.rag.search_service import RAGSearchService
    from app.services.semantic_search_service import SemanticSearchService

    semantic = SemanticSearchService()
    rag = RAGSearchService()
    timings: List[QueryTiming] = []

    # Warmup (Modell-/Cache-Kaltstart nicht mitmessen; 1 Query je Pfad)
    warm_category, warm_query = queries[0]
    try:
        await semantic.semantic_search(
            query=warm_query, session=db, user_id=user_id, limit=10
        )
        await rag.hybrid_search(db, warm_query, limit=10, user_id=user_id)
    except Exception:  # noqa: BLE001 — Warmup-Fehler zeigt sich in den Messungen
        pass

    for category, query in queries:
        # Pfad 1: whole-doc semantische Suche
        start = time.perf_counter()
        try:
            results = await semantic.semantic_search(
                query=query, session=db, user_id=user_id, limit=10
            )
            timings.append(
                QueryTiming(
                    endpoint="semantic",
                    category=category,
                    query=query,
                    ms=(time.perf_counter() - start) * 1000.0,
                    results=len(results),
                )
            )
        except Exception as exc:  # noqa: BLE001 — einzelner Fehler stoppt nicht die Messreihe
            timings.append(
                QueryTiming(
                    endpoint="semantic",
                    category=category,
                    query=query,
                    ms=(time.perf_counter() - start) * 1000.0,
                    results=0,
                    error=str(exc),
                )
            )
            # Abgebrochene Transaktion aufraeumen, sonst scheitern ALLE
            # Folge-Queries mit InFailedSQLTransactionError.
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass

        # Pfad 2: Chunk-Hybrid-Suche (RAG)
        start = time.perf_counter()
        try:
            response = await rag.hybrid_search(db, query, limit=10, user_id=user_id)
            timings.append(
                QueryTiming(
                    endpoint="rag_hybrid",
                    category=category,
                    query=query,
                    ms=(time.perf_counter() - start) * 1000.0,
                    results=int(getattr(response, "total_results", 0) or 0),
                )
            )
        except Exception as exc:  # noqa: BLE001
            timings.append(
                QueryTiming(
                    endpoint="rag_hybrid",
                    category=category,
                    query=query,
                    ms=(time.perf_counter() - start) * 1000.0,
                    results=0,
                    error=str(exc),
                )
            )
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return timings


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    queries = _load_queries(args.queries_file)

    import app.db.all_models  # noqa: F401  # registriert den vollstaendigen ORM-Modellgraphen
    from app.db.session import get_async_session_context

    async with get_async_session_context() as db:
        user_id = await _resolve_user_id(db, args.user_email)
        if user_id is None:
            print("FAIL: Kein Benutzer gefunden (--user-email pruefen)", flush=True)
            return 1
        print(
            f"Benchmark: {len(queries)} Queries x 2 Pfade, user_id={user_id}",
            flush=True,
        )
        timings = await _measure(db, user_id, queries)

    report = format_report(timings, p95_limit_ms=args.limit_ms)
    print("\n" + report, flush=True)

    if args.output != "-":
        out_path = Path(
            args.output
            or f"docs/qa-reports/{datetime.now(timezone.utc):%Y-%m-%d}-suche-benchmark.md"
        )
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report + "\n", encoding="utf-8")
            print(f"\nProtokoll: {out_path}", flush=True)
        except OSError as exc:
            print(f"\nProtokoll nicht schreibbar ({exc}) — stdout gilt.", flush=True)

    return 0 if "GESAMT: PASS" in report else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="30-Query-Such-Benchmark (DoD 6): P50/P95 fuer semantic + rag_hybrid"
    )
    parser.add_argument(
        "--user-email",
        default=None,
        help="Suchender Benutzer (Default: erster aktiver Superuser)",
    )
    parser.add_argument(
        "--queries-file",
        default=None,
        metavar="PFAD",
        help="JSON-Datei [[kategorie, text], ...] statt der 30 Default-Queries",
    )
    parser.add_argument(
        "--limit-ms",
        type=float,
        default=10_000.0,
        help="P95-Limit in ms (DoD 6: 10000; Ziel 2000)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PFAD",
        help="Protokoll-Datei (Default docs/qa-reports/<datum>-suche-benchmark.md; '-' = nur stdout)",
    )
    return parser


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
