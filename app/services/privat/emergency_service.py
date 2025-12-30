"""Service fuer Notfallzugriff im Privat-Modul.

Enterprise Features:
- Vertrauenspersonen-Verwaltung
- Wartezeit-basierte Notfallzugriff-Anfragen
- E-Mail-Benachrichtigungen an Owner
- Automatische Genehmigung nach Wartezeit
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog


# SECURITY FIX 27-9: PII Masking fuer Logs (GDPR-konform)
def _mask_email_for_log(email: Optional[str]) -> str:
    """Maskiert Email-Adresse fuer Log-Ausgabe."""
    if not email or "@" not in email:
        return "[no-email]"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}***@{domain}"

from app.db.models import (
    PrivatEmergencyContact,
    PrivatEmergencyAccessRequest,
    PrivatSpace,
    User,
)
from app.db.schemas import (
    PrivatEmergencyContactCreate,
    PrivatEmergencyContactUpdate,
    PrivatEmergencyContactResponse,
    PrivatEmergencyAccessRequestCreate,
    PrivatEmergencyAccessRequestResponse,
    PrivatEmergencyAccessStatus,
)
from app.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)

# Singleton NotificationService
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Gibt den globalen NotificationService zurueck."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


class PrivatEmergencyService:
    """Service fuer Notfallzugriff-Verwaltung.

    Workflow:
    1. Owner definiert Vertrauenspersonen (Emergency Contacts)
    2. Konfiguriert Wartezeit pro Kontakt (z.B. 30 Tage)
    3. Im Notfall: Vertrauensperson fordert Zugriff an
    4. Owner erhaelt Benachrichtigung
    5. Nach Wartezeit ohne Widerruf: Zugriff wird automatisch gewaehrt
    """

    # ========== Emergency Contact CRUD ==========

    async def create_contact(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatEmergencyContactCreate,
    ) -> PrivatEmergencyContact:
        """Erstellt einen neuen Notfallkontakt.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Kontakt-Daten

        Returns:
            Erstellter Kontakt
        """
        contact = PrivatEmergencyContact(
            id=uuid.uuid4(),
            space_id=space_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            relationship=data.relationship,
            waiting_period_days=data.waiting_period_days,
            notes=data.notes,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        # SECURITY FIX 27-9: PII Masking - Email nicht vollstaendig loggen!
        logger.info(
            "privat_emergency_contact_created",
            contact_id=str(contact.id),
            space_id=str(space_id),
            email=_mask_email_for_log(data.email),
        )

        return contact

    async def get_contact(
        self,
        db: AsyncSession,
        contact_id: uuid.UUID,
    ) -> Optional[PrivatEmergencyContact]:
        """Holt einen Kontakt nach ID."""
        result = await db.execute(
            select(PrivatEmergencyContact)
            .where(PrivatEmergencyContact.id == contact_id)
        )
        return result.scalar_one_or_none()

    async def get_contact_with_access_check(
        self,
        db: AsyncSession,
        contact_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatEmergencyContact]:
        """IDOR-sichere Methode: Holt Kontakt nur wenn User Zugriff hat.

        SECURITY: Gibt einheitlich None zurueck bei:
        - Kontakt existiert nicht
        - User hat keinen Zugriff

        Dies verhindert Information Disclosure ueber Existenz von Kontakten.

        Args:
            db: Datenbank-Session
            contact_id: Kontakt-ID
            requesting_user_id: ID des anfragenden Users

        Returns:
            Kontakt wenn vorhanden und Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpaceAccess

        # Join mit Space um Owner zu pruefen
        result = await db.execute(
            select(PrivatEmergencyContact, PrivatSpace)
            .join(PrivatSpace, PrivatEmergencyContact.space_id == PrivatSpace.id)
            .where(PrivatEmergencyContact.id == contact_id)
        )
        row = result.first()

        if not row:
            return None

        contact, space = row

        # Owner hat immer Zugriff
        if space.owner_id == requesting_user_id:
            return contact

        # Pruefe explizite Berechtigung (erfordert ADMIN-Level fuer Emergency Contacts)
        now = datetime.utcnow()
        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now,
                ),
                PrivatSpaceAccess.access_level == "admin",  # Nur Admins duerfen Kontakte verwalten
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            # SECURITY: Log IDOR-Versuch ohne sensible Details
            logger.warning(
                "idor_emergency_contact_attempt_blocked",
                contact_id=str(contact_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        return contact

    async def get_contact_by_email(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        email: str,
    ) -> Optional[PrivatEmergencyContact]:
        """Holt einen Kontakt nach E-Mail."""
        result = await db.execute(
            select(PrivatEmergencyContact)
            .where(
                PrivatEmergencyContact.space_id == space_id,
                PrivatEmergencyContact.email == email,
                PrivatEmergencyContact.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def list_contacts(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> List[PrivatEmergencyContactResponse]:
        """Listet alle Notfallkontakte eines Spaces.

        SECURITY FIX 22-4: Pagination um DoS durch unbegrenzte Listen zu verhindern.
        """
        conditions = [PrivatEmergencyContact.space_id == space_id]
        if active_only:
            conditions.append(PrivatEmergencyContact.is_active == True)

        # SECURITY FIX 22-4: Pagination anwenden
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatEmergencyContact)
            .where(and_(*conditions))
            .order_by(PrivatEmergencyContact.last_name)
            .offset(offset)
            .limit(page_size)
        )

        contacts = result.scalars().all()
        return [
            PrivatEmergencyContactResponse(
                id=c.id,
                space_id=c.space_id,
                first_name=c.first_name,
                last_name=c.last_name,
                email=c.email,
                phone=c.phone,
                relationship=c.relationship,
                waiting_period_days=c.waiting_period_days,
                notes=c.notes,
                is_active=c.is_active,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in contacts
        ]

    async def update_contact(
        self,
        db: AsyncSession,
        contact_id: uuid.UUID,
        data: PrivatEmergencyContactUpdate,
    ) -> Optional[PrivatEmergencyContact]:
        """Aktualisiert einen Kontakt.

        SECURITY FIX 23-11: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Kontaktdaten entstehen

        Args:
            db: Datenbank-Session
            contact_id: Kontakt-ID
            data: Update-Daten

        Returns:
            Aktualisierter Kontakt oder None
        """
        # SECURITY FIX 23-11: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatEmergencyContact)
            .where(PrivatEmergencyContact.id == contact_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Kontaktdaten!
        )
        contact = result.scalar_one_or_none()
        if not contact:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(contact, key, value)

        contact.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(contact)

        logger.info(
            "privat_emergency_contact_updated",
            contact_id=str(contact_id),
        )

        return contact

    async def delete_contact(
        self,
        db: AsyncSession,
        contact_id: uuid.UUID,
        soft_delete: bool = True,
    ) -> bool:
        """Loescht einen Kontakt.

        SECURITY FIX 23-12: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende bei gleichzeitigem Update/Delete entstehen

        Args:
            db: Datenbank-Session
            contact_id: Kontakt-ID
            soft_delete: Soft-Delete (deaktivieren) oder hard delete

        Returns:
            True wenn erfolgreich
        """
        # SECURITY FIX 23-12: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatEmergencyContact)
            .where(PrivatEmergencyContact.id == contact_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        contact = result.scalar_one_or_none()
        if not contact:
            return False

        if soft_delete:
            contact.is_active = False
            contact.updated_at = datetime.utcnow()
            await db.commit()
        else:
            await db.delete(contact)
            await db.commit()

        logger.info(
            "privat_emergency_contact_deleted",
            contact_id=str(contact_id),
            soft_delete=soft_delete,
        )

        return True

    # ========== Access Request Management ==========

    async def request_access(
        self,
        db: AsyncSession,
        contact_email: str,
        data: PrivatEmergencyAccessRequestCreate,
    ) -> Optional[PrivatEmergencyAccessRequest]:
        """Erstellt eine Notfallzugriff-Anfrage.

        Args:
            db: Datenbank-Session
            contact_email: E-Mail des anfragenden Kontakts
            data: Anfrage-Daten

        Returns:
            Erstellte Anfrage oder None wenn Kontakt nicht gefunden
        """
        # Finde Kontakt
        contact = await self.get_contact_by_email(db, data.space_id, contact_email)
        if not contact:
            # SECURITY FIX 27-9: PII Masking - Email nicht vollstaendig loggen!
            logger.warning(
                "privat_emergency_access_denied",
                space_id=str(data.space_id),
                email=_mask_email_for_log(contact_email),
                reason="contact_not_found",
            )
            return None

        # Pruefe ob bereits eine offene Anfrage existiert
        existing = await self._get_pending_request(db, data.space_id, contact.id)
        if existing:
            return existing

        # Berechne Wartezeit-Ende
        waiting_until = datetime.utcnow() + timedelta(days=contact.waiting_period_days)

        request = PrivatEmergencyAccessRequest(
            id=uuid.uuid4(),
            space_id=data.space_id,
            contact_id=contact.id,
            status=PrivatEmergencyAccessStatus.PENDING.value,
            reason=data.reason,
            requested_at=datetime.utcnow(),
            waiting_until=waiting_until,
        )

        db.add(request)
        await db.commit()
        await db.refresh(request)

        logger.info(
            "privat_emergency_access_requested",
            request_id=str(request.id),
            space_id=str(data.space_id),
            contact_id=str(contact.id),
            waiting_until=str(waiting_until),
        )

        # SECURITY: Benachrichtigung an Owner senden (Enterprise Requirement)
        await self._notify_owner_access_requested(db, request, contact)

        return request

    async def _get_pending_request(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        contact_id: uuid.UUID,
    ) -> Optional[PrivatEmergencyAccessRequest]:
        """Holt eine offene Anfrage."""
        result = await db.execute(
            select(PrivatEmergencyAccessRequest)
            .where(
                PrivatEmergencyAccessRequest.space_id == space_id,
                PrivatEmergencyAccessRequest.contact_id == contact_id,
                PrivatEmergencyAccessRequest.status == PrivatEmergencyAccessStatus.PENDING.value,
            )
        )
        return result.scalar_one_or_none()

    async def get_request(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
    ) -> Optional[PrivatEmergencyAccessRequest]:
        """Holt eine Anfrage nach ID."""
        result = await db.execute(
            select(PrivatEmergencyAccessRequest)
            .where(PrivatEmergencyAccessRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_request_with_access_check(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatEmergencyAccessRequest]:
        """IDOR-sichere Methode: Holt Request nur wenn User Zugriff hat.

        SECURITY: Gibt einheitlich None zurueck bei:
        - Request existiert nicht
        - User hat keinen Zugriff (kein Space-Owner)

        Nur der Space-Owner darf Notfallzugriff-Anfragen bearbeiten.

        Args:
            db: Datenbank-Session
            request_id: Request-ID
            requesting_user_id: ID des anfragenden Users

        Returns:
            Request wenn vorhanden und Zugriff erlaubt, sonst None
        """
        # Join mit Space um Owner zu pruefen
        result = await db.execute(
            select(PrivatEmergencyAccessRequest, PrivatSpace)
            .join(PrivatSpace, PrivatEmergencyAccessRequest.space_id == PrivatSpace.id)
            .where(PrivatEmergencyAccessRequest.id == request_id)
        )
        row = result.first()

        if not row:
            return None

        request, space = row

        # NUR Owner darf Notfallzugriff-Anfragen bearbeiten!
        # Dies ist ein Enterprise-Requirement fuer Datenschutz
        if space.owner_id != requesting_user_id:
            # SECURITY: Log IDOR-Versuch ohne sensible Details
            logger.warning(
                "idor_emergency_request_attempt_blocked",
                request_id=str(request_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        return request

    async def list_requests(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        status: Optional[PrivatEmergencyAccessStatus] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> List[PrivatEmergencyAccessRequestResponse]:
        """Listet alle Anfragen eines Spaces.

        SECURITY FIX 22-5: Pagination um DoS durch unbegrenzte Listen zu verhindern.
        """
        conditions = [PrivatEmergencyAccessRequest.space_id == space_id]
        if status:
            conditions.append(
                PrivatEmergencyAccessRequest.status == status.value
            )

        # SECURITY FIX 22-5: Pagination anwenden
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatEmergencyAccessRequest)
            .where(and_(*conditions))
            .order_by(PrivatEmergencyAccessRequest.requested_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        requests = result.scalars().all()
        return [
            PrivatEmergencyAccessRequestResponse(
                id=r.id,
                space_id=r.space_id,
                contact_id=r.contact_id,
                status=PrivatEmergencyAccessStatus(r.status),
                reason=r.reason,
                requested_at=r.requested_at,
                waiting_until=r.waiting_until,
                approved_at=r.approved_at,
                denied_at=r.denied_at,
                denied_reason=r.denied_reason,
            )
            for r in requests
        ]

    async def approve_request(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        approved_by: uuid.UUID,
    ) -> Optional[PrivatEmergencyAccessRequest]:
        """Genehmigt eine Notfallzugriff-Anfrage (durch Owner).

        SECURITY FIX 22-2: Row Lock und Access-Check um TOCTOU Race Conditions
        und IDOR zu verhindern.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID
            approved_by: ID des genehmigenden Benutzers (MUSS Space-Owner sein)

        Returns:
            Aktualisierte Anfrage
        """
        # SECURITY FIX 22-2: Row Lock + Access-Check in einer atomaren Query
        result = await db.execute(
            select(PrivatEmergencyAccessRequest, PrivatSpace)
            .join(PrivatSpace, PrivatEmergencyAccessRequest.space_id == PrivatSpace.id)
            .where(PrivatEmergencyAccessRequest.id == request_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Notfallzugriff!
        )
        row = result.first()
        if not row:
            return None

        request, space = row

        # SECURITY FIX 22-2: Nur Space-Owner darf genehmigen!
        if space.owner_id != approved_by:
            logger.warning(
                "emergency_approve_unauthorized",
                request_id=str(request_id),
                user_id=str(approved_by),
                owner_id=str(space.owner_id),
            )
            return None

        if request.status != PrivatEmergencyAccessStatus.PENDING.value:
            raise ValueError("Anfrage ist nicht mehr ausstehend")

        request.status = PrivatEmergencyAccessStatus.APPROVED.value
        request.approved_at = datetime.utcnow()

        await db.commit()
        await db.refresh(request)

        # SECURITY FIX 22-15: Audit-Log fuer Notfallzugriff
        logger.info(
            "privat_emergency_access_approved",
            request_id=str(request_id),
            approved_by=str(approved_by),
            space_id=str(space.id),
            audit_event="emergency_access_approved",
        )

        return request

    async def deny_request(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        denied_by: uuid.UUID,
        reason: str,
    ) -> Optional[PrivatEmergencyAccessRequest]:
        """Lehnt eine Anfrage ab (durch Owner).

        SECURITY FIX 22-2: Row Lock und Access-Check um TOCTOU Race Conditions
        und IDOR zu verhindern.
        SECURITY FIX 22-8: Input Validation fuer reason.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID
            denied_by: ID des ablehnenden Benutzers (MUSS Space-Owner sein)
            reason: Ablehnungsgrund (min 3, max 1000 Zeichen)

        Returns:
            Aktualisierte Anfrage
        """
        # SECURITY FIX 22-8: Input Validation fuer reason
        if not reason or len(reason.strip()) < 3:
            raise ValueError("Ablehnungsgrund muss mindestens 3 Zeichen haben")
        if len(reason) > 1000:
            raise ValueError("Ablehnungsgrund darf maximal 1000 Zeichen haben")

        # SECURITY FIX 22-2: Row Lock + Access-Check in einer atomaren Query
        result = await db.execute(
            select(PrivatEmergencyAccessRequest, PrivatSpace)
            .join(PrivatSpace, PrivatEmergencyAccessRequest.space_id == PrivatSpace.id)
            .where(PrivatEmergencyAccessRequest.id == request_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Notfallzugriff!
        )
        row = result.first()
        if not row:
            return None

        request, space = row

        # SECURITY FIX 22-2: Nur Space-Owner darf ablehnen!
        if space.owner_id != denied_by:
            logger.warning(
                "emergency_deny_unauthorized",
                request_id=str(request_id),
                user_id=str(denied_by),
                owner_id=str(space.owner_id),
            )
            return None

        if request.status != PrivatEmergencyAccessStatus.PENDING.value:
            raise ValueError("Anfrage ist nicht mehr ausstehend")

        request.status = PrivatEmergencyAccessStatus.DENIED.value
        request.denied_at = datetime.utcnow()
        request.denied_reason = reason.strip()

        await db.commit()
        await db.refresh(request)

        # SECURITY FIX 22-15: Audit-Log fuer Notfallzugriff
        logger.info(
            "privat_emergency_access_denied",
            request_id=str(request_id),
            denied_by=str(denied_by),
            space_id=str(space.id),
            audit_event="emergency_access_denied",
        )

        return request

    async def process_expired_requests(
        self,
        db: AsyncSession,
    ) -> List[PrivatEmergencyAccessRequest]:
        """Verarbeitet abgelaufene Anfragen (Wartezeit vorbei).

        Diese Methode sollte regelmaessig durch einen Celery Task
        aufgerufen werden.

        Returns:
            Liste von genehmigten Anfragen
        """
        now = datetime.utcnow()

        # SECURITY: FOR UPDATE mit skip_locked verhindert Race Conditions
        # bei parallelen Celery-Workers die gleiche Requests verarbeiten koennten
        result = await db.execute(
            select(PrivatEmergencyAccessRequest)
            .where(
                PrivatEmergencyAccessRequest.status == PrivatEmergencyAccessStatus.PENDING.value,
                PrivatEmergencyAccessRequest.waiting_until <= now,
            )
            .with_for_update(skip_locked=True)
        )

        requests = result.scalars().all()
        approved = []

        for request in requests:
            request.status = PrivatEmergencyAccessStatus.APPROVED.value
            request.approved_at = now
            approved.append(request)

            logger.info(
                "privat_emergency_access_auto_approved",
                request_id=str(request.id),
                space_id=str(request.space_id),
            )

            # SECURITY: Benachrichtigung an Kontakt nach Auto-Approval
            await self._notify_contact_approved(db, request)

        await db.commit()
        return approved

    async def check_emergency_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        contact_email: str,
    ) -> bool:
        """Prueft ob ein Kontakt Notfallzugriff auf einen Space hat.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            contact_email: E-Mail des Kontakts

        Returns:
            True wenn Zugriff gewaehrt
        """
        contact = await self.get_contact_by_email(db, space_id, contact_email)
        if not contact:
            return False

        result = await db.execute(
            select(PrivatEmergencyAccessRequest)
            .where(
                PrivatEmergencyAccessRequest.space_id == space_id,
                PrivatEmergencyAccessRequest.contact_id == contact.id,
                PrivatEmergencyAccessRequest.status == PrivatEmergencyAccessStatus.APPROVED.value,
            )
        )

        return result.scalar_one_or_none() is not None

    async def revoke_emergency_access(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
    ) -> bool:
        """Widerruft einen genehmigten Notfallzugriff.

        Args:
            db: Datenbank-Session
            request_id: Anfrage-ID

        Returns:
            True wenn erfolgreich
        """
        # SECURITY FIX 24-5: Row Lock fuer atomare Status-Aenderung (TOCTOU Prevention)
        result = await db.execute(
            select(PrivatEmergencyAccessRequest)
            .where(PrivatEmergencyAccessRequest.id == request_id)
            .with_for_update()  # SECURITY: Exclusive Row Lock - CWE-367 Prevention
        )
        request = result.scalar_one_or_none()
        if not request:
            return False

        if request.status != PrivatEmergencyAccessStatus.APPROVED.value:
            return False

        request.status = PrivatEmergencyAccessStatus.EXPIRED.value

        await db.commit()

        logger.info(
            "privat_emergency_access_revoked",
            request_id=str(request_id),
        )

        return True

    # ========== Notification Methods (Enterprise Feature) ==========

    async def _notify_owner_access_requested(
        self,
        db: AsyncSession,
        request: PrivatEmergencyAccessRequest,
        contact: PrivatEmergencyContact,
    ) -> None:
        """Benachrichtigt den Space-Owner ueber eine Notfallzugriff-Anfrage.

        SECURITY: Enterprise Requirement - Owner MUSS informiert werden,
        damit er die Anfrage ggf. widerrufen kann.

        Args:
            db: Datenbank-Session
            request: Die Zugriffsanfrage
            contact: Der anfragende Kontakt
        """
        try:
            # Hole Space und Owner
            space_result = await db.execute(
                select(PrivatSpace).where(PrivatSpace.id == request.space_id)
            )
            space = space_result.scalar_one_or_none()
            if not space:
                logger.warning(
                    "privat_notification_failed_no_space",
                    request_id=str(request.id),
                )
                return

            # Hole Owner-Details
            owner_result = await db.execute(
                select(User).where(User.id == space.owner_id)
            )
            owner = owner_result.scalar_one_or_none()
            if not owner or not owner.email:
                logger.warning(
                    "privat_notification_failed_no_owner_email",
                    request_id=str(request.id),
                    space_id=str(space.id),
                )
                return

            # Sende Benachrichtigung
            notification_service = get_notification_service()
            await notification_service.send_email(
                to_email=owner.email,
                subject="Notfallzugriff angefordert - Aktion erforderlich",
                template_name="emergency_access_request",
                context={
                    "owner_name": owner.full_name or owner.email,
                    "space_name": space.name,
                    "contact_name": f"{contact.first_name} {contact.last_name}",
                    "contact_email": contact.email,
                    "contact_relationship": contact.relationship or "Nicht angegeben",
                    "reason": request.reason,
                    "waiting_until": request.waiting_until.strftime("%d.%m.%Y %H:%M UTC"),
                    "waiting_days": contact.waiting_period_days,
                    "request_id": str(request.id),
                },
            )

            logger.info(
                "privat_emergency_access_owner_notified",
                request_id=str(request.id),
                owner_email=owner.email,
            )

        except Exception as e:
            # Notification-Fehler sollten den Workflow nicht stoppen,
            # aber geloggt werden fuer Monitoring
            logger.error(
                "privat_emergency_notification_failed",
                request_id=str(request.id),
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _notify_contact_approved(
        self,
        db: AsyncSession,
        request: PrivatEmergencyAccessRequest,
    ) -> None:
        """Benachrichtigt den Kontakt nach automatischer Genehmigung.

        Args:
            db: Datenbank-Session
            request: Die genehmigte Anfrage
        """
        try:
            # Hole Contact
            contact = await self.get_contact(db, request.contact_id)
            if not contact:
                return

            # Hole Space
            space_result = await db.execute(
                select(PrivatSpace).where(PrivatSpace.id == request.space_id)
            )
            space = space_result.scalar_one_or_none()
            if not space:
                return

            # Sende Benachrichtigung
            notification_service = get_notification_service()
            await notification_service.send_email(
                to_email=contact.email,
                subject="Notfallzugriff genehmigt",
                template_name="emergency_access_approved",
                context={
                    "contact_name": f"{contact.first_name} {contact.last_name}",
                    "space_name": space.name,
                    "approved_at": request.approved_at.strftime("%d.%m.%Y %H:%M UTC") if request.approved_at else "Jetzt",
                    "request_id": str(request.id),
                },
            )

            logger.info(
                "privat_emergency_access_contact_notified",
                request_id=str(request.id),
                contact_email=contact.email,
            )

        except Exception as e:
            logger.error(
                "privat_emergency_contact_notification_failed",
                request_id=str(request.id),
                error=str(e),
            )
