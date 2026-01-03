# -*- coding: utf-8 -*-
"""
Report Template Service.

CRUD-Operationen fuer Report-Templates, Columns, Filters und Charts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, or_, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ReportTemplate,
    ReportColumn,
    ReportFilter,
    ReportChart,
    ReportShare,
    ReportExecution,
    User,
)

logger = structlog.get_logger(__name__)


class ReportTemplateService:
    """Service fuer Report-Template CRUD-Operationen."""

    _instance: Optional["ReportTemplateService"] = None

    def __new__(cls) -> "ReportTemplateService":
        """Singleton-Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # =========================================================================
    # TEMPLATE CRUD
    # =========================================================================

    async def create_template(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        name: str,
        report_type: str,
        data_source: str,
        company_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        default_format: str = "excel",
        is_public: bool = False,
        layout_config: Optional[Dict[str, Any]] = None,
        sort_config: Optional[List[Dict[str, Any]]] = None,
        group_by_config: Optional[List[str]] = None,
    ) -> ReportTemplate:
        """Erstellt ein neues Report-Template."""
        template = ReportTemplate(
            id=uuid.uuid4(),
            user_id=user_id,
            company_id=company_id,
            name=name,
            description=description,
            report_type=report_type,
            data_source=data_source,
            default_format=default_format,
            is_public=is_public,
            layout_config=layout_config,
            sort_config=sort_config,
            group_by_config=group_by_config,
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)

        logger.info(
            "report_template_created",
            template_id=str(template.id),
            name=name,
            report_type=report_type,
            user_id=str(user_id),
        )

        return template

    async def get_template(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        include_relations: bool = True,
    ) -> Optional[ReportTemplate]:
        """Holt ein Template mit optionalen Relationen."""
        query = select(ReportTemplate).where(ReportTemplate.id == template_id)

        if include_relations:
            query = query.options(
                selectinload(ReportTemplate.columns),
                selectinload(ReportTemplate.filters),
                selectinload(ReportTemplate.charts),
            )

        result = await db.execute(query)
        template = result.scalar_one_or_none()

        if template and user_id:
            # Pruefe Zugriffsberechtigung
            if not await self._can_access_template(db, template, user_id):
                return None

        return template

    async def list_templates(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
        report_type: Optional[str] = None,
        include_public: bool = True,
        include_shared: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ReportTemplate]:
        """Listet Templates fuer einen User."""
        # Basis: Eigene Templates
        conditions = [ReportTemplate.user_id == user_id]

        if include_public:
            # Oeffentliche Templates (von anderen Usern)
            conditions.append(ReportTemplate.is_public == True)

        query = select(ReportTemplate).where(or_(*conditions))

        if company_id:
            query = query.where(
                or_(
                    ReportTemplate.company_id == company_id,
                    ReportTemplate.company_id.is_(None),
                )
            )

        if report_type:
            query = query.where(ReportTemplate.report_type == report_type)

        query = query.order_by(ReportTemplate.updated_at.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        templates = list(result.scalars().all())

        # Shared Templates hinzufuegen
        if include_shared:
            shared_query = (
                select(ReportTemplate)
                .join(ReportShare, ReportShare.template_id == ReportTemplate.id)
                .where(ReportShare.shared_with_user_id == user_id)
                .where(ReportShare.can_view == True)
            )
            shared_result = await db.execute(shared_query)
            shared_templates = list(shared_result.scalars().all())

            # Deduplizieren
            existing_ids = {t.id for t in templates}
            for t in shared_templates:
                if t.id not in existing_ids:
                    templates.append(t)

        return templates

    async def update_template(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        **updates: Any,
    ) -> Optional[ReportTemplate]:
        """Aktualisiert ein Template."""
        template = await self.get_template(db, template_id, include_relations=False)

        if not template:
            return None

        # Pruefe Berechtigung
        if not await self._can_edit_template(db, template, user_id):
            logger.warning(
                "template_update_forbidden",
                template_id=str(template_id),
                user_id=str(user_id),
            )
            return None

        # Erlaubte Felder
        allowed_fields = {
            "name", "description", "report_type", "data_source",
            "default_format", "is_public", "is_scheduled", "schedule_config",
            "layout_config", "sort_config", "group_by_config",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(template, field, value)

        template.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(template)

        logger.info(
            "report_template_updated",
            template_id=str(template_id),
            updated_fields=list(updates.keys()),
        )

        return template

    async def delete_template(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Loescht ein Template."""
        template = await self.get_template(db, template_id, include_relations=False)

        if not template:
            return False

        # Nur Owner oder mit can_delete Berechtigung
        if template.user_id != user_id:
            share = await self._get_share(db, template_id, user_id)
            if not share or not share.can_delete:
                logger.warning(
                    "template_delete_forbidden",
                    template_id=str(template_id),
                    user_id=str(user_id),
                )
                return False

        await db.delete(template)
        await db.commit()

        logger.info(
            "report_template_deleted",
            template_id=str(template_id),
            deleted_by=str(user_id),
        )

        return True

    async def clone_template(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        new_name: Optional[str] = None,
    ) -> Optional[ReportTemplate]:
        """Klont ein Template."""
        original = await self.get_template(db, template_id, user_id, include_relations=True)

        if not original:
            return None

        # Neues Template erstellen
        new_template = await self.create_template(
            db=db,
            user_id=user_id,
            name=new_name or f"{original.name} (Kopie)",
            report_type=original.report_type,
            data_source=original.data_source,
            company_id=original.company_id,
            description=original.description,
            default_format=original.default_format,
            is_public=False,
            layout_config=original.layout_config,
            sort_config=original.sort_config,
            group_by_config=original.group_by_config,
        )

        # Columns kopieren
        for col in original.columns:
            await self.add_column(
                db=db,
                template_id=new_template.id,
                field_path=col.field_path,
                display_name=col.display_name,
                data_type=col.data_type,
                format_pattern=col.format_pattern,
                width=col.width,
                sort_order=col.sort_order,
                is_visible=col.is_visible,
                aggregation=col.aggregation,
                conditional_format=col.conditional_format,
            )

        # Filters kopieren
        for f in original.filters:
            await self.add_filter(
                db=db,
                template_id=new_template.id,
                field_path=f.field_path,
                operator=f.operator,
                value=f.value,
                logic_operator=f.logic_operator,
                group_id=f.group_id,
                sort_order=f.sort_order,
                is_dynamic=f.is_dynamic,
                dynamic_source=f.dynamic_source,
            )

        # Charts kopieren
        for chart in original.charts:
            await self.add_chart(
                db=db,
                template_id=new_template.id,
                chart_type=chart.chart_type,
                title=chart.title,
                x_axis_field=chart.x_axis_field,
                y_axis_fields=chart.y_axis_fields,
                group_by_field=chart.group_by_field,
                colors=chart.colors,
                show_legend=chart.show_legend,
                show_labels=chart.show_labels,
                position=chart.position,
                width_percent=chart.width_percent,
                height_px=chart.height_px,
                sort_order=chart.sort_order,
            )

        logger.info(
            "report_template_cloned",
            original_id=str(template_id),
            new_id=str(new_template.id),
            user_id=str(user_id),
        )

        return new_template

    # =========================================================================
    # COLUMN CRUD
    # =========================================================================

    async def add_column(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        field_path: str,
        display_name: str,
        data_type: str,
        format_pattern: Optional[str] = None,
        width: Optional[int] = None,
        sort_order: int = 0,
        is_visible: bool = True,
        aggregation: Optional[str] = None,
        conditional_format: Optional[List[Dict[str, Any]]] = None,
    ) -> ReportColumn:
        """Fuegt eine Spalte zu einem Template hinzu."""
        column = ReportColumn(
            id=uuid.uuid4(),
            template_id=template_id,
            field_path=field_path,
            display_name=display_name,
            data_type=data_type,
            format_pattern=format_pattern,
            width=width,
            sort_order=sort_order,
            is_visible=is_visible,
            aggregation=aggregation,
            conditional_format=conditional_format,
        )
        db.add(column)
        await db.commit()
        await db.refresh(column)
        return column

    async def update_column(
        self,
        db: AsyncSession,
        column_id: uuid.UUID,
        **updates: Any,
    ) -> Optional[ReportColumn]:
        """Aktualisiert eine Spalte."""
        result = await db.execute(
            select(ReportColumn).where(ReportColumn.id == column_id)
        )
        column = result.scalar_one_or_none()

        if not column:
            return None

        allowed_fields = {
            "field_path", "display_name", "data_type", "format_pattern",
            "width", "sort_order", "is_visible", "aggregation", "conditional_format",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(column, field, value)

        await db.commit()
        await db.refresh(column)
        return column

    async def delete_column(
        self,
        db: AsyncSession,
        column_id: uuid.UUID,
    ) -> bool:
        """Loescht eine Spalte."""
        result = await db.execute(
            delete(ReportColumn).where(ReportColumn.id == column_id)
        )
        await db.commit()
        return result.rowcount > 0

    async def reorder_columns(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        column_orders: List[Dict[str, Any]],
    ) -> bool:
        """Sortiert Spalten neu."""
        for order_info in column_orders:
            await db.execute(
                update(ReportColumn)
                .where(ReportColumn.id == order_info["id"])
                .where(ReportColumn.template_id == template_id)
                .values(sort_order=order_info["sort_order"])
            )
        await db.commit()
        return True

    # =========================================================================
    # FILTER CRUD
    # =========================================================================

    async def add_filter(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        field_path: str,
        operator: str,
        value: Optional[Any] = None,
        logic_operator: str = "AND",
        group_id: Optional[int] = None,
        sort_order: int = 0,
        is_dynamic: bool = False,
        dynamic_source: Optional[str] = None,
    ) -> ReportFilter:
        """Fuegt einen Filter zu einem Template hinzu."""
        filter_obj = ReportFilter(
            id=uuid.uuid4(),
            template_id=template_id,
            field_path=field_path,
            operator=operator,
            value=value,
            logic_operator=logic_operator,
            group_id=group_id,
            sort_order=sort_order,
            is_dynamic=is_dynamic,
            dynamic_source=dynamic_source,
        )
        db.add(filter_obj)
        await db.commit()
        await db.refresh(filter_obj)
        return filter_obj

    async def update_filter(
        self,
        db: AsyncSession,
        filter_id: uuid.UUID,
        **updates: Any,
    ) -> Optional[ReportFilter]:
        """Aktualisiert einen Filter."""
        result = await db.execute(
            select(ReportFilter).where(ReportFilter.id == filter_id)
        )
        filter_obj = result.scalar_one_or_none()

        if not filter_obj:
            return None

        allowed_fields = {
            "field_path", "operator", "value", "logic_operator",
            "group_id", "sort_order", "is_dynamic", "dynamic_source",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(filter_obj, field, value)

        await db.commit()
        await db.refresh(filter_obj)
        return filter_obj

    async def delete_filter(
        self,
        db: AsyncSession,
        filter_id: uuid.UUID,
    ) -> bool:
        """Loescht einen Filter."""
        result = await db.execute(
            delete(ReportFilter).where(ReportFilter.id == filter_id)
        )
        await db.commit()
        return result.rowcount > 0

    # =========================================================================
    # CHART CRUD
    # =========================================================================

    async def add_chart(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        chart_type: str,
        y_axis_fields: List[str],
        title: Optional[str] = None,
        x_axis_field: Optional[str] = None,
        group_by_field: Optional[str] = None,
        colors: Optional[List[str]] = None,
        show_legend: bool = True,
        show_labels: bool = False,
        position: str = "bottom",
        width_percent: int = 100,
        height_px: int = 300,
        sort_order: int = 0,
    ) -> ReportChart:
        """Fuegt einen Chart zu einem Template hinzu."""
        chart = ReportChart(
            id=uuid.uuid4(),
            template_id=template_id,
            chart_type=chart_type,
            title=title,
            x_axis_field=x_axis_field,
            y_axis_fields=y_axis_fields,
            group_by_field=group_by_field,
            colors=colors,
            show_legend=show_legend,
            show_labels=show_labels,
            position=position,
            width_percent=width_percent,
            height_px=height_px,
            sort_order=sort_order,
        )
        db.add(chart)
        await db.commit()
        await db.refresh(chart)
        return chart

    async def update_chart(
        self,
        db: AsyncSession,
        chart_id: uuid.UUID,
        **updates: Any,
    ) -> Optional[ReportChart]:
        """Aktualisiert einen Chart."""
        result = await db.execute(
            select(ReportChart).where(ReportChart.id == chart_id)
        )
        chart = result.scalar_one_or_none()

        if not chart:
            return None

        allowed_fields = {
            "chart_type", "title", "x_axis_field", "y_axis_fields",
            "group_by_field", "colors", "show_legend", "show_labels",
            "position", "width_percent", "height_px", "sort_order",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(chart, field, value)

        await db.commit()
        await db.refresh(chart)
        return chart

    async def delete_chart(
        self,
        db: AsyncSession,
        chart_id: uuid.UUID,
    ) -> bool:
        """Loescht einen Chart."""
        result = await db.execute(
            delete(ReportChart).where(ReportChart.id == chart_id)
        )
        await db.commit()
        return result.rowcount > 0

    # =========================================================================
    # SHARING
    # =========================================================================

    async def share_template(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        shared_by_id: uuid.UUID,
        shared_with_user_id: uuid.UUID,
        can_view: bool = True,
        can_execute: bool = True,
        can_edit: bool = False,
        can_delete: bool = False,
    ) -> Optional[ReportShare]:
        """Teilt ein Template mit einem anderen User."""
        # Pruefe ob Template existiert und User der Owner ist
        template = await self.get_template(db, template_id, include_relations=False)
        if not template or template.user_id != shared_by_id:
            return None

        # Pruefe ob bereits geteilt
        existing = await self._get_share(db, template_id, shared_with_user_id)
        if existing:
            # Update existing share
            existing.can_view = can_view
            existing.can_execute = can_execute
            existing.can_edit = can_edit
            existing.can_delete = can_delete
            await db.commit()
            await db.refresh(existing)
            return existing

        share = ReportShare(
            id=uuid.uuid4(),
            template_id=template_id,
            shared_with_user_id=shared_with_user_id,
            shared_by_id=shared_by_id,
            can_view=can_view,
            can_execute=can_execute,
            can_edit=can_edit,
            can_delete=can_delete,
        )
        db.add(share)
        await db.commit()
        await db.refresh(share)

        logger.info(
            "report_template_shared",
            template_id=str(template_id),
            shared_with=str(shared_with_user_id),
            shared_by=str(shared_by_id),
        )

        return share

    async def revoke_share(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        shared_with_user_id: uuid.UUID,
    ) -> bool:
        """Widerruft eine Freigabe."""
        template = await self.get_template(db, template_id, include_relations=False)
        if not template or template.user_id != user_id:
            return False

        result = await db.execute(
            delete(ReportShare)
            .where(ReportShare.template_id == template_id)
            .where(ReportShare.shared_with_user_id == shared_with_user_id)
        )
        await db.commit()

        if result.rowcount > 0:
            logger.info(
                "report_share_revoked",
                template_id=str(template_id),
                revoked_from=str(shared_with_user_id),
            )
            return True

        return False

    async def list_shared_with_me(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> List[ReportTemplate]:
        """Listet alle mit mir geteilten Templates."""
        query = (
            select(ReportTemplate)
            .join(ReportShare, ReportShare.template_id == ReportTemplate.id)
            .where(ReportShare.shared_with_user_id == user_id)
            .where(ReportShare.can_view == True)
            .order_by(ReportTemplate.name)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _can_access_template(
        self,
        db: AsyncSession,
        template: ReportTemplate,
        user_id: uuid.UUID,
    ) -> bool:
        """Prueft ob ein User auf ein Template zugreifen darf."""
        if template.user_id == user_id:
            return True
        if template.is_public:
            return True

        share = await self._get_share(db, template.id, user_id)
        return share is not None and share.can_view

    async def _can_edit_template(
        self,
        db: AsyncSession,
        template: ReportTemplate,
        user_id: uuid.UUID,
    ) -> bool:
        """Prueft ob ein User ein Template bearbeiten darf."""
        if template.user_id == user_id:
            return True

        share = await self._get_share(db, template.id, user_id)
        return share is not None and share.can_edit

    async def _get_share(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[ReportShare]:
        """Holt eine Freigabe."""
        result = await db.execute(
            select(ReportShare)
            .where(ReportShare.template_id == template_id)
            .where(ReportShare.shared_with_user_id == user_id)
        )
        return result.scalar_one_or_none()
