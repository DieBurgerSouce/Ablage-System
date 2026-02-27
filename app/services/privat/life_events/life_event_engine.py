"""Life Event Engine Service.

Proaktiver Lebensberater: Umzug, Heirat, Kind, Jobwechsel
-> automatische Checklisten und Empfehlungen.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LifeEvent

logger = structlog.get_logger(__name__)

# Event-Typ Definitionen
EVENT_TYPES: dict[str, dict[str, str]] = {
    "umzug": {
        "label": "Umzug",
        "description": "Wohnortwechsel mit allen administrativen Aufgaben",
        "icon": "home",
    },
    "heirat": {
        "label": "Heirat",
        "description": "Eheschließung und zugehoerige Dokumente",
        "icon": "heart",
    },
    "kind": {
        "label": "Geburt eines Kindes",
        "description": "Familienzuwachs mit Elterngeld, Kindergeld etc.",
        "icon": "baby",
    },
    "jobwechsel": {
        "label": "Jobwechsel",
        "description": "Neuer Arbeitgeber oder Selbstaendigkeit",
        "icon": "briefcase",
    },
    "ruhestand": {
        "label": "Ruhestand",
        "description": "Übergang in den Ruhestand",
        "icon": "sunset",
    },
    "todesfall": {
        "label": "Todesfall",
        "description": "Trauerfall in der Familie",
        "icon": "candle",
    },
    "immobilienkauf": {
        "label": "Immobilienkauf",
        "description": "Kauf einer Immobilie",
        "icon": "building",
    },
    "scheidung": {
        "label": "Scheidung",
        "description": "Trennung und Scheidungsverfahren",
        "icon": "split",
    },
}


def _get_checklist_template(event_type: str) -> list[dict[str, object]]:
    """Gibt die Checkliste für einen Event-Typ zurück."""
    templates: dict[str, list[dict[str, object]]] = {
        "umzug": [
            {"id": "ummeldung", "label": "Ummeldung beim Einwohnermeldeamt", "category": "behoerden", "priority": "high", "done": False},
            {"id": "post_nachsendung", "label": "Nachsendeauftrag bei der Post", "category": "post", "priority": "high", "done": False},
            {"id": "bank_adresse", "label": "Adressänderung bei der Bank", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "versicherungen", "label": "Versicherungen informieren", "category": "versicherung", "priority": "medium", "done": False},
            {"id": "arbeitgeber", "label": "Arbeitgeber informieren", "category": "arbeit", "priority": "medium", "done": False},
            {"id": "finanzamt", "label": "Finanzamt informieren", "category": "behoerden", "priority": "medium", "done": False},
            {"id": "kfz_ummeldung", "label": "KFZ-Ummeldung", "category": "behoerden", "priority": "low", "done": False},
            {"id": "gez", "label": "Rundfunkbeitrag ummelden", "category": "behoerden", "priority": "low", "done": False},
        ],
        "heirat": [
            {"id": "standesamt", "label": "Termin beim Standesamt", "category": "behoerden", "priority": "high", "done": False},
            {"id": "steuerklasse", "label": "Steuerklasse ändern", "category": "finanzen", "priority": "high", "done": False},
            {"id": "namensänderung", "label": "Namensänderung (falls gewünscht)", "category": "behoerden", "priority": "medium", "done": False},
            {"id": "versicherung_partner", "label": "Partner in Versicherungen aufnehmen", "category": "versicherung", "priority": "medium", "done": False},
            {"id": "testament", "label": "Testament erstellen/aktualisieren", "category": "recht", "priority": "medium", "done": False},
            {"id": "bank_gemeinschaftskonto", "label": "Gemeinschaftskonto eröffnen", "category": "finanzen", "priority": "low", "done": False},
        ],
        "kind": [
            {"id": "geburtsurkunde", "label": "Geburtsurkunde beantragen", "category": "behoerden", "priority": "high", "done": False},
            {"id": "elterngeld", "label": "Elterngeld beantragen", "category": "finanzen", "priority": "high", "done": False},
            {"id": "kindergeld", "label": "Kindergeld beantragen", "category": "finanzen", "priority": "high", "done": False},
            {"id": "krankenversicherung", "label": "Kind bei Krankenversicherung anmelden", "category": "versicherung", "priority": "high", "done": False},
            {"id": "steuer_kinderfreibetrag", "label": "Kinderfreibetrag eintragen lassen", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "elternzeit", "label": "Elternzeit beim Arbeitgeber beantragen", "category": "arbeit", "priority": "high", "done": False},
            {"id": "sorgerecht", "label": "Sorgerechterklärung (unverheiratet)", "category": "recht", "priority": "medium", "done": False},
        ],
        "jobwechsel": [
            {"id": "arbeitsvertrag", "label": "Neuen Arbeitsvertrag prüfen", "category": "arbeit", "priority": "high", "done": False},
            {"id": "kündigung", "label": "Kündigungsfristen beachten", "category": "arbeit", "priority": "high", "done": False},
            {"id": "steuer_lohnsteuerkarte", "label": "Lohnsteuerkarte aktualisieren", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "altersvorsorge", "label": "Betriebliche Altersvorsorge prüfen", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "arbeitszeugnis", "label": "Arbeitszeugnis anfordern", "category": "arbeit", "priority": "medium", "done": False},
            {"id": "versicherungen_prüfen", "label": "Versicherungen prüfen/anpassen", "category": "versicherung", "priority": "low", "done": False},
        ],
        "ruhestand": [
            {"id": "rentenantrag", "label": "Rentenantrag stellen", "category": "behoerden", "priority": "high", "done": False},
            {"id": "krankenversicherung_rente", "label": "Krankenversicherung im Alter klaeren", "category": "versicherung", "priority": "high", "done": False},
            {"id": "altersvorsorge_auszahlung", "label": "Betriebliche Altersvorsorge abwickeln", "category": "finanzen", "priority": "high", "done": False},
            {"id": "steuererklärung", "label": "Steuererklärung als Rentner planen", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "testament_aktualisieren", "label": "Testament aktualisieren", "category": "recht", "priority": "medium", "done": False},
        ],
        "todesfall": [
            {"id": "sterbeurkunde", "label": "Sterbeurkunde beantragen", "category": "behoerden", "priority": "high", "done": False},
            {"id": "erbschein", "label": "Erbschein beantragen", "category": "recht", "priority": "high", "done": False},
            {"id": "versicherungen_melden", "label": "Versicherungen informieren", "category": "versicherung", "priority": "high", "done": False},
            {"id": "bank_informieren", "label": "Bank informieren", "category": "finanzen", "priority": "high", "done": False},
            {"id": "kündigungen", "label": "Verträge kündigen", "category": "verträge", "priority": "medium", "done": False},
            {"id": "rente_witwe", "label": "Witwenrente beantragen", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "steuererklarung_verstorbener", "label": "Steuererklärung des Verstorbenen", "category": "finanzen", "priority": "medium", "done": False},
        ],
        "immobilienkauf": [
            {"id": "finanzierung", "label": "Finanzierung sicherstellen", "category": "finanzen", "priority": "high", "done": False},
            {"id": "notar", "label": "Notartermin vereinbaren", "category": "recht", "priority": "high", "done": False},
            {"id": "grundbuch", "label": "Grundbucheintragung prüfen", "category": "behoerden", "priority": "high", "done": False},
            {"id": "grunderwerbsteuer", "label": "Grunderwerbsteuer einplanen", "category": "finanzen", "priority": "high", "done": False},
            {"id": "versicherungen_immobilie", "label": "Gebaeudeversicherung abschließen", "category": "versicherung", "priority": "medium", "done": False},
            {"id": "umzug_planen", "label": "Umzug planen", "category": "organisation", "priority": "medium", "done": False},
            {"id": "handwerker", "label": "Handwerkerkosten steuerlich absetzen", "category": "finanzen", "priority": "low", "done": False},
        ],
        "scheidung": [
            {"id": "anwalt", "label": "Scheidungsanwalt beauftragen", "category": "recht", "priority": "high", "done": False},
            {"id": "trennungsjahr", "label": "Trennungsjahr dokumentieren", "category": "recht", "priority": "high", "done": False},
            {"id": "finanzen_trennen", "label": "Finanzen trennen", "category": "finanzen", "priority": "high", "done": False},
            {"id": "steuerklasse_ändern", "label": "Steuerklasse ändern", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "versicherungen_ändern", "label": "Versicherungen anpassen", "category": "versicherung", "priority": "medium", "done": False},
            {"id": "unterhalt", "label": "Unterhalt berechnen", "category": "finanzen", "priority": "medium", "done": False},
            {"id": "sorgerecht_kinder", "label": "Sorgerecht für Kinder regeln", "category": "recht", "priority": "high", "done": False},
        ],
    }
    return templates.get(event_type, [])


def _get_recommendations(event_type: str) -> list[dict[str, str]]:
    """Gibt Empfehlungen für einen Event-Typ zurück."""
    recommendations: dict[str, list[dict[str, str]]] = {
        "umzug": [
            {"title": "Steuerliche Vorteile", "text": "Umzugskosten können steuerlich absetzbar sein (beruflich bedingt)."},
            {"title": "Kündigungsfristen", "text": "Mietvertrag-Kündigungsfrist beachten (meist 3 Monate)."},
        ],
        "heirat": [
            {"title": "Steuerklassenwahl", "text": "Kombination III/V oder IV/IV prüfen für optimale Steuerbelastung."},
            {"title": "Zusammenveranlagung", "text": "Ehegattensplitting kann erhebliche Steuervorteile bringen."},
        ],
        "kind": [
            {"title": "Elterngeld Plus", "text": "ElterngeldPlus ermöglicht längere Bezugsdauer bei Teilzeitarbeit."},
            {"title": "Kinderzulage Riester", "text": "300 EUR Kinderzulage pro Jahr bei Riester-Vertrag möglich."},
        ],
        "jobwechsel": [
            {"title": "Sperrzeit vermeiden", "text": "Bei Eigenkündigung droht 12 Wochen ALG-Sperrzeit."},
            {"title": "Wettbewerbsverbot", "text": "Nachvertragliches Wettbewerbsverbot und Karenzentschaedigung prüfen."},
        ],
    }
    return recommendations.get(event_type, [])


def _estimate_financial_impact(event_type: str) -> dict[str, object]:
    """Schätzt die finanziellen Auswirkungen eines Events."""
    impacts: dict[str, dict[str, object]] = {
        "umzug": {
            "estimated_cost_min": 500,
            "estimated_cost_max": 5000,
            "potential_savings": "Umzugskosten steuerlich absetzbar bei beruflichem Anlass",
            "recurring_changes": "Mietkosten können sich ändern",
        },
        "heirat": {
            "estimated_cost_min": 200,
            "estimated_cost_max": 1000,
            "potential_savings": "Ehegattensplitting: bis zu mehrere Tausend EUR/Jahr",
            "recurring_changes": "Steuerklassenänderung wirkt sich monatlich aus",
        },
        "kind": {
            "estimated_cost_min": 0,
            "estimated_cost_max": 500,
            "potential_savings": "Kindergeld: 250 EUR/Monat, Elterngeld: bis 1800 EUR/Monat",
            "recurring_changes": "Laufende Kosten ca. 600-800 EUR/Monat",
        },
        "jobwechsel": {
            "estimated_cost_min": 0,
            "estimated_cost_max": 200,
            "potential_savings": "Gehaltsverhandlung nutzen",
            "recurring_changes": "Neues Gehalt, ggf. andere Benefits",
        },
        "immobilienkauf": {
            "estimated_cost_min": 10000,
            "estimated_cost_max": 50000,
            "potential_savings": "Eigenheimzulage, Handwerkerkosten absetzbar",
            "recurring_changes": "Kreditraten statt Miete",
        },
    }
    return impacts.get(event_type, {
        "estimated_cost_min": 0,
        "estimated_cost_max": 0,
        "potential_savings": "Keine Schätzung verfügbar",
        "recurring_changes": "Individuell zu prüfen",
    })


class LifeEventEngine:
    """Proaktiver Lebensberater-Service."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_life_event(
        self,
        user_id: UUID,
        company_id: UUID,
        event_type: str,
        event_date: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> LifeEvent:
        """Erstellt ein neues Lebensereignis mit Checkliste.

        Args:
            user_id: Benutzer-ID
            company_id: Mandant (RLS)
            event_type: Typ des Ereignisses
            event_date: Datum des Ereignisses
            notes: Optionale Notizen

        Returns:
            Erstelltes LifeEvent
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unbekannter Event-Typ: {event_type}")

        checklist = _get_checklist_template(event_type)
        recommendations = _get_recommendations(event_type)
        financial_impact = _estimate_financial_impact(event_type)

        # Use notes if provided, otherwise use default description
        description_text = notes if notes else EVENT_TYPES[event_type]["description"]

        life_event = LifeEvent(
            user_id=user_id,
            company_id=company_id,
            event_type=event_type,
            title=EVENT_TYPES[event_type]["label"],
            description=description_text,
            event_date=event_date.date() if event_date else datetime.utcnow().date(),
            detection_source="manual",
            status="confirmed",
            checklist=checklist,
            recommendations=recommendations,
            financial_impact=financial_impact,
        )
        self.db.add(life_event)
        await self.db.flush()

        logger.info(
            "life_event_created",
            event_id=str(life_event.id),
            event_type=event_type,
            checklist_items=len(checklist),
        )
        return life_event

    async def get_life_events(
        self,
        user_id: UUID,
        company_id: UUID,
        status_filter: Optional[str] = None,
    ) -> Sequence[LifeEvent]:
        """Holt alle Lebensereignisse eines Benutzers."""
        query = select(LifeEvent).where(
            and_(
                LifeEvent.user_id == user_id,
                LifeEvent.company_id == company_id,
            )
        )
        if status_filter:
            query = query.where(LifeEvent.status == status_filter)
        query = query.order_by(desc(LifeEvent.event_date))

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_life_event(
        self,
        event_id: UUID,
        company_id: UUID,
    ) -> Optional[LifeEvent]:
        """Holt ein einzelnes Lebensereignis."""
        query = select(LifeEvent).where(
            and_(
                LifeEvent.id == event_id,
                LifeEvent.company_id == company_id,
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_checklist_item(
        self,
        event_id: UUID,
        company_id: UUID,
        item_id: str,
        done: bool,
    ) -> Optional[LifeEvent]:
        """Markiert einen Checklist-Eintrag als erledigt/offen."""
        event = await self.get_life_event(event_id, company_id)
        if not event:
            return None

        checklist = list(event.checklist or [])
        for item in checklist:
            if item.get("id") == item_id:
                item["done"] = done
                if done:
                    item["completed_at"] = datetime.utcnow().isoformat()
                break

        event.checklist = checklist

        # Prüfen ob alle Items erledigt
        all_done = all(item.get("done", False) for item in checklist)
        if all_done:
            event.status = "completed"

        await self.db.flush()
        return event

    async def complete_life_event(
        self,
        event_id: UUID,
        company_id: UUID,
    ) -> Optional[LifeEvent]:
        """Markiert ein Lebensereignis als abgeschlossen."""
        event = await self.get_life_event(event_id, company_id)
        if not event:
            return None

        event.status = "completed"
        event.completed_at = datetime.utcnow()
        await self.db.flush()
        return event

    async def get_event_types(self) -> dict[str, dict[str, str]]:
        """Gibt alle verfügbaren Event-Typen zurück."""
        return EVENT_TYPES

    async def get_active_events_count(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> int:
        """Zaehlt aktive Lebensereignisse."""
        query = select(func.count(LifeEvent.id)).where(
            and_(
                LifeEvent.user_id == user_id,
                LifeEvent.company_id == company_id,
                LifeEvent.status.in_(["confirmed", "in_progress"]),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one()
