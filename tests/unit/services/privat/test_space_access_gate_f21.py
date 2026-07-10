# -*- coding: utf-8 -*-
"""Regressionstest F-21: Privat-ACL-Gate darf keine nicht-existente Spalte abfragen.

Hintergrund (Adversarial-Review 2026-07, Finding F-21): Die beiden ACL-Gates
``space_service.get_with_access_check`` und
``document_service.get_by_id_with_space_and_access_check`` filterten die
Berechtigungstabelle ``PrivatSpaceAccess`` u. a. auf ``is_active == True``.
Diese Spalte existiert im Modell NICHT (die Aktiv-/Revoke-Logik trägt
``expires_at``). Der Nicht-Owner-Zweig warf dadurch einen ``AttributeError``
→ HTTP 500 statt des in DoD-8 zugesagten 403, und der geteilte Zugriff
(Shared Space) war komplett tot (auch mit gültigem Grant → 500).

Diese Tests sichern die Schema-Wahrheit, an der der Bug hing, und würden eine
Wiedereinführung der ``is_active``-Abfrage in den Gates auffallen lassen.
"""

from __future__ import annotations

import pytest

from app.db.models import PrivatSpaceAccess

pytestmark = pytest.mark.unit


def _columns() -> set:
    return {c.name for c in PrivatSpaceAccess.__table__.columns}


def test_privat_space_access_has_no_is_active_column() -> None:
    """PrivatSpaceAccess hat keine is_active-Spalte — die Gates dürfen sie nicht abfragen."""
    assert "is_active" not in _columns(), (
        "PrivatSpaceAccess.is_active existiert wieder — prüfen, ob die ACL-Gates "
        "(space_service.py / document_service.py) korrekt bleiben (F-21)."
    )


def test_privat_space_access_carries_revoke_via_expires_at() -> None:
    """expires_at ist die Revoke-/Aktiv-Logik, auf die die Gates sich stützen."""
    assert "expires_at" in _columns()


def test_acl_gate_source_does_not_reference_is_active() -> None:
    """Die beiden ACL-Gate-Quellen filtern PrivatSpaceAccess nicht auf is_active (F-21)."""
    import inspect

    from app.services.privat import document_service, space_service

    for module in (space_service, document_service):
        source = inspect.getsource(module)
        assert "PrivatSpaceAccess.is_active" not in source, (
            f"{module.__name__} referenziert PrivatSpaceAccess.is_active erneut — "
            "das warf HTTP 500 auf dem Nicht-Owner-Zweig (F-21)."
        )
