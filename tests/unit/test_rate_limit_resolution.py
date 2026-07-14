# -*- coding: utf-8 -*-
"""Regressionstest F-P1-003 (Perception-Audit 2026-07-12).

check_rate_limit codierte 10 Requests/Stunde fuer Free-Tier hart — normale
Buero-Nutzer waren nach 10 Such-/Listen-Aufrufen eine Stunde gesperrt (429,
Retry-After 3600). resolve_user_hourly_rate_limit verdrahtet stattdessen die
RATE_LIMIT_*_HOURLY-Settings und das Admin-Console-Override
users.rate_limit_hourly.
"""
from types import SimpleNamespace

from app.api.dependencies import resolve_user_hourly_rate_limit
from app.core.config import settings


def _user(**kwargs) -> SimpleNamespace:
    base = {"is_superuser": False, "tier": "free", "rate_limit_hourly": None}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_free_tier_nutzt_setting_statt_10():
    limit = resolve_user_hourly_rate_limit(_user())
    assert limit == settings.RATE_LIMIT_FREE_HOURLY
    # Kern der Regression: Buero-Nutzer duerfen nicht nach 10 Requests/h gesperrt sein
    assert limit >= 100, (
        f"Free-Tier-Limit {limit}/h ist fuer interaktive Buero-Nutzung zu niedrig "
        "(Regression F-P1-003: vorher hart codierte 10/h)"
    )


def test_premium_tier_nutzt_setting():
    assert (
        resolve_user_hourly_rate_limit(_user(tier="premium"))
        == settings.RATE_LIMIT_PREMIUM_HOURLY
    )


def test_superuser_nutzt_admin_setting():
    assert (
        resolve_user_hourly_rate_limit(_user(is_superuser=True))
        == settings.RATE_LIMIT_ADMIN_HOURLY
    )


def test_user_override_gewinnt_vor_tier():
    assert resolve_user_hourly_rate_limit(_user(rate_limit_hourly=42)) == 42
    assert (
        resolve_user_hourly_rate_limit(_user(tier="premium", rate_limit_hourly=7)) == 7
    )


def test_override_null_oder_none_faellt_auf_tier_zurueck():
    assert (
        resolve_user_hourly_rate_limit(_user(rate_limit_hourly=0))
        == settings.RATE_LIMIT_FREE_HOURLY
    )
    assert (
        resolve_user_hourly_rate_limit(_user(rate_limit_hourly=None))
        == settings.RATE_LIMIT_FREE_HOURLY
    )


def test_superuser_ignoriert_override():
    assert (
        resolve_user_hourly_rate_limit(_user(is_superuser=True, rate_limit_hourly=5))
        == settings.RATE_LIMIT_ADMIN_HOURLY
    )
