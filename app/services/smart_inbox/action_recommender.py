"""Smart Inbox Action Recommender - Empfiehlt beste nächste Aktion.

Analysiert den Kontext eines Inbox Items und empfiehlt:
- Die beste nächste Aktion
- Confidence-Score für Empfehlung
- Frontend-Route für schnellen Zugriff
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import SmartInboxItem, SmartInboxItemSource

logger = structlog.get_logger(__name__)


@dataclass
class RecommendedAction:
    """Empfohlene Aktion für ein Inbox Item."""
    action_type: str  # approve, review, pay, escalate, dismiss, snooze
    label: str  # Deutscher Label für Button
    description: str  # Deutsche Beschreibung
    confidence: float  # 0.0 - 1.0
    url: Optional[str] = None  # Frontend-Route
    icon: Optional[str] = None  # Icon-Name für UI
    variant: str = "default"  # UI-Variante: default, primary, danger, success


class ActionRecommender:
    """Empfiehlt beste nächste Aktionen für Smart Inbox Items."""

    def __init__(self) -> None:
        """Initialisiert den Action Recommender."""
        self.logger = logger.bind(service="action_recommender")

    async def recommend(
        self,
        item: SmartInboxItem,
        db: AsyncSession,
    ) -> List[RecommendedAction]:
        """
        Empfiehlt Aktionen für ein Smart Inbox Item.

        Args:
            item: SmartInboxItem
            db: Async DB Session

        Returns:
            Liste von RecommendedAction (sortiert nach Confidence)
        """
        self.logger.debug(
            "recommending_actions",
            item_id=str(item.id),
            source_type=item.source_type,
        )

        recommendations: List[RecommendedAction] = []

        # Source-spezifische Empfehlungen
        if item.source_type == SmartInboxItemSource.VALIDATION_QUEUE.value:
            recommendations = self._recommend_validation_queue(item)
        elif item.source_type == SmartInboxItemSource.ALERT.value:
            recommendations = self._recommend_alert(item)
        elif item.source_type == SmartInboxItemSource.DEADLINE.value:
            recommendations = self._recommend_deadline(item)
        elif item.source_type == SmartInboxItemSource.OCR_RESULT.value:
            recommendations = self._recommend_ocr_result(item)
        elif item.source_type == SmartInboxItemSource.APPROVAL.value:
            recommendations = self._recommend_approval(item)
        elif item.source_type == SmartInboxItemSource.TASK.value:
            recommendations = self._recommend_task(item)
        elif item.source_type == SmartInboxItemSource.INVOICE.value:
            recommendations = self._recommend_invoice(item)
        else:
            self.logger.warning(
                "unknown_source_type",
                source_type=item.source_type,
            )
            # Fallback: Generische Aktionen
            recommendations = self._recommend_generic(item)

        # Immer "Snooze" und "Dismiss" hinzufügen
        recommendations.extend(self._get_universal_actions())

        # Nach Confidence sortieren
        recommendations.sort(key=lambda x: x.confidence, reverse=True)

        self.logger.info(
            "actions_recommended",
            item_id=str(item.id),
            recommendation_count=len(recommendations),
        )

        return recommendations

    def _recommend_validation_queue(
        self,
        item: SmartInboxItem,
    ) -> List[RecommendedAction]:
        """Empfehlungen für Validation Queue Items."""
        confidence = item.context_data.get("confidence", 0.5)

        return [
            RecommendedAction(
                action_type="review",
                label="Überprüfen",
                description="OCR-Ergebnis im Detail überprüfen",
                confidence=0.9,
                url=f"/documents/{item.document_id}" if item.document_id else None,
                icon="eye",
                variant="primary",
            ),
            RecommendedAction(
                action_type="approve",
                label="Genehmigen",
                description="OCR-Ergebnis akzeptieren und weiterverarbeiten",
                confidence=confidence,
                icon="check",
                variant="success",
            ),
            RecommendedAction(
                action_type="reject",
                label="Ablehnen",
                description="OCR-Ergebnis korrigieren oder neu verarbeiten",
                confidence=1.0 - confidence,
                icon="x",
                variant="danger",
            ),
        ]

    def _recommend_alert(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Empfehlungen für Alert Items."""
        severity = item.context_data.get("severity", "medium")

        actions = [
            RecommendedAction(
                action_type="acknowledge",
                label="Bestätigen",
                description="Alert als gesehen markieren",
                confidence=0.8,
                icon="check",
                variant="default",
            ),
        ]

        # Bei high/critical: Eskalieren empfehlen
        if severity in ["high", "critical"]:
            actions.append(
                RecommendedAction(
                    action_type="escalate",
                    label="Eskalieren",
                    description="An Vorgesetzten weiterleiten",
                    confidence=0.7,
                    icon="arrow-up",
                    variant="primary",
                )
            )

        # Bei low/info: Verwerfen ist OK
        if severity in ["low", "info"]:
            actions.append(
                RecommendedAction(
                    action_type="dismiss",
                    label="Verwerfen",
                    description="Alert ignorieren",
                    confidence=0.6,
                    icon="trash",
                    variant="danger",
                )
            )

        # Immer: Zur Detail-Seite
        if item.document_id:
            actions.append(
                RecommendedAction(
                    action_type="view_document",
                    label="Dokument öffnen",
                    description="Verknüpftes Dokument anzeigen",
                    confidence=0.9,
                    url=f"/documents/{item.document_id}",
                    icon="file-text",
                    variant="default",
                )
            )

        return actions

    def _recommend_deadline(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Empfehlungen für Deadline Items."""
        days_until_due = item.context_data.get("days_until_due", 999)
        skonto_available = item.context_data.get("skonto_available", False)

        actions: List[RecommendedAction] = []

        # Skonto nutzen (falls verfügbar und noch Zeit)
        if skonto_available and days_until_due <= 14:
            actions.append(
                RecommendedAction(
                    action_type="use_skonto",
                    label="Skonto nutzen",
                    description="Mit Skonto-Abzug bezahlen und Geld sparen",
                    confidence=0.95,
                    icon="percent",
                    variant="success",
                )
            )

        # Bezahlen
        actions.append(
            RecommendedAction(
                action_type="pay",
                label="Bezahlen",
                description="Rechnung zur Zahlung freigeben",
                confidence=0.9,
                icon="credit-card",
                variant="primary",
            )
        )

        # Erinnerung setzen (falls noch Zeit)
        if days_until_due > 2:
            actions.append(
                RecommendedAction(
                    action_type="set_reminder",
                    label="Erinnerung setzen",
                    description="Später erinnern lassen",
                    confidence=0.5,
                    icon="bell",
                    variant="default",
                )
            )

        # Dokument öffnen
        if item.document_id:
            actions.append(
                RecommendedAction(
                    action_type="view_invoice",
                    label="Rechnung öffnen",
                    description="Details zur Rechnung anzeigen",
                    confidence=0.8,
                    url=f"/documents/{item.document_id}",
                    icon="file-text",
                    variant="default",
                )
            )

        return actions

    def _recommend_ocr_result(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Empfehlungen für OCR Result Items."""
        confidence = item.context_data.get("confidence", 0.5)

        return [
            RecommendedAction(
                action_type="review",
                label="Überprüfen",
                description="OCR-Ergebnis manuell prüfen",
                confidence=0.9,
                url=f"/documents/{item.document_id}" if item.document_id else None,
                icon="eye",
                variant="primary",
            ),
            RecommendedAction(
                action_type="reprocess",
                label="Neu verarbeiten",
                description="Mit anderem OCR-Backend versuchen",
                confidence=0.6 if confidence < 0.5 else 0.3,
                icon="refresh-cw",
                variant="default",
            ),
        ]

    def _recommend_approval(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Empfehlungen für Approval Items."""
        escalated = item.context_data.get("escalated", False)

        actions = [
            RecommendedAction(
                action_type="approve",
                label="Genehmigen",
                description="Anfrage genehmigen",
                confidence=0.85 if escalated else 0.7,
                icon="check",
                variant="success",
            ),
            RecommendedAction(
                action_type="reject",
                label="Ablehnen",
                description="Anfrage ablehnen",
                confidence=0.3,
                icon="x",
                variant="danger",
            ),
            RecommendedAction(
                action_type="delegate",
                label="Delegieren",
                description="An anderen Benutzer weiterleiten",
                confidence=0.5,
                icon="user-plus",
                variant="default",
            ),
        ]

        return actions

    def _recommend_task(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Empfehlungen für Task Items."""
        task_type = item.context_data.get("task_type", "review")

        actions = [
            RecommendedAction(
                action_type="complete",
                label="Erledigen",
                description="Aufgabe als erledigt markieren",
                confidence=0.8,
                icon="check-circle",
                variant="success",
            ),
        ]

        # Dokument öffnen
        if item.document_id:
            actions.append(
                RecommendedAction(
                    action_type="view_document",
                    label="Dokument öffnen",
                    description="Verknüpftes Dokument anzeigen",
                    confidence=0.9,
                    url=f"/documents/{item.document_id}",
                    icon="file-text",
                    variant="primary",
                )
            )

        actions.append(
            RecommendedAction(
                action_type="delegate",
                label="Delegieren",
                description="Aufgabe an anderen Benutzer übergeben",
                confidence=0.4,
                icon="user-plus",
                variant="default",
            )
        )

        actions.append(
            RecommendedAction(
                action_type="update",
                label="Aktualisieren",
                description="Status oder Details aktualisieren",
                confidence=0.5,
                icon="edit",
                variant="default",
            )
        )

        return actions

    def _recommend_invoice(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Empfehlungen für Invoice Items."""
        return [
            RecommendedAction(
                action_type="pay",
                label="Bezahlen",
                description="Rechnung zur Zahlung freigeben",
                confidence=0.9,
                icon="credit-card",
                variant="primary",
            ),
            RecommendedAction(
                action_type="send_dunning",
                label="Mahnung senden",
                description="Zahlungserinnerung verschicken",
                confidence=0.6,
                icon="mail",
                variant="default",
            ),
            RecommendedAction(
                action_type="dispute",
                label="Reklamieren",
                description="Rechnung beanstanden",
                confidence=0.3,
                icon="alert-triangle",
                variant="danger",
            ),
        ]

    def _recommend_generic(self, item: SmartInboxItem) -> List[RecommendedAction]:
        """Fallback: Generische Empfehlungen."""
        actions = [
            RecommendedAction(
                action_type="view",
                label="Anzeigen",
                description="Details anzeigen",
                confidence=0.8,
                icon="eye",
                variant="primary",
            ),
        ]

        if item.document_id:
            actions.append(
                RecommendedAction(
                    action_type="view_document",
                    label="Dokument öffnen",
                    description="Verknüpftes Dokument anzeigen",
                    confidence=0.9,
                    url=f"/documents/{item.document_id}",
                    icon="file-text",
                    variant="default",
                )
            )

        return actions

    def _get_universal_actions(self) -> List[RecommendedAction]:
        """Universelle Aktionen für alle Items."""
        return [
            RecommendedAction(
                action_type="snooze",
                label="Erinnern",
                description="Später erinnern lassen",
                confidence=0.4,
                icon="clock",
                variant="default",
            ),
            RecommendedAction(
                action_type="dismiss",
                label="Verwerfen",
                description="Aus Inbox entfernen",
                confidence=0.2,
                icon="trash",
                variant="danger",
            ),
        ]

    async def get_quick_action(
        self,
        item: SmartInboxItem,
        db: AsyncSession,
    ) -> Optional[RecommendedAction]:
        """
        Gibt die beste einzelne Quick-Action zurück.

        Wird für "Quick Action" Buttons in der UI verwendet.

        Args:
            item: SmartInboxItem
            db: Async DB Session

        Returns:
            Beste RecommendedAction oder None
        """
        recommendations = await self.recommend(item, db)

        # Erste empfohlene Aktion (höchste Confidence)
        # Aber nicht "snooze" oder "dismiss"
        for rec in recommendations:
            if rec.action_type not in ["snooze", "dismiss"]:
                return rec

        return None
