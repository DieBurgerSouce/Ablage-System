"""
DATEV Konstanten für Streckengeschäft / Dreiecksgeschäft

Kontenzuordnung basierend auf Rolle des deutschen Unternehmers:
- Zwischenhändler (Erlös): 8130 / 4130 → UStVA Kz. 42
- Letzter Abnehmer (Aufwand): 3553/5553 / 3553 → Steuerschlüssel 731
- Erster Lieferer (Erlös): 8125 / 4125 → UStVA Kz. 41
- Innergemeinschaftlicher Erwerb: 3425 / 5425 → UStVA Kz. 89
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DatevAccountMapping:
    """DATEV Kontenzuordnung für Streckengeschäfte"""
    role: str
    skr03_account: str
    skr04_account: str
    tax_code: Optional[str]
    ustva_kennzahl: str
    description: str
    am_function: Optional[str] = None  # Automatik-Funktion


# Vordefinierte DATEV-Zuordnungen
DATEV_DROP_SHIPMENT_ACCOUNTS: dict[str, DatevAccountMapping] = {
    "intermediate_revenue": DatevAccountMapping(
        role="intermediate_revenue",
        skr03_account="8130",
        skr04_account="4130",
        tax_code=None,  # Keine USt
        ustva_kennzahl="42",
        description="Zwischenhändler - Lieferungen des ersten Abnehmers bei igl. Dreiecksgeschäften §25b Abs. 2 UStG",
        am_function="AM 68000"  # Triggert ZM mit Dreiecksgeschäft-Kennzeichen
    ),
    "final_recipient_expense": DatevAccountMapping(
        role="final_recipient_expense",
        skr03_account="3553",  # Alternativ: 5553
        skr04_account="3553",
        tax_code="731",  # 19% USt auf 1788 + 19% VSt auf 1588 (neutralisierend)
        ustva_kennzahl="66+69",
        description="Letzter Abnehmer - Innergemeinschaftlicher Erwerb mit Reverse Charge"
    ),
    "first_supplier_revenue": DatevAccountMapping(
        role="first_supplier_revenue",
        skr03_account="8125",
        skr04_account="4125",
        tax_code=None,
        ustva_kennzahl="41",
        description="Erster Lieferer - Steuerfreie innergemeinschaftliche Lieferung"
    ),
    "ic_acquisition": DatevAccountMapping(
        role="ic_acquisition",
        skr03_account="3425",
        skr04_account="5425",
        tax_code=None,
        ustva_kennzahl="89",
        description="Innergemeinschaftlicher Erwerb"
    ),
}


# Steuerschlüssel für Dreiecksgeschäfte
DATEV_TAX_CODES = {
    "730": {
        "description": "Innergemeinschaftlicher Erwerb 19%",
        "vat_rate": 19.0,
        "ust_account": "1788",
        "vst_account": "1588",
    },
    "731": {
        "description": "Dreiecksgeschäft letzter Abnehmer 19%",
        "vat_rate": 19.0,
        "ust_account": "1788",
        "vst_account": "1588",
        "neutralizing": True,  # USt = VSt (neutralisierend)
    },
    "732": {
        "description": "Innergemeinschaftlicher Erwerb 7%",
        "vat_rate": 7.0,
        "ust_account": "1788",
        "vst_account": "1588",
    },
}


# UStVA-Kennzahlen für Streckengeschäfte
USTVA_KENNZAHLEN = {
    "41": "Innergemeinschaftliche Lieferungen an Abnehmer mit USt-IdNr.",
    "42": "Lieferungen des ersten Abnehmers bei innergemeinschaftlichen Dreiecksgeschäften",
    "66": "Steuer infolge Wechsels der Steuerschuldnerschaft",
    "69": "Im Inland steuerpflichtige sonstige Leistungen (Reverse Charge)",
    "89": "Innergemeinschaftliche Erwerbe nach § 1a Abs. 1 Nr. 2 UStG",
}


def get_datev_account(
    role: str,
    kontenrahmen: str = "03"
) -> Optional[str]:
    """
    Ermittelt das DATEV-Konto basierend auf Rolle und Kontenrahmen.
    
    Args:
        role: Rolle des Unternehmers (intermediate_revenue, final_recipient_expense, etc.)
        kontenrahmen: "03" für SKR03 oder "04" für SKR04
    
    Returns:
        Kontonummer oder None wenn nicht gefunden
    """
    mapping = DATEV_DROP_SHIPMENT_ACCOUNTS.get(role)
    if not mapping:
        return None
    
    if kontenrahmen == "03":
        return mapping.skr03_account
    elif kontenrahmen == "04":
        return mapping.skr04_account
    return None


def get_datev_tax_code(role: str) -> Optional[str]:
    """
    Ermittelt den DATEV-Steuerschlüssel basierend auf Rolle.
    
    Args:
        role: Rolle des Unternehmers
    
    Returns:
        Steuerschlüssel oder None
    """
    mapping = DATEV_DROP_SHIPMENT_ACCOUNTS.get(role)
    if not mapping:
        return None
    return mapping.tax_code


def format_vat_id_for_datev(vat_id: str) -> str:
    """
    Formatiert USt-IdNr. für DATEV-Export (Feld AN, Spalte 40).
    Format: LLXXXXXXXXXXX (2-stelliges Länderkürzel + max. 13-stellige Nummer)
    
    Args:
        vat_id: USt-IdNr. in beliebigem Format
    
    Returns:
        Formatierte USt-IdNr. für DATEV
    """
    # Entferne Leerzeichen und Sonderzeichen
    cleaned = "".join(c for c in vat_id.upper() if c.isalnum())
    
    # Extrahiere Länderkürzel (erste 2 Buchstaben)
    country_code = ""
    number = ""
    
    for i, char in enumerate(cleaned):
        if char.isalpha() and len(country_code) < 2:
            country_code += char
        else:
            number = cleaned[i:]
            break
    
    return f"{country_code}{number}"


# EU-Länder für Dreiecksgeschäft-Erkennung
EU_MEMBER_STATES = {
    "AT": "Österreich",
    "BE": "Belgien",
    "BG": "Bulgarien",
    "CY": "Zypern",
    "CZ": "Tschechien",
    "DE": "Deutschland",
    "DK": "Dänemark",
    "EE": "Estland",
    "EL": "Griechenland",  # Alternativ: GR
    "ES": "Spanien",
    "FI": "Finnland",
    "FR": "Frankreich",
    "HR": "Kroatien",
    "HU": "Ungarn",
    "IE": "Irland",
    "IT": "Italien",
    "LT": "Litauen",
    "LU": "Luxemburg",
    "LV": "Lettland",
    "MT": "Malta",
    "NL": "Niederlande",
    "PL": "Polen",
    "PT": "Portugal",
    "RO": "Rumänien",
    "SE": "Schweden",
    "SI": "Slowenien",
    "SK": "Slowakei",
}


def is_eu_vat_id(vat_id: str) -> bool:
    """Prüft ob USt-IdNr. aus EU-Mitgliedstaat stammt."""
    if not vat_id or len(vat_id) < 2:
        return False
    country_code = vat_id[:2].upper()
    return country_code in EU_MEMBER_STATES


def extract_country_from_vat_id(vat_id: str) -> Optional[str]:
    """Extrahiert Ländercode aus USt-IdNr."""
    if not vat_id or len(vat_id) < 2:
        return None
    return vat_id[:2].upper()
