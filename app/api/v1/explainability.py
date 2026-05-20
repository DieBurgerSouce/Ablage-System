# -*- coding: utf-8 -*-
"""
Explainability API - Phase 4.3 Erklaerbare AI-Entscheidungen.

Stellt REST-Endpunkte bereit, mit denen Benutzer nachvollziehen koennen,
warum das System bestimmte KI-Entscheidungen getroffen hat:

  GET /api/v1/explain/classification/{document_id}
      Warum wurde dieses Dokument so klassifiziert?

  GET /api/v1/explain/cluster-suggestion/{suggestion_id}
      Warum wird dieser Cluster vorgeschlagen?

  GET /api/v1/explain/anomaly/{anomaly_id}
      Warum wurde diese Anomalie gemeldet?

  GET /api/v1/explain/entity-link/{document_id}/{entity_id}
      Warum wurde diese Entitaet verknuepft?

Feinpoliert und durchdacht - Transparenz auf Enterprise-Niveau.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import Company, User
from app.middleware.company_context import require_company
from app.services.explainability_service import ExplainabilityService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/explain",
    tags=["Erklaerbare KI-Entscheidungen"],
)


# =============================================================================
# Response-Schemas
# =============================================================================


class ExplanationFactor(BaseModel):
    """Ein einzelner Einflussfaktor der KI-Entscheidung."""

    feature: str = Field(
        ...,
        description="Name des Merkmals (Deutsch)",
        examples=["Schluesselwoerter"],
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gewichtung des Faktors (0.0 bis 1.0)",
        examples=[0.40],
    )
    description: str = Field(
        ...,
        description="Deutsche Beschreibung des Faktors",
        examples=["Typische Begriffe fuer Rechnungen erkannt: rechnung, betrag, mwst"],
    )


class AlternativeDecision(BaseModel):
    """Eine alternative KI-Entscheidung, die in Betracht gezogen wurde."""

    category: str = Field(
        ...,
        description="Bezeichnung der Alternative (Deutsch)",
        examples=["Lieferschein"],
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Konfidenz der Alternative (0.0 bis 1.0)",
        examples=[0.12],
    )


class MatchingCriterion(BaseModel):
    """Ein Uebereinstimmungskriterium beim Entity-Linking."""

    field: str = Field(
        ...,
        description="Feldname, das den Match begruendet",
        examples=["Firmenname"],
    )
    pattern: str = Field(
        ...,
        description="Erkanntes Muster oder Wert",
        examples=["Mustermann GmbH"],
    )
    description: str = Field(
        ...,
        description="Deutsche Beschreibung des Kriteriums",
        examples=["Name 'Mustermann GmbH' im Dokumenttext gefunden."],
    )


class SimilarDocument(BaseModel):
    """Aehnliches Dokument bei Cluster-Erklaerung."""

    document_id: str = Field(..., description="UUID des Dokuments")
    title: str = Field(..., description="Titel oder Dateiname")
    similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aehnlichkeitswert (Cosine-Similarity)",
    )


# -------------------------------------------------------------------
# Klassifikations-Response
# -------------------------------------------------------------------

class ClassificationExplanationResponse(BaseModel):
    """Antwort fuer Dokument-Klassifikations-Erklaerung."""

    document_id: str = Field(..., description="UUID des Dokuments")
    predicted_category: str = Field(
        ...,
        description="Vorhergesagte Kategorie (Deutsch)",
        examples=["Rechnung"],
    )
    predicted_category_key: str = Field(
        ...,
        description="Interner Kategorieschluessel",
        examples=["invoice"],
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gesamtkonfidenz der Klassifikation",
    )
    top_features: List[ExplanationFactor] = Field(
        default_factory=list,
        description="Wichtigste Einflussfaktoren",
    )
    alternative_categories: List[AlternativeDecision] = Field(
        default_factory=list,
        description="Alternative Kategorien mit jeweiliger Konfidenz",
    )
    explanation_text: str = Field(
        ...,
        description="Natuerlichsprachliche Erklaerung (Deutsch)",
    )
    factors: List[ExplanationFactor] = Field(
        default_factory=list,
        description="Vollstaendige Faktoren-Liste (Alias fuer top_features)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Konfidenz (Alias fuer confidence_score)",
    )
    alternatives: List[AlternativeDecision] = Field(
        default_factory=list,
        description="Alternativen (Alias fuer alternative_categories)",
    )
    generated_at: str = Field(..., description="ISO-8601 Generierungszeitpunkt")

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------
# Cluster-Response
# -------------------------------------------------------------------

class ClusterSuggestionExplanationResponse(BaseModel):
    """Antwort fuer Cluster-Vorschlag-Erklaerung."""

    suggestion_id: str = Field(..., description="UUID des Cluster-Vorschlags")
    suggested_cluster_name: str = Field(
        ...,
        description="Name des vorgeschlagenen Clusters oder der Kategorie",
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aehnlichkeitswert zum Cluster-Zentroid",
    )
    top_similar_documents: List[SimilarDocument] = Field(
        default_factory=list,
        description="Aehnlichste Referenzdokumente",
    )
    common_features: List[str] = Field(
        default_factory=list,
        description="Gemeinsame Merkmale der Dokumente im Cluster",
    )
    explanation_text: str = Field(
        ...,
        description="Natuerlichsprachliche Erklaerung (Deutsch)",
    )
    factors: List[ExplanationFactor] = Field(
        default_factory=list,
        description="Einflussfaktoren der Vorschlags-Entscheidung",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gesamtkonfidenz",
    )
    alternatives: List[AlternativeDecision] = Field(
        default_factory=list,
        description="Betrachtete Alternativen",
    )
    generated_at: str = Field(..., description="ISO-8601 Generierungszeitpunkt")

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------
# Anomalie-Response
# -------------------------------------------------------------------

class AnomalyExplanationResponse(BaseModel):
    """Antwort fuer Anomalie-Erklaerung."""

    anomaly_id: str = Field(..., description="UUID der Anomalie")
    anomaly_type: str = Field(..., description="Typ der Anomalie (intern)")
    severity: str = Field(..., description="Schweregrad: info, warning, critical")
    rule_name: Optional[str] = Field(
        None,
        description="Name der ausloesenden Regel (null bei ML-Erkennung)",
    )
    trigger_conditions: List[str] = Field(
        default_factory=list,
        description="Bedingungen, die die Anomalie ausgeloest haben (Deutsch)",
    )
    historical_context: str = Field(
        ...,
        description="Historischer Kontext: Vergleich mit Normalwerten",
    )
    explanation_text: str = Field(
        ...,
        description="Natuerlichsprachliche Erklaerung (Deutsch)",
    )
    factors: List[ExplanationFactor] = Field(
        default_factory=list,
        description="Einflussfaktoren der Anomalie-Erkennung",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Erkennungskonfidenz (0.0 bis 1.0)",
    )
    alternatives: List[AlternativeDecision] = Field(
        default_factory=list,
        description="Betrachtete Alternativen",
    )
    details: Dict[str, Union[str, float, int]] = Field(
        default_factory=dict,
        description="Technische Rohdaten der Anomalie",
    )
    generated_at: str = Field(..., description="ISO-8601 Generierungszeitpunkt")

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------
# Entity-Link-Response
# -------------------------------------------------------------------

class EntityLinkExplanationResponse(BaseModel):
    """Antwort fuer Entity-Linking-Erklaerung."""

    document_id: str = Field(..., description="UUID des Dokuments")
    entity_id: str = Field(..., description="UUID der Geschaeftsentitaet")
    entity_name: str = Field(..., description="Name der Entitaet")
    match_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Uebereinstimmungs-Score (0.0 bis 1.0)",
    )
    link_type: str = Field(
        ...,
        description="Art der Verknuepfung (invoice_sender, mentioned, etc.)",
    )
    matching_criteria: List[MatchingCriterion] = Field(
        default_factory=list,
        description="Felder/Muster, die die Zuordnung begruenden",
    )
    explanation_text: str = Field(
        ...,
        description="Natuerlichsprachliche Erklaerung (Deutsch)",
    )
    factors: List[ExplanationFactor] = Field(
        default_factory=list,
        description="Einflussfaktoren der Verknuepfungs-Entscheidung",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gesamtkonfidenz",
    )
    alternatives: List[AlternativeDecision] = Field(
        default_factory=list,
        description="Betrachtete Alternativen",
    )
    generated_at: str = Field(..., description="ISO-8601 Generierungszeitpunkt")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Service-Factory
# =============================================================================

def _get_service() -> ExplainabilityService:
    """Erstellt eine ExplainabilityService-Instanz (kein Singleton noetig)."""
    return ExplainabilityService()


# =============================================================================
# Endpunkte
# =============================================================================


@router.get(
    "/classification/{document_id}",
    response_model=ClassificationExplanationResponse,
    summary="Klassifikations-Erklaerung",
    description=(
        "Erklaert, warum ein Dokument von der OCR-Pipeline einer bestimmten "
        "Kategorie zugeordnet wurde. Zeigt die wichtigsten Einflussfaktoren, "
        "Konfidenz und alternative Klassifikationen."
    ),
)
async def get_classification_explanation(
    document_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ClassificationExplanationResponse:
    """
    Erklaert die Dokumentklassifikation.

    Args:
        document_id: UUID des Dokuments
        company: Aktueller Mandant (aus company_context Middleware)
        current_user: Authentifizierter Benutzer
        db: Datenbankverbindung

    Returns:
        ClassificationExplanationResponse mit Faktoren und Erklaerungstext

    Raises:
        HTTPException 404: Dokument nicht gefunden
        HTTPException 500: Interner Fehler
    """
    logger.info(
        "api.explain.classification.request",
        document_id=str(document_id),
        company_id=str(company.id),
        user_id=str(current_user.id),
    )

    try:
        service = _get_service()
        result = await service.explain_classification(
            document_id=document_id,
            company_id=company.id,
            db=db,
        )
    except Exception as exc:
        logger.error(
            "api.explain.classification.error",
            **safe_error_log(exc, context="classification explanation"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(exc, "Klassifikationserlaeuterung"),
        ) from exc

    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder kein Zugriff.",
        )

    return ClassificationExplanationResponse(
        document_id=result.get("document_id", str(document_id)),
        predicted_category=result.get("predicted_category", "Unbekannt"),
        predicted_category_key=result.get("predicted_category_key", "other"),
        confidence_score=float(result.get("confidence_score", 0.0)),
        top_features=[
            ExplanationFactor(**f)
            for f in result.get("top_features", [])
        ],
        alternative_categories=[
            AlternativeDecision(**a)
            for a in result.get("alternative_categories", [])
        ],
        explanation_text=result.get("explanation_text", ""),
        factors=[
            ExplanationFactor(**f)
            for f in result.get("top_features", [])
        ],
        confidence=float(result.get("confidence_score", 0.0)),
        alternatives=[
            AlternativeDecision(**a)
            for a in result.get("alternative_categories", [])
        ],
        generated_at=result.get("generated_at", ""),
    )


@router.get(
    "/cluster-suggestion/{suggestion_id}",
    response_model=ClusterSuggestionExplanationResponse,
    summary="Cluster-Vorschlag-Erklaerung",
    description=(
        "Erklaert, warum ein bestimmter Cluster fuer ein Dokument vorgeschlagen "
        "wurde. Zeigt aehnliche Referenzdokumente, Vektoraehnlichkeit und "
        "gemeinsame Merkmale."
    ),
)
async def get_cluster_suggestion_explanation(
    suggestion_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ClusterSuggestionExplanationResponse:
    """
    Erklaert einen Cluster-Vorschlag.

    Args:
        suggestion_id: UUID des ClusterSuggestion-Eintrags
        company: Aktueller Mandant
        current_user: Authentifizierter Benutzer
        db: Datenbankverbindung

    Returns:
        ClusterSuggestionExplanationResponse mit Erklaerungstext

    Raises:
        HTTPException 404: Vorschlag nicht gefunden
        HTTPException 500: Interner Fehler
    """
    logger.info(
        "api.explain.cluster.request",
        suggestion_id=str(suggestion_id),
        company_id=str(company.id),
        user_id=str(current_user.id),
    )

    try:
        service = _get_service()
        result = await service.explain_cluster_suggestion(
            suggestion_id=suggestion_id,
            company_id=company.id,
            db=db,
        )
    except Exception as exc:
        logger.error(
            "api.explain.cluster.error",
            **safe_error_log(exc, context="cluster suggestion explanation"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(exc, "Cluster-Vorschlag-Erlaeuterung"),
        ) from exc

    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster-Vorschlag nicht gefunden oder kein Zugriff.",
        )

    top_similar = [
        SimilarDocument(**doc)
        for doc in result.get("top_similar_documents", [])
    ]

    return ClusterSuggestionExplanationResponse(
        suggestion_id=result.get("suggestion_id", str(suggestion_id)),
        suggested_cluster_name=result.get("suggested_cluster_name", "Unbekannt"),
        similarity_score=float(result.get("similarity_score", 0.0)),
        top_similar_documents=top_similar,
        common_features=result.get("common_features", []),
        explanation_text=result.get("explanation_text", ""),
        factors=[
            ExplanationFactor(**f)
            for f in result.get("factors", [])
        ],
        confidence=float(result.get("confidence", 0.0)),
        alternatives=[
            AlternativeDecision(**a)
            for a in result.get("alternatives", [])
        ],
        generated_at=result.get("generated_at", ""),
    )


@router.get(
    "/anomaly/{anomaly_id}",
    response_model=AnomalyExplanationResponse,
    summary="Anomalie-Erklaerung",
    description=(
        "Erklaert, warum eine Anomalie-Warnung ausgeloest wurde. Beschreibt "
        "die Ausloesebedingungen, die verantwortliche Regel (falls regelbasiert) "
        "und den historischen Kontext."
    ),
)
async def get_anomaly_explanation(
    anomaly_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AnomalyExplanationResponse:
    """
    Erklaert eine erkannte Anomalie.

    Args:
        anomaly_id: UUID der Anomalie
        company: Aktueller Mandant
        current_user: Authentifizierter Benutzer
        db: Datenbankverbindung

    Returns:
        AnomalyExplanationResponse mit Bedingungen und Erklaerungstext

    Raises:
        HTTPException 404: Anomalie nicht gefunden
        HTTPException 500: Interner Fehler
    """
    logger.info(
        "api.explain.anomaly.request",
        anomaly_id=str(anomaly_id),
        company_id=str(company.id),
        user_id=str(current_user.id),
    )

    try:
        service = _get_service()
        result = await service.explain_anomaly(
            anomaly_id=anomaly_id,
            company_id=company.id,
            db=db,
        )
    except Exception as exc:
        logger.error(
            "api.explain.anomaly.error",
            **safe_error_log(exc, context="anomaly explanation"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(exc, "Anomalie-Erlaeuterung"),
        ) from exc

    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomalie nicht gefunden oder kein Zugriff.",
        )

    # details kann gemischte Typen enthalten - sicheres Casting
    raw_details = result.get("details", {})
    safe_details: Dict[str, Union[str, float, int]] = {
        k: v
        for k, v in raw_details.items()
        if isinstance(v, (str, float, int))
    }

    return AnomalyExplanationResponse(
        anomaly_id=result.get("anomaly_id", str(anomaly_id)),
        anomaly_type=result.get("anomaly_type", "unknown"),
        severity=result.get("severity", "info"),
        rule_name=result.get("rule_name"),
        trigger_conditions=result.get("trigger_conditions", []),
        historical_context=result.get("historical_context", ""),
        explanation_text=result.get("explanation_text", ""),
        factors=[
            ExplanationFactor(**f)
            for f in result.get("factors", [])
        ],
        confidence=float(result.get("confidence", 0.0)),
        alternatives=[
            AlternativeDecision(**a)
            for a in result.get("alternatives", [])
        ],
        details=safe_details,
        generated_at=result.get("generated_at", ""),
    )


@router.get(
    "/entity-link/{document_id}/{entity_id}",
    response_model=EntityLinkExplanationResponse,
    summary="Entity-Link-Erklaerung",
    description=(
        "Erklaert, warum ein Dokument mit einer bestimmten Geschaeftsentitaet "
        "verknuepft wurde. Zeigt Uebereinstimmungskriterien wie Name, USt-ID "
        "oder Adresse und den Verknuepfungstyp."
    ),
)
async def get_entity_link_explanation(
    document_id: UUID,
    entity_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EntityLinkExplanationResponse:
    """
    Erklaert die Entity-Linking-Entscheidung.

    Args:
        document_id: UUID des Dokuments
        entity_id: UUID der Geschaeftsentitaet
        company: Aktueller Mandant
        current_user: Authentifizierter Benutzer
        db: Datenbankverbindung

    Returns:
        EntityLinkExplanationResponse mit Uebereinstimmungskriterien

    Raises:
        HTTPException 404: Dokument oder Entitaet nicht gefunden
        HTTPException 500: Interner Fehler
    """
    logger.info(
        "api.explain.entity_link.request",
        document_id=str(document_id),
        entity_id=str(entity_id),
        company_id=str(company.id),
        user_id=str(current_user.id),
    )

    try:
        service = _get_service()
        result = await service.explain_entity_linking(
            document_id=document_id,
            entity_id=entity_id,
            company_id=company.id,
            db=db,
        )
    except Exception as exc:
        logger.error(
            "api.explain.entity_link.error",
            **safe_error_log(exc, context="entity link explanation"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(exc, "Entity-Link-Erlaeuterung"),
        ) from exc

    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument oder Entitaet nicht gefunden oder kein Zugriff.",
        )

    criteria = [
        MatchingCriterion(**c)
        for c in result.get("matching_criteria", [])
    ]

    return EntityLinkExplanationResponse(
        document_id=result.get("document_id", str(document_id)),
        entity_id=result.get("entity_id", str(entity_id)),
        entity_name=result.get("entity_name", "Unbekannt"),
        match_score=float(result.get("match_score", 0.0)),
        link_type=result.get("link_type", "auto"),
        matching_criteria=criteria,
        explanation_text=result.get("explanation_text", ""),
        factors=[
            ExplanationFactor(**f)
            for f in result.get("factors", [])
        ],
        confidence=float(result.get("confidence", 0.0)),
        alternatives=[
            AlternativeDecision(**a)
            for a in result.get("alternatives", [])
        ],
        generated_at=result.get("generated_at", ""),
    )
