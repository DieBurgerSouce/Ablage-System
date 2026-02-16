"""
Portal-Kommunikationsservice.

Nachrichten zwischen Kunden und Unternehmen.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update
import structlog

from app.db.models_portal import (
    PortalMessage, PortalUser, MessageDirection
)

logger = structlog.get_logger(__name__)


class PortalCommunicationService:
    """
    Service für Kommunikation im Kundenportal.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_message(
        self,
        portal_user: PortalUser,
        content: str,
        subject: Optional[str] = None,
        complaint_id: Optional[UUID] = None,
        attachments: Optional[List[str]] = None,
    ) -> PortalMessage:
        """
        Sende eine Nachricht vom Kunden an das Unternehmen.
        """
        message = PortalMessage(
            company_id=portal_user.company_id,
            entity_id=portal_user.entity_id,
            complaint_id=complaint_id,
            portal_user_id=portal_user.id,
            direction=MessageDirection.INBOUND.value,
            subject=subject,
            content=content,
            attachments=attachments or [],
            is_read=False,
        )

        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        logger.info(
            "portal_message_sent",
            message_id=str(message.id),
            entity_id=str(portal_user.entity_id),
            direction="inbound",
        )

        return message

    async def get_messages(
        self,
        entity_id: UUID,
        company_id: UUID,
        complaint_id: Optional[UUID] = None,
        direction: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole alle Nachrichten für einen Entity.
        """
        query = select(PortalMessage).where(
            and_(
                PortalMessage.entity_id == entity_id,
                PortalMessage.company_id == company_id,
            )
        )

        if complaint_id:
            query = query.where(PortalMessage.complaint_id == complaint_id)
        if direction:
            query = query.where(PortalMessage.direction == direction)
        if unread_only:
            query = query.where(
                and_(
                    PortalMessage.is_read == False,
                    PortalMessage.direction == MessageDirection.OUTBOUND.value,
                )
            )

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(PortalMessage.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        message_list = []
        for msg in messages:
            message_list.append({
                "id": str(msg.id),
                "direction": msg.direction,
                "subject": msg.subject,
                "content": msg.content,
                "attachments": msg.attachments,
                "is_read": msg.is_read,
                "read_at": msg.read_at.isoformat() if msg.read_at else None,
                "complaint_id": str(msg.complaint_id) if msg.complaint_id else None,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            })

        return message_list, total

    async def get_conversation(
        self,
        entity_id: UUID,
        company_id: UUID,
        complaint_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        Hole alle Nachrichten einer Konversation in chronologischer Reihenfolge.
        """
        query = select(PortalMessage).where(
            and_(
                PortalMessage.entity_id == entity_id,
                PortalMessage.company_id == company_id,
            )
        )

        if complaint_id:
            query = query.where(PortalMessage.complaint_id == complaint_id)

        query = query.order_by(PortalMessage.created_at.asc())
        query = query.limit(limit)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        return [
            {
                "id": str(msg.id),
                "direction": msg.direction,
                "subject": msg.subject,
                "content": msg.content,
                "attachments": msg.attachments,
                "is_read": msg.is_read,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]

    async def mark_as_read(
        self,
        message_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> bool:
        """
        Markiere eine Nachricht als gelesen.

        Nur für ausgehende Nachrichten (vom Unternehmen an Kunden).
        """
        result = await self.db.execute(
            select(PortalMessage).where(
                and_(
                    PortalMessage.id == message_id,
                    PortalMessage.entity_id == entity_id,
                    PortalMessage.company_id == company_id,
                    PortalMessage.direction == MessageDirection.OUTBOUND.value,
                )
            )
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        if not message.is_read:
            message.is_read = True
            message.read_at = datetime.now(timezone.utc)
            await self.db.commit()

        return True

    async def mark_all_as_read(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> int:
        """
        Markiere alle ungelesenen Nachrichten als gelesen.

        Returns:
            Anzahl der markierten Nachrichten.
        """
        result = await self.db.execute(
            update(PortalMessage)
            .where(
                and_(
                    PortalMessage.entity_id == entity_id,
                    PortalMessage.company_id == company_id,
                    PortalMessage.direction == MessageDirection.OUTBOUND.value,
                    PortalMessage.is_read == False,
                )
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        await self.db.commit()

        count = result.rowcount
        logger.info(
            "portal_messages_marked_read",
            entity_id=str(entity_id),
            count=count,
        )

        return count

    async def get_unread_count(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> int:
        """
        Hole Anzahl ungelesener Nachrichten.
        """
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    PortalMessage.entity_id == entity_id,
                    PortalMessage.company_id == company_id,
                    PortalMessage.direction == MessageDirection.OUTBOUND.value,
                    PortalMessage.is_read == False,
                )
            )
        )
        return result.scalar() or 0

    async def get_communication_summary(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict:
        """
        Hole Zusammenfassung der Kommunikation.
        """
        # Alle Nachrichten
        result = await self.db.execute(
            select(PortalMessage).where(
                and_(
                    PortalMessage.entity_id == entity_id,
                    PortalMessage.company_id == company_id,
                )
            )
        )
        messages = result.scalars().all()

        total = len(messages)
        inbound = sum(1 for m in messages if m.direction == MessageDirection.INBOUND.value)
        outbound = sum(1 for m in messages if m.direction == MessageDirection.OUTBOUND.value)
        unread = sum(
            1 for m in messages
            if m.direction == MessageDirection.OUTBOUND.value and not m.is_read
        )

        # Letzte Nachricht
        last_message = None
        if messages:
            sorted_messages = sorted(messages, key=lambda m: m.created_at or datetime.min, reverse=True)
            last = sorted_messages[0]
            last_message = {
                "id": str(last.id),
                "direction": last.direction,
                "subject": last.subject,
                "created_at": last.created_at.isoformat() if last.created_at else None,
            }

        return {
            "total_messages": total,
            "inbound_count": inbound,
            "outbound_count": outbound,
            "unread_count": unread,
            "last_message": last_message,
        }


def get_portal_communication_service(db: AsyncSession) -> PortalCommunicationService:
    """Factory-Funktion für PortalCommunicationService."""
    return PortalCommunicationService(db)
