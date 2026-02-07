# -*- coding: utf-8 -*-
"""
TrustLevelService - Multi-Level Trust System fuer autonome Aktionen.

Implementiert ein 4-stufiges Trust-System:
- Level 1 (ASSISTANCE): Alle Aktionen erfordern Bestaetigung
- Level 2 (AUTO_ACCEPT): >90% Confidence, 24h Auto-Accept
- Level 3 (CONFIDENCE): >95% sofort, 80-95% verzoegert (4h)
- Level 4 (AUTONOMOUS): Volle Autonomie, nur Exceptions

Trust-Level werden basierend auf Erfolgsmetriken angepasst:
- Upgrade: Nach 100+ erfolgreichen Aktionen ohne Fehler
- Downgrade: Bei Fehlern oder Ablehnungen
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import (
    AIDecision,
    AILearningFeedback,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Trust Level Enum
# ============================================================================


class TrustLevel(str, Enum):
    """Trust-Level fuer autonome Aktionen."""

    LEVEL_1_ASSISTANCE = "assistance"     # Alle Aktionen erfordern Bestaetigung
    LEVEL_2_AUTO_ACCEPT = "auto_accept"   # >90% Confidence, 24h Auto-Accept
    LEVEL_3_CONFIDENCE = "confidence"     # >95% sofort, 80-95% verzoegert (4h)
    LEVEL_4_AUTONOMOUS = "autonomous"     # Volle Autonomie, nur Exceptions


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class TrustLevelConfig:
    """Konfiguration fuer ein Trust-Level."""

    level: TrustLevel
    immediate_threshold: float  # Ab hier sofortige Aktion
    delayed_threshold: float    # Ab hier verzoegerte Aktion
    delay_hours: int            # Wartezeit bei Verzoegerung
    require_confirmation: bool  # Immer Bestaetigung erfordern
    allow_auto_apply: bool      # Automatische Anwendung erlaubt


@dataclass
class TrustMetrics:
    """Metriken zur Trust-Level Berechnung."""

    total_decisions: int
    auto_applied: int
    approved: int
    rejected: int
    corrected: int
    approval_rate: float
    error_rate: float
    avg_confidence: float
    days_without_error: int
    last_error_at: Optional[datetime]


@dataclass
class TrustLevelRecommendation:
    """Empfehlung fuer Trust-Level Aenderung."""

    current_level: TrustLevel
    recommended_level: TrustLevel
    reason: str
    confidence: float
    can_upgrade: bool
    upgrade_requirements: Dict[str, Any]


# ============================================================================
# Trust Level Configurations
# ============================================================================


TRUST_LEVEL_CONFIGS: Dict[TrustLevel, TrustLevelConfig] = {
    TrustLevel.LEVEL_1_ASSISTANCE: TrustLevelConfig(
        level=TrustLevel.LEVEL_1_ASSISTANCE,
        immediate_threshold=1.0,   # Nie automatisch
        delayed_threshold=1.0,     # Nie verzoegert
        delay_hours=0,
        require_confirmation=True,
        allow_auto_apply=False,
    ),
    TrustLevel.LEVEL_2_AUTO_ACCEPT: TrustLevelConfig(
        level=TrustLevel.LEVEL_2_AUTO_ACCEPT,
        immediate_threshold=1.0,   # Keine sofortige Aktion
        delayed_threshold=0.90,    # Ab 90% -> 24h Auto-Accept
        delay_hours=24,
        require_confirmation=False,
        allow_auto_apply=True,
    ),
    TrustLevel.LEVEL_3_CONFIDENCE: TrustLevelConfig(
        level=TrustLevel.LEVEL_3_CONFIDENCE,
        immediate_threshold=0.95,  # Ab 95% sofort
        delayed_threshold=0.80,    # 80-95% -> 4h verzoegert
        delay_hours=4,
        require_confirmation=False,
        allow_auto_apply=True,
    ),
    TrustLevel.LEVEL_4_AUTONOMOUS: TrustLevelConfig(
        level=TrustLevel.LEVEL_4_AUTONOMOUS,
        immediate_threshold=0.70,  # Ab 70% sofort
        delayed_threshold=0.50,    # 50-70% verzoegert
        delay_hours=1,
        require_confirmation=False,
        allow_auto_apply=True,
    ),
}


# Upgrade-Anforderungen pro Level
UPGRADE_REQUIREMENTS: Dict[TrustLevel, Dict[str, Any]] = {
    TrustLevel.LEVEL_2_AUTO_ACCEPT: {
        "min_decisions": 50,
        "min_approval_rate": 0.90,
        "max_error_rate": 0.05,
        "min_days_without_error": 7,
    },
    TrustLevel.LEVEL_3_CONFIDENCE: {
        "min_decisions": 100,
        "min_approval_rate": 0.95,
        "max_error_rate": 0.02,
        "min_days_without_error": 14,
    },
    TrustLevel.LEVEL_4_AUTONOMOUS: {
        "min_decisions": 500,
        "min_approval_rate": 0.98,
        "max_error_rate": 0.01,
        "min_days_without_error": 30,
    },
}


# ============================================================================
# Trust Level Service
# ============================================================================


class TrustLevelService:
    """Service fuer Trust-Level Management.

    Verwaltet Trust-Level pro Company und Dokumenttyp.
    Berechnet Empfehlungen basierend auf Erfolgsmetriken.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def get_trust_level(
        self,
        company_id: uuid.UUID,
        document_type: Optional[str] = None,
    ) -> TrustLevel:
        """Holt das aktuelle Trust-Level fuer eine Company.

        Args:
            company_id: ID der Company
            document_type: Optional Dokumenttyp fuer spezifisches Level

        Returns:
            Aktuelles TrustLevel
        """
        try:
            # Import hier um zirkulaere Imports zu vermeiden
            from app.db.models import AutonomousTrustConfig

            # Suche spezifisches Level fuer Dokumenttyp
            if document_type:
                result = await self.db.execute(
                    select(AutonomousTrustConfig).where(
                        and_(
                            AutonomousTrustConfig.company_id == company_id,
                            AutonomousTrustConfig.document_type == document_type,
                        )
                    )
                )
                config = result.scalar_one_or_none()
                if config:
                    return TrustLevel(config.trust_level)

            # Suche globales Level fuer Company
            result = await self.db.execute(
                select(AutonomousTrustConfig).where(
                    and_(
                        AutonomousTrustConfig.company_id == company_id,
                        AutonomousTrustConfig.document_type.is_(None),
                    )
                )
            )
            config = result.scalar_one_or_none()

            if config:
                return TrustLevel(config.trust_level)

            # Default: Level 1 (Assistance)
            return TrustLevel.LEVEL_1_ASSISTANCE

        except Exception as e:
            logger.warning(
                "get_trust_level_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return TrustLevel.LEVEL_1_ASSISTANCE

    async def set_trust_level(
        self,
        company_id: uuid.UUID,
        trust_level: TrustLevel,
        document_type: Optional[str] = None,
        updated_by_id: Optional[uuid.UUID] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Setzt das Trust-Level fuer eine Company.

        Args:
            company_id: ID der Company
            trust_level: Neues Trust-Level
            document_type: Optional Dokumenttyp
            updated_by_id: ID des Benutzers
            reason: Grund fuer Aenderung

        Returns:
            True bei Erfolg
        """
        try:
            from app.db.models import AutonomousTrustConfig

            # Suche existierende Konfiguration
            result = await self.db.execute(
                select(AutonomousTrustConfig).where(
                    and_(
                        AutonomousTrustConfig.company_id == company_id,
                        AutonomousTrustConfig.document_type == document_type
                        if document_type
                        else AutonomousTrustConfig.document_type.is_(None),
                    )
                )
            )
            config = result.scalar_one_or_none()

            now = utc_now()

            if config:
                old_level = config.trust_level
                config.trust_level = trust_level.value
                config.updated_at = now
                config.updated_by_id = updated_by_id
                if reason:
                    config.change_reason = reason
                config.level_changed_at = now
            else:
                config = AutonomousTrustConfig(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    document_type=document_type,
                    trust_level=trust_level.value,
                    is_enabled=True,
                    updated_by_id=updated_by_id,
                    change_reason=reason,
                    level_changed_at=now,
                )
                self.db.add(config)
                old_level = None

            await self.db.commit()

            logger.info(
                "trust_level_changed",
                company_id=str(company_id),
                document_type=document_type,
                old_level=old_level,
                new_level=trust_level.value,
                reason=reason,
            )

            return True

        except Exception as e:
            logger.error(
                "set_trust_level_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            await self.db.rollback()
            return False

    async def get_trust_config(
        self,
        company_id: uuid.UUID,
        document_type: Optional[str] = None,
    ) -> TrustLevelConfig:
        """Holt die Trust-Level Konfiguration.

        Args:
            company_id: ID der Company
            document_type: Optional Dokumenttyp

        Returns:
            TrustLevelConfig
        """
        trust_level = await self.get_trust_level(company_id, document_type)
        return TRUST_LEVEL_CONFIGS[trust_level]

    async def get_trust_metrics(
        self,
        company_id: uuid.UUID,
        document_type: Optional[str] = None,
        days: int = 30,
    ) -> TrustMetrics:
        """Berechnet Trust-Metriken fuer eine Company.

        Args:
            company_id: ID der Company
            document_type: Optional Dokumenttyp
            days: Anzahl Tage fuer Analyse

        Returns:
            TrustMetrics
        """
        cutoff = utc_now() - timedelta(days=days)

        # Basis-Query
        base_filter = [
            AIDecision.company_id == company_id,
            AIDecision.created_at >= cutoff,
            AIDecision.is_final == True,
        ]

        # Optional: Dokumenttyp-Filter
        if document_type:
            # Filter auf Entscheidungen mit passendem Dokumenttyp
            # (erfordert Join mit Document oder decision_value Analyse)
            pass

        # Total Decisions
        result = await self.db.execute(
            select(func.count(AIDecision.id)).where(and_(*base_filter))
        )
        total_decisions = result.scalar() or 0

        # Auto-Applied
        result = await self.db.execute(
            select(func.count(AIDecision.id)).where(
                and_(*base_filter, AIDecision.auto_applied == True)
            )
        )
        auto_applied = result.scalar() or 0

        # Approved (nach Review)
        result = await self.db.execute(
            select(func.count(AIDecision.id)).where(
                and_(*base_filter, AIDecision.review_action == "approved")
            )
        )
        approved = result.scalar() or 0

        # Rejected
        result = await self.db.execute(
            select(func.count(AIDecision.id)).where(
                and_(*base_filter, AIDecision.review_action == "rejected")
            )
        )
        rejected = result.scalar() or 0

        # Corrected (Modified)
        result = await self.db.execute(
            select(func.count(AIDecision.id)).where(
                and_(*base_filter, AIDecision.review_action == "modified")
            )
        )
        corrected = result.scalar() or 0

        # Durchschnittliche Confidence
        result = await self.db.execute(
            select(func.avg(AIDecision.confidence)).where(and_(*base_filter))
        )
        avg_confidence = result.scalar() or 0.0

        # Letzter Fehler
        result = await self.db.execute(
            select(AIDecision.created_at)
            .where(
                and_(
                    *base_filter,
                    AIDecision.review_action == "rejected",
                )
            )
            .order_by(AIDecision.created_at.desc())
            .limit(1)
        )
        last_error_at = result.scalar_one_or_none()

        # Tage ohne Fehler
        if last_error_at:
            days_without_error = (utc_now() - last_error_at).days
        else:
            days_without_error = days  # Keine Fehler im Zeitraum

        # Berechnete Raten
        approval_rate = (
            (auto_applied + approved) / total_decisions
            if total_decisions > 0
            else 0.0
        )
        error_rate = (
            (rejected + corrected) / total_decisions
            if total_decisions > 0
            else 0.0
        )

        return TrustMetrics(
            total_decisions=total_decisions,
            auto_applied=auto_applied,
            approved=approved,
            rejected=rejected,
            corrected=corrected,
            approval_rate=approval_rate,
            error_rate=error_rate,
            avg_confidence=float(avg_confidence),
            days_without_error=days_without_error,
            last_error_at=last_error_at,
        )

    async def evaluate_trust_level(
        self,
        company_id: uuid.UUID,
        document_type: Optional[str] = None,
    ) -> TrustLevelRecommendation:
        """Evaluiert und empfiehlt Trust-Level basierend auf Metriken.

        Args:
            company_id: ID der Company
            document_type: Optional Dokumenttyp

        Returns:
            TrustLevelRecommendation
        """
        current_level = await self.get_trust_level(company_id, document_type)
        metrics = await self.get_trust_metrics(company_id, document_type)

        # Pruefe ob Downgrade erforderlich
        if metrics.error_rate > 0.10:  # >10% Fehlerrate
            if current_level != TrustLevel.LEVEL_1_ASSISTANCE:
                return TrustLevelRecommendation(
                    current_level=current_level,
                    recommended_level=TrustLevel.LEVEL_1_ASSISTANCE,
                    reason=f"Hohe Fehlerrate ({metrics.error_rate:.1%}). Downgrade auf Level 1 empfohlen.",
                    confidence=0.95,
                    can_upgrade=False,
                    upgrade_requirements={},
                )

        # Pruefe ob Upgrade moeglich
        next_level = self._get_next_level(current_level)
        if next_level is None:
            return TrustLevelRecommendation(
                current_level=current_level,
                recommended_level=current_level,
                reason="Hoechstes Trust-Level bereits erreicht.",
                confidence=1.0,
                can_upgrade=False,
                upgrade_requirements={},
            )

        requirements = UPGRADE_REQUIREMENTS.get(next_level, {})
        meets_requirements = self._check_upgrade_requirements(metrics, requirements)

        if meets_requirements:
            return TrustLevelRecommendation(
                current_level=current_level,
                recommended_level=next_level,
                reason=f"Alle Anforderungen fuer {next_level.value} erfuellt. Upgrade moeglich.",
                confidence=0.90,
                can_upgrade=True,
                upgrade_requirements=requirements,
            )
        else:
            missing = self._get_missing_requirements(metrics, requirements)
            return TrustLevelRecommendation(
                current_level=current_level,
                recommended_level=current_level,
                reason=f"Anforderungen fuer Upgrade nicht erfuellt: {missing}",
                confidence=0.80,
                can_upgrade=False,
                upgrade_requirements=requirements,
            )

    async def handle_decision_outcome(
        self,
        company_id: uuid.UUID,
        decision_id: uuid.UUID,
        was_approved: bool,
        was_corrected: bool,
        document_type: Optional[str] = None,
    ) -> None:
        """Reagiert auf Entscheidungs-Outcome fuer Trust-Anpassung.

        Args:
            company_id: ID der Company
            decision_id: ID der Entscheidung
            was_approved: Wurde genehmigt
            was_corrected: Wurde korrigiert
            document_type: Optional Dokumenttyp
        """
        try:
            from app.db.models import AutonomousTrustConfig

            current_level = await self.get_trust_level(company_id, document_type)
            metrics = await self.get_trust_metrics(company_id, document_type, days=7)

            # Bei Ablehnung: Sofortiger Downgrade moeglich
            if not was_approved and not was_corrected:
                # Kritischer Fehler: Downgrade erwaegen
                if metrics.error_rate > 0.15:
                    prev_level = self._get_previous_level(current_level)
                    if prev_level:
                        await self.set_trust_level(
                            company_id=company_id,
                            trust_level=prev_level,
                            document_type=document_type,
                            reason=f"Automatischer Downgrade: Fehlerrate {metrics.error_rate:.1%}",
                        )
                        logger.warning(
                            "trust_level_auto_downgrade",
                            company_id=str(company_id),
                            from_level=current_level.value,
                            to_level=prev_level.value,
                            error_rate=metrics.error_rate,
                        )

            # Bei hoher Erfolgsrate: Upgrade pruefen
            elif was_approved and metrics.approval_rate > 0.98:
                recommendation = await self.evaluate_trust_level(
                    company_id, document_type
                )
                if recommendation.can_upgrade:
                    logger.info(
                        "trust_level_upgrade_available",
                        company_id=str(company_id),
                        current_level=current_level.value,
                        recommended_level=recommendation.recommended_level.value,
                    )

        except Exception as e:
            logger.warning(
                "handle_decision_outcome_error",
                company_id=str(company_id),
                decision_id=str(decision_id),
                **safe_error_log(e),
            )

    def _get_next_level(self, current: TrustLevel) -> Optional[TrustLevel]:
        """Gibt das naechste Trust-Level zurueck."""
        levels = list(TrustLevel)
        try:
            idx = levels.index(current)
            if idx < len(levels) - 1:
                return levels[idx + 1]
        except ValueError:
            pass
        return None

    def _get_previous_level(self, current: TrustLevel) -> Optional[TrustLevel]:
        """Gibt das vorherige Trust-Level zurueck."""
        levels = list(TrustLevel)
        try:
            idx = levels.index(current)
            if idx > 0:
                return levels[idx - 1]
        except ValueError:
            pass
        return None

    def _check_upgrade_requirements(
        self,
        metrics: TrustMetrics,
        requirements: Dict[str, Any],
    ) -> bool:
        """Prueft ob Upgrade-Anforderungen erfuellt sind."""
        if not requirements:
            return False

        if metrics.total_decisions < requirements.get("min_decisions", 0):
            return False
        if metrics.approval_rate < requirements.get("min_approval_rate", 1.0):
            return False
        if metrics.error_rate > requirements.get("max_error_rate", 0.0):
            return False
        if metrics.days_without_error < requirements.get("min_days_without_error", 0):
            return False

        return True

    def _get_missing_requirements(
        self,
        metrics: TrustMetrics,
        requirements: Dict[str, Any],
    ) -> str:
        """Gibt fehlende Anforderungen als String zurueck."""
        missing = []

        min_decisions = requirements.get("min_decisions", 0)
        if metrics.total_decisions < min_decisions:
            missing.append(
                f"Entscheidungen: {metrics.total_decisions}/{min_decisions}"
            )

        min_approval = requirements.get("min_approval_rate", 1.0)
        if metrics.approval_rate < min_approval:
            missing.append(
                f"Erfolgsrate: {metrics.approval_rate:.1%}/{min_approval:.1%}"
            )

        max_error = requirements.get("max_error_rate", 0.0)
        if metrics.error_rate > max_error:
            missing.append(
                f"Fehlerrate: {metrics.error_rate:.1%} (max {max_error:.1%})"
            )

        min_days = requirements.get("min_days_without_error", 0)
        if metrics.days_without_error < min_days:
            missing.append(
                f"Tage ohne Fehler: {metrics.days_without_error}/{min_days}"
            )

        return "; ".join(missing) if missing else "Keine"


# ============================================================================
# Factory Function
# ============================================================================


def get_trust_level_service(db: AsyncSession) -> TrustLevelService:
    """Factory-Funktion fuer TrustLevelService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter TrustLevelService
    """
    return TrustLevelService(db=db)
