"""W1 Pipeline-Idempotenz: ``_claim_pipeline_job`` / ``_finish_pipeline_job``.

Verhindert, dass doppelte Celery-Zustellungen (acks_late) oder parallele
Laeufe dasselbe Dokument mehrfach durch die Pipeline schicken (doppelte
Entity-Extraktion/Inserts). Grundlage: Partial-Unique-Index
``uq_processing_jobs_active_per_doc_type`` (Migration 268, via Modell auch
in create_all-Datenbanken vorhanden).

Braucht PostgreSQL (``test_db``-Fixture); ohne DB: Laufzeit-Skip.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Document, ProcessingJob
from app.workers.pipeline_tasks import (
    STALE_CLAIM_SECONDS,
    _claim_pipeline_job,
    _finish_pipeline_job,
)


async def _seed_document(session: AsyncSession) -> Document:
    company = Company(id=uuid.uuid4(), name="Pipeline Test GmbH")
    session.add(company)
    await session.flush()
    doc = Document(
        id=uuid.uuid4(),
        filename="claim_test.pdf",
        original_filename="claim_test.pdf",
        company_id=company.id,
    )
    session.add(doc)
    await session.flush()
    return doc


@pytest.mark.asyncio
async def test_first_claim_succeeds(test_db: AsyncSession) -> None:
    doc = await _seed_document(test_db)

    proceed, job_id = await _claim_pipeline_job(test_db, str(doc.id), "task-1")

    assert proceed is True
    assert job_id is not None


@pytest.mark.asyncio
async def test_duplicate_delivery_skips_second_run(test_db: AsyncSession) -> None:
    """Fremde task_id auf aktivem Claim -> Duplikat, zweiter Lauf skippt."""
    doc = await _seed_document(test_db)

    proceed1, _job1 = await _claim_pipeline_job(test_db, str(doc.id), "task-1")
    proceed2, job2 = await _claim_pipeline_job(test_db, str(doc.id), "task-2")

    assert proceed1 is True
    assert proceed2 is False
    assert job2 is None


@pytest.mark.asyncio
async def test_same_task_retry_may_continue(test_db: AsyncSession) -> None:
    """Celery-Retry (gleiche task_id) darf den eigenen Claim fortsetzen."""
    doc = await _seed_document(test_db)

    _, job1 = await _claim_pipeline_job(test_db, str(doc.id), "task-1")
    proceed, job2 = await _claim_pipeline_job(test_db, str(doc.id), "task-1")

    assert proceed is True
    assert job2 == job1


@pytest.mark.asyncio
async def test_stale_claim_taken_over(test_db: AsyncSession) -> None:
    """Verwaister Claim (Worker-Crash) blockiert die Verarbeitung nicht ewig."""
    doc = await _seed_document(test_db)
    _, job1 = await _claim_pipeline_job(test_db, str(doc.id), "task-tot")

    job = (
        await test_db.execute(select(ProcessingJob).where(ProcessingJob.id == job1))
    ).scalar_one()
    job.started_at = datetime.now(UTC) - timedelta(
        seconds=STALE_CLAIM_SECONDS + 60
    )
    await test_db.commit()

    proceed, job2 = await _claim_pipeline_job(test_db, str(doc.id), "task-neu")

    assert proceed is True
    assert job2 == job1


@pytest.mark.asyncio
async def test_finish_releases_claim_for_next_run(test_db: AsyncSession) -> None:
    """Nach failed/completed ist ein neuer Lauf wieder moeglich."""
    doc = await _seed_document(test_db)
    _, job1 = await _claim_pipeline_job(test_db, str(doc.id), "task-1")

    await _finish_pipeline_job(test_db, job1, success=False, error="kaputt")

    proceed, job2 = await _claim_pipeline_job(test_db, str(doc.id), "task-2")
    assert proceed is True
    assert job2 is not None
    assert job2 != job1

    failed = (
        await test_db.execute(select(ProcessingJob).where(ProcessingJob.id == job1))
    ).scalar_one()
    assert failed.status == "failed"
    assert "kaputt" in (failed.error_message or "")
