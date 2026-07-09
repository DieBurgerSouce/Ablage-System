# -*- coding: utf-8 -*-
"""Contract-Test: Modul-Freeze wirkt auf der ECHTEN App-Oberfläche.

Hintergrund (Odoo-Neuausrichtung 2026, Plan §4a + DoD §8.2): Die ERP-Doppel-
Module sind eingefroren — ihre Router dürfen in der ausgelieferten App NICHT
registriert sein (alle Endpoints → 404). ``tests/unit/core/test_module_registry.py``
prüft nur das *Verhalten* von ``include_module_router`` an einem Dummy-Router.
Es fehlte ein Test, der die **echte** ``app.main.app`` gegen die Freeze-Zusage
hält — genau diese Lücke ließ den Misch-Router ``finance.py`` (F-01: aktives
Jahres-Archiv + gefrorener Cashflow-Forecast unter einem plain registrierten
Router) durchrutschen.

Dieser Test lädt die reale OpenAPI (Fixture ``openapi_schema`` aus
``tests/contract/conftest.py``) und prüft:

1. **Kein Auftauchen** — für jede vollständig gefrorene Domäne darf kein Pfad
   mit ihrem Router-Präfix existieren (Unter-Freeze-Schutz, u. a. M-06 einvoice).
2. **Leck-Pfade** — die aus dem Misch-Router ``finance.py`` ausgegliederten,
   gefrorenen Cashflow-Pfade dürfen nicht mehr erreichbar sein (F-01-Regression).
3. **Über-Freeze-Schutz** — die aktiven Jahres-Archiv-Pfade MÜSSEN erhalten
   bleiben; ein Router-Split, der sie versehentlich einfriert, wird rot.

Default-Konfiguration (``ACTIVE_OPTIONAL_MODULES`` leer) wird vorausgesetzt —
so läuft die App im Auslieferungszustand.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

import pytest

from app.core.module_registry import (
    KNOWN_OPTIONAL_MODULES,
    MODULE_ACCOUNTING,
    MODULE_AI_SPECULATIVE,
    MODULE_BANKING,
    MODULE_DATEV,
    MODULE_DOCUMENT_CHAINS,
    MODULE_EINVOICE,
    MODULE_FINANCE,
    MODULE_HOLDING,
    MODULE_INVOICE_TRACKING,
    MODULE_KASSE,
    MODULE_LEXWARE,
    MODULE_RISK_FINANZKI,
    MODULE_STRECKENGESCHAEFT,
)

pytestmark = pytest.mark.contract


# Router-Präfixe vollständig gefrorener Domänen. Jeder wurde gegen die
# Live-OpenAPI als sauber (0 Pfade) verifiziert — es gibt keine aktive Route,
# die dasselbe Präfix legitim nutzt (z. B. läuft DATEV-Metrik unter
# ``/api/v1/metrics/datev``, NICHT ``/api/v1/datev``).
# Modul → Router-Präfix(e), die bei eingefrorenem Modul komplett fehlen müssen.
# Diese 10 Module haben je einen sauberen Prefix und werden vollständig
# präfix-verifiziert. Jeder wurde gegen die Live-OpenAPI als sauber (0 Pfade)
# bestätigt — es gibt keine aktive Route, die dasselbe Präfix legitim nutzt
# (z. B. läuft DATEV-Metrik unter ``/api/v1/metrics/datev``, NICHT ``/api/v1/datev``).
FROZEN_PREFIX_BY_MODULE: Dict[str, str] = {
    MODULE_EINVOICE: "/api/v1/einvoice",              # Go-Live-Audit M-06!
    MODULE_BANKING: "/api/v1/banking",
    MODULE_ACCOUNTING: "/api/v1/accounting",
    MODULE_HOLDING: "/api/v1/holding",
    MODULE_STRECKENGESCHAEFT: "/api/v1/streckengeschaeft",
    MODULE_DOCUMENT_CHAINS: "/api/v1/document-chains",
    MODULE_LEXWARE: "/api/v1/lexware",
    MODULE_DATEV: "/api/v1/datev",
    MODULE_INVOICE_TRACKING: "/api/v1/invoices",
    MODULE_KASSE: "/api/v1/cash",
}
FROZEN_ROUTER_PREFIXES: List[str] = list(FROZEN_PREFIX_BY_MODULE.values())

# Module, deren Freeze dieser Präfix-Test NICHT vollständig abdeckt — mit Grund.
# Wichtig: Diese Ausnahmen sind bewusst und dokumentiert; die Coverage-Assertion
# unten erzwingt, dass ein NEU hinzugefügtes optionales Modul entweder einen
# Präfix-Check bekommt oder hier mit Begründung eingetragen wird (schließt die
# „stilles Auftauen eines neuen Moduls"-Lücke, die eine reine Hardcode-Liste ließe).
MODULES_NOT_PREFIX_VERIFIED: Dict[str, str] = {
    MODULE_FINANCE: (
        "Misch-Prefix /finance: aktives Jahres-Archiv + gefrorene /liquidity/* "
        "(F-01) — separat über FROZEN_LEAK_PATHS/ACTIVE_ARCHIVE_PATHS geprüft."
    ),
    MODULE_RISK_FINANZKI: (
        "Verstreute Präfixe (/predictions, /payment-behavior, /fraud, "
        "/risk-intelligence, /credit, /financial-insights, …) — live per "
        "OpenAPI-Sweep als 404 verifiziert, hier nicht einzeln enumeriert."
    ),
    MODULE_AI_SPECULATIVE: (
        "Verstreute Präfixe + BEKANNTE FE/BE-Inkonsistenz (Review-Finding H3, "
        "P2): ml_dashboard/adhoc_reports/predictive_actions sind FE-frozen, aber "
        "am BE plain registriert (aktiv). Bis zur koordinierten Freeze-Bereinigung "
        "bewusst NICHT als vollständig gefroren asserted."
    ),
}

# Einzelpfade, die aus dem Misch-Router ``finance.py`` als gefroren
# ausgegliedert wurden (F-01). Vor dem Split waren sie live erreichbar.
FROZEN_LEAK_PATHS: List[str] = [
    "/api/v1/finance/liquidity/forecast",
    "/api/v1/finance/liquidity/waterfall",
    "/api/v1/finance/liquidity/bottlenecks",
    "/api/v1/finance/liquidity/anomalies",
]

# Aktive Jahres-Archiv-Pfade — dürfen durch den Split NICHT verloren gehen.
ACTIVE_ARCHIVE_PATHS: List[str] = [
    "/api/v1/finance/years",
    "/api/v1/finance/aggregations",
]


def _paths(openapi_schema: Dict[str, Any]) -> Set[str]:
    return set(openapi_schema.get("paths", {}).keys())


class TestModuleFreezeSurface:
    """DoD §8.2: Die ausgelieferte App zeigt nur aktive Module.

    Deckung (ehrlich): Der Präfix-Test verifiziert die 10 Module in
    ``FROZEN_PREFIX_BY_MODULE`` vollständig (0 Pfade) plus die F-01-Leck-Pfade.
    Die 3 Module in ``MODULES_NOT_PREFIX_VERIFIED`` (finance, risk_finanzki,
    ai_speculative) sind hier NICHT vollständig abgedeckt — mit dokumentierter
    Begründung. ``test_frozen_module_coverage_is_complete`` stellt sicher, dass
    ein neu hinzugefügtes optionales Modul nicht unbemerkt durch dieses Raster
    fällt.
    """

    def test_frozen_module_coverage_is_complete(self) -> None:
        """Jedes optionale Modul ist entweder präfix-verifiziert oder mit Grund ausgenommen.

        Regressionsschutz gegen die Hardcode-Falle (Review-Finding R6): Ohne
        diese Assertion würde ein NEUES gefrorenes Modul (oder ein Umbenennen)
        still am Präfix-Test vorbeilaufen. Schlägt fehl, sobald
        ``KNOWN_OPTIONAL_MODULES`` einen Key enthält, der weder einen
        Präfix-Check noch einen dokumentierten Ausnahme-Eintrag hat.
        """
        covered = set(FROZEN_PREFIX_BY_MODULE) | set(MODULES_NOT_PREFIX_VERIFIED)
        uncovered = set(KNOWN_OPTIONAL_MODULES) - covered
        assert not uncovered, (
            "Optionale Module ohne Freeze-Test-Deckung (Präfix-Check ergänzen "
            f"oder in MODULES_NOT_PREFIX_VERIFIED mit Grund eintragen): {sorted(uncovered)}"
        )
        # Keine verwaisten Einträge (Modul umbenannt/entfernt):
        stale = covered - set(KNOWN_OPTIONAL_MODULES)
        assert not stale, f"Test kennt Module, die die Registry nicht (mehr) hat: {sorted(stale)}"

    def test_frozen_router_prefixes_absent(
        self, openapi_schema: Dict[str, Any]
    ) -> None:
        """Kein Pfad einer vollständig gefrorenen Domäne ist registriert."""
        paths = _paths(openapi_schema)
        leaked = {
            prefix: sorted(p for p in paths if p.startswith(prefix))
            for prefix in FROZEN_ROUTER_PREFIXES
        }
        leaked = {k: v for k, v in leaked.items() if v}
        assert not leaked, (
            "Gefrorene Router sind in der OpenAPI erreichbar (Freeze umgangen): "
            f"{leaked}"
        )

    def test_frozen_finance_leak_paths_absent(
        self, openapi_schema: Dict[str, Any]
    ) -> None:
        """F-01: Die gefrorenen Cashflow-Pfade aus finance.py sind 404."""
        paths = _paths(openapi_schema)
        still_live = [p for p in FROZEN_LEAK_PATHS if p in paths]
        assert not still_live, (
            "Misch-Router-Leck (F-01): gefrorene Cashflow-Pfade weiterhin live — "
            f"{still_live}. Erwartung: über liquidity_router mit MODULE_FINANCE "
            "gegated (app/main.py) → nicht registriert."
        )

    def test_active_archive_paths_present(
        self, openapi_schema: Dict[str, Any]
    ) -> None:
        """Über-Freeze-Schutz: Das aktive Jahres-Archiv bleibt erreichbar."""
        paths = _paths(openapi_schema)
        missing = [p for p in ACTIVE_ARCHIVE_PATHS if p not in paths]
        assert not missing, (
            "Aktive Archiv-Pfade fehlen — der Router-Split hat zu viel "
            f"eingefroren: {missing}"
        )
