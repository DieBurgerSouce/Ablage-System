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

pytestmark = pytest.mark.contract


# Router-Präfixe vollständig gefrorener Domänen. Jeder wurde gegen die
# Live-OpenAPI als sauber (0 Pfade) verifiziert — es gibt keine aktive Route,
# die dasselbe Präfix legitim nutzt (z. B. läuft DATEV-Metrik unter
# ``/api/v1/metrics/datev``, NICHT ``/api/v1/datev``).
FROZEN_ROUTER_PREFIXES: List[str] = [
    "/api/v1/einvoice",          # MODULE_EINVOICE (Go-Live-Audit M-06!)
    "/api/v1/banking",           # MODULE_BANKING
    "/api/v1/accounting",        # MODULE_ACCOUNTING
    "/api/v1/holding",           # MODULE_HOLDING
    "/api/v1/streckengeschaeft", # MODULE_STRECKENGESCHAEFT
    "/api/v1/document-chains",   # MODULE_DOCUMENT_CHAINS
    "/api/v1/lexware",           # MODULE_LEXWARE
    "/api/v1/datev",             # MODULE_DATEV
    "/api/v1/invoices",          # MODULE_INVOICE_TRACKING
    "/api/v1/cash",              # MODULE_KASSE
]

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
    """DoD §8.2: Die ausgelieferte App zeigt nur aktive Module."""

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
