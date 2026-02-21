# -*- coding: utf-8 -*-
"""
Dashboard-Builder Service fuer Ablage-System.

Phase 7.3: Dashboard-Builder

Zustaendigkeiten:
  - CRUD-Operationen fuer DashboardConfig und DashboardBuilderWidget
  - Rollen-basierte Standard-Dashboards
  - Live-Datenabfrage je Widget-Typ (Delegation an spezialisierte Services)
  - Teilen/Entteilen von Dashboards

Widget-Datenquellen-Routing:
  invoice_status      -> SmartDashboardService.get_finance_tab (InvoiceTracking)
  cashflow_chart      -> SmartDashboardService.get_finance_tab
  ocr_queue           -> SmartDashboardService.get_documents_tab (ProcessingJob)
  kpi_cards           -> SmartDashboardService.get_realtime_kpis
  anomaly_summary     -> AnomalyDetectionService (Anomaly-Tabelle)
  recent_documents    -> SmartDashboardService.get_documents_tab
  open_tasks          -> SmartDashboardService.get_workflows_tab
  integration_health  -> SmartDashboardService.get_system_tab
  active_learning_stats -> ActiveLearningService.get_queue_stats

Feinpoliert und durchdacht - Enterprise Dashboard-Builder.
"""

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.safe_errors import safe_error_log
from app.db.models_dashboard import DashboardBuilderWidget, DashboardConfig, WidgetTypeEnum

logger = structlog.get_logger(__name__)


# =============================================================================
# Rollen-basierte Standard-Widget-Definitionen
# =============================================================================

# Aufbau: {widget_type, title, data_source, refresh_interval_seconds, config}
# Reihenfolge bestimmt die initiale Anordnung im Grid.

_DEFAULT_WIDGETS_BY_ROLE: Dict[str, List[Dict]] = {
    "buchhaltung": [
        {
            "widget_type": WidgetTypeEnum.INVOICE_STATUS.value,
            "title": "Rechnungsstatus",
            "data_source": "invoice_tracking",
            "refresh_interval_seconds": 120,
            "config": {"show_overdue": True, "show_open": True},
        },
        {
            "widget_type": WidgetTypeEnum.CASHFLOW_CHART.value,
            "title": "Cashflow-Uebersicht",
            "data_source": "cashflow_predictor",
            "refresh_interval_seconds": 300,
            "config": {"period_days": 30},
        },
        {
            "widget_type": WidgetTypeEnum.OPEN_TASKS.value,
            "title": "Offene Aufgaben",
            "data_source": "approval_service",
            "refresh_interval_seconds": 60,
            "config": {"show_overdue": True},
        },
    ],
    "management": [
        {
            "widget_type": WidgetTypeEnum.KPI_CARDS.value,
            "title": "KPI-Uebersicht",
            "data_source": "smart_dashboard_kpis",
            "refresh_interval_seconds": 120,
            "config": {"kpi_keys": ["open_invoices_total", "cashflow_current", "active_alerts"]},
        },
        {
            "widget_type": WidgetTypeEnum.CASHFLOW_CHART.value,
            "title": "Cashflow-Prognose",
            "data_source": "cashflow_predictor",
            "refresh_interval_seconds": 300,
            "config": {"period_days": 90, "show_forecast": True},
        },
        {
            "widget_type": WidgetTypeEnum.ANOMALY_SUMMARY.value,
            "title": "Anomalie-Uebersicht",
            "data_source": "anomaly_detection",
            "refresh_interval_seconds": 180,
            "config": {"severity_filter": ["critical", "warning"]},
        },
    ],
    "sachbearbeitung": [
        {
            "widget_type": WidgetTypeEnum.OCR_QUEUE.value,
            "title": "OCR-Warteschlange",
            "data_source": "processing_jobs",
            "refresh_interval_seconds": 30,
            "config": {},
        },
        {
            "widget_type": WidgetTypeEnum.RECENT_DOCUMENTS.value,
            "title": "Zuletzt verarbeitet",
            "data_source": "recent_documents",
            "refresh_interval_seconds": 60,
            "config": {"limit": 10},
        },
        {
            "widget_type": WidgetTypeEnum.ACTIVE_LEARNING_STATS.value,
            "title": "Active-Learning-Status",
            "data_source": "active_learning",
            "refresh_interval_seconds": 300,
            "config": {},
        },
    ],
    "admin": [
        {
            "widget_type": WidgetTypeEnum.INTEGRATION_HEALTH.value,
            "title": "Integrations-Gesundheit",
            "data_source": "system_health",
            "refresh_interval_seconds": 60,
            "config": {},
        },
        {
            "widget_type": WidgetTypeEnum.OCR_QUEUE.value,
            "title": "OCR-Warteschlange",
            "data_source": "processing_jobs",
            "refresh_interval_seconds": 30,
            "config": {},
        },
        {
            "widget_type": WidgetTypeEnum.KPI_CARDS.value,
            "title": "System-KPIs",
            "data_source": "smart_dashboard_kpis",
            "refresh_interval_seconds": 120,
            "config": {},
        },
    ],
}

# Standard-Rollenname fuer unbekannte Rollen
_FALLBACK_ROLE = "sachbearbeitung"


# =============================================================================
# Dashboard-Builder Service
# =============================================================================


class DashboardBuilderService:
    """
    Service fuer den Dashboard-Builder.

    Koordiniert CRUD-Operationen fuer benutzerdefinierte Dashboards
    und delegiert Live-Datenabfragen an die jeweiligen Fach-Services.
    """

    # =========================================================================
    # Dashboard-Abfragen
    # =========================================================================

    async def get_dashboards(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
    ) -> List[Dict]:
        """
        Gibt alle sichtbaren Dashboards des Benutzers zurueck.

        Enthalten sind:
        - Eigene Dashboards des Benutzers
        - Firmenweit geteilte Dashboards anderer Benutzer

        Args:
            db:         Async Datenbank-Session.
            company_id: Aktive Mandanten-ID.
            user_id:    Aktueller Benutzer.

        Returns:
            Liste von Dashboard-Dicts (ohne Widget-Details fuer Listenansicht).
        """
        logger.info(
            "dashboard_builder.get_dashboards",
            company_id=str(company_id),
            user_id=str(user_id),
        )

        stmt = (
            select(DashboardConfig)
            .where(
                and_(
                    DashboardConfig.company_id == company_id,
                    or_(
                        DashboardConfig.user_id == user_id,
                        DashboardConfig.is_shared.is_(True),
                    ),
                )
            )
            .order_by(
                DashboardConfig.is_default.desc(),
                DashboardConfig.updated_at.desc(),
            )
        )

        result = await db.execute(stmt)
        configs = result.scalars().all()

        return [
            {
                "id": str(c.id),
                "company_id": str(c.company_id),
                "user_id": str(c.user_id),
                "name": c.name,
                "description": c.description,
                "is_default": c.is_default,
                "is_shared": c.is_shared,
                "is_owner": c.user_id == user_id,
                "layout": c.layout or [],
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in configs
        ]

    async def get_dashboard(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        company_id: UUID,
    ) -> Optional[Dict]:
        """
        Holt ein einzelnes Dashboard mit allen Widget-Details.

        Gibt None zurueck, wenn das Dashboard nicht existiert oder
        nicht zum angegebenen Mandanten gehoert.

        Args:
            db:           Async Datenbank-Session.
            dashboard_id: ID des Dashboards.
            company_id:   Mandanten-ID fuer Zugriffsvalidierung.

        Returns:
            Dashboard-Dict mit 'widgets'-Liste oder None.
        """
        logger.info(
            "dashboard_builder.get_dashboard",
            dashboard_id=str(dashboard_id),
            company_id=str(company_id),
        )

        stmt = (
            select(DashboardConfig)
            .options(selectinload(DashboardConfig.widgets))
            .where(
                and_(
                    DashboardConfig.id == dashboard_id,
                    DashboardConfig.company_id == company_id,
                )
            )
        )

        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            return None

        return config.to_dict()

    # =========================================================================
    # Dashboard-Verwaltung (CRUD)
    # =========================================================================

    async def create_dashboard(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        name: str,
        layout: Optional[List[Dict]] = None,
        description: Optional[str] = None,
        is_shared: bool = False,
    ) -> Dict:
        """
        Erstellt ein neues Dashboard fuer den Benutzer.

        Wird dieses als erstes Dashboard des Benutzers erstellt,
        wird es automatisch als Standard-Dashboard markiert.

        Args:
            db:          Async Datenbank-Session.
            company_id:  Aktive Mandanten-ID.
            user_id:     Eigentuemer.
            name:        Anzeigename (max. 255 Zeichen).
            layout:      Initiales Grid-Layout (Standard: leere Liste).
            description: Optionale Beschreibung.
            is_shared:   Firmenweit freigeben.

        Returns:
            Neu erstelltes Dashboard als Dict.
        """
        logger.info(
            "dashboard_builder.create_dashboard",
            company_id=str(company_id),
            user_id=str(user_id),
            name=name,
        )

        # Pruefen, ob Benutzer bereits ein Dashboard hat (fuer is_default)
        existing_stmt = select(DashboardConfig.id).where(
            and_(
                DashboardConfig.company_id == company_id,
                DashboardConfig.user_id == user_id,
            )
        ).limit(1)
        existing_result = await db.execute(existing_stmt)
        has_existing = existing_result.scalar_one_or_none() is not None

        config = DashboardConfig(
            company_id=company_id,
            user_id=user_id,
            name=name,
            description=description,
            layout=layout or [],
            is_default=(not has_existing),
            is_shared=is_shared,
        )
        db.add(config)
        await db.flush()
        await db.refresh(config)

        return {
            "id": str(config.id),
            "company_id": str(config.company_id),
            "user_id": str(config.user_id),
            "name": config.name,
            "description": config.description,
            "layout": config.layout or [],
            "is_default": config.is_default,
            "is_shared": config.is_shared,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    async def update_dashboard(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        company_id: UUID,
        user_id: UUID,
        layout: Optional[List[Dict]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Aktualisiert Layout und Metadaten eines Dashboards.

        Nur der Eigentuemer kann sein Dashboard bearbeiten.

        Args:
            db:           Async Datenbank-Session.
            dashboard_id: ID des Dashboards.
            company_id:   Mandanten-ID fuer Zugriffsvalidierung.
            user_id:      Muss dem Eigentuemer entsprechen.
            layout:       Neues Grid-Layout (None = unveraendert).
            name:         Neuer Name (None = unveraendert).
            description:  Neue Beschreibung (None = unveraendert).

        Returns:
            Aktualisiertes Dashboard-Dict oder None (nicht gefunden / kein Zugriff).
        """
        logger.info(
            "dashboard_builder.update_dashboard",
            dashboard_id=str(dashboard_id),
            company_id=str(company_id),
            user_id=str(user_id),
        )

        stmt = (
            select(DashboardConfig)
            .where(
                and_(
                    DashboardConfig.id == dashboard_id,
                    DashboardConfig.company_id == company_id,
                    DashboardConfig.user_id == user_id,
                )
            )
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            return None

        if layout is not None:
            config.layout = layout
        if name is not None:
            config.name = name
        if description is not None:
            config.description = description

        await db.flush()
        await db.refresh(config)

        return {
            "id": str(config.id),
            "company_id": str(config.company_id),
            "user_id": str(config.user_id),
            "name": config.name,
            "description": config.description,
            "layout": config.layout or [],
            "is_default": config.is_default,
            "is_shared": config.is_shared,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    async def delete_dashboard(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Loescht ein Dashboard, wenn der Benutzer Eigentuemer ist.

        Standard-Dashboards (is_default=True) koennen NICHT geloescht werden,
        um zu verhindern, dass Benutzer ohne Dashboard zurueckbleiben.

        Args:
            db:           Async Datenbank-Session.
            dashboard_id: ID des Dashboards.
            company_id:   Mandanten-ID.
            user_id:      Muss Eigentuemer sein.

        Returns:
            True bei Erfolg, False wenn nicht gefunden / kein Zugriff / Default.

        Raises:
            ValueError: Wenn versucht wird, das Standard-Dashboard zu loeschen.
        """
        logger.info(
            "dashboard_builder.delete_dashboard",
            dashboard_id=str(dashboard_id),
            company_id=str(company_id),
            user_id=str(user_id),
        )

        stmt = (
            select(DashboardConfig)
            .where(
                and_(
                    DashboardConfig.id == dashboard_id,
                    DashboardConfig.company_id == company_id,
                    DashboardConfig.user_id == user_id,
                )
            )
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            return False

        if config.is_default:
            raise ValueError(
                "Das Standard-Dashboard kann nicht geloescht werden. "
                "Bitte waehlen Sie zuerst ein anderes Dashboard als Standard."
            )

        await db.delete(config)
        await db.flush()
        return True

    # =========================================================================
    # Widget-Verwaltung
    # =========================================================================

    async def add_widget(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        company_id: UUID,
        widget_type: str,
        title: str,
        config: Optional[Dict] = None,
        data_source: Optional[str] = None,
        refresh_interval_seconds: int = 300,
    ) -> Optional[Dict]:
        """
        Fuegt ein Widget zum Dashboard hinzu.

        Die data_source wird automatisch aus dem widget_type abgeleitet,
        wenn nicht explizit angegeben.

        Args:
            db:                       Async Datenbank-Session.
            dashboard_id:             Ziel-Dashboard (muss company_id gehoeren).
            company_id:               Mandanten-ID fuer Zugriffsvalidierung.
            widget_type:              Typ (aus WidgetTypeEnum).
            title:                    Anzeigename.
            config:                   Widget-spezifische Einstellungen.
            data_source:              Optionale explizite Datenquelle.
            refresh_interval_seconds: Aktualisierungsintervall (min. 30 s).

        Returns:
            Neu erstelltes Widget als Dict oder None (Dashboard nicht gefunden).

        Raises:
            ValueError: Bei ungueltigem widget_type oder refresh_interval.
        """
        # Widget-Typ validieren
        valid_types = {wt.value for wt in WidgetTypeEnum}
        if widget_type not in valid_types:
            raise ValueError(
                f"Ungueltiger Widget-Typ: {widget_type!r}. "
                f"Erlaubt: {sorted(valid_types)}"
            )

        if refresh_interval_seconds < 30:
            raise ValueError(
                f"Aktualisierungsintervall muss mindestens 30 Sekunden betragen, "
                f"erhalten: {refresh_interval_seconds}"
            )

        logger.info(
            "dashboard_builder.add_widget",
            dashboard_id=str(dashboard_id),
            company_id=str(company_id),
            widget_type=widget_type,
        )

        # Dashboard-Existenz und Mandanten-Zugehoerigkeit pruefen
        dash_stmt = select(DashboardConfig.id).where(
            and_(
                DashboardConfig.id == dashboard_id,
                DashboardConfig.company_id == company_id,
            )
        )
        dash_result = await db.execute(dash_stmt)
        if not dash_result.scalar_one_or_none():
            return None

        # data_source aus Widget-Typ ableiten, wenn nicht angegeben
        resolved_data_source = data_source or _DATA_SOURCE_BY_WIDGET_TYPE.get(
            widget_type, widget_type
        )

        widget = DashboardBuilderWidget(
            dashboard_id=dashboard_id,
            widget_type=widget_type,
            title=title,
            config=config or {},
            data_source=resolved_data_source,
            refresh_interval_seconds=refresh_interval_seconds,
        )
        db.add(widget)
        await db.flush()
        await db.refresh(widget)

        return widget.to_dict()

    async def remove_widget(
        self,
        db: AsyncSession,
        widget_id: UUID,
        dashboard_id: UUID,
        company_id: UUID,
    ) -> bool:
        """
        Entfernt ein Widget vom Dashboard.

        Args:
            db:           Async Datenbank-Session.
            widget_id:    ID des Widgets.
            dashboard_id: Dashboard-ID (verhindert Cross-Dashboard-Zugriff).
            company_id:   Mandanten-ID fuer Zugriffsvalidierung.

        Returns:
            True bei Erfolg, False wenn nicht gefunden.
        """
        logger.info(
            "dashboard_builder.remove_widget",
            widget_id=str(widget_id),
            dashboard_id=str(dashboard_id),
            company_id=str(company_id),
        )

        # Widget mit Dashboard-Join fuer Mandanten-Sicherheit
        stmt = (
            select(DashboardBuilderWidget)
            .join(
                DashboardConfig,
                DashboardBuilderWidget.dashboard_id == DashboardConfig.id,
            )
            .where(
                and_(
                    DashboardBuilderWidget.id == widget_id,
                    DashboardBuilderWidget.dashboard_id == dashboard_id,
                    DashboardConfig.company_id == company_id,
                )
            )
        )
        result = await db.execute(stmt)
        widget = result.scalar_one_or_none()

        if not widget:
            return False

        await db.delete(widget)
        await db.flush()
        return True

    # =========================================================================
    # Live-Widget-Daten
    # =========================================================================

    async def get_widget_data(
        self,
        db: AsyncSession,
        widget_type: str,
        company_id: UUID,
    ) -> Dict:
        """
        Holt Live-Daten fuer einen Widget-Typ.

        Delegiert an den jeweils zustaendigen Fach-Service:
          invoice_status, cashflow_chart -> SmartDashboardService.get_finance_tab
          ocr_queue, recent_documents    -> SmartDashboardService.get_documents_tab
          kpi_cards                      -> SmartDashboardService.get_realtime_kpis
          anomaly_summary                -> AnomalyDetectionService
          open_tasks                     -> SmartDashboardService.get_workflows_tab
          integration_health             -> SmartDashboardService.get_system_tab
          active_learning_stats          -> ActiveLearningService.get_queue_stats

        Args:
            db:          Async Datenbank-Session.
            widget_type: Widget-Typ (aus WidgetTypeEnum).
            company_id:  Mandanten-ID.

        Returns:
            Dict mit widget_type und data-Schluessel.

        Raises:
            ValueError: Bei ungueltigem widget_type.
        """
        valid_types = {wt.value for wt in WidgetTypeEnum}
        if widget_type not in valid_types:
            raise ValueError(
                f"Ungueltiger Widget-Typ: {widget_type!r}. "
                f"Erlaubt: {sorted(valid_types)}"
            )

        logger.info(
            "dashboard_builder.get_widget_data",
            widget_type=widget_type,
            company_id=str(company_id),
        )

        try:
            data = await self._fetch_widget_data(db, widget_type, company_id)
            return {"widget_type": widget_type, "data": data}
        except Exception as exc:
            logger.warning(
                "dashboard_builder.get_widget_data.service_error",
                widget_type=widget_type,
                company_id=str(company_id),
                **safe_error_log(exc),
            )
            # Graceful Degradation: leere Daten statt Fehler
            return {
                "widget_type": widget_type,
                "data": {},
                "error": "Daten konnten nicht geladen werden",
            }

    async def _fetch_widget_data(
        self,
        db: AsyncSession,
        widget_type: str,
        company_id: UUID,
    ) -> Dict:
        """
        Interne Routing-Logik fuer Widget-Daten.

        Importiert Services lazy, um zirkulaere Abhaengigkeiten zu vermeiden.

        Args:
            db:          Async Datenbank-Session.
            widget_type: Widget-Typ-String.
            company_id:  Mandanten-ID.

        Returns:
            Service-spezifisches Daten-Dict.
        """
        if widget_type in (
            WidgetTypeEnum.INVOICE_STATUS.value,
            WidgetTypeEnum.CASHFLOW_CHART.value,
        ):
            # Finanz-Tab des Smart-Dashboard-Services
            from app.services.smart_dashboard_service import SmartDashboardService
            svc = SmartDashboardService()
            return await svc.get_finance_tab(db, company_id)

        if widget_type in (
            WidgetTypeEnum.OCR_QUEUE.value,
            WidgetTypeEnum.RECENT_DOCUMENTS.value,
        ):
            # Dokument-Tab des Smart-Dashboard-Services
            from app.services.smart_dashboard_service import SmartDashboardService
            svc = SmartDashboardService()
            return await svc.get_documents_tab(db, company_id)

        if widget_type == WidgetTypeEnum.KPI_CARDS.value:
            # Echtzeit-KPIs
            from app.services.smart_dashboard_service import SmartDashboardService
            svc = SmartDashboardService()
            return {"kpis": await svc.get_realtime_kpis(db, company_id)}

        if widget_type == WidgetTypeEnum.ANOMALY_SUMMARY.value:
            # Anomalie-Zusammenfassung
            return await self._fetch_anomaly_summary(db, company_id)

        if widget_type == WidgetTypeEnum.OPEN_TASKS.value:
            # Workflow-Tab des Smart-Dashboard-Services
            from app.services.smart_dashboard_service import SmartDashboardService
            svc = SmartDashboardService()
            return await svc.get_workflows_tab(db, company_id)

        if widget_type == WidgetTypeEnum.INTEGRATION_HEALTH.value:
            # System-Tab des Smart-Dashboard-Services
            from app.services.smart_dashboard_service import SmartDashboardService
            svc = SmartDashboardService()
            return await svc.get_system_tab(db, company_id)

        if widget_type == WidgetTypeEnum.ACTIVE_LEARNING_STATS.value:
            # Active-Learning-Statistiken
            return await self._fetch_active_learning_stats(db, company_id)

        # Sollte durch Validierung oben nie erreicht werden
        return {}

    async def _fetch_anomaly_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict:
        """
        Holt aggregierte Anomalie-Statistiken.

        Args:
            db:         Async Datenbank-Session.
            company_id: Mandanten-ID.

        Returns:
            Dict mit Gesamtanzahl, offenen und nach Schweregrad gruppierten Anomalien.
        """
        from sqlalchemy import func as sa_func
        from app.db.models_anomaly import Anomaly, AnomalyStatus

        stmt_total = select(sa_func.count(Anomaly.id)).where(
            Anomaly.company_id == company_id
        )
        stmt_open = select(sa_func.count(Anomaly.id)).where(
            and_(
                Anomaly.company_id == company_id,
                Anomaly.status == AnomalyStatus.OPEN.value,
            )
        )

        total_result = await db.execute(stmt_total)
        open_result = await db.execute(stmt_open)

        return {
            "total": total_result.scalar() or 0,
            "open": open_result.scalar() or 0,
        }

    async def _fetch_active_learning_stats(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict:
        """
        Holt Active-Learning Queue-Statistiken.

        Args:
            db:         Async Datenbank-Session.
            company_id: Mandanten-ID.

        Returns:
            Dict mit Queue-Statistiken aus dem ActiveLearningService.
        """
        from app.services.active_learning.active_learning_service import ActiveLearningService

        svc = ActiveLearningService()
        stats = await svc.get_queue_stats(db, company_id)
        return stats if isinstance(stats, dict) else {}

    # =========================================================================
    # Dashboard teilen
    # =========================================================================

    async def share_dashboard(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[Dict]:
        """
        Schaltet das Teilen eines Dashboards um (Toggle).

        Nur der Eigentuemer kann is_shared aendern.

        Args:
            db:           Async Datenbank-Session.
            dashboard_id: ID des Dashboards.
            company_id:   Mandanten-ID.
            user_id:      Muss Eigentuemer sein.

        Returns:
            Aktualisiertes Dashboard-Dict (nur Metadaten, ohne Widgets)
            oder None (nicht gefunden / kein Zugriff).
        """
        logger.info(
            "dashboard_builder.share_dashboard",
            dashboard_id=str(dashboard_id),
            company_id=str(company_id),
            user_id=str(user_id),
        )

        stmt = (
            select(DashboardConfig)
            .where(
                and_(
                    DashboardConfig.id == dashboard_id,
                    DashboardConfig.company_id == company_id,
                    DashboardConfig.user_id == user_id,
                )
            )
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            return None

        config.is_shared = not config.is_shared

        logger.info(
            "dashboard_builder.share_dashboard.toggled",
            dashboard_id=str(dashboard_id),
            is_shared=config.is_shared,
        )

        await db.flush()
        await db.refresh(config)

        return {
            "id": str(config.id),
            "name": config.name,
            "is_shared": config.is_shared,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    # =========================================================================
    # Rollen-basiertes Standard-Dashboard
    # =========================================================================

    async def get_default_dashboard_for_role(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        role: str,
    ) -> Dict:
        """
        Gibt das Standard-Dashboard fuer eine Benutzerrolle zurueck.

        Prueft zuerst, ob der Benutzer bereits ein Standard-Dashboard hat.
        Falls nicht, wird ein neues Rollen-basiertes Dashboard erstellt
        und mit den Standard-Widgets befuellt.

        Rollen-Mapping:
          buchhaltung     -> invoice_status, cashflow_chart, open_tasks
          management      -> kpi_cards, cashflow_chart, anomaly_summary
          sachbearbeitung -> ocr_queue, recent_documents, active_learning_stats
          admin           -> integration_health, ocr_queue, kpi_cards

        Unbekannte Rollen erhalten das 'sachbearbeitung'-Layout.

        Args:
            db:         Async Datenbank-Session.
            company_id: Aktive Mandanten-ID.
            user_id:    Aktueller Benutzer.
            role:       Rollenname (z. B. 'admin', 'buchhaltung').

        Returns:
            Vollstaendiges Dashboard-Dict inkl. Widgets.
        """
        logger.info(
            "dashboard_builder.get_default_dashboard_for_role",
            company_id=str(company_id),
            user_id=str(user_id),
            role=role,
        )

        # Vorhandenes Standard-Dashboard des Benutzers suchen
        existing_stmt = (
            select(DashboardConfig)
            .options(selectinload(DashboardConfig.widgets))
            .where(
                and_(
                    DashboardConfig.company_id == company_id,
                    DashboardConfig.user_id == user_id,
                    DashboardConfig.is_default.is_(True),
                )
            )
        )
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            logger.info(
                "dashboard_builder.get_default_dashboard_for_role.found_existing",
                dashboard_id=str(existing.id),
            )
            return existing.to_dict()

        # Rollen-Mapping aufloesen (Fallback auf 'sachbearbeitung')
        normalized_role = role.lower().strip()
        widget_defs = _DEFAULT_WIDGETS_BY_ROLE.get(
            normalized_role,
            _DEFAULT_WIDGETS_BY_ROLE[_FALLBACK_ROLE],
        )

        # Rollen-lesbaren Namen erzeugen
        role_label = _ROLE_DISPLAY_NAMES.get(normalized_role, normalized_role.capitalize())
        dashboard_name = f"Mein Dashboard ({role_label})"

        # Standard-Dashboard anlegen
        new_config = DashboardConfig(
            company_id=company_id,
            user_id=user_id,
            name=dashboard_name,
            description=f"Automatisch erstelltes Standard-Dashboard fuer die Rolle '{role_label}'",
            layout=[],
            is_default=True,
            is_shared=False,
        )
        db.add(new_config)
        await db.flush()

        # Standard-Widgets anlegen und Layout berechnen
        layout_items: List[Dict] = []
        widgets_per_row = 2
        widget_w = 6   # Breite in 12-Spalten-Grid
        widget_h = 4   # Standardhoehe

        for idx, wdef in enumerate(widget_defs):
            widget = DashboardBuilderWidget(
                dashboard_id=new_config.id,
                widget_type=wdef["widget_type"],
                title=wdef["title"],
                config=wdef.get("config", {}),
                data_source=wdef["data_source"],
                refresh_interval_seconds=wdef.get("refresh_interval_seconds", 300),
            )
            db.add(widget)
            await db.flush()
            await db.refresh(widget)

            # Grid-Position berechnen
            col = idx % widgets_per_row
            row = idx // widgets_per_row
            layout_items.append({
                "widget_id": str(widget.id),
                "x": col * widget_w,
                "y": row * widget_h,
                "w": widget_w,
                "h": widget_h,
            })

        # Layout im Dashboard speichern
        new_config.layout = layout_items
        await db.flush()
        await db.refresh(new_config)

        logger.info(
            "dashboard_builder.get_default_dashboard_for_role.created",
            dashboard_id=str(new_config.id),
            role=role,
            widget_count=len(widget_defs),
        )

        # Vollstaendiges Dashboard mit Widgets laden
        full_stmt = (
            select(DashboardConfig)
            .options(selectinload(DashboardConfig.widgets))
            .where(DashboardConfig.id == new_config.id)
        )
        full_result = await db.execute(full_stmt)
        full_config = full_result.scalar_one()

        return full_config.to_dict()


# =============================================================================
# Konstanten (interne Verwendung)
# =============================================================================

# Standard-Datenquelle je Widget-Typ (wird genutzt, wenn data_source nicht
# explizit uebergeben wird)
_DATA_SOURCE_BY_WIDGET_TYPE: Dict[str, str] = {
    WidgetTypeEnum.INVOICE_STATUS.value: "invoice_tracking",
    WidgetTypeEnum.CASHFLOW_CHART.value: "cashflow_predictor",
    WidgetTypeEnum.OCR_QUEUE.value: "processing_jobs",
    WidgetTypeEnum.KPI_CARDS.value: "smart_dashboard_kpis",
    WidgetTypeEnum.ANOMALY_SUMMARY.value: "anomaly_detection",
    WidgetTypeEnum.RECENT_DOCUMENTS.value: "recent_documents",
    WidgetTypeEnum.OPEN_TASKS.value: "approval_service",
    WidgetTypeEnum.INTEGRATION_HEALTH.value: "system_health",
    WidgetTypeEnum.ACTIVE_LEARNING_STATS.value: "active_learning",
}

# Menschenlesbare Anzeigenamen fuer Rollen
_ROLE_DISPLAY_NAMES: Dict[str, str] = {
    "buchhaltung": "Buchhaltung",
    "management": "Management",
    "sachbearbeitung": "Sachbearbeitung",
    "admin": "Administrator",
    "owner": "Inhaber",
    "viewer": "Betrachter",
    "member": "Mitglied",
}
