# -*- coding: utf-8 -*-
"""
Contract Extraction Service.

NLP-basierte Extraktion von Vertragsklauseln und Metadaten
aus OCR-Text. Extrahiert:
- Laufzeit & Kündigungsfristen
- Zahlungsbedingungen (Skonto, Zahlungsziele)
- Haftungsklauseln (Limits, Ausschluesse)
- Preisanpassungsklauseln (Indexierung)
- Parteien & Unterschriften
- Geheimhaltung (NDA)
- Lieferbedingungen (Incoterms)
- Garantien & Gewährleistungen
- Gerichtsstand

Feinpoliert und durchdacht.
"""

import re
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models_contract import (
    Contract,
    ContractType,
    ContractStatus,
    ContractObligation,
    ContractDeadline,
    ObligationType,
    ObligationStatus,
)

logger = logging.getLogger(__name__)


class ContractExtractionService:
    """
    Service für die automatische Extraktion von Vertragsklauseln.

    Verwendet regelbasierte Pattern-Matching kombiniert mit
    NLP-Heuristiken für die Extraktion strukturierter Daten.
    """

    # Deutsche Patterns für Vertragsklauseln
    PATTERNS = {
        # Laufzeit
        "duration": [
            r"(?:Laufzeit|Vertragsdauer|Mietdauer)[:\s]+(\d+)\s*(?:Jahre?|Monate?|Wochen?)",
            r"(?:für|über)\s+(?:einen?\s+)?(?:Zeitraum\s+von\s+)?(\d+)\s*(?:Jahre?|Monate?)",
            r"(?:befristet\s+(?:auf|bis)\s+)?(\d{1,2})[./](\d{1,2})[./](\d{2,4})",
        ],
        # Kündigungsfrist
        "notice_period": [
            r"(?:Kündigungsfrist|Kündigung)[:\s]+(\d+)\s*(?:Tage?|Wochen?|Monate?)",
            r"(?:mit\s+einer?\s+Frist\s+von)\s+(\d+)\s*(?:Tagen?|Wochen?|Monaten?)",
            r"(\d+)\s*(?:Tage?|Wochen?|Monate?)\s+(?:vor\s+)?(?:Vertragsende|Ablauf)",
        ],
        # Zahlungsbedingungen
        "payment_terms": [
            r"(?:Zahlungsziel|Zahlungsfrist|fällig)[:\s]+(\d+)\s*(?:Tage?|Werktage?)",
            r"(?:innerhalb\s+von)\s+(\d+)\s*(?:Tagen?|Werktagen?)",
            r"(?:netto|rein\s+netto)[:\s]+(\d+)\s*(?:Tage?)",
        ],
        # Skonto
        "skonto": [
            r"(\d+(?:[,.]\d+)?)\s*%?\s*Skonto\s*(?:bei|innerhalb|binnen)\s*(\d+)\s*(?:Tagen?|Werktagen?)",
            r"bei\s+Zahlung\s+innerhalb\s+(\d+)\s*(?:Tagen?)[:\s]+(\d+(?:[,.]\d+)?)\s*%",
            r"Skonto[:\s]+(\d+(?:[,.]\d+)?)\s*%\s*/\s*(\d+)\s*(?:Tage?)",
        ],
        # Haftungslimit
        "liability_limit": [
            r"(?:Haftung|Haftungslimit|Hoechstbetrag)[:\s]+(?:EUR|€)?\s*([\d.,]+)",
            r"(?:maximal|hoechstens|begrenzt\s+auf)[:\s]+(?:EUR|€)?\s*([\d.,]+)",
            r"(?:bis\s+zu\s+einem\s+Betrag\s+von)\s+(?:EUR|€)?\s*([\d.,]+)",
        ],
        # Gewährleistung/Garantie
        "warranty": [
            r"(?:Gewährleistung|Garantie|Gewährleistungsfrist)[:\s]+(\d+)\s*(?:Jahre?|Monate?)",
            r"(?:Gewährleistungsansprueche\s+verjaehren\s+nach)\s+(\d+)\s*(?:Jahren?|Monaten?)",
            r"(\d+)\s*(?:Jahre?|Monate?)\s+(?:Gewährleistung|Garantie)",
        ],
        # Gerichtsstand
        "jurisdiction": [
            r"(?:Gerichtsstand|Erfuellungsort)[:\s]+(\w+(?:\s+\w+)?)",
            r"(?:zuständig\s+ist\s+das\s+(?:Gericht|Landgericht|Amtsgericht)\s+)(\w+)",
            r"(?:ausschließlicher?\s+Gerichtsstand)[:\s]+(\w+)",
        ],
        # Incoterms
        "incoterms": [
            r"\b(EXW|FCA|CPT|CIP|DAP|DPU|DDP|FAS|FOB|CFR|CIF)\b",
        ],
        # Preisanpassung
        "price_adjustment": [
            r"(?:Preisanpassung|Preiserhöhung|Indexierung)[:\s]+(\w+)",
            r"(?:Anpassung\s+an\s+den?)\s+(\w+(?:-?\w+)?-?Index)",
            r"(\d+(?:[,.]\d+)?)\s*%\s*(?:jährlich|pro\s+Jahr)",
        ],
        # Vertragswert
        "value": [
            r"(?:Gesamtwert|Vertragswert|Gesamtpreis|Auftragswert)[:\s]+(?:EUR|€)?\s*([\d.,]+)",
            r"(?:EUR|€)\s*([\d.,]+)\s*(?:netto|brutto|zzgl)",
            r"(?:Betrag|Summe)[:\s]+(?:EUR|€)?\s*([\d.,]+)",
        ],
        # Vertragsparteien
        "parties": [
            r"(?:zwischen|Vertragspartner)[:\s]*\n?\s*1[.)]\s*(.+?)(?:\n|,|und)",
            r"(?:Auftraggeber|Käufer|Mieter|Arbeitgeber)[:\s]+(.+?)(?:\n|,)",
            r"(?:Auftragnehmer|Verkäufer|Vermieter|Arbeitnehmer)[:\s]+(.+?)(?:\n|,)",
        ],
        # NDA/Geheimhaltung
        "confidentiality": [
            r"(?:Geheimhaltung|Vertraulichkeit|NDA)[:\s]+(\d+)\s*(?:Jahre?|Monate?)",
            r"(?:vertraulich\s+zu\s+behandeln\s+für)\s+(\d+)\s*(?:Jahre?)",
            r"(?:Geheimhaltungspflicht\s+(?:gilt|besteht)\s+für)\s+(\d+)\s*(?:Jahre?)",
        ],
    }

    # Vertragstyp-Indikatoren
    CONTRACT_TYPE_INDICATORS = {
        ContractType.SUPPLIER_FRAMEWORK: [
            "Rahmenvertrag", "Rahmenvereinbarung", "Einkaufskonditionen",
            "Lieferantenvertrag", "Beschaffungsvertrag",
        ],
        ContractType.CUSTOMER_SLA: [
            "Service Level Agreement", "SLA", "Dienstguetevereinbarung",
            "Reaktionszeit", "Verfügbarkeit",
        ],
        ContractType.LEASE_PROPERTY: [
            "Mietvertrag", "Mietobjekt", "Mieter", "Vermieter",
            "Kaution", "Nebenkosten", "Wohnflaeche",
        ],
        ContractType.LEASE_VEHICLE: [
            "Fahrzeugleasing", "Leasingvertrag", "Leasinggeber",
            "Leasingnehmer", "Kilometerleasing", "Restwert",
        ],
        ContractType.LEASE_EQUIPMENT: [
            "Maschinenleasing", "Equipment", "Anlagenleasing",
            "Geräteleasin", "Mietkauf",
        ],
        ContractType.EMPLOYMENT_PERMANENT: [
            "Arbeitsvertrag", "Arbeitnehmer", "Arbeitgeber",
            "Gehalt", "unbefristet", "Kündigungsschutz",
        ],
        ContractType.EMPLOYMENT_FIXED: [
            "befristeter Arbeitsvertrag", "Befristung", "endet am",
            "sachgrundlose Befristung", "Projektvertrag",
        ],
        ContractType.NDA: [
            "Geheimhaltungsvereinbarung", "Non-Disclosure", "NDA",
            "Vertraulichkeitsvereinbarung", "vertrauliche Informationen",
        ],
        ContractType.LICENSE: [
            "Lizenzvertrag", "Nutzungsrecht", "Lizenzgeber",
            "Lizenznehmer", "Software-Lizenz",
        ],
        ContractType.MAINTENANCE: [
            "Wartungsvertrag", "Instandhaltung", "Service-Vertrag",
            "Wartungsleistungen", "Inspektionen",
        ],
    }

    def __init__(self, db: AsyncSession):
        """Initialisiere Service mit Datenbank-Session."""
        self.db = db

    async def extract_from_text(
        self,
        text: str,
        document_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Extrahiere Vertragsklauseln aus OCR-Text.

        Args:
            text: Der zu analysierende Vertragstext
            document_id: Optional ID des Quelldokuments
            company_id: ID der Firma für Multi-Tenant

        Returns:
            Dictionary mit extrahierten Klauseln und Metadaten
        """
        if not text or len(text.strip()) < 50:
            logger.warning("Text zu kurz für Vertragsextraktion")
            return {"error": "Text zu kurz", "clauses": {}}

        # Normalisiere Text
        normalized_text = self._normalize_text(text)

        # Extrahiere alle Klauseln
        extraction_result = {
            "contract_type": self._detect_contract_type(normalized_text),
            "duration": self._extract_duration(normalized_text),
            "notice_period": self._extract_notice_period(normalized_text),
            "payment_terms": self._extract_payment_terms(normalized_text),
            "liability": self._extract_liability(normalized_text),
            "warranty": self._extract_warranty(normalized_text),
            "jurisdiction": self._extract_jurisdiction(normalized_text),
            "incoterms": self._extract_incoterms(normalized_text),
            "price_adjustment": self._extract_price_adjustment(normalized_text),
            "value": self._extract_value(normalized_text),
            "parties": self._extract_parties(normalized_text),
            "confidentiality": self._extract_confidentiality(normalized_text),
            "dates": self._extract_dates(normalized_text),
        }

        # Berechne Extraktions-Confidence
        extraction_result["confidence"] = self._calculate_confidence(extraction_result)

        logger.info(
            f"Vertragsextraktion abgeschlossen: Typ={extraction_result['contract_type']}, "
            f"Confidence={extraction_result['confidence']:.2%}"
        )

        return extraction_result

    async def create_contract_from_extraction(
        self,
        extraction: Dict[str, Any],
        document_id: UUID,
        company_id: UUID,
        created_by_id: Optional[UUID] = None,
        title: Optional[str] = None,
    ) -> Contract:
        """
        Erstelle einen Contract-Eintrag aus Extraktionsergebnissen.

        Args:
            extraction: Ergebnis von extract_from_text
            document_id: ID des Quelldokuments
            company_id: ID der Firma
            created_by_id: Optional ID des erstellenden Benutzers
            title: Optional Vertragstitel (sonst automatisch generiert)

        Returns:
            Erstellter Contract
        """
        contract_type = extraction.get("contract_type", ContractType.OTHER)

        # Generiere Titel wenn nicht angegeben
        if not title:
            title = self._generate_title(extraction)

        # Erstelle Contract
        contract = Contract(
            document_id=document_id,
            title=title,
            contract_type=contract_type.value if isinstance(contract_type, ContractType) else contract_type,
            status=ContractStatus.DRAFT.value,
            parties=extraction.get("parties", {}).get("list", []),
            effective_date=extraction.get("dates", {}).get("start"),
            expiration_date=extraction.get("dates", {}).get("end"),
            notice_period_days=extraction.get("notice_period", {}).get("days"),
            total_value=extraction.get("value", {}).get("amount"),
            currency=extraction.get("value", {}).get("currency", "EUR"),
            payment_terms=extraction.get("payment_terms", {}),
            clauses={
                "liability": extraction.get("liability", {}),
                "warranty": extraction.get("warranty", {}),
                "jurisdiction": extraction.get("jurisdiction", {}),
                "incoterms": extraction.get("incoterms"),
                "price_adjustment": extraction.get("price_adjustment", {}),
                "confidentiality": extraction.get("confidentiality", {}),
            },
            risk_score=self._calculate_risk_score(extraction),
            extraction_confidence=Decimal(str(extraction.get("confidence", 0))),
            extraction_backend="contract_ai_v1",
            last_analyzed_at=datetime.now(),
            analysis_version="1.0",
            company_id=company_id,
            created_by_id=created_by_id,
        )

        self.db.add(contract)
        await self.db.flush()

        # Erstelle automatische Deadlines
        await self._create_automatic_deadlines(contract, extraction)

        # Erstelle wiederkehrende Obligations
        await self._create_automatic_obligations(contract, extraction)

        await self.db.commit()
        await self.db.refresh(contract)

        logger.info(f"Contract erstellt: {contract.id}, Titel: {contract.title}")
        return contract

    def _normalize_text(self, text: str) -> str:
        """Normalisiere Text für besseres Pattern-Matching."""
        # Ersetze Umlaute durch ASCII-Äquivalente für Regex
        replacements = {
            "ä": "ae", "ö": "oe", "ü": "ue",
            "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
            "ß": "ss",
        }
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)

        # Normalisiere Whitespace
        result = re.sub(r'\s+', ' ', result)

        return result

    def _detect_contract_type(self, text: str) -> ContractType:
        """Erkenne Vertragstyp basierend auf Schluesselwoertern."""
        text_lower = text.lower()
        scores: Dict[ContractType, int] = {}

        for contract_type, indicators in self.CONTRACT_TYPE_INDICATORS.items():
            score = 0
            for indicator in indicators:
                # Normalisiere Indicator
                indicator_normalized = self._normalize_text(indicator).lower()
                if indicator_normalized in text_lower:
                    score += 1
            if score > 0:
                scores[contract_type] = score

        if scores:
            return max(scores, key=scores.get)
        return ContractType.OTHER

    def _extract_duration(self, text: str) -> Dict[str, Any]:
        """Extrahiere Vertragslaufzeit."""
        for pattern in self.PATTERNS["duration"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 1:
                    try:
                        value = int(groups[0])
                        # Bestimme Einheit
                        match_text = match.group(0).lower()
                        if "jahr" in match_text:
                            return {"months": value * 12, "unit": "years", "value": value}
                        elif "woche" in match_text:
                            return {"months": value // 4, "unit": "weeks", "value": value}
                        else:
                            return {"months": value, "unit": "months", "value": value}
                    except ValueError:
                        continue
        return {}

    def _extract_notice_period(self, text: str) -> Dict[str, Any]:
        """Extrahiere Kündigungsfrist."""
        for pattern in self.PATTERNS["notice_period"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = int(match.group(1))
                    match_text = match.group(0).lower()
                    if "monat" in match_text:
                        return {"days": value * 30, "unit": "months", "value": value}
                    elif "woche" in match_text:
                        return {"days": value * 7, "unit": "weeks", "value": value}
                    else:
                        return {"days": value, "unit": "days", "value": value}
                except ValueError:
                    continue
        return {}

    def _extract_payment_terms(self, text: str) -> Dict[str, Any]:
        """Extrahiere Zahlungsbedingungen inkl. Skonto."""
        result = {}

        # Zahlungsziel
        for pattern in self.PATTERNS["payment_terms"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    result["due_days"] = int(match.group(1))
                    break
                except ValueError:
                    continue

        # Skonto
        for pattern in self.PATTERNS["skonto"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    # Bestimme welche Gruppe Prozent und welche Tage ist
                    if "%" in match.group(0) or float(groups[0].replace(",", ".")) < 10:
                        result["skonto_percent"] = float(groups[0].replace(",", "."))
                        result["skonto_days"] = int(groups[1])
                    else:
                        result["skonto_days"] = int(groups[0])
                        result["skonto_percent"] = float(groups[1].replace(",", "."))
                    break
                except (ValueError, IndexError):
                    continue

        return result

    def _extract_liability(self, text: str) -> Dict[str, Any]:
        """Extrahiere Haftungsklauseln."""
        result = {}

        for pattern in self.PATTERNS["liability_limit"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1).replace(".", "").replace(",", ".")
                    result["limit"] = float(amount_str)
                    result["currency"] = "EUR"
                    break
                except ValueError:
                    continue

        # Suche nach Haftungsausschluessen
        exclusion_patterns = [
            r"(?:Haftungsausschluss|ausgeschlossen)[:\s]*(.+?)(?:\.|;|\n)",
            r"(?:haftet\s+nicht\s+für)[:\s]*(.+?)(?:\.|;|\n)",
        ]
        exclusions = []
        for pattern in exclusion_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            exclusions.extend(matches)
        if exclusions:
            result["exclusions"] = exclusions[:5]  # Max 5

        return result

    def _extract_warranty(self, text: str) -> Dict[str, Any]:
        """Extrahiere Gewährleistung/Garantie."""
        for pattern in self.PATTERNS["warranty"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = int(match.group(1))
                    match_text = match.group(0).lower()
                    if "jahr" in match_text:
                        return {"period_months": value * 12, "unit": "years", "value": value}
                    else:
                        return {"period_months": value, "unit": "months", "value": value}
                except ValueError:
                    continue
        return {}

    def _extract_jurisdiction(self, text: str) -> Dict[str, Any]:
        """Extrahiere Gerichtsstand."""
        for pattern in self.PATTERNS["jurisdiction"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                court = match.group(1).strip()
                # Entferne unerwünschte Zeichen
                court = re.sub(r'[.,;]', '', court)
                if len(court) > 2:
                    return {"court": court, "law": "German"}
        return {}

    def _extract_incoterms(self, text: str) -> Optional[str]:
        """Extrahiere Incoterms."""
        for pattern in self.PATTERNS["incoterms"]:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_price_adjustment(self, text: str) -> Dict[str, Any]:
        """Extrahiere Preisanpassungsklauseln."""
        result = {}

        for pattern in self.PATTERNS["price_adjustment"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                if "index" in value.lower() or "vpi" in value.lower() or "cpi" in value.lower():
                    result["type"] = "index"
                    result["index_name"] = value
                elif re.match(r'\d+', value):
                    result["type"] = "percentage"
                    result["percentage"] = float(value.replace(",", "."))
                    result["interval"] = "annual"
                break

        return result

    def _extract_value(self, text: str) -> Dict[str, Any]:
        """Extrahiere Vertragswert."""
        for pattern in self.PATTERNS["value"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1).replace(".", "").replace(",", ".")
                    amount = float(amount_str)
                    if amount > 0:
                        return {"amount": amount, "currency": "EUR"}
                except ValueError:
                    continue
        return {}

    def _extract_parties(self, text: str) -> Dict[str, Any]:
        """Extrahiere Vertragsparteien."""
        parties = []

        for pattern in self.PATTERNS["parties"]:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                party_name = match.strip()
                # Bereinige
                party_name = re.sub(r'[,;].*$', '', party_name).strip()
                if len(party_name) > 3 and party_name not in [p.get("name") for p in parties]:
                    parties.append({"name": party_name, "role": "party"})

        return {"list": parties[:4]}  # Max 4 Parteien

    def _extract_confidentiality(self, text: str) -> Dict[str, Any]:
        """Extrahiere Geheimhaltungsklauseln."""
        for pattern in self.PATTERNS["confidentiality"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = int(match.group(1))
                    return {"duration_years": value}
                except ValueError:
                    continue
        return {}

    def _extract_dates(self, text: str) -> Dict[str, Any]:
        """Extrahiere relevante Daten."""
        result = {}

        # Deutsche Datumsformate
        date_patterns = [
            r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})",
            r"(\d{1,2})\.\s*(?:Januar|Februar|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})",
        ]

        dates_found = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    if len(match) == 3:
                        day, month, year = int(match[0]), int(match[1]), int(match[2])
                        if year < 100:
                            year += 2000
                        parsed_date = date(year, month, day)
                        dates_found.append(parsed_date)
                except (ValueError, IndexError):
                    continue

        if dates_found:
            dates_found.sort()
            result["start"] = dates_found[0]
            if len(dates_found) > 1:
                result["end"] = dates_found[-1]

        return result

    def _calculate_confidence(self, extraction: Dict[str, Any]) -> float:
        """Berechne Extraktions-Confidence."""
        # Gewichte für verschiedene Felder
        weights = {
            "contract_type": 0.15,
            "duration": 0.1,
            "notice_period": 0.1,
            "payment_terms": 0.1,
            "liability": 0.1,
            "warranty": 0.05,
            "jurisdiction": 0.05,
            "value": 0.15,
            "parties": 0.1,
            "dates": 0.1,
        }

        score = 0.0
        for field, weight in weights.items():
            value = extraction.get(field)
            if value:
                if isinstance(value, dict) and value:
                    score += weight
                elif isinstance(value, ContractType) and value != ContractType.OTHER:
                    score += weight
                elif value:
                    score += weight

        return min(score, 1.0)

    def _calculate_risk_score(self, extraction: Dict[str, Any]) -> int:
        """Berechne Risiko-Score (0-100)."""
        risk_score = 50  # Basis

        # Risiko-Faktoren
        # Kurze Kündigungsfrist = höher Risiko
        notice = extraction.get("notice_period", {})
        if notice:
            days = notice.get("days", 30)
            if days < 14:
                risk_score += 15
            elif days < 30:
                risk_score += 5

        # Keine Haftungsbegrenzung = höher Risiko
        liability = extraction.get("liability", {})
        if not liability.get("limit"):
            risk_score += 10

        # Keine Gewährleistung = höher Risiko
        warranty = extraction.get("warranty", {})
        if not warranty:
            risk_score += 5

        # Niedriger Wert mit langer Laufzeit = geringes Risiko
        value = extraction.get("value", {}).get("amount", 0)
        duration = extraction.get("duration", {}).get("months", 0)
        if value > 100000:
            risk_score += 10
        if duration > 24:
            risk_score += 5

        return max(0, min(100, risk_score))

    def _generate_title(self, extraction: Dict[str, Any]) -> str:
        """Generiere automatischen Titel."""
        contract_type = extraction.get("contract_type", ContractType.OTHER)

        type_names = {
            ContractType.SUPPLIER_FRAMEWORK: "Rahmenvertrag",
            ContractType.SUPPLIER_PURCHASE: "Einkaufsvertrag",
            ContractType.CUSTOMER_SLA: "Service Level Agreement",
            ContractType.CUSTOMER_WARRANTY: "Gewährleistungsvertrag",
            ContractType.CUSTOMER_SALES: "Verkaufsvertrag",
            ContractType.LEASE_PROPERTY: "Mietvertrag",
            ContractType.LEASE_VEHICLE: "Fahrzeugleasing",
            ContractType.LEASE_EQUIPMENT: "Equipment-Leasing",
            ContractType.EMPLOYMENT_PERMANENT: "Arbeitsvertrag",
            ContractType.EMPLOYMENT_FIXED: "Befristeter Arbeitsvertrag",
            ContractType.NDA: "Geheimhaltungsvereinbarung",
            ContractType.LICENSE: "Lizenzvertrag",
            ContractType.MAINTENANCE: "Wartungsvertrag",
            ContractType.OTHER: "Vertrag",
        }

        base_title = type_names.get(contract_type, "Vertrag")

        # Fuege Partei hinzu wenn vorhanden
        parties = extraction.get("parties", {}).get("list", [])
        if parties:
            first_party = parties[0].get("name", "")[:30]
            return f"{base_title} - {first_party}"

        return base_title

    async def _create_automatic_deadlines(
        self,
        contract: Contract,
        extraction: Dict[str, Any],
    ) -> List[ContractDeadline]:
        """Erstelle automatische Deadlines basierend auf Extraktion."""
        deadlines = []

        # Vertragsablauf
        if contract.expiration_date:
            deadline = ContractDeadline(
                contract_id=contract.id,
                deadline_type="contract_expiry",
                title="Vertragsablauf",
                description=f"Der Vertrag '{contract.title}' laeuft ab.",
                deadline_date=contract.expiration_date,
                priority="high",
                company_id=contract.company_id,
            )
            self.db.add(deadline)
            deadlines.append(deadline)

            # Kündigungsfrist-Erinnerung
            if contract.notice_period_days:
                notice_deadline = contract.expiration_date - timedelta(days=contract.notice_period_days)
                if notice_deadline > date.today():
                    deadline = ContractDeadline(
                        contract_id=contract.id,
                        deadline_type="termination_notice",
                        title="Kündigungsfrist",
                        description=f"Letzte Möglichkeit zur Kündigung (Frist: {contract.notice_period_days} Tage)",
                        deadline_date=notice_deadline,
                        priority="critical",
                        company_id=contract.company_id,
                    )
                    self.db.add(deadline)
                    deadlines.append(deadline)

        # Gewährleistungsende
        warranty = extraction.get("warranty", {})
        if warranty.get("period_months") and contract.effective_date:
            warranty_end = contract.effective_date + timedelta(days=warranty["period_months"] * 30)
            deadline = ContractDeadline(
                contract_id=contract.id,
                deadline_type="warranty_expiry",
                title="Gewährleistungsende",
                description=f"Gewährleistung endet nach {warranty['period_months']} Monaten",
                deadline_date=warranty_end,
                priority="medium",
                company_id=contract.company_id,
            )
            self.db.add(deadline)
            deadlines.append(deadline)

        return deadlines

    async def _create_automatic_obligations(
        self,
        contract: Contract,
        extraction: Dict[str, Any],
    ) -> List[ContractObligation]:
        """Erstelle wiederkehrende Obligations basierend auf Extraktion."""
        obligations = []

        # Zahlungspflichten
        payment = extraction.get("payment_terms", {})
        if payment.get("due_days"):
            obligation = ContractObligation(
                contract_id=contract.id,
                obligation_type=ObligationType.PAYMENT.value,
                title="Zahlungspflicht",
                description=f"Zahlung innerhalb von {payment['due_days']} Tagen",
                responsible_party="us",
                status=ObligationStatus.PENDING.value,
                company_id=contract.company_id,
            )
            self.db.add(obligation)
            obligations.append(obligation)

        return obligations
