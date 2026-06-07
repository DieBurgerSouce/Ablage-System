# -*- coding: utf-8 -*-
"""Regression test for the BPMN per-instance concurrency lock (Bug C).

The engine runs signal / timer-firing / continue_after_task as recursive
read-modify-write of an instance's token state with no row lock. The fix takes a
transaction-scoped Postgres advisory lock keyed on the instance id at each entry
point so those operations serialize per instance. This test guards that the lock
helper actually emits ``pg_advisory_xact_lock`` for the given instance.
"""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.bpmn.process_execution_service import acquire_instance_lock


@pytest.mark.asyncio
async def test_acquire_instance_lock_emits_advisory_lock() -> None:
    db = AsyncMock()
    instance_id = uuid4()

    await acquire_instance_lock(db, instance_id)

    db.execute.assert_awaited_once()
    args, _kwargs = db.execute.call_args
    sql = str(args[0])
    assert "pg_advisory_xact_lock" in sql
    # Keyed on the instance id, parameterized (no SQL injection surface).
    assert args[1] == {"iid": str(instance_id)}
