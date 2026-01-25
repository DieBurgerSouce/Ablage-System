# -*- coding: utf-8 -*-
"""
RoutingIntelligenceService - KI-basiertes Dokumenten-Routing.

Entscheidet automatisch:
1. Welcher Workflow fuer ein Dokument zustaendig ist
2. Welche Abteilung/Person es bearbeiten soll
3. Welche Prioritaet es hat
4. Ob Eskalation erforderlich ist

Basiert auf:
- Dokumenttyp
- Erkannte Entitaet (Kunde/Lieferant)
- Betrag
- Historische Muster
- OCR-Inhalt (Keywords)

Phase 2.2 der Feature-Roadmap (Januar 2026)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document, BusinessEntity

# NOTE: Folder model does not exist - folder-based routing disabled
Folder = None

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================


class RoutingTarget(str, Enum):
    """Ziel des Routings."""

    WORKFLOW = "workflow"  # BPMN-Workflow
    DEPARTMENT = "department"  # Abteilung
    USER = "user"  # Spezifischer User
    QUEUE = "queue"  # Warteschlange


class Priority(str, Enum):
    """Prioritaet eines Dokuments."""

    CRITICAL = "critical"  # Sofortige Bearbeitung (heute)
    HIGH = "high"  # Dringend (24h)
    MEDIUM = "medium"  # Normal (1 Woche)
    LOW = "low"  # Niedrig (wenn Zeit)


class Department(str, Enum):
    """Standard-Abteilungen."""

    BUCHHALTUNG = "buchhaltung"
    EINKAUF = "einkauf"
    VERKAUF = "verkauf"
    PERSONAL = "personal"
    GESCHAEFTSFUEHRUNG = "geschaeftsfuehrung"
    IT = "it"
    LAGER = "lager"
    QUALITAET = "qualitaet"
    ALLGEMEIN = "allgemein"


class RoutingReason(str, Enum):
    """Grund fuer das Routing."""

    DOCUMENT_TYPE = "document_type"  # Basierend auf Dokumenttyp
    AMOUNT_THRESHOLD = "amount_threshold"  # Basierend auf Betrag
    ENTITY_ASSIGNMENT = "entity_assignment"  # Basierend auf Entity
    KEYWORD_MATCH = "keyword_match"  # Basierend auf Keywords
    HISTORICAL_PATTERN = "historical_pattern"  # Basierend auf Historie
    EXPLICIT_RULE = "explicit_rule"  # Explizite Regel
    ESCALATION = "escalation"  # Eskalation
    DEFAULT = "default"  # Fallback


@dataclass
class RoutingDecision:
    """Ergebnis einer Routing-Entscheidung."""

    document_id: uuid.UUID
    target_type: RoutingTarget
    target_id: Optional[str]  # Workflow-ID, User-ID, Department-Name
    target_name: str  # Menschenlesbarer Name
    priority: Priority
    confidence: float
    reasons: List[RoutingReason]
    explanation: str  # Erklaerung fuer den User
    requires_approval: bool = False
    suggested_deadline: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingRule:
    """Eine Routing-Regel."""

    id: uuid.UUID
    name: str
    description: str
    priority: int  # Niedrig = hohe Prioritaet
    conditions: Dict[str, Any]  # z.B. {"document_type": "invoice", "amount_gt": 1000}
    action: Dict[str, Any]  # z.B. {"route_to": "buchhaltung", "priority": "high"}
    enabled: bool = True


# ============================================================================
# Keyword Mappings fuer Abteilungen
# ============================================================================

DEPARTMENT_KEYWORDS: Dict[Department, List[str]] = {
    Department.BUCHHALTUNG: [
        "rechnung", "invoice", "mahnung", "zahlung", "skonto", "ueberweisung",
        "lastschrift", "gutschrift", "steuern", "umsatzsteuer", "vorsteuer",
        "bilanz", "jahresabschluss", "buchhaltung", "konto", "beleg",
    ],
    Department.EINKAUF: [
        "bestellung", "lieferant", "angebot", "anfrage", "einkauf",
        "lieferung", "wareneingang", "lieferschein", "rahmenvertrag",
        "beschaffung", "procurement", "supplier",
    ],
    Department.VERKAUF: [
        "kunde", "kundenauftrag", "auftragsbestaetigung", "angebot",
        "verkauf", "sales", "vertrieb", "customer", "bestellung",
        "auftrag", "offerte",
    ],
    Department.PERSONAL: [
        "personal", "mitarbeiter", "gehalt", "lohn", "arbeitsvertrag",
        "kuendigung", "bewerbung", "urlaub", "krankmeldung", "hr",
        "human resources", "einstellung",
    ],
    Department.GESCHAEFTSFUEHRUNG: [
        "geschaeftsfuehrer", "vorstand", "aufsichtsrat", "strategie",
        "management", "investition", "uebernahme", "merger", "board",
    ],
    Department.IT: [
        "software", "hardware", "server", "netzwerk", "it", "edv",
        "computer", "lizenz", "wartung", "support", "system",
    ],
    Department.LAGER: [
        "lager", "bestand", "inventur", "warenausgang", "kommissionierung",
        "versand", "logistik", "warehouse", "stock",
    ],
    Department.QUALITAET: [
        "qualitaet", "reklamation", "mangel", "pruefung", "zertifikat",
        "audit", "iso", "quality", "defekt", "rueckgabe",
    ],
}

# Dokumenttyp zu Abteilung Mapping
DOCUMENT_TYPE_DEPARTMENT: Dict[str, Department] = {
    "invoice": Department.BUCHHALTUNG,
    "rechnung": Department.BUCHHALTUNG,
    "credit_note": Department.BUCHHALTUNG,
    "gutschrift": Department.BUCHHALTUNG,
    "dunning": Department.BUCHHALTUNG,
    "mahnung": Department.BUCHHALTUNG,
    "offer": Department.VERKAUF,
    "angebot": Department.VERKAUF,
    "order": Department.VERKAUF,
    "auftrag": Department.VERKAUF,
    "delivery_note": Department.LAGER,
    "lieferschein": Department.LAGER,
    "contract": Department.GESCHAEFTSFUEHRUNG,
    "vertrag": Department.GESCHAEFTSFUEHRUNG,
    "correspondence": Department.ALLGEMEIN,
    "korrespondenz": Department.ALLGEMEIN,
}

# Betrags-Schwellen fuer Prioritaet und Eskalation
AMOUNT_THRESHOLDS = {
    "critical": Decimal("50000"),  # >= 50k EUR -> Critical
    "high": Decimal("10000"),  # >= 10k EUR -> High
    "medium": Decimal("1000"),  # >= 1k EUR -> Medium
}


# ============================================================================
# Routing Intelligence Service
# ============================================================================


class RoutingIntelligenceService:
    """Service fuer intelligentes Dokumenten-Routing.

    Analysiert Dokumente und entscheidet automatisch ueber
    Routing, Prioritaet und Eskalation.

    Settings werden aus app.core.config.settings geladen.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._load_config()
        self._custom_rules: List[RoutingRule] = []

    def _load_config(self) -> None:
        """Laedt Konfiguration aus Settings."""
        try:
            from app.core.config import settings

            self.enabled = settings.AUTONOMY_ROUTING_ENABLED
            self.min_confidence = settings.AUTONOMY_ROUTING_MIN_CONFIDENCE
            self.audit_logging = settings.AUTONOMY_AUDIT_LOGGING_ENABLED
        except Exception:
            # Fallback-Defaults
            self.enabled = True
            self.min_confidence = 0.85
            self.audit_logging = True

    async def route_document(
        self,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> RoutingDecision:
        """Bestimmt das Routing fuer ein Dokument.

        Args:
            document_id: ID des Dokuments
            company_id: Optional Company-ID fuer Multi-Tenant

        Returns:
            RoutingDecision mit Ziel und Prioritaet
        """
        if not self.enabled:
            return RoutingDecision(
                document_id=document_id,
                target_type=RoutingTarget.QUEUE,
                target_id="manual_review",
                target_name="Manuelle Pruefung",
                priority=Priority.MEDIUM,
                confidence=0.0,
                reasons=[RoutingReason.DEFAULT],
                explanation="Automatisches Routing ist deaktiviert.",
            )

        # Dokument laden
        stmt = select(Document).where(Document.id == document_id)
        result = await self.db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            logger.warning("routing_document_not_found", document_id=str(document_id))
            return RoutingDecision(
                document_id=document_id,
                target_type=RoutingTarget.QUEUE,
                target_id="error",
                target_name="Fehler",
                priority=Priority.MEDIUM,
                confidence=0.0,
                reasons=[RoutingReason.DEFAULT],
                explanation="Dokument nicht gefunden.",
            )

        # Analyse durchfuehren
        decisions: List[Tuple[RoutingDecision, float]] = []

        # 1. Dokumenttyp-basiertes Routing
        doc_type_decision = await self._route_by_document_type(document)
        if doc_type_decision:
            decisions.append((doc_type_decision, 0.9))

        # 2. Betrags-basiertes Routing
        amount_decision = await self._route_by_amount(document)
        if amount_decision:
            decisions.append((amount_decision, 0.85))

        # 3. Entity-basiertes Routing
        entity_decision = await self._route_by_entity(document)
        if entity_decision:
            decisions.append((entity_decision, 0.8))

        # 4. Keyword-basiertes Routing
        keyword_decision = await self._route_by_keywords(document)
        if keyword_decision:
            decisions.append((keyword_decision, 0.7))

        # 5. Historisches Pattern-Routing
        pattern_decision = await self._route_by_historical_pattern(document)
        if pattern_decision:
            decisions.append((pattern_decision, 0.75))

        # 6. Benutzerdefinierte Regeln
        custom_decision = await self._apply_custom_rules(document)
        if custom_decision:
            decisions.append((custom_decision, 0.95))  # Hohe Prioritaet

        # Beste Entscheidung waehlen
        if not decisions:
            return self._default_routing(document)

        # Sortieren nach Gewichtung und Confidence
        decisions.sort(key=lambda x: x[0].confidence * x[1], reverse=True)
        best_decision = decisions[0][0]

        # Confidence-Check
        if best_decision.confidence < self.min_confidence:
            best_decision.requires_approval = True
            best_decision.explanation += " (Confidence unter Schwellenwert - manuelle Pruefung empfohlen)"

        # Audit-Logging
        if self.audit_logging:
            logger.info(
                "routing_decision_made",
                document_id=str(document_id),
                target_type=best_decision.target_type.value,
                target_id=best_decision.target_id,
                priority=best_decision.priority.value,
                confidence=best_decision.confidence,
                reasons=[r.value for r in best_decision.reasons],
            )

        return best_decision

    async def _route_by_document_type(
        self, document: Document
    ) -> Optional[RoutingDecision]:
        """Routing basierend auf Dokumenttyp."""
        doc_type = document.document_type
        if not doc_type:
            return None

        doc_type_lower = doc_type.lower()
        department = DOCUMENT_TYPE_DEPARTMENT.get(doc_type_lower)

        if not department:
            # Versuche Teiluebereinstimmung
            for key, dept in DOCUMENT_TYPE_DEPARTMENT.items():
                if key in doc_type_lower or doc_type_lower in key:
                    department = dept
                    break

        if not department:
            return None

        return RoutingDecision(
            document_id=document.id,
            target_type=RoutingTarget.DEPARTMENT,
            target_id=department.value,
            target_name=department.value.capitalize(),
            priority=Priority.MEDIUM,
            confidence=0.9,
            reasons=[RoutingReason.DOCUMENT_TYPE],
            explanation=f"Dokumenttyp '{doc_type}' wird von {department.value.capitalize()} bearbeitet.",
        )

    async def _route_by_amount(
        self, document: Document
    ) -> Optional[RoutingDecision]:
        """Routing basierend auf Betrag."""
        # Betrag aus extracted_data holen
        extracted = document.extracted_data or {}
        amount_str = extracted.get("total_amount") or extracted.get("amount")

        if not amount_str:
            return None

        try:
            # Betrag parsen (Format: "1.234,56 EUR" oder "1234.56")
            amount_clean = str(amount_str).replace("EUR", "").replace("€", "").strip()
            amount_clean = amount_clean.replace(".", "").replace(",", ".")
            amount = Decimal(amount_clean)
        except Exception:
            return None

        # Prioritaet basierend auf Betrag
        if amount >= AMOUNT_THRESHOLDS["critical"]:
            priority = Priority.CRITICAL
            target = Department.GESCHAEFTSFUEHRUNG
            explanation = f"Hoher Betrag ({amount:,.2f} EUR) - Geschaeftsfuehrung informiert."
        elif amount >= AMOUNT_THRESHOLDS["high"]:
            priority = Priority.HIGH
            target = Department.BUCHHALTUNG
            explanation = f"Betrag ({amount:,.2f} EUR) erfordert schnelle Bearbeitung."
        elif amount >= AMOUNT_THRESHOLDS["medium"]:
            priority = Priority.MEDIUM
            target = Department.BUCHHALTUNG
            explanation = f"Betrag ({amount:,.2f} EUR) - Standard-Bearbeitung."
        else:
            return None  # Keine spezielle Routing-Entscheidung

        return RoutingDecision(
            document_id=document.id,
            target_type=RoutingTarget.DEPARTMENT,
            target_id=target.value,
            target_name=target.value.capitalize(),
            priority=priority,
            confidence=0.85,
            reasons=[RoutingReason.AMOUNT_THRESHOLD],
            explanation=explanation,
            metadata={"amount": float(amount)},
        )

    async def _route_by_entity(
        self, document: Document
    ) -> Optional[RoutingDecision]:
        """Routing basierend auf verknuepfter Entity."""
        entity_id = document.linked_entity_id
        if not entity_id:
            return None

        # Entity laden
        stmt = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            return None

        # Entity-Typ bestimmt Abteilung
        if entity.entity_type == "customer":
            department = Department.VERKAUF
            explanation = f"Dokument von Kunde '{entity.name}' - Verkauf zustaendig."
        elif entity.entity_type == "supplier":
            department = Department.EINKAUF
            explanation = f"Dokument von Lieferant '{entity.name}' - Einkauf zustaendig."
        else:
            department = Department.ALLGEMEIN
            explanation = f"Dokument verknuepft mit '{entity.name}'."

        return RoutingDecision(
            document_id=document.id,
            target_type=RoutingTarget.DEPARTMENT,
            target_id=department.value,
            target_name=department.value.capitalize(),
            priority=Priority.MEDIUM,
            confidence=0.8,
            reasons=[RoutingReason.ENTITY_ASSIGNMENT],
            explanation=explanation,
            metadata={"entity_id": str(entity.id), "entity_name": entity.name},
        )

    async def _route_by_keywords(
        self, document: Document
    ) -> Optional[RoutingDecision]:
        """Routing basierend auf Keywords im Text."""
        text = (document.extracted_text or "").lower()
        if not text:
            return None

        # Keywords zaehlen pro Abteilung
        department_scores: Dict[Department, int] = {}

        for department, keywords in DEPARTMENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                department_scores[department] = score

        if not department_scores:
            return None

        # Beste Abteilung waehlen
        best_dept = max(department_scores, key=department_scores.get)
        score = department_scores[best_dept]
        total_keywords = sum(len(kws) for kws in DEPARTMENT_KEYWORDS.values())

        # Confidence basierend auf Treffer-Anzahl
        confidence = min(0.5 + (score * 0.1), 0.85)

        return RoutingDecision(
            document_id=document.id,
            target_type=RoutingTarget.DEPARTMENT,
            target_id=best_dept.value,
            target_name=best_dept.value.capitalize(),
            priority=Priority.MEDIUM,
            confidence=confidence,
            reasons=[RoutingReason.KEYWORD_MATCH],
            explanation=f"Keywords deuten auf {best_dept.value.capitalize()} ({score} Treffer).",
            metadata={"keyword_score": score, "matched_department": best_dept.value},
        )

    async def _route_by_historical_pattern(
        self, document: Document
    ) -> Optional[RoutingDecision]:
        """Routing basierend auf historischen Mustern.

        NOTE: Deaktiviert - Folder-Model nicht implementiert.
        """
        # Folder-System nicht verfuegbar
        if Folder is None:
            return None

        doc_type = document.document_type
        if not doc_type:
            return None

        return None  # Folder-basiertes Routing deaktiviert

    async def _apply_custom_rules(
        self, document: Document
    ) -> Optional[RoutingDecision]:
        """Wendet benutzerdefinierte Regeln an."""
        if not self._custom_rules:
            return None

        for rule in sorted(self._custom_rules, key=lambda r: r.priority):
            if not rule.enabled:
                continue

            if self._rule_matches(document, rule.conditions):
                return self._apply_rule_action(document, rule)

        return None

    def _rule_matches(
        self, document: Document, conditions: Dict[str, Any]
    ) -> bool:
        """Prueft ob ein Dokument die Regel-Bedingungen erfuellt."""
        extracted = document.extracted_data or {}

        for key, value in conditions.items():
            if key == "document_type":
                if document.document_type != value:
                    return False
            elif key == "amount_gt":
                amount = extracted.get("total_amount")
                if not amount or Decimal(str(amount)) <= Decimal(str(value)):
                    return False
            elif key == "amount_lt":
                amount = extracted.get("total_amount")
                if not amount or Decimal(str(amount)) >= Decimal(str(value)):
                    return False
            elif key == "entity_type":
                # Wuerde Entity-Lookup erfordern
                pass
            elif key == "contains_keyword":
                text = (document.extracted_text or "").lower()
                if value.lower() not in text:
                    return False

        return True

    def _apply_rule_action(
        self, document: Document, rule: RoutingRule
    ) -> RoutingDecision:
        """Wendet die Aktion einer Regel an."""
        action = rule.action

        target_type = RoutingTarget(action.get("target_type", "department"))
        target_id = action.get("route_to", "allgemein")
        priority = Priority(action.get("priority", "medium"))

        return RoutingDecision(
            document_id=document.id,
            target_type=target_type,
            target_id=target_id,
            target_name=action.get("target_name", target_id.capitalize()),
            priority=priority,
            confidence=0.95,
            reasons=[RoutingReason.EXPLICIT_RULE],
            explanation=f"Regel '{rule.name}' angewendet.",
            metadata={"rule_id": str(rule.id), "rule_name": rule.name},
        )

    def _default_routing(self, document: Document) -> RoutingDecision:
        """Fallback-Routing wenn keine Regel greift."""
        return RoutingDecision(
            document_id=document.id,
            target_type=RoutingTarget.QUEUE,
            target_id="inbox",
            target_name="Posteingang",
            priority=Priority.MEDIUM,
            confidence=0.5,
            reasons=[RoutingReason.DEFAULT],
            explanation="Keine spezifische Zuordnung moeglich - manuelles Routing erforderlich.",
            requires_approval=True,
        )

    def add_custom_rule(self, rule: RoutingRule) -> None:
        """Fuegt eine benutzerdefinierte Regel hinzu."""
        self._custom_rules.append(rule)
        logger.info(
            "routing_rule_added",
            rule_id=str(rule.id),
            rule_name=rule.name,
        )

    def remove_custom_rule(self, rule_id: uuid.UUID) -> bool:
        """Entfernt eine benutzerdefinierte Regel."""
        for i, rule in enumerate(self._custom_rules):
            if rule.id == rule_id:
                del self._custom_rules[i]
                logger.info("routing_rule_removed", rule_id=str(rule_id))
                return True
        return False

    async def get_routing_statistics(
        self,
        company_id: uuid.UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Gibt Routing-Statistiken zurueck.

        Args:
            company_id: Company-ID
            days: Anzahl Tage fuer Statistik

        Returns:
            Dictionary mit Statistiken
        """
        since = utc_now() - timedelta(days=days)

        # Dokumente nach Folder gruppieren (deaktiviert - Folder nicht implementiert)
        folder_distribution: list = []  # Folder-System nicht verfuegbar

        # Dokumente nach Typ gruppieren
        type_stmt = (
            select(
                Document.document_type.label("doc_type"),
                func.count(Document.id).label("count"),
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= since,
                    Document.document_type.isnot(None),
                )
            )
            .group_by(Document.document_type)
            .order_by(desc("count"))
            .limit(10)
        )

        type_result = await self.db.execute(type_stmt)
        type_distribution = [
            {"type": row.doc_type, "count": row.count}
            for row in type_result.fetchall()
        ]

        return {
            "period_days": days,
            "folder_distribution": folder_distribution,
            "type_distribution": type_distribution,
            "custom_rules_count": len(self._custom_rules),
            "routing_enabled": self.enabled,
            "min_confidence": self.min_confidence,
        }


# ============================================================================
# Factory Function
# ============================================================================


def get_routing_intelligence_service(db: AsyncSession) -> RoutingIntelligenceService:
    """Factory-Funktion fuer RoutingIntelligenceService.

    Args:
        db: Async Database Session

    Returns:
        RoutingIntelligenceService Instanz
    """
    return RoutingIntelligenceService(db)
