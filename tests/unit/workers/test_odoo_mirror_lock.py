"""Tests fuer den Mirror-Overlap-Lock (F-04, Review-P2 / Runbook R-6).

Ohne Lock koennen sich zwei Spiegel-Laeufe derselben Connection ueberlappen
(Beat-Intervall 30 min vs. langer Backfill, manueller Trigger) -> Duplikat-
Pfad + Fehl-Alarme unter Concurrency. Der Lock ist ein Redis SET NX EX je
Connection (Muster: GPU-Lock in celery_app). Redis-Ausfall = fail-open
(der GoBD-Spiegel darf nicht an einem Lock-Hiccup sterben).
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

pytestmark = [pytest.mark.unit]


def _patch_redis(client: MagicMock):
    return patch(
        "app.workers.tasks.odoo_tasks._get_mirror_lock_client",
        return_value=client,
    )


def test_lock_wird_erworben():
    from app.workers.tasks.odoo_tasks import _try_acquire_mirror_lock

    redis = MagicMock()
    redis.set = MagicMock(return_value=True)
    connection_id = str(uuid4())

    with _patch_redis(redis):
        should_run, lock_value = _try_acquire_mirror_lock(connection_id)

    assert should_run is True
    assert lock_value
    args, kwargs = redis.set.call_args
    assert args[0] == f"ablage:odoo_mirror:lock:{connection_id}"
    assert kwargs["nx"] is True
    assert kwargs["ex"] > 0


def test_belegter_lock_ueberspringt_lauf():
    from app.workers.tasks.odoo_tasks import _try_acquire_mirror_lock

    redis = MagicMock()
    redis.set = MagicMock(return_value=None)  # NX: bereits gesetzt

    with _patch_redis(redis):
        should_run, lock_value = _try_acquire_mirror_lock(str(uuid4()))

    assert should_run is False
    assert lock_value is None


def test_redis_fehler_ist_fail_open():
    """Lock-Infrastruktur kaputt -> Lauf findet trotzdem statt (ohne Lock)."""
    from app.workers.tasks.odoo_tasks import _try_acquire_mirror_lock

    redis = MagicMock()
    redis.set = MagicMock(side_effect=RedisError("down"))

    with _patch_redis(redis):
        should_run, lock_value = _try_acquire_mirror_lock(str(uuid4()))

    assert should_run is True
    assert lock_value is None  # nichts zu releasen


def test_release_nur_bei_eigentum():
    from app.workers.tasks.odoo_tasks import _release_mirror_lock

    connection_id = str(uuid4())
    redis = MagicMock()
    redis.get = MagicMock(return_value=b"fremder-wert")
    redis.delete = MagicMock()

    with _patch_redis(redis):
        _release_mirror_lock(connection_id, "mein-wert")

    redis.delete.assert_not_called()


def test_release_loescht_eigenen_lock():
    from app.workers.tasks.odoo_tasks import _release_mirror_lock

    connection_id = str(uuid4())
    redis = MagicMock()
    redis.get = MagicMock(return_value=b"mein-wert")
    redis.delete = MagicMock()

    with _patch_redis(redis):
        _release_mirror_lock(connection_id, "mein-wert")

    redis.delete.assert_called_once_with(f"ablage:odoo_mirror:lock:{connection_id}")
