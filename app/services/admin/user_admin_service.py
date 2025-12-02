"""User Administration Service.

Provides user management operations for the admin console:
- List users with filtering and pagination
- Create, update, delete users
- Role and tier management
- Password reset
- User activity tracking
"""

import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import math

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import User, AuditLog, AdminAction
from app.db.schemas import (
    UserAdminView,
    UserListFilters,
    UserListResponse,
    UserAdminCreate,
    UserAdminUpdate,
    UserPasswordReset,
    UserActivityItem,
    UserActivityResponse,
    UserRole,
    UserStatus,
    UserTier,
    SortOrder,
)
from app.core.security import get_password_hash

logger = structlog.get_logger(__name__)


class UserAdminService:
    """Service for user administration operations."""

    # Default rate limits by tier
    TIER_DEFAULTS = {
        "free": {"ocr_hourly": 10, "ocr_daily": 50, "batch_hourly": 5, "api_per_minute": 20},
        "premium": {"ocr_hourly": 100, "ocr_daily": 1000, "batch_hourly": 50, "api_per_minute": 100},
        "admin": {"ocr_hourly": 10000, "ocr_daily": 100000, "batch_hourly": 1000, "api_per_minute": 1000},
    }

    @staticmethod
    async def list_users(
        db: AsyncSession,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[UserListFilters] = None,
        sort_by: str = "created_at",
        sort_order: SortOrder = SortOrder.DESC,
    ) -> UserListResponse:
        """List users with filtering and pagination.

        Args:
            db: Database session
            page: Page number (1-based)
            per_page: Items per page
            filters: Optional filters
            sort_by: Field to sort by
            sort_order: Sort direction

        Returns:
            Paginated user list
        """
        query = select(User)

        # Apply filters
        if filters:
            conditions = []

            # Search filter (email, username, full_name)
            if filters.search:
                # Escape LIKE-Wildcards um Injection zu verhindern
                # % und _ werden als literale Zeichen behandelt
                safe_search = (
                    filters.search
                    .replace("\\", "\\\\")  # Escape backslash first
                    .replace("%", "\\%")     # Escape %
                    .replace("_", "\\_")     # Escape _
                )
                search_term = f"%{safe_search}%"
                conditions.append(
                    or_(
                        User.email.ilike(search_term, escape="\\"),
                        User.username.ilike(search_term, escape="\\"),
                        User.full_name.ilike(search_term, escape="\\"),
                    )
                )

            # Role filter
            if filters.role:
                if filters.role == UserRole.SUPERUSER:
                    conditions.append(User.is_superuser == True)
                elif filters.role == UserRole.ADMIN:
                    conditions.append(and_(User.tier == "admin", User.is_superuser == False))
                else:
                    conditions.append(and_(User.tier != "admin", User.is_superuser == False))

            # Status filter
            if filters.status:
                if filters.status == UserStatus.ACTIVE:
                    conditions.append(and_(User.is_active == True, User.deactivated_at.is_(None)))
                elif filters.status == UserStatus.INACTIVE:
                    conditions.append(and_(User.is_active == False, User.deactivated_at.is_(None)))
                elif filters.status == UserStatus.DEACTIVATED:
                    conditions.append(User.deactivated_at.isnot(None))

            # Tier filter
            if filters.tier:
                conditions.append(User.tier == filters.tier.value)

            # Date filters
            if filters.created_from:
                conditions.append(User.created_at >= filters.created_from)
            if filters.created_to:
                conditions.append(User.created_at <= filters.created_to)
            if filters.last_login_from:
                conditions.append(User.last_login >= filters.last_login_from)
            if filters.last_login_to:
                conditions.append(User.last_login <= filters.last_login_to)

            if conditions:
                query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(User, sort_by, User.created_at)
        if sort_order == SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Execute query
        result = await db.execute(query)
        users = result.scalars().all()

        # Convert to response format
        user_views = [UserAdminView.from_orm_with_computed(user) for user in users]

        return UserListResponse(
            users=user_views,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=math.ceil(total / per_page) if total > 0 else 1,
        )

    @staticmethod
    async def get_user(db: AsyncSession, user_id: UUID) -> Optional[UserAdminView]:
        """Get a single user by ID.

        Args:
            db: Database session
            user_id: User UUID

        Returns:
            User view or None if not found
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            return UserAdminView.from_orm_with_computed(user)
        return None

    @staticmethod
    async def create_user(
        db: AsyncSession,
        data: UserAdminCreate,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> User:
        """Create a new user.

        Args:
            db: Database session
            data: User creation data
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Created user
        """
        # Hash password
        hashed_password = get_password_hash(data.password)

        # Create user
        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hashed_password,
            full_name=data.full_name,
            is_superuser=data.is_superuser,
            tier=data.tier.value,
            daily_quota=data.daily_quota,
            notes=data.notes,
            is_active=True,
        )

        db.add(user)
        await db.flush()

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user.id,
            action="create_user",
            action_details={
                "email": data.email,
                "username": data.username,
                "tier": data.tier.value,
                "is_superuser": data.is_superuser,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "user_created_by_admin",
            user_id=str(user.id),
            admin_id=str(admin.id),
            email=data.email,
        )

        return user

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: UUID,
        data: UserAdminUpdate,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """Update a user.

        Args:
            db: Database session
            user_id: User to update
            data: Update data
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Updated user or None if not found
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Track changes
        changes = {}
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if value is not None:
                old_value = getattr(user, field)
                if old_value != value:
                    # Convert enum to string if necessary
                    if hasattr(value, 'value'):
                        value = value.value
                    changes[field] = {"old": old_value, "new": value}
                    setattr(user, field, value)

        if changes:
            # Log admin action
            admin_action = AdminAction(
                admin_id=admin.id,
                target_user_id=user.id,
                action="update_user",
                action_details={"changes": changes},
                ip_address=ip_address,
            )
            db.add(admin_action)

            await db.commit()
            await db.refresh(user)

            logger.info(
                "user_updated_by_admin",
                user_id=str(user_id),
                admin_id=str(admin.id),
                changes=list(changes.keys()),
            )

        return user

    @staticmethod
    async def deactivate_user(
        db: AsyncSession,
        user_id: UUID,
        admin: User,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """Deactivate a user account.

        Args:
            db: Database session
            user_id: User to deactivate
            admin: Admin performing the action
            reason: Reason for deactivation
            ip_address: Request IP address

        Returns:
            Deactivated user or None if not found
        """
        # Prevent self-deactivation
        if user_id == admin.id:
            raise ValueError("Sie koennen Ihr eigenes Konto nicht deaktivieren")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Deactivate
        user.is_active = False
        user.deactivated_at = datetime.utcnow()
        user.deactivated_by_id = admin.id

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user.id,
            action="deactivate_user",
            action_details={"reason": reason},
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "user_deactivated",
            user_id=str(user_id),
            admin_id=str(admin.id),
            reason=reason,
        )

        return user

    @staticmethod
    async def activate_user(
        db: AsyncSession,
        user_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """Reactivate a deactivated user account.

        Args:
            db: Database session
            user_id: User to activate
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Activated user or None if not found
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Activate
        user.is_active = True
        user.deactivated_at = None
        user.deactivated_by_id = None

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user.id,
            action="activate_user",
            action_details={},
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "user_activated",
            user_id=str(user_id),
            admin_id=str(admin.id),
        )

        return user

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        user_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> Optional[UserPasswordReset]:
        """Reset a user's password.

        Generates a secure temporary password and sets password_reset_required.

        Args:
            db: Database session
            user_id: User whose password to reset
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Password reset response or None if user not found
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Generate secure temporary password
        temp_password = secrets.token_urlsafe(16)
        hashed_password = get_password_hash(temp_password)

        # Update user
        user.hashed_password = hashed_password
        user.password_reset_required = True

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user.id,
            action="reset_password",
            action_details={},
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()

        logger.info(
            "password_reset_by_admin",
            user_id=str(user_id),
            admin_id=str(admin.id),
        )

        return UserPasswordReset(
            success=True,
            temporary_password=temp_password,
            message="Passwort wurde zurueckgesetzt. Der Benutzer muss es bei der naechsten Anmeldung aendern.",
        )

    @staticmethod
    async def change_role(
        db: AsyncSession,
        user_id: UUID,
        is_superuser: bool,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """Change a user's superuser status.

        Args:
            db: Database session
            user_id: User whose role to change
            is_superuser: New superuser status
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Updated user or None if not found
        """
        # Prevent self-demotion
        if user_id == admin.id and not is_superuser:
            raise ValueError("Sie koennen sich nicht selbst herabstufen")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        old_value = user.is_superuser
        user.is_superuser = is_superuser

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user.id,
            action="change_role",
            action_details={
                "old_is_superuser": old_value,
                "new_is_superuser": is_superuser,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "user_role_changed",
            user_id=str(user_id),
            admin_id=str(admin.id),
            is_superuser=is_superuser,
        )

        return user

    @staticmethod
    async def get_user_activity(
        db: AsyncSession,
        user_id: UUID,
        limit: int = 50,
    ) -> UserActivityResponse:
        """Get recent activity for a user.

        Args:
            db: Database session
            user_id: User to get activity for
            limit: Maximum number of entries

        Returns:
            User activity response
        """
        query = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(query)
        logs = result.scalars().all()

        activities = [
            UserActivityItem(
                id=log.id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                created_at=log.created_at,
                details=log.audit_metadata or {},
            )
            for log in logs
        ]

        # Get total count
        count_result = await db.execute(
            select(func.count()).where(AuditLog.user_id == user_id)
        )
        total = count_result.scalar() or 0

        return UserActivityResponse(
            user_id=user_id,
            activities=activities,
            total=total,
        )

    @staticmethod
    async def delete_user(
        db: AsyncSession,
        user_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Permanently delete a user.

        This is a destructive operation. Consider using deactivate_user instead.

        Args:
            db: Database session
            user_id: User to delete
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            True if deleted, False if not found
        """
        # Prevent self-deletion
        if user_id == admin.id:
            raise ValueError("Sie koennen Ihr eigenes Konto nicht loeschen")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Log admin action BEFORE deletion
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=None,  # Will be null after deletion
            action="delete_user",
            action_details={
                "deleted_user_email": user.email,
                "deleted_user_id": str(user_id),
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        # Delete user
        await db.delete(user)
        await db.commit()

        logger.warning(
            "user_deleted_permanently",
            user_id=str(user_id),
            admin_id=str(admin.id),
            deleted_email=user.email,
        )

        return True
