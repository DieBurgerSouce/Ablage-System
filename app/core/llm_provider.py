# -*- coding: utf-8 -*-
"""
Provider-Agnostischer LLM Abstraktions-Layer.

Enterprise Feature: Flexibler KI-Provider der lokal (Ollama, vLLM, LM Studio)
oder Cloud (Anthropic, OpenAI) nutzen kann. Konfigurierbar pro Agent/Task.

Architektur:
- LLMProvider ABC: Gemeinsames Interface fuer alle Provider
- LLMRegistry: Registrierung und Auswahl von Providern
- LLMRouter: Routet Anfragen basierend auf Task-Typ zum optimalen Provider/Modell

100% On-Premises als Default. Cloud-Provider optional konfigurierbar.

Feinpoliert und durchdacht - Provider-agnostische KI.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Union,
)

import structlog

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# DATENTYPEN
# =============================================================================


class LLMRole(str, Enum):
    """Rollen in einer Chat-Nachricht."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class TaskComplexity(str, Enum):
    """Komplexitaet einer Aufgabe fuer Modell-Routing."""

    SIMPLE = "simple"          # Keyword-Extraktion, Klassifikation
    MODERATE = "moderate"      # NER, Zusammenfassung, Kategorisierung
    COMPLEX = "complex"        # Vertragsanalyse, NLQ, Anomalie-Erklaerung
    REASONING = "reasoning"    # Multi-Step Reasoning, Planung, Entscheidungen


@dataclass(frozen=True)
class ChatMessage:
    """Eine Chat-Nachricht."""

    role: LLMRole
    content: str


@dataclass
class LLMResponse:
    """Antwort eines LLM-Providers."""

    content: str
    model: str
    provider: str
    usage: LLMUsage
    latency_ms: float
    raw_response: Optional[Dict[str, object]] = None


@dataclass
class LLMUsage:
    """Token-Verbrauch."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMStreamChunk:
    """Ein Chunk aus einem Streaming-Response."""

    content: str
    done: bool = False
    model: Optional[str] = None


@dataclass
class ModelConfig:
    """Konfiguration fuer ein spezifisches Modell."""

    model_id: str
    provider_name: str
    display_name: str
    max_context_length: int = 8192
    supports_streaming: bool = True
    supports_json_mode: bool = False
    complexity_level: TaskComplexity = TaskComplexity.MODERATE
    cost_per_1k_tokens: float = 0.0  # 0 = lokal/kostenlos
    tags: List[str] = field(default_factory=list)


@dataclass
class GenerationParams:
    """Parameter fuer Text-Generierung."""

    temperature: float = 0.1
    max_tokens: int = 2048
    top_p: float = 0.9
    stop_sequences: Optional[List[str]] = None
    json_mode: bool = False
    stream: bool = False


# =============================================================================
# PROVIDER INTERFACE
# =============================================================================


class LLMProvider(ABC):
    """
    Abstraktes Interface fuer LLM-Provider.

    Jeder Provider (Ollama, vLLM, Anthropic, OpenAI) implementiert
    dieses Interface fuer einheitliche Nutzung.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Provider-Name."""

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """True wenn Provider lokal laeuft (kein Cloud-API-Call)."""

    @abstractmethod
    async def generate(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: GenerationParams,
    ) -> LLMResponse:
        """
        Generiert eine Antwort.

        Args:
            messages: Chat-Verlauf
            model: Modell-ID
            params: Generierungs-Parameter

        Returns:
            LLMResponse mit Inhalt und Metadaten
        """

    @abstractmethod
    async def stream(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: GenerationParams,
    ) -> AsyncIterator[LLMStreamChunk]:
        """
        Generiert eine Streaming-Antwort.

        Args:
            messages: Chat-Verlauf
            model: Modell-ID
            params: Generierungs-Parameter

        Yields:
            LLMStreamChunk pro Chunk
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Prueft ob der Provider erreichbar ist."""

    @abstractmethod
    def list_models(self) -> List[ModelConfig]:
        """Listet verfuegbare Modelle."""


# =============================================================================
# OLLAMA PROVIDER (DEFAULT - ON-PREMISES)
# =============================================================================


class OllamaProvider(LLMProvider):
    """
    Ollama Provider fuer lokale LLM-Ausfuehrung.

    Default-Provider fuer 100% On-Premises Betrieb.
    Unterstuetzt alle gaengigen Open-Source Modelle.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
        default_model: str = "mistral",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._default_model = default_model
        self._models: List[ModelConfig] = [
            ModelConfig(
                model_id="mistral",
                provider_name="ollama",
                display_name="Mistral 7B",
                max_context_length=8192,
                complexity_level=TaskComplexity.MODERATE,
                tags=["general", "german", "fast"],
            ),
            ModelConfig(
                model_id="llama3.1:8b",
                provider_name="ollama",
                display_name="Llama 3.1 8B",
                max_context_length=131072,
                complexity_level=TaskComplexity.COMPLEX,
                tags=["general", "reasoning", "long-context"],
            ),
            ModelConfig(
                model_id="phi3:mini",
                provider_name="ollama",
                display_name="Phi-3 Mini",
                max_context_length=4096,
                complexity_level=TaskComplexity.SIMPLE,
                tags=["fast", "classification", "extraction"],
            ),
        ]

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def is_local(self) -> bool:
        return True

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: GenerationParams,
    ) -> LLMResponse:
        import httpx

        start = time.monotonic()
        model = model or self._default_model

        payload: Dict[str, object] = {
            "model": model,
            "messages": [
                {"role": m.role.value, "content": m.content} for m in messages
            ],
            "stream": False,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
                "top_p": params.top_p,
            },
        }

        if params.json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        latency_ms = (time.monotonic() - start) * 1000
        content = data.get("message", {}).get("content", "")

        return LLMResponse(
            content=content,
            model=model,
            provider="ollama",
            usage=LLMUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0)
                + data.get("eval_count", 0),
            ),
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: GenerationParams,
    ) -> AsyncIterator[LLMStreamChunk]:
        import httpx

        model = model or self._default_model
        payload: Dict[str, object] = {
            "model": model,
            "messages": [
                {"role": m.role.value, "content": m.content} for m in messages
            ],
            "stream": True,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
                "top_p": params.top_p,
            },
        }

        if params.json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        done = data.get("done", False)
                        yield LLMStreamChunk(
                            content=content,
                            done=done,
                            model=model,
                        )
                    except json.JSONDecodeError:
                        continue

    async def is_available(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[ModelConfig]:
        return list(self._models)

    def add_model(self, config: ModelConfig) -> None:
        """Fuegt ein neues Modell zur Liste hinzu."""
        self._models.append(config)


# =============================================================================
# LLM REGISTRY
# =============================================================================


class LLMRegistry:
    """
    Registry fuer LLM-Provider.

    Verwaltet alle registrierten Provider und ermoeglicht
    dynamisches Hinzufuegen neuer Provider zur Laufzeit.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {}
        self._default_provider: Optional[str] = None

    def register(
        self,
        provider: LLMProvider,
        set_default: bool = False,
    ) -> None:
        """Registriert einen Provider."""
        self._providers[provider.name] = provider
        if set_default or self._default_provider is None:
            self._default_provider = provider.name
        logger.info(
            "llm_provider_registered",
            provider=provider.name,
            is_local=provider.is_local,
            is_default=self._default_provider == provider.name,
        )

    def get(self, name: str) -> LLMProvider:
        """Holt einen Provider nach Name."""
        provider = self._providers.get(name)
        if not provider:
            available = list(self._providers.keys())
            raise KeyError(
                f"LLM-Provider '{name}' nicht gefunden. "
                f"Verfuegbar: {available}"
            )
        return provider

    @property
    def default(self) -> LLMProvider:
        """Gibt den Default-Provider zurueck."""
        if not self._default_provider:
            raise RuntimeError("Kein LLM-Provider registriert")
        return self._providers[self._default_provider]

    @property
    def providers(self) -> Dict[str, LLMProvider]:
        """Alle registrierten Provider."""
        return dict(self._providers)

    async def get_available(self) -> List[str]:
        """Prueft welche Provider erreichbar sind."""
        available = []
        for name, provider in self._providers.items():
            try:
                if await provider.is_available():
                    available.append(name)
            except Exception:
                pass
        return available

    def list_all_models(self) -> List[ModelConfig]:
        """Listet alle Modelle aller Provider."""
        models: List[ModelConfig] = []
        for provider in self._providers.values():
            models.extend(provider.list_models())
        return models


# =============================================================================
# LLM ROUTER
# =============================================================================


class LLMRouter:
    """
    Intelligenter Router der Anfragen zum optimalen Provider/Modell leitet.

    Routet basierend auf:
    - Task-Komplexitaet
    - Modell-Verfuegbarkeit
    - Lokal-bevorzugt Policy (On-Premises first)
    - Fallback-Kette
    """

    def __init__(self, registry: LLMRegistry) -> None:
        self._registry = registry

    async def route(
        self,
        messages: Sequence[ChatMessage],
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        params: Optional[GenerationParams] = None,
        preferred_provider: Optional[str] = None,
        preferred_model: Optional[str] = None,
        require_local: bool = True,
    ) -> LLMResponse:
        """
        Routet eine Anfrage zum optimalen Provider/Modell.

        Args:
            messages: Chat-Verlauf
            complexity: Aufgaben-Komplexitaet
            params: Generierungs-Parameter
            preferred_provider: Bevorzugter Provider (optional)
            preferred_model: Bevorzugtes Modell (optional)
            require_local: Nur lokale Provider erlauben (Default: True)

        Returns:
            LLMResponse vom ausgewaehlten Provider
        """
        params = params or GenerationParams()

        # 1. Bevorzugten Provider/Modell versuchen
        if preferred_provider and preferred_model:
            try:
                provider = self._registry.get(preferred_provider)
                if not require_local or provider.is_local:
                    return await provider.generate(messages, preferred_model, params)
            except Exception as e:
                logger.warning(
                    "preferred_provider_failed",
                    provider=preferred_provider,
                    model=preferred_model,
                    error=str(e),
                )

        # 2. Bestes Modell fuer Komplexitaet finden
        provider, model = self._select_best_model(complexity, require_local)

        try:
            return await provider.generate(messages, model, params)
        except Exception as e:
            logger.error(
                "llm_route_failed",
                provider=provider.name,
                model=model,
                **safe_error_log(e),
            )
            # 3. Fallback: Default-Provider mit Default-Modell
            default = self._registry.default
            default_models = default.list_models()
            if default_models:
                return await default.generate(
                    messages, default_models[0].model_id, params,
                )
            raise

    async def route_stream(
        self,
        messages: Sequence[ChatMessage],
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        params: Optional[GenerationParams] = None,
        require_local: bool = True,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Routet eine Streaming-Anfrage."""
        params = params or GenerationParams(stream=True)
        provider, model = self._select_best_model(complexity, require_local)
        async for chunk in provider.stream(messages, model, params):
            yield chunk

    def _select_best_model(
        self,
        complexity: TaskComplexity,
        require_local: bool,
    ) -> tuple[LLMProvider, str]:
        """Waehlt das beste Modell fuer eine Komplexitaets-Stufe."""
        all_models = self._registry.list_all_models()

        # Filter: nur lokale wenn noetig
        if require_local:
            candidates = [
                m for m in all_models
                if self._registry.get(m.provider_name).is_local
            ]
        else:
            candidates = all_models

        if not candidates:
            # Fallback auf alle Modelle
            candidates = all_models

        # Sortiere nach Eignung fuer Komplexitaet
        complexity_order = {
            TaskComplexity.SIMPLE: 0,
            TaskComplexity.MODERATE: 1,
            TaskComplexity.COMPLEX: 2,
            TaskComplexity.REASONING: 3,
        }

        target = complexity_order[complexity]

        def score(m: ModelConfig) -> int:
            model_level = complexity_order.get(m.complexity_level, 1)
            # Bevorzuge Modelle die zur Komplexitaet passen
            # (nicht zu gross, nicht zu klein)
            return abs(model_level - target)

        candidates.sort(key=score)
        best = candidates[0]

        provider = self._registry.get(best.provider_name)
        return provider, best.model_id


# =============================================================================
# SINGLETON & FACTORY
# =============================================================================

_registry: Optional[LLMRegistry] = None
_router: Optional[LLMRouter] = None


def get_llm_registry() -> LLMRegistry:
    """Gibt die globale LLM-Registry zurueck (Lazy Init)."""
    global _registry
    if _registry is None:
        _registry = LLMRegistry()
        # Default: Ollama als lokaler Provider
        ollama = OllamaProvider()
        _registry.register(ollama, set_default=True)
        logger.info("llm_registry_initialized", default_provider="ollama")
    return _registry


def get_llm_router() -> LLMRouter:
    """Gibt den globalen LLM-Router zurueck (Lazy Init)."""
    global _router
    if _router is None:
        _router = LLMRouter(get_llm_registry())
    return _router


def register_provider(provider: LLMProvider, set_default: bool = False) -> None:
    """Registriert einen neuen LLM-Provider global."""
    registry = get_llm_registry()
    registry.register(provider, set_default=set_default)
