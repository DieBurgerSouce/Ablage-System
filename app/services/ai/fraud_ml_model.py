# -*- coding: utf-8 -*-
"""
Fraud Detection ML Model Service for Ablage-System.

ML components for fraud detection:
- Feature extraction from documents and transactions
- Anomaly scoring using Isolation Forest
- Explainability for fraud alerts (SHAP-like feature importance)

SECURITY: NEVER log actual values, only feature names and scores.

Feinpoliert und durchdacht - ML-based Fraud Detection.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Feature Definitions
# =============================================================================

class FeatureType(str, Enum):
    """Types of features used in fraud detection."""
    NUMERICAL = "numerical"
    CATEGORICAL = "categorical"
    TEMPORAL = "temporal"
    TEXT = "text"
    BOOLEAN = "boolean"


@dataclass
class FeatureDefinition:
    """Definition of a feature for fraud detection."""
    name: str
    feature_type: FeatureType
    description: str
    weight: float = 1.0
    is_normalized: bool = True


# Feature catalog for fraud detection
FRAUD_FEATURES: Dict[str, FeatureDefinition] = {
    # Amount features
    "amount_zscore": FeatureDefinition(
        name="amount_zscore",
        feature_type=FeatureType.NUMERICAL,
        description="Z-Score des Betrags gegenüber Historik",
        weight=1.5,
    ),
    "amount_deviation_pct": FeatureDefinition(
        name="amount_deviation_pct",
        feature_type=FeatureType.NUMERICAL,
        description="Prozentuale Abweichung vom Median",
        weight=1.2,
    ),
    "is_round_amount": FeatureDefinition(
        name="is_round_amount",
        feature_type=FeatureType.BOOLEAN,
        description="Betrag ist verdaechtig rund",
        weight=0.8,
    ),

    # Temporal features
    "is_weekend": FeatureDefinition(
        name="is_weekend",
        feature_type=FeatureType.BOOLEAN,
        description="Erstellt am Wochenende",
        weight=0.6,
    ),
    "is_after_hours": FeatureDefinition(
        name="is_after_hours",
        feature_type=FeatureType.BOOLEAN,
        description="Erstellt ausserhalb Geschäftszeiten",
        weight=0.5,
    ),
    "days_since_last_invoice": FeatureDefinition(
        name="days_since_last_invoice",
        feature_type=FeatureType.NUMERICAL,
        description="Tage seit letzter Rechnung dieses Lieferanten",
        weight=0.7,
    ),

    # Entity features
    "is_new_entity": FeatureDefinition(
        name="is_new_entity",
        feature_type=FeatureType.BOOLEAN,
        description="Neuer/unbekannter Geschäftspartner",
        weight=1.3,
    ),
    "entity_invoice_count": FeatureDefinition(
        name="entity_invoice_count",
        feature_type=FeatureType.NUMERICAL,
        description="Anzahl bisheriger Rechnungen von diesem Partner",
        weight=0.5,
    ),
    "entity_risk_score": FeatureDefinition(
        name="entity_risk_score",
        feature_type=FeatureType.NUMERICAL,
        description="Risiko-Score des Geschäftspartners",
        weight=1.0,
    ),

    # Text features
    "urgency_keyword_count": FeatureDefinition(
        name="urgency_keyword_count",
        feature_type=FeatureType.NUMERICAL,
        description="Anzahl Dringlichkeits-Schlagwoerter",
        weight=1.4,
    ),
    "confidentiality_flag": FeatureDefinition(
        name="confidentiality_flag",
        feature_type=FeatureType.BOOLEAN,
        description="Vertraulichkeitsanfrage erkannt",
        weight=1.2,
    ),
    "bank_change_mention": FeatureDefinition(
        name="bank_change_mention",
        feature_type=FeatureType.BOOLEAN,
        description="Bankverbindungsänderung erwaehnt",
        weight=1.5,
    ),

    # Duplicate features
    "duplicate_hash_match": FeatureDefinition(
        name="duplicate_hash_match",
        feature_type=FeatureType.BOOLEAN,
        description="Exaktes Duplikat erkannt",
        weight=2.0,
    ),
    "similar_invoice_count": FeatureDefinition(
        name="similar_invoice_count",
        feature_type=FeatureType.NUMERICAL,
        description="Anzahl ähnlicher Rechnungen",
        weight=1.0,
    ),

    # IBAN features
    "iban_changed": FeatureDefinition(
        name="iban_changed",
        feature_type=FeatureType.BOOLEAN,
        description="IBAN weicht von Baseline ab",
        weight=1.8,
    ),
    "iban_country_changed": FeatureDefinition(
        name="iban_country_changed",
        feature_type=FeatureType.BOOLEAN,
        description="IBAN-Land hat sich geändert",
        weight=1.5,
    ),
    "recent_iban_changes": FeatureDefinition(
        name="recent_iban_changes",
        feature_type=FeatureType.NUMERICAL,
        description="Anzahl IBAN-Änderungen in 90 Tagen",
        weight=1.2,
    ),
}


@dataclass
class FeatureVector:
    """Extracted feature vector for a sample."""
    features: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_array(self, feature_names: List[str]) -> np.ndarray:
        """Convert to numpy array in specified feature order."""
        return np.array([self.features.get(name, 0.0) for name in feature_names])


@dataclass
class AnomalyScore:
    """Result of anomaly scoring."""
    score: float  # 0.0 - 1.0 (higher = more anomalous)
    feature_contributions: Dict[str, float]  # Feature name -> contribution
    threshold: float
    is_anomaly: bool

    @property
    def top_contributors(self) -> List[Tuple[str, float]]:
        """Get top contributing features."""
        sorted_features = sorted(
            self.feature_contributions.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        return sorted_features[:5]


# =============================================================================
# Feature Extractor
# =============================================================================

class FraudFeatureExtractor:
    """
    Extracts features from documents and transactions for fraud detection.

    Features are designed to capture fraud signals while
    maintaining privacy (no actual values stored).
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize feature extractor."""
        self.session = session
        self._historical_cache: Dict[UUID, Dict[str, float]] = {}

    async def extract_document_features(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> FeatureVector:
        """
        Extract features from a document.

        Args:
            document_id: Document to analyze
            company_id: Company context

        Returns:
            FeatureVector with extracted features
        """
        features: Dict[str, float] = {}

        # Load document
        stmt = select(Document).where(Document.id == document_id)
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return FeatureVector(features={}, metadata={"error": "document_not_found"})

        extracted_data = doc.extracted_data or {}
        text_content = (doc.extracted_text or "").lower()

        # Amount features
        amount = self._parse_amount(extracted_data.get("total_gross"))
        if amount:
            hist_stats = await self._get_historical_stats(company_id)
            if hist_stats.get("median", 0) > 0:
                features["amount_zscore"] = self._calculate_zscore(
                    float(amount),
                    hist_stats.get("mean", 0),
                    hist_stats.get("std", 1),
                )
                features["amount_deviation_pct"] = (
                    float(amount) - hist_stats["median"]
                ) / hist_stats["median"]

            features["is_round_amount"] = 1.0 if self._is_round_amount(float(amount)) else 0.0

        # Temporal features
        if doc.created_at:
            features["is_weekend"] = 1.0 if doc.created_at.weekday() >= 5 else 0.0
            features["is_after_hours"] = 1.0 if (
                doc.created_at.hour < 7 or doc.created_at.hour > 19
            ) else 0.0

        # Text features
        urgency_count = self._count_urgency_keywords(text_content)
        features["urgency_keyword_count"] = min(urgency_count / 5.0, 1.0)
        features["confidentiality_flag"] = 1.0 if self._has_confidentiality_request(text_content) else 0.0
        features["bank_change_mention"] = 1.0 if self._mentions_bank_change(text_content) else 0.0

        # Entity features
        entity_id = doc.business_entity_id
        if entity_id:
            entity_stats = await self._get_entity_stats(entity_id, company_id)
            features["is_new_entity"] = 1.0 if entity_stats.get("invoice_count", 0) < 3 else 0.0
            features["entity_invoice_count"] = min(entity_stats.get("invoice_count", 0) / 20.0, 1.0)
            features["entity_risk_score"] = entity_stats.get("risk_score", 0.5)

        return FeatureVector(
            features=features,
            metadata={
                "document_id": str(document_id),
                "feature_count": len(features),
            },
        )

    async def extract_invoice_features(
        self,
        invoice_id: UUID,
        company_id: UUID,
    ) -> FeatureVector:
        """
        Extract features from an invoice for duplicate detection.

        Args:
            invoice_id: Invoice to analyze
            company_id: Company context

        Returns:
            FeatureVector with extracted features
        """
        features: Dict[str, float] = {}

        stmt = select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        result = await self.session.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            return FeatureVector(features={}, metadata={"error": "invoice_not_found"})

        # Amount features
        if invoice.total_amount:
            hist_stats = await self._get_historical_stats(company_id)
            if hist_stats.get("median", 0) > 0:
                features["amount_zscore"] = self._calculate_zscore(
                    float(invoice.total_amount),
                    hist_stats.get("mean", 0),
                    hist_stats.get("std", 1),
                )
            features["is_round_amount"] = 1.0 if self._is_round_amount(float(invoice.total_amount)) else 0.0

        # Duplicate features
        similar_count = await self._count_similar_invoices(
            invoice.total_amount,
            invoice.entity_id,
            invoice_id,
            company_id,
        )
        features["similar_invoice_count"] = min(similar_count / 3.0, 1.0)

        # Temporal features
        if invoice.created_at:
            features["is_weekend"] = 1.0 if invoice.created_at.weekday() >= 5 else 0.0

            if invoice.entity_id:
                days_since = await self._days_since_last_invoice(
                    invoice.entity_id, invoice.created_at, company_id
                )
                # Normalize: 0-30 days = 0.0-1.0
                features["days_since_last_invoice"] = min(days_since / 30.0, 2.0) if days_since else 0.0

        return FeatureVector(
            features=features,
            metadata={
                "invoice_id": str(invoice_id),
                "feature_count": len(features),
            },
        )

    async def extract_iban_features(
        self,
        entity_id: UUID,
        new_iban: str,
        company_id: UUID,
    ) -> FeatureVector:
        """
        Extract features for IBAN manipulation detection.

        Args:
            entity_id: Entity whose IBAN is changing
            new_iban: New IBAN value
            company_id: Company context

        Returns:
            FeatureVector with IBAN-related features
        """
        features: Dict[str, float] = {}
        new_iban_normalized = new_iban.upper().replace(" ", "")

        # Get current baselines
        from app.db.models_fraud import IBANBaseline
        stmt = (
            select(IBANBaseline)
            .where(
                and_(
                    IBANBaseline.entity_id == entity_id,
                    IBANBaseline.company_id == company_id,
                    IBANBaseline.is_active == True,
                )
            )
        )
        result = await self.session.execute(stmt)
        baselines = list(result.scalars().all())

        if baselines:
            existing_ibans = [b.iban for b in baselines]

            # Check if IBAN changed
            features["iban_changed"] = 0.0 if new_iban_normalized in existing_ibans else 1.0

            # Check country change
            old_countries = set(iban[:2] for iban in existing_ibans)
            new_country = new_iban_normalized[:2]
            features["iban_country_changed"] = 0.0 if new_country in old_countries else 1.0

            # Count recent changes
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            recent_count = sum(1 for b in baselines if b.first_seen_at and b.first_seen_at >= cutoff)
            features["recent_iban_changes"] = min(recent_count / 3.0, 1.0)
        else:
            # No baseline exists
            features["iban_changed"] = 0.5  # Uncertain
            features["iban_country_changed"] = 0.0 if new_iban_normalized.startswith("DE") else 0.5
            features["recent_iban_changes"] = 0.0

        return FeatureVector(
            features=features,
            metadata={
                "entity_id": str(entity_id),
                "has_baseline": len(baselines) > 0,
            },
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_amount(self, value: object) -> Optional[Decimal]:
        """Parse amount from various formats."""
        if value is None:
            return None
        try:
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))
        except Exception:
            return None

    def _calculate_zscore(self, value: float, mean: float, std: float) -> float:
        """Calculate Z-score."""
        if std == 0:
            return 0.0
        return (value - mean) / std

    def _is_round_amount(self, amount: float) -> bool:
        """Check if amount is suspiciously round."""
        if amount < 100:
            return False
        return (
            amount % 1000 == 0 or
            amount % 500 == 0 or
            (amount % 100 == 0 and amount >= 1000)
        )

    def _count_urgency_keywords(self, text: str) -> int:
        """Count urgency keywords in text."""
        keywords = [
            "dringend", "sofort", "umgehend", "unverzueglich", "eilig",
            "schnellstmöglich", "asap", "dringende", "schnellstens",
        ]
        return sum(1 for kw in keywords if kw in text)

    def _has_confidentiality_request(self, text: str) -> bool:
        """Check for confidentiality requests."""
        keywords = ["vertraulich", "geheim", "nur für sie", "persoenlich", "diskret"]
        return any(kw in text for kw in keywords)

    def _mentions_bank_change(self, text: str) -> bool:
        """Check if text mentions bank change."""
        patterns = [
            "neue iban", "neues konto", "bankverbindung geändert",
            "iban geändert", "konto geändert", "neue bankdaten",
        ]
        return any(p in text for p in patterns)

    async def _get_historical_stats(self, company_id: UUID) -> Dict[str, float]:
        """Get historical statistics for amounts."""
        cache_key = company_id
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]

        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        stmt = (
            select(
                func.avg(InvoiceTracking.total_amount).label("mean"),
                func.stddev(InvoiceTracking.total_amount).label("std"),
                func.percentile_cont(0.5).within_group(InvoiceTracking.total_amount).label("median"),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.total_amount.isnot(None),
                    InvoiceTracking.created_at >= cutoff,
                )
            )
        )

        try:
            result = await self.session.execute(stmt)
            row = result.one_or_none()
            if row:
                stats = {
                    "mean": float(row.mean or 0),
                    "std": float(row.std or 1),
                    "median": float(row.median or 0),
                }
                self._historical_cache[cache_key] = stats
                return stats
        except Exception as e:
            logger.warning("historical_stats_failed", **safe_error_log(e))

        return {"mean": 0, "std": 1, "median": 0}

    async def _get_entity_stats(self, entity_id: UUID, company_id: UUID) -> Dict[str, Any]:
        """Get statistics for an entity."""
        stmt = (
            select(
                func.count(InvoiceTracking.id).label("invoice_count"),
            )
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()

        # Get entity risk score
        entity_stmt = select(BusinessEntity.risk_score).where(BusinessEntity.id == entity_id)
        entity_result = await self.session.execute(entity_stmt)
        risk_score = entity_result.scalar() or 0.5

        return {
            "invoice_count": row.invoice_count if row else 0,
            "risk_score": float(risk_score) / 100.0 if risk_score else 0.5,
        }

    async def _count_similar_invoices(
        self,
        amount: Optional[Decimal],
        entity_id: Optional[UUID],
        exclude_id: UUID,
        company_id: UUID,
        tolerance: float = 0.05,
    ) -> int:
        """Count similar invoices."""
        if not amount:
            return 0

        min_amount = float(amount) * (1 - tolerance)
        max_amount = float(amount) * (1 + tolerance)

        stmt = (
            select(func.count(InvoiceTracking.id))
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.id != exclude_id,
                    InvoiceTracking.total_amount >= min_amount,
                    InvoiceTracking.total_amount <= max_amount,
                )
            )
        )
        if entity_id:
            stmt = stmt.where(InvoiceTracking.entity_id == entity_id)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _days_since_last_invoice(
        self,
        entity_id: UUID,
        current_date: datetime,
        company_id: UUID,
    ) -> Optional[int]:
        """Get days since last invoice from this entity."""
        stmt = (
            select(func.max(InvoiceTracking.created_at))
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at < current_date,
                )
            )
        )
        result = await self.session.execute(stmt)
        last_date = result.scalar()

        if last_date:
            return (current_date - last_date).days
        return None


# =============================================================================
# Anomaly Scorer (Isolation Forest-like)
# =============================================================================

class FraudAnomalyScorer:
    """
    Anomaly scorer for fraud detection.

    Uses a simplified Isolation Forest-like approach
    with feature weighting and explainability.
    """

    def __init__(self, contamination: float = 0.1) -> None:
        """
        Initialize anomaly scorer.

        Args:
            contamination: Expected fraction of anomalies (default 10%)
        """
        self.contamination = contamination
        self.threshold = 0.5  # Default threshold
        self.feature_weights = {name: defn.weight for name, defn in FRAUD_FEATURES.items()}

    def score(self, feature_vector: FeatureVector) -> AnomalyScore:
        """
        Score a feature vector for anomalies.

        Uses weighted sum of features with normalization.

        Args:
            feature_vector: Extracted features

        Returns:
            AnomalyScore with score and feature contributions
        """
        features = feature_vector.features

        if not features:
            return AnomalyScore(
                score=0.0,
                feature_contributions={},
                threshold=self.threshold,
                is_anomaly=False,
            )

        # Calculate weighted contributions
        contributions: Dict[str, float] = {}
        total_weight = 0.0
        weighted_sum = 0.0

        for name, value in features.items():
            weight = self.feature_weights.get(name, 1.0)
            # Normalize value to 0-1 range (most features already are)
            normalized_value = min(max(abs(value), 0.0), 1.0)
            contribution = normalized_value * weight
            contributions[name] = contribution
            weighted_sum += contribution
            total_weight += weight

        # Normalize score to 0-1
        if total_weight > 0:
            score = weighted_sum / total_weight
        else:
            score = 0.0

        # Apply sigmoid to get smoother distribution
        score = self._sigmoid(score * 2 - 1)

        return AnomalyScore(
            score=score,
            feature_contributions=contributions,
            threshold=self.threshold,
            is_anomaly=score >= self.threshold,
        )

    def explain(self, anomaly_score: AnomalyScore) -> Dict[str, Any]:
        """
        Generate human-readable explanation for anomaly score.

        Args:
            anomaly_score: Score to explain

        Returns:
            Explanation dictionary with German text
        """
        top_features = anomaly_score.top_contributors

        explanations = []
        for feature_name, contribution in top_features:
            feature_def = FRAUD_FEATURES.get(feature_name)
            if feature_def:
                explanations.append({
                    "feature": feature_name,
                    "description": feature_def.description,
                    "contribution": round(contribution, 3),
                })

        risk_description = self._get_risk_description(anomaly_score.score)

        return {
            "score": round(anomaly_score.score, 3),
            "is_anomaly": anomaly_score.is_anomaly,
            "risk_description": risk_description,
            "top_contributors": explanations,
            "threshold": anomaly_score.threshold,
        }

    def _sigmoid(self, x: float) -> float:
        """Sigmoid function for score normalization."""
        return 1 / (1 + math.exp(-x))

    def _get_risk_description(self, score: float) -> str:
        """Get German risk description for score."""
        if score >= 0.8:
            return "Kritisch - Sofortige Untersuchung erforderlich"
        elif score >= 0.6:
            return "Hoch - Zeitnahe Überprüfung empfohlen"
        elif score >= 0.4:
            return "Mittel - Bei Gelegenheit prüfen"
        elif score >= 0.2:
            return "Niedrig - Zur Kenntnisnahme"
        else:
            return "Minimal - Keine Auffälligkeiten erkannt"


# =============================================================================
# Factory Functions
# =============================================================================

def get_fraud_feature_extractor(session: AsyncSession) -> FraudFeatureExtractor:
    """Factory function for FraudFeatureExtractor."""
    return FraudFeatureExtractor(session)


def get_fraud_anomaly_scorer(contamination: float = 0.1) -> FraudAnomalyScorer:
    """Factory function for FraudAnomalyScorer."""
    return FraudAnomalyScorer(contamination=contamination)
