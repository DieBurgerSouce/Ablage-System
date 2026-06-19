# -*- coding: utf-8 -*-
"""Guard gegen doppelte Top-Level-Definitionen (Shadowing-Bugs).

Zwei Klassen/Funktionen mit gleichem Namen im selben Modul: die zweite
ueberschreibt still die erste. Bei Pydantic-Modellen fuehrt das zu
order-abhaengigen Schema-Aufloesungen (z. B. SeasonalPatternResponse,
TrendDataPoint -> Feld required<->optional je nach Aufloesungsreihenfolge).

Die bekannten Faelle sind als Tech-Debt eingefroren (sie brauchen einen
reviewten Fix mit Klaerung, welche Definition kanonisch ist). NEUE Duplikate
sind verboten -> dieser Test schlaegt dann fehl.
"""

import ast
import pathlib
from collections import Counter

# Bekannte Alt-Lasten (Stand 2026-06-04). Format: (relpath, "class"|"func", name).
KNOWN_DUPLICATES = {
    # SeasonalPatternResponse (orchestration.py) BEHOBEN: die detaillierte Klasse
    # wurde zu SeasonalPatternDetailResponse umbenannt (war Shadowing-Bug ->
    # detect-patterns-Endpoint konstruierte die falsche Klasse -> 500).
    # EntityType -> BusinessPartnerType; create_quality_snapshot -> _bulk umbenannt;
    # DocumentTypeStats/TrendDataPoint/ValidationQueueListResponse tote 1.-Defs
    # entfernt (alle agent-verifiziert KOSMETISCH, 0 Runtime-Bug).
    # VERBLEIBEND (bewusst belassen, agent-verifiziert kosmetisch): das inter-
    # referenzierende RiskFactorsResponse/EntityRiskResponse-Cluster (1. Defs tot,
    # Konstruktionen nutzen die 2. Defs; intricate Cluster-Refactor lohnt nicht).
    ("app/db/schemas.py", "class", "EntityRiskResponse"),
    ("app/db/schemas.py", "class", "RiskFactorsResponse"),
    # TransactionFilter (banking/models.py) BEHOBEN: tote Basis-Def (mit
    # bank_account_id) entfernt - war shadowed, kein Aufrufer nutzte sie.
}


def _find_duplicates() -> set:
    repo = pathlib.Path(__file__).resolve().parents[2]
    dups: set = set()
    for p in (repo / "app").rglob("*.py"):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = p.relative_to(repo).as_posix()
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        funcs = [
            n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for kind, names in (("class", classes), ("func", funcs)):
            for name, count in Counter(names).items():
                if count > 1:
                    dups.add((rel, kind, name))
    return dups


def test_no_new_duplicate_definitions() -> None:
    """Keine NEUEN Top-Level-Doppeldefinitionen (Shadowing) erlaubt."""
    current = _find_duplicates()

    new = current - KNOWN_DUPLICATES
    assert not new, (
        "Neue Doppeldefinition(en) (Shadowing-Bug) gefunden:\n  "
        + "\n  ".join(f"{kind} {name} in {f}" for f, kind, name in sorted(new))
    )

    fixed = KNOWN_DUPLICATES - current
    assert not fixed, (
        "Bekannte Alt-Lasten wurden behoben - bitte aus KNOWN_DUPLICATES entfernen:\n  "
        + "\n  ".join(f"{kind} {name} in {f}" for f, kind, name in sorted(fixed))
    )
