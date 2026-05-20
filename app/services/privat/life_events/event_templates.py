"""
Life Event Templates.

Vordefinierte Templates für Lebensereignisse mit Checklisten und Empfehlungen.
"""

from typing import Any, Dict, List

# ============================================================================
# LIFE EVENT TEMPLATES
# ============================================================================

LIFE_EVENT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "umzug": {
        "title": "Umzug",
        "checklist": [
            {"id": "addr_change", "task": "Adressänderung bei Behörden", "category": "behoerden"},
            {"id": "bank_notify", "task": "Bank über neue Adresse informieren", "category": "finanzen"},
            {"id": "insurance_update", "task": "Versicherungen aktualisieren", "category": "versicherung"},
            {"id": "employer_notify", "task": "Arbeitgeber informieren", "category": "arbeit"},
            {"id": "tax_office", "task": "Finanzamt informieren", "category": "steuer"},
            {"id": "gez_update", "task": "Rundfunkbeitrag ummelden", "category": "behoerden"},
            {"id": "post_redirect", "task": "Nachsendeauftrag einrichten", "category": "post"},
            {"id": "utilities", "task": "Strom/Gas/Wasser anmelden", "category": "utilities"},
            {"id": "internet", "task": "Internet/Telefon ummelden", "category": "telekom"},
        ],
        "financial_impact": {"estimated_cost": "500-3000 EUR", "tax_deductible": True},
        "documents_needed": ["Mietvertrag", "Personalausweis", "Meldebescheinigung"],
        "deadlines": {"addr_change": "14 Tage nach Umzug"},
    },
    "heirat": {
        "title": "Heirat",
        "checklist": [
            {"id": "standesamt", "task": "Anmeldung beim Standesamt", "category": "behoerden"},
            {"id": "name_change", "task": "Namensänderung (optional)", "category": "behoerden"},
            {"id": "tax_class", "task": "Steuerklasse ändern", "category": "steuer"},
            {"id": "insurance", "task": "Krankenversicherung prüfen", "category": "versicherung"},
            {"id": "testament", "task": "Testament erstellen/aktualisieren", "category": "recht"},
            {"id": "bank_update", "task": "Bankdaten aktualisieren", "category": "finanzen"},
            {"id": "employer", "task": "Arbeitgeber informieren", "category": "arbeit"},
        ],
        "financial_impact": {"estimated_cost": "100-500 EUR", "tax_deductible": False},
        "documents_needed": ["Geburtsurkunde", "Personalausweis", "Ehefähigkeitszeugnis"],
        "deadlines": {"standesamt": "6 Monate vor Hochzeit anmelden"},
    },
    "kind": {
        "title": "Geburt eines Kindes",
        "checklist": [
            {"id": "birth_cert", "task": "Geburtsurkunde beantragen", "category": "behoerden"},
            {"id": "elterngeld", "task": "Elterngeld beantragen", "category": "finanzen"},
            {"id": "kindergeld", "task": "Kindergeld beantragen", "category": "finanzen"},
            {"id": "insurance", "task": "Krankenversicherung fürs Kind", "category": "versicherung"},
            {"id": "tax_class", "task": "Steuerklasse prüfen", "category": "steuer"},
            {"id": "kita", "task": "Kita-Platz anmelden", "category": "betreuung"},
            {"id": "parental_leave", "task": "Elternzeit beim Arbeitgeber beantragen", "category": "arbeit"},
        ],
        "financial_impact": {"estimated_cost": "0 EUR (staatliche Leistungen)", "tax_deductible": True},
        "documents_needed": ["Geburtsurkunde", "Personalausweis", "Einkommensnachweise"],
        "deadlines": {"birth_cert": "7 Tage nach Geburt", "elterngeld": "Innerhalb 3 Monate"},
    },
    "jobwechsel": {
        "title": "Jobwechsel",
        "checklist": [
            {"id": "resignation", "task": "Kündigung einreichen", "category": "arbeit"},
            {"id": "zeugnis", "task": "Arbeitszeugnis anfordern", "category": "arbeit"},
            {"id": "insurance", "task": "Krankenversicherung prüfen", "category": "versicherung"},
            {"id": "tax_card", "task": "Lohnsteuerkarte einreichen", "category": "steuer"},
            {"id": "pension", "task": "Betriebliche Altersvorsorge klären", "category": "finanzen"},
            {"id": "unemployment", "task": "Bei Arbeitsagentur melden (falls Lücke)", "category": "behoerden"},
        ],
        "financial_impact": {"estimated_cost": "0 EUR", "tax_deductible": False},
        "documents_needed": ["Kündigungsbestätigung", "Arbeitsvertrag (neu)", "Lohnsteuerkarte"],
        "deadlines": {"unemployment": "3 Monate vor Vertragsende melden"},
    },
    "ruhestand": {
        "title": "Ruhestand",
        "checklist": [
            {"id": "rentenantrag", "task": "Rentenantrag stellen", "category": "finanzen"},
            {"id": "insurance", "task": "Krankenversicherung klären", "category": "versicherung"},
            {"id": "tax_class", "task": "Steuerklasse ändern", "category": "steuer"},
            {"id": "pension", "task": "Betriebliche Altersvorsorge auszahlen", "category": "finanzen"},
            {"id": "testament", "task": "Testament aktualisieren", "category": "recht"},
        ],
        "financial_impact": {"estimated_cost": "0 EUR", "tax_deductible": False},
        "documents_needed": ["Versicherungsnummer", "Personalausweis", "Arbeitsbescheinigungen"],
        "deadlines": {"rentenantrag": "3 Monate vor Rentenbeginn"},
    },
    "immobilienkauf": {
        "title": "Immobilienkauf",
        "checklist": [
            {"id": "notary", "task": "Notartermin vereinbaren", "category": "recht"},
            {"id": "financing", "task": "Finanzierung sichern", "category": "finanzen"},
            {"id": "insurance", "task": "Gebäudeversicherung abschließen", "category": "versicherung"},
            {"id": "grundsteuer", "task": "Grundsteuer anmelden", "category": "steuer"},
            {"id": "utilities", "task": "Strom/Gas/Wasser anmelden", "category": "utilities"},
            {"id": "renovation", "task": "Renovierung planen (optional)", "category": "wohnen"},
        ],
        "financial_impact": {"estimated_cost": "5000-20000 EUR (Nebenkosten)", "tax_deductible": True},
        "documents_needed": ["Kaufvertrag", "Grundbuchauszug", "Finanzierungsbestätigung"],
        "deadlines": {"grundsteuer": "Innerhalb 2 Jahre nach Kauf"},
    },
    "scheidung": {
        "title": "Scheidung",
        "checklist": [
            {"id": "lawyer", "task": "Anwalt konsultieren", "category": "recht"},
            {"id": "separation", "task": "Trennungsjahr dokumentieren", "category": "recht"},
            {"id": "tax_class", "task": "Steuerklasse ändern", "category": "steuer"},
            {"id": "insurance", "task": "Krankenversicherung prüfen", "category": "versicherung"},
            {"id": "pension_split", "task": "Versorgungsausgleich klären", "category": "finanzen"},
            {"id": "testament", "task": "Testament aktualisieren", "category": "recht"},
        ],
        "financial_impact": {"estimated_cost": "1000-5000 EUR", "tax_deductible": False},
        "documents_needed": ["Heiratsurkunde", "Einkommensnachweise", "Vermögensaufstellung"],
        "deadlines": {"separation": "1 Jahr Trennungszeit erforderlich"},
    },
}


def get_template(event_type: str) -> Dict[str, Any]:
    """
    Gibt Template für Event-Typ zurück.

    Args:
        event_type: Event-Typ (umzug, heirat, etc.)

    Returns:
        Template-Dict

    Raises:
        ValueError: Event-Typ nicht gefunden
    """
    if event_type not in LIFE_EVENT_TEMPLATES:
        raise ValueError(f"Event-Typ '{event_type}' nicht gefunden")

    return LIFE_EVENT_TEMPLATES[event_type]


def get_available_event_types() -> List[str]:
    """
    Gibt verfügbare Event-Typen zurück.

    Returns:
        Liste von Event-Typ-Keys
    """
    return list(LIFE_EVENT_TEMPLATES.keys())
