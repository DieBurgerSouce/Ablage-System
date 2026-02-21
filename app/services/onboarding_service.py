# -*- coding: utf-8 -*-
"""Guided Onboarding Service.

Phase 6.5: Interaktive Produkttour fuer neue Nutzer.
- Rollenbasierte Touren (Buchhaltung, GF, Sachbearbeitung, IT)
- Schritt-fuer-Schritt Checklisten
- Fortschrittsverfolgung pro Nutzer
- Kontextuelle Hilfe-Tooltips

Feinpoliert und durchdacht.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Onboarding-Konfiguration (In-Memory, kein DB-Model noetig)
# =============================================================================

# Tour-Schritte pro Rolle
ONBOARDING_TOURS: Dict[str, List[Dict[str, str]]] = {
    "buchhaltung": [
        {
            "id": "upload_first_doc",
            "title": "Erstes Dokument hochladen",
            "description": "Laden Sie Ihr erstes Dokument hoch. Das System erkennt automatisch den Typ und extrahiert relevante Daten.",
            "target": "/documents/upload",
            "action_label": "Dokument hochladen",
            "icon": "upload",
        },
        {
            "id": "check_ocr_result",
            "title": "OCR-Ergebnis pruefen",
            "description": "Pruefen Sie die automatisch erkannten Daten und korrigieren Sie bei Bedarf. Das System lernt aus Ihren Korrekturen.",
            "target": "/documents",
            "action_label": "Dokumente ansehen",
            "icon": "scan",
        },
        {
            "id": "link_entity",
            "title": "Geschaeftspartner zuordnen",
            "description": "Verknuepfen Sie Dokumente mit Geschaeftspartnern fuer eine strukturierte Ablage.",
            "target": "/entities",
            "action_label": "Geschaeftspartner oeffnen",
            "icon": "link",
        },
        {
            "id": "setup_datev",
            "title": "DATEV-Export einrichten",
            "description": "Konfigurieren Sie den automatischen DATEV-Export fuer Ihren Steuerberater.",
            "target": "/admin/integrations",
            "action_label": "Integrationen oeffnen",
            "icon": "settings",
        },
        {
            "id": "review_invoice",
            "title": "Rechnung pruefen und freigeben",
            "description": "Pruefen Sie eine erkannte Rechnung und geben Sie sie zur Zahlung frei.",
            "target": "/invoices",
            "action_label": "Rechnungen oeffnen",
            "icon": "receipt",
        },
    ],
    "management": [
        {
            "id": "view_dashboard",
            "title": "Dashboard kennenlernen",
            "description": "Ihr persoenliches Dashboard zeigt KPIs, Cashflow-Prognosen und offene Freigaben auf einen Blick.",
            "target": "/dashboard",
            "action_label": "Dashboard oeffnen",
            "icon": "layout-dashboard",
        },
        {
            "id": "check_cashflow",
            "title": "Cashflow-Prognose pruefen",
            "description": "Sehen Sie die automatische Cashflow-Prognose fuer die naechsten 30, 60 und 90 Tage.",
            "target": "/analytics/cashflow",
            "action_label": "Cashflow oeffnen",
            "icon": "trending-up",
        },
        {
            "id": "approve_document",
            "title": "Dokument freigeben",
            "description": "Geben Sie anstehende Dokumente und Rechnungen frei - direkt aus dem Dashboard.",
            "target": "/approvals",
            "action_label": "Freigaben oeffnen",
            "icon": "check-circle",
        },
        {
            "id": "explore_reports",
            "title": "Berichte erkunden",
            "description": "Nutzen Sie die vordefinierten Berichte oder erstellen Sie eigene Auswertungen.",
            "target": "/analytics",
            "action_label": "Berichte oeffnen",
            "icon": "bar-chart",
        },
    ],
    "sachbearbeitung": [
        {
            "id": "upload_batch",
            "title": "Dokumente im Batch hochladen",
            "description": "Laden Sie mehrere Dokumente gleichzeitig hoch. Drag & Drop oder Ordner-Upload wird unterstuetzt.",
            "target": "/documents/upload",
            "action_label": "Upload starten",
            "icon": "upload",
        },
        {
            "id": "categorize_doc",
            "title": "Dokument kategorisieren",
            "description": "Das System schlaegt Kategorien vor. Bestaetigen oder korrigieren Sie die Zuordnung.",
            "target": "/documents",
            "action_label": "Dokumente oeffnen",
            "icon": "folder",
        },
        {
            "id": "use_smart_search",
            "title": "Smart Search nutzen",
            "description": "Finden Sie Dokumente blitzschnell mit der intelligenten Suche. Nutzen Sie Cmd+K fuer den Schnellzugriff.",
            "target": "/search",
            "action_label": "Suche oeffnen",
            "icon": "search",
        },
        {
            "id": "review_corrections",
            "title": "OCR-Korrekturen pruefen",
            "description": "Pruefen Sie Dokumente mit niedriger Erkennungs-Konfidenz. Ihre Korrekturen verbessern das System.",
            "target": "/active-learning",
            "action_label": "Korrekturen oeffnen",
            "icon": "edit",
        },
    ],
    "admin": [
        {
            "id": "check_system_health",
            "title": "System-Status pruefen",
            "description": "Ueberblick ueber alle Systemkomponenten: OCR-Backends, Datenbank, Integrations-Status.",
            "target": "/admin/system",
            "action_label": "System-Status oeffnen",
            "icon": "activity",
        },
        {
            "id": "manage_users",
            "title": "Benutzer verwalten",
            "description": "Legen Sie neue Benutzer an und weisen Sie Rollen zu.",
            "target": "/admin/users",
            "action_label": "Benutzerverwaltung oeffnen",
            "icon": "users",
        },
        {
            "id": "configure_integrations",
            "title": "Integrationen konfigurieren",
            "description": "Richten Sie DATEV, Lexware, Banking und andere Integrationen ein.",
            "target": "/admin/integrations",
            "action_label": "Integrationen oeffnen",
            "icon": "plug",
        },
        {
            "id": "setup_feature_flags",
            "title": "Feature-Toggles konfigurieren",
            "description": "Aktivieren oder deaktivieren Sie Features fuer Ihr Unternehmen.",
            "target": "/admin/feature-toggles",
            "action_label": "Feature-Toggles oeffnen",
            "icon": "toggle-left",
        },
        {
            "id": "review_audit_log",
            "title": "Audit-Log pruefen",
            "description": "Ueberpruefen Sie alle Aktionen im System fuer Compliance und Nachvollziehbarkeit.",
            "target": "/admin/audit",
            "action_label": "Audit-Log oeffnen",
            "icon": "shield",
        },
    ],
}

# Kontextuelle Hilfe-Tooltips (Feature -> Tooltip)
CONTEXTUAL_HELP: Dict[str, Dict[str, str]] = {
    "smart_search": {
        "title": "Smart Search",
        "description": "Nutzen Sie Cmd+K (Mac) oder Strg+K (Windows) fuer den Schnellzugriff. Die Suche unterstuetzt Volltextsuche, Filter und Vorschlaege.",
    },
    "ocr_correction": {
        "title": "OCR-Korrektur",
        "description": "Klicken Sie auf ein erkanntes Feld um es zu korrigieren. Das System lernt aus Ihren Aenderungen und wird mit der Zeit genauer.",
    },
    "document_clustering": {
        "title": "Dokumenten-Clustering",
        "description": "Das System gruppiert aehnliche Dokumente automatisch. Akzeptieren oder aendern Sie Vorschlaege mit einem Klick.",
    },
    "anomaly_detection": {
        "title": "Anomalie-Erkennung",
        "description": "Das System warnt Sie automatisch bei verdaechtigen Mustern wie doppelten Rechnungen oder unueblichen Betraegen.",
    },
    "datev_export": {
        "title": "DATEV-Export",
        "description": "Exportieren Sie Belege und Buchungsdaten direkt im DATEV-Format. Der Export kann automatisch oder manuell erfolgen.",
    },
    "keyboard_shortcuts": {
        "title": "Tastaturkuerzel",
        "description": "Druecken Sie ? um alle verfuegbaren Tastaturkuerzel zu sehen. Cmd+K oeffnet die Schnellsuche.",
    },
}


class OnboardingService:
    """Service fuer Guided Onboarding und kontextuelle Hilfe."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def get_tour_for_role(self, role: str) -> List[Dict[str, str]]:
        """Tour-Schritte fuer eine bestimmte Rolle abrufen."""
        return ONBOARDING_TOURS.get(role, ONBOARDING_TOURS["sachbearbeitung"])

    async def get_user_progress(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Dict[str, object]:
        """Onboarding-Fortschritt eines Nutzers abrufen.

        Nutzt die User-Tabelle preferences JSONB-Feld fuer Speicherung.
        """
        from app.db.models import User

        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return {"completed_steps": [], "tour_completed": False}

        prefs = getattr(user, "preferences", None) or {}
        onboarding = prefs.get("onboarding", {})
        return {
            "completed_steps": onboarding.get("completed_steps", []),
            "tour_completed": onboarding.get("tour_completed", False),
            "started_at": onboarding.get("started_at"),
            "completed_at": onboarding.get("completed_at"),
        }

    async def mark_step_completed(
        self,
        user_id: uuid.UUID,
        step_id: str,
    ) -> Dict[str, object]:
        """Einen Tour-Schritt als abgeschlossen markieren."""
        from app.db.models import User

        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return {"success": False}

        prefs = getattr(user, "preferences", None) or {}
        onboarding = prefs.get("onboarding", {})
        completed = onboarding.get("completed_steps", [])

        if step_id not in completed:
            completed.append(step_id)

        onboarding["completed_steps"] = completed
        if not onboarding.get("started_at"):
            onboarding["started_at"] = datetime.utcnow().isoformat()

        prefs["onboarding"] = onboarding
        user.preferences = prefs
        await self.db.flush()

        logger.info(
            "onboarding_step_completed",
            user_id=str(user_id),
            step_id=step_id,
            total_completed=len(completed),
        )

        return {
            "success": True,
            "completed_steps": completed,
            "total_completed": len(completed),
        }

    async def complete_tour(
        self,
        user_id: uuid.UUID,
    ) -> Dict[str, object]:
        """Tour als komplett abgeschlossen markieren."""
        from app.db.models import User

        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return {"success": False}

        prefs = getattr(user, "preferences", None) or {}
        onboarding = prefs.get("onboarding", {})
        onboarding["tour_completed"] = True
        onboarding["completed_at"] = datetime.utcnow().isoformat()
        prefs["onboarding"] = onboarding
        user.preferences = prefs
        await self.db.flush()

        logger.info("onboarding_tour_completed", user_id=str(user_id))
        return {"success": True, "tour_completed": True}

    def get_contextual_help(self, feature: str) -> Optional[Dict[str, str]]:
        """Kontextuelle Hilfe fuer ein bestimmtes Feature."""
        return CONTEXTUAL_HELP.get(feature)

    def get_all_contextual_help(self) -> Dict[str, Dict[str, str]]:
        """Alle verfuegbaren Hilfe-Tooltips."""
        return CONTEXTUAL_HELP


def get_onboarding_service(db: AsyncSession) -> OnboardingService:
    """Factory fuer OnboardingService."""
    return OnboardingService(db)
