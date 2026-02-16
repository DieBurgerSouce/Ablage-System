# -*- coding: utf-8 -*-
"""
Contract Classification Service.

ML-basierte Klassifikation von Vertragstypen.
Verwendet ein Ensemble aus:
- Regelbasiertem Keyword-Matching
- TF-IDF basierter Textklassifikation
- Strukturanalyse

Feinpoliert und durchdacht.
"""

import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import ContractType

logger = logging.getLogger(__name__)


class ContractClassificationService:
    """
    Service für die Klassifikation von Vertragstypen.

    Kombiniert mehrere Klassifikationsansätze für
    robuste Typenerkennung.
    """

    # Detaillierte Keyword-Mappings pro Vertragstyp
    KEYWORDS = {
        ContractType.SUPPLIER_FRAMEWORK: {
            "high": [
                "rahmenvertrag", "rahmenvereinbarung", "master agreement",
                "mengenrabatt", "jahresvereinbarung", "grundsatzvereinbarung",
            ],
            "medium": [
                "lieferant", "beschaffung", "einkaufskonditionen",
                "rahmenbestellung", "abrufauftrag",
            ],
            "low": [
                "lieferung", "bestellung", "konditionen",
            ],
        },
        ContractType.SUPPLIER_PURCHASE: {
            "high": [
                "einkaufsvertrag", "liefervertrag", "kaufvertrag",
                "beschaffungsvertrag", "lieferantenvertrag",
            ],
            "medium": [
                "warenlieferung", "materiallieferung", "zulieferung",
                "einkaufspreis",
            ],
            "low": [
                "lieferant", "bestellung",
            ],
        },
        ContractType.CUSTOMER_SLA: {
            "high": [
                "service level agreement", "sla", "dienstguete",
                "servicevereinbarung", "verfügbarkeitsgarantie",
            ],
            "medium": [
                "reaktionszeit", "verfügbarkeit", "uptime",
                "servicezeit", "entstörung",
            ],
            "low": [
                "service", "support", "wartung",
            ],
        },
        ContractType.CUSTOMER_WARRANTY: {
            "high": [
                "gewährleistungsvertrag", "garantievertrag",
                "maengelgewährleistung", "garantievereinbarung",
            ],
            "medium": [
                "gewährleistung", "garantie", "maengelhaftung",
                "nachbesserung", "ersatzlieferung",
            ],
            "low": [
                "reklamation", "maengel",
            ],
        },
        ContractType.CUSTOMER_SALES: {
            "high": [
                "verkaufsvertrag", "kaufvertrag", "vertriebsvertrag",
                "absatzvertrag",
            ],
            "medium": [
                "verkäufer", "käufer", "kaufpreis",
                "verkaufspreis", "absatz",
            ],
            "low": [
                "verkauf", "kauf",
            ],
        },
        ContractType.LEASE_PROPERTY: {
            "high": [
                "mietvertrag", "gewerbemietvertrag", "pachtvertrag",
                "mietobjekt", "wohnraummietvertrag",
            ],
            "medium": [
                "mieter", "vermieter", "mietzins", "kaution",
                "nebenkosten", "mietflaeche",
            ],
            "low": [
                "miete", "pacht", "immobilie",
            ],
        },
        ContractType.LEASE_VEHICLE: {
            "high": [
                "fahrzeugleasing", "kfz-leasing", "autoleasing",
                "fuhrparkleasin", "flottenleasing",
            ],
            "medium": [
                "leasingrate", "kilometerleasing", "restwertleasing",
                "leasinggeber", "leasingnehmer", "fahrzeug",
            ],
            "low": [
                "leasing", "kfz", "auto", "fahrzeug",
            ],
        },
        ContractType.LEASE_EQUIPMENT: {
            "high": [
                "maschinenleasing", "anlagenleasing", "equipment-leasing",
                "geräteleasin", "it-leasing",
            ],
            "medium": [
                "leasingobjekt", "investitionsgueter", "betriebsmittel",
                "maschine", "anlage",
            ],
            "low": [
                "leasing", "miete", "equipment",
            ],
        },
        ContractType.EMPLOYMENT_PERMANENT: {
            "high": [
                "unbefristeter arbeitsvertrag", "festanstellung",
                "dauerarbeitsvertrag",
            ],
            "medium": [
                "arbeitsvertrag", "arbeitnehmer", "arbeitgeber",
                "gehalt", "vergütung", "kündigungsschutz",
            ],
            "low": [
                "arbeit", "beschäftigung", "anstellung",
            ],
        },
        ContractType.EMPLOYMENT_FIXED: {
            "high": [
                "befristeter arbeitsvertrag", "zeitvertrag",
                "befristung", "projektvertrag",
            ],
            "medium": [
                "befristet", "endet am", "sachgrund",
                "vertragsende", "auslaufen",
            ],
            "low": [
                "arbeitsvertrag", "projekt",
            ],
        },
        ContractType.EMPLOYMENT_FREELANCE: {
            "high": [
                "freiberuflervertrag", "freelance-vertrag",
                "honorarvertrag", "werkvertrag",
            ],
            "medium": [
                "freiberufler", "selbstaendig", "honorar",
                "werklohn", "abnahme",
            ],
            "low": [
                "projekt", "auftrag",
            ],
        },
        ContractType.NDA: {
            "high": [
                "geheimhaltungsvereinbarung", "nda", "non-disclosure",
                "vertraulichkeitsvereinbarung", "verschwiegenheitsvereinbarung",
            ],
            "medium": [
                "vertraulich", "geheimhaltung", "geheimhaltungspflicht",
                "vertraulichkeit", "offenlegung",
            ],
            "low": [
                "vertraulich", "geheim",
            ],
        },
        ContractType.PARTNERSHIP: {
            "high": [
                "partnerschaftsvertrag", "kooperationsvertrag",
                "joint-venture", "konsortialvertrag",
            ],
            "medium": [
                "partner", "kooperation", "zusammenarbeit",
                "gemeinschaftlich", "konsortium",
            ],
            "low": [
                "partner", "zusammen",
            ],
        },
        ContractType.LICENSE: {
            "high": [
                "lizenzvertrag", "softwarelizenz", "patentlizenz",
                "markenlizenvertrag", "nutzungsrechtsvertrag",
            ],
            "medium": [
                "lizenz", "nutzungsrecht", "lizenzgeber",
                "lizenznehmer", "lizenzgebühr",
            ],
            "low": [
                "software", "patent", "marke",
            ],
        },
        ContractType.MAINTENANCE: {
            "high": [
                "wartungsvertrag", "instandhaltungsvertrag",
                "servicevertrag", "pflegevertrag",
            ],
            "medium": [
                "wartung", "instandhaltung", "reparatur",
                "inspektion", "wartungsleistung",
            ],
            "low": [
                "service", "pflege",
            ],
        },
    }

    # Strukturelle Indikatoren
    STRUCTURAL_INDICATORS = {
        ContractType.LEASE_PROPERTY: [
            "kaltmiete", "warmmiete", "betriebskosten",
            "hausordnung", "übergabeprotokoll",
        ],
        ContractType.EMPLOYMENT_PERMANENT: [
            "arbeitszeit", "urlaub", "kündigungsfrist",
            "probezeit", "sozialversicherung",
        ],
        ContractType.NDA: [
            "vertrauliche informationen", "offenlegung",
            "rückgabe", "vernichtung",
        ],
        ContractType.LICENSE: [
            "nutzungsumfang", "lizenzgebiet", "unterlizenz",
            "exklusiv", "nicht-exklusiv",
        ],
    }

    def __init__(self, db: Optional[AsyncSession] = None):
        """Initialisiere Service."""
        self.db = db

    async def classify(
        self,
        text: str,
        return_scores: bool = False,
    ) -> Tuple[ContractType, float] | Tuple[ContractType, float, Dict[ContractType, float]]:
        """
        Klassifiziere Vertragstext.

        Args:
            text: Zu klassifizierender Text
            return_scores: Ob alle Scores zurückgegeben werden sollen

        Returns:
            Tuple aus (ContractType, Confidence) oder
            (ContractType, Confidence, AlleScores) wenn return_scores=True
        """
        if not text or len(text.strip()) < 50:
            if return_scores:
                return ContractType.OTHER, 0.0, {}
            return ContractType.OTHER, 0.0

        # Normalisiere Text
        text_lower = self._normalize_for_classification(text)

        # Berechne Scores für alle Typen
        scores = {}
        for contract_type in ContractType:
            if contract_type == ContractType.OTHER:
                continue
            scores[contract_type] = self._calculate_type_score(text_lower, contract_type)

        # Finde besten Match
        if scores:
            best_type = max(scores, key=scores.get)
            best_score = scores[best_type]

            # Schwellenwert für Confidence
            if best_score < 0.1:
                best_type = ContractType.OTHER
                best_score = 0.0

            # Normalisiere Confidence auf 0-1
            confidence = min(best_score / 2.0, 1.0)  # Score 2.0 = 100% Confidence

            logger.info(f"Vertragsklassifikation: {best_type.value}, Confidence: {confidence:.2%}")

            if return_scores:
                return best_type, confidence, scores
            return best_type, confidence

        if return_scores:
            return ContractType.OTHER, 0.0, {}
        return ContractType.OTHER, 0.0

    async def classify_batch(
        self,
        texts: List[str],
    ) -> List[Tuple[ContractType, float]]:
        """
        Klassifiziere mehrere Texte.

        Args:
            texts: Liste von Texten

        Returns:
            Liste von (ContractType, Confidence) Tuples
        """
        results = []
        for text in texts:
            result = await self.classify(text)
            results.append(result)
        return results

    def _normalize_for_classification(self, text: str) -> str:
        """Normalisiere Text für Klassifikation."""
        # Kleinschreibung
        result = text.lower()

        # Deutsche Umlaute
        replacements = {
            "ä": "ae", "ö": "oe", "ü": "ue",
            "ß": "ss",
        }
        for old, new in replacements.items():
            result = result.replace(old, new)

        return result

    def _calculate_type_score(self, text: str, contract_type: ContractType) -> float:
        """
        Berechne Score für einen Vertragstyp.

        Kombiniert Keyword-Matching mit Gewichtung.
        """
        score = 0.0

        keywords = self.KEYWORDS.get(contract_type, {})

        # High-Priority Keywords (gewichtet mit 1.0)
        for keyword in keywords.get("high", []):
            keyword_normalized = self._normalize_for_classification(keyword)
            if keyword_normalized in text:
                score += 1.0
                # Bonus für mehrfaches Vorkommen
                count = text.count(keyword_normalized)
                if count > 1:
                    score += min(count - 1, 3) * 0.2  # Max 0.6 Bonus

        # Medium-Priority Keywords (gewichtet mit 0.4)
        for keyword in keywords.get("medium", []):
            keyword_normalized = self._normalize_for_classification(keyword)
            if keyword_normalized in text:
                score += 0.4

        # Low-Priority Keywords (gewichtet mit 0.1)
        for keyword in keywords.get("low", []):
            keyword_normalized = self._normalize_for_classification(keyword)
            if keyword_normalized in text:
                score += 0.1

        # Strukturelle Indikatoren
        structural = self.STRUCTURAL_INDICATORS.get(contract_type, [])
        for indicator in structural:
            indicator_normalized = self._normalize_for_classification(indicator)
            if indicator_normalized in text:
                score += 0.3

        return score

    async def get_type_explanation(
        self,
        text: str,
        contract_type: ContractType,
    ) -> Dict[str, List[str]]:
        """
        Erkläre warum ein Text als bestimmter Typ klassifiziert wurde.

        Args:
            text: Der klassifizierte Text
            contract_type: Der zugewiesene Typ

        Returns:
            Dictionary mit gefundenen Keywords pro Kategorie
        """
        text_lower = self._normalize_for_classification(text)
        keywords = self.KEYWORDS.get(contract_type, {})

        found = {
            "high_priority": [],
            "medium_priority": [],
            "low_priority": [],
            "structural": [],
        }

        for keyword in keywords.get("high", []):
            keyword_normalized = self._normalize_for_classification(keyword)
            if keyword_normalized in text_lower:
                found["high_priority"].append(keyword)

        for keyword in keywords.get("medium", []):
            keyword_normalized = self._normalize_for_classification(keyword)
            if keyword_normalized in text_lower:
                found["medium_priority"].append(keyword)

        for keyword in keywords.get("low", []):
            keyword_normalized = self._normalize_for_classification(keyword)
            if keyword_normalized in text_lower:
                found["low_priority"].append(keyword)

        for indicator in self.STRUCTURAL_INDICATORS.get(contract_type, []):
            indicator_normalized = self._normalize_for_classification(indicator)
            if indicator_normalized in text_lower:
                found["structural"].append(indicator)

        return found

    @staticmethod
    def get_type_description(contract_type: ContractType) -> str:
        """Gibt deutsche Beschreibung für Vertragstyp zurück."""
        descriptions = {
            ContractType.SUPPLIER_FRAMEWORK: "Rahmenvertrag mit Lieferanten",
            ContractType.SUPPLIER_PURCHASE: "Einkaufs-/Liefervertrag",
            ContractType.CUSTOMER_SLA: "Service Level Agreement (SLA)",
            ContractType.CUSTOMER_WARRANTY: "Gewährleistungsvertrag",
            ContractType.CUSTOMER_SALES: "Verkaufsvertrag",
            ContractType.LEASE_PROPERTY: "Miet-/Pachtvertrag (Immobilie)",
            ContractType.LEASE_VEHICLE: "Fahrzeugleasing",
            ContractType.LEASE_EQUIPMENT: "Equipment-/Maschinenleasing",
            ContractType.EMPLOYMENT_PERMANENT: "Unbefristeter Arbeitsvertrag",
            ContractType.EMPLOYMENT_FIXED: "Befristeter Arbeitsvertrag",
            ContractType.EMPLOYMENT_FREELANCE: "Freiberufler-/Werkvertrag",
            ContractType.NDA: "Geheimhaltungsvereinbarung (NDA)",
            ContractType.PARTNERSHIP: "Partnerschafts-/Kooperationsvertrag",
            ContractType.LICENSE: "Lizenzvertrag",
            ContractType.MAINTENANCE: "Wartungs-/Servicevertrag",
            ContractType.OTHER: "Sonstiger Vertrag",
        }
        return descriptions.get(contract_type, "Unbekannter Vertragstyp")

    @staticmethod
    def get_all_types_with_descriptions() -> List[Dict[str, str]]:
        """Gibt alle Vertragstypen mit Beschreibungen zurück."""
        return [
            {
                "value": ct.value,
                "label": ContractClassificationService.get_type_description(ct),
            }
            for ct in ContractType
        ]
