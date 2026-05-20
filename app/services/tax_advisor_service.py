"""GoBD Steuerberater-Zugang Service.

Verwaltet zeitlich begrenzte Zugaenge für Steuerberater und Prüfer:
- Einladungen erstellen und versenden
- Einladungen akzeptieren (Benutzer erstellen)
- Zugriffsrechte verwalten
- Aktivitäten protokollieren

GoBD-Konformität:
- Nachvollziehbarkeit: Alle Aktionen werden protokolliert
- Zeitliche Begrenzung: Zugang laeuft automatisch ab
- Eingeschraenkter Zugriff: Nur Lesezugriff auf relevante Dokumente
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

import structlog
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import (
    User,
    Role,
    Company,
    TaxAdvisorInvite,
    TaxAdvisorAccessLog,
    TaxAdvisorInviteStatus,
)
from app.core.security import get_password_hash

logger = structlog.get_logger(__name__)


class TaxAdvisorService:
    """Service für Steuerberater-Zugang und -Verwaltung."""

    # Konstanten
    TOKEN_LENGTH = 64  # Bytes für secure token
    TOKEN_EXPIRY_DAYS = 7  # Tage bis Invite ablaeuft
    DEFAULT_ACCESS_DAYS = 30  # Standard-Zugang in Tagen

    async def create_invite(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        email: str,
        invited_by: User,
        full_name: Optional[str] = None,
        tax_firm_name: Optional[str] = None,
        tax_advisor_id: Optional[str] = None,
        access_duration_days: int = DEFAULT_ACCESS_DAYS,
        access_scope: Optional[Dict[str, Any]] = None,
    ) -> tuple[TaxAdvisorInvite, str]:
        """Erstellt eine neue Steuerberater-Einladung.

        Args:
            db: Database Session
            company_id: Firma, für die der Zugang gilt
            email: E-Mail des Steuerberaters
            invited_by: Einladender Benutzer (Admin)
            full_name: Optionaler Name des Steuerberaters
            tax_firm_name: Optionaler Name der Steuerkanzlei
            tax_advisor_id: Optionale Steuerberater-ID der Kammer
            access_duration_days: Zugang in Tagen (Standard: 30)
            access_scope: Optionale Zugriffsbeschraenkungen

        Returns:
            Tuple aus TaxAdvisorInvite und dem Klartext-Token (für E-Mail)

        Raises:
            ValueError: Bei ungültigem company_id oder wenn bereits eine
                       aktive Einladung für diese E-Mail existiert
        """
        # Prüfen ob Company existiert
        company = await db.get(Company, company_id)
        if not company:
            raise ValueError(f"Firma mit ID {company_id} nicht gefunden")

        # Prüfen ob bereits eine aktive Einladung existiert
        existing = await db.execute(
            select(TaxAdvisorInvite).where(
                and_(
                    TaxAdvisorInvite.email == email.lower(),
                    TaxAdvisorInvite.company_id == company_id,
                    TaxAdvisorInvite.status == TaxAdvisorInviteStatus.PENDING.value,
                    TaxAdvisorInvite.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Es existiert bereits eine aktive Einladung für {email}"
            )

        # Token generieren
        token = secrets.token_urlsafe(self.TOKEN_LENGTH)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Einladung erstellen
        invite = TaxAdvisorInvite(
            id=uuid.uuid4(),
            token_hash=token_hash,
            company_id=company_id,
            invited_by_id=invited_by.id,
            email=email.lower(),
            full_name=full_name,
            tax_firm_name=tax_firm_name,
            tax_advisor_id=tax_advisor_id,
            access_duration_days=access_duration_days,
            access_scope=access_scope,
            status=TaxAdvisorInviteStatus.PENDING.value,
            expires_at=datetime.now(timezone.utc) + timedelta(days=self.TOKEN_EXPIRY_DAYS),
        )

        db.add(invite)
        await db.commit()
        await db.refresh(invite)

        logger.info(
            "tax_advisor_invite_created",
            invite_id=str(invite.id),
            email=email,
            company_id=str(company_id),
            invited_by=str(invited_by.id),
            access_days=access_duration_days
        )

        return invite, token

    async def accept_invite(
        self,
        db: AsyncSession,
        token: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> User:
        """Akzeptiert eine Einladung und erstellt den Steuerberater-Benutzer.

        Args:
            db: Database Session
            token: Klartext-Token aus der Einladung
            password: Gewaehltes Passwort des Steuerberaters
            ip_address: IP-Adresse für Audit
            user_agent: User-Agent für Audit

        Returns:
            Erstellter User mit tax_advisor Rolle

        Raises:
            ValueError: Bei ungültigem oder abgelaufenem Token
        """
        # Token hashen und Einladung suchen
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # SECURITY FIX: Pessimistic Lock verhindert Race Condition
        # SELECT ... FOR UPDATE sperrt die Zeile bis zum Commit/Rollback
        # Dies verhindert, dass parallele Requests dasselbe Token verwenden
        result = await db.execute(
            select(TaxAdvisorInvite)
            .options(joinedload(TaxAdvisorInvite.company))
            .where(TaxAdvisorInvite.token_hash == token_hash)
            .with_for_update(nowait=False)  # Wartet auf Lock statt Fehler
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise ValueError("Ungültige Einladung")

        if invite.status != TaxAdvisorInviteStatus.PENDING.value:
            raise ValueError(
                f"Diese Einladung wurde bereits {invite.status}"
            )

        if invite.expires_at < datetime.now(timezone.utc):
            # Status auf expired setzen
            invite.status = TaxAdvisorInviteStatus.EXPIRED.value
            await db.commit()
            raise ValueError("Diese Einladung ist abgelaufen")

        # Prüfen ob E-Mail bereits verwendet wird
        existing_user = await db.execute(
            select(User).where(User.email == invite.email)
        )
        if existing_user.scalar_one_or_none():
            raise ValueError(
                f"Ein Benutzer mit der E-Mail {invite.email} existiert bereits"
            )

        # tax_advisor Rolle laden
        role_result = await db.execute(
            select(Role).where(Role.name == "tax_advisor")
        )
        tax_advisor_role = role_result.scalar_one_or_none()
        if not tax_advisor_role:
            raise ValueError(
                "tax_advisor Rolle nicht gefunden. Bitte Migration ausführen."
            )

        # Benutzer erstellen
        access_until = datetime.now(timezone.utc) + timedelta(
            days=invite.access_duration_days
        )

        user = User(
            id=uuid.uuid4(),
            email=invite.email,
            username=self._generate_username(invite.email),
            hashed_password=get_password_hash(password),
            full_name=invite.full_name,
            is_active=True,
            is_superuser=False,
            preferred_language="de",
            access_until=access_until,
            invited_by_id=invite.invited_by_id,
            invited_at=datetime.now(timezone.utc),
            access_scope=invite.access_scope,
            email_verified=True,  # Per Einladung verifiziert
            email_verified_at=datetime.now(timezone.utc),
        )

        # Rolle zuweisen
        user.roles.append(tax_advisor_role)
        db.add(user)

        # Einladung aktualisieren
        invite.status = TaxAdvisorInviteStatus.ACCEPTED.value
        invite.accepted_at = datetime.now(timezone.utc)
        invite.accepted_user_id = user.id

        await db.commit()
        await db.refresh(user)

        # Audit-Log erstellen
        await self.log_access(
            db=db,
            user_id=user.id,
            company_id=invite.company_id,
            action="account_created",
            resource_type="user",
            resource_id=user.id,
            details={
                "invite_id": str(invite.id),
                "access_until": access_until.isoformat(),
                "access_duration_days": invite.access_duration_days,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info(
            "tax_advisor_account_created",
            user_id=str(user.id),
            invite_id=str(invite.id),
            company_id=str(invite.company_id),
            access_until=access_until.isoformat()
        )

        return user

    async def revoke_invite(
        self,
        db: AsyncSession,
        invite_id: uuid.UUID,
        revoked_by: User,
    ) -> TaxAdvisorInvite:
        """Widerruft eine ausstehende Einladung.

        Args:
            db: Database Session
            invite_id: ID der Einladung
            revoked_by: Benutzer, der die Einladung widerruft

        Returns:
            Aktualisierte Einladung

        Raises:
            ValueError: Wenn Einladung nicht gefunden oder bereits akzeptiert
        """
        invite = await db.get(TaxAdvisorInvite, invite_id)
        if not invite:
            raise ValueError(f"Einladung {invite_id} nicht gefunden")

        if invite.status != TaxAdvisorInviteStatus.PENDING.value:
            raise ValueError(
                f"Einladung kann nicht widerrufen werden (Status: {invite.status})"
            )

        invite.status = TaxAdvisorInviteStatus.REVOKED.value
        await db.commit()
        await db.refresh(invite)

        logger.info(
            "tax_advisor_invite_revoked",
            invite_id=str(invite_id),
            revoked_by=str(revoked_by.id)
        )

        return invite

    async def extend_access(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        additional_days: int,
        extended_by: User,
    ) -> User:
        """Verlängert den Zugang eines Steuerberaters.

        Args:
            db: Database Session
            user_id: ID des Steuerberaters
            additional_days: Zusätzliche Tage
            extended_by: Admin, der den Zugang verlängert

        Returns:
            Aktualisierter User
        """
        user = await db.get(User, user_id)
        if not user:
            raise ValueError(f"Benutzer {user_id} nicht gefunden")

        if not user.access_until:
            raise ValueError(
                "Dieser Benutzer hat keinen zeitlich begrenzten Zugang"
            )

        old_access_until = user.access_until
        # Wenn Zugang bereits abgelaufen, von jetzt rechnen
        base_date = max(old_access_until, datetime.now(timezone.utc))
        user.access_until = base_date + timedelta(days=additional_days)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "tax_advisor_access_extended",
            user_id=str(user_id),
            extended_by=str(extended_by.id),
            old_access_until=old_access_until.isoformat(),
            new_access_until=user.access_until.isoformat(),
            additional_days=additional_days
        )

        return user

    async def revoke_access(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        revoked_by: User,
        reason: Optional[str] = None,
    ) -> User:
        """Widerruft den Zugang eines Steuerberaters sofort.

        Args:
            db: Database Session
            user_id: ID des Steuerberaters
            revoked_by: Admin, der den Zugang widerruft
            reason: Optionaler Grund

        Returns:
            Aktualisierter User
        """
        user = await db.get(User, user_id)
        if not user:
            raise ValueError(f"Benutzer {user_id} nicht gefunden")

        user.access_until = datetime.now(timezone.utc)
        user.is_active = False
        user.deactivated_at = datetime.now(timezone.utc)
        user.deactivated_by_id = revoked_by.id
        user.notes = f"Zugang widerrufen: {reason}" if reason else "Zugang widerrufen"

        await db.commit()
        await db.refresh(user)

        logger.warning(
            "tax_advisor_access_revoked",
            user_id=str(user_id),
            revoked_by=str(revoked_by.id),
            reason=reason
        )

        return user

    async def log_access(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: Optional[uuid.UUID] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> TaxAdvisorAccessLog:
        """Protokolliert eine Steuerberater-Aktion.

        Args:
            db: Database Session
            user_id: ID des Steuerberaters
            company_id: Firma auf die zugegriffen wurde
            action: Aktionstyp (document_view, archive_export, etc.)
            resource_type: Ressourcentyp (document, archive, procedure_doc)
            resource_id: Optionale Ressourcen-ID
            details: Optionale Zusatzinfos
            ip_address: IP-Adresse
            user_agent: User-Agent

        Returns:
            Erstellter Log-Eintrag
        """
        log = TaxAdvisorAccessLog(
            id=uuid.uuid4(),
            user_id=user_id,
            company_id=company_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.add(log)
        await db.commit()
        await db.refresh(log)

        return log

    async def get_access_logs(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaxAdvisorAccessLog]:
        """Ruft Zugriffslogs ab.

        Args:
            db: Database Session
            company_id: Firma
            user_id: Optionaler Filter nach Benutzer
            action: Optionaler Filter nach Aktion
            from_date: Optionales Start-Datum
            to_date: Optionales End-Datum
            limit: Max. Ergebnisse
            offset: Offset für Paginierung

        Returns:
            Liste der Log-Einträge
        """
        query = select(TaxAdvisorAccessLog).where(
            TaxAdvisorAccessLog.company_id == company_id
        )

        if user_id:
            query = query.where(TaxAdvisorAccessLog.user_id == user_id)
        if action:
            query = query.where(TaxAdvisorAccessLog.action == action)
        if from_date:
            query = query.where(TaxAdvisorAccessLog.accessed_at >= from_date)
        if to_date:
            query = query.where(TaxAdvisorAccessLog.accessed_at <= to_date)

        query = query.order_by(TaxAdvisorAccessLog.accessed_at.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_pending_invites(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[TaxAdvisorInvite]:
        """Ruft ausstehende Einladungen für eine Firma ab."""
        result = await db.execute(
            select(TaxAdvisorInvite)
            .where(
                and_(
                    TaxAdvisorInvite.company_id == company_id,
                    TaxAdvisorInvite.status == TaxAdvisorInviteStatus.PENDING.value,
                    TaxAdvisorInvite.expires_at > datetime.now(timezone.utc)
                )
            )
            .order_by(TaxAdvisorInvite.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_active_tax_advisors(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[User]:
        """Ruft aktive Steuerberater für eine Firma ab."""
        # Benutzer mit tax_advisor Rolle und aktivem Zugang
        result = await db.execute(
            select(User)
            .join(User.roles)
            .where(
                and_(
                    Role.name == "tax_advisor",
                    User.is_active == True,
                    or_(
                        User.access_until == None,
                        User.access_until > datetime.now(timezone.utc)
                    )
                )
            )
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def cleanup_expired_invites(
        self,
        db: AsyncSession,
    ) -> int:
        """Markiert abgelaufene Einladungen als expired.

        Returns:
            Anzahl aktualisierter Einladungen
        """
        result = await db.execute(
            update(TaxAdvisorInvite)
            .where(
                and_(
                    TaxAdvisorInvite.status == TaxAdvisorInviteStatus.PENDING.value,
                    TaxAdvisorInvite.expires_at < datetime.now(timezone.utc)
                )
            )
            .values(status=TaxAdvisorInviteStatus.EXPIRED.value)
        )
        await db.commit()

        count = result.rowcount
        if count > 0:
            logger.info("expired_invites_cleaned_up", count=count)

        return count

    async def deactivate_expired_access(
        self,
        db: AsyncSession,
    ) -> int:
        """Deaktiviert Benutzer mit abgelaufenem Zugang.

        Returns:
            Anzahl deaktivierter Benutzer
        """
        result = await db.execute(
            update(User)
            .where(
                and_(
                    User.access_until != None,
                    User.access_until < datetime.now(timezone.utc),
                    User.is_active == True
                )
            )
            .values(
                is_active=False,
                deactivated_at=datetime.now(timezone.utc),
                notes="Automatisch deaktiviert: Zugang abgelaufen"
            )
        )
        await db.commit()

        count = result.rowcount
        if count > 0:
            logger.info("expired_access_deactivated", count=count)

        return count

    def _generate_username(self, email: str) -> str:
        """Generiert einen Benutzernamen aus der E-Mail."""
        # Nimmt den Teil vor dem @
        base = email.split("@")[0].lower()
        # Entfernt Sonderzeichen
        base = "".join(c for c in base if c.isalnum() or c in "._-")
        # Fuegt Suffix hinzu für Eindeutigkeit
        suffix = secrets.token_hex(4)
        return f"ta_{base}_{suffix}"


# Singleton-Instanz
tax_advisor_service = TaxAdvisorService()
