# -*- coding: utf-8 -*-
"""
Extraction Learning Service.

Lernendes System - Lernt aus User-Korrekturen.
'Wenn ich 3x den gleichen Lieferanten korrigiere, merke es dir.'

Per-Lieferant und Per-Dokumenttyp Lernprofile:
- Speichert Korrektur-Patterns
- Erstellt automatische Feld-Ueberschreibungen ab 3 Korrekturen
- Berechnet Confidence-Boost basierend auf Lernhistorie

Feinpoliert und durchdacht - Selbstlernendes Extraktionssystem.
"""

import structlog
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models_ki_pipeline import LearningProfile

logger = structlog.get_logger(__name__)

# Mindestanzahl identischer Korrekturen, bevor eine Regel erstellt wird
MIN_CORRECTIONS_FOR_OVERRIDE = 3

# Maximaler Confidence-Boost durch Lernprofil
MAX_CONFIDENCE_BOOST = 0.15

# Boost-Inkrement pro erfolgreicher Korrektur
BOOST_PER_CORRECTION = 0.02


class ExtractionLearningService:
    """Lernendes System - Lernt aus User-Korrekturen.

    'Wenn ich 3x den gleichen Lieferanten korrigiere, merke es dir.'
    Per-Lieferant und Per-Dokumenttyp Lernprofile.
    """

    async def record_correction(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
        field_name: str,
        original_value: str,
        corrected_value: str,
        supplier_name: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> LearningProfile:
        """Korrektur aufzeichnen und Lernprofil aktualisieren.

        Findet oder erstellt ein LearningProfile und aktualisiert
        die Korrektur-Patterns. Ab MIN_CORRECTIONS_FOR_OVERRIDE
        identischen Korrekturen wird eine automatische Regel erstellt.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            document_id: Dokument-ID (fuer Logging)
            field_name: Name des korrigierten Feldes
            original_value: Urspruenglicher extrahierter Wert
            corrected_value: Korrigierter Wert
            supplier_name: Lieferantenname (fuer Lieferant-Profil)
            document_type: Dokumenttyp (fuer Dokumenttyp-Profil)

        Returns:
            Aktualisiertes LearningProfile
        """
        # Bestimme Profiltyp und Key
        if supplier_name:
            profile_type = "supplier"
            profile_key = supplier_name.strip()
        elif document_type:
            profile_type = "document_type"
            profile_key = document_type.strip()
        else:
            # Fallback: Dokumenttyp "unknown"
            profile_type = "document_type"
            profile_key = "unknown"

        # Profil laden oder erstellen
        profile = await self._get_or_create_profile(
            db, company_id, profile_type, profile_key
        )

        now = utc_now()

        # Korrektur-Patterns aktualisieren
        patterns = dict(profile.correction_patterns or {})
        if field_name not in patterns:
            patterns[field_name] = {"original": [], "corrected": []}

        field_patterns = patterns[field_name]

        # Neue Korrektur hinzufuegen (begrenzt auf letzte 50 Eintraege)
        field_patterns["original"].append(original_value)
        field_patterns["corrected"].append(corrected_value)
        if len(field_patterns["original"]) > 50:
            field_patterns["original"] = field_patterns["original"][-50:]
            field_patterns["corrected"] = field_patterns["corrected"][-50:]

        patterns[field_name] = field_patterns
        profile.correction_patterns = patterns

        # Korrektur-Zaehler erhoehen
        profile.correction_count = (profile.correction_count or 0) + 1
        profile.last_correction_at = now

        # Pruefen ob automatische Regel erstellt werden soll
        await self._check_and_create_override(profile, field_name)

        # Confidence-Boost aktualisieren
        profile.confidence_boost = min(
            MAX_CONFIDENCE_BOOST,
            (profile.correction_count or 0) * BOOST_PER_CORRECTION,
        )

        await db.flush()

        logger.info(
            "learning_correction_recorded",
            company_id=str(company_id),
            document_id=str(document_id),
            profile_type=profile_type,
            profile_key=profile_key,
            field_name=field_name,
            correction_count=profile.correction_count,
            has_override=field_name in (profile.field_overrides or {}),
        )

        return profile

    async def _get_or_create_profile(
        self,
        db: AsyncSession,
        company_id: UUID,
        profile_type: str,
        profile_key: str,
    ) -> LearningProfile:
        """Lernprofil laden oder neu erstellen.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            profile_type: "supplier" oder "document_type"
            profile_key: Lieferantenname oder Dokumenttyp

        Returns:
            Existierendes oder neues LearningProfile
        """
        result = await db.execute(
            select(LearningProfile).where(
                and_(
                    LearningProfile.company_id == company_id,
                    LearningProfile.profile_type == profile_type,
                    LearningProfile.profile_key == profile_key,
                )
            )
        )
        profile = result.scalar_one_or_none()

        if profile is None:
            profile = LearningProfile(
                company_id=company_id,
                profile_type=profile_type,
                profile_key=profile_key,
                correction_count=0,
                correction_patterns={},
                field_overrides={},
                confidence_boost=0.0,
            )
            db.add(profile)
            await db.flush()

        return profile

    async def _check_and_create_override(
        self,
        profile: LearningProfile,
        field_name: str,
    ) -> None:
        """Prueft ob eine automatische Feld-Regel erstellt werden soll.

        Ab MIN_CORRECTIONS_FOR_OVERRIDE identischen Korrekturen fuer
        dasselbe Feld wird ein field_override erstellt.

        Args:
            profile: Lernprofil
            field_name: Name des Feldes
        """
        patterns = profile.correction_patterns or {}
        field_patterns = patterns.get(field_name, {})
        corrected_values = field_patterns.get("corrected", [])

        if len(corrected_values) < MIN_CORRECTIONS_FOR_OVERRIDE:
            return

        # Pruefen ob die letzten N Korrekturen identisch sind
        recent = corrected_values[-MIN_CORRECTIONS_FOR_OVERRIDE:]
        if len(set(recent)) == 1:
            # Alle gleich -> Override erstellen
            overrides = dict(profile.field_overrides or {})
            overrides[field_name] = {
                "rule": "learned_correction",
                "value": recent[0],
                "correction_count": len(corrected_values),
                "auto_created": True,
            }
            profile.field_overrides = overrides

            logger.info(
                "learning_override_created",
                profile_id=str(profile.id),
                field_name=field_name,
                override_value=recent[0][:100],
                correction_count=len(corrected_values),
            )

    async def get_learned_overrides(
        self,
        db: AsyncSession,
        company_id: UUID,
        supplier_name: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Gelernte Ueberschreibungen fuer Extraktion abrufen.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            supplier_name: Lieferantenname
            document_type: Dokumenttyp

        Returns:
            Dict {field_name: {rule, value, ...}}
        """
        profiles = await self._find_matching_profiles(
            db, company_id, supplier_name, document_type
        )

        # Overrides zusammenfuehren (Lieferant hat Vorrang vor Dokumenttyp)
        merged: Dict[str, Dict[str, str]] = {}
        for profile in profiles:
            if profile.field_overrides:
                for field_name, override in profile.field_overrides.items():
                    if field_name not in merged:
                        merged[field_name] = override

        return merged

    async def get_confidence_boost(
        self,
        db: AsyncSession,
        company_id: UUID,
        supplier_name: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> float:
        """Confidence-Boost basierend auf Lernhistorie.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            supplier_name: Lieferantenname
            document_type: Dokumenttyp

        Returns:
            Confidence-Boost als Float (0.0 bis MAX_CONFIDENCE_BOOST)
        """
        profiles = await self._find_matching_profiles(
            db, company_id, supplier_name, document_type
        )

        if not profiles:
            return 0.0

        # Hoechsten Boost verwenden
        return max(p.confidence_boost or 0.0 for p in profiles)

    async def _find_matching_profiles(
        self,
        db: AsyncSession,
        company_id: UUID,
        supplier_name: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> List[LearningProfile]:
        """Passende Lernprofile finden.

        Sucht zuerst nach Lieferant-Profil, dann nach Dokumenttyp-Profil.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            supplier_name: Lieferantenname
            document_type: Dokumenttyp

        Returns:
            Liste passender Profile (Lieferant zuerst, dann Dokumenttyp)
        """
        profiles: List[LearningProfile] = []

        if supplier_name:
            result = await db.execute(
                select(LearningProfile).where(
                    and_(
                        LearningProfile.company_id == company_id,
                        LearningProfile.profile_type == "supplier",
                        LearningProfile.profile_key == supplier_name.strip(),
                    )
                )
            )
            supplier_profile = result.scalar_one_or_none()
            if supplier_profile:
                profiles.append(supplier_profile)

        if document_type:
            result = await db.execute(
                select(LearningProfile).where(
                    and_(
                        LearningProfile.company_id == company_id,
                        LearningProfile.profile_type == "document_type",
                        LearningProfile.profile_key == document_type.strip(),
                    )
                )
            )
            doctype_profile = result.scalar_one_or_none()
            if doctype_profile:
                profiles.append(doctype_profile)

        return profiles

    async def get_learning_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, object]:
        """Statistiken zum Lernfortschritt.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID

        Returns:
            Dict mit Lernstatistiken
        """
        # Gesamtanzahl Profile
        total_result = await db.execute(
            select(func.count(LearningProfile.id)).where(
                LearningProfile.company_id == company_id
            )
        )
        total_profiles = total_result.scalar() or 0

        # Gesamtanzahl Korrekturen
        corrections_result = await db.execute(
            select(func.sum(LearningProfile.correction_count)).where(
                LearningProfile.company_id == company_id
            )
        )
        total_corrections = corrections_result.scalar() or 0

        # Profile mit Overrides (aktive Regeln)
        overrides_result = await db.execute(
            select(func.count(LearningProfile.id)).where(
                and_(
                    LearningProfile.company_id == company_id,
                    LearningProfile.field_overrides != {},
                )
            )
        )
        profiles_with_overrides = overrides_result.scalar() or 0

        # Durchschnittlicher Boost
        avg_boost_result = await db.execute(
            select(func.avg(LearningProfile.confidence_boost)).where(
                and_(
                    LearningProfile.company_id == company_id,
                    LearningProfile.confidence_boost > 0,
                )
            )
        )
        avg_boost = avg_boost_result.scalar() or 0.0

        # Profile nach Typ
        type_counts_result = await db.execute(
            select(
                LearningProfile.profile_type,
                func.count(LearningProfile.id),
            )
            .where(LearningProfile.company_id == company_id)
            .group_by(LearningProfile.profile_type)
        )
        type_counts = {row[0]: row[1] for row in type_counts_result.all()}

        return {
            "total_profiles": total_profiles,
            "total_corrections": total_corrections,
            "profiles_with_active_rules": profiles_with_overrides,
            "average_confidence_boost": round(float(avg_boost), 4),
            "profiles_by_type": type_counts,
            "min_corrections_for_rule": MIN_CORRECTIONS_FOR_OVERRIDE,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: Optional[ExtractionLearningService] = None


def get_extraction_learning_service() -> ExtractionLearningService:
    """Gibt die Singleton-Instanz des ExtractionLearningService zurueck."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ExtractionLearningService()
    return _service_instance
