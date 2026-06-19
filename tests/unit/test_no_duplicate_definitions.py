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
    # AUFGELOEST (aus KNOWN entfernt):
    #  - SeasonalPatternResponse (orchestration.py): ECHTER Shadowing-Bug -> detect-
    #    patterns konstruierte die falsche Klasse -> 500; detaillierte Klasse zu
    #    SeasonalPatternDetailResponse umbenannt + Endpoint umgestellt.
    #  - TransactionFilter (banking/models.py): tote Basis-Def entfernt (kein Aufrufer).
    #  - create_quality_snapshot (training.py): 1. Route-Handler -> _bulk umbenannt.
    #
    # VERBLEIBEND - die 6 schemas.py-Duplikate sind agent-verifiziert KOSMETISCH
    # (Konstruktionen treffen die ueberschattende 2. Def), aber NICHT trivial
    # entfernbar: schemas.py hat KEINE deferred annotations, und Klassen ZWISCHEN den
    # beiden Defs nutzen die 1. Def (z.B. BusinessEntityBase -> EntityType.SUPPLIER;
    # TrendResponse -> List[TrendDataPoint]). Loeschen/Umbenennen der 1. Def -> NameError
    # beim Import (gelernt: AST/ratchet maskiert das, nur ein Import-Check faengt es).
    # Sauberer Fix braucht Umverdrahtung der Zwischen-Nutzer -> separater Task.
    ("app/db/schemas.py", "class", "EntityType"),
    ("app/db/schemas.py", "class", "DocumentTypeStats"),
    ("app/db/schemas.py", "class", "EntityRiskResponse"),
    ("app/db/schemas.py", "class", "RiskFactorsResponse"),
    ("app/db/schemas.py", "class", "TrendDataPoint"),
    ("app/db/schemas.py", "class", "ValidationQueueListResponse"),
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
