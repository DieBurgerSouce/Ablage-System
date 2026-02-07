# -*- coding: utf-8 -*-
"""Dunning Stage Config Service - Mahnstufen-Konfiguration.

Verwaltet konfigurierbare Mahnstufen:
- Standard-Stufen mit deutschen Defaults
- Benutzerdefinierte Stufen
- Drag-and-Drop Reihenfolge
- Kundenspezifische Overrides

BGB §286 Compliance:
- B2B: Basiszins + 9% = 11.27% p.a.
- B2C: Basiszins + 5% = 7.27% p.a.
- EUR 40 Pauschale nach §288 Abs. 5 BGB
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from app.core.datetime_utils import utc_now
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Union
from uuid import UUID, uuid4

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]
import structlog

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DunningStageConfig,
    CustomerDunningOverride,
    BusinessEntity,
    User,
)
from app.services.banking.models import (
    AutoDunningSettingsResponse,
    AutoDunningSettingsUpdate,
    LevelIntervals,
)

logger = structlog.get_logger(__name__)


# Aktueller Basiszinssatz (Stand: Januar 2025)
# Wird halbjährlich aktualisiert (01.01 und 01.07)
BASE_INTEREST_RATE = Decimal("2.27")

# Aufschläge nach BGB §288
B2B_INTEREST_ADDON = Decimal("9.00")  # Basiszins + 9% = 11.27% p.a.
B2C_INTEREST_ADDON = Decimal("5.00")  # Basiszins + 5% = 7.27% p.a.

# Pauschale nach §288 Abs. 5 BGB (nur B2B)
B2B_PAUSCHALE = Decimal("40.00")


class DunningActionType(str, Enum):
    """Aktionstyp bei Mahnstufe."""
    EMAIL = "email"             # E-Mail
    LETTER = "letter"           # Brief
    PHONE = "phone"             # Telefonanruf
    ESCALATION = "escalation"   # An Inkasso/Rechtlich


class ContactMethod(str, Enum):
    """Bevorzugte Kontaktmethode."""
    EMAIL = "email"
    PHONE = "phone"
    LETTER = "letter"


@dataclass
class DefaultStage:
    """Standard-Mahnstufe."""
    stage_number: int
    stage_name: str
    trigger_days_after_due: int
    action_type: DunningActionType
    fee_amount: Decimal


# Standard-Mahnstufen (deutsch)
DEFAULT_STAGES: List[DefaultStage] = [
    DefaultStage(
        stage_number=1,
        stage_name="Zahlungserinnerung",
        trigger_days_after_due=7,
        action_type=DunningActionType.EMAIL,
        fee_amount=Decimal("0.00"),
    ),
    DefaultStage(
        stage_number=2,
        stage_name="1. Mahnung",
        trigger_days_after_due=17,
        action_type=DunningActionType.EMAIL,
        fee_amount=Decimal("5.00"),
    ),
    DefaultStage(
        stage_number=3,
        stage_name="2. Mahnung + Telefonkontakt",
        trigger_days_after_due=27,
        action_type=DunningActionType.PHONE,
        fee_amount=Decimal("10.00"),
    ),
    DefaultStage(
        stage_number=4,
        stage_name="Letzte Mahnung",
        trigger_days_after_due=37,
        action_type=DunningActionType.LETTER,
        fee_amount=Decimal("15.00"),
    ),
    DefaultStage(
        stage_number=5,
        stage_name="Inkasso-Uebergabe",
        trigger_days_after_due=50,
        action_type=DunningActionType.ESCALATION,
        fee_amount=Decimal("0.00"),
    ),
]


class DunningStageConfigService:
    """Service fuer Mahnstufen-Konfiguration."""

    async def get_stages(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> List[JSONDict]:
        """Hole alle Mahnstufen fuer Benutzer.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Liste der Mahnstufen-Konfigurationen
        """
        query = (
            select(DunningStageConfig)
            .where(DunningStageConfig.user_id == user_id)
            .order_by(DunningStageConfig.sort_order.asc())
        )

        result = await db.execute(query)
        stages = result.scalars().all()

        # Falls keine Stufen vorhanden, Standards erstellen
        if not stages:
            stages = await self._create_default_stages(db, user_id)

        return [self._stage_to_dict(s) for s in stages]

    async def get_stage(
        self,
        db: AsyncSession,
        user_id: UUID,
        stage_id: UUID,
    ) -> Optional[JSONDict]:
        """Hole einzelne Mahnstufe.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            stage_id: Stufen-ID

        Returns:
            Mahnstufe oder None
        """
        query = select(DunningStageConfig).where(
            and_(
                DunningStageConfig.id == stage_id,
                DunningStageConfig.user_id == user_id,
            )
        )
        result = await db.execute(query)
        stage = result.scalar_one_or_none()

        return self._stage_to_dict(stage) if stage else None

    async def create_stage(
        self,
        db: AsyncSession,
        user_id: UUID,
        stage_name: str,
        trigger_days_after_due: int,
        action_type: DunningActionType,
        fee_amount: Decimal = Decimal("0.00"),
        template_id: Optional[UUID] = None,
    ) -> JSONDict:
        """Erstelle neue Mahnstufe.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            stage_name: Name der Stufe
            trigger_days_after_due: Tage nach Faelligkeit
            action_type: Aktionstyp
            fee_amount: Mahngebuehr
            template_id: Optionale Template-ID

        Returns:
            Erstellte Mahnstufe
        """
        # Naechste Stufennummer und Sortierung bestimmen
        max_query = select(
            func.max(DunningStageConfig.stage_number),
            func.max(DunningStageConfig.sort_order)
        ).where(DunningStageConfig.user_id == user_id)

        max_result = await db.execute(max_query)
        max_values = max_result.one()
        next_stage = (max_values[0] or 0) + 1
        next_sort = (max_values[1] or 0) + 1

        stage = DunningStageConfig(
            id=uuid4(),
            user_id=user_id,
            stage_number=next_stage,
            stage_name=stage_name,
            trigger_days_after_due=trigger_days_after_due,
            action_type=action_type.value,
            template_id=template_id,
            fee_amount=fee_amount,
            is_active=True,
            sort_order=next_sort,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(stage)
        await db.commit()
        await db.refresh(stage)

        logger.info(
            "dunning_stage_created",
            stage_id=str(stage.id),
            stage_name=stage_name,
            user_id=str(user_id),
        )

        return self._stage_to_dict(stage)

    async def update_stage(
        self,
        db: AsyncSession,
        user_id: UUID,
        stage_id: UUID,
        stage_name: Optional[str] = None,
        trigger_days_after_due: Optional[int] = None,
        action_type: Optional[DunningActionType] = None,
        fee_amount: Optional[Decimal] = None,
        template_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> JSONDict:
        """Aktualisiere Mahnstufe.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            stage_id: Stufen-ID
            stage_name: Neuer Name
            trigger_days_after_due: Neue Tage
            action_type: Neuer Aktionstyp
            fee_amount: Neue Gebuehr
            template_id: Neue Template-ID
            is_active: Aktiv/Inaktiv

        Returns:
            Aktualisierte Mahnstufe
        """
        stage = await self._get_stage(db, user_id, stage_id)
        if not stage:
            raise ValueError("Mahnstufe nicht gefunden")

        if stage_name is not None:
            stage.stage_name = stage_name
        if trigger_days_after_due is not None:
            stage.trigger_days_after_due = trigger_days_after_due
        if action_type is not None:
            stage.action_type = action_type.value
        if fee_amount is not None:
            stage.fee_amount = fee_amount
        if template_id is not None:
            stage.template_id = template_id
        if is_active is not None:
            stage.is_active = is_active

        stage.updated_at = utc_now()

        await db.commit()
        await db.refresh(stage)

        logger.info(
            "dunning_stage_updated",
            stage_id=str(stage_id),
        )

        return self._stage_to_dict(stage)

    async def delete_stage(
        self,
        db: AsyncSession,
        user_id: UUID,
        stage_id: UUID,
    ) -> bool:
        """Loesche Mahnstufe.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            stage_id: Stufen-ID

        Returns:
            True wenn geloescht
        """
        stage = await self._get_stage(db, user_id, stage_id)
        if not stage:
            raise ValueError("Mahnstufe nicht gefunden")

        await db.delete(stage)
        await db.commit()

        logger.info(
            "dunning_stage_deleted",
            stage_id=str(stage_id),
        )

        return True

    async def reorder_stages(
        self,
        db: AsyncSession,
        user_id: UUID,
        stage_ids: List[UUID],
    ) -> List[JSONDict]:
        """Ordne Mahnstufen neu (Drag-and-Drop).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            stage_ids: Neue Reihenfolge der IDs

        Returns:
            Aktualisierte Stufenliste
        """
        # Alle Stufen laden
        query = select(DunningStageConfig).where(
            DunningStageConfig.user_id == user_id
        )
        result = await db.execute(query)
        stages = {s.id: s for s in result.scalars().all()}

        # Reihenfolge aktualisieren
        for sort_order, stage_id in enumerate(stage_ids, start=1):
            if stage_id in stages:
                stages[stage_id].sort_order = sort_order
                stages[stage_id].stage_number = sort_order
                stages[stage_id].updated_at = utc_now()

        await db.commit()

        logger.info(
            "dunning_stages_reordered",
            user_id=str(user_id),
            new_order=[str(sid) for sid in stage_ids],
        )

        # Aktualisierte Liste zurueckgeben
        return await self.get_stages(db, user_id)

    async def reset_to_defaults(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> List[JSONDict]:
        """Setze Mahnstufen auf Standard zurueck.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Standard-Stufenliste
        """
        # Alle bestehenden Stufen loeschen
        await db.execute(
            delete(DunningStageConfig).where(
                DunningStageConfig.user_id == user_id
            )
        )

        # Standards erstellen
        stages = await self._create_default_stages(db, user_id)

        logger.info(
            "dunning_stages_reset",
            user_id=str(user_id),
        )

        return [self._stage_to_dict(s) for s in stages]

    # =========================================================================
    # Customer Dunning Overrides
    # =========================================================================

    async def get_customer_override(
        self,
        db: AsyncSession,
        business_entity_id: UUID,
    ) -> Optional[JSONDict]:
        """Hole kundenspezifische Mahneinstellungen.

        Args:
            db: Datenbank-Session
            business_entity_id: Geschaeftspartner-ID

        Returns:
            Override-Einstellungen oder None
        """
        query = select(CustomerDunningOverride).where(
            CustomerDunningOverride.business_entity_id == business_entity_id
        )
        result = await db.execute(query)
        override = result.scalar_one_or_none()

        return self._override_to_dict(override) if override else None

    async def set_customer_override(
        self,
        db: AsyncSession,
        business_entity_id: UUID,
        custom_payment_terms_days: Optional[int] = None,
        max_mahn_stufe: Optional[int] = None,
        preferred_contact_method: Optional[ContactMethod] = None,
        exclude_from_auto_dunning: bool = False,
        exclusion_reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> JSONDict:
        """Setze kundenspezifische Mahneinstellungen.

        Args:
            db: Datenbank-Session
            business_entity_id: Geschaeftspartner-ID
            custom_payment_terms_days: Abweichende Zahlungsfrist
            max_mahn_stufe: Max. Eskalationsstufe
            preferred_contact_method: Bevorzugte Kontaktart
            exclude_from_auto_dunning: Von Auto-Mahnung ausschliessen
            exclusion_reason: Grund für Ausschluss
            notes: Notizen

        Returns:
            Gespeicherte Einstellungen
        """
        # Pruefen ob Override existiert
        query = select(CustomerDunningOverride).where(
            CustomerDunningOverride.business_entity_id == business_entity_id
        )
        result = await db.execute(query)
        override = result.scalar_one_or_none()

        if override:
            # Update
            if custom_payment_terms_days is not None:
                override.custom_payment_terms_days = custom_payment_terms_days
            if max_mahn_stufe is not None:
                override.max_mahn_stufe = max_mahn_stufe
            if preferred_contact_method is not None:
                override.preferred_contact_method = preferred_contact_method.value
            override.exclude_from_auto_dunning = exclude_from_auto_dunning
            if exclusion_reason is not None:
                override.exclusion_reason = exclusion_reason
            if notes is not None:
                override.notes = notes
            override.updated_at = utc_now()
        else:
            # Create
            override = CustomerDunningOverride(
                id=uuid4(),
                business_entity_id=business_entity_id,
                custom_payment_terms_days=custom_payment_terms_days,
                max_mahn_stufe=max_mahn_stufe,
                preferred_contact_method=preferred_contact_method.value if preferred_contact_method else "email",
                exclude_from_auto_dunning=exclude_from_auto_dunning,
                exclusion_reason=exclusion_reason,
                notes=notes,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.add(override)

        await db.commit()
        await db.refresh(override)

        logger.info(
            "customer_dunning_override_set",
            business_entity_id=str(business_entity_id),
            exclude_from_auto=exclude_from_auto_dunning,
        )

        return self._override_to_dict(override)

    async def delete_customer_override(
        self,
        db: AsyncSession,
        business_entity_id: UUID,
    ) -> bool:
        """Loesche kundenspezifische Mahneinstellungen.

        Args:
            db: Datenbank-Session
            business_entity_id: Geschaeftspartner-ID

        Returns:
            True wenn geloescht
        """
        query = select(CustomerDunningOverride).where(
            CustomerDunningOverride.business_entity_id == business_entity_id
        )
        result = await db.execute(query)
        override = result.scalar_one_or_none()

        if not override:
            return False

        await db.delete(override)
        await db.commit()

        logger.info(
            "customer_dunning_override_deleted",
            business_entity_id=str(business_entity_id),
        )

        return True

    # =========================================================================
    # Auto-Mahnlauf Einstellungen
    # =========================================================================

    # Schluessel fuer Auto-Mahnlauf-Einstellungen im User.preferences JSONB
    AUTO_DUNNING_SETTINGS_KEY = "auto_dunning_settings"

    async def get_auto_dunning_settings(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> AutoDunningSettingsResponse:
        """Hole Auto-Mahnlauf-Einstellungen fuer Benutzer.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Auto-Mahnlauf-Einstellungen mit Standardwerten wenn nicht gesetzt
        """
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError("Benutzer nicht gefunden")

        # Einstellungen aus preferences laden oder Defaults verwenden
        preferences = user.preferences or {}
        settings_data = preferences.get(self.AUTO_DUNNING_SETTINGS_KEY, {})

        # Level-Intervalle parsen
        level_intervals_data = settings_data.get("level_intervals", {})
        level_intervals = LevelIntervals(
            level_1=level_intervals_data.get("level_1", 7),
            level_2=level_intervals_data.get("level_2", 14),
            level_3=level_intervals_data.get("level_3", 21),
        )

        return AutoDunningSettingsResponse(
            enabled=settings_data.get("enabled", False),
            run_time=settings_data.get("run_time", "08:00"),
            exclude_weekends=settings_data.get("exclude_weekends", True),
            exclude_holidays=settings_data.get("exclude_holidays", True),
            auto_send_email=settings_data.get("auto_send_email", False),
            min_amount=Decimal(str(settings_data.get("min_amount", "10.00"))),
            max_auto_level=settings_data.get("max_auto_level", 2),
            level_intervals=level_intervals,
            last_run_at=settings_data.get("last_run_at"),
            next_run_at=settings_data.get("next_run_at"),
        )

    async def update_auto_dunning_settings(
        self,
        db: AsyncSession,
        user_id: UUID,
        settings: AutoDunningSettingsUpdate,
    ) -> AutoDunningSettingsResponse:
        """Aktualisiere Auto-Mahnlauf-Einstellungen fuer Benutzer.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            settings: Zu aktualisierende Einstellungen

        Returns:
            Aktualisierte Auto-Mahnlauf-Einstellungen
        """
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError("Benutzer nicht gefunden")

        # Aktuelle Einstellungen laden
        preferences = dict(user.preferences or {})
        current_settings = dict(preferences.get(self.AUTO_DUNNING_SETTINGS_KEY, {}))

        # Nur gesetzte Werte aktualisieren
        if settings.enabled is not None:
            current_settings["enabled"] = settings.enabled
        if settings.run_time is not None:
            current_settings["run_time"] = settings.run_time
        if settings.exclude_weekends is not None:
            current_settings["exclude_weekends"] = settings.exclude_weekends
        if settings.exclude_holidays is not None:
            current_settings["exclude_holidays"] = settings.exclude_holidays
        if settings.auto_send_email is not None:
            current_settings["auto_send_email"] = settings.auto_send_email
        if settings.min_amount is not None:
            current_settings["min_amount"] = str(settings.min_amount)
        if settings.max_auto_level is not None:
            current_settings["max_auto_level"] = settings.max_auto_level

        # Level-Intervalle aktualisieren
        if settings.level_intervals is not None:
            level_intervals = current_settings.get("level_intervals", {})
            if settings.level_intervals.level_1 is not None:
                level_intervals["level_1"] = settings.level_intervals.level_1
            if settings.level_intervals.level_2 is not None:
                level_intervals["level_2"] = settings.level_intervals.level_2
            if settings.level_intervals.level_3 is not None:
                level_intervals["level_3"] = settings.level_intervals.level_3
            current_settings["level_intervals"] = level_intervals

        # Zeitstempel aktualisieren
        current_settings["updated_at"] = utc_now().isoformat()

        # In preferences speichern
        preferences[self.AUTO_DUNNING_SETTINGS_KEY] = current_settings
        user.preferences = preferences
        user.updated_at = utc_now()

        await db.commit()
        await db.refresh(user)

        logger.info(
            "auto_dunning_settings_updated",
            user_id=str(user_id),
            enabled=current_settings.get("enabled", False),
        )

        return await self.get_auto_dunning_settings(db, user_id)

    # =========================================================================
    # Verzugszinsen-Berechnung (BGB §286)
    # =========================================================================

    def get_interest_rate(self, is_b2b: bool = True) -> Decimal:
        """Berechne aktuellen Verzugszinssatz.

        Args:
            is_b2b: B2B oder B2C Kunde

        Returns:
            Jaehrlicher Zinssatz in Prozent
        """
        addon = B2B_INTEREST_ADDON if is_b2b else B2C_INTEREST_ADDON
        return BASE_INTEREST_RATE + addon

    def get_b2b_pauschale(self) -> Decimal:
        """Hole B2B-Pauschale nach §288 Abs. 5 BGB.

        Returns:
            EUR 40.00
        """
        return B2B_PAUSCHALE

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _get_stage(
        self,
        db: AsyncSession,
        user_id: UUID,
        stage_id: UUID,
    ) -> Optional[DunningStageConfig]:
        """Hole einzelne Mahnstufe."""
        query = select(DunningStageConfig).where(
            and_(
                DunningStageConfig.id == stage_id,
                DunningStageConfig.user_id == user_id,
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _create_default_stages(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> List[DunningStageConfig]:
        """Erstelle Standard-Mahnstufen fuer Benutzer."""
        stages = []

        for default in DEFAULT_STAGES:
            stage = DunningStageConfig(
                id=uuid4(),
                user_id=user_id,
                stage_number=default.stage_number,
                stage_name=default.stage_name,
                trigger_days_after_due=default.trigger_days_after_due,
                action_type=default.action_type.value,
                fee_amount=default.fee_amount,
                is_active=True,
                sort_order=default.stage_number,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.add(stage)
            stages.append(stage)

        await db.commit()

        # Refresh all stages
        for stage in stages:
            await db.refresh(stage)

        logger.info(
            "default_dunning_stages_created",
            user_id=str(user_id),
            count=len(stages),
        )

        return stages

    def _stage_to_dict(self, stage: DunningStageConfig) -> JSONDict:
        """Konvertiere Mahnstufe zu Dictionary."""
        return {
            "id": str(stage.id),
            "user_id": str(stage.user_id),
            "stage_number": stage.stage_number,
            "stage_name": stage.stage_name,
            "trigger_days_after_due": stage.trigger_days_after_due,
            "action_type": stage.action_type,
            "template_id": str(stage.template_id) if stage.template_id else None,
            "fee_amount": float(stage.fee_amount) if stage.fee_amount else 0,
            "is_active": stage.is_active,
            "sort_order": stage.sort_order,
            "created_at": stage.created_at.isoformat() if stage.created_at else None,
            "updated_at": stage.updated_at.isoformat() if stage.updated_at else None,
        }

    def _override_to_dict(self, override: CustomerDunningOverride) -> JSONDict:
        """Konvertiere Override zu Dictionary."""
        return {
            "id": str(override.id),
            "business_entity_id": str(override.business_entity_id),
            "custom_payment_terms_days": override.custom_payment_terms_days,
            "max_mahn_stufe": override.max_mahn_stufe,
            "preferred_contact_method": override.preferred_contact_method,
            "exclude_from_auto_dunning": override.exclude_from_auto_dunning,
            "exclusion_reason": override.exclusion_reason,
            "notes": override.notes,
            "created_at": override.created_at.isoformat() if override.created_at else None,
            "updated_at": override.updated_at.isoformat() if override.updated_at else None,
        }


# Singleton
dunning_stage_service = DunningStageConfigService()
