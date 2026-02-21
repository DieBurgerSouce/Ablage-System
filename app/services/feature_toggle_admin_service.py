# -*- coding: utf-8 -*-
"""
Service für die Admin-Verwaltung von Feature-Flags.

Bietet:
- Vollständige CRUD-Operationen für Feature-Flags mit Audit-Trail
- Per-User Overrides (target_users Liste)
- Rollout-Prozentsatz Verwaltung
- A/B Test Statistiken
- Lückenlosen Änderungsverlauf (feature_toggle_history)
"""

from __future__ import annotations

import hashlib
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func as sa_func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_cache
from app.core.safe_errors import safe_error_log
from app.db.models import FeatureFlag
from app.services.feature_flag_service import FEATURE_FLAG_CACHE_PREFIX

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Allowed action values stored in feature_toggle_history.action
# ---------------------------------------------------------------------------
ACTION_ENABLED = "enabled"
ACTION_DISABLED = "disabled"
ACTION_ROLLOUT_CHANGED = "rollout_changed"
ACTION_CONFIG_CHANGED = "config_changed"
ACTION_USER_OVERRIDE_SET = "user_override_set"
ACTION_USER_OVERRIDE_REMOVED = "user_override_removed"


# ---------------------------------------------------------------------------
# Internal helper – raw INSERT into feature_toggle_history
# ---------------------------------------------------------------------------

async def _write_history(
    db: AsyncSession,
    *,
    flag: FeatureFlag,
    action: str,
    old_value: Optional[Dict[str, object]],
    new_value: Optional[Dict[str, object]],
    changed_by_id: Optional[UUID],
    reason: Optional[str],
) -> None:
    """Schreibt einen Eintrag in feature_toggle_history.

    Verwendet ein rohes INSERT statt eines ORM-Modells, damit dieser
    Service ohne Circular-Import auf models.py auskommt.
    """
    try:
        await db.execute(
            text(
                "INSERT INTO feature_toggle_history "
                "(id, feature_flag_id, flag_name, action, old_value, new_value, "
                " changed_by_id, reason, created_at) "
                "VALUES (:id, :feature_flag_id, :flag_name, :action, "
                "        CAST(:old_value AS jsonb), CAST(:new_value AS jsonb), "
                "        :changed_by_id, :reason, :created_at)"
            ),
            {
                "id": str(uuid4()),
                "feature_flag_id": str(flag.id),
                "flag_name": flag.key,
                "action": action,
                "old_value": _jsonb_serialize(old_value),
                "new_value": _jsonb_serialize(new_value),
                "changed_by_id": str(changed_by_id) if changed_by_id else None,
                "reason": reason,
                "created_at": datetime.now(timezone.utc),
            },
        )
    except Exception as exc:
        # Non-fatal – we log and continue so the main operation isn't blocked
        logger.error("write_toggle_history_failed", **safe_error_log(exc), flag=flag.key)


def _jsonb_serialize(value: Optional[Dict[str, object]]) -> Optional[str]:
    """Wandelt ein Dict in einen JSON-String um (für CAST AS jsonb)."""
    if value is None:
        return None
    import json
    return json.dumps(value, default=str)


def _flag_snapshot(flag: FeatureFlag) -> Dict[str, object]:
    """Erstellt eine lesbare Momentaufnahme eines Feature-Flags für den Audit-Trail."""
    return {
        "enabled": flag.enabled,
        "rollout_percentage": flag.rollout_percentage,
        "target_tiers": flag.target_tiers or [],
        "target_users": flag.target_users or [],
        "variants": flag.variants or {},
        "config": flag.config or {},
        "starts_at": flag.starts_at.isoformat() if flag.starts_at else None,
        "ends_at": flag.ends_at.isoformat() if flag.ends_at else None,
    }


# ---------------------------------------------------------------------------
# Main Service
# ---------------------------------------------------------------------------

class FeatureToggleAdminService:
    """Admin-Service für Feature-Flag Verwaltung mit vollem Audit-Trail."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # List / Detail
    # ------------------------------------------------------------------

    async def list_flags(
        self,
        company_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, object]]:
        """Listet alle Feature-Flags mit aktuellem Status.

        Args:
            company_id: Wird für zukünftige Multi-Tenancy Erweiterungen
                        reserviert (Feature-Flags sind derzeit global).
            limit: Maximale Anzahl zurückgegebener Einträge.
            offset: Überspringene Einträge für Paginierung.

        Returns:
            Liste von Flag-Zusammenfassungen.
        """
        try:
            stmt = (
                select(FeatureFlag)
                .order_by(FeatureFlag.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            flags = list(result.scalars().all())

            return [self._flag_to_summary(f) for f in flags]
        except Exception as exc:
            logger.error("list_flags_failed", **safe_error_log(exc))
            return []

    async def get_flag_detail(
        self,
        flag_name: str,
        company_id: Optional[UUID] = None,
        history_limit: int = 10,
    ) -> Optional[Dict[str, object]]:
        """Ruft Detailinformationen zu einem Feature-Flag ab.

        Args:
            flag_name: Flag-Key (z.B. 'new_ocr_pipeline').
            company_id: Für künftige Multi-Tenancy reserviert.
            history_limit: Anzahl der letzten Verlaufseinträge.

        Returns:
            Detailansicht inkl. Verlauf oder None wenn nicht gefunden.
        """
        try:
            flag = await self._get_flag_by_name(flag_name)
            if flag is None:
                return None

            history = await self.get_flag_history(flag_name, company_id, history_limit)
            detail = self._flag_to_summary(flag)
            detail["history"] = history
            return detail
        except Exception as exc:
            logger.error("get_flag_detail_failed", **safe_error_log(exc), flag=flag_name)
            return None

    # ------------------------------------------------------------------
    # Toggle enabled/disabled
    # ------------------------------------------------------------------

    async def toggle_flag(
        self,
        flag_name: str,
        company_id: Optional[UUID],
        user_id: UUID,
        enabled: bool,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, object]]:
        """Aktiviert oder deaktiviert ein Feature-Flag.

        Args:
            flag_name: Flag-Key.
            company_id: Für künftige Multi-Tenancy reserviert.
            user_id: ID des Benutzers der die Änderung vornimmt.
            enabled: Neuer Aktivierungsstatus.
            reason: Optionaler Grund für die Änderung.

        Returns:
            Aktualisierte Flag-Zusammenfassung oder None bei Fehler.

        Raises:
            ValueError: Wenn das Flag nicht gefunden wird.
        """
        try:
            flag = await self._get_flag_by_name(flag_name)
            if flag is None:
                raise ValueError(f"Feature-Flag nicht gefunden: {flag_name}")

            old_snapshot = _flag_snapshot(flag)
            flag.enabled = enabled
            flag.updated_by_id = user_id

            await self.db.flush()

            new_snapshot = _flag_snapshot(flag)
            action = ACTION_ENABLED if enabled else ACTION_DISABLED

            await _write_history(
                self.db,
                flag=flag,
                action=action,
                old_value=old_snapshot,
                new_value=new_snapshot,
                changed_by_id=user_id,
                reason=reason,
            )

            await self.db.commit()
            await self.db.refresh(flag)
            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.info(
                "feature_flag_toggled",
                flag=flag_name,
                enabled=enabled,
                changed_by=str(user_id),
            )
            return self._flag_to_summary(flag)

        except ValueError:
            raise
        except Exception as exc:
            await self.db.rollback()
            logger.error("toggle_flag_failed", **safe_error_log(exc), flag=flag_name)
            raise ValueError(f"Fehler beim Umschalten des Feature-Flags: {flag_name}")

    # ------------------------------------------------------------------
    # Rollout percentage
    # ------------------------------------------------------------------

    async def update_rollout(
        self,
        flag_name: str,
        company_id: Optional[UUID],
        user_id: UUID,
        rollout_percentage: int,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, object]]:
        """Ändert den Rollout-Prozentsatz eines Feature-Flags.

        Args:
            flag_name: Flag-Key.
            company_id: Für künftige Multi-Tenancy reserviert.
            user_id: ID des ändernden Benutzers.
            rollout_percentage: Neuer Prozentsatz (0-100).
            reason: Optionaler Grund.

        Returns:
            Aktualisierte Flag-Zusammenfassung oder None bei Fehler.

        Raises:
            ValueError: Wenn das Flag nicht gefunden wird oder der Wert ungültig ist.
        """
        if not 0 <= rollout_percentage <= 100:
            raise ValueError(
                f"Rollout-Prozentsatz muss zwischen 0 und 100 liegen, "
                f"erhalten: {rollout_percentage}"
            )

        try:
            flag = await self._get_flag_by_name(flag_name)
            if flag is None:
                raise ValueError(f"Feature-Flag nicht gefunden: {flag_name}")

            old_snapshot = _flag_snapshot(flag)
            flag.rollout_percentage = rollout_percentage
            flag.updated_by_id = user_id

            await self.db.flush()

            new_snapshot = _flag_snapshot(flag)

            await _write_history(
                self.db,
                flag=flag,
                action=ACTION_ROLLOUT_CHANGED,
                old_value=old_snapshot,
                new_value=new_snapshot,
                changed_by_id=user_id,
                reason=reason,
            )

            await self.db.commit()
            await self.db.refresh(flag)
            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.info(
                "feature_flag_rollout_updated",
                flag=flag_name,
                rollout_percentage=rollout_percentage,
                changed_by=str(user_id),
            )
            return self._flag_to_summary(flag)

        except ValueError:
            raise
        except Exception as exc:
            await self.db.rollback()
            logger.error("update_rollout_failed", **safe_error_log(exc), flag=flag_name)
            raise ValueError(f"Fehler beim Aktualisieren des Rollout-Prozentsatzes: {flag_name}")

    # ------------------------------------------------------------------
    # Per-user overrides
    # ------------------------------------------------------------------

    async def set_flag_for_user(
        self,
        flag_name: str,
        target_user_id: str,
        company_id: Optional[UUID],
        enabled: bool,
        changed_by_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, object]]:
        """Setzt einen benutzerspezifischen Override für ein Feature-Flag.

        Fügt den Benutzer zur target_users-Liste hinzu (enable) oder
        entfernt ihn (disable). Die Änderung wird im Audit-Trail erfasst.

        Args:
            flag_name: Flag-Key.
            target_user_id: User-ID für den Override als String.
            company_id: Für künftige Multi-Tenancy reserviert.
            enabled: True = Benutzer explizit aktivieren, False = entfernen.
            changed_by_id: UUID des durchführenden Admins.

        Returns:
            Aktualisierte Flag-Zusammenfassung oder None bei Fehler.

        Raises:
            ValueError: Wenn das Flag nicht gefunden wird.
        """
        try:
            flag = await self._get_flag_by_name(flag_name)
            if flag is None:
                raise ValueError(f"Feature-Flag nicht gefunden: {flag_name}")

            old_snapshot = _flag_snapshot(flag)
            current_users: List[str] = list(flag.target_users or [])

            if enabled:
                if target_user_id not in current_users:
                    current_users.append(target_user_id)
                action = ACTION_USER_OVERRIDE_SET
            else:
                current_users = [u for u in current_users if u != target_user_id]
                action = ACTION_USER_OVERRIDE_REMOVED

            flag.target_users = current_users
            if changed_by_id:
                flag.updated_by_id = changed_by_id

            await self.db.flush()

            new_snapshot = _flag_snapshot(flag)
            reason = (
                f"Benutzer {target_user_id} {'aktiviert' if enabled else 'entfernt'}"
            )

            await _write_history(
                self.db,
                flag=flag,
                action=action,
                old_value=old_snapshot,
                new_value=new_snapshot,
                changed_by_id=changed_by_id,
                reason=reason,
            )

            await self.db.commit()
            await self.db.refresh(flag)
            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.info(
                "feature_flag_user_override_set",
                flag=flag_name,
                target_user=target_user_id,
                enabled=enabled,
            )
            return self._flag_to_summary(flag)

        except ValueError:
            raise
        except Exception as exc:
            await self.db.rollback()
            logger.error("set_flag_for_user_failed", **safe_error_log(exc), flag=flag_name)
            raise ValueError(f"Fehler beim Setzen des Benutzer-Overrides: {flag_name}")

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_flag_history(
        self,
        flag_name: str,
        company_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[Dict[str, object]]:
        """Ruft den Änderungsverlauf eines Feature-Flags ab.

        Args:
            flag_name: Flag-Key.
            company_id: Für künftige Multi-Tenancy reserviert.
            limit: Maximale Anzahl zurückgegebener Einträge.

        Returns:
            Liste von Verlaufseinträgen, neueste zuerst.
        """
        try:
            rows = await self.db.execute(
                text(
                    "SELECT id, feature_flag_id, flag_name, action, "
                    "       old_value, new_value, changed_by_id, reason, created_at "
                    "FROM feature_toggle_history "
                    "WHERE flag_name = :flag_name "
                    "ORDER BY created_at DESC "
                    "LIMIT :limit"
                ),
                {"flag_name": flag_name, "limit": limit},
            )
            return [
                {
                    "id": str(row.id),
                    "feature_flag_id": str(row.feature_flag_id) if row.feature_flag_id else None,
                    "flag_name": row.flag_name,
                    "action": row.action,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                    "changed_by_id": str(row.changed_by_id) if row.changed_by_id else None,
                    "reason": row.reason,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows.fetchall()
            ]
        except Exception as exc:
            logger.error("get_flag_history_failed", **safe_error_log(exc), flag=flag_name)
            return []

    # ------------------------------------------------------------------
    # A/B test results
    # ------------------------------------------------------------------

    async def get_ab_test_results(
        self,
        flag_name: str,
        company_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, object]]:
        """Berechnet A/B Test Statistiken für ein Feature-Flag.

        Verwendet deterministische SHA-256 Benutzer-Zuweisung (analog
        zu FeatureFlag.get_variant_for_user) und schätzt die Verteilung
        über die gespeicherten target_users.

        Args:
            flag_name: Flag-Key.
            company_id: Für künftige Multi-Tenancy reserviert.

        Returns:
            A/B Test Zusammenfassung oder None wenn kein A/B Test konfiguriert.
        """
        try:
            flag = await self._get_flag_by_name(flag_name)
            if flag is None:
                return None

            if not flag.variants:
                return {
                    "flag_name": flag_name,
                    "has_ab_test": False,
                    "message": "Kein A/B Test konfiguriert",
                    "variants": {},
                    "total_users_in_target": 0,
                }

            variants: Dict[str, int] = flag.variants or {}
            target_users: List[str] = flag.target_users or []
            variant_counts: Dict[str, int] = {v: 0 for v in variants}

            # Simulate deterministic assignment for users in target_users
            for uid in target_users:
                hash_input = f"{flag.key}:variant:{uid}".encode()
                hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16) % 100
                cumulative = 0
                for variant_name, percentage in variants.items():
                    cumulative += percentage
                    if hash_value < cumulative:
                        variant_counts[variant_name] = variant_counts.get(variant_name, 0) + 1
                        break

            total = len(target_users)
            variant_stats: Dict[str, object] = {
                name: {
                    "count": count,
                    "percentage_of_targets": round(count / total * 100, 2) if total > 0 else 0.0,
                    "configured_weight": variants.get(name, 0),
                }
                for name, count in variant_counts.items()
            }

            return {
                "flag_name": flag_name,
                "has_ab_test": True,
                "rollout_percentage": flag.rollout_percentage,
                "total_users_in_target": total,
                "variants": variant_stats,
                "is_active": flag.is_active(),
            }
        except Exception as exc:
            logger.error("get_ab_test_results_failed", **safe_error_log(exc), flag=flag_name)
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_flag_by_name(self, flag_name: str) -> Optional[FeatureFlag]:
        """Lädt ein Feature-Flag anhand des Keys aus der Datenbank."""
        stmt = select(FeatureFlag).where(FeatureFlag.key == flag_name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _flag_to_summary(flag: FeatureFlag) -> Dict[str, object]:
        """Wandelt ein FeatureFlag-Modell in ein serialisierbares Dict um."""
        return {
            "id": str(flag.id),
            "key": flag.key,
            "name": flag.name,
            "description": flag.description,
            "enabled": flag.enabled,
            "is_active": flag.is_active(),
            "rollout_percentage": flag.rollout_percentage,
            "target_tiers": flag.target_tiers or [],
            "target_users": flag.target_users or [],
            "has_ab_test": bool(flag.variants),
            "variants": flag.variants or {},
            "starts_at": flag.starts_at.isoformat() if flag.starts_at else None,
            "ends_at": flag.ends_at.isoformat() if flag.ends_at else None,
            "config": flag.config or {},
            "created_by_id": str(flag.created_by_id) if flag.created_by_id else None,
            "updated_by_id": str(flag.updated_by_id) if flag.updated_by_id else None,
            "created_at": flag.created_at.isoformat() if flag.created_at else None,
            "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_feature_toggle_admin_service(db: AsyncSession) -> FeatureToggleAdminService:
    """Factory für FeatureToggleAdminService."""
    return FeatureToggleAdminService(db)
