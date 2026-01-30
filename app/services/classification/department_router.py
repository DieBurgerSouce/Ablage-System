# -*- coding: utf-8 -*-
"""
Department Router Service.

Routet Dokumente zur zustaendigen Abteilung basierend auf:
- Dokumenttyp
- Inhalt und Keywords
- Geschaeftspartner-Kontext
- Betragsschwellen

Abteilungen:
- BUCHHALTUNG: Rechnungen, Gutschriften, Kontoauszuege
- EINKAUF: Bestellungen, Lieferscheine, Angebote (eingehend)
- VERTRIEB: Angebote (ausgehend), Auftraege, Kundenkorrespondenz
- HR: Arbeitsvertraege, Lohnabrechnungen, Bewerbungen
- GESCHAEFTSFUEHRUNG: Hohe Betraege, Vertraege, strategische Dokumente
- IT: Technische Dokumente, Lizenzen, Wartungsvertraege
- RECHT: Vertraege, Mahnungen, rechtliche Korrespondenz

Feinpoliert und durchdacht.
"""

import re
import structlog
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Set

logger = structlog.get_logger(__name__)


class Department(str, Enum):
    """Abteilungen fuer Dokumenten-Routing."""
    BUCHHALTUNG = "buchhaltung"
    EINKAUF = "einkauf"
    VERTRIEB = "vertrieb"
    HR = "hr"
    GESCHAEFTSFUEHRUNG = "geschaeftsfuehrung"
    IT = "it"
    RECHT = "recht"
    ALLGEMEIN = "allgemein"  # Fallback


@dataclass
class DepartmentRoutingResult:
    """Ergebnis des Abteilungs-Routings."""
    primary_department: Department
    confidence: float
    secondary_departments: List[Department]
    matched_indicators: List[str]
    reason: str
    requires_cfo_approval: bool  # Fuer hohe Betraege


# =============================================================================
# DEPARTMENT CONFIGURATION
# =============================================================================

@dataclass
class DepartmentConfig:
    """Konfiguration fuer eine Abteilung."""
    department: Department
    document_types: Set[str]
    primary_keywords: Set[str]
    secondary_keywords: Set[str]
    amount_threshold: Optional[Decimal]  # Mindestbetrag fuer Routing
    amount_ceiling: Optional[Decimal]  # Max-Betrag ohne Eskalation


BUCHHALTUNG_CONFIG = DepartmentConfig(
    department=Department.BUCHHALTUNG,
    document_types={
        "invoice", "rechnung", "credit_note", "gutschrift",
        "bank_statement", "kontoauszug", "receipt", "quittung",
        "dunning", "mahnung", "tax_document", "steuerbescheid",
    },
    primary_keywords={
        "rechnung", "rechnungsnummer", "buchung", "kontierung",
        "mwst", "mehrwertsteuer", "umsatzsteuer", "ust-id",
        "zahlungsziel", "skonto", "ueberweisung", "lastschrift",
        "gutschrift", "kontoauszug", "saldo", "buchungskreis",
        "debitoren", "kreditoren", "sachkonto", "kostenstelle",
    },
    secondary_keywords={
        "bank", "iban", "bic", "zahlung", "betrag", "netto", "brutto",
        "steuersatz", "vorsteuer", "finanzamt", "steuerberater",
        "jahresabschluss", "bilanz", "guv", "kontenrahmen",
    },
    amount_threshold=None,
    amount_ceiling=Decimal("50000"),  # > 50k geht zur GF
)

EINKAUF_CONFIG = DepartmentConfig(
    department=Department.EINKAUF,
    document_types={
        "purchase_order", "bestellung", "order", "auftrag",
        "delivery_note", "lieferschein", "offer", "angebot",
    },
    primary_keywords={
        "bestellung", "bestellnummer", "einkauf", "beschaffung",
        "lieferant", "lieferung", "lieferschein", "wareneingang",
        "artikelnummer", "materialnummer", "stueckliste",
        "rahmenvertrag", "konditionen", "einkaufskonditionen",
    },
    secondary_keywords={
        "menge", "einzelpreis", "liefertermin", "versand",
        "tracking", "incoterms", "fracht", "palette",
        "qualitaet", "reklamation", "retoure", "ruecksendung",
    },
    amount_threshold=None,
    amount_ceiling=Decimal("25000"),  # > 25k braucht GF-Freigabe
)

VERTRIEB_CONFIG = DepartmentConfig(
    department=Department.VERTRIEB,
    document_types={
        "offer", "angebot",  # Ausgehende Angebote
        "order_confirmation", "auftragsbestaetigung",
    },
    primary_keywords={
        "kunde", "kundennummer", "kundenauftrag", "vertrieb",
        "verkauf", "angebot", "offerte", "provision",
        "rabatt", "nachlass", "sonderkonditionen",
        "kundenprojekt", "opportunity", "lead",
    },
    secondary_keywords={
        "umsatz", "marge", "deckungsbeitrag", "preisliste",
        "produktkatalog", "kundenservice", "support",
        "reklamation", "beschwerde", "anfrage",
    },
    amount_threshold=None,
    amount_ceiling=Decimal("100000"),  # > 100k geht zur GF
)

HR_CONFIG = DepartmentConfig(
    department=Department.HR,
    document_types={
        "employment_contract", "arbeitsvertrag",
        "payslip", "lohnabrechnung", "gehaltsabrechnung",
        "application", "bewerbung",
    },
    primary_keywords={
        "mitarbeiter", "personal", "gehalt", "lohn", "arbeitnehmer",
        "arbeitsvertrag", "kuendigung", "abmahnung", "zeugnis",
        "bewerbung", "einstellung", "entlassung", "urlaub",
        "krankmeldung", "arbeitszeit", "ueberstunden",
        "sozialversicherung", "lohnsteuer", "betriebsrat",
    },
    secondary_keywords={
        "befristung", "probezeit", "verguetung", "bonus",
        "zielvereinbarung", "leistungsbeurteilung",
        "weiterbildung", "schulung", "homeoffice", "teilzeit",
    },
    amount_threshold=None,
    amount_ceiling=None,  # Keine Betrags-Eskalation fuer HR
)

GESCHAEFTSFUEHRUNG_CONFIG = DepartmentConfig(
    department=Department.GESCHAEFTSFUEHRUNG,
    document_types={
        "contract", "vertrag",  # Wichtige Vertraege
        "board_resolution", "gesellschafterbeschluss",
        "annual_report", "jahresbericht",
    },
    primary_keywords={
        "geschaeftsfuehrung", "vorstand", "aufsichtsrat",
        "gesellschafter", "strategie", "investment",
        "akquisition", "fusion", "uebernahme", "beteiligung",
        "geschaeftsplan", "budget", "forecast", "prognose",
    },
    secondary_keywords={
        "vertraulich", "streng vertraulich", "geheim",
        "handelsregister", "notar", "prokura", "vollmacht",
    },
    amount_threshold=Decimal("50000"),  # Ab 50k direkt zur GF
    amount_ceiling=None,
)

IT_CONFIG = DepartmentConfig(
    department=Department.IT,
    document_types={
        "license", "lizenz", "software_contract",
        "service_agreement", "wartungsvertrag",
    },
    primary_keywords={
        "software", "hardware", "lizenz", "it", "edv",
        "server", "cloud", "saas", "hosting", "domain",
        "datenschutz", "backup", "security", "firewall",
        "support", "wartung", "update", "patch",
    },
    secondary_keywords={
        "api", "integration", "schnittstelle", "datenbank",
        "netzwerk", "vpn", "zertifikat", "ssl", "https",
        "gdpr", "dsgvo", "datensicherung", "verschluesselung",
    },
    amount_threshold=None,
    amount_ceiling=Decimal("10000"),
)

RECHT_CONFIG = DepartmentConfig(
    department=Department.RECHT,
    document_types={
        "contract", "vertrag",
        "legal_notice", "abmahnung",
        "court_document", "gerichtsdokument",
    },
    primary_keywords={
        "anwalt", "rechtsanwalt", "kanzlei", "gericht",
        "klage", "verteidigung", "verfahren", "urteil",
        "vergleich", "vollstreckung", "zwangsvollstreckung",
        "schadensersatz", "haftung", "gewaehrleistung",
        "marke", "patent", "urheberrecht", "lizenz",
    },
    secondary_keywords={
        "paragraph", "gesetz", "verordnung", "richtlinie",
        "compliance", "regulierung", "aufsicht",
        "widerspruch", "einspruch", "berufung", "revision",
    },
    amount_threshold=None,
    amount_ceiling=Decimal("5000"),  # Rechtliche Sachen schnell eskalieren
)

# Alle Konfigurationen (Reihenfolge = Prioritaet)
DEPARTMENT_CONFIGS = [
    RECHT_CONFIG,  # Rechtliche Dokumente haben Vorrang
    GESCHAEFTSFUEHRUNG_CONFIG,
    HR_CONFIG,
    IT_CONFIG,
    EINKAUF_CONFIG,
    VERTRIEB_CONFIG,
    BUCHHALTUNG_CONFIG,  # Buchhaltung als Fallback fuer Rechnungen
]


class DepartmentRouter:
    """
    Routet Dokumente zur zustaendigen Abteilung.

    Performance: < 10ms pro Dokument (rein regelbasiert)
    """

    def __init__(self) -> None:
        """Initialisiere den Department Router."""
        self.configs = DEPARTMENT_CONFIGS
        self._stats = {
            "total_routings": 0,
            "by_department": {dept.value: 0 for dept in Department},
        }

    def route(
        self,
        text: str,
        document_type: Optional[str] = None,
        amount: Optional[Decimal] = None,
        is_incoming: bool = True,
    ) -> DepartmentRoutingResult:
        """
        Route ein Dokument zur zustaendigen Abteilung.

        Args:
            text: OCR-Text des Dokuments
            document_type: Optionaler Dokumenttyp
            amount: Optionaler Betrag fuer Schwellenwert-Pruefung
            is_incoming: True fuer eingehende, False fuer ausgehende Dokumente

        Returns:
            DepartmentRoutingResult mit Abteilung und Details
        """
        if not text or not text.strip():
            return DepartmentRoutingResult(
                primary_department=Department.ALLGEMEIN,
                confidence=0.3,
                secondary_departments=[],
                matched_indicators=[],
                reason="Kein Text zur Analyse vorhanden",
                requires_cfo_approval=False,
            )

        self._stats["total_routings"] += 1

        # Text normalisieren
        normalized_text = self._normalize_text(text)

        # Scores fuer alle Abteilungen berechnen
        scores: Dict[Department, tuple] = {}

        for config in self.configs:
            score, matches = self._calculate_score(
                normalized_text=normalized_text,
                document_type=document_type,
                amount=amount,
                config=config,
            )
            if score > 0:
                scores[config.department] = (score, matches)

        # Sonderfall: Angebote (Richtung beachten)
        if document_type and "angebot" in document_type.lower() or "offer" in document_type.lower():
            if is_incoming:
                # Eingehende Angebote -> Einkauf
                if Department.EINKAUF in scores:
                    scores[Department.EINKAUF] = (scores[Department.EINKAUF][0] + 0.2, scores[Department.EINKAUF][1])
            else:
                # Ausgehende Angebote -> Vertrieb
                if Department.VERTRIEB in scores:
                    scores[Department.VERTRIEB] = (scores[Department.VERTRIEB][0] + 0.2, scores[Department.VERTRIEB][1])

        # Keine Matches -> Allgemein
        if not scores:
            return DepartmentRoutingResult(
                primary_department=Department.ALLGEMEIN,
                confidence=0.5,
                secondary_departments=[],
                matched_indicators=[],
                reason="Keine abteilungsspezifischen Indikatoren erkannt",
                requires_cfo_approval=self._requires_cfo_approval(amount),
            )

        # Sortieren nach Score
        sorted_depts = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
        primary_dept = sorted_depts[0][0]
        primary_score, primary_matches = sorted_depts[0][1]

        # Sekundaere Abteilungen (Score > 0.3 und min. halb so hoch wie primary)
        secondary = [
            dept for dept, (score, _) in sorted_depts[1:]
            if score >= 0.3 and score >= primary_score * 0.5
        ]

        # Confidence berechnen
        confidence = min(0.99, 0.4 + primary_score)

        # CFO-Genehmigung pruefen
        requires_cfo = self._requires_cfo_approval(amount, primary_dept)

        # Statistik aktualisieren
        self._stats["by_department"][primary_dept.value] += 1

        # Reason generieren
        if primary_matches:
            reason = f"Erkannte Indikatoren: {', '.join(primary_matches[:3])}"
        elif document_type:
            reason = f"Basierend auf Dokumenttyp: {document_type}"
        else:
            reason = "Allgemeine Klassifikation"

        logger.debug(
            "document_routed",
            primary_department=primary_dept.value,
            confidence=confidence,
            secondary=[(d.value) for d in secondary],
            matched_indicators=primary_matches[:5],
        )

        return DepartmentRoutingResult(
            primary_department=primary_dept,
            confidence=confidence,
            secondary_departments=secondary,
            matched_indicators=primary_matches,
            reason=reason,
            requires_cfo_approval=requires_cfo,
        )

    def _normalize_text(self, text: str) -> str:
        """Normalisiere Text fuer Keyword-Matching."""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _calculate_score(
        self,
        normalized_text: str,
        document_type: Optional[str],
        amount: Optional[Decimal],
        config: DepartmentConfig,
    ) -> tuple:
        """
        Berechne Score fuer eine Abteilung.

        Returns:
            (score, matched_keywords)
        """
        score = 0.0
        matches: List[str] = []

        # 1. Dokumenttyp-Match (staerkster Indikator)
        if document_type:
            doc_type_lower = document_type.lower()
            for dt in config.document_types:
                if dt in doc_type_lower or doc_type_lower in dt:
                    score += 0.5
                    matches.append(f"Typ: {document_type}")
                    break

        # 2. Primary Keywords
        for keyword in config.primary_keywords:
            if keyword in normalized_text:
                score += 0.15
                matches.append(keyword)

        # 3. Secondary Keywords
        for keyword in config.secondary_keywords:
            if keyword in normalized_text:
                score += 0.08
                matches.append(keyword)

        # 4. Betragsschwellen
        if amount is not None and config.amount_threshold is not None:
            if amount >= config.amount_threshold:
                score += 0.3
                matches.append(f"Betrag >= {config.amount_threshold}")

        # Normalisieren (max 1.0)
        score = min(1.0, score)

        return score, matches

    def _requires_cfo_approval(
        self,
        amount: Optional[Decimal],
        department: Optional[Department] = None,
    ) -> bool:
        """Pruefe ob CFO-Genehmigung erforderlich ist."""
        if amount is None:
            return False

        # Generelle Schwelle: 50.000 EUR
        if amount >= Decimal("50000"):
            return True

        # Abteilungsspezifische Schwellen
        if department:
            for config in self.configs:
                if config.department == department and config.amount_ceiling:
                    if amount >= config.amount_ceiling:
                        return True

        return False

    def get_stats(self) -> dict:
        """Gibt Routing-Statistiken zurueck."""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Setzt Statistiken zurueck."""
        self._stats = {
            "total_routings": 0,
            "by_department": {dept.value: 0 for dept in Department},
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_department_router: Optional[DepartmentRouter] = None


def get_department_router() -> DepartmentRouter:
    """Gibt die Singleton-Instanz des Department Router zurueck."""
    global _department_router
    if _department_router is None:
        _department_router = DepartmentRouter()
    return _department_router
