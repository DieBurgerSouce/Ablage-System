"""
OCR Self-Learning API Endpoints

API für das Self-Learning OCR System:
- Korrektur-Feedback verarbeiten
- Confidence-Kalibrierung
- A/B Test Management
- Learning-Statistiken

SECURITY:
- Alle Endpoints erfordern Authentifizierung
- Admin-only für kritische Operationen
- Input-Validierung mit Whitelists
"""

import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.ocr.self_learning_service import (
    SelfLearningOCRService,
    CorrectionFeedback,
    LearningMode,
    ModelVersion,
    get_self_learning_service,
)


# ==================== Security Constants ====================

# Erlaubte OCR-Backends (Whitelist gegen Injection)
ALLOWED_OCR_BACKENDS = frozenset([
    "deepseek",
    "got_ocr",
    "surya",
    "surya_gpu",
    "paddle",
    "qwen",
    "hybrid",
])

# Erlaubte Feldnamen (gegen Path Traversal / Injection)
ALLOWED_FIELD_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")

# Erlaubte Korrektur-Typen
ALLOWED_CORRECTION_TYPES = frozenset(["text", "amount", "date", "entity"])

# Test-ID Pattern (alphanumerisch + Bindestriche/Unterstriche, 3-64 Zeichen)
ALLOWED_TEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")


def validate_test_id_path_param(test_id: str) -> str:
    """
    Validiere test_id Path-Parameter.

    Wirft HTTPException bei ungültigem Format.
    """
    if not ALLOWED_TEST_ID_PATTERN.match(test_id):
        raise HTTPException(
            status_code=400,
            detail="Test-ID muss mit Buchstabe/Zahl beginnen, 3-64 Zeichen, nur alphanumerisch/Bindestriche/Unterstriche"
        )
    return test_id


router = APIRouter(prefix="/ocr-learning", tags=["OCR Self-Learning"])


# ==================== Schemas ====================


class CorrectionFeedbackRequest(BaseModel):
    """Request für Korrektur-Feedback."""
    document_id: UUID
    field_name: str = Field(..., description="Name des korrigierten Felds", max_length=64)
    original_value: str = Field(..., description="Urspruenglicher OCR-Wert", max_length=10000)
    corrected_value: str = Field(..., description="Korrigierter Wert vom User", max_length=10000)
    ocr_backend: str = Field(..., description="Verwendetes OCR-Backend")
    original_confidence: float = Field(..., ge=0.0, le=1.0, description="Urspruengliche Confidence")
    correction_type: str = Field("text", description="Art der Korrektur: text, amount, date, entity")

    @field_validator("ocr_backend")
    @classmethod
    def validate_ocr_backend(cls, v: str) -> str:
        """Whitelist-Validierung für OCR-Backend."""
        backend_lower = v.lower().strip()
        if backend_lower not in ALLOWED_OCR_BACKENDS:
            raise ValueError(f"Ungültiges OCR-Backend. Erlaubt: {sorted(ALLOWED_OCR_BACKENDS)}")
        return backend_lower

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        """Pattern-Validierung gegen Injection."""
        if not ALLOWED_FIELD_PATTERN.match(v):
            raise ValueError("Feldname muss mit Buchstabe beginnen und nur alphanumerische Zeichen/Unterstriche enthalten")
        return v

    @field_validator("correction_type")
    @classmethod
    def validate_correction_type(cls, v: str) -> str:
        """Whitelist-Validierung für Korrektur-Typ."""
        type_lower = v.lower().strip()
        if type_lower not in ALLOWED_CORRECTION_TYPES:
            raise ValueError(f"Ungültiger Korrektur-Typ. Erlaubt: {sorted(ALLOWED_CORRECTION_TYPES)}")
        return type_lower


class CorrectionFeedbackResponse(BaseModel):
    """Response für Korrektur-Feedback."""
    processed: bool
    learning_mode: str
    confidence_adjustment: float
    training_sample_id: Optional[str] = None
    rollback_triggered: bool = False
    adjustments: list


class CalibratedConfidenceRequest(BaseModel):
    """Request für kalibrierte Confidence."""
    backend: str
    field: str = Field(..., max_length=64)
    raw_confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Whitelist-Validierung für OCR-Backend."""
        backend_lower = v.lower().strip()
        if backend_lower not in ALLOWED_OCR_BACKENDS:
            raise ValueError(f"Ungültiges OCR-Backend. Erlaubt: {sorted(ALLOWED_OCR_BACKENDS)}")
        return backend_lower

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        """Pattern-Validierung gegen Injection."""
        if not ALLOWED_FIELD_PATTERN.match(v):
            raise ValueError("Feldname muss mit Buchstabe beginnen und nur alphanumerische Zeichen/Unterstriche enthalten")
        return v


class CalibratedConfidenceResponse(BaseModel):
    """Response für kalibrierte Confidence."""
    backend: str
    field: str
    raw_confidence: float
    calibrated_confidence: float
    adjustment_applied: float


class ABTestStartRequest(BaseModel):
    """Request zum Starten eines A/B Tests."""
    test_id: str = Field(..., description="Eindeutige Test-ID", min_length=3, max_length=64)
    candidate_version: str = Field(..., description="candidate_a oder candidate_b")
    traffic_split: float = Field(0.1, ge=0.01, le=0.5, description="Anteil Traffic für Kandidat")
    min_samples: int = Field(100, ge=10, description="Minimale Samples vor Auswertung")
    max_duration_days: int = Field(7, ge=1, le=30, description="Maximale Test-Dauer")

    @field_validator("test_id")
    @classmethod
    def validate_test_id(cls, v: str) -> str:
        """Pattern-Validierung für Test-ID gegen Injection."""
        if not ALLOWED_TEST_ID_PATTERN.match(v):
            raise ValueError(
                "Test-ID muss mit Buchstabe/Zahl beginnen, "
                "3-64 Zeichen, nur alphanumerisch/Bindestriche/Unterstriche"
            )
        return v


class ABTestResponse(BaseModel):
    """Response für A/B Test."""
    test_id: str
    baseline_version: str
    candidate_version: str
    traffic_split: float
    min_samples: int
    max_duration_days: int
    started_at: str


class ABTestResultResponse(BaseModel):
    """Response für A/B Test Ergebnis."""
    test_id: str
    improvement_percent: float
    is_significant: bool
    recommendation: str
    confidence_level: float
    baseline_quality_score: float
    candidate_quality_score: float


class ABTestEndRequest(BaseModel):
    """Request zum Beenden eines A/B Tests."""
    action: str = Field("rollback", description="promote oder rollback")


class LearningStatsResponse(BaseModel):
    """Response für Learning-Statistiken."""
    learning_mode: str
    training_samples: int
    total_corrections: int
    backend_adjustments: dict
    field_adjustments: dict
    active_ab_tests: list
    model_metrics: dict


# ==================== Endpoints ====================


@router.post("/feedback", response_model=CorrectionFeedbackResponse)
async def submit_correction_feedback(
    request: CorrectionFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Übermittle Korrektur-Feedback.

    Im AGGRESSIVE Modus wird das System sofort angepasst.
    Erstellt automatisch Training Samples für späteres Batch-Training.
    """
    service = get_self_learning_service(db)

    feedback = CorrectionFeedback(
        document_id=request.document_id,
        field_name=request.field_name,
        original_value=request.original_value,
        corrected_value=request.corrected_value,
        ocr_backend=request.ocr_backend,
        original_confidence=request.original_confidence,
        user_id=current_user.id,
        correction_type=request.correction_type,
    )

    result = await service.process_correction(feedback)

    return CorrectionFeedbackResponse(
        processed=result["processed"],
        learning_mode=result["learning_mode"],
        confidence_adjustment=result["confidence_adjustment"],
        training_sample_id=result.get("training_sample_id"),
        rollback_triggered=result.get("rollback_triggered", False),
        adjustments=result["adjustments"],
    )


@router.post("/calibrate", response_model=CalibratedConfidenceResponse)
async def get_calibrated_confidence(
    request: CalibratedConfidenceRequest,
    current_user: User = Depends(get_current_user),  # AUTH REQUIRED
    db: AsyncSession = Depends(get_db),
):
    """
    Liefere kalibrierte Confidence.

    Wendet gelernte Adjustments auf Raw-Confidence an.
    Erfordert Authentifizierung.
    """
    service = get_self_learning_service(db)

    # State aus DB laden (lazy)
    await service._load_state_from_db()

    calibrated = service.get_calibrated_confidence(
        backend=request.backend,
        field=request.field,
        raw_confidence=request.raw_confidence,
    )

    adjustment = calibrated - request.raw_confidence

    return CalibratedConfidenceResponse(
        backend=request.backend,
        field=request.field,
        raw_confidence=request.raw_confidence,
        calibrated_confidence=calibrated,
        adjustment_applied=adjustment,
    )


@router.get("/confidence-stats")
async def get_confidence_statistics(
    backend: Optional[str] = Query(None, description="Filter nach Backend"),
    current_user: User = Depends(get_current_user),  # AUTH REQUIRED
    db: AsyncSession = Depends(get_db),
):
    """
    Liefere Confidence-Statistiken.

    Zeigt aktuelle Adjustments pro Backend und Feld.
    Erfordert Authentifizierung.
    """
    # Validiere backend Parameter wenn gesetzt
    if backend is not None:
        backend_lower = backend.lower().strip()
        if backend_lower not in ALLOWED_OCR_BACKENDS:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültiges OCR-Backend. Erlaubt: {sorted(ALLOWED_OCR_BACKENDS)}"
            )
        backend = backend_lower

    service = get_self_learning_service(db)
    return await service.get_confidence_statistics(backend)


@router.post("/ab-test/start", response_model=ABTestResponse)
async def start_ab_test(
    request: ABTestStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Starte neuen A/B Test.

    Nur Admins können A/B Tests starten.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins können A/B Tests starten")

    # Validiere candidate_version
    try:
        candidate = ModelVersion(request.candidate_version)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Kandidat-Version. Erlaubt: {[v.value for v in ModelVersion]}"
        )

    service = get_self_learning_service(db)

    config = await service.start_ab_test(
        test_id=request.test_id,
        candidate_version=candidate,
        traffic_split=request.traffic_split,
        min_samples=request.min_samples,
        max_duration_days=request.max_duration_days,
    )

    return ABTestResponse(
        test_id=config.test_id,
        baseline_version=config.baseline_version.value,
        candidate_version=config.candidate_version.value,
        traffic_split=config.traffic_split,
        min_samples=config.min_samples,
        max_duration_days=config.max_duration_days,
        started_at=config.started_at.isoformat(),
    )


@router.get("/ab-test/{test_id}", response_model=ABTestResultResponse)
async def get_ab_test_result(
    test_id: str,
    current_user: User = Depends(get_current_user),  # AUTH REQUIRED
    db: AsyncSession = Depends(get_db),
):
    """
    Liefere A/B Test Ergebnis.

    Zeigt aktuelle Metriken und Empfehlung.
    Erfordert Authentifizierung.
    """
    # Validiere test_id Path-Parameter gegen Injection
    test_id = validate_test_id_path_param(test_id)

    service = get_self_learning_service(db)

    result = await service.evaluate_ab_test(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test nicht gefunden oder nicht genug Daten")

    return ABTestResultResponse(
        test_id=result.test_id,
        improvement_percent=result.improvement_percent,
        is_significant=result.is_significant,
        recommendation=result.recommendation,
        confidence_level=result.confidence_level,
        baseline_quality_score=result.baseline_metrics.quality_score,
        candidate_quality_score=result.candidate_metrics.quality_score,
    )


@router.post("/ab-test/{test_id}/end")
async def end_ab_test(
    test_id: str,
    request: ABTestEndRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Beende A/B Test.

    Actions:
    - promote: Kandidat wird neue Baseline
    - rollback: Zurück zu Baseline
    """
    # Validiere test_id Path-Parameter gegen Injection
    test_id = validate_test_id_path_param(test_id)

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins können A/B Tests beenden")

    if request.action not in ["promote", "rollback"]:
        raise HTTPException(status_code=400, detail="Action muss 'promote' oder 'rollback' sein")

    service = get_self_learning_service(db)

    result = await service.end_ab_test(test_id, request.action)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Unbekannter Fehler"))

    return result


@router.get("/stats", response_model=LearningStatsResponse)
async def get_learning_statistics(
    current_user: User = Depends(get_current_user),  # AUTH REQUIRED
    db: AsyncSession = Depends(get_db),
):
    """
    Liefere umfassende Learning-Statistiken.

    Zeigt:
    - Aktuelle Learning-Mode
    - Anzahl Training Samples
    - Backend-Adjustments
    - Aktive A/B Tests
    - Model-Metriken

    Erfordert Authentifizierung.
    """
    service = get_self_learning_service(db)
    stats = await service.get_learning_statistics()

    return LearningStatsResponse(**stats)


@router.post("/mode/{mode}")
async def set_learning_mode(
    mode: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Setze Learning-Modus.

    Modi:
    - aggressive: Jede Korrektur fliesst sofort ein
    - cautious: Nur verifizierte Korrekturen
    - batch: Batch-Learning (täglich)

    Wird in der Datenbank persistiert.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins können den Modus ändern")

    try:
        learning_mode = LearningMode(mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Modus. Erlaubt: {[m.value for m in LearningMode]}"
        )

    service = get_self_learning_service(db)

    # State aus DB laden und Modus persistieren
    await service._load_state_from_db()
    service.learning_mode = learning_mode
    await service._persist_adjustments()  # Speichert auch den Modus

    return {
        "success": True,
        "learning_mode": learning_mode.value,
        "persisted": True,
    }


@router.get("/model-version")
async def get_current_model_version(
    test_id: Optional[str] = Query(None, description="Optional: Spezifischer A/B Test", max_length=64),
    current_user: User = Depends(get_current_user),  # AUTH REQUIRED
    db: AsyncSession = Depends(get_db),
):
    """
    Liefere aktuelle Modell-Version.

    Berücksichtigt aktive A/B Tests und Traffic-Split.
    Erfordert Authentifizierung.
    """
    # Validiere test_id Query-Parameter wenn gesetzt
    if test_id is not None:
        test_id = validate_test_id_path_param(test_id)

    service = get_self_learning_service(db)
    version = service.select_model_version(test_id)

    return {
        "model_version": version.value,
        "test_id": test_id,
    }
