# -*- coding: utf-8 -*-
"""
Document Pipeline Orchestrator - Zero-Touch Document Processing.

Das Herzstück der vollautomatischen Dokumentenverarbeitung:
- OCR → Klassifizierung → Entity-Linking → Projekt-Zuweisung → Kategorisierung → Workflow

Philosophie: 85% Confidence-Schwelle für automatische Verarbeitung
Alle Entscheidungen sind erklärbar und nachvollziehbar.

Vision 2026 Q2 - Smart Document Router
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

PIPELINE_DOCUMENTS_PROCESSED = Counter(
    "pipeline_documents_processed_total",
    "Anzahl verarbeiteter Dokumente",
    ["result"]  # auto, manual_review, failed
)

PIPELINE_STEP_LATENCY = Histogram(
    "pipeline_step_latency_seconds",
    "Latenz pro Pipeline-Schritt",
    ["step"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)

PIPELINE_CONFIDENCE_SCORES = Histogram(
    "pipeline_confidence_scores",
    "Verteilung der Confidence-Scores",
    ["step"],
    buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
)

PIPELINE_QUEUE_SIZE = Gauge(
    "pipeline_queue_size",
    "Anzahl Dokumente in der Pipeline-Queue"
)


# =============================================================================
# Enums und Typen
# =============================================================================

class PipelineStep(str, Enum):
    """Schritte in der Document Pipeline."""
    OCR = "ocr"
    CLASSIFY = "classify"
    EXTRACT_ENTITIES = "extract_entities"
    LINK_ENTITY = "link_entity"
    ASSIGN_PROJECT = "assign_project"
    CATEGORIZE = "categorize"
    ANOMALY_CHECK = "anomaly_check"
    WORKFLOW_TRIGGER = "workflow_trigger"


class PipelineStatus(str, Enum):
    """Status der Pipeline-Verarbeitung."""
    PENDING = "pending"
    PROCESSING = "processing"
    AUTO_COMPLETED = "auto_completed"
    REQUIRES_REVIEW = "requires_review"
    FAILED = "failed"


class DecisionConfidence(str, Enum):
    """Konfidenz-Level für Entscheidungen."""
    AUTO = "auto"          # >= 85% - Automatische Verarbeitung
    SUGGEST = "suggest"    # 70-85% - Vorschlag, manuelle Bestätigung
    MANUAL = "manual"      # < 70% - Manuelle Bearbeitung erforderlich


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PipelineDecision:
    """Eine einzelne Entscheidung in der Pipeline."""
    id: UUID = field(default_factory=uuid4)
    step: PipelineStep = PipelineStep.CLASSIFY

    # Ergebnis
    action: str = ""                       # z.B. "classify", "link_entity"
    result: Any = None                     # Das Ergebnis der Entscheidung
    confidence: float = 0.0                # 0.0 - 1.0
    confidence_level: DecisionConfidence = DecisionConfidence.MANUAL

    # Erklärung (Explainability)
    explanation: str = ""                  # Menschenlesbare Erklärung
    factors: List[Dict[str, Any]] = field(default_factory=list)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    processing_time_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "step": self.step.value,
            "action": self.action,
            "result": self.result,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "explanation": self.explanation,
            "factors": self.factors,
            "alternatives": self.alternatives,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AnomalyResult:
    """Ergebnis der Anomalie-Erkennung."""
    type: str                              # "duplicate", "amount_unusual", etc.
    severity: str                          # "info", "warning", "high", "critical"
    confidence: float = 0.0
    explanation: str = ""
    recommendation: str = ""
    related_document_id: Optional[UUID] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "type": self.type,
            "severity": self.severity,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
            "related_document_id": str(self.related_document_id) if self.related_document_id else None,
        }


@dataclass
class PipelineResult:
    """Vollständiges Ergebnis der Pipeline-Verarbeitung."""
    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)

    # Status
    status: PipelineStatus = PipelineStatus.PENDING
    auto_processed: bool = False           # True wenn alle Schritte > 85% Confidence

    # Entscheidungen
    decisions: List[PipelineDecision] = field(default_factory=list)

    # Ergebnisse der einzelnen Schritte
    document_type: Optional[str] = None
    document_type_confidence: float = 0.0

    linked_entity_id: Optional[UUID] = None
    linked_entity_name: Optional[str] = None
    entity_link_confidence: float = 0.0

    assigned_project_id: Optional[UUID] = None
    assigned_project_name: Optional[str] = None
    project_assignment_confidence: float = 0.0

    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    category_confidence: float = 0.0

    # Anomalien
    anomalies: List[AnomalyResult] = field(default_factory=list)

    # Workflow
    triggered_workflows: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    total_processing_time_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    # Flags
    requires_review: bool = False
    review_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für API."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "status": self.status.value,
            "auto_processed": self.auto_processed,
            "decisions": [d.to_dict() for d in self.decisions],
            "document_type": self.document_type,
            "document_type_confidence": self.document_type_confidence,
            "linked_entity": {
                "id": str(self.linked_entity_id) if self.linked_entity_id else None,
                "name": self.linked_entity_name,
                "confidence": self.entity_link_confidence,
            } if self.linked_entity_id else None,
            "assigned_project": {
                "id": str(self.assigned_project_id) if self.assigned_project_id else None,
                "name": self.assigned_project_name,
                "confidence": self.project_assignment_confidence,
            } if self.assigned_project_id else None,
            "category": {
                "id": str(self.category_id) if self.category_id else None,
                "name": self.category_name,
                "confidence": self.category_confidence,
            } if self.category_id else None,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "triggered_workflows": self.triggered_workflows,
            "total_processing_time_ms": self.total_processing_time_ms,
            "requires_review": self.requires_review,
            "review_reasons": self.review_reasons,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# =============================================================================
# Document Pipeline Orchestrator
# =============================================================================

class DocumentPipelineOrchestrator:
    """
    Orchestriert die vollautomatische Dokumentenverarbeitung.

    Pipeline-Schritte:
    1. OCR (bereits vorhanden, wird referenziert)
    2. Dokumententyp-Klassifikation
    3. Entity-Extraktion & Linking
    4. Projekt/Kostenstellen-Zuweisung
    5. Auto-Kategorisierung & Ablage
    6. Workflow-Trigger
    7. Anomalie-Check

    Confidence-Schwelle: 85% (moderat) für automatische Verarbeitung
    """

    # Confidence Thresholds
    AUTO_THRESHOLD = 0.85      # Automatische Verarbeitung
    SUGGEST_THRESHOLD = 0.70   # Vorschlag mit Review

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Pipeline Orchestrator."""
        self.db = db

        # Services werden lazy geladen
        self._classification_service = None
        self._entity_linker_service = None
        self._project_service = None
        self._anomaly_service = None
        self._workflow_service = None

    # =========================================================================
    # Main Processing
    # =========================================================================

    async def process_document(
        self,
        document_id: UUID,
        ocr_text: str,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """
        Verarbeitet ein Dokument durch die komplette Pipeline.

        Args:
            document_id: ID des Dokuments
            ocr_text: Extrahierter Text aus OCR
            company_id: Mandant-ID
            user_id: Optional - User der das Dokument hochgeladen hat
            metadata: Optional - Zusätzliche Metadaten (Dateiname, etc.)

        Returns:
            PipelineResult mit allen Entscheidungen und Ergebnissen
        """
        start_time = datetime.now(timezone.utc)
        result = PipelineResult(document_id=document_id)
        result.status = PipelineStatus.PROCESSING

        PIPELINE_QUEUE_SIZE.inc()

        try:
            # 1. Dokumententyp klassifizieren
            classification_decision = await self._classify_document(
                document_id, ocr_text, metadata
            )
            result.decisions.append(classification_decision)
            result.document_type = classification_decision.result
            result.document_type_confidence = classification_decision.confidence

            # 2. Entity-Linking
            entity_decision = await self._link_entity(
                document_id, ocr_text, company_id
            )
            result.decisions.append(entity_decision)
            if entity_decision.result:
                result.linked_entity_id = entity_decision.result.get("entity_id")
                result.linked_entity_name = entity_decision.result.get("entity_name")
                result.entity_link_confidence = entity_decision.confidence

            # 3. Projekt-Zuweisung
            project_decision = await self._assign_project(
                document_id,
                result.document_type,
                result.linked_entity_id,
                company_id,
            )
            result.decisions.append(project_decision)
            if project_decision.result:
                result.assigned_project_id = project_decision.result.get("project_id")
                result.assigned_project_name = project_decision.result.get("project_name")
                result.project_assignment_confidence = project_decision.confidence

            # 4. Kategorisierung
            category_decision = await self._categorize_document(
                document_id,
                result.document_type,
                result.linked_entity_id,
                metadata,
            )
            result.decisions.append(category_decision)
            if category_decision.result:
                result.category_id = category_decision.result.get("category_id")
                result.category_name = category_decision.result.get("category_name")
                result.category_confidence = category_decision.confidence

            # 5. Anomalie-Check
            anomalies = await self._check_anomalies(
                document_id,
                ocr_text,
                result.document_type,
                result.linked_entity_id,
                company_id,
            )
            result.anomalies = anomalies

            # 6. Workflow-Trigger (nur bei ausreichender Confidence)
            if self._should_trigger_workflows(result):
                workflows = await self._trigger_matching_workflows(
                    document_id,
                    result.document_type,
                    result.linked_entity_id,
                    anomalies,
                    company_id,
                )
                result.triggered_workflows = workflows

            # Finale Auswertung
            result = self._evaluate_pipeline_result(result)

            # Timing
            end_time = datetime.now(timezone.utc)
            result.total_processing_time_ms = int(
                (end_time - start_time).total_seconds() * 1000
            )
            result.completed_at = end_time

            # Metriken
            status_label = "auto" if result.auto_processed else (
                "manual_review" if result.requires_review else "completed"
            )
            PIPELINE_DOCUMENTS_PROCESSED.labels(result=status_label).inc()

            logger.info(
                "document_pipeline_completed",
                document_id=str(document_id),
                status=result.status.value,
                auto_processed=result.auto_processed,
                decisions_count=len(result.decisions),
                anomalies_count=len(result.anomalies),
                processing_time_ms=result.total_processing_time_ms,
            )

            return result

        except Exception as e:
            result.status = PipelineStatus.FAILED
            result.requires_review = True
            result.review_reasons.append(safe_error_detail(e, "Pipeline"))

            PIPELINE_DOCUMENTS_PROCESSED.labels(result="failed").inc()

            logger.error(
                "document_pipeline_failed",
                document_id=str(document_id),
                **safe_error_log(e),
                exc_info=True,
            )

            return result

        finally:
            PIPELINE_QUEUE_SIZE.dec()

    # =========================================================================
    # Step 1: Document Classification
    # =========================================================================

    async def _classify_document(
        self,
        document_id: UUID,
        ocr_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PipelineDecision:
        """Klassifiziert den Dokumententyp."""
        start_time = datetime.now(timezone.utc)

        decision = PipelineDecision(
            step=PipelineStep.CLASSIFY,
            action="classify_document_type",
        )

        try:
            from app.services.document_classification_service import (
                DocumentClassificationService,
            )

            classifier = DocumentClassificationService()
            classification = classifier.classify(ocr_text)

            decision.result = classification.document_type.value
            decision.confidence = classification.confidence
            decision.confidence_level = self._get_confidence_level(classification.confidence)

            # Erklärung generieren
            decision.explanation = self._generate_classification_explanation(
                classification
            )

            # Faktoren
            decision.factors = [
                {
                    "name": "Dokumenttyp",
                    "value": classification.document_type.value,
                    "contribution": classification.confidence,
                },
                {
                    "name": "Primäre Keywords",
                    "value": classification.matched_keywords[:5] if classification.matched_keywords else [],
                    "contribution": 0.6,
                },
            ]

            # Alternativen
            if classification.alternatives:
                decision.alternatives = [
                    {
                        "type": alt.document_type.value,
                        "confidence": alt.confidence,
                        "reason": f"Confidence: {alt.confidence*100:.0f}%",
                    }
                    for alt in classification.alternatives[:3]
                ]

            # Metriken
            PIPELINE_CONFIDENCE_SCORES.labels(step="classify").observe(decision.confidence)

        except Exception as e:
            decision.confidence = 0.0
            decision.confidence_level = DecisionConfidence.MANUAL
            decision.explanation = f"Klassifikation fehlgeschlagen: {str(e)}"
            logger.error("pipeline_classify_error", **safe_error_log(e))

        # Timing
        end_time = datetime.now(timezone.utc)
        decision.processing_time_ms = int(
            (end_time - start_time).total_seconds() * 1000
        )
        PIPELINE_STEP_LATENCY.labels(step="classify").observe(
            decision.processing_time_ms / 1000
        )

        return decision

    def _generate_classification_explanation(self, classification) -> str:
        """Generiert Erklärung für Dokumentklassifikation."""
        doc_type = classification.document_type.value
        confidence = classification.confidence * 100

        keywords = classification.matched_keywords[:3] if classification.matched_keywords else []
        keyword_str = ", ".join(keywords) if keywords else "keine spezifischen"

        return (
            f"Erkannt als {doc_type}: {keyword_str} Keywords gefunden. "
            f"Konfidenz: {confidence:.0f}%"
        )

    # =========================================================================
    # Step 2: Entity Linking
    # =========================================================================

    async def _link_entity(
        self,
        document_id: UUID,
        ocr_text: str,
        company_id: UUID,
    ) -> PipelineDecision:
        """Verknüpft Dokument mit BusinessEntity."""
        start_time = datetime.now(timezone.utc)

        decision = PipelineDecision(
            step=PipelineStep.LINK_ENTITY,
            action="link_to_entity",
        )

        try:
            from app.services.document_entity_linker_service import (
                DocumentEntityLinkerService,
            )

            linker = DocumentEntityLinkerService(self.db)
            match = await linker.find_best_match(ocr_text, company_id)

            if match:
                decision.result = {
                    "entity_id": match.entity.id,
                    "entity_name": match.entity.name,
                    "match_type": match.match_type,
                }
                decision.confidence = match.confidence
                decision.confidence_level = self._get_confidence_level(match.confidence)

                # Erklärung
                decision.explanation = (
                    f"Zugeordnet zu '{match.entity.name}': "
                    f"{match.match_details} ({match.match_type})"
                )

                decision.factors = [
                    {
                        "name": "Match-Strategie",
                        "value": match.match_type,
                        "contribution": match.confidence,
                    },
                    {
                        "name": "Entity-Name",
                        "value": match.entity.name,
                        "contribution": 1.0,
                    },
                ]
            else:
                decision.result = None
                decision.confidence = 0.0
                decision.confidence_level = DecisionConfidence.MANUAL
                decision.explanation = "Keine passende Entity gefunden"

            PIPELINE_CONFIDENCE_SCORES.labels(step="link_entity").observe(
                decision.confidence
            )

        except Exception as e:
            decision.confidence = 0.0
            decision.confidence_level = DecisionConfidence.MANUAL
            decision.explanation = f"Entity-Linking fehlgeschlagen: {str(e)}"
            logger.error("pipeline_link_entity_error", **safe_error_log(e))

        # Timing
        end_time = datetime.now(timezone.utc)
        decision.processing_time_ms = int(
            (end_time - start_time).total_seconds() * 1000
        )
        PIPELINE_STEP_LATENCY.labels(step="link_entity").observe(
            decision.processing_time_ms / 1000
        )

        return decision

    # =========================================================================
    # Step 3: Project Assignment
    # =========================================================================

    async def _assign_project(
        self,
        document_id: UUID,
        document_type: Optional[str],
        entity_id: Optional[UUID],
        company_id: UUID,
    ) -> PipelineDecision:
        """Weist Dokument einem Projekt zu."""
        start_time = datetime.now(timezone.utc)

        decision = PipelineDecision(
            step=PipelineStep.ASSIGN_PROJECT,
            action="assign_to_project",
        )

        try:
            from app.services.project_service import ProjectService

            project_service = ProjectService(self.db)
            suggestion = await project_service.suggest_project_for_document(
                document_id=document_id,
                document_type=document_type,
                entity_id=entity_id,
                company_id=company_id,
            )

            if suggestion:
                decision.result = {
                    "project_id": suggestion["project_id"],
                    "project_name": suggestion["project_name"],
                    "match_reason": suggestion["match_reason"],
                }
                decision.confidence = suggestion["confidence"]
                decision.confidence_level = self._get_confidence_level(
                    suggestion["confidence"]
                )

                decision.explanation = (
                    f"Projekt '{suggestion['project_name']}' vorgeschlagen: "
                    f"{suggestion['match_reason']}"
                )

                decision.factors = [
                    {
                        "name": "Match-Strategie",
                        "value": suggestion["match_reason"],
                        "contribution": suggestion["confidence"],
                    },
                ]
            else:
                decision.result = None
                decision.confidence = 0.0
                decision.confidence_level = DecisionConfidence.MANUAL
                decision.explanation = "Kein passendes Projekt gefunden"

            PIPELINE_CONFIDENCE_SCORES.labels(step="assign_project").observe(
                decision.confidence
            )

        except Exception as e:
            decision.confidence = 0.0
            decision.confidence_level = DecisionConfidence.MANUAL
            decision.explanation = f"Projekt-Zuweisung fehlgeschlagen: {str(e)}"
            logger.error("pipeline_assign_project_error", **safe_error_log(e))

        # Timing
        end_time = datetime.now(timezone.utc)
        decision.processing_time_ms = int(
            (end_time - start_time).total_seconds() * 1000
        )
        PIPELINE_STEP_LATENCY.labels(step="assign_project").observe(
            decision.processing_time_ms / 1000
        )

        return decision

    # =========================================================================
    # Step 4: Categorization
    # =========================================================================

    async def _categorize_document(
        self,
        document_id: UUID,
        document_type: Optional[str],
        entity_id: Optional[UUID],
        metadata: Optional[Dict[str, Any]],
    ) -> PipelineDecision:
        """Kategorisiert das Dokument für die Ablage."""
        start_time = datetime.now(timezone.utc)

        decision = PipelineDecision(
            step=PipelineStep.CATEGORIZE,
            action="categorize_document",
        )

        try:
            # Kategorisierung basierend auf Dokumenttyp
            category_mapping = {
                "invoice": ("Rechnungen", 0.95),
                "order": ("Bestellungen", 0.95),
                "contract": ("Verträge", 0.95),
                "delivery_note": ("Lieferscheine", 0.90),
                "receipt": ("Quittungen", 0.90),
                "bank_statement": ("Kontoauszüge", 0.95),
                "tax_document": ("Steuer", 0.95),
                "letter": ("Korrespondenz", 0.80),
            }

            if document_type and document_type.lower() in category_mapping:
                category_name, confidence = category_mapping[document_type.lower()]

                decision.result = {
                    "category_name": category_name,
                }
                decision.confidence = confidence
                decision.confidence_level = self._get_confidence_level(confidence)
                decision.explanation = (
                    f"Kategorisiert als '{category_name}' "
                    f"basierend auf Dokumenttyp '{document_type}'"
                )
            else:
                decision.result = {
                    "category_name": "Sonstige",
                }
                decision.confidence = 0.5
                decision.confidence_level = DecisionConfidence.MANUAL
                decision.explanation = (
                    "Keine automatische Kategorie zuweisbar, "
                    "Standardkategorie 'Sonstige' verwendet"
                )

            PIPELINE_CONFIDENCE_SCORES.labels(step="categorize").observe(
                decision.confidence
            )

        except Exception as e:
            decision.confidence = 0.0
            decision.confidence_level = DecisionConfidence.MANUAL
            decision.explanation = f"Kategorisierung fehlgeschlagen: {str(e)}"
            logger.error("pipeline_categorize_error", **safe_error_log(e))

        # Timing
        end_time = datetime.now(timezone.utc)
        decision.processing_time_ms = int(
            (end_time - start_time).total_seconds() * 1000
        )
        PIPELINE_STEP_LATENCY.labels(step="categorize").observe(
            decision.processing_time_ms / 1000
        )

        return decision

    # =========================================================================
    # Step 5: Anomaly Detection
    # =========================================================================

    async def _check_anomalies(
        self,
        document_id: UUID,
        ocr_text: str,
        document_type: Optional[str],
        entity_id: Optional[UUID],
        company_id: UUID,
    ) -> List[AnomalyResult]:
        """Prüft auf Anomalien im Dokument."""
        start_time = datetime.now(timezone.utc)
        anomalies: List[AnomalyResult] = []

        try:
            # Duplikat-Check
            duplicate = await self._check_duplicate(
                document_id, ocr_text, company_id
            )
            if duplicate:
                anomalies.append(duplicate)

            # Betrags-Check (nur für Rechnungen)
            if document_type and document_type.lower() == "invoice" and entity_id:
                amount_anomaly = await self._check_amount_anomaly(
                    ocr_text, entity_id
                )
                if amount_anomaly:
                    anomalies.append(amount_anomaly)

            # Timing
            end_time = datetime.now(timezone.utc)
            latency = (end_time - start_time).total_seconds()
            PIPELINE_STEP_LATENCY.labels(step="anomaly_check").observe(latency)

        except Exception as e:
            logger.error("pipeline_anomaly_check_error", **safe_error_log(e))

        return anomalies

    async def _check_duplicate(
        self,
        document_id: UUID,
        ocr_text: str,
        company_id: UUID,
    ) -> Optional[AnomalyResult]:
        """Prüft auf mögliche Duplikate."""
        try:
            from app.db.models import Document
            import hashlib

            # Einfacher Hash-basierter Check
            text_hash = hashlib.sha256(ocr_text.encode()).hexdigest()[:32]

            # Suche nach Dokumenten mit ähnlichem Hash
            stmt = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.id != document_id,
                    Document.content_hash == text_hash,
                )
            )

            result = await self.db.execute(stmt)
            existing = result.scalars().first()

            if existing:
                return AnomalyResult(
                    type="duplicate_invoice",
                    severity="high",
                    confidence=0.92,
                    explanation=(
                        f"Ähnliches Dokument gefunden: {existing.id} "
                        f"(gleicher Content-Hash)"
                    ),
                    recommendation="Prüfen ob Doppelbuchung",
                    related_document_id=existing.id,
                )

        except Exception as e:
            logger.warning("duplicate_check_failed", **safe_error_log(e))

        return None

    async def _check_amount_anomaly(
        self,
        ocr_text: str,
        entity_id: UUID,
    ) -> Optional[AnomalyResult]:
        """Prüft auf ungewöhnliche Beträge."""
        try:
            import re
            from decimal import Decimal

            # Betrag aus Text extrahieren
            amount_pattern = r'(?:Gesamt|Summe|Total|Brutto)[:\s]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:€|EUR)'
            match = re.search(amount_pattern, ocr_text, re.IGNORECASE)

            if not match:
                return None

            # Betrag parsen
            amount_str = match.group(1).replace('.', '').replace(',', '.')
            amount = Decimal(amount_str)

            # Historischen Durchschnitt für Entity abrufen
            from app.db.models import InvoiceTracking


            stmt = select(InvoiceTracking.gross_amount).where(
                InvoiceTracking.business_entity_id == entity_id
            ).limit(10)

            result = await self.db.execute(stmt)
            historical = [row[0] for row in result.fetchall() if row[0]]

            if historical:
                avg = sum(historical) / len(historical)
                deviation = abs(float(amount) - float(avg)) / float(avg) * 100

                if deviation > 50:  # Mehr als 50% Abweichung
                    return AnomalyResult(
                        type="unusual_amount",
                        severity="warning" if deviation < 100 else "high",
                        confidence=0.78,
                        explanation=(
                            f"Betrag {amount:.2f} EUR weicht um {deviation:.0f}% "
                            f"vom Durchschnitt ({avg:.2f} EUR) ab"
                        ),
                        recommendation="Manuell prüfen ob Betrag korrekt",
                    )

        except Exception as e:
            logger.warning("amount_anomaly_check_failed", **safe_error_log(e))

        return None

    # =========================================================================
    # Step 6: Workflow Triggers
    # =========================================================================

    def _should_trigger_workflows(self, result: PipelineResult) -> bool:
        """Entscheidet ob Workflows getriggert werden sollen."""
        # Nur bei ausreichender Confidence triggern
        return (
            result.document_type_confidence >= self.SUGGEST_THRESHOLD
            and len(result.anomalies) == 0  # Keine kritischen Anomalien
        )

    async def _trigger_matching_workflows(
        self,
        document_id: UUID,
        document_type: Optional[str],
        entity_id: Optional[UUID],
        anomalies: List[AnomalyResult],
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Triggert passende Workflows."""
        triggered = []

        try:
            # Beispiel: Invoice Approval Workflow
            if document_type and document_type.lower() == "invoice":
                triggered.append({
                    "workflow_type": "invoice_approval",
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "Automatisch bei Rechnung",
                })

            # Anomalie-Workflow
            critical_anomalies = [a for a in anomalies if a.severity in ["high", "critical"]]
            if critical_anomalies:
                triggered.append({
                    "workflow_type": "anomaly_review",
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "reason": f"{len(critical_anomalies)} kritische Anomalie(n) erkannt",
                })

        except Exception as e:
            logger.error("trigger_workflows_error", **safe_error_log(e))

        return triggered

    # =========================================================================
    # Evaluation
    # =========================================================================

    def _evaluate_pipeline_result(self, result: PipelineResult) -> PipelineResult:
        """Evaluiert das Gesamtergebnis der Pipeline."""
        # Prüfen ob alle Schritte automatisch verarbeitet werden können
        auto_decisions = [
            d for d in result.decisions
            if d.confidence_level == DecisionConfidence.AUTO
        ]

        manual_decisions = [
            d for d in result.decisions
            if d.confidence_level == DecisionConfidence.MANUAL
        ]

        critical_anomalies = [
            a for a in result.anomalies
            if a.severity in ["high", "critical"]
        ]

        # Auto-Verarbeitung nur wenn:
        # - Alle Entscheidungen AUTO-Level haben
        # - Keine kritischen Anomalien
        result.auto_processed = (
            len(manual_decisions) == 0
            and len(critical_anomalies) == 0
            and result.document_type_confidence >= self.AUTO_THRESHOLD
        )

        # Review erforderlich wenn:
        # - Mindestens eine MANUAL-Entscheidung
        # - Oder kritische Anomalien
        result.requires_review = (
            len(manual_decisions) > 0
            or len(critical_anomalies) > 0
        )

        # Review-Gründe sammeln
        for decision in manual_decisions:
            result.review_reasons.append(
                f"{decision.step.value}: {decision.explanation}"
            )

        for anomaly in critical_anomalies:
            result.review_reasons.append(
                f"Anomalie: {anomaly.explanation}"
            )

        # Status setzen
        if result.auto_processed:
            result.status = PipelineStatus.AUTO_COMPLETED
        elif result.requires_review:
            result.status = PipelineStatus.REQUIRES_REVIEW
        else:
            result.status = PipelineStatus.AUTO_COMPLETED

        return result

    # =========================================================================
    # Helpers
    # =========================================================================

    def _get_confidence_level(self, confidence: float) -> DecisionConfidence:
        """Bestimmt das Confidence-Level."""
        if confidence >= self.AUTO_THRESHOLD:
            return DecisionConfidence.AUTO
        elif confidence >= self.SUGGEST_THRESHOLD:
            return DecisionConfidence.SUGGEST
        else:
            return DecisionConfidence.MANUAL


# =============================================================================
# Factory
# =============================================================================

def get_document_pipeline_orchestrator(db: AsyncSession) -> DocumentPipelineOrchestrator:
    """Factory-Funktion für DocumentPipelineOrchestrator."""
    return DocumentPipelineOrchestrator(db)
