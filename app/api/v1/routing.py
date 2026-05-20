# -*- coding: utf-8 -*-
"""
Predictive Document Routing API Endpoints.

Phase 9.2: Dream Features - Predictive Routing

Ermöglicht:
- Vorhersage des Dokumenten-Routings (Bearbeiter, Prioritaet, Tags)
- Training des Routing-Modells
- Feedback für Online-Learning
"""

import structlog
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.rbac import require_permission
from app.db.models import User
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.ml.routing_predictor import (
    PriorityLevel,
    RoutingPredictor,
    RoutingTarget,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/routing", tags=["Predictive Routing"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class RoutingPredictionRequest(BaseModel):
    """Request für Routing-Vorhersage."""

    document_id: UUID = Field(..., description="ID des Dokuments")
    targets: List[RoutingTarget] = Field(
        default=[RoutingTarget.USER],
        description="Vorherzusagende Ziele (user, priority, tags, folder)",
    )


class UserPredictionResponse(BaseModel):
    """Vorhersage für Benutzer-Zuweisung."""

    user_id: Optional[UUID]
    username: Optional[str]
    confidence: float
    reasoning: str


class PriorityPredictionResponse(BaseModel):
    """Vorhersage für Prioritaet."""

    priority: str
    confidence: float
    reasoning: str


class TagsPredictionResponse(BaseModel):
    """Vorhersage für Tags."""

    tags: List[str]
    confidence: float
    reasoning: str


class FolderPredictionResponse(BaseModel):
    """Vorhersage für Ordner."""

    folder_id: Optional[UUID]
    folder_name: Optional[str]
    confidence: float
    reasoning: str


class RoutingPredictionResponse(BaseModel):
    """Kombinierte Routing-Vorhersage."""

    document_id: UUID
    user_prediction: Optional[UserPredictionResponse]
    priority_prediction: Optional[PriorityPredictionResponse]
    tags_prediction: Optional[TagsPredictionResponse]
    folder_prediction: Optional[FolderPredictionResponse]
    overall_confidence: float
    model_version: str
    predicted_at: str


class RoutingFeedbackRequest(BaseModel):
    """Feedback für Routing-Vorhersage."""

    routing_id: UUID = Field(..., description="ID der Routing-Vorhersage")
    target: RoutingTarget = Field(..., description="Welches Ziel betroffen")
    correct_value: str = Field(..., description="Korrekter Wert")
    was_correct: bool = Field(..., description="War die Vorhersage korrekt?")


class TrainingDataItem(BaseModel):
    """Einzelner Trainingsdatensatz."""

    document_id: UUID
    actual_user_id: Optional[UUID] = None
    actual_priority: Optional[str] = None
    actual_tags: Optional[List[str]] = None
    actual_folder_id: Optional[UUID] = None


class TrainingRequest(BaseModel):
    """Request für Modell-Training."""

    target: RoutingTarget = Field(
        default=RoutingTarget.USER,
        description="Welches Ziel trainiert werden soll",
    )
    training_data: Optional[List[TrainingDataItem]] = Field(
        default=None,
        description="Optionale zusätzliche Trainingsdaten",
    )
    use_historical: bool = Field(
        default=True,
        description="Historische Daten aus DB verwenden",
    )
    days_back: int = Field(
        default=90,
        ge=7,
        le=365,
        description="Zeitraum für historische Daten",
    )


class TrainingResultResponse(BaseModel):
    """Ergebnis des Modell-Trainings."""

    target: str
    samples_used: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    feature_importance: Dict[str, float]
    model_version: str
    trained_at: str


class ModelInfoResponse(BaseModel):
    """Informationen über das Routing-Modell."""

    model_version: str
    targets_available: List[str]
    last_trained: Optional[str]
    training_samples: int
    accuracy: Dict[str, float]
    is_ml_model: bool


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/predict",
    response_model=RoutingPredictionResponse,
    summary="Vorhersage für Dokumenten-Routing",
    description="Sagt vorher, an wen ein Dokument geroutet werden soll.",
)
async def predict_routing(
    request: RoutingPredictionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoutingPredictionResponse:
    """
    Generiert Routing-Vorhersagen für ein Dokument.

    - **document_id**: ID des zu routenden Dokuments
    - **targets**: Welche Vorhersagen gewünscht sind

    Returns:
        RoutingPredictionResponse mit Vorhersagen und Confidence-Werten
    """
    from datetime import datetime

    from sqlalchemy import select

    from app.db.models import Document

    # Hole Dokument
    stmt = select(Document).where(
        Document.id == request.document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    predictor = RoutingPredictor(db)
    predictions = {}
    confidences = []

    for target in request.targets:
        try:
            prediction = await predictor.predict(document, target)

            if target == RoutingTarget.USER:
                # Hole Username falls vorhanden
                username = None
                if prediction.predicted_value:
                    from app.db.models import User as UserModel

                    user_stmt = select(UserModel).where(
                        UserModel.id == UUID(prediction.predicted_value)
                    )
                    user_result = await db.execute(user_stmt)
                    user = user_result.scalar_one_or_none()
                    if user:
                        username = user.username

                predictions["user_prediction"] = UserPredictionResponse(
                    user_id=UUID(prediction.predicted_value)
                    if prediction.predicted_value
                    else None,
                    username=username,
                    confidence=prediction.confidence,
                    reasoning=prediction.reasoning,
                )

            elif target == RoutingTarget.PRIORITY:
                predictions["priority_prediction"] = PriorityPredictionResponse(
                    priority=prediction.predicted_value or "normal",
                    confidence=prediction.confidence,
                    reasoning=prediction.reasoning,
                )

            elif target == RoutingTarget.TAGS:
                tags = []
                if prediction.predicted_value:
                    tags = prediction.predicted_value.split(",")
                predictions["tags_prediction"] = TagsPredictionResponse(
                    tags=tags,
                    confidence=prediction.confidence,
                    reasoning=prediction.reasoning,
                )

            elif target == RoutingTarget.FOLDER:
                folder_name = None
                folder_id = None
                if prediction.predicted_value:
                    folder_id = UUID(prediction.predicted_value)
                    # Hier könnte Folder-Name geladen werden

                predictions["folder_prediction"] = FolderPredictionResponse(
                    folder_id=folder_id,
                    folder_name=folder_name,
                    confidence=prediction.confidence,
                    reasoning=prediction.reasoning,
                )

            confidences.append(prediction.confidence)

        except Exception as e:
            logger.debug("prediction_failed", target=target, error_type=type(e).__name__, **safe_error_log(e))
            continue

    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return RoutingPredictionResponse(
        document_id=request.document_id,
        user_prediction=predictions.get("user_prediction"),
        priority_prediction=predictions.get("priority_prediction"),
        tags_prediction=predictions.get("tags_prediction"),
        folder_prediction=predictions.get("folder_prediction"),
        overall_confidence=overall_confidence,
        model_version=predictor.model_version,
        predicted_at=datetime.utcnow().isoformat(),
    )


@router.post(
    "/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Feedback zu Routing-Vorhersage",
    description="Gibt Feedback zur Qualitaet einer Routing-Vorhersage.",
)
async def submit_routing_feedback(
    request: RoutingFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Übermittelt Feedback zu einer Routing-Vorhersage.

    Dies ermöglicht Online-Learning des Modells.

    - **routing_id**: ID der urspruenglichen Vorhersage
    - **target**: Welches Ziel betroffen (user, priority, tags, folder)
    - **correct_value**: Der korrekte Wert
    - **was_correct**: War die urspruengliche Vorhersage korrekt?
    """
    predictor = RoutingPredictor(db)

    try:
        await predictor.update_from_feedback(
            routing_id=request.routing_id,
            correct_target=request.correct_value,
            was_correct=request.was_correct,
        )
    except Exception as e:
        logger.error(f"Feedback-Verarbeitung fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback konnte nicht verarbeitet werden",
        )


@router.post(
    "/train",
    response_model=TrainingResultResponse,
    summary="Trainiere Routing-Modell",
    description="Trainiert das Routing-Modell mit historischen Daten.",
    dependencies=[Depends(require_permission("admin:ml"))],
)
async def train_routing_model(
    request: TrainingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingResultResponse:
    """
    Trainiert das Routing-Modell.

    Erfordert Admin-Berechtigung.

    - **target**: Welches Ziel trainiert werden soll
    - **training_data**: Optionale zusätzliche Trainingsdaten
    - **use_historical**: Historische Daten aus DB verwenden
    - **days_back**: Zeitraum für historische Daten

    Returns:
        TrainingResultResponse mit Metriken
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.db.models import Document
    from app.ml.routing_predictor import RoutingHistory

    predictor = RoutingPredictor(db)
    training_data = []

    # Sammle historische Daten wenn gewünscht
    if request.use_historical:
        cutoff_date = datetime.utcnow() - timedelta(days=request.days_back)

        stmt = (
            select(Document)
            .where(Document.company_id == current_user.company_id)
            .where(Document.created_at >= cutoff_date)
            .where(Document.deleted_at.is_(None))
            .where(Document.assigned_to_id.isnot(None))  # Nur zugewiesene Dokumente
        )
        result = await db.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            history = RoutingHistory(
                document_id=doc.id,
                routed_to=str(doc.assigned_to_id) if doc.assigned_to_id else None,
                routed_at=doc.updated_at or doc.created_at,
                was_correct=True,  # Annahme: manuelle Zuweisungen waren korrekt
                time_to_process=None,
            )
            training_data.append(history)

    # Fuege optionale zusätzliche Trainingsdaten hinzu
    if request.training_data:
        for item in request.training_data:
            if request.target == RoutingTarget.USER and item.actual_user_id:
                history = RoutingHistory(
                    document_id=item.document_id,
                    routed_to=str(item.actual_user_id),
                    routed_at=datetime.utcnow(),
                    was_correct=True,
                    time_to_process=None,
                )
                training_data.append(history)
            elif request.target == RoutingTarget.PRIORITY and item.actual_priority:
                history = RoutingHistory(
                    document_id=item.document_id,
                    routed_to=item.actual_priority,
                    routed_at=datetime.utcnow(),
                    was_correct=True,
                    time_to_process=None,
                )
                training_data.append(history)
            elif request.target == RoutingTarget.TAGS and item.actual_tags:
                history = RoutingHistory(
                    document_id=item.document_id,
                    routed_to=",".join(item.actual_tags),
                    routed_at=datetime.utcnow(),
                    was_correct=True,
                    time_to_process=None,
                )
                training_data.append(history)

    if len(training_data) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens 10 Trainingsdatensätze erforderlich",
        )

    try:
        result = await predictor.train(training_data, request.target)

        return TrainingResultResponse(
            target=request.target.value,
            samples_used=result.samples_used,
            accuracy=result.accuracy,
            precision=result.precision,
            recall=result.recall,
            f1_score=result.f1_score,
            feature_importance=result.feature_importance,
            model_version=result.model_version,
            trained_at=result.trained_at.isoformat(),
        )

    except Exception as e:
        logger.error(f"Modell-Training fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.get(
    "/model/info",
    response_model=ModelInfoResponse,
    summary="Modell-Informationen",
    description="Gibt Informationen über das aktuelle Routing-Modell zurück.",
)
async def get_model_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ModelInfoResponse:
    """
    Ruft Informationen über das Routing-Modell ab.

    Returns:
        ModelInfoResponse mit Modell-Details
    """
    predictor = RoutingPredictor(db)

    return ModelInfoResponse(
        model_version=predictor.model_version,
        targets_available=[t.value for t in RoutingTarget],
        last_trained=predictor.last_trained.isoformat()
        if predictor.last_trained
        else None,
        training_samples=predictor.training_samples,
        accuracy=predictor.accuracy_by_target,
        is_ml_model=predictor.model is not None,
    )


@router.get(
    "/suggestions/{document_id}",
    response_model=JSONDict,
    summary="Schnelle Routing-Vorschläge",
    description="Gibt schnelle Routing-Vorschläge ohne volles ML-Modell.",
)
async def get_quick_suggestions(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Gibt schnelle regelbasierte Routing-Vorschläge zurück.

    Verwendet einfache Heuristiken statt ML für schnelle Antworten.

    - **document_id**: ID des Dokuments

    Returns:
        Dict mit Vorschlägen
    """
    from datetime import datetime

    from sqlalchemy import func, select

    from app.db.models import BusinessEntity, Document

    # Hole Dokument
    stmt = select(Document).where(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    suggestions = {
        "document_id": str(document_id),
        "suggested_users": [],
        "suggested_priority": "normal",
        "suggested_tags": [],
        "reasoning": [],
    }

    # Wenn Dokument einer Entity zugeordnet ist, schaue wer diese Entity bearbeitet
    if document.business_entity_id:
        entity_stmt = select(BusinessEntity).where(
            BusinessEntity.id == document.business_entity_id
        )
        entity_result = await db.execute(entity_stmt)
        entity = entity_result.scalar_one_or_none()

        if entity:
            # Finde Benutzer die diese Entity bearbeitet haben
            from app.db.models import User as UserModel

            user_stmt = (
                select(UserModel.id, UserModel.username, func.count().label("count"))
                .join(Document, Document.assigned_to_id == UserModel.id)
                .where(Document.business_entity_id == entity.id)
                .where(Document.deleted_at.is_(None))
                .group_by(UserModel.id, UserModel.username)
                .order_by(func.count().desc())
                .limit(3)
            )
            user_result = await db.execute(user_stmt)
            frequent_users = user_result.all()

            for user_id, username, count in frequent_users:
                suggestions["suggested_users"].append(
                    {
                        "user_id": str(user_id),
                        "username": username,
                        "documents_processed": count,
                    }
                )
                suggestions["reasoning"].append(
                    f"{username} hat {count} Dokumente dieser Entity bearbeitet"
                )

    # Prioritaet basierend auf Dokumenttyp und Betrag
    extracted = document.extracted_data or {}

    if document.document_type in ["invoice", "rechnung"]:
        amount = extracted.get("total_amount") or extracted.get("amount")
        if amount:
            try:
                amount_value = float(str(amount).replace(",", ".").replace("€", "").strip())
                if amount_value > 10000:
                    suggestions["suggested_priority"] = "high"
                    suggestions["reasoning"].append(
                        f"Hoher Betrag ({amount_value:.2f} EUR) - Prioritaet hoch"
                    )
                elif amount_value > 5000:
                    suggestions["suggested_priority"] = "medium"
            except (ValueError, TypeError) as e:
                logger.debug(
                    "amount_parse_for_priority_failed",
                    error_type=type(e).__name__,
                )

    # Tags basierend auf Dokumenttyp
    if document.document_type:
        suggestions["suggested_tags"].append(document.document_type)

    if document.business_entity_id:
        suggestions["suggested_tags"].append("mit_entity")

    suggestions["generated_at"] = datetime.utcnow().isoformat()

    return suggestions


@router.post(
    "/auto-route/{document_id}",
    response_model=JSONDict,
    summary="Automatisches Routing anwenden",
    description="Wendet die Routing-Vorhersage automatisch an.",
)
async def auto_route_document(
    document_id: UUID,
    apply_user: bool = Query(default=True, description="Benutzer-Zuweisung anwenden"),
    apply_priority: bool = Query(default=True, description="Prioritaet anwenden"),
    apply_tags: bool = Query(default=False, description="Tags anwenden"),
    min_confidence: float = Query(
        default=0.7, ge=0.5, le=1.0, description="Mindest-Confidence"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Wendet Routing-Vorhersagen automatisch auf ein Dokument an.

    - **document_id**: ID des Dokuments
    - **apply_user**: Benutzer-Zuweisung anwenden
    - **apply_priority**: Prioritaet anwenden
    - **apply_tags**: Tags anwenden
    - **min_confidence**: Mindest-Confidence für Anwendung

    Returns:
        Dict mit angewendeten Änderungen
    """
    from datetime import datetime

    from sqlalchemy import select

    from app.db.models import Document


    # Hole Dokument
    stmt = select(Document).where(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    predictor = RoutingPredictor(db)
    applied_changes = []
    skipped = []

    # User-Zuweisung
    if apply_user:
        try:
            prediction = await predictor.predict(document, RoutingTarget.USER)
            if prediction.confidence >= min_confidence and prediction.predicted_value:
                document.assigned_to_id = UUID(prediction.predicted_value)
                applied_changes.append(
                    {
                        "field": "assigned_to_id",
                        "value": prediction.predicted_value,
                        "confidence": prediction.confidence,
                    }
                )
            else:
                skipped.append(
                    {
                        "field": "assigned_to_id",
                        "reason": f"Confidence zu niedrig ({prediction.confidence:.2f} < {min_confidence})",
                    }
                )
        except Exception as e:
            logger.debug("assigned_to_prediction_failed", document_id=str(document_id), error_type=type(e).__name__)
            skipped.append({"field": "assigned_to_id", "reason": safe_error_detail(e, "Feld")})

    # Prioritaet
    if apply_priority:
        try:
            prediction = await predictor.predict(document, RoutingTarget.PRIORITY)
            if prediction.confidence >= min_confidence and prediction.predicted_value:
                # Setze Prioritaet in extracted_data oder separatem Feld
                if document.extracted_data is None:
                    document.extracted_data = {}
                document.extracted_data["priority"] = prediction.predicted_value
                applied_changes.append(
                    {
                        "field": "priority",
                        "value": prediction.predicted_value,
                        "confidence": prediction.confidence,
                    }
                )
            else:
                skipped.append(
                    {
                        "field": "priority",
                        "reason": f"Confidence zu niedrig ({prediction.confidence:.2f})",
                    }
                )
        except Exception as e:
            logger.debug("priority_prediction_failed", document_id=str(document_id), error_type=type(e).__name__)
            skipped.append({"field": "priority", "reason": safe_error_detail(e, "Feld")})

    # Tags
    if apply_tags:
        try:
            prediction = await predictor.predict(document, RoutingTarget.TAGS)
            if prediction.confidence >= min_confidence and prediction.predicted_value:
                new_tags = prediction.predicted_value.split(",")
                existing_tags = document.tags or []
                document.tags = list(set(existing_tags + new_tags))
                applied_changes.append(
                    {
                        "field": "tags",
                        "value": new_tags,
                        "confidence": prediction.confidence,
                    }
                )
            else:
                skipped.append(
                    {
                        "field": "tags",
                        "reason": f"Confidence zu niedrig ({prediction.confidence:.2f})",
                    }
                )
        except Exception as e:
            logger.debug("tags_prediction_failed", document_id=str(document_id), error_type=type(e).__name__)
            skipped.append({"field": "tags", "reason": safe_error_detail(e, "Feld")})

    # Speichere Änderungen
    if applied_changes:
        document.updated_at = datetime.utcnow()
        await db.commit()

    return {
        "document_id": str(document_id),
        "applied_changes": applied_changes,
        "skipped": skipped,
        "min_confidence_used": min_confidence,
        "applied_at": datetime.utcnow().isoformat(),
    }
