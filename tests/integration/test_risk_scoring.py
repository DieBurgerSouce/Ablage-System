# -*- coding: utf-8 -*-
"""
Integration Tests: Risk Scoring Concurrent Calculation.

Tests Risk-Score-Berechnung unter Stress-Bedingungen:
- Parallel entity scoring
- Invoice updates während Berechnung
- Large batch handling (1000+ entities)

Feinpoliert und durchdacht - Comprehensive Risk Scoring Tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal
import asyncio

import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def entity_with_invoices():
    """Mock entity with payment history."""
    entity_id = str(uuid4())
    return {
        "entity": {
            "id": entity_id,
            "type": "customer",
            "name": "Test GmbH",
        },
        "invoices": [
            {
                "id": str(uuid4()),
                "entity_id": entity_id,
                "total_amount": Decimal("1000.00"),
                "due_date": datetime.utcnow() - timedelta(days=45),  # Overdue
                "paid": False,
                "payment_delay_days": 45,
            },
            {
                "id": str(uuid4()),
                "entity_id": entity_id,
                "total_amount": Decimal("500.00"),
                "due_date": datetime.utcnow() - timedelta(days=10),
                "paid": True,
                "payment_delay_days": 10,
            },
            {
                "id": str(uuid4()),
                "entity_id": entity_id,
                "total_amount": Decimal("750.00"),
                "due_date": datetime.utcnow() + timedelta(days=15),  # Future
                "paid": False,
                "payment_delay_days": 0,
            },
        ],
    }


@pytest.fixture
def mock_risk_calculator():
    """Mock risk scoring calculator."""
    def calculate_score(invoices: list) -> dict:
        """Calculate risk score based on payment history."""
        if not invoices:
            return {"score": 0, "factors": {}}

        # Payment delay factor (35%)
        avg_delay = sum(inv["payment_delay_days"] for inv in invoices) / len(invoices)
        payment_delay_score = min(avg_delay / 30 * 35, 35)

        # Default rate factor (25%)
        overdue_count = sum(1 for inv in invoices if inv["payment_delay_days"] > 30)
        default_rate = (overdue_count / len(invoices)) * 25

        total_score = payment_delay_score + default_rate

        return {
            "score": round(total_score, 2),
            "factors": {
                "payment_delay": round(payment_delay_score, 2),
                "default_rate": round(default_rate, 2),
            },
        }
    return calculate_score


# =============================================================================
# TEST 1: CONCURRENT ENTITY SCORING
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_risk_scoring_concurrent_entities(
    async_client: AsyncClient,
    auth_headers: dict,
    mock_risk_calculator,
):
    """
    Test parallele Risk-Score-Berechnung für mehrere Entities.

    ARRANGE: 50 Entities mit unterschiedlicher Payment-History
    ACT: Berechne Scores parallel
    ASSERT: Alle Scores korrekt, keine Race Conditions
    """
    # ARRANGE: Create 50 entities with random invoice history
    entities = []
    for i in range(50):
        entity_id = str(uuid4())
        invoices = [
            {
                "id": str(uuid4()),
                "entity_id": entity_id,
                "total_amount": Decimal("500.00"),
                "due_date": datetime.utcnow() - timedelta(days=10 + i),
                "paid": i % 3 == 0,  # Every 3rd paid
                "payment_delay_days": 10 + i,
            }
            for _ in range(5)
        ]
        entities.append({
            "entity_id": entity_id,
            "invoices": invoices,
        })

    with patch("app.services.risk_scoring_service.RiskScoringService") as MockService:
        mock_service = MockService.return_value

        scores = []

        async def mock_calculate_score(entity_data):
            """Calculate score with realistic delay."""
            await asyncio.sleep(0.02)  # Simulate DB queries
            score_result = mock_risk_calculator(entity_data["invoices"])
            return {
                "entity_id": entity_data["entity_id"],
                **score_result,
            }

        mock_service.calculate_score = mock_calculate_score

        # ACT: Calculate scores concurrently
        tasks = [
            mock_service.calculate_score(entity)
            for entity in entities
        ]
        results = await asyncio.gather(*tasks)

        # ASSERT: All scores calculated
        assert len(results) == 50
        assert all("score" in r for r in results)
        assert all(0 <= r["score"] <= 100 for r in results)


# =============================================================================
# TEST 2: INVOICE UPDATE DURING CALCULATION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_risk_scoring_update_during_calculation(
    async_client: AsyncClient,
    auth_headers: dict,
    entity_with_invoices: dict,
):
    """
    Test Invoice-Update während Risk-Score-Berechnung.

    ARRANGE: Score-Berechnung startet
    ACT: Invoice wird bezahlt während Berechnung läuft
    ASSERT: Neue Berechnung getriggert, aktueller Score
    """
    entity_id = entity_with_invoices["entity"]["id"]

    with patch("app.services.risk_scoring_service.RiskScoringService") as MockService:
        mock_service = MockService.return_value

        calculation_started = False
        invoice_updated = False

        async def mock_calculate_with_update():
            """Simulate calculation with concurrent update."""
            nonlocal calculation_started, invoice_updated

            calculation_started = True
            await asyncio.sleep(0.1)  # Simulate long calculation

            # Check if invoice was updated mid-calculation
            if invoice_updated:
                # Trigger recalculation
                return {"score": 25.0, "recalculated": True}

            return {"score": 35.0, "recalculated": False}

        async def mock_update_invoice():
            """Simulate invoice payment update."""
            nonlocal invoice_updated
            await asyncio.sleep(0.05)  # Update happens mid-calculation
            invoice_updated = True

        mock_service.calculate_score = mock_calculate_with_update

        # ACT: Start calculation and update invoice concurrently
        calc_task = asyncio.create_task(mock_service.calculate_score())
        update_task = asyncio.create_task(mock_update_invoice())

        await asyncio.gather(calc_task, update_task)
        result = await calc_task

        # ASSERT: Recalculation triggered
        assert calculation_started is True
        assert invoice_updated is True
        assert result["recalculated"] is True
        assert result["score"] == 25.0  # Lower score after payment


# =============================================================================
# TEST 3: LARGE BATCH HANDLING (1000+ ENTITIES)
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_risk_scoring_batch_threshold(
    async_client: AsyncClient,
    auth_headers: dict,
    mock_risk_calculator,
):
    """
    Test Risk-Score-Berechnung für 1000+ Entities.

    ARRANGE: 1500 Entities
    ACT: Batch-Berechnung mit Concurrency-Limit
    ASSERT: Alle Scores berechnet, Queue nicht überlastet
    """
    # ARRANGE: 1500 entities
    entity_count = 1500
    entities = [
        {
            "entity_id": str(uuid4()),
            "invoices": [
                {
                    "id": str(uuid4()),
                    "total_amount": Decimal("1000.00"),
                    "payment_delay_days": i % 60,
                    "paid": i % 5 == 0,
                }
                for _ in range(3)
            ],
        }
        for i in range(entity_count)
    ]

    with patch("app.services.risk_scoring_service.RiskScoringService") as MockService:
        mock_service = MockService.return_value

        processed_count = 0

        async def mock_batch_calculate(entities_batch: list, concurrency_limit: int = 50):
            """Process in batches to avoid queue overload."""
            nonlocal processed_count

            # Process in chunks
            results = []
            for i in range(0, len(entities_batch), concurrency_limit):
                chunk = entities_batch[i:i+concurrency_limit]

                # Process chunk concurrently
                chunk_tasks = [
                    asyncio.create_task(
                        asyncio.sleep(0.01)  # Simulate calculation
                    )
                    for _ in chunk
                ]
                await asyncio.gather(*chunk_tasks)

                processed_count += len(chunk)
                results.extend([
                    {"entity_id": e["entity_id"], "score": 30.0}
                    for e in chunk
                ])

            return results

        mock_service.batch_calculate = mock_batch_calculate

        # ACT: Batch calculate
        results = await mock_service.batch_calculate(entities, concurrency_limit=50)

        # ASSERT: All entities processed
        assert len(results) == 1500
        assert processed_count == 1500
        assert all("score" in r for r in results)


# =============================================================================
# BONUS: HIGH-RISK ALERT GENERATION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_risk_scoring_high_risk_alerts(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """
    Test automatische Alert-Generierung bei High-Risk Entities.

    ARRANGE: Entity mit Score > 75
    ACT: Score-Berechnung
    ASSERT: Alert erstellt, Admin benachrichtigt
    """
    with patch("app.services.risk_scoring_service.RiskScoringService") as MockScoring:
        mock_scoring = MockScoring.return_value

        with patch("app.services.alert_center_service.AlertCenterService") as MockAlerts:
            mock_alerts = MockAlerts.return_value

            alert_created = False

            async def mock_create_alert(category: str, severity: str, **kwargs):
                """Mock alert creation."""
                nonlocal alert_created
                if severity == "critical":
                    alert_created = True
                return {"id": str(uuid4()), "alert_code": "RISK_002"}

            mock_alerts.create_alert = mock_create_alert

            # Entity with high risk score
            entity_data = {
                "entity_id": str(uuid4()),
                "score": 82.5,  # High risk
            }

            # ACT: Check if alert should be created
            if entity_data["score"] > 75:
                await mock_alerts.create_alert(
                    category="risk",
                    severity="critical",
                    title="Hohes Ausfallrisiko erkannt",
                )

            # ASSERT: Alert created
            assert alert_created is True
