"""API Endpoints für KI-Funktionen (Ollama).

Enterprise Feature: Lokale LLM-Integration ohne Cloud-Abhängigkeiten.

Endpoints:
- NER (Named Entity Recognition)
- Vertragsanalyse
- Dokumentenkategorisierung
- Textzusammenfassung
- Frage-Antwort
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.db.models import User
from app.services.ai.ollama_service import (
    OllamaService,
    ExtractedEntities,
    ContractAnalysis,
    get_ollama_service,
)

router = APIRouter(prefix="/ai", tags=["AI/LLM"])


# ===== Pydantic Schemas =====


class HealthResponse(BaseModel):
    """Antwort für Health-Check."""

    available: bool
    models: list[str]


class EntityExtractionRequest(BaseModel):
    """Anfrage für NER."""

    text: str = Field(..., min_length=1, max_length=50000)


class EntityExtractionResponse(BaseModel):
    """Antwort für NER."""

    persons: list[str]
    organizations: list[str]
    locations: list[str]
    money_amounts: list[str]
    dates: list[str]
    contract_numbers: list[str]


class ContractAnalysisRequest(BaseModel):
    """Anfrage für Vertragsanalyse.

    Schemathesis-Fix (W1-004 #8): Minimal-Texte wie "00" sind kein
    analysierbarer Vertrag -> 422 statt Durchreichen an Ollama.
    """

    text: str = Field(
        ...,
        min_length=10,
        max_length=50000,
        description="Vertragstext (mindestens 10 Zeichen)",
    )


class ContractAnalysisResponse(BaseModel):
    """Antwort für Vertragsanalyse."""

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notice_period_days: Optional[int] = None
    parties: list[str] = Field(default_factory=list)
    payment_terms: Optional[str] = None
    milestones: list[dict[str, str]] = Field(default_factory=list)
    auto_renewal: bool = False
    contract_type: Optional[str] = None


class CategorizeRequest(BaseModel):
    """Anfrage für Dokumentenkategorisierung."""

    text: str = Field(..., min_length=1, max_length=20000)
    available_categories: list[str] = Field(..., min_length=1)


class CategorizeResponse(BaseModel):
    """Antwort für Dokumentenkategorisierung."""

    category: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class SummarizeRequest(BaseModel):
    """Anfrage für Textzusammenfassung."""

    text: str = Field(..., min_length=1, max_length=50000)
    max_sentences: int = Field(default=3, ge=1, le=10)
    language: str = Field(default="de", pattern="^(de|en)$")


class SummarizeResponse(BaseModel):
    """Antwort für Textzusammenfassung."""

    summary: str


class QuestionAnswerRequest(BaseModel):
    """Anfrage für Frage-Antwort."""

    context: str = Field(..., min_length=1, max_length=50000)
    question: str = Field(..., min_length=1, max_length=1000)


class QuestionAnswerResponse(BaseModel):
    """Antwort für Frage-Antwort."""

    answer: str


class KeyValueExtractionRequest(BaseModel):
    """Anfrage für Schluessel-Wert-Extraktion."""

    text: str = Field(..., min_length=1, max_length=30000)
    expected_keys: Optional[list[str]] = None


class KeyValueExtractionResponse(BaseModel):
    """Antwort für Schluessel-Wert-Extraktion."""

    pairs: dict[str, str]


class GenerateRequest(BaseModel):
    """Anfrage für freie Textgenerierung."""

    prompt: str = Field(..., min_length=1, max_length=10000)
    system_prompt: Optional[str] = Field(default=None, max_length=5000)
    model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class GenerateResponse(BaseModel):
    """Antwort für Textgenerierung."""

    text: str


# ===== Dependency =====


def get_service() -> OllamaService:
    """Dependency für OllamaService."""
    return get_ollama_service()


# ===== Endpoints =====


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Prüft Ollama-Verfügbarkeit",
    description="Prüft ob Ollama laeuft und welche Modelle verfügbar sind.",
)
async def check_health(
    service: OllamaService = Depends(get_service),
) -> HealthResponse:
    """Prüft ob Ollama verfügbar ist."""
    available = await service.is_available()
    models: list[str] = []

    if available:
        models = await service.list_models()

    return HealthResponse(available=available, models=models)


@router.post(
    "/entities/extract",
    response_model=EntityExtractionResponse,
    summary="Named Entity Recognition",
    description="Extrahiert Personen, Organisationen, Orte, Geldbetraege, Daten und Vertragsnummern aus deutschem Text.",
)
async def extract_entities(
    request: EntityExtractionRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> EntityExtractionResponse:
    """Extrahiert Named Entities aus Text."""
    # Verfügbarkeit prüfen
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    result: ExtractedEntities = await service.extract_entities(request.text)

    return EntityExtractionResponse(
        persons=result.persons,
        organizations=result.organizations,
        locations=result.locations,
        money_amounts=result.money_amounts,
        dates=result.dates,
        contract_numbers=result.contract_numbers,
    )


@router.post(
    "/contracts/analyze",
    response_model=ContractAnalysisResponse,
    summary="Vertragsanalyse",
    description="Analysiert einen Vertragstext und extrahiert Laufzeiten, Kündigungsfristen und andere Details.",
)
async def analyze_contract(
    request: ContractAnalysisRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> ContractAnalysisResponse:
    """Analysiert einen Vertragstext."""
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    result: ContractAnalysis = await service.analyze_contract(request.text)

    return ContractAnalysisResponse(
        start_date=result.start_date,
        end_date=result.end_date,
        notice_period_days=result.notice_period_days,
        parties=result.parties or [],
        payment_terms=result.payment_terms,
        milestones=result.milestones or [],
        auto_renewal=result.auto_renewal,
        contract_type=result.contract_type,
    )


@router.post(
    "/documents/categorize",
    response_model=CategorizeResponse,
    summary="Dokumentenkategorisierung",
    description="Kategorisiert ein Dokument basierend auf verfügbaren Kategorien.",
)
async def categorize_document(
    request: CategorizeRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> CategorizeResponse:
    """Kategorisiert ein Dokument."""
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    category, confidence = await service.categorize_document(
        text=request.text,
        available_categories=request.available_categories,
    )

    return CategorizeResponse(category=category, confidence=confidence)


@router.post(
    "/text/summarize",
    response_model=SummarizeResponse,
    summary="Textzusammenfassung",
    description="Fasst einen Text auf eine bestimmte Anzahl Sätze zusammen.",
)
async def summarize_text(
    request: SummarizeRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> SummarizeResponse:
    """Fasst einen Text zusammen."""
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    summary = await service.summarize(
        text=request.text,
        max_sentences=request.max_sentences,
        language=request.language,
    )

    return SummarizeResponse(summary=summary)


@router.post(
    "/text/answer",
    response_model=QuestionAnswerResponse,
    summary="Frage-Antwort",
    description="Beantwortet eine Frage basierend auf dem gegebenen Kontext.",
)
async def answer_question(
    request: QuestionAnswerRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> QuestionAnswerResponse:
    """Beantwortet eine Frage basierend auf Kontext."""
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    answer = await service.answer_question(
        context=request.context,
        question=request.question,
    )

    return QuestionAnswerResponse(answer=answer)


@router.post(
    "/text/extract-pairs",
    response_model=KeyValueExtractionResponse,
    summary="Schluessel-Wert-Extraktion",
    description="Extrahiert Schluessel-Wert-Paare aus einem Dokument.",
)
async def extract_key_value_pairs(
    request: KeyValueExtractionRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> KeyValueExtractionResponse:
    """Extrahiert Schluessel-Wert-Paare."""
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    pairs = await service.extract_key_value_pairs(
        text=request.text,
        expected_keys=request.expected_keys,
    )

    return KeyValueExtractionResponse(pairs=pairs)


@router.post(
    "/generate",
    response_model=GenerateResponse,
    summary="Freie Textgenerierung",
    description="Generiert Text basierend auf einem Prompt.",
)
async def generate_text(
    request: GenerateRequest,
    current_user: User = Depends(get_current_user),
    service: OllamaService = Depends(get_service),
) -> GenerateResponse:
    """Generiert Text basierend auf Prompt."""
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama-Service ist nicht verfügbar",
        )

    text = await service.generate(
        prompt=request.prompt,
        system_prompt=request.system_prompt,
        model=request.model,
        temperature=request.temperature,
    )

    return GenerateResponse(text=text)
