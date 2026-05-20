# -*- coding: utf-8 -*-
"""
Proaktiver Action-Queue-Service.

Aggregiert ausstehende Aufgaben aus verschiedenen Quellen zu einer
priorisierten Tages-Todo-Liste.

Quellen:
- Fällige Rechnungen (Dokumente vom Typ Invoice mit überfälligem Datum)
- Offene Genehmigungen (PendingAction-Einträge)
- Skonto-Deadlines (SkontoRecommendation mit nahender Frist)
- Unkategorisierte Dokumente (Dokumente ohne Kategorie)
- Anomalien (offene Einträge aus der Anomalie-Tabelle)
- Vertragsfrist-Warnungen (Verträge die bald ablaufen)

Feinpoliert und durchdacht - Enterprise-grade Proactive Intelligence.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.action_priority_engine import (
    ActionPriorityEngine,
    ProactiveActionType,
    get_priority_engine,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# PROMETHEUS METRICS
# =============================================================================


PROACTIVE_QUEUE_SIZE = Gauge(
    "proactive_action_queue_size",
    "Anzahl offener proaktiver Aufgaben",
    ["company_id", "action_type"],
)

PROACTIVE_REFRESH_TOTAL = Counter(
    "proactive_action_queue_refresh_total",
    "Anzahl der Queue-Aktualisierungen",
    ["company_id"],
)

PROACTIVE_COMPLETE_TOTAL = Counter(
    "proactive_action_queue_complete_total",
    "Anzahl abgeschlossener proaktiver Aufgaben",
    ["action_type"],
)

PROACTIVE_REFRESH_DURATION = Histogram(
    "proactive_action_queue_refresh_duration_seconds",
    "Dauer der Queue-Aktualisierung",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)


# =============================================================================
# PYDANTIC MODELS (DATA TRANSFER OBJECTS)
# =============================================================================


class ProactiveActionItem(BaseModel):
    """Einzelner Eintrag in der proaktiven Action-Queue."""

    id: str = Field(..., description="Eindeutige Aufgaben-ID")
    action_type: str = Field(..., description="Typ der Aufgabe")
    title: str = Field(..., description="Titel der Aufgabe (Deutsch)")
    description: str = Field(..., description="Beschreibung der Aufgabe")
    priority_score: float = Field(
        ..., ge=0.0, le=1.0, description="Prioritäts-Score (0-1, 1=höchste Priorität)"
    )
    priority_label: str = Field(
        ..., description="Lesbare Priorität: kritisch, hoch, mittel, niedrig"
    )
    deadline: Optional[str] = Field(None, description="ISO-Frist (falls vorhanden)")
    financial_amount: Optional[float] = Field(
        None, description="Monetärer Betrag in EUR (falls relevant)"
    )
    source_id: Optional[str] = Field(
        None, description="ID des Quelldokuments/-datensatzes"
    )
    source_url: Optional[str] = Field(
        None, description="Relativer Pfad zum Quellelement"
    )
    is_completed: bool = Field(default=False, description="Aufgabe erledigt?")
    completed_at: Optional[str] = Field(None, description="ISO-Zeitstempel der Erledigung")
    snoozed_until: Optional[str] = Field(
        None, description="ISO-Zeitstempel 'Erinnere mich später'"
    )
    metadata: Dict = Field(default_factory=dict, description="Zusätzliche Metadaten")

    model_config = ConfigDict(str_strip_whitespace=True)


class ActionQueueProgress(BaseModel):
    """Fortschrittsanzeige für den heutigen Tag."""

    total: int = Field(..., description="Gesamtanzahl Aufgaben")
    completed: int = Field(..., description="Erledigte Aufgaben")
    snoozed: int = Field(..., description="Aufgeschobene Aufgaben")
    pending: int = Field(..., description="Offene Aufgaben")
    completion_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Erledigungsquote (0-1)"
    )
    by_type: Dict = Field(
        default_factory=dict, description="Aufgaben nach Typ"
    )


class ActionQueueResponse(BaseModel):
    """Vollständige Antwort der heutigen Action-Queue."""

    date: str = Field(..., description="Datum dieser Queue (ISO)")
    items: List[ProactiveActionItem] = Field(
        default_factory=list, description="Priorisierte Aufgabenliste"
    )
    progress: ActionQueueProgress = Field(..., description="Fortschrittsübersicht")
    last_refreshed_at: str = Field(..., description="Letztes Refresh-Datum (ISO)")


class SnoozeRequest(BaseModel):
    """Anfrage zum Verschieben einer Aufgabe."""

    snooze_until: datetime = Field(
        ..., description="Zeitpunkt bis wann verschieben (ISO, timezone-aware)"
    )


# =============================================================================
# PROACTIVE ACTION QUEUE SERVICE
# =============================================================================


class ProactiveActionQueueService:
    """
    Aggregiert und priorisiert proaktive Aufgaben aus dem gesamten System.

    Baut täglich eine priorisierte Todo-Liste aus sechs Quellen:
    1. Fällige Rechnungen
    2. Offene Genehmigungen
    3. Skonto-Deadlines
    4. Unkategorisierte Dokumente
    5. Anomalien
    6. Vertragsfrist-Warnungen
    """

    def __init__(self, priority_engine: Optional[ActionPriorityEngine] = None) -> None:
        """
        Initialisiert den Service.

        Args:
            priority_engine: Optionale benutzerdefinierte Priority Engine.
                             Wenn None, wird die globale Singleton-Instanz verwendet.
        """
        self._engine = priority_engine or get_priority_engine()

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def get_today_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ActionQueueResponse:
        """
        Gibt die priorisierte Aufgabenliste für heute zurück.

        Aggregiert Aufgaben aus allen Quellen, priorisiert sie und
        filtert bereits erledigte oder noch gesnoozete Einträge.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID
            user_id:    Aktueller Benutzer (für Logging)

        Returns:
            ActionQueueResponse mit priorisierten Aufgaben
        """
        now_utc = datetime.now(tz=timezone.utc)
        today_str = now_utc.date().isoformat()

        logger.info(
            "proactive_queue_requested",
            company_id=str(company_id),
            user_id=str(user_id),
            date=today_str,
        )

        # Alle Quellen parallel aggregieren (sequenziell in einem try-Block
        # damit ein einzelner Fehler nicht die ganze Queue blockiert)
        all_items: List[ProactiveActionItem] = []

        sources = [
            ("fällige_rechnungen", self._collect_overdue_invoices),
            ("offene_genehmigungen", self._collect_pending_approvals),
            ("skonto_deadlines", self._collect_skonto_deadlines),
            ("unkategorisierte_dokumente", self._collect_uncategorized_docs),
            ("anomalien", self._collect_anomalies),
            ("vertragsfrist_warnungen", self._collect_contract_expiries),
        ]

        for source_name, collector in sources:
            try:
                items = await collector(db, company_id)
                all_items.extend(items)
                logger.debug(
                    "proactive_source_collected",
                    source=source_name,
                    count=len(items),
                    company_id=str(company_id),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "proactive_source_failed",
                    source=source_name,
                    company_id=str(company_id),
                    error=str(exc),
                )

        # Sortieren nach Priorität
        sorted_items = self._engine.rank_actions(all_items)

        # Fortschritt berechnen
        progress = self._build_progress(sorted_items)

        return ActionQueueResponse(
            date=today_str,
            items=sorted_items,
            progress=progress,
            last_refreshed_at=now_utc.isoformat(),
        )

    async def complete_action(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        action_id: str,
        user_id: uuid.UUID,
    ) -> bool:
        """
        Markiert eine Aufgabe als erledigt.

        Aktuell wird der Abschluss in der ProactiveActionState-Tabelle
        persistiert (falls vorhanden), ansonsten wird nur geloggt.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID
            action_id:  Aufgaben-ID (zusammengesetzt aus Typ + Quelle)
            user_id:    Ausführender Benutzer

        Returns:
            True wenn erfolgreich, False wenn Aufgabe nicht gefunden
        """
        now_utc = datetime.now(tz=timezone.utc)

        try:
            state = await self._get_or_create_state(db, company_id, action_id)
            state.is_completed = True
            state.completed_at = now_utc
            state.snoozed_until = None
            await db.commit()

            PROACTIVE_COMPLETE_TOTAL.labels(
                action_type=self._parse_action_type(action_id),
            ).inc()

            logger.info(
                "proactive_action_completed",
                action_id=action_id,
                company_id=str(company_id),
                user_id=str(user_id),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "proactive_action_complete_failed",
                action_id=action_id,
                company_id=str(company_id),
                error=str(exc),
            )
            return False

    async def snooze_action(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        action_id: str,
        user_id: uuid.UUID,
        snooze_until: datetime,
    ) -> bool:
        """
        Verschiebt eine Aufgabe auf einen späteren Zeitpunkt.

        Args:
            db:           Datenbank-Session
            company_id:   Tenant-ID
            action_id:    Aufgaben-ID
            user_id:      Ausführender Benutzer
            snooze_until: Zeitpunkt bis wann verschieben (timezone-aware)

        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        # Sicherstellen dass snooze_until timezone-aware ist
        if snooze_until.tzinfo is None:
            snooze_until = snooze_until.replace(tzinfo=timezone.utc)

        try:
            state = await self._get_or_create_state(db, company_id, action_id)
            state.snoozed_until = snooze_until
            state.is_completed = False
            await db.commit()

            logger.info(
                "proactive_action_snoozed",
                action_id=action_id,
                company_id=str(company_id),
                user_id=str(user_id),
                snooze_until=snooze_until.isoformat(),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "proactive_action_snooze_failed",
                action_id=action_id,
                company_id=str(company_id),
                error=str(exc),
            )
            return False

    async def refresh_queue(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> int:
        """
        Aktualisiert die Queue und gibt die Anzahl neuer Aufgaben zurück.

        Wird von Celery Beat aufgerufen. Löscht abgelaufene Snooze-States
        und berechnet Metriken neu.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Anzahl aktiver Aufgaben nach Refresh
        """
        import time
        start_ts = time.monotonic()

        try:
            # Abgelaufene Snooze-States zurücksetzen
            await self._reset_expired_snoozes(db, company_id)

            # Queue neu aggregieren (ohne User-ID für Systemaufrufe)
            now_utc = datetime.now(tz=timezone.utc)
            all_items: List[ProactiveActionItem] = []

            for collector in [
                self._collect_overdue_invoices,
                self._collect_pending_approvals,
                self._collect_skonto_deadlines,
                self._collect_uncategorized_docs,
                self._collect_anomalies,
                self._collect_contract_expiries,
            ]:
                try:
                    items = await collector(db, company_id)
                    all_items.extend(items)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "proactive_refresh_source_failed",
                        company_id=str(company_id),
                        error=str(exc),
                    )

            count = len(all_items)

            # Metriken aktualisieren
            PROACTIVE_REFRESH_TOTAL.labels(company_id=str(company_id)).inc()

            duration = time.monotonic() - start_ts
            PROACTIVE_REFRESH_DURATION.observe(duration)

            logger.info(
                "proactive_queue_refreshed",
                company_id=str(company_id),
                total_items=count,
                duration_s=round(duration, 3),
            )

            return count

        except Exception as exc:
            logger.error(
                "proactive_queue_refresh_failed",
                company_id=str(company_id),
                error=str(exc),
            )
            return 0

    async def get_progress(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ActionQueueProgress:
        """
        Gibt den heutigen Fortschritt zurück (ohne vollständige Item-Liste).

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID
            user_id:    Aktueller Benutzer

        Returns:
            ActionQueueProgress mit Erledigungsquote
        """
        response = await self.get_today_actions(db, company_id, user_id)
        return response.progress

    # =========================================================================
    # SOURCE COLLECTORS
    # =========================================================================

    async def _collect_overdue_invoices(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ProactiveActionItem]:
        """
        Sammelt fällige Rechnungen.

        Sucht Dokumente vom Typ 'invoice' bei denen das extrahierte
        Fälligkeitsdatum überschritten ist oder kein Zahlungseingang
        verbucht wurde.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Liste proaktiver Aufgaben
        """
        from app.db.models import Document, DocumentType, ProcessingStatus

        now_utc = datetime.now(tz=timezone.utc)

        query = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type == DocumentType.INVOICE.value,
                    Document.status == ProcessingStatus.COMPLETED.value,
                )
            )
            .limit(50)
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        items: List[ProactiveActionItem] = []
        states = await self._load_states(db, company_id, [
            self._make_action_id(ProactiveActionType.OVERDUE_INVOICE, str(doc.id))
            for doc in documents
        ])

        for doc in documents:
            action_id = self._make_action_id(
                ProactiveActionType.OVERDUE_INVOICE, str(doc.id)
            )
            state = states.get(action_id)

            # Überspringe erledigte oder gesnoozete Aufgaben
            if self._is_suppressed(state, now_utc):
                continue

            # Fälligkeitsdatum aus extrahierten Daten
            extracted = doc.document_metadata or {}
            due_date_str = extracted.get("due_date") or extracted.get("faelligkeitsdatum")
            due_date: Optional[datetime] = None
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(str(due_date_str)).replace(
                        tzinfo=timezone.utc
                    )
                except (ValueError, TypeError):
                    pass

            # Nur Rechnungen mit vergangenem Fälligkeitsdatum
            if due_date is not None and due_date > now_utc:
                continue

            amount = self._extract_amount(doc)
            days_overdue = 0
            if due_date:
                days_overdue = int((now_utc - due_date).days)

            score = self._engine.calculate_score(
                action_type=ProactiveActionType.OVERDUE_INVOICE,
                deadline=due_date,
                financial_amount=amount,
            )

            label = _score_to_label(score)
            deadline_str = due_date.isoformat() if due_date else None
            title = f"Fällige Rechnung: {doc.original_filename}"
            if days_overdue > 0:
                title = f"Überfällige Rechnung ({days_overdue} Tage): {doc.original_filename}"

            items.append(ProactiveActionItem(
                id=action_id,
                action_type=ProactiveActionType.OVERDUE_INVOICE.value,
                title=title,
                description=(
                    f"Rechnung '{doc.original_filename}' ist seit {days_overdue} Tagen "
                    f"fällig. Bitte prüfen und Zahlung veranlassen."
                ),
                priority_score=score,
                priority_label=label,
                deadline=deadline_str,
                financial_amount=amount,
                source_id=str(doc.id),
                source_url=f"/documents/{doc.id}",
                is_completed=False,
                metadata={
                    "days_overdue": days_overdue,
                    "filename": doc.original_filename,
                },
            ))

        return items

    async def _collect_pending_approvals(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ProactiveActionItem]:
        """
        Sammelt offene Genehmigungsanfragen aus der PendingAction-Tabelle.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Liste proaktiver Aufgaben
        """
        from app.db.models_autonomy import PendingAction, PendingActionStatus

        now_utc = datetime.now(tz=timezone.utc)

        query = (
            select(PendingAction)
            .where(
                and_(
                    PendingAction.company_id == company_id,
                    PendingAction.status == PendingActionStatus.PENDING.value,
                    PendingAction.expires_at > now_utc,
                )
            )
            .order_by(PendingAction.priority.desc(), PendingAction.created_at.asc())
            .limit(30)
        )

        result = await db.execute(query)
        actions = result.scalars().all()

        items: List[ProactiveActionItem] = []
        states = await self._load_states(db, company_id, [
            self._make_action_id(ProactiveActionType.PENDING_APPROVAL, str(a.id))
            for a in actions
        ])

        for action in actions:
            action_id = self._make_action_id(
                ProactiveActionType.PENDING_APPROVAL, str(action.id)
            )
            state = states.get(action_id)

            if self._is_suppressed(state, now_utc):
                continue

            expires_at = action.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            score = self._engine.calculate_score(
                action_type=ProactiveActionType.PENDING_APPROVAL,
                deadline=expires_at,
                financial_amount=None,
            )

            items.append(ProactiveActionItem(
                id=action_id,
                action_type=ProactiveActionType.PENDING_APPROVAL.value,
                title=f"Offene Genehmigung: {action.description[:80]}",
                description=(
                    f"KI-Aktion '{action.action_type}' wartet auf Ihre Genehmigung. "
                    f"Kategorie: {action.action_category}. "
                    f"Konfidenz: {action.confidence:.0%}."
                ),
                priority_score=score,
                priority_label=_score_to_label(score),
                deadline=expires_at.isoformat() if expires_at else None,
                financial_amount=None,
                source_id=str(action.id),
                source_url=f"/action-queue/queue/{action.id}",
                is_completed=False,
                metadata={
                    "action_type": action.action_type,
                    "category": action.action_category,
                    "confidence": action.confidence,
                },
            ))

        return items

    async def _collect_skonto_deadlines(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ProactiveActionItem]:
        """
        Sammelt Skonto-Deadlines die in den nächsten 7 Tagen ablaufen.

        Liest aus der SkontoRecommendation-Tabelle (models_insights.py).

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Liste proaktiver Aufgaben
        """
        try:
            from app.db.models_insights import SkontoRecommendation
        except ImportError:
            logger.debug("SkontoRecommendation nicht verfügbar, überspringe")
            return []

        now_utc = datetime.now(tz=timezone.utc)
        cutoff = now_utc + timedelta(days=7)
        cutoff_date = cutoff.date()

        query = (
            select(SkontoRecommendation)
            .where(
                and_(
                    SkontoRecommendation.company_id == company_id,
                    SkontoRecommendation.skonto_deadline <= cutoff_date,
                    SkontoRecommendation.skonto_deadline >= now_utc.date(),
                    SkontoRecommendation.recommendation == "use_skonto",
                )
            )
            .order_by(SkontoRecommendation.skonto_deadline.asc())
            .limit(20)
        )

        result = await db.execute(query)
        recommendations = result.scalars().all()

        items: List[ProactiveActionItem] = []
        states = await self._load_states(db, company_id, [
            self._make_action_id(ProactiveActionType.SKONTO_DEADLINE, str(r.id))
            for r in recommendations
        ])

        for rec in recommendations:
            action_id = self._make_action_id(
                ProactiveActionType.SKONTO_DEADLINE, str(rec.id)
            )
            state = states.get(action_id)

            if self._is_suppressed(state, now_utc):
                continue

            deadline_dt = datetime.combine(
                rec.skonto_deadline, datetime.min.time(), tzinfo=timezone.utc
            )
            days_left = rec.days_until_deadline

            score = self._engine.calculate_score(
                action_type=ProactiveActionType.SKONTO_DEADLINE,
                deadline=deadline_dt,
                financial_amount=float(rec.skonto_amount) if rec.skonto_amount else None,
            )

            items.append(ProactiveActionItem(
                id=action_id,
                action_type=ProactiveActionType.SKONTO_DEADLINE.value,
                title=f"Skonto-Frist in {days_left} Tag(en): {rec.skonto_amount:.2f} EUR sparen",
                description=(
                    f"Skonto-Frist läuft am {rec.skonto_deadline.strftime('%d.%m.%Y')} ab. "
                    f"Durch frühzeitige Zahlung können Sie {rec.skonto_amount:.2f} EUR "
                    f"({rec.skonto_percentage:.1f}%) sparen."
                ),
                priority_score=score,
                priority_label=_score_to_label(score),
                deadline=deadline_dt.isoformat(),
                financial_amount=float(rec.skonto_amount) if rec.skonto_amount else None,
                source_id=str(rec.id),
                source_url=f"/insights/skonto/{rec.id}",
                is_completed=False,
                metadata={
                    "skonto_percentage": float(rec.skonto_percentage),
                    "days_until_deadline": days_left,
                    "invoice_amount": float(rec.invoice_amount) if rec.invoice_amount else None,
                },
            ))

        return items

    async def _collect_uncategorized_docs(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ProactiveActionItem]:
        """
        Sammelt Dokumente ohne Kategorie (document_type = 'unknown' oder 'other').

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Liste proaktiver Aufgaben
        """
        from app.db.models import Document, DocumentType, ProcessingStatus

        now_utc = datetime.now(tz=timezone.utc)

        query = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.status == ProcessingStatus.COMPLETED.value,
                    or_(
                        Document.document_type == DocumentType.UNKNOWN.value,
                        Document.document_type == DocumentType.OTHER.value,
                        Document.document_type.is_(None),
                    ),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(25)
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        items: List[ProactiveActionItem] = []
        states = await self._load_states(db, company_id, [
            self._make_action_id(ProactiveActionType.UNCATEGORIZED_DOC, str(doc.id))
            for doc in documents
        ])

        for doc in documents:
            action_id = self._make_action_id(
                ProactiveActionType.UNCATEGORIZED_DOC, str(doc.id)
            )
            state = states.get(action_id)

            if self._is_suppressed(state, now_utc):
                continue

            age_days = max(0, (now_utc - doc.created_at.replace(tzinfo=timezone.utc)).days)

            score = self._engine.calculate_score(
                action_type=ProactiveActionType.UNCATEGORIZED_DOC,
                deadline=None,
                financial_amount=None,
            )

            items.append(ProactiveActionItem(
                id=action_id,
                action_type=ProactiveActionType.UNCATEGORIZED_DOC.value,
                title=f"Unkategorisiertes Dokument: {doc.original_filename}",
                description=(
                    f"Dokument '{doc.original_filename}' wurde vor {age_days} Tag(en) "
                    f"hochgeladen und ist noch nicht kategorisiert. "
                    f"Bitte Typ und Ablageort festlegen."
                ),
                priority_score=score,
                priority_label=_score_to_label(score),
                deadline=None,
                financial_amount=None,
                source_id=str(doc.id),
                source_url=f"/documents/{doc.id}",
                is_completed=False,
                metadata={
                    "age_days": age_days,
                    "filename": doc.original_filename,
                    "current_type": doc.document_type,
                },
            ))

        return items

    async def _collect_anomalies(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ProactiveActionItem]:
        """
        Sammelt offene Anomalien aus der Anomalie-Tabelle.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Liste proaktiver Aufgaben
        """
        try:
            from app.db.models_anomaly import Anomaly, AnomalyStatus, AnomalySeverity
        except ImportError:
            logger.debug("Anomaly-Modell nicht verfügbar, überspringe")
            return []

        now_utc = datetime.now(tz=timezone.utc)

        query = (
            select(Anomaly)
            .where(
                and_(
                    Anomaly.company_id == company_id,
                    Anomaly.status == AnomalyStatus.OPEN.value,
                )
            )
            .order_by(Anomaly.score.desc(), Anomaly.created_at.desc())
            .limit(20)
        )

        result = await db.execute(query)
        anomalies = result.scalars().all()

        items: List[ProactiveActionItem] = []
        states = await self._load_states(db, company_id, [
            self._make_action_id(ProactiveActionType.ANOMALY, str(a.id))
            for a in anomalies
        ])

        _severity_amounts: Dict = {
            "critical": 50_000.0,
            "high": 10_000.0,
            "medium": 1_000.0,
            "low": 100.0,
        }

        for anomaly in anomalies:
            action_id = self._make_action_id(
                ProactiveActionType.ANOMALY, str(anomaly.id)
            )
            state = states.get(action_id)

            if self._is_suppressed(state, now_utc):
                continue

            # Finanzielle Auswirkung anhand Schweregrad schätzen
            fin_amount = _severity_amounts.get(
                getattr(anomaly, "severity", "medium"), 1_000.0
            )

            score = self._engine.calculate_score(
                action_type=ProactiveActionType.ANOMALY,
                deadline=None,
                financial_amount=fin_amount,
            )

            title = getattr(anomaly, "title", f"Anomalie: {anomaly.anomaly_type}")

            items.append(ProactiveActionItem(
                id=action_id,
                action_type=ProactiveActionType.ANOMALY.value,
                title=title,
                description=(
                    getattr(anomaly, "description", None)
                    or f"Erkannte Anomalie vom Typ '{anomaly.anomaly_type}'. "
                    f"Bitte prüfen und ggf. Maßnahmen ergreifen."
                ),
                priority_score=score,
                priority_label=_score_to_label(score),
                deadline=None,
                financial_amount=fin_amount,
                source_id=str(anomaly.id),
                source_url=f"/anomalies/{anomaly.id}",
                is_completed=False,
                metadata={
                    "anomaly_type": anomaly.anomaly_type,
                    "severity": getattr(anomaly, "severity", "unknown"),
                    "score": float(anomaly.score),
                },
            ))

        return items

    async def _collect_contract_expiries(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ProactiveActionItem]:
        """
        Sammelt Verträge die in den nächsten 90 Tagen ablaufen.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID

        Returns:
            Liste proaktiver Aufgaben
        """
        try:
            from app.db.models_contract import Contract, ContractStatus
        except ImportError:
            logger.debug("Contract-Modell nicht verfügbar, überspringe")
            return []

        now_utc = datetime.now(tz=timezone.utc)
        today = now_utc.date()
        cutoff = today + timedelta(days=90)

        query = (
            select(Contract)
            .where(
                and_(
                    Contract.company_id == company_id,
                    Contract.status == ContractStatus.ACTIVE.value,
                    Contract.expiration_date.isnot(None),
                    Contract.expiration_date >= today,
                    Contract.expiration_date <= cutoff,
                )
            )
            .order_by(Contract.expiration_date.asc())
            .limit(20)
        )

        result = await db.execute(query)
        contracts = result.scalars().all()

        items: List[ProactiveActionItem] = []
        states = await self._load_states(db, company_id, [
            self._make_action_id(ProactiveActionType.CONTRACT_EXPIRY, str(c.id))
            for c in contracts
        ])

        for contract in contracts:
            action_id = self._make_action_id(
                ProactiveActionType.CONTRACT_EXPIRY, str(contract.id)
            )
            state = states.get(action_id)

            if self._is_suppressed(state, now_utc):
                continue

            expiry_date: Optional[date] = contract.expiration_date
            expiry_dt: Optional[datetime] = None
            days_left: Optional[int] = None

            if expiry_date:
                expiry_dt = datetime.combine(
                    expiry_date, datetime.min.time(), tzinfo=timezone.utc
                )
                days_left = (expiry_date - today).days

            total_value = getattr(contract, "total_value", None)
            fin_amount = float(total_value) if total_value is not None else None

            score = self._engine.calculate_score(
                action_type=ProactiveActionType.CONTRACT_EXPIRY,
                deadline=expiry_dt,
                financial_amount=fin_amount,
            )

            days_label = f"in {days_left} Tagen" if days_left is not None else ""

            items.append(ProactiveActionItem(
                id=action_id,
                action_type=ProactiveActionType.CONTRACT_EXPIRY.value,
                title=f"Vertrag läuft ab {days_label}: {contract.title}",
                description=(
                    f"Vertrag '{contract.title}' läuft am "
                    f"{expiry_date.strftime('%d.%m.%Y') if expiry_date else 'unbekannt'} ab. "
                    f"Bitte über Verlängerung oder Kündigung entscheiden."
                ),
                priority_score=score,
                priority_label=_score_to_label(score),
                deadline=expiry_dt.isoformat() if expiry_dt else None,
                financial_amount=fin_amount,
                source_id=str(contract.id),
                source_url=f"/contracts/{contract.id}",
                is_completed=False,
                metadata={
                    "contract_type": getattr(contract, "contract_type", "unknown"),
                    "days_until_expiry": days_left,
                    "auto_renewal": getattr(contract, "auto_renewal", False),
                },
            ))

        return items

    # =========================================================================
    # STATE MANAGEMENT (Completed / Snoozed)
    # =========================================================================

    async def _load_states(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        action_ids: List[str],
    ) -> Dict:
        """
        Lädt die persistierten Zustände für eine Liste von Aufgaben-IDs.

        Importiert ProactiveActionState lazy um Circular Imports zu vermeiden.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID
            action_ids: Liste der Aufgaben-IDs

        Returns:
            Dict: action_id -> ProactiveActionState (oder leeres Dict)
        """
        if not action_ids:
            return {}

        try:
            from app.db.models_autonomy import ProactiveActionState

            query = select(ProactiveActionState).where(
                and_(
                    ProactiveActionState.company_id == company_id,
                    ProactiveActionState.action_id.in_(action_ids),
                )
            )
            result = await db.execute(query)
            rows = result.scalars().all()
            return {row.action_id: row for row in rows}
        except Exception:  # noqa: BLE001
            # Tabelle existiert noch nicht - graceful degradation
            return {}

    async def _get_or_create_state(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        action_id: str,
    ) -> object:
        """
        Holt oder erstellt einen ProactiveActionState-Eintrag.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID
            action_id:  Aufgaben-ID

        Returns:
            ProactiveActionState-Instanz
        """
        from app.db.models_autonomy import ProactiveActionState

        query = select(ProactiveActionState).where(
            and_(
                ProactiveActionState.company_id == company_id,
                ProactiveActionState.action_id == action_id,
            )
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()

        if state is None:
            state = ProactiveActionState(
                id=uuid.uuid4(),
                company_id=company_id,
                action_id=action_id,
                is_completed=False,
                completed_at=None,
                snoozed_until=None,
            )
            db.add(state)
            await db.flush()

        return state

    async def _reset_expired_snoozes(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> None:
        """
        Setzt abgelaufene Snooze-Zeiträume zurück.

        Args:
            db:         Datenbank-Session
            company_id: Tenant-ID
        """
        try:
            from app.db.models_autonomy import ProactiveActionState

            now_utc = datetime.now(tz=timezone.utc)
            stmt = (
                update(ProactiveActionState)
                .where(
                    and_(
                        ProactiveActionState.company_id == company_id,
                        ProactiveActionState.snoozed_until.isnot(None),
                        ProactiveActionState.snoozed_until <= now_utc,
                    )
                )
                .values(snoozed_until=None)
            )
            await db.execute(stmt)
            await db.commit()
        except Exception:  # noqa: BLE001
            pass  # Graceful degradation falls Tabelle fehlt

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _make_action_id(
        self,
        action_type: ProactiveActionType,
        source_id: str,
    ) -> str:
        """
        Erstellt eine eindeutige Aufgaben-ID aus Typ und Quell-ID.

        Format: '{action_type}:{source_id}'

        Args:
            action_type: Aufgabentyp
            source_id:   ID des Quelldatensatzes

        Returns:
            Zusammengesetzte Aufgaben-ID
        """
        return f"{action_type.value}:{source_id}"

    def _parse_action_type(self, action_id: str) -> str:
        """
        Extrahiert den Aufgabentyp aus einer zusammengesetzten Aufgaben-ID.

        Args:
            action_id: Zusammengesetzte Aufgaben-ID

        Returns:
            Aufgabentyp (oder 'unknown')
        """
        parts = action_id.split(":", 1)
        return parts[0] if parts else "unknown"

    def _is_suppressed(self, state: Optional[object], now_utc: datetime) -> bool:
        """
        Prüft ob eine Aufgabe unterdrückt werden soll (erledigt oder gesnoozet).

        Args:
            state:   ProactiveActionState (oder None)
            now_utc: Aktueller UTC-Zeitstempel

        Returns:
            True wenn Aufgabe unterdrückt werden soll
        """
        if state is None:
            return False

        if getattr(state, "is_completed", False):
            return True

        snoozed_until = getattr(state, "snoozed_until", None)
        if snoozed_until is not None:
            if snoozed_until.tzinfo is None:
                snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
            if snoozed_until > now_utc:
                return True

        return False

    def _extract_amount(self, doc: object) -> Optional[float]:
        """
        Versucht einen Geldbetrag aus den Dokumentmetadaten zu extrahieren.

        Args:
            doc: Document-Instanz

        Returns:
            Geldbetrag in EUR oder None
        """
        meta = getattr(doc, "document_metadata", None) or {}
        for key in ("total_amount", "gesamtbetrag", "betrag", "amount", "nettobetrag"):
            val = meta.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return None

    def _build_progress(self, items: List[ProactiveActionItem]) -> ActionQueueProgress:
        """
        Berechnet den Fortschritt aus der Item-Liste.

        Args:
            items: Vollständige Item-Liste (inkl. erledigter/gesnoozeter Einträge)

        Returns:
            ActionQueueProgress
        """
        total = len(items)
        completed = sum(1 for i in items if i.is_completed)
        snoozed = sum(
            1 for i in items if not i.is_completed and i.snoozed_until is not None
        )
        pending = total - completed - snoozed
        rate = completed / total if total > 0 else 0.0

        by_type: Dict = {}
        for item in items:
            by_type.setdefault(item.action_type, {"total": 0, "completed": 0})
            by_type[item.action_type]["total"] += 1
            if item.is_completed:
                by_type[item.action_type]["completed"] += 1

        return ActionQueueProgress(
            total=total,
            completed=completed,
            snoozed=snoozed,
            pending=pending,
            completion_rate=round(rate, 4),
            by_type=by_type,
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _score_to_label(score: float) -> str:
    """
    Konvertiert einen Prioritäts-Score in ein lesbares Label (Deutsch).

    Args:
        score: Score [0.0, 1.0]

    Returns:
        'kritisch' | 'hoch' | 'mittel' | 'niedrig'
    """
    if score >= 0.75:
        return "kritisch"
    if score >= 0.50:
        return "hoch"
    if score >= 0.25:
        return "mittel"
    return "niedrig"


# =============================================================================
# SINGLETON
# =============================================================================


_proactive_service: Optional[ProactiveActionQueueService] = None


def get_proactive_action_queue_service() -> ProactiveActionQueueService:
    """Gibt die Singleton-Instanz des ProactiveActionQueueService zurück."""
    global _proactive_service
    if _proactive_service is None:
        _proactive_service = ProactiveActionQueueService()
    return _proactive_service
