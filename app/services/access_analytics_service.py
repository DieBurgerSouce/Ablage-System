# -*- coding: utf-8 -*-
"""
Zugriffs-Analytik Service fuer das Ablage-System.

Analysiert Audit-Logs, um Muster in Dokumentenzugriffen zu erkennen,
Anomalien aufzuspueren und Statistiken fuer das Admin-Dashboard bereitzustellen.

Phaenomene die erkannt werden:
- Massen-Downloads (>50 Downloads/Stunde pro Benutzer)
- Brute-Force-Versuche (>10 fehlgeschlagene Logins/Stunde pro IP)
- Zugriffe ausserhalb der Geschaeftszeiten (23:00-05:00 Uhr)
- Massen-Dokumentenscans (>100 eindeutige Dokumente in 30 Minuten)
- Ungewoehnliche Exporte ausserhalb der Geschaeftszeiten

SECURITY: Niemals PII oder sensible Dokument-Inhalte loggen.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, text, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Document, User

logger = structlog.get_logger(__name__)


# =============================================================================
# Response-Schemas (Pydantic)
# =============================================================================


class TopDocument(BaseModel):
    """Meistbesuchtes Dokument."""

    document_id: str
    filename: str
    access_count: int


class ActiveUser(BaseModel):
    """Aktivster Benutzer nach Aktion-Anzahl."""

    user_id: str
    email: str
    action_count: int


class FailedLoginDay(BaseModel):
    """Fehlgeschlagene Logins pro Tag."""

    date: str
    count: int


class AccessOverview(BaseModel):
    """Uebersicht der Zugriffs-Analytik."""

    top_documents: List[TopDocument] = Field(default_factory=list)
    most_active_users: List[ActiveUser] = Field(default_factory=list)
    failed_logins_per_day: List[FailedLoginDay] = Field(default_factory=list)
    period_days: int
    total_events: int


class UserTimelineEntry(BaseModel):
    """Einzelner Eintrag in der Nutzer-Timeline."""

    event_id: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool
    timestamp: datetime


class UserTimeline(BaseModel):
    """Timeline aller Aktionen eines Benutzers."""

    user_id: str
    items: List[UserTimelineEntry] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


class DocumentAccessEntry(BaseModel):
    """Einzelner Dokumentenzugriff."""

    event_id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    ip_address: Optional[str] = None
    success: bool
    timestamp: datetime


class DocumentAccessLog(BaseModel):
    """Zugriffs-Log fuer ein einzelnes Dokument."""

    document_id: str
    items: List[DocumentAccessEntry] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


class AccessAnomaly(BaseModel):
    """Erkannte Zugriffs-Anomalie."""

    anomaly_type: str
    severity: str  # "warning" | "critical"
    description: str
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    count: int
    detected_at: datetime
    details: dict = Field(default_factory=dict)


class HourlyStats(BaseModel):
    """Stundliche Zugriffsverteilung fuer Heatmap."""

    hour: int  # 0-23
    count: int


class EventTypeStat(BaseModel):
    """Statistik fuer einen Event-Typ."""

    event_type: str
    count: int
    percentage: float


# =============================================================================
# Service-Implementierung
# =============================================================================


class AccessAnalyticsService:
    """Service fuer Zugriffs-Analytik und Anomalie-Erkennung.

    Alle Methoden erfordern company_id fuer Multi-Tenant-Isolation.
    Keine sensiblen Dokument-Inhalte werden protokolliert.
    """

    # Schwellenwerte fuer Anomalie-Erkennung
    MASS_DOWNLOAD_THRESHOLD = 50      # Downloads/Stunde pro Benutzer
    BRUTE_FORCE_THRESHOLD = 10        # Fehlgeschlagene Logins/Stunde pro IP
    OFF_HOURS_START = 23              # Stunde ab der Off-Hours beginnen
    OFF_HOURS_END = 5                 # Stunde bis zu der Off-Hours enden
    MASS_SCAN_THRESHOLD = 100         # Eindeutige Dokumente in 30 Minuten
    TOP_DOCUMENTS_LIMIT = 10          # Top-Dokumente fuer Uebersicht
    TOP_USERS_LIMIT = 10              # Aktivste Benutzer fuer Uebersicht
    MAX_DAYS = 90                     # Maximale Zeitspanne in Tagen

    # Action-Namen die als Download-Events gewertet werden
    DOWNLOAD_ACTIONS = frozenset({
        "document_download",
        "document_export",
        "document_view",
    })

    # Action-Namen die als Login-Fehler gewertet werden
    FAILED_LOGIN_ACTIONS = frozenset({
        "login_failed",
        "login_attempt_failed",
        "auth_failed",
    })

    # Action-Namen die als Exporte gewertet werden
    EXPORT_ACTIONS = frozenset({
        "document_export",
        "batch_export",
        "export_created",
    })

    async def get_overview(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 7,
    ) -> AccessOverview:
        """Uebersicht: Top-Dokumente, aktivste Nutzer, Fehlversuche.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID fuer Multi-Tenant-Isolation
            days: Anzahl der Tage fuer den Betrachtungszeitraum (max 90)

        Returns:
            AccessOverview mit aggregierten Metriken
        """
        days = min(days, self.MAX_DAYS)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info(
            "access_analytics_overview_requested",
            company_id=str(company_id),
            days=days,
        )

        base_conditions = and_(
            AuditLog.company_id == company_id,
            AuditLog.created_at >= cutoff,
        )

        # Gesamtanzahl Events im Zeitraum
        total_events_result = await db.execute(
            select(func.count(AuditLog.id)).where(base_conditions)
        )
        total_events: int = total_events_result.scalar() or 0

        # Top-10 meistbesuchte Dokumente (resource_type='document')
        top_docs_query = (
            select(
                AuditLog.resource_id,
                func.count(AuditLog.id).label("access_count"),
            )
            .where(
                and_(
                    base_conditions,
                    AuditLog.resource_type == "document",
                    AuditLog.resource_id.isnot(None),
                    AuditLog.success.is_(True),
                )
            )
            .group_by(AuditLog.resource_id)
            .order_by(func.count(AuditLog.id).desc())
            .limit(self.TOP_DOCUMENTS_LIMIT)
        )
        top_docs_result = await db.execute(top_docs_query)
        top_doc_rows = top_docs_result.fetchall()

        # Dateinamen fuer Top-Dokumente nachladen
        top_documents: List[TopDocument] = []
        for row in top_doc_rows:
            doc_id = row.resource_id
            filename = await self._get_document_filename(db, doc_id, company_id)
            top_documents.append(
                TopDocument(
                    document_id=str(doc_id),
                    filename=filename,
                    access_count=row.access_count,
                )
            )

        # Top-10 aktivste Benutzer
        active_users_query = (
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("action_count"),
            )
            .where(
                and_(
                    base_conditions,
                    AuditLog.user_id.isnot(None),
                )
            )
            .group_by(AuditLog.user_id)
            .order_by(func.count(AuditLog.id).desc())
            .limit(self.TOP_USERS_LIMIT)
        )
        active_users_result = await db.execute(active_users_query)
        active_user_rows = active_users_result.fetchall()

        most_active_users: List[ActiveUser] = []
        for row in active_user_rows:
            email = await self._get_user_email(db, row.user_id)
            most_active_users.append(
                ActiveUser(
                    user_id=str(row.user_id),
                    email=email,
                    action_count=row.action_count,
                )
            )

        # Fehlgeschlagene Logins pro Tag
        failed_logins_query = (
            select(
                func.date_trunc(literal_column("'day'"), AuditLog.created_at).label("day"),
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                    AuditLog.success.is_(False),
                    AuditLog.action.in_(list(self.FAILED_LOGIN_ACTIONS)),
                )
            )
            .group_by(func.date_trunc(literal_column("'day'"), AuditLog.created_at))
            .order_by(func.date_trunc(literal_column("'day'"), AuditLog.created_at))
        )
        failed_logins_result = await db.execute(failed_logins_query)
        failed_login_rows = failed_logins_result.fetchall()

        failed_logins_per_day: List[FailedLoginDay] = [
            FailedLoginDay(
                date=row.day.strftime("%Y-%m-%d"),
                count=row.count,
            )
            for row in failed_login_rows
        ]

        return AccessOverview(
            top_documents=top_documents,
            most_active_users=most_active_users,
            failed_logins_per_day=failed_logins_per_day,
            period_days=days,
            total_events=total_events,
        )

    async def get_user_timeline(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> UserTimeline:
        """Timeline der Aktionen eines Nutzers.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID fuer Multi-Tenant-Isolation
            user_id: ID des zu untersuchenden Benutzers
            offset: Paginierungs-Offset
            limit: Anzahl Eintraege pro Seite (max 200)

        Returns:
            UserTimeline mit paginierten Ereignissen
        """
        limit = min(limit, 200)

        logger.info(
            "access_analytics_user_timeline_requested",
            company_id=str(company_id),
            user_id=str(user_id),
        )

        conditions = and_(
            AuditLog.company_id == company_id,
            AuditLog.user_id == user_id,
        )

        # Gesamtanzahl
        count_result = await db.execute(
            select(func.count(AuditLog.id)).where(conditions)
        )
        total: int = count_result.scalar() or 0

        # Paginierte Eintraege, neueste zuerst
        entries_query = (
            select(AuditLog)
            .where(conditions)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        entries_result = await db.execute(entries_query)
        entries = entries_result.scalars().all()

        items: List[UserTimelineEntry] = [
            UserTimelineEntry(
                event_id=str(entry.id),
                action=entry.action,
                resource_type=entry.resource_type,
                resource_id=str(entry.resource_id) if entry.resource_id else None,
                ip_address=entry.ip_address,
                success=entry.success,
                timestamp=entry.created_at,
            )
            for entry in entries
        ]

        return UserTimeline(
            user_id=str(user_id),
            items=items,
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get_document_access_log(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> DocumentAccessLog:
        """Wer hat dieses Dokument wann angesehen/bearbeitet.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID fuer Multi-Tenant-Isolation
            document_id: ID des zu untersuchenden Dokuments
            offset: Paginierungs-Offset
            limit: Anzahl Eintraege pro Seite (max 200)

        Returns:
            DocumentAccessLog mit paginierten Zugriffen
        """
        limit = min(limit, 200)

        logger.info(
            "access_analytics_document_log_requested",
            company_id=str(company_id),
            document_id=str(document_id),
        )

        conditions = and_(
            AuditLog.company_id == company_id,
            AuditLog.resource_id == document_id,
            AuditLog.resource_type == "document",
        )

        # Gesamtanzahl
        count_result = await db.execute(
            select(func.count(AuditLog.id)).where(conditions)
        )
        total: int = count_result.scalar() or 0

        # Paginierte Eintraege mit Benutzer-Informationen
        entries_query = (
            select(AuditLog, User.email)
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(conditions)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        entries_result = await db.execute(entries_query)
        rows = entries_result.fetchall()

        items: List[DocumentAccessEntry] = [
            DocumentAccessEntry(
                event_id=str(row.AuditLog.id),
                user_id=str(row.AuditLog.user_id) if row.AuditLog.user_id else None,
                user_email=row.email,
                action=row.AuditLog.action,
                ip_address=row.AuditLog.ip_address,
                success=row.AuditLog.success,
                timestamp=row.AuditLog.created_at,
            )
            for row in rows
        ]

        return DocumentAccessLog(
            document_id=str(document_id),
            items=items,
            total=total,
            offset=offset,
            limit=limit,
        )

    async def detect_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
        hours: int = 24,
    ) -> List[AccessAnomaly]:
        """Erkennt ungewoehnliche Zugriffsmuster.

        Prueft auf:
        1. mass_download: >50 Downloads/Stunde pro Benutzer
        2. brute_force: >10 fehlgeschlagene Logins/Stunde pro IP
        3. off_hours_access: Erhebliche Aktivitaet zwischen 23:00-05:00 Uhr
        4. mass_document_scan: >100 eindeutige Dokumente in 30 Minuten
        5. unusual_export: Grosse Exporte ausserhalb der Geschaeftszeiten

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID fuer Multi-Tenant-Isolation
            hours: Betrachtungszeitraum in Stunden (max 168 = 7 Tage)

        Returns:
            Liste erkannter Anomalien, neueste zuerst
        """
        hours = min(hours, 168)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        anomalies: List[AccessAnomaly] = []
        detected_at = datetime.now(timezone.utc)

        logger.info(
            "access_analytics_anomaly_detection_started",
            company_id=str(company_id),
            hours=hours,
        )

        # --- 1. Massen-Download-Erkennung ---
        mass_download_query = (
            select(
                AuditLog.user_id,
                func.date_trunc(literal_column("'hour'"), AuditLog.created_at).label("hour_bucket"),
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                    AuditLog.user_id.isnot(None),
                    AuditLog.action.in_(list(self.DOWNLOAD_ACTIONS)),
                    AuditLog.success.is_(True),
                )
            )
            .group_by(
                AuditLog.user_id,
                func.date_trunc(literal_column("'hour'"), AuditLog.created_at),
            )
            .having(func.count(AuditLog.id) > self.MASS_DOWNLOAD_THRESHOLD)
        )
        md_result = await db.execute(mass_download_query)
        for row in md_result.fetchall():
            anomalies.append(
                AccessAnomaly(
                    anomaly_type="mass_download",
                    severity="critical",
                    description=(
                        f"Benutzer hat {row.count} Dokumente in einer Stunde heruntergeladen "
                        f"(Schwellenwert: {self.MASS_DOWNLOAD_THRESHOLD})."
                    ),
                    user_id=str(row.user_id),
                    count=row.count,
                    detected_at=detected_at,
                    details={"hour_bucket": row.hour_bucket.isoformat()},
                )
            )

        # --- 2. Brute-Force-Erkennung ---
        brute_force_query = (
            select(
                AuditLog.ip_address,
                func.date_trunc(literal_column("'hour'"), AuditLog.created_at).label("hour_bucket"),
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                    AuditLog.ip_address.isnot(None),
                    AuditLog.action.in_(list(self.FAILED_LOGIN_ACTIONS)),
                    AuditLog.success.is_(False),
                )
            )
            .group_by(
                AuditLog.ip_address,
                func.date_trunc(literal_column("'hour'"), AuditLog.created_at),
            )
            .having(func.count(AuditLog.id) > self.BRUTE_FORCE_THRESHOLD)
        )
        bf_result = await db.execute(brute_force_query)
        for row in bf_result.fetchall():
            anomalies.append(
                AccessAnomaly(
                    anomaly_type="brute_force",
                    severity="critical",
                    description=(
                        f"IP-Adresse hat {row.count} fehlgeschlagene Anmeldeversuche in einer Stunde "
                        f"(Schwellenwert: {self.BRUTE_FORCE_THRESHOLD})."
                    ),
                    ip_address=row.ip_address,
                    count=row.count,
                    detected_at=detected_at,
                    details={"hour_bucket": row.hour_bucket.isoformat()},
                )
            )

        # --- 3. Off-Hours-Zugriffe ---
        # Zaehlt Benutzer mit signifikanter Aktivitaet ausserhalb der Geschaeftszeiten
        # OFF_HOURS: 23:00-05:00 Uhr (Stunden 23, 0, 1, 2, 3, 4)
        off_hours_query = (
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                    AuditLog.user_id.isnot(None),
                    # Off-Hours: 23:00 bis 05:00 Uhr
                    text(
                        "EXTRACT(HOUR FROM created_at AT TIME ZONE 'Europe/Berlin') >= 23 "
                        "OR EXTRACT(HOUR FROM created_at AT TIME ZONE 'Europe/Berlin') < 5"
                    ),
                )
            )
            .group_by(AuditLog.user_id)
            .having(func.count(AuditLog.id) >= 20)  # Nur signifikante Aktivitaet melden
        )
        oh_result = await db.execute(off_hours_query)
        for row in oh_result.fetchall():
            anomalies.append(
                AccessAnomaly(
                    anomaly_type="off_hours_access",
                    severity="warning",
                    description=(
                        f"Benutzer hatte {row.count} Zugriffe ausserhalb der Geschaeftszeiten "
                        f"(23:00-05:00 Uhr) im Betrachtungszeitraum."
                    ),
                    user_id=str(row.user_id),
                    count=row.count,
                    detected_at=detected_at,
                    details={
                        "off_hours_start": self.OFF_HOURS_START,
                        "off_hours_end": self.OFF_HOURS_END,
                    },
                )
            )

        # --- 4. Massen-Dokumentenscan ---
        # Prueft ob ein Benutzer in 30 Minuten mehr als 100 verschiedene Dokumente aufgerufen hat
        scan_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        mass_scan_query = (
            select(
                AuditLog.user_id,
                func.count(func.distinct(AuditLog.resource_id)).label("unique_docs"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= scan_cutoff,
                    AuditLog.user_id.isnot(None),
                    AuditLog.resource_type == "document",
                    AuditLog.resource_id.isnot(None),
                    AuditLog.success.is_(True),
                )
            )
            .group_by(AuditLog.user_id)
            .having(
                func.count(func.distinct(AuditLog.resource_id)) > self.MASS_SCAN_THRESHOLD
            )
        )
        ms_result = await db.execute(mass_scan_query)
        for row in ms_result.fetchall():
            anomalies.append(
                AccessAnomaly(
                    anomaly_type="mass_document_scan",
                    severity="critical",
                    description=(
                        f"Benutzer hat {row.unique_docs} verschiedene Dokumente in 30 Minuten aufgerufen "
                        f"(Schwellenwert: {self.MASS_SCAN_THRESHOLD})."
                    ),
                    user_id=str(row.user_id),
                    count=row.unique_docs,
                    detected_at=detected_at,
                    details={"window_minutes": 30},
                )
            )

        # --- 5. Ungewoehnliche Exporte ausserhalb der Geschaeftszeiten ---
        unusual_export_query = (
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                    AuditLog.user_id.isnot(None),
                    AuditLog.action.in_(list(self.EXPORT_ACTIONS)),
                    AuditLog.success.is_(True),
                    text(
                        "EXTRACT(HOUR FROM created_at AT TIME ZONE 'Europe/Berlin') >= 23 "
                        "OR EXTRACT(HOUR FROM created_at AT TIME ZONE 'Europe/Berlin') < 5"
                    ),
                )
            )
            .group_by(AuditLog.user_id)
            .having(func.count(AuditLog.id) >= 5)
        )
        ue_result = await db.execute(unusual_export_query)
        for row in ue_result.fetchall():
            anomalies.append(
                AccessAnomaly(
                    anomaly_type="unusual_export",
                    severity="warning",
                    description=(
                        f"Benutzer hat {row.count} Exporte ausserhalb der Geschaeftszeiten durchgefuehrt."
                    ),
                    user_id=str(row.user_id),
                    count=row.count,
                    detected_at=detected_at,
                    details={"export_actions": list(self.EXPORT_ACTIONS)},
                )
            )

        logger.info(
            "access_analytics_anomaly_detection_completed",
            company_id=str(company_id),
            anomalies_found=len(anomalies),
        )

        return anomalies

    async def get_hourly_distribution(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 7,
    ) -> List[HourlyStats]:
        """Stuendliche Zugriffsverteilung fuer Heatmap-Visualisierung.

        Gibt fuer jede Stunde (0-23) die Gesamtanzahl der Zugriffe zurueck.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID fuer Multi-Tenant-Isolation
            days: Betrachtungszeitraum in Tagen (max 90)

        Returns:
            Liste von HourlyStats fuer alle 24 Stunden
        """
        days = min(days, self.MAX_DAYS)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        hourly_query = (
            select(
                func.extract("hour", AuditLog.created_at).label("hour"),
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                )
            )
            .group_by(func.extract("hour", AuditLog.created_at))
            .order_by(func.extract("hour", AuditLog.created_at))
        )
        result = await db.execute(hourly_query)
        rows = result.fetchall()

        # Sicherstellen dass alle 24 Stunden vertreten sind (fehlende mit 0)
        counts_by_hour = {int(row.hour): row.count for row in rows}
        return [
            HourlyStats(hour=h, count=counts_by_hour.get(h, 0))
            for h in range(24)
        ]

    async def get_event_type_stats(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 7,
    ) -> List[EventTypeStat]:
        """Verteilung der Event-Typen im Betrachtungszeitraum.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID fuer Multi-Tenant-Isolation
            days: Betrachtungszeitraum in Tagen (max 90)

        Returns:
            Liste von EventTypeStat, absteigend nach Haeufigkeit sortiert
        """
        days = min(days, self.MAX_DAYS)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Gesamtanzahl fuer Prozentberechnung
        total_result = await db.execute(
            select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                )
            )
        )
        total: int = total_result.scalar() or 0
        if total == 0:
            return []

        stats_query = (
            select(
                AuditLog.action,
                func.count(AuditLog.id).label("count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= cutoff,
                )
            )
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
            .limit(50)  # Top-50 Event-Typen
        )
        result = await db.execute(stats_query)
        rows = result.fetchall()

        return [
            EventTypeStat(
                event_type=row.action,
                count=row.count,
                percentage=round((row.count / total) * 100, 2),
            )
            for row in rows
        ]

    # -------------------------------------------------------------------------
    # Hilfsmethoden (private)
    # -------------------------------------------------------------------------

    async def _get_document_filename(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
    ) -> str:
        """Laed den Dateinamen eines Dokuments (mit Tenant-Pruefung).

        Bei nicht gefundenen Dokumenten wird ein Platzhalter zurueckgegeben.
        """
        try:
            result = await db.execute(
                select(Document.filename, Document.original_filename)
                .where(
                    and_(
                        Document.id == document_id,
                        Document.company_id == company_id,
                    )
                )
                .limit(1)
            )
            row = result.fetchone()
            if row:
                return row.original_filename or row.filename or str(document_id)
        except Exception as e:
            # OPEN-46: Audit-Lookup-Fehler sichtbar machen (war still -> Audit-Trail
            # zeigte stumm die ID statt des Dateinamens bei DB-Fehlern).
            logger.warning(
                "audit_document_filename_lookup_failed",
                document_id=str(document_id),
                company_id=str(company_id),
                error_type=type(e).__name__,
            )
        return str(document_id)

    async def _get_user_email(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> str:
        """Laed die E-Mail-Adresse eines Benutzers.

        Bei nicht gefundenen Benutzern wird ein Platzhalter zurueckgegeben.
        SECURITY: Nur E-Mail, keine weiteren PII.
        """
        try:
            result = await db.execute(
                select(User.email).where(User.id == user_id).limit(1)
            )
            row = result.fetchone()
            if row and row.email:
                return row.email
        except Exception as e:
            # OPEN-46: Audit-Lookup-Fehler sichtbar machen (war still).
            logger.warning(
                "audit_user_email_lookup_failed",
                user_id=str(user_id),
                error_type=type(e).__name__,
            )
        return str(user_id)
