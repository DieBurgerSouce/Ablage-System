# -*- coding: utf-8 -*-
"""
Personalized Thresholds DB Service.

PHASE 0 CRITICAL FIX: DB-backed Version des PersonalizedThresholdsService.

Diese Version ersetzt das in-memory Storage durch echte DB-Persistenz.
Der Service ist als Drop-In-Replacement für den Original-Service konzipiert.

Verwendung:
    # Dependency Injection in FastAPI
    async def get_thresholds_service(
        db: AsyncSession = Depends(get_db),
    ) -> PersonalizedThresholdsDBService:
        return PersonalizedThresholdsDBService(db)

    @router.get("/thresholds")
    async def get_thresholds(
        user_id: UUID,
        service: PersonalizedThresholdsDBService = Depends(get_thresholds_service),
    ):
        return await service.get_all_thresholds(user_id)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.repositories import (
    PrivatUserProfileRepository,
    PrivatUserThresholdRepository,
    PrivatThresholdAdjustmentRepository,
    PrivatThresholdRecommendationRepository,
)
from app.services.orchestration.personalized_thresholds_service import (
    AdjustmentSource,
    ProfessionType,
    RiskTolerance,
    ThresholdCategory,
    ThresholdType,
    ThresholdRegistry,
    ThresholdDefinition,
    UserProfile,
    UserThreshold,
    ThresholdAdjustment,
    ThresholdRecommendation,
)

logger = structlog.get_logger(__name__)


class PersonalizedThresholdsDBService:
    """
    DB-backed Service für personalisierte Schwellenwerte.

    Diese Version verwendet PostgreSQL statt In-Memory Storage.
    Alle Daten werden persistent gespeichert.

    Features:
    - Volle DB-Persistenz
    - Keine Datenverluste bei Restarts
    - Multi-Instance Support
    - Audit-Trail aller Änderungen
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den Service mit einer DB-Session.

        Args:
            db: Async SQLAlchemy Session
        """
        self.db = db
        self.registry = ThresholdRegistry()

        # Repositories
        self._profile_repo = PrivatUserProfileRepository(db)
        self._threshold_repo = PrivatUserThresholdRepository(db)
        self._adjustment_repo = PrivatThresholdAdjustmentRepository(db)
        self._recommendation_repo = PrivatThresholdRecommendationRepository(db)

        logger.debug("PersonalizedThresholdsDBService initialisiert")

    # -------------------------------------------------------------------------
    # Profile Management
    # -------------------------------------------------------------------------

    async def get_or_create_profile(
        self,
        user_id: UUID,
        profession_type: Optional[ProfessionType] = None,
        risk_tolerance: Optional[RiskTolerance] = None,
    ) -> UserProfile:
        """Holt oder erstellt ein User-Profil."""
        db_profile = await self._profile_repo.get_by_user_id(user_id)

        if db_profile:
            # Update wenn neue Werte
            updates = {}
            if profession_type:
                updates["profession_type"] = profession_type.value
            if risk_tolerance:
                updates["risk_tolerance"] = risk_tolerance.value

            if updates:
                db_profile = await self._profile_repo.upsert(user_id, updates)

            return self._db_profile_to_dataclass(db_profile)

        # Neues Profil erstellen
        profile_data = {
            "profession_type": (profession_type or ProfessionType.EMPLOYEE).value,
            "risk_tolerance": (risk_tolerance or RiskTolerance.MODERATE).value,
            "income_stability": Decimal("0.7"),
            "age_group": "31-45",
            "household_size": 2,
            "has_dependents": False,
            "is_homeowner": False,
            "has_pension_plan": True,
            "prefers_aggressive_alerts": False,
            "prefers_conservative_targets": True,
            "feedback_history": [],
        }

        db_profile = await self._profile_repo.upsert(user_id, profile_data)
        profile = self._db_profile_to_dataclass(db_profile)

        # Initialisiere Thresholds für neuen User
        await self._initialize_user_thresholds(user_id, profile)

        logger.info(
            "user_profile_created",
            user_id=str(user_id),
            profession=profile.profession_type.value,
            risk=profile.risk_tolerance.value,
        )

        return profile

    async def update_profile(
        self,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> UserProfile:
        """Aktualisiert ein User-Profil."""
        profile = await self.get_or_create_profile(user_id)

        # Convert enums to strings for DB
        db_updates = {}
        for key, value in updates.items():
            if key == "profession_type":
                db_updates[key] = ProfessionType(value).value if isinstance(value, str) else value.value
            elif key == "risk_tolerance":
                db_updates[key] = RiskTolerance(value).value if isinstance(value, str) else value.value
            else:
                db_updates[key] = value

        db_profile = await self._profile_repo.upsert(user_id, db_updates)
        profile = self._db_profile_to_dataclass(db_profile)

        # Recalculate thresholds
        await self._recalculate_thresholds(user_id, profile)

        logger.info("user_profile_updated", user_id=str(user_id))

        return profile

    def _db_profile_to_dataclass(self, db_profile) -> UserProfile:
        """Konvertiert DB-Model zu Dataclass."""
        return UserProfile(
            user_id=db_profile.user_id,
            profession_type=ProfessionType(db_profile.profession_type),
            risk_tolerance=RiskTolerance(db_profile.risk_tolerance),
            income_stability=float(db_profile.income_stability),
            age_group=db_profile.age_group or "31-45",
            household_size=db_profile.household_size,
            has_dependents=db_profile.has_dependents,
            is_homeowner=db_profile.is_homeowner,
            has_pension_plan=db_profile.has_pension_plan,
            prefers_aggressive_alerts=db_profile.prefers_aggressive_alerts,
            prefers_conservative_targets=db_profile.prefers_conservative_targets,
            feedback_history=db_profile.feedback_history or [],
            created_at=db_profile.created_at,
            updated_at=db_profile.updated_at,
        )

    # -------------------------------------------------------------------------
    # Threshold Management
    # -------------------------------------------------------------------------

    async def _initialize_user_thresholds(
        self,
        user_id: UUID,
        profile: UserProfile,
    ) -> None:
        """Initialisiert Thresholds für einen neuen User."""
        thresholds_data = []

        for definition in self.registry.get_all_thresholds():
            calculated_value = self._calculate_personalized_value(definition, profile)

            thresholds_data.append({
                "threshold_type": definition.threshold_type.value,
                "default_value": Decimal(str(definition.default_value)),
                "current_value": Decimal(str(calculated_value)),
                "adjustment_source": AdjustmentSource.PROFESSION_PROFILE.value,
                "adjustment_reason": f"Basierend auf Berufsprofil: {profile.profession_type.value}",
                "confidence": Decimal("0.75"),
                "times_triggered": 0,
                "times_acted_on": 0,
                "effectiveness_score": Decimal("1.0"),
            })

        await self._threshold_repo.bulk_upsert(user_id, thresholds_data)

    def _calculate_personalized_value(
        self,
        definition: ThresholdDefinition,
        profile: UserProfile,
    ) -> float:
        """Berechnet personalisierten Schwellenwert."""
        # Start mit Default
        value = definition.default_value

        # Profession-basierter Override
        if profile.profession_type in definition.profession_defaults:
            value = definition.profession_defaults[profile.profession_type]

        # Risk Modifier anwenden
        if profile.risk_tolerance in definition.risk_modifiers:
            modifier = definition.risk_modifiers[profile.risk_tolerance]
            value = value * modifier

        # Clamp to allowed range
        value = max(definition.min_allowed, min(definition.max_allowed, value))

        return round(value, 2)

    async def _recalculate_thresholds(
        self,
        user_id: UUID,
        profile: UserProfile,
    ) -> None:
        """Berechnet alle Thresholds nach Profil-Änderung neu."""
        db_thresholds = await self._threshold_repo.get_by_user_id(user_id)

        if not db_thresholds:
            await self._initialize_user_thresholds(user_id, profile)
            return

        for db_threshold in db_thresholds:
            # Nur wenn nicht User-Override
            if db_threshold.adjustment_source in [
                AdjustmentSource.SYSTEM_DEFAULT.value,
                AdjustmentSource.PROFESSION_PROFILE.value,
            ]:
                threshold_type = ThresholdType(db_threshold.threshold_type)
                definition = self.registry.get_threshold(threshold_type)

                if definition:
                    new_value = self._calculate_personalized_value(definition, profile)

                    if float(db_threshold.current_value) != new_value:
                        # Log adjustment
                        adjustment_data = {
                            "user_id": user_id,
                            "threshold_type": threshold_type.value,
                            "previous_value": db_threshold.current_value,
                            "new_value": Decimal(str(new_value)),
                            "adjustment_source": AdjustmentSource.PROFESSION_PROFILE.value,
                            "reason": f"Profil-Update: {profile.profession_type.value}, {profile.risk_tolerance.value}",
                            "confidence": Decimal("0.8"),
                        }
                        await self._adjustment_repo.create(adjustment_data)

                        # Update threshold
                        await self._threshold_repo.upsert(
                            user_id,
                            threshold_type.value,
                            {
                                "current_value": Decimal(str(new_value)),
                                "adjustment_source": AdjustmentSource.PROFESSION_PROFILE.value,
                            }
                        )

    async def get_threshold(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
    ) -> Optional[UserThreshold]:
        """Holt einen personalisierten Schwellenwert."""
        await self.get_or_create_profile(user_id)  # Ensure initialized

        db_threshold = await self._threshold_repo.get_by_user_and_type(
            user_id,
            threshold_type.value,
        )

        if not db_threshold:
            return None

        # Update last_used_at
        await self._threshold_repo.upsert(
            user_id,
            threshold_type.value,
            {"last_used_at": datetime.now(timezone.utc)}
        )

        return self._db_threshold_to_dataclass(db_threshold)

    async def get_all_thresholds(
        self,
        user_id: UUID,
        category: Optional[ThresholdCategory] = None,
    ) -> List[UserThreshold]:
        """Holt alle personalisierten Schwellenwerte eines Users."""
        await self.get_or_create_profile(user_id)  # Ensure initialized

        db_thresholds = await self._threshold_repo.get_by_user_id(user_id)

        thresholds = [
            self._db_threshold_to_dataclass(t) for t in db_thresholds
        ]

        if category:
            category_types = {
                t.threshold_type
                for t in self.registry.get_thresholds_by_category(category)
            }
            thresholds = [t for t in thresholds if t.threshold_type in category_types]

        return thresholds

    async def set_threshold(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
        value: float,
        reason: Optional[str] = None,
    ) -> UserThreshold:
        """Setzt einen personalisierten Schwellenwert."""
        await self.get_or_create_profile(user_id)  # Ensure initialized

        definition = self.registry.get_threshold(threshold_type)
        if not definition:
            raise ValueError(f"Unknown threshold type: {threshold_type}")

        # Validate value
        if value < definition.min_allowed or value > definition.max_allowed:
            raise ValueError(
                f"Wert {value} ausserhalb des erlaubten Bereichs "
                f"[{definition.min_allowed}, {definition.max_allowed}]"
            )

        # Get existing for audit
        existing = await self._threshold_repo.get_by_user_and_type(
            user_id,
            threshold_type.value,
        )
        previous_value = Decimal(str(definition.default_value))
        if existing:
            previous_value = existing.current_value

        # Log adjustment
        adjustment_data = {
            "user_id": user_id,
            "threshold_type": threshold_type.value,
            "previous_value": previous_value,
            "new_value": Decimal(str(value)),
            "adjustment_source": AdjustmentSource.USER_PREFERENCE.value,
            "reason": reason or "User-Praeferenz",
            "confidence": Decimal("1.0"),
        }
        await self._adjustment_repo.create(adjustment_data)

        # Update/create threshold
        threshold_data = {
            "default_value": Decimal(str(definition.default_value)),
            "current_value": Decimal(str(value)),
            "adjustment_source": AdjustmentSource.USER_PREFERENCE.value,
            "adjustment_reason": reason,
            "confidence": Decimal("1.0"),
        }
        db_threshold = await self._threshold_repo.upsert(
            user_id,
            threshold_type.value,
            threshold_data,
        )

        logger.info(
            "threshold_set",
            user_id=str(user_id),
            threshold_type=threshold_type.value,
            value=value,
            reason=reason,
        )

        return self._db_threshold_to_dataclass(db_threshold)

    async def reset_threshold(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
    ) -> UserThreshold:
        """Setzt einen Schwellenwert auf den profil-basierten Default zurück."""
        profile = await self.get_or_create_profile(user_id)

        definition = self.registry.get_threshold(threshold_type)
        if not definition:
            raise ValueError(f"Unknown threshold type: {threshold_type}")

        # Calculate personalized default
        default_value = self._calculate_personalized_value(definition, profile)

        return await self.set_threshold(
            user_id=user_id,
            threshold_type=threshold_type,
            value=default_value,
            reason="Zurückgesetzt auf Profil-Default",
        )

    async def reset_all_thresholds(self, user_id: UUID) -> List[UserThreshold]:
        """Setzt alle Schwellenwerte zurück."""
        profile = await self.get_or_create_profile(user_id)

        results = []
        for threshold_type in ThresholdType:
            try:
                threshold = await self.reset_threshold(user_id, threshold_type)
                results.append(threshold)
            except ValueError:
                continue

        logger.info("all_thresholds_reset", user_id=str(user_id), count=len(results))

        return results

    def _db_threshold_to_dataclass(self, db_threshold) -> UserThreshold:
        """Konvertiert DB-Model zu Dataclass."""
        return UserThreshold(
            id=db_threshold.id,
            user_id=db_threshold.user_id,
            threshold_type=ThresholdType(db_threshold.threshold_type),
            default_value=float(db_threshold.default_value),
            current_value=float(db_threshold.current_value),
            adjustment_source=AdjustmentSource(db_threshold.adjustment_source),
            adjustment_reason=db_threshold.adjustment_reason,
            created_at=db_threshold.created_at,
            updated_at=db_threshold.updated_at,
            last_used_at=db_threshold.last_used_at,
            confidence=float(db_threshold.confidence),
            times_triggered=db_threshold.times_triggered,
            times_acted_on=db_threshold.times_acted_on,
            effectiveness_score=float(db_threshold.effectiveness_score),
        )

    # -------------------------------------------------------------------------
    # Effectiveness Tracking
    # -------------------------------------------------------------------------

    async def record_threshold_trigger(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
        actual_value: float,
        triggered: bool,
    ) -> None:
        """Zeichnet auf, wenn ein Threshold getriggert wurde."""
        await self._threshold_repo.record_trigger(user_id, threshold_type.value)

    async def record_threshold_action(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
        action_taken: bool,
    ) -> None:
        """Zeichnet auf, ob User auf Threshold-Alert reagiert hat."""
        await self._threshold_repo.record_action(
            user_id,
            threshold_type.value,
            action_taken,
        )

    # -------------------------------------------------------------------------
    # Recommendations
    # -------------------------------------------------------------------------

    async def generate_threshold_recommendations(
        self,
        user_id: UUID,
        current_kpis: Dict[str, float],
    ) -> List[ThresholdRecommendation]:
        """Generiert Empfehlungen für Schwellenwert-Anpassungen."""
        profile = await self.get_or_create_profile(user_id)
        recommendations: List[ThresholdRecommendation] = []
        now = datetime.now(timezone.utc)

        # DTI-basierte Empfehlung
        if "dti_ratio" in current_kpis:
            dti = current_kpis["dti_ratio"]
            dti_warning = await self.get_threshold(user_id, ThresholdType.DTI_WARNING)

            if dti_warning:
                # User ist chronisch nah am Threshold
                if dti > dti_warning.current_value * 0.9 and dti < dti_warning.current_value:
                    # Vielleicht Threshold erhöhen wenn stabil
                    if profile.income_stability > 0.8:
                        rec_data = {
                            "user_id": user_id,
                            "threshold_type": ThresholdType.DTI_WARNING.value,
                            "current_value": Decimal(str(dti_warning.current_value)),
                            "recommended_value": Decimal(str(min(dti_warning.current_value + 3, 50))),
                            "reason": (
                                f"Ihr DTI liegt stabil bei {dti:.1f}%. "
                                f"Bei Ihrer Einkommensstabilität könnte der Warnschwellenwert "
                                f"leicht erhöht werden."
                            ),
                            "confidence": Decimal("0.7"),
                            "potential_impact": "Weniger Warnungen bei stabilem Einkommen",
                            "expires_at": now + timedelta(days=30),
                        }
                        db_rec = await self._recommendation_repo.create(rec_data)
                        recommendations.append(self._db_recommendation_to_dataclass(db_rec))

        # Notgroschen-Empfehlung
        if "emergency_fund_months" in current_kpis:
            ef_months = current_kpis["emergency_fund_months"]
            ef_target = await self.get_threshold(user_id, ThresholdType.EMERGENCY_FUND_TARGET)

            if ef_target:
                # User hat deutlich mehr als Ziel
                if ef_months > ef_target.current_value * 1.5:
                    rec_data = {
                        "user_id": user_id,
                        "threshold_type": ThresholdType.EMERGENCY_FUND_TARGET.value,
                        "current_value": Decimal(str(ef_target.current_value)),
                        "recommended_value": Decimal(str(min(ef_months * 0.8, 12))),
                        "reason": (
                            f"Ihr Notgroschen ({ef_months:.1f} Monate) ist deutlich über "
                            f"dem Ziel ({ef_target.current_value:.1f} Monate). "
                            f"Überschuessige Liquiditaet könnte investiert werden."
                        ),
                        "confidence": Decimal("0.75"),
                        "potential_impact": "Mehr Kapital für Investments verfügbar",
                        "expires_at": now + timedelta(days=60),
                    }
                    db_rec = await self._recommendation_repo.create(rec_data)
                    recommendations.append(self._db_recommendation_to_dataclass(db_rec))

        # Sparrate-Empfehlung
        if "monthly_savings_rate" in current_kpis:
            savings_rate = current_kpis["monthly_savings_rate"]
            sr_target = await self.get_threshold(user_id, ThresholdType.SAVINGS_RATE_TARGET)

            if sr_target and savings_rate > sr_target.current_value * 1.2:
                rec_data = {
                    "user_id": user_id,
                    "threshold_type": ThresholdType.SAVINGS_RATE_TARGET.value,
                    "current_value": Decimal(str(sr_target.current_value)),
                    "recommended_value": Decimal(str(min(savings_rate, 50))),
                    "reason": (
                        f"Sie sparen konstant {savings_rate:.1f}%, mehr als Ihr Ziel "
                        f"von {sr_target.current_value:.1f}%. Das neue Ziel reflektiert "
                        f"Ihre tatsaechliche Sparleistung."
                    ),
                    "confidence": Decimal("0.8"),
                    "potential_impact": "Realistischeres Ziel, besseres Tracking",
                    "expires_at": now + timedelta(days=30),
                }
                db_rec = await self._recommendation_repo.create(rec_data)
                recommendations.append(self._db_recommendation_to_dataclass(db_rec))

        return recommendations

    async def get_pending_recommendations(
        self,
        user_id: UUID,
    ) -> List[ThresholdRecommendation]:
        """Holt ausstehende Empfehlungen."""
        db_recs = await self._recommendation_repo.get_pending_by_user(user_id)
        return [self._db_recommendation_to_dataclass(r) for r in db_recs]

    async def accept_recommendation(
        self,
        user_id: UUID,
        recommendation_id: UUID,
    ) -> Optional[UserThreshold]:
        """Akzeptiert eine Empfehlung."""
        db_rec = await self._recommendation_repo.accept(recommendation_id)

        if not db_rec:
            return None

        # Apply the recommendation
        return await self.set_threshold(
            user_id=user_id,
            threshold_type=ThresholdType(db_rec.threshold_type),
            value=float(db_rec.recommended_value),
            reason=f"Empfehlung akzeptiert: {db_rec.reason[:100]}",
        )

    async def reject_recommendation(
        self,
        user_id: UUID,
        recommendation_id: UUID,
        reason: Optional[str] = None,
    ) -> bool:
        """Lehnt eine Empfehlung ab."""
        db_rec = await self._recommendation_repo.reject(recommendation_id)

        if not db_rec:
            return False

        # Learn from rejection - update profile feedback history
        db_profile = await self._profile_repo.get_by_user_id(user_id)
        if db_profile:
            feedback_history = db_profile.feedback_history or []
            feedback_history.append({
                "type": "recommendation_rejected",
                "threshold_type": db_rec.threshold_type,
                "recommended_value": float(db_rec.recommended_value),
                "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            await self._profile_repo.upsert(
                user_id,
                {"feedback_history": feedback_history}
            )

        return True

    def _db_recommendation_to_dataclass(self, db_rec) -> ThresholdRecommendation:
        """Konvertiert DB-Model zu Dataclass."""
        return ThresholdRecommendation(
            id=db_rec.id,
            user_id=db_rec.user_id,
            threshold_type=ThresholdType(db_rec.threshold_type),
            current_value=float(db_rec.current_value),
            recommended_value=float(db_rec.recommended_value),
            reason=db_rec.reason,
            confidence=float(db_rec.confidence),
            potential_impact=db_rec.potential_impact,
            created_at=db_rec.created_at,
            expires_at=db_rec.expires_at,
            accepted=db_rec.accepted,
            accepted_at=db_rec.accepted_at,
        )

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    async def get_threshold_statistics(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken zu Schwellenwerten."""
        thresholds = await self.get_all_thresholds(user_id)

        if not thresholds:
            return {
                "total_thresholds": 0,
                "customized_count": 0,
                "average_effectiveness": 0,
            }

        customized = [
            t for t in thresholds
            if t.adjustment_source == AdjustmentSource.USER_PREFERENCE
        ]

        effectiveness_scores = [
            t.effectiveness_score for t in thresholds
            if t.times_triggered > 0
        ]

        return {
            "total_thresholds": len(thresholds),
            "customized_count": len(customized),
            "system_defaults_count": len(thresholds) - len(customized),
            "average_effectiveness": (
                sum(effectiveness_scores) / len(effectiveness_scores)
                if effectiveness_scores else 0
            ),
            "total_triggers": sum(t.times_triggered for t in thresholds),
            "total_actions": sum(t.times_acted_on for t in thresholds),
            "pending_recommendations": len(
                await self.get_pending_recommendations(user_id)
            ),
        }

    async def get_adjustment_history(
        self,
        user_id: UUID,
        limit: int = 20,
    ) -> List[ThresholdAdjustment]:
        """Holt Anpassungs-Historie."""
        db_adjustments = await self._adjustment_repo.get_by_user_id(user_id, limit)
        return [self._db_adjustment_to_dataclass(a) for a in db_adjustments]

    def _db_adjustment_to_dataclass(self, db_adj) -> ThresholdAdjustment:
        """Konvertiert DB-Model zu Dataclass."""
        return ThresholdAdjustment(
            id=db_adj.id,
            user_id=db_adj.user_id,
            threshold_type=ThresholdType(db_adj.threshold_type),
            previous_value=float(db_adj.previous_value),
            new_value=float(db_adj.new_value),
            adjustment_source=AdjustmentSource(db_adj.adjustment_source),
            reason=db_adj.reason or "",
            confidence=float(db_adj.confidence),
            applied_at=db_adj.applied_at,
            can_rollback=db_adj.can_rollback,
            rolled_back=db_adj.rolled_back,
        )


# =============================================================================
# Factory Function
# =============================================================================

def get_personalized_thresholds_db_service(
    db: AsyncSession,
) -> PersonalizedThresholdsDBService:
    """Factory-Funktion für Dependency Injection."""
    return PersonalizedThresholdsDBService(db)
