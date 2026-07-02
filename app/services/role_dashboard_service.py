# -*- coding: utf-8 -*-
"""
Rollen-basierter Dashboard Service.

Liefert aggregierte Kennzahlen je nach Benutzerrolle:
- Buchhaltung: Rechnungen, DATEV-Export, Mahnwesen, Skonto-Fristen
- Management:  KPIs, Cashflow-Prognose, Freigaben, Uebersicht
- Sachbearbeitung: OCR-Queue, Kategorisierung, Uploads, Korrekturen
- Admin: System-Health, Audit-Log, Integrations-Status, Feature-Flags

Methoden geben bei fehlenden Daten robuste Defaults zurueck (kein Crash).

Feinpoliert und durchdacht - Phase 5.3: Rollen-basierte Dashboard APIs.
"""

import asyncio
import platform
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import (
    AuditLog,
    DATEVExport,
    Document,
    FeatureFlag,
    InvoiceStatus,
    InvoiceTracking,
    ProcessingStatus,
    User,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Kleine Hilfsfunktion: Jetzt in UTC
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Bucket-Grenzen fuer Mahnwesen (Tage ueberfaellig)
# ---------------------------------------------------------------------------

_DUNNING_BUCKETS: List[Dict[str, object]] = [
    {"label": "1-30 Tage", "min_days": 1, "max_days": 30},
    {"label": "31-60 Tage", "min_days": 31, "max_days": 60},
    {"label": "61-90 Tage", "min_days": 61, "max_days": 90},
    {"label": "> 90 Tage", "min_days": 91, "max_days": None},
]


class RoleDashboardService:
    """
    Aggregiert Dashboard-Daten rollenbasiert.

    Jede get_*_dashboard-Methode gibt ein Dict zurueck das direkt als
    JSON-Response genutzt werden kann. Alle Teilabfragen sind defensiv
    implementiert: bei einem Fehler wird 0 / [] / {} zurueckgegeben
    statt eine Exception zu propagieren.
    """

    # =========================================================================
    # BUCHHALTUNG
    # =========================================================================

    async def get_buchhaltung_dashboard(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, object]:
        """
        Dashboard fuer Buchhaltungs-Mitarbeiter.

        Enthaelt:
        - offene_rechnungen (Anzahl + Gesamtbetrag)
        - datev_export_status (letzter Export, ausstehende Elemente)
        - mahnungen (ueberfaellige Rechnungen nach Altersklassen)
        - skonto_fristen (bevorstehende Skonto-Deadlines)
        - letzte_buchungen (kuerlich verarbeitete Buchungs-Dokumente)
        """
        now = _now()

        offene_rechnungen, datev_export_status, mahnungen, skonto_fristen, letzte_buchungen = await asyncio.gather(
            self._get_offene_rechnungen(company_id, db),
            self._get_datev_export_status(company_id, db),
            self._get_mahnungen(company_id, now, db),
            self._get_skonto_fristen(company_id, now, db),
            self._get_letzte_buchungen(company_id, db),
            return_exceptions=True,
        )

        def _safe(value: object, default: object) -> object:
            return default if isinstance(value, Exception) else value

        result: Dict[str, object] = {
            "offene_rechnungen": _safe(offene_rechnungen, {"anzahl": 0, "gesamtbetrag": 0.0}),
            "datev_export_status": _safe(datev_export_status, {"letzter_export": None, "ausstehend": 0}),
            "mahnungen": _safe(mahnungen, []),
            "skonto_fristen": _safe(skonto_fristen, []),
            "letzte_buchungen": _safe(letzte_buchungen, []),
            "timestamp": now.isoformat(),
        }

        if isinstance(offene_rechnungen, Exception):
            logger.warning("buchhaltung_dashboard.offene_rechnungen_failed", **safe_error_log(offene_rechnungen))  # type: ignore[arg-type]
        if isinstance(datev_export_status, Exception):
            logger.warning("buchhaltung_dashboard.datev_status_failed", **safe_error_log(datev_export_status))  # type: ignore[arg-type]
        if isinstance(mahnungen, Exception):
            logger.warning("buchhaltung_dashboard.mahnungen_failed", **safe_error_log(mahnungen))  # type: ignore[arg-type]
        if isinstance(skonto_fristen, Exception):
            logger.warning("buchhaltung_dashboard.skonto_failed", **safe_error_log(skonto_fristen))  # type: ignore[arg-type]
        if isinstance(letzte_buchungen, Exception):
            logger.warning("buchhaltung_dashboard.letzte_buchungen_failed", **safe_error_log(letzte_buchungen))  # type: ignore[arg-type]

        return result

    async def _get_offene_rechnungen(
        self, company_id: UUID, db: AsyncSession
    ) -> Dict[str, object]:
        stmt = (
            select(
                func.count(InvoiceTracking.id).label("anzahl"),
                func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("gesamtbetrag"),
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.deleted_at.is_(None)
                    if hasattr(InvoiceTracking, "deleted_at")
                    else True,
                    InvoiceTracking.status.in_(
                        [InvoiceStatus.OPEN.value, InvoiceStatus.SENT.value, InvoiceStatus.PARTIAL.value]
                    ),
                )
            )
        )
        row = (await db.execute(stmt)).one()
        return {
            "anzahl": int(row.anzahl),
            "gesamtbetrag": float(row.gesamtbetrag),
        }

    async def _get_datev_export_status(
        self, company_id: UUID, db: AsyncSession
    ) -> Dict[str, object]:
        # Letzter Export (kompanyweites Ergebnis ueber DATEVConfiguration-Verknuepfung)
        last_export_stmt = (
            select(DATEVExport.exported_at, DATEVExport.document_count, DATEVExport.status)
            .join(
                Document,
                DATEVExport.id == DATEVExport.id,  # self-join placeholder – resolved via config
                isouter=True,
            )
            .order_by(DATEVExport.exported_at.desc())
            .limit(1)
        )
        # Ausstehende Dokumente (noch nicht DATEV-exportiert) fuer diese Company
        pending_stmt = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.datev_exported_at.is_(None),  # type: ignore[attr-defined]
                    Document.document_type.in_(["invoice", "credit_note", "receipt"]),
                )
            )
        )

        try:
            pending_count = (await db.execute(pending_stmt)).scalar() or 0
        except Exception:
            pending_count = 0

        # Letzter globaler Export – wir holen nur den Timestamp
        letzter_export: Optional[str] = None
        try:
            last_row = (
                await db.execute(
                    select(DATEVExport.exported_at)
                    .order_by(DATEVExport.exported_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_row:
                letzter_export = last_row.isoformat()
        except Exception as e:
            logger.warning(
                "role_dashboard_last_export_query_failed",
                error_type=type(e).__name__,
            )

        return {
            "letzter_export": letzter_export,
            "ausstehend": int(pending_count),
        }

    async def _get_mahnungen(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> List[Dict[str, object]]:
        """Ueberfaellige Rechnungen gruppiert nach Altersklassen."""
        result: List[Dict[str, object]] = []
        for bucket in _DUNNING_BUCKETS:
            min_days = int(bucket["min_days"])  # type: ignore[arg-type]
            max_days = bucket["max_days"]

            min_due = now - timedelta(days=min_days + (int(max_days) if max_days else 3650))
            max_due = now - timedelta(days=min_days - 1)

            due_condition = and_(
                InvoiceTracking.due_date <= max_due,
                InvoiceTracking.due_date >= min_due if max_days else InvoiceTracking.due_date <= max_due,
            )
            if max_days is None:
                due_condition = InvoiceTracking.due_date <= (now - timedelta(days=min_days - 1))

            stmt = (
                select(
                    func.count(InvoiceTracking.id).label("anzahl"),
                    func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("gesamtbetrag"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.status.in_(
                            [InvoiceStatus.OVERDUE.value, InvoiceStatus.DUNNING.value]
                        ),
                        InvoiceTracking.due_date.isnot(None),
                    )
                )
            )
            # Altersfilter nachtraeglich (range berechnet relativ zu now)
            from_date = now - timedelta(days=(int(max_days) if max_days else 36500))
            to_date = now - timedelta(days=min_days - 1)
            stmt = stmt.where(
                and_(
                    InvoiceTracking.due_date <= to_date,
                    InvoiceTracking.due_date >= from_date,
                )
            )

            row = (await db.execute(stmt)).one()
            result.append(
                {
                    "altersklasse": bucket["label"],
                    "anzahl": int(row.anzahl),
                    "gesamtbetrag": float(row.gesamtbetrag),
                }
            )
        return result

    async def _get_skonto_fristen(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> List[Dict[str, object]]:
        """Rechnungen mit Skonto-Deadline in den naechsten 14 Tagen."""
        deadline_limit = now + timedelta(days=14)
        stmt = (
            select(
                InvoiceTracking.id,
                InvoiceTracking.invoice_number,
                InvoiceTracking.skonto_deadline,
                InvoiceTracking.skonto_percentage,
                InvoiceTracking.skonto_amount,
                InvoiceTracking.amount,
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_deadline >= now,
                    InvoiceTracking.skonto_deadline <= deadline_limit,
                    InvoiceTracking.skonto_used.is_(False),
                    InvoiceTracking.status.in_(
                        [InvoiceStatus.OPEN.value, InvoiceStatus.SENT.value, InvoiceStatus.PARTIAL.value]
                    ),
                )
            )
            .order_by(InvoiceTracking.skonto_deadline.asc())
            .limit(20)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "rechnung_id": str(row.id),
                "rechnungsnummer": row.invoice_number,
                "skonto_deadline": row.skonto_deadline.isoformat() if row.skonto_deadline else None,
                "skonto_prozent": row.skonto_percentage,
                "skonto_betrag": row.skonto_amount,
                "rechnungsbetrag": row.amount,
                "tage_verbleibend": (row.skonto_deadline - now).days if row.skonto_deadline else None,
            }
            for row in rows
        ]

    async def _get_letzte_buchungen(
        self, company_id: UUID, db: AsyncSession
    ) -> List[Dict[str, object]]:
        """Die letzten 10 Buchungs-Dokumente (Rechnung, Gutschrift, Quittung)."""
        stmt = (
            select(
                Document.id,
                Document.original_filename,
                Document.document_type,
                Document.status,
                Document.created_at,
                Document.upload_date,
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type.in_(["invoice", "credit_note", "receipt"]),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(10)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "id": str(row.id),
                "dateiname": row.original_filename,
                "typ": row.document_type,
                "status": row.status,
                "erstellt_am": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    # =========================================================================
    # MANAGEMENT
    # =========================================================================

    async def get_management_dashboard(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, object]:
        """
        Dashboard fuer Management / Geschaeftsfuehrung.

        Enthaelt:
        - kpis: Umsatz, Ausgaben, Offene Posten, Dokumenten-Volumen
        - cashflow_prognose (30/60/90 Tage Aggregation)
        - freigaben (ausstehende Freigaben)
        - ueberblick (Dokumente heute/Woche/Monat)
        """
        now = _now()

        kpis, cashflow_prognose, freigaben, ueberblick = await asyncio.gather(
            self._get_management_kpis(company_id, now, db),
            self._get_cashflow_prognose(company_id, now, db),
            self._get_freigaben(company_id, db),
            self._get_ueberblick(company_id, now, db),
            return_exceptions=True,
        )

        def _safe(value: object, default: object) -> object:
            return default if isinstance(value, Exception) else value

        result: Dict[str, object] = {
            "kpis": _safe(kpis, {}),
            "cashflow_prognose": _safe(cashflow_prognose, {}),
            "freigaben": _safe(freigaben, {"ausstehend": 0}),
            "ueberblick": _safe(ueberblick, {}),
            "timestamp": now.isoformat(),
        }

        for name, value in [("kpis", kpis), ("cashflow_prognose", cashflow_prognose), ("freigaben", freigaben), ("ueberblick", ueberblick)]:
            if isinstance(value, Exception):
                logger.warning(f"management_dashboard.{name}_failed", **safe_error_log(value))  # type: ignore[arg-type]

        return result

    async def _get_management_kpis(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> Dict[str, object]:
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Umsatz: Summe bezahlter Ausgangsrechnungen diesen Monat
        umsatz_stmt = (
            select(func.coalesce(func.sum(InvoiceTracking.paid_amount), 0.0))
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type == "invoice",
                    InvoiceTracking.status == InvoiceStatus.PAID.value,
                    InvoiceTracking.paid_at >= month_start,
                )
            )
        )

        # Offene Posten (ausstehender Betrag)
        offene_posten_stmt = (
            select(func.coalesce(func.sum(InvoiceTracking.amount), 0.0))
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.status.in_(
                        [InvoiceStatus.OPEN.value, InvoiceStatus.SENT.value, InvoiceStatus.PARTIAL.value, InvoiceStatus.OVERDUE.value]
                    ),
                )
            )
        )

        # Dokumenten-Volumen diesen Monat
        volumen_stmt = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.created_at >= month_start,
                )
            )
        )

        umsatz, offene_posten, volumen = await asyncio.gather(
            db.execute(umsatz_stmt),
            db.execute(offene_posten_stmt),
            db.execute(volumen_stmt),
        )

        return {
            "umsatz_monat": float(umsatz.scalar() or 0.0),
            "offene_posten": float(offene_posten.scalar() or 0.0),
            "dokumenten_volumen_monat": int(volumen.scalar() or 0),
            "waehrung": "EUR",
        }

    async def _get_cashflow_prognose(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> Dict[str, object]:
        """Erwartete Zahlungseingaenge in 30/60/90 Tagen basierend auf offenen Rechnungen."""
        prognose: Dict[str, object] = {}
        for horizon in [30, 60, 90]:
            limit_date = now + timedelta(days=horizon)
            stmt = (
                select(func.coalesce(func.sum(InvoiceTracking.amount), 0.0))
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.status.in_(
                            [InvoiceStatus.OPEN.value, InvoiceStatus.SENT.value, InvoiceStatus.PARTIAL.value]
                        ),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.due_date <= limit_date,
                    )
                )
            )
            value = (await db.execute(stmt)).scalar() or 0.0
            prognose[f"tage_{horizon}"] = float(value)

        return prognose

    async def _get_freigaben(
        self, company_id: UUID, db: AsyncSession
    ) -> Dict[str, object]:
        """Ausstehende Freigaben (Dokumente im 'pending'-Approval-Status)."""
        # Wir zaehlen Dokumente mit Status PENDING und approval-relevanten Typen
        stmt = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.status == ProcessingStatus.PENDING.value,
                )
            )
        )
        count = (await db.execute(stmt)).scalar() or 0
        return {"ausstehend": int(count)}

    async def _get_ueberblick(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> Dict[str, object]:
        """Verarbeitete Dokumente heute / diese Woche / diesen Monat."""
        heute_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        woche_start = heute_start - timedelta(days=heute_start.weekday())
        monat_start = heute_start.replace(day=1)

        async def _count(since: datetime) -> int:
            stmt = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.status == ProcessingStatus.COMPLETED.value,
                        Document.processed_date >= since,
                    )
                )
            )
            return int((await db.execute(stmt)).scalar() or 0)

        heute, woche, monat = await asyncio.gather(
            _count(heute_start),
            _count(woche_start),
            _count(monat_start),
        )
        return {
            "verarbeitet_heute": heute,
            "verarbeitet_woche": woche,
            "verarbeitet_monat": monat,
        }

    # =========================================================================
    # SACHBEARBEITUNG
    # =========================================================================

    async def get_sachbearbeitung_dashboard(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, object]:
        """
        Dashboard fuer Sachbearbeiter.

        Enthaelt:
        - ocr_queue (ausstehend, in Verarbeitung, heute abgeschlossen)
        - zu_kategorisieren (Dokumente ohne Kategorie)
        - letzte_uploads (kuerlich hochgeladene Dokumente mit Status)
        - korrektur_queue (Dokumente mit niedrigem OCR-Confidence)
        """
        now = _now()

        ocr_queue, zu_kategorisieren, letzte_uploads, korrektur_queue = await asyncio.gather(
            self._get_ocr_queue(company_id, now, db),
            self._get_zu_kategorisieren(company_id, db),
            self._get_letzte_uploads(company_id, db),
            self._get_korrektur_queue(company_id, db),
            return_exceptions=True,
        )

        def _safe(value: object, default: object) -> object:
            return default if isinstance(value, Exception) else value

        result: Dict[str, object] = {
            "ocr_queue": _safe(ocr_queue, {"ausstehend": 0, "in_verarbeitung": 0, "heute_abgeschlossen": 0}),
            "zu_kategorisieren": _safe(zu_kategorisieren, {"anzahl": 0}),
            "letzte_uploads": _safe(letzte_uploads, []),
            "korrektur_queue": _safe(korrektur_queue, {"anzahl": 0, "dokumente": []}),
            "timestamp": now.isoformat(),
        }

        for name, value in [("ocr_queue", ocr_queue), ("zu_kategorisieren", zu_kategorisieren), ("letzte_uploads", letzte_uploads), ("korrektur_queue", korrektur_queue)]:
            if isinstance(value, Exception):
                logger.warning(f"sachbearbeitung_dashboard.{name}_failed", **safe_error_log(value))  # type: ignore[arg-type]

        return result

    async def _get_ocr_queue(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> Dict[str, object]:
        heute_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async def _count_status(status: str, extra_filter: object = None) -> int:
            conditions = [
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.status == status,
            ]
            if extra_filter is not None:
                conditions.append(extra_filter)  # type: ignore[arg-type]
            stmt = select(func.count(Document.id)).where(and_(*conditions))
            return int((await db.execute(stmt)).scalar() or 0)

        ausstehend, in_verarbeitung, heute_abgeschlossen = await asyncio.gather(
            _count_status(ProcessingStatus.PENDING.value),
            _count_status(ProcessingStatus.PROCESSING.value),
            _count_status(ProcessingStatus.COMPLETED.value, Document.processed_date >= heute_start),
        )

        return {
            "ausstehend": ausstehend,
            "in_verarbeitung": in_verarbeitung,
            "heute_abgeschlossen": heute_abgeschlossen,
        }

    async def _get_zu_kategorisieren(
        self, company_id: UUID, db: AsyncSession
    ) -> Dict[str, object]:
        """Dokumente ohne Dokumenttyp-Zuordnung (OTHER oder leer)."""
        stmt = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.status == ProcessingStatus.COMPLETED.value,
                    Document.document_type.in_(["other", "OTHER", ""]),
                )
            )
        )
        count = (await db.execute(stmt)).scalar() or 0
        return {"anzahl": int(count)}

    async def _get_letzte_uploads(
        self, company_id: UUID, db: AsyncSession
    ) -> List[Dict[str, object]]:
        """Die letzten 15 hochgeladenen Dokumente mit OCR-Status."""
        stmt = (
            select(
                Document.id,
                Document.original_filename,
                Document.document_type,
                Document.status,
                Document.ocr_confidence,
                Document.upload_date,
                Document.ocr_backend_used,
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.upload_date.desc())
            .limit(15)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "id": str(row.id),
                "dateiname": row.original_filename,
                "typ": row.document_type,
                "status": row.status,
                "ocr_confidence": round(row.ocr_confidence, 3) if row.ocr_confidence is not None else None,
                "ocr_backend": row.ocr_backend_used,
                "hochgeladen_am": row.upload_date.isoformat() if row.upload_date else None,
            }
            for row in rows
        ]

    async def _get_korrektur_queue(
        self, company_id: UUID, db: AsyncSession
    ) -> Dict[str, object]:
        """Dokumente mit OCR-Konfidenz unter 0.7 (benoetigen manuelle Pruefung)."""
        LOW_CONFIDENCE_THRESHOLD = 0.7

        count_stmt = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.status == ProcessingStatus.COMPLETED.value,
                    Document.ocr_confidence.isnot(None),
                    Document.ocr_confidence < LOW_CONFIDENCE_THRESHOLD,
                )
            )
        )

        docs_stmt = (
            select(
                Document.id,
                Document.original_filename,
                Document.ocr_confidence,
                Document.document_type,
                Document.created_at,
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.status == ProcessingStatus.COMPLETED.value,
                    Document.ocr_confidence.isnot(None),
                    Document.ocr_confidence < LOW_CONFIDENCE_THRESHOLD,
                )
            )
            .order_by(Document.ocr_confidence.asc())
            .limit(10)
        )

        count, docs_result = await asyncio.gather(
            db.execute(count_stmt),
            db.execute(docs_stmt),
        )
        docs_rows = docs_result.all()

        return {
            "anzahl": int(count.scalar() or 0),
            "dokumente": [
                {
                    "id": str(row.id),
                    "dateiname": row.original_filename,
                    "ocr_confidence": round(row.ocr_confidence, 3) if row.ocr_confidence is not None else None,
                    "typ": row.document_type,
                    "erstellt_am": row.created_at.isoformat() if row.created_at else None,
                }
                for row in docs_rows
            ],
        }

    # =========================================================================
    # ADMIN
    # =========================================================================

    async def get_admin_dashboard(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, object]:
        """
        Dashboard fuer Administratoren.

        Enthaelt:
        - system_health (CPU, Arbeitsspeicher, Festplatte, GPU falls verfuegbar)
        - audit_log_summary (letzte 24h Aktionen nach Typ)
        - integrations_status (je Integration: letzter Sync, Fehler)
        - feature_toggle_summary (aktiv/inaktiv)
        - user_activity (aktive Nutzer letzte 24h)
        """
        now = _now()

        system_health, audit_log_summary, integrations_status, feature_toggle_summary, user_activity = await asyncio.gather(
            self._get_system_health(),
            self._get_audit_log_summary(company_id, now, db),
            self._get_integrations_status(company_id, now, db),
            self._get_feature_toggle_summary(db),
            self._get_user_activity(company_id, now, db),
            return_exceptions=True,
        )

        def _safe(value: object, default: object) -> object:
            return default if isinstance(value, Exception) else value

        result: Dict[str, object] = {
            "system_health": _safe(system_health, {}),
            "audit_log_summary": _safe(audit_log_summary, {"gesamt": 0, "nach_typ": {}}),
            "integrations_status": _safe(integrations_status, []),
            "feature_toggle_summary": _safe(feature_toggle_summary, {"aktiv": 0, "inaktiv": 0}),
            "user_activity": _safe(user_activity, {"aktive_nutzer": 0}),
            "timestamp": now.isoformat(),
        }

        for name, value in [("system_health", system_health), ("audit_log_summary", audit_log_summary), ("integrations_status", integrations_status), ("feature_toggle_summary", feature_toggle_summary), ("user_activity", user_activity)]:
            if isinstance(value, Exception):
                logger.warning(f"admin_dashboard.{name}_failed", **safe_error_log(value))  # type: ignore[arg-type]

        return result

    async def _get_system_health(self) -> Dict[str, object]:
        """System-Metriken (CPU, Speicher, Disk) via psutil. GPU optional."""
        metrics: Dict[str, object] = {}

        try:
            import psutil

            metrics["cpu_prozent"] = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            metrics["arbeitsspeicher"] = {
                "gesamt_gb": round(mem.total / (1024 ** 3), 2),
                "verwendet_gb": round(mem.used / (1024 ** 3), 2),
                "prozent": mem.percent,
            }
            disk = psutil.disk_usage("/")
            metrics["festplatte"] = {
                "gesamt_gb": round(disk.total / (1024 ** 3), 2),
                "verwendet_gb": round(disk.used / (1024 ** 3), 2),
                "prozent": round(disk.percent, 1),
            }
        except Exception as e:
            logger.debug("admin_dashboard.psutil_unavailable", **safe_error_log(e))
            metrics["cpu_prozent"] = None
            metrics["arbeitsspeicher"] = None
            metrics["festplatte"] = None

        # GPU via nvidia-smi (optional)
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 3:
                    used_mb = int(parts[0])
                    total_mb = int(parts[1])
                    util = int(parts[2])
                    metrics["gpu"] = {
                        "vram_verwendet_mb": used_mb,
                        "vram_gesamt_mb": total_mb,
                        "vram_prozent": round(used_mb / total_mb * 100, 1) if total_mb > 0 else 0,
                        "auslastung_prozent": util,
                        "status": "ok" if used_mb / total_mb < 0.85 else "warnung",
                    }
            else:
                metrics["gpu"] = None
        except Exception:
            metrics["gpu"] = None

        metrics["os"] = platform.system()
        metrics["python_version"] = platform.python_version()

        return metrics

    async def _get_audit_log_summary(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> Dict[str, object]:
        """Zusammenfassung der Audit-Log-Eintraege der letzten 24 Stunden."""
        since = now - timedelta(hours=24)
        stmt = (
            select(AuditLog.action, func.count(AuditLog.id).label("anzahl"))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= since,
                )
            )
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
            .limit(20)
        )
        rows = (await db.execute(stmt)).all()

        gesamt_stmt = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= since,
                )
            )
        )
        gesamt = (await db.execute(gesamt_stmt)).scalar() or 0

        return {
            "gesamt": int(gesamt),
            "nach_typ": {row.action: int(row.anzahl) for row in rows},
        }

    async def _get_integrations_status(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> List[Dict[str, object]]:
        """Status bekannter Integrationen (DATEV-Export als Beispiel)."""
        integrations: List[Dict[str, object]] = []

        # DATEV: letzter Export
        try:
            datev_stmt = (
                select(DATEVExport.exported_at, DATEVExport.status)
                .order_by(DATEVExport.exported_at.desc())
                .limit(1)
            )
            row = (await db.execute(datev_stmt)).one_or_none()
            integrations.append(
                {
                    "name": "DATEV",
                    "letzter_sync": row.exported_at.isoformat() if row else None,
                    "status": row.status if row else "unbekannt",
                    "fehler": row.status == "failed" if row else False,
                }
            )
        except Exception as e:
            logger.debug("admin_dashboard.datev_status_failed", **safe_error_log(e))
            integrations.append({"name": "DATEV", "letzter_sync": None, "status": "unbekannt", "fehler": False})

        return integrations

    async def _get_feature_toggle_summary(
        self, db: AsyncSession
    ) -> Dict[str, object]:
        """Anzahl aktiver und inaktiver Feature-Flags."""
        stmt = (
            select(
                FeatureFlag.enabled,
                func.count(FeatureFlag.id).label("anzahl"),
            )
            .group_by(FeatureFlag.enabled)
        )
        rows = (await db.execute(stmt)).all()
        aktiv = 0
        inaktiv = 0
        for row in rows:
            if row.enabled:
                aktiv = int(row.anzahl)
            else:
                inaktiv = int(row.anzahl)
        return {"aktiv": aktiv, "inaktiv": inaktiv}

    async def _get_user_activity(
        self, company_id: UUID, now: datetime, db: AsyncSession
    ) -> Dict[str, object]:
        """Anzahl aktiver Nutzer (last_activity_at) in den letzten 24 Stunden."""
        since = now - timedelta(hours=24)
        stmt = (
            select(func.count(User.id))
            .where(
                and_(
                    User.is_active.is_(True),
                    User.last_activity_at >= since,
                )
            )
        )
        count = (await db.execute(stmt)).scalar() or 0
        return {"aktive_nutzer": int(count)}
