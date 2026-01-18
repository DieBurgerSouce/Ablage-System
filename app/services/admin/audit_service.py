"""Audit Log Service.

Provides audit log operations for the admin console:
- Search and filter audit logs
- View admin actions
- Export audit data
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import math
import csv
import io

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import AuditLog, AdminAction, User
from app.db.schemas import (
    AuditLogView,
    AuditLogFilters,
    AuditLogListResponse,
    AdminActionView,
    SortOrder,
)

logger = structlog.get_logger(__name__)


class AuditService:
    """Service for audit log operations."""

    @staticmethod
    async def list_audit_logs(
        db: AsyncSession,
        page: int = 1,
        per_page: int = 50,
        filters: Optional[AuditLogFilters] = None,
        sort_by: str = "created_at",
        sort_order: SortOrder = SortOrder.DESC,
    ) -> AuditLogListResponse:
        """List audit logs with filtering and pagination.

        Args:
            db: Database session
            page: Page number (1-based)
            per_page: Items per page
            filters: Optional filters
            sort_by: Field to sort by
            sort_order: Sort direction

        Returns:
            Paginated audit log list
        """
        query = select(AuditLog)

        # Apply filters
        if filters:
            conditions = []

            if filters.user_id:
                conditions.append(AuditLog.user_id == filters.user_id)
            if filters.action:
                conditions.append(AuditLog.action.ilike(f"%{filters.action}%"))
            if filters.resource_type:
                conditions.append(AuditLog.resource_type == filters.resource_type)
            if filters.resource_id:
                conditions.append(AuditLog.resource_id == filters.resource_id)
            if filters.ip_address:
                conditions.append(AuditLog.ip_address == filters.ip_address)
            if filters.date_from:
                conditions.append(AuditLog.created_at >= filters.date_from)
            if filters.date_to:
                conditions.append(AuditLog.created_at <= filters.date_to)
            if filters.success is not None:
                conditions.append(AuditLog.success == filters.success)

            if conditions:
                query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(AuditLog, sort_by, AuditLog.created_at)
        if sort_order == SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Execute query
        result = await db.execute(query)
        logs = result.scalars().all()

        # Get user info for logs
        user_ids = {log.user_id for log in logs if log.user_id}
        users_map = {}
        if user_ids:
            users_result = await db.execute(
                select(User).where(User.id.in_(user_ids))
            )
            for user in users_result.scalars().all():
                users_map[user.id] = user

        # Convert to response format
        log_views = []
        for log in logs:
            user = users_map.get(log.user_id) if log.user_id else None
            log_views.append(AuditLogView(
                id=log.id,
                user_id=log.user_id,
                user_email=user.email if user else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                success=log.success,
                error_message=log.error_message,
                metadata=log.audit_metadata or {},
                created_at=log.created_at,
            ))

        # Action type summary
        action_result = await db.execute(
            select(AuditLog.action, func.count())
            .group_by(AuditLog.action)
            .order_by(func.count().desc())
            .limit(10)
        )
        action_summary = {row[0]: row[1] for row in action_result.all()}

        return AuditLogListResponse(
            logs=log_views,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=math.ceil(total / per_page) if total > 0 else 1,
            action_summary=action_summary,
        )

    @staticmethod
    async def get_audit_log(db: AsyncSession, log_id: UUID) -> Optional[AuditLogView]:
        """Get a single audit log entry by ID.

        Args:
            db: Database session
            log_id: Audit log UUID

        Returns:
            Audit log view or None if not found
        """
        result = await db.execute(
            select(AuditLog).where(AuditLog.id == log_id)
        )
        log = result.scalar_one_or_none()

        if not log:
            return None

        user = None
        if log.user_id:
            user_result = await db.execute(
                select(User).where(User.id == log.user_id)
            )
            user = user_result.scalar_one_or_none()

        return AuditLogView(
            id=log.id,
            user_id=log.user_id,
            user_email=user.email if user else None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            success=log.success,
            error_message=log.error_message,
            metadata=log.audit_metadata or {},
            created_at=log.created_at,
        )

    @staticmethod
    async def list_admin_actions(
        db: AsyncSession,
        page: int = 1,
        per_page: int = 50,
        admin_id: Optional[UUID] = None,
        target_user_id: Optional[UUID] = None,
        action: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Dict[str, Any]:
        """List admin actions with filtering and pagination.

        Args:
            db: Database session
            page: Page number (1-based)
            per_page: Items per page
            admin_id: Filter by admin
            target_user_id: Filter by target user
            action: Filter by action type
            from_date: Filter from date
            to_date: Filter to date
            sort_order: Sort direction

        Returns:
            Paginated admin action list
        """
        query = select(AdminAction)

        conditions = []
        if admin_id:
            conditions.append(AdminAction.admin_id == admin_id)
        if target_user_id:
            conditions.append(AdminAction.target_user_id == target_user_id)
        if action:
            conditions.append(AdminAction.action.ilike(f"%{action}%"))
        if from_date:
            conditions.append(AdminAction.created_at >= from_date)
        if to_date:
            conditions.append(AdminAction.created_at <= to_date)

        if conditions:
            query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        if sort_order == SortOrder.DESC:
            query = query.order_by(AdminAction.created_at.desc())
        else:
            query = query.order_by(AdminAction.created_at.asc())

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Execute query
        result = await db.execute(query)
        actions = result.scalars().all()

        # Get user info
        user_ids = set()
        for action_item in actions:
            if action_item.admin_id:
                user_ids.add(action_item.admin_id)
            if action_item.target_user_id:
                user_ids.add(action_item.target_user_id)

        users_map = {}
        if user_ids:
            users_result = await db.execute(
                select(User).where(User.id.in_(user_ids))
            )
            for user in users_result.scalars().all():
                users_map[user.id] = user

        # Convert to response format
        action_views = []
        for action_item in actions:
            admin = users_map.get(action_item.admin_id) if action_item.admin_id else None
            target = users_map.get(action_item.target_user_id) if action_item.target_user_id else None

            action_views.append(AdminActionView(
                id=action_item.id,
                admin_id=action_item.admin_id,
                admin_email=admin.email if admin else None,
                target_user_id=action_item.target_user_id,
                target_user_email=target.email if target else None,
                action=action_item.action,
                action_details=action_item.action_details or {},
                ip_address=action_item.ip_address,
                user_agent=action_item.user_agent,
                created_at=action_item.created_at,
            ))

        return {
            "actions": action_views,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": math.ceil(total / per_page) if total > 0 else 1,
        }

    @staticmethod
    async def get_user_audit_trail(
        db: AsyncSession,
        user_id: UUID,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Get complete audit trail for a user.

        Combines both audit logs (user's own actions) and admin actions
        (actions taken on the user).

        Args:
            db: Database session
            user_id: User to get trail for
            limit: Maximum entries

        Returns:
            Combined audit trail
        """
        # Get user's audit logs
        audit_result = await db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        audit_logs = audit_result.scalars().all()

        # Get admin actions targeting this user
        admin_result = await db.execute(
            select(AdminAction)
            .where(AdminAction.target_user_id == user_id)
            .order_by(AdminAction.created_at.desc())
            .limit(limit)
        )
        admin_actions = admin_result.scalars().all()

        # Get admin info for admin actions
        admin_ids = {action.admin_id for action in admin_actions if action.admin_id}
        admins_map = {}
        if admin_ids:
            admins_result = await db.execute(
                select(User).where(User.id.in_(admin_ids))
            )
            for admin in admins_result.scalars().all():
                admins_map[admin.id] = admin

        # Format results
        user_actions = [
            {
                "type": "user_action",
                "id": str(log.id),
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "ip_address": log.ip_address,
                "success": log.success,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            }
            for log in audit_logs
        ]

        admin_action_list = [
            {
                "type": "admin_action",
                "id": str(action.id),
                "action": action.action,
                "admin_id": str(action.admin_id) if action.admin_id else None,
                "admin_email": admins_map.get(action.admin_id, None).email if action.admin_id and admins_map.get(action.admin_id) else None,
                "details": action.action_details,
                "ip_address": action.ip_address,
                "timestamp": action.created_at.isoformat() if action.created_at else None,
            }
            for action in admin_actions
        ]

        # Merge and sort by timestamp
        all_entries = user_actions + admin_action_list
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "user_id": str(user_id),
            "entries": all_entries[:limit],
            "user_action_count": len(audit_logs),
            "admin_action_count": len(admin_actions),
        }

    @staticmethod
    async def export_audit_logs(
        db: AsyncSession,
        filters: Optional[AuditLogFilters] = None,
        format: str = "csv",
    ) -> bytes:
        """Export audit logs to file.

        Args:
            db: Database session
            filters: Optional filters
            format: Export format (csv, json)

        Returns:
            File content as bytes
        """
        # Get filtered logs (up to 10000 for export)
        response = await AuditService.list_audit_logs(
            db, page=1, per_page=10000, filters=filters
        )

        if format == "csv":
            return AuditService._export_to_csv(response.logs)
        else:
            return AuditService._export_to_json(response.logs)

    @staticmethod
    def _export_to_csv(logs: List[AuditLogView]) -> bytes:
        """Export logs to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)

        # Header
        writer.writerow([
            "ID",
            "Zeitstempel",
            "Benutzer-ID",
            "Benutzer-Email",
            "Aktion",
            "Ressourcen-Typ",
            "Ressourcen-ID",
            "IP-Adresse",
            "Erfolgreich",
            "Fehlermeldung",
        ])

        # Data
        for log in logs:
            writer.writerow([
                str(log.id),
                log.created_at.isoformat() if log.created_at else "",
                str(log.user_id) if log.user_id else "",
                log.user_email or "",
                log.action,
                log.resource_type or "",
                log.resource_id or "",
                log.ip_address or "",
                "Ja" if log.success else "Nein",
                log.error_message or "",
            ])

        return output.getvalue().encode('utf-8-sig')  # BOM for Excel

    @staticmethod
    def _export_to_json(logs: List[AuditLogView]) -> bytes:
        """Export logs to JSON format."""
        import json

        data = [
            {
                "id": str(log.id),
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "user_id": str(log.user_id) if log.user_id else None,
                "user_email": log.user_email,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "success": log.success,
                "error_message": log.error_message,
                "metadata": log.metadata,
            }
            for log in logs
        ]

        return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

    @staticmethod
    async def get_statistics(
        db: AsyncSession,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get audit log statistics.

        Args:
            db: Database session
            days: Number of days to analyze

        Returns:
            Statistics dictionary
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Total entries
        total_result = await db.execute(
            select(func.count()).where(AuditLog.created_at >= cutoff)
        )
        total_entries = total_result.scalar() or 0

        # Entries by action
        action_result = await db.execute(
            select(AuditLog.action, func.count())
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.action)
            .order_by(func.count().desc())
            .limit(20)
        )
        by_action = {row[0]: row[1] for row in action_result.all()}

        # Entries by resource type
        resource_result = await db.execute(
            select(AuditLog.resource_type, func.count())
            .where(
                and_(
                    AuditLog.created_at >= cutoff,
                    AuditLog.resource_type.isnot(None),
                )
            )
            .group_by(AuditLog.resource_type)
            .order_by(func.count().desc())
        )
        by_resource = {row[0]: row[1] for row in resource_result.all()}

        # Success/failure ratio
        success_result = await db.execute(
            select(AuditLog.success, func.count())
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.success)
        )
        success_counts = {row[0]: row[1] for row in success_result.all()}

        # Most active users
        user_result = await db.execute(
            select(AuditLog.user_id, func.count())
            .where(
                and_(
                    AuditLog.created_at >= cutoff,
                    AuditLog.user_id.isnot(None),
                )
            )
            .group_by(AuditLog.user_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_user_ids = [(row[0], row[1]) for row in user_result.all()]

        # Get user emails
        if top_user_ids:
            user_ids = [uid for uid, _ in top_user_ids]
            users_result = await db.execute(
                select(User).where(User.id.in_(user_ids))
            )
            users_map = {u.id: u.email for u in users_result.scalars().all()}
            most_active_users = [
                {"user_id": str(uid), "email": users_map.get(uid), "count": count}
                for uid, count in top_user_ids
            ]
        else:
            most_active_users = []

        # Admin actions count
        admin_result = await db.execute(
            select(func.count()).where(AdminAction.created_at >= cutoff)
        )
        admin_action_count = admin_result.scalar() or 0

        return {
            "period_days": days,
            "total_entries": total_entries,
            "by_action": by_action,
            "by_resource_type": by_resource,
            "success_count": success_counts.get(True, 0),
            "failure_count": success_counts.get(False, 0),
            "most_active_users": most_active_users,
            "admin_action_count": admin_action_count,
        }
