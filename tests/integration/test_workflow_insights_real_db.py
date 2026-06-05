# -*- coding: utf-8 -*-
"""Integrationstests fuer WorkflowInsightsService gegen ECHTES Postgres.

Verifiziert die SQL-Semantik der Query-Rewrites (Bug #4), die Unit-Tests mit
gemockter DB NICHT abdecken koennen:
- polymorpher Join ApprovalRequest(entity_type="document", entity_id) ⋈ Document
- Supplier-Gruppierung via Document.business_entity_id ⋈ BusinessEntity
- Betrag aus ApprovalRequest.amount (nicht Document.total_amount)
- "Assignee"-Gruppierung via Join auf ApprovalStep.assigned_user_id
- Status-Filter ueber Enum-Member (native Enum speichert NAME "PENDING")
- strikte Multi-Tenant-Isolation (company_id)

Voraussetzung: ein Postgres mit dem realen Schema unter TEST_DATABASE_URL
(siehe scripts/dbtest/setup_real_test_db.sh). Ohne erreichbare DB werden die
Tests uebersprungen (kein False-Green).

Ausfuehrung (in CI / mit gesetztem TEST_DATABASE_URL):
    pytest tests/integration/test_workflow_insights_real_db.py -v -m integration
"""

import os
import re
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def _test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        return url
    base = os.getenv("DATABASE_URL")
    if not base:
        pytest.skip("Kein TEST_DATABASE_URL / DATABASE_URL gesetzt")
    base = re.sub(r"/[^/?]+(\?|$)", r"/ablage_test\1", base)
    # Async-Treiber erzwingen (CI setzt oft postgresql:// = sync)
    base = re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", base)
    return base


@pytest_asyncio.fixture
async def db_engine():
    # Funktions-Scope: jeder Test bekommt eine Engine, die an SEINEN Event-Loop
    # gebunden ist (asyncpg + pytest-asyncio vertragen kein Engine-Sharing ueber
    # Loops -> "unknown protocol state"). app.main-Import ist nach dem ersten Mal
    # gecached (kein Mehraufwand).
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    import app.main  # noqa: F401 - erprobter App-Import-Graph (volle, konsistente Mapper)
    from sqlalchemy.orm import configure_mappers
    configure_mappers()

    from app.db.models import Base
    engine = create_async_engine(_test_db_url(), echo=False, pool_pre_ping=True)
    try:
        # Selbst-enthaltend: Schema modell-treu via create_all bauen (kein Klon/Patch,
        # CI-faehig - nur ein leeres Postgres unter TEST_DATABASE_URL noetig).
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover - Infra-Skip (kein Postgres erreichbar)
        await engine.dispose()
        pytest.skip(f"Test-DB nicht erreichbar/baubar ({type(exc).__name__}): {str(exc)[:140]}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        try:
            yield s
        finally:
            await s.rollback()


# --------------------------------------------------------------------------
# Factories (nur Pflichtfelder + was die Queries brauchen)
# --------------------------------------------------------------------------

def _company(name):
    from app.db.models import Company
    return Company(id=uuid4(), name=name, legal_form="GmbH", kontenrahmen="SKR03", is_active=True)


def _entity(name):
    from app.db.models import BusinessEntity
    return BusinessEntity(id=uuid4(), entity_type="supplier", name=name)


def _document(company_id, entity_id):
    from app.db.models import Document
    return Document(id=uuid4(), filename="rechnung.pdf", original_filename="rechnung.pdf",
                    company_id=company_id, business_entity_id=entity_id)


def _approval(company_id, doc_id, amount):
    from app.db.models import ApprovalRequest, ApprovalStatus
    return ApprovalRequest(id=uuid4(), company_id=company_id, entity_type="document",
                           entity_id=doc_id, title="Rechnung", total_steps=1, current_step=1,
                           status=ApprovalStatus.PENDING, amount=Decimal(amount))


def _step(request_id, user_id, step=1):
    from app.db.models import ApprovalStep, ApprovalStatus
    return ApprovalStep(id=uuid4(), approval_request_id=request_id, step_number=step,
                        approver_type="user", approver_value=str(user_id),
                        assigned_user_id=user_id, status=ApprovalStatus.PENDING)


def _user(email):
    from app.db.models import User
    return User(id=uuid4(), email=email, username=email.split("@")[0], hashed_password="x")


async def _seed_supplier_batch(session, company_id, supplier_name, amounts):
    ent = _entity(supplier_name)
    session.add(ent)
    await session.flush()
    for amount in amounts:
        doc = _document(company_id, ent.id)
        session.add(doc)
        await session.flush()
        session.add(_approval(company_id, doc.id, amount))
    await session.flush()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_approvals_polymorpher_join_und_gruppierung(session):
    """3 pending Rechnungen desselben Lieferanten -> genau 1 BATCH_APPROVAL-Insight."""
    from app.services.orchestration.workflow_insights_service import WorkflowInsightsService
    from app.services.orchestration.proactive_insights_service import InsightType
    comp = _company("Firma A")
    session.add(comp)
    await session.flush()
    await _seed_supplier_batch(session, comp.id, "Lieferant ABC", ["500.00", "750.00", "300.00"])

    insights = await WorkflowInsightsService().suggest_batch_approvals(db=session, company_id=comp.id)

    assert len(insights) == 1
    assert insights[0].insight_type == InsightType.OPTIMIZATION
    assert "Lieferant ABC" in insights[0].title


@pytest.mark.asyncio
async def test_batch_approvals_unter_schwellwert(session):
    """2 Rechnungen (< Schwellwert 3) -> kein Insight."""
    from app.services.orchestration.workflow_insights_service import WorkflowInsightsService
    comp = _company("Firma A")
    session.add(comp)
    await session.flush()
    await _seed_supplier_batch(session, comp.id, "Lieferant Klein", ["100.00", "200.00"])

    insights = await WorkflowInsightsService().suggest_batch_approvals(db=session, company_id=comp.id)
    assert insights == []


@pytest.mark.asyncio
async def test_batch_approvals_tenant_isolation(session):
    """Firma A sieht NIE die Approvals von Firma B (company_id-Filter)."""
    from app.services.orchestration.workflow_insights_service import WorkflowInsightsService
    comp_a, comp_b = _company("Firma A"), _company("Firma B")
    session.add_all([comp_a, comp_b])
    await session.flush()
    await _seed_supplier_batch(session, comp_a.id, "Lieferant ABC", ["500.00", "750.00", "300.00"])
    await _seed_supplier_batch(session, comp_b.id, "Lieferant XYZ", ["100.00", "100.00", "100.00"])

    ins_a = await WorkflowInsightsService().suggest_batch_approvals(db=session, company_id=comp_a.id)
    ins_b = await WorkflowInsightsService().suggest_batch_approvals(db=session, company_id=comp_b.id)

    assert len(ins_a) == 1 and "Lieferant ABC" in ins_a[0].title
    assert all("XYZ" not in i.title for i in ins_a), "Tenant-Leak A<-B"
    assert len(ins_b) == 1 and "Lieferant XYZ" in ins_b[0].title
    assert all("ABC" not in i.title for i in ins_b), "Tenant-Leak B<-A"


@pytest.mark.asyncio
async def test_detect_bottlenecks_assignee_join(session):
    """User mit >= 5 pending Approvals (via ApprovalStep) -> 1 BOTTLENECK-Insight."""
    from app.services.orchestration.workflow_insights_service import WorkflowInsightsService
    from app.services.orchestration.proactive_insights_service import InsightType, InsightPriority
    comp = _company("Firma A")
    user = _user("ueberlastet@firma-a.de")
    session.add_all([comp, user])
    await session.flush()
    ent = _entity("Lieferant ABC")
    session.add(ent)
    await session.flush()
    for _ in range(6):  # >= _bottleneck_threshold (5)
        doc = _document(comp.id, ent.id)
        session.add(doc)
        await session.flush()
        appr = _approval(comp.id, doc.id, "100.00")
        session.add(appr)
        await session.flush()
        session.add(_step(appr.id, user.id))
    await session.flush()

    insights = await WorkflowInsightsService().detect_bottlenecks(db=session, company_id=comp.id)

    assert len(insights) >= 1
    assert any(i.insight_type == InsightType.WARNING and i.priority == InsightPriority.HIGH
               for i in insights)


@pytest.mark.asyncio
async def test_detect_bottlenecks_tenant_isolation(session):
    """Bottleneck-Erkennung leakt nicht ueber company_id."""
    from app.services.orchestration.workflow_insights_service import WorkflowInsightsService
    comp_a, comp_b = _company("Firma A"), _company("Firma B")
    user_b = _user("user-b@firma-b.de")
    session.add_all([comp_a, comp_b, user_b])
    await session.flush()
    ent = _entity("Lieferant B")
    session.add(ent)
    await session.flush()
    # Firma B: ein ueberlasteter User
    for _ in range(6):
        doc = _document(comp_b.id, ent.id)
        session.add(doc)
        await session.flush()
        appr = _approval(comp_b.id, doc.id, "100.00")
        session.add(appr)
        await session.flush()
        session.add(_step(appr.id, user_b.id))
    await session.flush()

    # Firma A hat nichts -> keine Bottlenecks; Firma B's Daten leaken nicht
    insights_a = await WorkflowInsightsService().detect_bottlenecks(db=session, company_id=comp_a.id)
    assert insights_a == []
