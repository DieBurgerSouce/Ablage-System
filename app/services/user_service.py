"""
User service for managing user accounts and authentication.

Handles user CRUD operations, password management, and authentication logic.
All error messages in German.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.db.models import User
from app.db.schemas import UserCreate, UserUpdate, UserChangePassword, UserResponse
from app.core.security import (
    get_password_hash,
    verify_password,
    validate_password_strength
)


class UserService:
    """Service for user management operations."""

    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_data: UserCreate
    ) -> User:
        """
        Create a new user account.

        Args:
            db: Database session
            user_data: User creation data

        Returns:
            Created user object

        Raises:
            HTTPException: If user already exists or password is weak
        """
        # Validate password strength
        is_valid, error_msg = validate_password_strength(user_data.password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

        # Check if user already exists
        existing_user = await UserService.get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Benutzer mit dieser E-Mail existiert bereits"  # User with this email already exists
            )

        existing_username = await UserService.get_user_by_username(db, user_data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Benutzername ist bereits vergeben"  # Username is already taken
            )

        # Create user
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            username=user_data.username.lower(),
            hashed_password=hashed_password,
            full_name=user_data.full_name,
            preferred_language=user_data.preferred_language,
            is_active=True,
            is_superuser=False
        )

        try:
            db.add(db_user)
            await db.commit()
            await db.refresh(db_user)
            return db_user
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fehler beim Erstellen des Benutzers"  # Error creating user
            )

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str
    ) -> Optional[User]:
        """
        Authenticate a user with email and password.

        Args:
            db: Database session
            email: User email
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        user = await UserService.get_user_by_email(db, email)
        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        # Update last login
        await UserService.update_last_login(db, user.id)

        return user

    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: UUID
    ) -> Optional[User]:
        """
        Get user by ID.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            User object or None if not found
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(
        db: AsyncSession,
        email: str
    ) -> Optional[User]:
        """
        Get user by email.

        Args:
            db: Database session
            email: User email

        Returns:
            User object or None if not found
        """
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(
        db: AsyncSession,
        username: str
    ) -> Optional[User]:
        """
        Get user by username.

        Args:
            db: Database session
            username: Username

        Returns:
            User object or None if not found
        """
        result = await db.execute(
            select(User).where(User.username == username.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: UUID,
        user_data: UserUpdate
    ) -> Optional[User]:
        """
        Update user profile.

        Args:
            db: Database session
            user_id: User ID
            user_data: Update data

        Returns:
            Updated user object or None if not found

        Raises:
            HTTPException: If email or username already exists
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        # Check email uniqueness if changing
        if user_data.email and user_data.email != user.email:
            existing = await UserService.get_user_by_email(db, user_data.email)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="E-Mail-Adresse wird bereits verwendet"  # Email already in use
                )

        # Update fields
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        try:
            await db.commit()
            await db.refresh(user)
            return user
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fehler beim Aktualisieren des Benutzers"  # Error updating user
            )

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user_id: UUID,
        password_data: UserChangePassword
    ) -> bool:
        """
        Change user password.

        Args:
            db: Database session
            user_id: User ID
            password_data: Current and new password

        Returns:
            True if password changed successfully

        Raises:
            HTTPException: If current password is wrong or new password is weak
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Benutzer nicht gefunden"  # User not found
            )

        # Verify current password
        if not verify_password(password_data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aktuelles Passwort ist falsch"  # Current password is incorrect
            )

        # Validate new password strength
        is_valid, error_msg = validate_password_strength(password_data.new_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

        # Update password
        user.hashed_password = get_password_hash(password_data.new_password)

        try:
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Fehler beim Ändern des Passworts"  # Error changing password
            )

    @staticmethod
    async def delete_user(
        db: AsyncSession,
        user_id: UUID
    ) -> bool:
        """
        Delete a user account (soft delete by setting is_active=False).

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if user deleted successfully
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return False

        user.is_active = False

        try:
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            return False

    @staticmethod
    async def update_last_login(
        db: AsyncSession,
        user_id: UUID
    ) -> None:
        """
        Update user's last login timestamp.

        Args:
            db: Database session
            user_id: User ID
        """
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login=datetime.now(timezone.utc))
        )
        await db.commit()

    @staticmethod
    async def list_users(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True
    ) -> List[User]:
        """
        List users with pagination.

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            active_only: If True, return only active users

        Returns:
            List of user objects
        """
        query = select(User)

        if active_only:
            query = query.where(User.is_active == True)

        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def activate_user(
        db: AsyncSession,
        user_id: UUID
    ) -> bool:
        """
        Activate a user account.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if user activated successfully
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return False

        user.is_active = True

        try:
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            return False

    @staticmethod
    async def deactivate_user(
        db: AsyncSession,
        user_id: UUID
    ) -> bool:
        """
        Deactivate a user account.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if user deactivated successfully
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return False

        user.is_active = False

        try:
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            return False

    @staticmethod
    async def make_superuser(
        db: AsyncSession,
        user_id: UUID
    ) -> bool:
        """
        Grant superuser privileges to a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if privileges granted successfully
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return False

        user.is_superuser = True

        try:
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            return False
