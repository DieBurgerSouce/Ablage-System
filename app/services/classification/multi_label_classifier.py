# -*- coding: utf-8 -*-
"""
Multi-Label Document Classifier Service.

Kombiniert alle Klassifikations-Dimensionen zu einer einheitlichen
Dokumenten-Klassifikation:
- Dokumenttyp (Invoice, Contract, etc.)
- Dringlichkeit (Immediate, Normal, CanWait)
- Abteilung (Buchhaltung, Einkauf, Vertrieb, etc.)
- Vertraulichkeit (Public, Internal, Confidential, etc.)

Feinpoliert und durchdacht.
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.api.schemas.extracted_data import (
    DocumentClassificationResult,
    ExtractedDocumentType,
)
from app.services.document_classification_service import (
    get_classification_service,
)
from app.services.classification.urgency_classifier import (
    get_urgency_classifier,
    UrgencyLevel,
    UrgencyClassificationResult,
)
from app.services.classification.department_router import (
    get_department_router,
    Department,
    DepartmentRoutingResult,
)
from app.services.classification.confidentiality_classifier import (
    get_confidentiality_classifier,
    ConfidentialityLevel,
    ConfidentialityClassificationResult,
)

logger = structlog.get_logger(__name__)


@dataclass
class MultiLabelClassificationResult:
    """Vollständiges Multi-Label Klassifikationsergebnis."""

    # Dokumenttyp
    document_type: ExtractedDocumentType
    document_type_confidence: float
    document_type_alternatives: List[str]

    # Dringlichkeit
    urgency_level: UrgencyLevel
    urgency_confidence: float
    deadline: Optional[datetime]
    days_until_deadline: Optional[int]

    # Abteilung
    primary_department: Department
    department_confidence: float
    secondary_departments: List[Department]
    requires_cfo_approval: bool

    # Vertraulichkeit
    confidentiality_level: ConfidentialityLevel
    confidentiality_confidence: float
    detected_pii_types: List[str]
    requires_encryption: bool
    access_restriction: str

    # Gesamtbild
    overall_confidence: float
    classification_summary: str
    matched_indicators: Dict[str, List[str]] = field(default_factory=dict)
    processing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API-Response."""
        return {
            "document_type": {
                "type": self.document_type.value,
                "confidence": self.document_type_confidence,
                "alternatives": self.document_type_alternatives,
            },
            "urgency": {
                "level": self.urgency_level.value,
                "confidence": self.urgency_confidence,
                "deadline": self.deadline.isoformat() if self.deadline else None,
                "days_until_deadline": self.days_until_deadline,
            },
            "department": {
                "primary": self.primary_department.value,
                "confidence": self.department_confidence,
                "secondary": [d.value for d in self.secondary_departments],
                "requires_cfo_approval": self.requires_cfo_approval,
            },
            "confidentiality": {
                "level": self.confidentiality_level.value,
                "confidence": self.confidentiality_confidence,
                "detected_pii_types": self.detected_pii_types,
                "requires_encryption": self.requires_encryption,
                "access_restriction": self.access_restriction,
            },
            "overall": {
                "confidence": self.overall_confidence,
                "summary": self.classification_summary,
                "matched_indicators": self.matched_indicators,
                "processing_time_ms": self.processing_time_ms,
            },
        }

    def to_metadata(self) -> Dict[str, Any]:
        """Konvertiere zu kompaktem Metadata-Format für Dokument-Speicherung."""
        return {
            "document_type": self.document_type.value,
            "document_type_confidence": self.document_type_confidence,
            "urgency_level": self.urgency_level.value,
            "urgency_confidence": self.urgency_confidence,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "days_until_deadline": self.days_until_deadline,
            "primary_department": self.primary_department.value,
            "department_confidence": self.department_confidence,
            "secondary_departments": [d.value for d in self.secondary_departments],
            "confidentiality_level": self.confidentiality_level.value,
            "confidentiality_confidence": self.confidentiality_confidence,
            "detected_pii_types": self.detected_pii_types,
            "requires_encryption": self.requires_encryption,
            "requires_cfo_approval": self.requires_cfo_approval,
            "overall_confidence": self.overall_confidence,
        }


class MultiLabelClassifier:
    """
    Kombinierter Multi-Label Classifier.

    Orchestriert alle Einzelklassifizierer und kombiniert die Ergebnisse.
    Performance: < 50ms pro Dokument (alle 4 Dimensionen)
    """

    def __init__(self) -> None:
        """Initialisiere den Multi-Label Classifier."""
        self.doc_type_classifier = get_classification_service()
        self.urgency_classifier = get_urgency_classifier()
        self.department_router = get_department_router()
        self.confidentiality_classifier = get_confidentiality_classifier()

        self._stats = {
            "total_classifications": 0,
            "avg_processing_time_ms": 0.0,
        }

    def classify(
        self,
        text: str,
        document_date: Optional[datetime] = None,
        amount: Optional[Decimal] = None,
        is_incoming: bool = True,
    ) -> MultiLabelClassificationResult:
        """
        Führe vollständige Multi-Label Klassifikation durch.

        Args:
            text: OCR-Text des Dokuments
            document_date: Optionales Dokumentdatum
            amount: Optionaler Betrag (für CFO-Approval und Department-Routing)
            is_incoming: True für eingehende, False für ausgehende Dokumente

        Returns:
            MultiLabelClassificationResult mit allen Dimensionen
        """
        import time
        start_time = time.time()

        self._stats["total_classifications"] += 1

        # 1. Dokumenttyp klassifizieren
        doc_type_result = self.doc_type_classifier.classify(text)

        # 2. Dringlichkeit klassifizieren
        urgency_result = self.urgency_classifier.classify(
            text=text,
            document_type=doc_type_result.document_type.value if doc_type_result.document_type else None,
            document_date=document_date,
        )

        # 3. Abteilung routen
        department_result = self.department_router.route(
            text=text,
            document_type=doc_type_result.document_type.value if doc_type_result.document_type else None,
            amount=amount,
            is_incoming=is_incoming,
        )

        # 4. Vertraulichkeit klassifizieren
        confidentiality_result = self.confidentiality_classifier.classify(
            text=text,
            document_type=doc_type_result.document_type.value if doc_type_result.document_type else None,
        )

        # Processing-Zeit berechnen
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Statistik aktualisieren
        self._stats["avg_processing_time_ms"] = (
            (self._stats["avg_processing_time_ms"] * (self._stats["total_classifications"] - 1) + processing_time_ms)
            / self._stats["total_classifications"]
        )

        # Gesamtconfidence berechnen (gewichteter Durchschnitt)
        overall_confidence = (
            doc_type_result.confidence * 0.3 +
            urgency_result.confidence * 0.2 +
            department_result.confidence * 0.25 +
            confidentiality_result.confidence * 0.25
        )

        # Summary generieren
        summary = self._generate_summary(
            doc_type_result,
            urgency_result,
            department_result,
            confidentiality_result,
        )

        # Matched Indicators sammeln
        matched_indicators = {
            "document_type": doc_type_result.matched_keywords[:5] if doc_type_result.matched_keywords else [],
            "urgency": urgency_result.matched_indicators[:5],
            "department": department_result.matched_indicators[:5],
            "confidentiality": confidentiality_result.matched_indicators[:5],
        }

        # Alternatives für Dokumenttyp
        alternatives = []
        if doc_type_result.alternative_type:
            alternatives.append(doc_type_result.alternative_type.value)

        logger.info(
            "multi_label_classification_complete",
            document_type=doc_type_result.document_type.value,
            urgency=urgency_result.urgency_level.value,
            department=department_result.primary_department.value,
            confidentiality=confidentiality_result.level.value,
            overall_confidence=round(overall_confidence, 3),
            processing_time_ms=processing_time_ms,
        )

        return MultiLabelClassificationResult(
            # Dokumenttyp
            document_type=doc_type_result.document_type,
            document_type_confidence=doc_type_result.confidence,
            document_type_alternatives=alternatives,
            # Dringlichkeit
            urgency_level=urgency_result.urgency_level,
            urgency_confidence=urgency_result.confidence,
            deadline=urgency_result.deadline,
            days_until_deadline=urgency_result.days_until_deadline,
            # Abteilung
            primary_department=department_result.primary_department,
            department_confidence=department_result.confidence,
            secondary_departments=department_result.secondary_departments,
            requires_cfo_approval=department_result.requires_cfo_approval,
            # Vertraulichkeit
            confidentiality_level=confidentiality_result.level,
            confidentiality_confidence=confidentiality_result.confidence,
            detected_pii_types=confidentiality_result.detected_pii_types,
            requires_encryption=confidentiality_result.requires_encryption,
            access_restriction=confidentiality_result.access_restriction,
            # Gesamt
            overall_confidence=round(overall_confidence, 4),
            classification_summary=summary,
            matched_indicators=matched_indicators,
            processing_time_ms=processing_time_ms,
        )

    def _generate_summary(
        self,
        doc_type_result: DocumentClassificationResult,
        urgency_result: UrgencyClassificationResult,
        department_result: DepartmentRoutingResult,
        confidentiality_result: ConfidentialityClassificationResult,
    ) -> str:
        """Generiere menschenlesbare Zusammenfassung."""
        parts = []

        # Dokumenttyp
        type_names = {
            ExtractedDocumentType.INVOICE: "Rechnung",
            ExtractedDocumentType.ORDER: "Bestellung",
            ExtractedDocumentType.CONTRACT: "Vertrag",
            ExtractedDocumentType.DELIVERY_NOTE: "Lieferschein",
            ExtractedDocumentType.OFFER: "Angebot",
            ExtractedDocumentType.DUNNING: "Mahnung",
            ExtractedDocumentType.CREDIT_NOTE: "Gutschrift",
            ExtractedDocumentType.RECEIPT: "Quittung",
            ExtractedDocumentType.BANK_STATEMENT: "Kontoauszug",
            ExtractedDocumentType.TAX_DOCUMENT: "Steuerdokument",
            ExtractedDocumentType.LETTER: "Brief",
            ExtractedDocumentType.FORM: "Formular",
            ExtractedDocumentType.REPORT: "Bericht",
            ExtractedDocumentType.PURCHASE_ORDER: "Bestellauftrag",
            ExtractedDocumentType.UNKNOWN: "Unbekannt",
        }
        type_name = type_names.get(doc_type_result.document_type, doc_type_result.document_type.value)
        parts.append(type_name)

        # Dringlichkeit
        urgency_names = {
            UrgencyLevel.IMMEDIATE: "dringend",
            UrgencyLevel.NORMAL: "normal",
            UrgencyLevel.CAN_WAIT: "niedrig priorisiert",
        }
        parts.append(urgency_names.get(urgency_result.urgency_level, ""))

        # Abteilung
        dept_names = {
            Department.BUCHHALTUNG: "Buchhaltung",
            Department.EINKAUF: "Einkauf",
            Department.VERTRIEB: "Vertrieb",
            Department.HR: "Personal",
            Department.GESCHAEFTSFUEHRUNG: "Geschäftsführung",
            Department.IT: "IT",
            Department.RECHT: "Rechtsabteilung",
            Department.ALLGEMEIN: "Allgemein",
        }
        dept_name = dept_names.get(department_result.primary_department, "")
        parts.append(f"für {dept_name}")

        # Vertraulichkeit
        conf_names = {
            ConfidentialityLevel.PUBLIC: "öffentlich",
            ConfidentialityLevel.INTERNAL: "intern",
            ConfidentialityLevel.CONFIDENTIAL: "vertraulich",
            ConfidentialityLevel.STRICTLY_CONFIDENTIAL: "streng vertraulich",
        }
        conf_name = conf_names.get(confidentiality_result.level, "")
        parts.append(f"({conf_name})")

        return " ".join(filter(None, parts))

    def classify_batch(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[MultiLabelClassificationResult]:
        """
        Klassifiziere mehrere Dokumente.

        Args:
            documents: Liste von Dicts mit 'text', optional 'date', 'amount', 'is_incoming'

        Returns:
            Liste von Klassifikationsergebnissen
        """
        results = []
        for doc in documents:
            result = self.classify(
                text=doc.get("text", ""),
                document_date=doc.get("date"),
                amount=doc.get("amount"),
                is_incoming=doc.get("is_incoming", True),
            )
            results.append(result)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Gibt kombinierte Statistiken zurück."""
        return {
            "multi_label": self._stats.copy(),
            "document_type": self.doc_type_classifier.get_stats(),
            "urgency": self.urgency_classifier.get_stats(),
            "department": self.department_router.get_stats(),
            "confidentiality": self.confidentiality_classifier.get_stats(),
        }

    def reset_stats(self) -> None:
        """Setzt alle Statistiken zurück."""
        self._stats = {
            "total_classifications": 0,
            "avg_processing_time_ms": 0.0,
        }
        self.doc_type_classifier.reset_stats()
        self.urgency_classifier.reset_stats()
        self.department_router.reset_stats()
        self.confidentiality_classifier.reset_stats()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_multi_label_classifier: Optional[MultiLabelClassifier] = None


def get_multi_label_classifier() -> MultiLabelClassifier:
    """Gibt die Singleton-Instanz des Multi-Label Classifier zurück."""
    global _multi_label_classifier
    if _multi_label_classifier is None:
        _multi_label_classifier = MultiLabelClassifier()
    return _multi_label_classifier
