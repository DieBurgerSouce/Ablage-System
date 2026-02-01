# -*- coding: utf-8 -*-
"""
Unit tests for Enhanced Fraud Detection Service.

Tests:
- CEO Fraud Detection
- Duplicate Payment Detection
- IBAN Manipulation Detection
- Feature extraction
- Anomaly scoring

Feinpoliert und durchdacht - Enterprise Fraud Prevention Testing.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.ai.fraud_detection_service import (
    EnhancedFraudDetectionService,
    FraudDetectionResult,
    FraudIndicator,
    GERMAN_URGENCY_KEYWORDS,
    CEO_FRAUD_INDICATORS,
)
from app.services.ai.fraud_ml_model import (
    FraudFeatureExtractor,
    FraudAnomalyScorer,
    FeatureVector,
    AnomalyScore,
    FRAUD_FEATURES,
)
from app.db.models_fraud import (
    FraudScanType,
    FraudRiskLevel,
    FraudScanStatus,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def fraud_service(mock_session):
    """Create a fraud detection service with mocked session."""
    return EnhancedFraudDetectionService(mock_session)


@pytest.fixture
def feature_extractor(mock_session):
    """Create a feature extractor with mocked session."""
    return FraudFeatureExtractor(mock_session)


@pytest.fixture
def anomaly_scorer():
    """Create an anomaly scorer."""
    return FraudAnomalyScorer(contamination=0.1)


# =============================================================================
# CEO Fraud Detection Tests
# =============================================================================


class TestCEOFraudDetection:
    """Tests for CEO fraud detection."""

    def test_german_urgency_keywords_defined(self):
        """Verify German urgency keywords are defined."""
        assert len(GERMAN_URGENCY_KEYWORDS) > 0
        assert "dringend" in GERMAN_URGENCY_KEYWORDS
        assert "sofort" in GERMAN_URGENCY_KEYWORDS
        assert "vertraulich" in GERMAN_URGENCY_KEYWORDS
        assert "geheim" in GERMAN_URGENCY_KEYWORDS

    def test_ceo_fraud_indicators_weights_sum_to_one(self):
        """Verify CEO fraud indicator weights sum to approximately 1.0."""
        total = sum(CEO_FRAUD_INDICATORS.values())
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_detect_ceo_fraud_no_document(self, fraud_service, mock_session):
        """Test CEO fraud detection with missing document."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await fraud_service.detect_ceo_fraud(
            document_id=uuid4(),
            company_id=uuid4(),
        )

        assert result.scan_type == FraudScanType.CEO_FRAUD
        assert result.risk_score == 0.0
        assert result.confidence == 0.0
        assert len(result.indicators) == 0

    @pytest.mark.asyncio
    async def test_detect_ceo_fraud_with_urgency_language(self, fraud_service, mock_session):
        """Test CEO fraud detection with urgency language."""
        # Create mock document with urgency keywords
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.company_id = uuid4()
        mock_doc.extracted_data = {}
        mock_doc.extracted_text = "Dringende Zahlung erforderlich. Bitte sofort ueberweisen. Vertraulich."

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_doc)
        mock_session.execute.return_value = mock_result

        # Mock the store_scan_result to avoid DB issues
        with patch.object(fraud_service, "_store_scan_result", new_callable=AsyncMock):
            with patch.object(fraud_service, "_create_fraud_alert", new_callable=AsyncMock):
                result = await fraud_service.detect_ceo_fraud(
                    document_id=mock_doc.id,
                    company_id=mock_doc.company_id,
                )

        assert result.scan_type == FraudScanType.CEO_FRAUD
        assert result.risk_score > 0
        assert len(result.indicators) >= 1

        # Check for urgency indicator
        indicator_names = [ind.name for ind in result.indicators]
        assert "urgency_language" in indicator_names or "confidentiality_request" in indicator_names


# =============================================================================
# Duplicate Payment Detection Tests
# =============================================================================


class TestDuplicatePaymentDetection:
    """Tests for duplicate payment detection."""

    @pytest.mark.asyncio
    async def test_detect_duplicate_no_invoice(self, fraud_service, mock_session):
        """Test duplicate detection with missing invoice."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await fraud_service.detect_duplicate_payment(
            invoice_id=uuid4(),
            company_id=uuid4(),
        )

        assert result.scan_type == FraudScanType.DUPLICATE_PAYMENT
        assert result.risk_score == 0.0

    def test_create_invoice_hash_consistent(self, fraud_service):
        """Test that invoice hash is consistent."""
        mock_invoice = MagicMock()
        mock_invoice.invoice_number = "INV-001"
        mock_invoice.total_amount = Decimal("1000.00")
        mock_invoice.entity_id = uuid4()

        hash1 = fraud_service._create_invoice_hash(mock_invoice)
        hash2 = fraud_service._create_invoice_hash(mock_invoice)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hash length

    def test_create_invoice_hash_different_for_different_data(self, fraud_service):
        """Test that invoice hash differs for different data."""
        invoice1 = MagicMock()
        invoice1.invoice_number = "INV-001"
        invoice1.total_amount = Decimal("1000.00")
        invoice1.entity_id = uuid4()

        invoice2 = MagicMock()
        invoice2.invoice_number = "INV-002"
        invoice2.total_amount = Decimal("1000.00")
        invoice2.entity_id = invoice1.entity_id

        hash1 = fraud_service._create_invoice_hash(invoice1)
        hash2 = fraud_service._create_invoice_hash(invoice2)

        assert hash1 != hash2


# =============================================================================
# IBAN Manipulation Detection Tests
# =============================================================================


class TestIBANManipulationDetection:
    """Tests for IBAN manipulation detection."""

    @pytest.mark.asyncio
    async def test_detect_iban_manipulation_no_baseline(self, fraud_service, mock_session):
        """Test IBAN manipulation with no existing baseline."""
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        mock_session.execute.return_value = mock_result

        with patch.object(fraud_service, "_store_scan_result", new_callable=AsyncMock):
            result = await fraud_service.detect_iban_manipulation(
                entity_id=uuid4(),
                new_iban="DE89370400440532013000",
                company_id=uuid4(),
            )

        assert result.scan_type == FraudScanType.IBAN_MANIPULATION
        # No baseline = low risk for German IBAN
        assert result.risk_score <= 0.3

    @pytest.mark.asyncio
    async def test_detect_iban_manipulation_foreign_iban_no_baseline(self, fraud_service, mock_session):
        """Test IBAN manipulation with foreign IBAN and no baseline."""
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        mock_session.execute.return_value = mock_result

        with patch.object(fraud_service, "_store_scan_result", new_callable=AsyncMock):
            result = await fraud_service.detect_iban_manipulation(
                entity_id=uuid4(),
                new_iban="FR7630006000011234567890189",  # French IBAN
                company_id=uuid4(),
            )

        assert result.scan_type == FraudScanType.IBAN_MANIPULATION
        # Foreign IBAN for first entry = slightly elevated risk
        indicator_names = [ind.name for ind in result.indicators]
        assert "foreign_iban" in indicator_names

    @pytest.mark.asyncio
    async def test_get_iban_history(self, fraud_service, mock_session):
        """Test getting IBAN history for an entity."""
        mock_baseline = MagicMock()
        mock_baseline.id = uuid4()
        mock_baseline.iban = "DE89370400440532013000"
        mock_baseline.bic = "COBADEFFXXX"
        mock_baseline.bank_name = "Commerzbank"
        mock_baseline.first_seen_at = datetime.now(timezone.utc)
        mock_baseline.last_used_at = datetime.now(timezone.utc)
        mock_baseline.is_verified = True
        mock_baseline.is_active = True
        mock_baseline.verification_method = "manual"

        mock_baseline.to_dict = MagicMock(return_value={
            "id": str(mock_baseline.id),
            "iban_masked": "DE89...3000",
            "is_verified": True,
        })

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[mock_baseline])
        mock_session.execute.return_value = mock_result

        history = await fraud_service.get_iban_history(
            entity_id=uuid4(),
            company_id=uuid4(),
        )

        assert len(history) == 1
        assert history[0]["iban_masked"] == "DE89...3000"


# =============================================================================
# Feature Extractor Tests
# =============================================================================


class TestFraudFeatureExtractor:
    """Tests for fraud feature extraction."""

    def test_fraud_features_defined(self):
        """Verify fraud features are properly defined."""
        assert len(FRAUD_FEATURES) > 0
        assert "amount_zscore" in FRAUD_FEATURES
        assert "urgency_keyword_count" in FRAUD_FEATURES
        assert "iban_changed" in FRAUD_FEATURES

    def test_feature_vector_to_array(self):
        """Test converting feature vector to numpy array."""
        features = {
            "amount_zscore": 2.5,
            "is_weekend": 1.0,
            "urgency_keyword_count": 0.6,
        }
        vector = FeatureVector(features=features)

        array = vector.to_array(["amount_zscore", "is_weekend", "urgency_keyword_count"])
        assert len(array) == 3
        assert array[0] == 2.5
        assert array[1] == 1.0
        assert array[2] == 0.6

    def test_feature_vector_to_array_missing_feature(self):
        """Test that missing features default to 0."""
        features = {"amount_zscore": 2.5}
        vector = FeatureVector(features=features)

        array = vector.to_array(["amount_zscore", "missing_feature"])
        assert len(array) == 2
        assert array[0] == 2.5
        assert array[1] == 0.0

    def test_parse_amount_decimal(self, feature_extractor):
        """Test parsing decimal amounts."""
        result = feature_extractor._parse_amount(Decimal("1234.56"))
        assert result == Decimal("1234.56")

    def test_parse_amount_string(self, feature_extractor):
        """Test parsing string amounts."""
        result = feature_extractor._parse_amount("1234.56")
        assert result == Decimal("1234.56")

    def test_parse_amount_none(self, feature_extractor):
        """Test parsing None amount."""
        result = feature_extractor._parse_amount(None)
        assert result is None

    def test_is_round_amount(self, feature_extractor):
        """Test round amount detection."""
        assert feature_extractor._is_round_amount(1000.0) is True
        assert feature_extractor._is_round_amount(5000.0) is True
        assert feature_extractor._is_round_amount(10000.0) is True
        assert feature_extractor._is_round_amount(1234.56) is False
        assert feature_extractor._is_round_amount(50.0) is False  # Below threshold

    def test_count_urgency_keywords(self, feature_extractor):
        """Test urgency keyword counting."""
        text = "dringende zahlung erforderlich. bitte sofort ueberweisen."
        count = feature_extractor._count_urgency_keywords(text)
        assert count >= 2

    def test_has_confidentiality_request(self, feature_extractor):
        """Test confidentiality detection."""
        assert feature_extractor._has_confidentiality_request("vertraulich behandeln") is True
        assert feature_extractor._has_confidentiality_request("nur fuer sie bestimmt") is True
        assert feature_extractor._has_confidentiality_request("normale nachricht") is False

    def test_mentions_bank_change(self, feature_extractor):
        """Test bank change detection."""
        assert feature_extractor._mentions_bank_change("neue iban verwenden") is True
        assert feature_extractor._mentions_bank_change("bankverbindung geaendert") is True
        assert feature_extractor._mentions_bank_change("normale rechnung") is False


# =============================================================================
# Anomaly Scorer Tests
# =============================================================================


class TestFraudAnomalyScorer:
    """Tests for fraud anomaly scoring."""

    def test_score_empty_features(self, anomaly_scorer):
        """Test scoring with empty features."""
        vector = FeatureVector(features={})
        score = anomaly_scorer.score(vector)

        assert score.score == 0.0
        assert score.is_anomaly is False
        assert len(score.feature_contributions) == 0

    def test_score_low_risk_features(self, anomaly_scorer):
        """Test scoring with low-risk features."""
        vector = FeatureVector(features={
            "amount_zscore": 0.1,
            "is_weekend": 0.0,
            "urgency_keyword_count": 0.0,
        })
        score = anomaly_scorer.score(vector)

        assert score.score < 0.5
        assert score.is_anomaly is False

    def test_score_high_risk_features(self, anomaly_scorer):
        """Test scoring with high-risk features."""
        vector = FeatureVector(features={
            "amount_zscore": 1.0,
            "urgency_keyword_count": 1.0,
            "confidentiality_flag": 1.0,
            "bank_change_mention": 1.0,
            "is_new_entity": 1.0,
        })
        score = anomaly_scorer.score(vector)

        assert score.score > 0.5
        assert score.is_anomaly is True

    def test_top_contributors(self, anomaly_scorer):
        """Test getting top contributing features."""
        vector = FeatureVector(features={
            "amount_zscore": 0.8,
            "urgency_keyword_count": 0.3,
            "is_weekend": 0.1,
        })
        score = anomaly_scorer.score(vector)
        top = score.top_contributors

        assert len(top) <= 5
        # Top contributor should be amount_zscore (highest weighted)
        assert top[0][0] == "amount_zscore"

    def test_explain_anomaly(self, anomaly_scorer):
        """Test anomaly explanation generation."""
        vector = FeatureVector(features={
            "amount_zscore": 0.8,
            "urgency_keyword_count": 0.5,
        })
        score = anomaly_scorer.score(vector)
        explanation = anomaly_scorer.explain(score)

        assert "score" in explanation
        assert "is_anomaly" in explanation
        assert "risk_description" in explanation
        assert "top_contributors" in explanation

    def test_risk_descriptions(self, anomaly_scorer):
        """Test that risk descriptions are German."""
        descriptions = [
            anomaly_scorer._get_risk_description(0.1),
            anomaly_scorer._get_risk_description(0.3),
            anomaly_scorer._get_risk_description(0.5),
            anomaly_scorer._get_risk_description(0.7),
            anomaly_scorer._get_risk_description(0.9),
        ]

        for desc in descriptions:
            assert desc  # Not empty
            # Should contain German words
            assert any(word in desc.lower() for word in ["kritisch", "hoch", "mittel", "niedrig", "minimal"])


# =============================================================================
# Risk Level Calculation Tests
# =============================================================================


class TestRiskLevelCalculation:
    """Tests for risk level calculation."""

    def test_calculate_risk_level_low(self, fraud_service):
        """Test low risk level calculation."""
        level = fraud_service._calculate_risk_level(0.2)
        assert level == FraudRiskLevel.LOW

    def test_calculate_risk_level_medium(self, fraud_service):
        """Test medium risk level calculation."""
        level = fraud_service._calculate_risk_level(0.4)
        assert level == FraudRiskLevel.MEDIUM

    def test_calculate_risk_level_high(self, fraud_service):
        """Test high risk level calculation."""
        level = fraud_service._calculate_risk_level(0.7)
        assert level == FraudRiskLevel.HIGH

    def test_calculate_risk_level_critical(self, fraud_service):
        """Test critical risk level calculation."""
        level = fraud_service._calculate_risk_level(0.9)
        assert level == FraudRiskLevel.CRITICAL

    def test_calculate_confidence(self, fraud_service):
        """Test confidence calculation."""
        # No indicators
        conf = fraud_service._calculate_confidence(0, 5)
        assert conf == 0.1

        # Half coverage
        conf = fraud_service._calculate_confidence(3, 6)
        assert conf == 0.75

        # Full coverage
        conf = fraud_service._calculate_confidence(5, 5)
        assert conf == 0.95


# =============================================================================
# Integration Tests
# =============================================================================


class TestFraudDetectionIntegration:
    """Integration tests for fraud detection components."""

    def test_fraud_detection_result_is_suspicious(self):
        """Test FraudDetectionResult.is_suspicious property."""
        # Low risk
        result1 = FraudDetectionResult(
            scan_type=FraudScanType.CEO_FRAUD,
            risk_score=0.3,
            risk_level=FraudRiskLevel.LOW,
            confidence=0.5,
            indicators=[],
            explanation={},
        )
        assert result1.is_suspicious is False

        # High score
        result2 = FraudDetectionResult(
            scan_type=FraudScanType.CEO_FRAUD,
            risk_score=0.6,
            risk_level=FraudRiskLevel.MEDIUM,
            confidence=0.7,
            indicators=[],
            explanation={},
        )
        assert result2.is_suspicious is True

        # High risk level
        result3 = FraudDetectionResult(
            scan_type=FraudScanType.CEO_FRAUD,
            risk_score=0.4,
            risk_level=FraudRiskLevel.HIGH,
            confidence=0.6,
            indicators=[],
            explanation={},
        )
        assert result3.is_suspicious is True

    def test_fraud_indicator_creation(self):
        """Test FraudIndicator creation."""
        indicator = FraudIndicator(
            name="test_indicator",
            weight=0.5,
            description="Test beschreibung",
            details={"key": "value"},
        )

        assert indicator.name == "test_indicator"
        assert indicator.weight == 0.5
        assert indicator.description == "Test beschreibung"
        assert indicator.details["key"] == "value"
