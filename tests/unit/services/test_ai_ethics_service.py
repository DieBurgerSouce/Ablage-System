# -*- coding: utf-8 -*-
"""Unit tests for AI Ethics Services."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.ai_ethics.bias_detector import BiasDetector, BiasReport, BiasDimension
from app.services.ai_ethics.explainability_service import (
    ExplainabilityService,
    Explanation,
    ExplanationFactor,
)
from app.services.ai_ethics.ethical_guardrails import EthicalGuardrails, GuardrailResult
from app.db.models import BusinessEntity, Document, InvoiceTracking


# =============================================================================
# Bias Detector Tests
# =============================================================================


@pytest.mark.asyncio
async def test_bias_detection_entity_type():
    """Bias Detector sollte Entity-Typ Bias erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Entities: Customers haben hohen Risk Score, Suppliers niedrigen
    # created_at MUSS gesetzt sein: _check_relationship_bias rechnet
    # (now - entity.created_at).days -> sonst MagicMock-Vergleich (TypeError).
    base_created = datetime.now(timezone.utc) - timedelta(days=200)
    customers = []
    for i in range(10):
        entity = MagicMock(spec=BusinessEntity)
        entity.entity_type = "customer"
        entity.risk_score = 80.0  # Hoch
        entity.created_at = base_created - timedelta(days=30 * i)
        customers.append(entity)

    suppliers = []
    for i in range(10):
        entity = MagicMock(spec=BusinessEntity)
        entity.entity_type = "supplier"
        entity.risk_score = 20.0  # Niedrig
        entity.created_at = base_created - timedelta(days=30 * i)
        suppliers.append(entity)

    all_entities = customers + suppliers

    entities_result = MagicMock()
    entities_result.scalars.return_value.all.return_value = all_entities

    mock_db.execute.return_value = entities_result

    detector = BiasDetector()
    report = await detector.detect_bias(company_id, mock_db)

    assert isinstance(report, BiasReport)
    # overall_fairness ist der Mittel der 3 Dimensionen. Hier ist NUR die
    # Entity-Typ-Achse verzerrt (Δ=60 -> 0.60), die anderen beiden fair (1.0),
    # also overall ~0.87 (<1.0 = Bias vorhanden, aber nicht auf allen Achsen).
    assert report.overall_fairness < 1.0  # Bias vorhanden
    assert len(report.dimensions) >= 3

    # Kern-Signal: Entity-Typ-Dimension MUSS den Bias flaggen.
    type_dim = next((d for d in report.dimensions if d.name == "Entity-Typ"), None)
    assert type_dim is not None
    assert type_dim.fairness_score < 0.8  # 60 Punkte Differenz -> 0.60


@pytest.mark.asyncio
async def test_bias_detection_no_bias():
    """Bias Detector sollte keine Bias bei fairen Daten erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Entities: Alle mit ähnlichen Risk Scores
    entities = []
    for i in range(20):
        entity = MagicMock(spec=BusinessEntity)
        entity.entity_type = "customer" if i % 2 == 0 else "supplier"
        entity.risk_score = 45.0 + (i % 10)  # 45-55 (geringe Varianz)
        entity.created_at = datetime.now(timezone.utc) - timedelta(days=30 * i)
        entities.append(entity)

    entities_result = MagicMock()
    entities_result.scalars.return_value.all.return_value = entities

    mock_db.execute.return_value = entities_result

    detector = BiasDetector()
    report = await detector.detect_bias(company_id, mock_db)

    assert report.overall_fairness > 0.85  # Sollte fair sein
    assert len(report.recommendations) <= 2


@pytest.mark.asyncio
async def test_bias_report_generation():
    """Bias Report sollte vollständigen Report generieren."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock diverse Entities
    entities = []
    for i in range(30):
        entity = MagicMock(spec=BusinessEntity)
        entity.entity_type = "customer" if i < 15 else "supplier"
        entity.risk_score = float(i * 3)  # 0, 3, 6, ..., 87
        entity.created_at = datetime.now(timezone.utc) - timedelta(days=30 * (i % 12))
        entities.append(entity)

    entities_result = MagicMock()
    entities_result.scalars.return_value.all.return_value = entities

    mock_db.execute.return_value = entities_result

    detector = BiasDetector()
    report = await detector.detect_bias(company_id, mock_db)

    assert isinstance(report, BiasReport)
    assert 0.0 <= report.overall_fairness <= 1.0
    assert len(report.dimensions) == 3  # Type, Distribution, Relationship
    assert isinstance(report.recommendations, list)
    assert report.generated_at is not None

    # Alle Dimensionen sollten vorhanden sein
    dim_names = {d.name for d in report.dimensions}
    assert "Entity-Typ" in dim_names
    assert "Risk-Score-Verteilung" in dim_names
    assert "Beziehungsdauer" in dim_names


# =============================================================================
# Explainability Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_explainability_risk_score():
    """Explainability sollte Risk Score Faktoren erklären."""
    mock_db = AsyncMock()
    entity_id = uuid4()

    # Mock Entity mit Risk Factors
    entity = MagicMock(spec=BusinessEntity)
    entity.id = entity_id
    entity.risk_score = 65.0
    entity.risk_factors = {
        "payment_delay_days": 25.0,
        "default_rate": 0.15,  # 15%
        "invoice_volume": 25000.0,
        "relationship_months": 18.0,
        "document_frequency": 3.5,
        "total_invoices": 50,
    }

    mock_db.get.return_value = entity

    service = ExplainabilityService()
    result = await service.explain_decision(entity_id, "risk_score", mock_db)

    assert result is not None
    assert isinstance(result, Explanation)
    assert result.decision_type == "risk_score"
    assert len(result.factors) == 5  # 5 Faktoren

    # Check Faktoren
    factor_names = {f.name for f in result.factors}
    assert "Zahlungsverhalten" in factor_names
    assert "Ausfallrate" in factor_names
    assert "Rechnungsvolumen" in factor_names
    assert "Beziehungsdauer" in factor_names
    assert "Transaktionsfrequenz" in factor_names

    # Check Gewichtungen summieren zu 1.0
    total_weight = sum(f.weight for f in result.factors)
    assert abs(total_weight - 1.0) < 0.01

    # Check Summary ist German
    assert result.summary is not None
    assert "Risiko" in result.summary


@pytest.mark.asyncio
async def test_explainability_auto_approval():
    """Explainability sollte Auto-Approval Entscheidung erklären."""
    mock_db = AsyncMock()
    invoice_id = uuid4()

    # Mock Invoice - InvoiceTracking-Spalte heisst 'amount' (nicht total_amount);
    # _explain_auto_approval liest invoice.amount. Restliche genutzte Felder
    # konkret setzen, damit spec-MagicMock keine ungesetzten Mock-Attribute
    # in Vergleiche einschleust (entity_id=None -> kein BusinessEntity-Lookup).
    invoice = MagicMock(spec=InvoiceTracking)
    invoice.id = invoice_id
    invoice.amount = 500.0
    invoice.entity_id = None
    invoice.invoice_number = "RE-2026-001"
    invoice.due_date = datetime.now(timezone.utc) + timedelta(days=14)

    mock_db.get.return_value = invoice

    service = ExplainabilityService()
    result = await service.explain_decision(invoice_id, "auto_approval", mock_db)

    assert result is not None
    assert result.decision_type == "auto_approval"
    assert len(result.factors) >= 3

    # Check Faktoren
    factor_names = {f.name for f in result.factors}
    assert "Betragsschwelle" in factor_names


@pytest.mark.asyncio
async def test_explainability_classification():
    """Explainability sollte Document Classification erklären."""
    mock_db = AsyncMock()
    document_id = uuid4()

    # Mock Document
    document = MagicMock(spec=Document)
    document.id = document_id
    document.document_type = "invoice"
    document.ocr_confidence = 0.92
    document.extracted_text = "Rechnung Betrag MwSt zahlbar"
    document.document_metadata = {}

    mock_db.get.return_value = document

    service = ExplainabilityService()
    result = await service.explain_decision(document_id, "document_classification", mock_db)

    assert result is not None
    assert result.decision_type == "document_classification"
    assert result.confidence == 0.92

    # Check OCR-Konfidenz Faktor
    ocr_factor = next((f for f in result.factors if f.name == "OCR-Konfidenz"), None)
    assert ocr_factor is not None
    assert ocr_factor.impact == "positive"  # 92% ist hoch


# =============================================================================
# Ethical Guardrails Tests
# =============================================================================


@pytest.mark.asyncio
async def test_guardrail_bulk_action_blocked():
    """Guardrail sollte Bulk-Aktionen blockieren."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: 15 Dokumente (> Threshold von 10)
    document_ids = [uuid4() for _ in range(15)]
    parameters = {"document_ids": document_ids}

    # Mock keine Invoices verknüpft
    invoices_result = MagicMock()
    invoices_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = invoices_result

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("delete_documents", parameters, company_id, mock_db)

    assert isinstance(result, GuardrailResult)
    assert result.allowed is False
    assert result.risk_level == "high"
    assert result.requires_human_review is True
    assert "15" in result.reason


@pytest.mark.asyncio
async def test_guardrail_high_value_warning():
    """Guardrail sollte bei hohen Beträgen warnen."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: Hoher Betrag (15000 EUR > Threshold 10000)
    entity_id = uuid4()
    parameters = {
        "amount": 15000.0,
        "entity_id": entity_id,
        "invoice_id": uuid4(),
    }

    # Mock Entity mit normalem Risk Score
    entity = MagicMock(spec=BusinessEntity)
    entity.risk_score = 40.0
    entity.company_id = company_id

    # Mock execute für SELECT mit company_id Filter
    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity
    mock_db.execute.return_value = entity_result

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("approve_payment", parameters, company_id, mock_db)

    assert result.allowed is False
    assert result.risk_level == "high"
    assert result.requires_human_review is True
    assert "15,000" in result.reason or "15000" in result.reason


@pytest.mark.asyncio
async def test_guardrail_allowed():
    """Guardrail sollte normale Aktionen erlauben."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: Normaler Betrag (500 EUR < Threshold 10000)
    entity_id = uuid4()
    parameters = {
        "amount": 500.0,
        "entity_id": entity_id,
        "invoice_id": uuid4(),
    }

    # Mock Entity mit niedrigem Risk Score
    entity = MagicMock(spec=BusinessEntity)
    entity.risk_score = 30.0
    entity.company_id = company_id

    # Mock execute für SELECT mit company_id Filter
    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity
    mock_db.execute.return_value = entity_result

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("approve_payment", parameters, company_id, mock_db)

    assert result.allowed is True
    assert result.risk_level == "low"
    assert result.requires_human_review is False


@pytest.mark.asyncio
async def test_guardrail_high_risk_entity():
    """Guardrail sollte bei High-Risk Entities blockieren."""
    mock_db = AsyncMock()
    company_id = uuid4()

    entity_id = uuid4()
    parameters = {
        "amount": 5000.0,  # Normaler Betrag
        "entity_id": entity_id,
        "invoice_id": uuid4(),
    }

    # Mock Entity mit HOHEM Risk Score (>75)
    entity = MagicMock(spec=BusinessEntity)
    entity.risk_score = 85.0  # HOCH
    entity.company_id = company_id

    # Mock execute für SELECT mit company_id Filter
    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity
    mock_db.execute.return_value = entity_result

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("approve_payment", parameters, company_id, mock_db)

    assert result.allowed is False
    assert result.risk_level == "high"
    assert result.requires_human_review is True
    assert "Risk Score" in result.reason


@pytest.mark.asyncio
async def test_guardrail_bulk_export_pii():
    """Guardrail sollte PII-Export blockieren."""
    mock_db = AsyncMock()
    company_id = uuid4()

    parameters = {
        "document_count": 50,
        "include_pii": True,  # PII enthalten
    }

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("bulk_export", parameters, company_id, mock_db)

    assert result.allowed is False
    assert result.risk_level == "high"
    assert result.requires_human_review is True
    assert "GDPR" in result.reason or "personenbezogenen" in result.reason


@pytest.mark.asyncio
async def test_guardrail_auto_approve_invoices():
    """Guardrail sollte Auto-Approve für viele Rechnungen blockieren."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: 15 Rechnungen (> Threshold 10)
    invoice_ids = [uuid4() for _ in range(15)]
    parameters = {
        "invoice_ids": invoice_ids,
        "total_amount": 15000.0,
    }

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("auto_approve_invoices", parameters, company_id, mock_db)

    assert result.allowed is False
    assert result.risk_level == "high"
    assert result.requires_human_review is True


# =============================================================================
# Fairness Metrics Tests
# =============================================================================


@pytest.mark.asyncio
async def test_fairness_metrics():
    """Bias Detector sollte Fairness Scores korrekt berechnen."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock perfekt balancierte Entities
    entities = []
    for i in range(40):
        entity = MagicMock(spec=BusinessEntity)
        entity.entity_type = "customer" if i % 2 == 0 else "supplier"
        entity.risk_score = 50.0  # Alle gleich
        entity.created_at = datetime.now(timezone.utc) - timedelta(days=180)  # Alle etabliert
        entities.append(entity)

    entities_result = MagicMock()
    entities_result.scalars.return_value.all.return_value = entities

    mock_db.execute.return_value = entities_result

    detector = BiasDetector()
    report = await detector.detect_bias(company_id, mock_db)

    # Alle Dimensionen sollten perfekt sein
    for dimension in report.dimensions:
        assert dimension.fairness_score >= 0.95


# =============================================================================
# Ethics Dashboard Tests
# =============================================================================


@pytest.mark.asyncio
async def test_ethics_dashboard():
    """Ethics Dashboard sollte aggregierte Metriken liefern."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Entities
    entities = []
    for i in range(50):
        entity = MagicMock(spec=BusinessEntity)
        entity.entity_type = "customer"
        entity.risk_score = float(i * 2)  # 0-100
        entity.created_at = datetime.now(timezone.utc) - timedelta(days=30 * (i % 24))
        entities.append(entity)

    entities_result = MagicMock()
    entities_result.scalars.return_value.all.return_value = entities

    mock_db.execute.return_value = entities_result

    # Bias Report
    detector = BiasDetector()
    bias_report = await detector.detect_bias(company_id, mock_db)

    # Dashboard Metriken
    dashboard = {
        "overall_fairness": bias_report.overall_fairness,
        "dimension_scores": {d.name: d.fairness_score for d in bias_report.dimensions},
        "recommendations": bias_report.recommendations,
    }

    assert "overall_fairness" in dashboard
    assert "dimension_scores" in dashboard
    assert len(dashboard["dimension_scores"]) == 3


@pytest.mark.asyncio
async def test_explainability_unknown_type():
    """Explainability sollte None für unbekannten Typ returnen."""
    mock_db = AsyncMock()
    decision_id = uuid4()

    service = ExplainabilityService()
    result = await service.explain_decision(decision_id, "unknown_type", mock_db)

    assert result is None


@pytest.mark.asyncio
async def test_guardrail_unknown_action():
    """Guardrail sollte unbekannte Aktion mit Review erlauben."""
    mock_db = AsyncMock()
    company_id = uuid4()
    parameters = {}

    guardrails = EthicalGuardrails()
    result = await guardrails.check_action("unknown_action", parameters, company_id, mock_db)

    assert result.allowed is True
    assert result.risk_level == "medium"
    assert result.requires_human_review is True
