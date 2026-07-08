# -*- coding: utf-8 -*-
"""Modul-Registry: Einfrieren der ERP-Doppel-Module (Odoo-Neuausrichtung 2026).

Hintergrund (Plan "Neuausrichtung Ablage-System nach Lexware→Odoo-Wechsel",
§4a + §4c.1): Odoo 18 übernimmt ab 01.08.2026 die Geschäftsprozesse
(Bank-Sync, Mahnwesen, Buchhaltung, DATEV, E-Rechnung, ...). Die dadurch
redundanten Module des Ablage-Systems werden EINGEFROREN — nicht entfernt:

- Backend-Router werden nicht mehr registriert → alle Endpoints liefern 404.
  Sicherheitsrelevant: Das schließt u. a. die unauthentifizierten
  einvoice-Endpoints (Go-Live-Audit M-06, ``app/api/v1/einvoice.py``).
- Celery: Task-Module eingefrorener Domänen fliegen aus der include-Liste,
  zugehörige Beat-Einträge werden gepoppt (``app/workers/celery_app.py``).
- Code, ORM-Modelle (``app/db/all_models``) und Daten bleiben unverändert →
  das Einfrieren ist vollständig reversibel und erfordert keine Migration.

Reaktivierung (Rollback pro Modul, ohne Code-Änderung):
    ACTIVE_OPTIONAL_MODULES="banking,datev"   # Komma-Liste von Modul-Keys
    ACTIVE_OPTIONAL_MODULES="*"               # alle Module aktivieren

Danach Backend und Worker neu starten — Router-Registrierung und
Celery-Includes passieren beim Prozess-Start, nicht zur Laufzeit
(deshalb ist das DB-basierte ``feature_flag_service`` hier ungeeignet).

Der Status ist zur Laufzeit über ``GET /api/v1/system/modules`` abfragbar
(``app/api/v1/system_modules.py``, fürs Frontend-Gating).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, FrozenSet, List, Optional, Union, cast

import structlog

from app.core.config import settings

if TYPE_CHECKING:  # Nur für Type-Hints; hält den Celery-Worker fastapi-frei
    from enum import Enum

    from fastapi import APIRouter, FastAPI

logger = structlog.get_logger(__name__)


# =============================================================================
# Modul-Keys (Freeze-Liste gemäß Plan §4a — maßgeblich)
# =============================================================================

#: Banking/Reconciliation inkl. FinTS/PSD2/SEPA, Skonto, Teilzahlungen,
#: Mahnwesen/Dunning, Liquidität, Cash-Flow (→ Odoo account_online_synchronization
#: + account_followup).
MODULE_BANKING: str = "banking"

#: Buchhaltung: GL, USt-VA, EÜR, BWA, Budgets, Jahresabschluss (→ Odoo/DATEV-StB).
MODULE_ACCOUNTING: str = "accounting"

#: Finanz-Workflows: Recurring Invoices, PO-Matching, Cashflow-Prognosen,
#: vollautomatische Rechnungs-Pipeline (→ Odoo Fakturierung/Einkauf).
MODULE_FINANCE: str = "finance"

#: Invoice-Tracking (offene Posten, ``api/v1/invoices.py`` → Odoo offene Posten).
MODULE_INVOICE_TRACKING: str = "invoice_tracking"

#: DATEV-Export/Connect/Buchungsvorschläge + DATEV/Lexware-Sync-Admin
#: (→ StB bekommt DATEV künftig aus Odoo).
MODULE_DATEV: str = "datev"

#: E-Rechnungs-ERZEUGUNG (ZUGFeRD/XRechnung-Generierung, Audit M-06!).
#: Das ZUGFeRD-PARSING im E-Mail-Import (``app/services/einvoice/*`` als
#: Service) bleibt davon unberührt — eingefroren wird nur der Router
#: + der Batch-Validierungs-Task.
MODULE_EINVOICE: str = "einvoice"

#: Streckengeschäft / Drop-Shipment (→ Odoo Verkauf/Einkauf).
MODULE_STRECKENGESCHAEFT: str = "streckengeschaeft"

#: Lexware-Import/-Sync (Migration abgeschlossen; Bestandsdaten bleiben lesbar
#: über die normalen Entity-/Dokument-APIs).
MODULE_LEXWARE: str = "lexware"

#: Holding-/Intercompany-Dashboard.
MODULE_HOLDING: str = "holding"

#: Kassenbuch-Skelett (TSE/Kasse macht ggf. Odoo POS).
MODULE_KASSE: str = "kasse"

#: Belegketten (Document Chains — ERP-Overlap laut Plan §4a; das getrennte
#: ``lineage``-Modul bleibt aktiv).
MODULE_DOCUMENT_CHAINS: str = "document_chains"

#: Risk-Scoring/FinanzKI: Risk-Intelligence, Payment-Behavior/-Predictions,
#: Fraud, Predictive Cashflow, Liquiditäts-Szenarien, Creditreform,
#: Handelsregister-Monitoring (externe Quellen ohnehin Stubs, W1-011).
MODULE_RISK_FINANZKI: str = "risk_finanzki"

#: Im Go-Live-Audit 2026-07-02 als spekulativ markierte AI/Analytics-Router:
#: ai_*, digital_twin, command_center, proactive_assistant, trust_dashboard,
#: xai, zero_touch, ceo_dashboard, nlq, knowledge_graph, esg,
#: industry_benchmarks, learning_autonomy, smart_dashboard,
#: executive-reporting, autonomous/action_queue, agent_orchestrator,
#: finance_assistant, ai_mentor.
MODULE_AI_SPECULATIVE: str = "ai_speculative"


#: Alle bekannten optionalen Module. Aktuell sind alle optionalen Module
#: zugleich default-eingefroren; die Trennung KNOWN/FROZEN erlaubt später
#: optionale Module mit Default "aktiv".
KNOWN_OPTIONAL_MODULES: FrozenSet[str] = frozenset(
    {
        MODULE_BANKING,
        MODULE_ACCOUNTING,
        MODULE_FINANCE,
        MODULE_INVOICE_TRACKING,
        MODULE_DATEV,
        MODULE_EINVOICE,
        MODULE_STRECKENGESCHAEFT,
        MODULE_LEXWARE,
        MODULE_HOLDING,
        MODULE_KASSE,
        MODULE_DOCUMENT_CHAINS,
        MODULE_RISK_FINANZKI,
        MODULE_AI_SPECULATIVE,
    }
)

#: Module, die ohne expliziten Override in ``ACTIVE_OPTIONAL_MODULES``
#: eingefroren sind (Plan §4a).
FROZEN_BY_DEFAULT: FrozenSet[str] = KNOWN_OPTIONAL_MODULES

# -----------------------------------------------------------------------------
# Bewusst AKTIV gelassene Freeze-KANDIDATEN (Plan §4a nennt sie nicht; im
# Zweifel aktiv — Entscheidung fällt in einer späteren Welle):
#   inventory (Lagerverwaltung — Odoo-WaWi-Overlap), expenses (Spesen),
#   subscriptions/portal/onboarding (ruhende Produkt-Ambition),
#   shipments (explizit nicht entschieden), transactions (Vorgangsketten,
#   DocumentGroup-basiert), tax_advisor_packages (StB-Belegpakete =
#   Archiv-Funktion), supplier_ranking, supplier_verification, enrichment
#   (externe Quellen), booking_suggestions (generische Kontierung),
#   morning_briefing, daily_insights, proactive_insights (Insights-UI),
#   process_mining, explainability, predictive_actions, smart_escalation,
#   magic_buttons, period_comparison, assistant (Ollama-Chat, RAG-nah).
# -----------------------------------------------------------------------------


def _parse_active_overrides(raw_value: Optional[str] = None) -> FrozenSet[str]:
    """Parst ``ACTIVE_OPTIONAL_MODULES`` (Komma-Liste, ``*`` = alle).

    Args:
        raw_value: Roh-String; ``None`` liest ``settings.ACTIVE_OPTIONAL_MODULES``.

    Returns:
        Menge der explizit reaktivierten Modul-Keys (normalisiert).
    """
    if raw_value is None:
        raw_value = getattr(settings, "ACTIVE_OPTIONAL_MODULES", "")
    tokens = {token.strip().lower() for token in raw_value.split(",") if token.strip()}
    if "*" in tokens:
        return KNOWN_OPTIONAL_MODULES
    unknown = tokens - KNOWN_OPTIONAL_MODULES
    if unknown:
        logger.warning(
            "module_registry_unknown_keys_ignored",
            unknown_keys=sorted(unknown),
            known_keys=sorted(KNOWN_OPTIONAL_MODULES),
        )
    return frozenset(tokens & KNOWN_OPTIONAL_MODULES)


def is_module_active(module_key: str) -> bool:
    """Prüft, ob ein Modul aktiv ist.

    Liest ``settings.ACTIVE_OPTIONAL_MODULES`` bei jedem Aufruf (kein
    Modul-Cache), damit Tests via monkeypatch und Prozess-Neustarts mit
    geänderter ENV deterministisch wirken.

    Args:
        module_key: Modul-Key (siehe ``MODULE_*``-Konstanten). Keys außerhalb
            von ``FROZEN_BY_DEFAULT`` gelten immer als aktiv.

    Returns:
        True, wenn das Modul aktiv ist (Router registrieren / Tasks laden).
    """
    key = module_key.strip().lower()
    if key not in FROZEN_BY_DEFAULT:
        return True
    return key in _parse_active_overrides()


def include_module_router(
    app: FastAPI,
    router: APIRouter,
    module_key: str,
    *,
    prefix: str = "",
    tags: Optional[List[Union[str, Enum]]] = None,
    **kwargs: object,
) -> bool:
    """Registriert einen Router nur, wenn sein Modul aktiv ist.

    Drop-in-Ersatz für ``app.include_router(...)`` an den Freeze-Stellen in
    ``app/main.py``. Ist das Modul eingefroren, wird der Router NICHT
    registriert (alle seine Endpoints → 404) und ein strukturiertes Log
    geschrieben.

    Args:
        app: FastAPI-Applikation.
        router: Zu registrierender APIRouter.
        module_key: Modul-Key aus dieser Registry.
        prefix: URL-Prefix (wie bei ``include_router``).
        tags: Optionale OpenAPI-Tags (wie bei ``include_router``).
        **kwargs: Weitere ``include_router``-Argumente (durchgereicht).

    Returns:
        True, wenn der Router registriert wurde, sonst False.
    """
    if not is_module_active(module_key):
        logger.info(
            "module_frozen_router_skipped",
            module=module_key,
            router_prefix=f"{prefix}{router.prefix}",
            routes=len(router.routes),
            reactivation_hint="ACTIVE_OPTIONAL_MODULES (app/core/module_registry.py)",
        )
        return False
    # Passthrough beliebiger include_router-Argumente: bewusst als Callable[..., None]
    # gecastet (kein `Any`), da include_router ~15 spezifisch getypte Parameter hat.
    include_router_fn = cast("Callable[..., None]", app.include_router)
    if tags is not None:
        include_router_fn(router, prefix=prefix, tags=tags, **kwargs)
    else:
        include_router_fn(router, prefix=prefix, **kwargs)
    return True


def get_module_status() -> Dict[str, List[str]]:
    """Liefert den Aktiv-/Frozen-Status aller bekannten optionalen Module.

    Returns:
        ``{"active": [...], "frozen": [...]}`` — beide Listen sortiert,
        zusammen ergeben sie genau ``KNOWN_OPTIONAL_MODULES``.
    """
    active = sorted(key for key in KNOWN_OPTIONAL_MODULES if is_module_active(key))
    frozen = sorted(key for key in KNOWN_OPTIONAL_MODULES if not is_module_active(key))
    return {"active": active, "frozen": frozen}
