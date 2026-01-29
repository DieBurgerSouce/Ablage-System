# -*- coding: utf-8 -*-
"""
Consent Management Service.

Verwaltung von Einwilligungen nach DSGVO:
- Einwilligungen erfassen und verwalten
- Widerruf verarbeiten
- Audit-Trail fuehren
- Ablauf-Benachrichtigungen

Feinpoliert und durchdacht.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_consent import (
    ConsentRecord,
    DataProcessingAgreement,
    ConsentAuditLog,
    RetentionPolicy,
    ConsentStatus,
    ConsentType,
    ConsentSource,
    LegalBasis,
    AuditAction,
)

logger = logging.getLogger(__name__)


class ConsentService:
    """
    Service fuer Einwilligungsverwaltung.

    Unterstuetzt alle DSGVO-Anforderungen fuer Consent Management.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Service.

        Args:
            db: AsyncSession fuer Datenbankzugriff
        """
        self.db = db

    # =========================================================================
    # Consent CRUD
    # =========================================================================

    async def request_consent(
        self,
        company_id: UUID,
        consent_type: str,
        entity_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        grantor_name: Optional[str] = None,
        grantor_email: Optional[str] = None,
        scope: Optional[Dict] = None,
        expires_at: Optional[datetime] = None,
        source: str = ConsentSource.WEB_FORM.value,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentRecord:
        """
        Erstelle neue Einwilligungsanfrage.

        Args:
            company_id: Mandanten-ID
            consent_type: Typ der Einwilligung
            entity_id: Optional - betroffene Entity
            user_id: Optional - betroffener User
            grantor_name: Name des Einwilligenden
            grantor_email: E-Mail fuer Kommunikation
            scope: Umfang der Einwilligung
            expires_at: Ablaufdatum
            source: Quelle der Anfrage
            ip_address: IP-Adresse
            user_agent: Browser User-Agent

        Returns:
            Erstellte ConsentRecord
        """
        consent = ConsentRecord(
            company_id=company_id,
            entity_id=entity_id,
            user_id=user_id,
            consent_type=consent_type,
            status=ConsentStatus.PENDING.value,
            grantor_name=grantor_name,
            grantor_email=grantor_email,
            scope=scope or {},
            expires_at=expires_at,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.add(consent)
        await self.db.flush()

        # Audit-Log erstellen
        await self._create_audit_log(
            consent_record_id=consent.id,
            company_id=company_id,
            action=AuditAction.REQUESTED.value,
            new_value=consent.to_dict(),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info(
            f"Consent requested: {consent_type} for entity={entity_id}, user={user_id}"
        )

        return consent

    async def grant_consent(
        self,
        consent_id: UUID,
        granted_by_id: Optional[UUID] = None,
        grantor_name: Optional[str] = None,
        grantor_role: Optional[str] = None,
        conditions: Optional[str] = None,
        restrictions: Optional[List] = None,
        document_id: Optional[UUID] = None,
        document_reference: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[ConsentRecord]:
        """
        Erteile Einwilligung.

        Args:
            consent_id: ID der Einwilligung
            granted_by_id: User der erteilt
            grantor_name: Name des Erteilenden
            grantor_role: Rolle/Position
            conditions: Textuelle Bedingungen
            restrictions: Einschraenkungen
            document_id: Verweis auf Dokument
            document_reference: Textuelle Referenz
            ip_address: IP-Adresse
            user_agent: Browser User-Agent

        Returns:
            Aktualisierte ConsentRecord oder None
        """
        result = await self.db.execute(
            select(ConsentRecord).where(ConsentRecord.id == consent_id)
        )
        consent = result.scalar_one_or_none()

        if not consent:
            return None

        old_value = consent.to_dict()

        consent.status = ConsentStatus.GRANTED.value
        consent.granted_at = datetime.utcnow()
        consent.grantor_name = grantor_name or consent.grantor_name
        consent.grantor_role = grantor_role
        consent.conditions = conditions
        consent.restrictions = restrictions or []
        consent.document_id = document_id
        consent.document_reference = document_reference

        await self.db.flush()

        # Audit-Log
        await self._create_audit_log(
            consent_record_id=consent.id,
            company_id=consent.company_id,
            action=AuditAction.GRANTED.value,
            performed_by_id=granted_by_id,
            performed_by_name=grantor_name,
            performed_by_role=grantor_role,
            old_value=old_value,
            new_value=consent.to_dict(),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info(f"Consent granted: {consent.consent_type}, id={consent_id}")

        return consent

    async def deny_consent(
        self,
        consent_id: UUID,
        denied_by_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[ConsentRecord]:
        """
        Verweigere Einwilligung.

        Args:
            consent_id: ID der Einwilligung
            denied_by_id: User der verweigert
            reason: Begruendung
            ip_address: IP-Adresse

        Returns:
            Aktualisierte ConsentRecord oder None
        """
        result = await self.db.execute(
            select(ConsentRecord).where(ConsentRecord.id == consent_id)
        )
        consent = result.scalar_one_or_none()

        if not consent:
            return None

        old_value = consent.to_dict()

        consent.status = ConsentStatus.DENIED.value
        consent.denied_at = datetime.utcnow()
        consent.notes = reason

        await self.db.flush()

        # Audit-Log
        await self._create_audit_log(
            consent_record_id=consent.id,
            company_id=consent.company_id,
            action=AuditAction.DENIED.value,
            performed_by_id=denied_by_id,
            old_value=old_value,
            new_value=consent.to_dict(),
            reason=reason,
            ip_address=ip_address,
        )

        logger.info(f"Consent denied: {consent.consent_type}, id={consent_id}")

        return consent

    async def withdraw_consent(
        self,
        consent_id: UUID,
        withdrawn_by_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        method: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[ConsentRecord]:
        """
        Widerrufe Einwilligung.

        Args:
            consent_id: ID der Einwilligung
            withdrawn_by_id: User der widerruft
            reason: Widerrufsgrund
            method: Widerrufsmethode
            ip_address: IP-Adresse

        Returns:
            Aktualisierte ConsentRecord oder None
        """
        result = await self.db.execute(
            select(ConsentRecord).where(ConsentRecord.id == consent_id)
        )
        consent = result.scalar_one_or_none()

        if not consent:
            return None

        if consent.status != ConsentStatus.GRANTED.value:
            logger.warning(f"Cannot withdraw non-granted consent: {consent_id}")
            return None

        old_value = consent.to_dict()

        consent.status = ConsentStatus.WITHDRAWN.value
        consent.withdrawn_at = datetime.utcnow()
        consent.withdrawal_reason = reason
        consent.withdrawal_method = method

        await self.db.flush()

        # Audit-Log
        await self._create_audit_log(
            consent_record_id=consent.id,
            company_id=consent.company_id,
            action=AuditAction.WITHDRAWN.value,
            performed_by_id=withdrawn_by_id,
            old_value=old_value,
            new_value=consent.to_dict(),
            reason=reason,
            ip_address=ip_address,
        )

        logger.info(f"Consent withdrawn: {consent.consent_type}, id={consent_id}")

        return consent

    async def get_consent(
        self,
        consent_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[ConsentRecord]:
        """
        Einzelne Einwilligung abrufen.

        Args:
            consent_id: ID der Einwilligung
            company_id: Optional - Mandanten-Filter

        Returns:
            ConsentRecord oder None
        """
        query = select(ConsentRecord).where(ConsentRecord.id == consent_id)

        if company_id:
            query = query.where(ConsentRecord.company_id == company_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_consents(
        self,
        company_id: UUID,
        entity_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        consent_type: Optional[str] = None,
        status: Optional[str] = None,
        only_valid: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[ConsentRecord], int]:
        """
        Liste Einwilligungen mit Filteroptionen.

        Args:
            company_id: Mandanten-ID
            entity_id: Filter nach Entity
            user_id: Filter nach User
            consent_type: Filter nach Typ
            status: Filter nach Status
            only_valid: Nur gueltige
            offset: Pagination
            limit: Pagination

        Returns:
            Tuple aus Liste und Gesamtanzahl
        """
        query = select(ConsentRecord).where(ConsentRecord.company_id == company_id)
        count_query = select(func.count(ConsentRecord.id)).where(
            ConsentRecord.company_id == company_id
        )

        filters = []

        if entity_id:
            filters.append(ConsentRecord.entity_id == entity_id)
        if user_id:
            filters.append(ConsentRecord.user_id == user_id)
        if consent_type:
            filters.append(ConsentRecord.consent_type == consent_type)
        if status:
            filters.append(ConsentRecord.status == status)
        if only_valid:
            filters.append(ConsentRecord.status == ConsentStatus.GRANTED.value)
            filters.append(
                or_(
                    ConsentRecord.expires_at.is_(None),
                    ConsentRecord.expires_at > datetime.utcnow()
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Zaehlen
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginieren
        query = query.order_by(desc(ConsentRecord.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    async def check_consent(
        self,
        company_id: UUID,
        consent_type: str,
        entity_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Pruefe ob gueltige Einwilligung vorliegt.

        Args:
            company_id: Mandanten-ID
            consent_type: Typ der Einwilligung
            entity_id: Betroffene Entity
            user_id: Betroffener User

        Returns:
            True wenn gueltige Einwilligung vorliegt
        """
        query = select(ConsentRecord).where(
            and_(
                ConsentRecord.company_id == company_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.status == ConsentStatus.GRANTED.value,
                or_(
                    ConsentRecord.expires_at.is_(None),
                    ConsentRecord.expires_at > datetime.utcnow()
                )
            )
        )

        if entity_id:
            query = query.where(ConsentRecord.entity_id == entity_id)
        if user_id:
            query = query.where(ConsentRecord.user_id == user_id)

        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none() is not None

    async def get_expiring_consents(
        self,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> List[ConsentRecord]:
        """
        Hole bald ablaufende Einwilligungen.

        Args:
            company_id: Mandanten-ID
            days_ahead: Tage voraus

        Returns:
            Liste ablaufender Einwilligungen
        """
        threshold = datetime.utcnow() + timedelta(days=days_ahead)

        result = await self.db.execute(
            select(ConsentRecord)
            .where(
                and_(
                    ConsentRecord.company_id == company_id,
                    ConsentRecord.status == ConsentStatus.GRANTED.value,
                    ConsentRecord.expires_at.isnot(None),
                    ConsentRecord.expires_at <= threshold,
                    ConsentRecord.expires_at > datetime.utcnow(),
                )
            )
            .order_by(ConsentRecord.expires_at)
        )

        return list(result.scalars().all())

    async def expire_consents(self, company_id: UUID) -> int:
        """
        Markiere abgelaufene Einwilligungen.

        Args:
            company_id: Mandanten-ID

        Returns:
            Anzahl markierter Einwilligungen
        """
        result = await self.db.execute(
            select(ConsentRecord)
            .where(
                and_(
                    ConsentRecord.company_id == company_id,
                    ConsentRecord.status == ConsentStatus.GRANTED.value,
                    ConsentRecord.expires_at.isnot(None),
                    ConsentRecord.expires_at <= datetime.utcnow(),
                )
            )
        )

        consents = list(result.scalars().all())

        for consent in consents:
            old_value = consent.to_dict()
            consent.status = ConsentStatus.EXPIRED.value

            await self._create_audit_log(
                consent_record_id=consent.id,
                company_id=company_id,
                action=AuditAction.EXPIRED.value,
                old_value=old_value,
                new_value=consent.to_dict(),
            )

        await self.db.flush()

        if consents:
            logger.info(f"Expired {len(consents)} consents for company {company_id}")

        return len(consents)

    # =========================================================================
    # Data Processing Agreements (AVV)
    # =========================================================================

    async def create_dpa(
        self,
        company_id: UUID,
        controller_name: str,
        processor_name: str,
        title: str,
        effective_date: datetime,
        expiration_date: Optional[datetime] = None,
        processor_entity_id: Optional[UUID] = None,
        subject_matter: Optional[str] = None,
        processing_purposes: Optional[List] = None,
        data_categories: Optional[List] = None,
        data_subjects: Optional[List] = None,
        subprocessor_allowed: bool = False,
        international_transfer: bool = False,
        **kwargs,
    ) -> DataProcessingAgreement:
        """
        Erstelle neuen Auftragsverarbeitungsvertrag.

        Args:
            company_id: Mandanten-ID
            controller_name: Name des Verantwortlichen
            processor_name: Name des Auftragsverarbeiters
            title: Titel des AVV
            effective_date: Wirksamkeitsdatum
            expiration_date: Ablaufdatum
            processor_entity_id: Entity des Verarbeiters
            subject_matter: Gegenstand der Verarbeitung
            processing_purposes: Zwecke
            data_categories: Datenkategorien
            data_subjects: Betroffenengruppen
            subprocessor_allowed: Subunternehmer erlaubt
            international_transfer: Internationale Uebermittlung
            **kwargs: Weitere Felder

        Returns:
            Erstellter DataProcessingAgreement
        """
        dpa = DataProcessingAgreement(
            company_id=company_id,
            controller_name=controller_name,
            processor_name=processor_name,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            processor_entity_id=processor_entity_id,
            subject_matter=subject_matter,
            processing_purposes=processing_purposes or [],
            data_categories=data_categories or [],
            data_subjects=data_subjects or [],
            subprocessor_allowed=subprocessor_allowed,
            international_transfer=international_transfer,
            status="active",
            **kwargs,
        )

        self.db.add(dpa)
        await self.db.flush()

        logger.info(f"DPA created: {title} with {processor_name}")

        return dpa

    async def list_dpas(
        self,
        company_id: UUID,
        status: Optional[str] = None,
        only_active: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[DataProcessingAgreement], int]:
        """
        Liste Auftragsverarbeitungsvertraege.

        Args:
            company_id: Mandanten-ID
            status: Filter nach Status
            only_active: Nur aktive
            offset: Pagination
            limit: Pagination

        Returns:
            Tuple aus Liste und Gesamtanzahl
        """
        query = select(DataProcessingAgreement).where(
            DataProcessingAgreement.company_id == company_id
        )
        count_query = select(func.count(DataProcessingAgreement.id)).where(
            DataProcessingAgreement.company_id == company_id
        )

        if status:
            query = query.where(DataProcessingAgreement.status == status)
            count_query = count_query.where(DataProcessingAgreement.status == status)

        if only_active:
            query = query.where(DataProcessingAgreement.status == "active")
            count_query = count_query.where(DataProcessingAgreement.status == "active")

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        query = query.order_by(desc(DataProcessingAgreement.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    async def get_dpa(
        self,
        dpa_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[DataProcessingAgreement]:
        """
        Einzelnen AVV abrufen.

        Args:
            dpa_id: ID des AVV
            company_id: Optional - Mandanten-Filter

        Returns:
            DataProcessingAgreement oder None
        """
        query = select(DataProcessingAgreement).where(DataProcessingAgreement.id == dpa_id)

        if company_id:
            query = query.where(DataProcessingAgreement.company_id == company_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def terminate_dpa(
        self,
        dpa_id: UUID,
        reason: Optional[str] = None,
    ) -> Optional[DataProcessingAgreement]:
        """
        Kuendige AVV.

        Args:
            dpa_id: ID des AVV
            reason: Kuendigungsgrund

        Returns:
            Aktualisierter AVV oder None
        """
        result = await self.db.execute(
            select(DataProcessingAgreement).where(DataProcessingAgreement.id == dpa_id)
        )
        dpa = result.scalar_one_or_none()

        if not dpa:
            return None

        dpa.status = "terminated"
        dpa.terminated_at = datetime.utcnow()
        dpa.termination_reason = reason

        await self.db.flush()

        logger.info(f"DPA terminated: {dpa.title}")

        return dpa

    # =========================================================================
    # Retention Policies
    # =========================================================================

    async def create_retention_policy(
        self,
        company_id: UUID,
        name: str,
        retention_days: int,
        document_type: Optional[str] = None,
        data_category: Optional[str] = None,
        legal_basis: Optional[str] = None,
        action_after_expiry: str = "archive",
        notify_days_before: int = 30,
        notify_emails: Optional[List] = None,
        **kwargs,
    ) -> RetentionPolicy:
        """
        Erstelle neue Aufbewahrungsrichtlinie.

        Args:
            company_id: Mandanten-ID
            name: Name der Richtlinie
            retention_days: Aufbewahrungsdauer in Tagen
            document_type: Betroffener Dokumenttyp
            data_category: Betroffene Datenkategorie
            legal_basis: Rechtsgrundlage
            action_after_expiry: Aktion nach Ablauf
            notify_days_before: Tage vor Ablauf benachrichtigen
            notify_emails: E-Mails fuer Benachrichtigung

        Returns:
            Erstellte RetentionPolicy
        """
        policy = RetentionPolicy(
            company_id=company_id,
            name=name,
            retention_days=retention_days,
            document_type=document_type,
            data_category=data_category,
            legal_basis=legal_basis,
            action_after_expiry=action_after_expiry,
            notify_days_before=notify_days_before,
            notify_emails=notify_emails or [],
            **kwargs,
        )

        self.db.add(policy)
        await self.db.flush()

        logger.info(f"Retention policy created: {name}, {retention_days} days")

        return policy

    async def list_retention_policies(
        self,
        company_id: UUID,
        only_active: bool = True,
    ) -> List[RetentionPolicy]:
        """
        Liste Aufbewahrungsrichtlinien.

        Args:
            company_id: Mandanten-ID
            only_active: Nur aktive

        Returns:
            Liste von Richtlinien
        """
        query = select(RetentionPolicy).where(RetentionPolicy.company_id == company_id)

        if only_active:
            query = query.where(RetentionPolicy.is_active == True)

        result = await self.db.execute(query.order_by(RetentionPolicy.name))
        return list(result.scalars().all())

    async def get_applicable_policy(
        self,
        company_id: UUID,
        document_type: Optional[str] = None,
        data_category: Optional[str] = None,
    ) -> Optional[RetentionPolicy]:
        """
        Finde anwendbare Aufbewahrungsrichtlinie.

        Args:
            company_id: Mandanten-ID
            document_type: Dokumenttyp
            data_category: Datenkategorie

        Returns:
            Anwendbare Richtlinie oder None
        """
        # Versuche spezifische Richtlinie zu finden
        query = select(RetentionPolicy).where(
            and_(
                RetentionPolicy.company_id == company_id,
                RetentionPolicy.is_active == True,
            )
        )

        # Prioritaet: Spezifisch vor Allgemein
        if document_type:
            result = await self.db.execute(
                query.where(RetentionPolicy.document_type == document_type).limit(1)
            )
            policy = result.scalar_one_or_none()
            if policy:
                return policy

        if data_category:
            result = await self.db.execute(
                query.where(RetentionPolicy.data_category == data_category).limit(1)
            )
            policy = result.scalar_one_or_none()
            if policy:
                return policy

        # Fallback: Allgemeine Richtlinie
        result = await self.db.execute(
            query.where(
                and_(
                    RetentionPolicy.document_type.is_(None),
                    RetentionPolicy.data_category.is_(None),
                )
            ).limit(1)
        )

        return result.scalar_one_or_none()

    # =========================================================================
    # Audit Trail
    # =========================================================================

    async def _create_audit_log(
        self,
        consent_record_id: UUID,
        company_id: UUID,
        action: str,
        performed_by_id: Optional[UUID] = None,
        performed_by_name: Optional[str] = None,
        performed_by_role: Optional[str] = None,
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentAuditLog:
        """
        Erstelle Audit-Log Eintrag.

        Args:
            consent_record_id: ID der Einwilligung
            company_id: Mandanten-ID
            action: Ausgefuehrte Aktion
            performed_by_id: User-ID
            performed_by_name: User-Name
            performed_by_role: User-Rolle
            old_value: Vorheriger Zustand
            new_value: Neuer Zustand
            reason: Begruendung
            ip_address: IP-Adresse
            user_agent: Browser User-Agent

        Returns:
            Erstellter ConsentAuditLog
        """
        # Berechne Aenderungen
        changes = {}
        if old_value and new_value:
            for key in set(old_value.keys()) | set(new_value.keys()):
                old_val = old_value.get(key)
                new_val = new_value.get(key)
                if old_val != new_val:
                    changes[key] = {"old": old_val, "new": new_val}

        log = ConsentAuditLog(
            consent_record_id=consent_record_id,
            company_id=company_id,
            action=action,
            performed_by_id=performed_by_id,
            performed_by_name=performed_by_name,
            performed_by_role=performed_by_role,
            old_value=old_value or {},
            new_value=new_value or {},
            changes=changes,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.add(log)
        return log

    async def get_audit_trail(
        self,
        consent_id: UUID,
    ) -> List[ConsentAuditLog]:
        """
        Hole Audit-Trail fuer eine Einwilligung.

        Args:
            consent_id: ID der Einwilligung

        Returns:
            Liste von Audit-Eintraegen
        """
        result = await self.db.execute(
            select(ConsentAuditLog)
            .where(ConsentAuditLog.consent_record_id == consent_id)
            .order_by(desc(ConsentAuditLog.performed_at))
        )

        return list(result.scalars().all())

    async def search_audit_logs(
        self,
        company_id: UUID,
        action: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ConsentAuditLog]:
        """
        Suche in Audit-Logs.

        Args:
            company_id: Mandanten-ID
            action: Filter nach Aktion
            date_from: Startdatum
            date_to: Enddatum
            limit: Maximale Anzahl

        Returns:
            Liste von Audit-Eintraegen
        """
        query = select(ConsentAuditLog).where(ConsentAuditLog.company_id == company_id)

        if action:
            query = query.where(ConsentAuditLog.action == action)
        if date_from:
            query = query.where(ConsentAuditLog.performed_at >= date_from)
        if date_to:
            query = query.where(ConsentAuditLog.performed_at <= date_to)

        query = query.order_by(desc(ConsentAuditLog.performed_at)).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_consent_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Hole Einwilligungs-Statistiken.

        Args:
            company_id: Mandanten-ID

        Returns:
            Statistik-Dictionary
        """
        # Nach Status
        status_result = await self.db.execute(
            select(
                ConsentRecord.status,
                func.count(ConsentRecord.id).label("count"),
            )
            .where(ConsentRecord.company_id == company_id)
            .group_by(ConsentRecord.status)
        )
        by_status = {row.status: row.count for row in status_result.all()}

        # Nach Typ
        type_result = await self.db.execute(
            select(
                ConsentRecord.consent_type,
                func.count(ConsentRecord.id).label("count"),
            )
            .where(
                and_(
                    ConsentRecord.company_id == company_id,
                    ConsentRecord.status == ConsentStatus.GRANTED.value,
                )
            )
            .group_by(ConsentRecord.consent_type)
        )
        by_type = {row.consent_type: row.count for row in type_result.all()}

        # Ablaufend in 30 Tagen
        expiring = await self.get_expiring_consents(company_id, days_ahead=30)

        # DPAs
        dpa_result = await self.db.execute(
            select(func.count(DataProcessingAgreement.id))
            .where(
                and_(
                    DataProcessingAgreement.company_id == company_id,
                    DataProcessingAgreement.status == "active",
                )
            )
        )
        active_dpas = dpa_result.scalar() or 0

        return {
            "by_status": by_status,
            "by_type": by_type,
            "total_granted": by_status.get(ConsentStatus.GRANTED.value, 0),
            "total_pending": by_status.get(ConsentStatus.PENDING.value, 0),
            "total_withdrawn": by_status.get(ConsentStatus.WITHDRAWN.value, 0),
            "expiring_soon": len(expiring),
            "active_dpas": active_dpas,
        }
