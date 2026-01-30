"""LLM Service fuer RAG Intelligence Layer.

Integration mit Ollama fuer lokale LLM-Inference:
- Qwen3-8B fuer Realtime-Anfragen (<15s)
- Qwen3-14B fuer detaillierte Analysen
- Streaming Support
- Thinking Mode Control
"""

import asyncio
import json
import re
from typing import List, Optional, Dict, Any, AsyncGenerator, Literal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

import httpx
import structlog

from app.core.config import settings
from app.db.models import RAGLLMModel, RAGLLMModelType
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff in seconds
RETRYABLE_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
)


class LLMContextType(str, Enum):
    """Kontext-Typ fuer LLM-Anfragen."""
    GENERAL = "general"  # Allgemeine Dokumenten-Fragen
    CUSTOMER = "customer"  # Kunden-bezogene Anfragen
    REPORT = "report"  # Report-Generierung
    REALTIME = "realtime"  # Schnelle Telefon-Support Antworten
    EXTRACTION = "extraction"  # Daten-Extraktion aus Dokumenten


@dataclass
class LLMMessage:
    """Einzelne Nachricht fuer LLM."""
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResponse:
    """Response von LLM."""
    content: str
    thinking_content: Optional[str] = None
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    generation_time_ms: int = 0
    finish_reason: str = "stop"


@dataclass
class ModelConfig:
    """Konfiguration fuer ein LLM-Modell."""
    name: str
    context_window: int = 8192
    max_output_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    use_case: LLMContextType = LLMContextType.GENERAL


class ModelRouter:
    """Waehlt das passende Modell basierend auf Kontext und Anforderungen."""

    def __init__(self) -> None:
        self.models: Dict[str, ModelConfig] = {
            "realtime": ModelConfig(
                name=settings.DEFAULT_LLM_REALTIME,
                context_window=8192,
                max_output_tokens=2048,
                temperature=0.5,  # Weniger kreativ fuer schnelle Antworten
                use_case=LLMContextType.REALTIME
            ),
            "analysis": ModelConfig(
                name=settings.DEFAULT_LLM_ANALYSIS,
                context_window=16384,
                max_output_tokens=4096,
                temperature=0.7,
                use_case=LLMContextType.GENERAL
            ),
        }

    def select_model(
        self,
        context_type: LLMContextType,
        require_fast: bool = False
    ) -> ModelConfig:
        """Waehlt das passende Modell.

        Args:
            context_type: Art der Anfrage
            require_fast: Schnelle Antwort erforderlich (<15s)

        Returns:
            ModelConfig fuer das ausgewaehlte Modell
        """
        # Realtime-Anfragen immer mit schnellem Modell
        if require_fast or context_type == LLMContextType.REALTIME:
            return self.models["realtime"]

        # Extraktion und Reports mit groesserem Modell
        if context_type in (LLMContextType.EXTRACTION, LLMContextType.REPORT):
            return self.models["analysis"]

        # Default: Analysis-Modell
        return self.models["analysis"]


class LLMService:
    """Service fuer LLM-Inference mit Ollama.

    Features:
    - Model-Routing basierend auf Kontext
    - Streaming-Support fuer Real-Time Responses
    - Thinking Mode Control (/think, /no_think)
    - Retry-Logic bei Fehlern
    """

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_URL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.router = ModelRouter()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-load HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0)
            )
        return self._client

    async def close(self) -> None:
        """Schliesst den HTTP Client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _prepare_messages(
        self,
        messages: List[LLMMessage],
        enable_thinking: bool = True
    ) -> List[Dict[str, str]]:
        """Bereitet Nachrichten fuer Ollama vor.

        Args:
            messages: Liste von LLMMessage
            enable_thinking: Thinking-Modus aktivieren

        Returns:
            Liste von Dictionaries fuer Ollama API
        """
        prepared = []

        for msg in messages:
            content = msg.content

            # Thinking Mode Control (Qwen3 specific)
            if msg.role == "user" and not enable_thinking:
                # Deaktiviere Thinking fuer schnellere Antworten
                if not content.strip().startswith("/no_think"):
                    content = "/no_think\n" + content

            prepared.append({
                "role": msg.role,
                "content": content
            })

        return prepared

    def _extract_thinking(self, content: str) -> tuple[str, Optional[str]]:
        """Extrahiert Thinking-Content aus der Antwort.

        Qwen3 verwendet <think>...</think> Tags fuer Chain-of-Thought.

        Args:
            content: Rohe LLM-Antwort

        Returns:
            Tuple von (saubere Antwort, thinking content)
        """
        thinking = None

        # Suche nach <think>...</think> Block
        think_pattern = r'<think>(.*?)</think>'
        match = re.search(think_pattern, content, re.DOTALL)

        if match:
            thinking = match.group(1).strip()
            # Entferne Thinking-Block aus Antwort
            content = re.sub(think_pattern, '', content, flags=re.DOTALL).strip()

        return content, thinking

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        context_type: LLMContextType = LLMContextType.GENERAL,
        enable_thinking: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Generiert eine LLM-Antwort.

        Args:
            messages: Chat-Nachrichten
            model: Optionales Modell (sonst automatisch gewaehlt)
            context_type: Kontext-Typ fuer Model-Routing
            enable_thinking: Chain-of-Thought aktivieren
            temperature: Optionale Temperature-Override
            max_tokens: Optionales Token-Limit

        Returns:
            LLMResponse mit Antwort und Metadaten
        """
        start_time = datetime.now(timezone.utc)

        # Modell waehlen
        if model:
            model_config = ModelConfig(name=model)
        else:
            require_fast = context_type == LLMContextType.REALTIME
            model_config = self.router.select_model(context_type, require_fast)

        # Nachrichten vorbereiten
        prepared_messages = self._prepare_messages(messages, enable_thinking)

        # Request-Body
        request_body = {
            "model": model_config.name,
            "messages": prepared_messages,
            "stream": False,
            "options": {
                "temperature": temperature or model_config.temperature,
                "top_p": model_config.top_p,
                "num_predict": max_tokens or model_config.max_output_tokens,
            }
        }

        logger.info(
            "llm_generate_start",
            model=model_config.name,
            context_type=context_type.value,
            message_count=len(messages),
            enable_thinking=enable_thinking
        )

        # Retry-Loop mit exponential backoff
        last_error: Optional[Exception] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                response = await client.post("/api/chat", json=request_body)
                response.raise_for_status()

                data = response.json()
                raw_content = data.get("message", {}).get("content", "")

                # Thinking extrahieren
                content, thinking = self._extract_thinking(raw_content)

                # Metadaten
                generation_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                result = LLMResponse(
                    content=content,
                    thinking_content=thinking,
                    model=model_config.name,
                    tokens_input=data.get("prompt_eval_count", 0),
                    tokens_output=data.get("eval_count", 0),
                    generation_time_ms=int(generation_time * 1000),
                    finish_reason=data.get("done_reason", "stop")
                )

                logger.info(
                    "llm_generate_complete",
                    model=model_config.name,
                    tokens_input=result.tokens_input,
                    tokens_output=result.tokens_output,
                    generation_time_ms=result.generation_time_ms,
                    has_thinking=thinking is not None,
                    retry_attempt=attempt
                )

                return result

            except RETRYABLE_ERRORS as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "llm_generate_retry",
                        model=model_config.name,
                        attempt=attempt + 1,
                        max_retries=MAX_RETRIES,
                        delay_seconds=delay,
                        **safe_error_log(e)
                    )
                    await asyncio.sleep(delay)
                    continue

                # Max retries reached
                logger.error(
                    "llm_generate_max_retries",
                    model=model_config.name,
                    attempts=MAX_RETRIES + 1,
                    **safe_error_log(e)
                )
                raise RuntimeError(
                    f"LLM Fehler nach {MAX_RETRIES + 1} Versuchen: {e}"
                ) from e

            except httpx.HTTPStatusError as e:
                # HTTP errors (4xx, 5xx) - retry only for 5xx
                if e.response.status_code >= 500 and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "llm_generate_retry_5xx",
                        model=model_config.name,
                        attempt=attempt + 1,
                        status=e.response.status_code,
                        delay_seconds=delay
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "llm_generate_http_error",
                    model=model_config.name,
                    status=e.response.status_code,
                    detail=e.response.text
                )
                raise RuntimeError(f"LLM HTTP Fehler: {e.response.status_code}") from e

            except Exception as e:
                logger.exception(
                    "llm_generate_error",
                    model=model_config.name,
                    **safe_error_log(e)
                )
                raise

        # Should not reach here, but just in case
        raise RuntimeError(f"LLM Generierung fehlgeschlagen: {last_error}")

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        context_type: LLMContextType = LLMContextType.GENERAL,
        enable_thinking: bool = False,  # Meist deaktiviert fuer Streaming
        max_tokens: Optional[int] = None  # Optionales Token-Limit
    ) -> AsyncGenerator[str, None]:
        """Generiert eine Streaming-LLM-Antwort.

        Args:
            messages: Chat-Nachrichten
            model: Optionales Modell
            context_type: Kontext-Typ
            enable_thinking: Chain-of-Thought aktivieren
            max_tokens: Optionales Token-Limit (Ollama: num_predict)

        Yields:
            Text-Chunks der Antwort
        """
        # Modell waehlen
        if model:
            model_config = ModelConfig(name=model)
        else:
            require_fast = context_type == LLMContextType.REALTIME
            model_config = self.router.select_model(context_type, require_fast)

        # Nachrichten vorbereiten
        prepared_messages = self._prepare_messages(messages, enable_thinking)

        # Options aufbauen
        options = {
            "temperature": model_config.temperature,
            "top_p": model_config.top_p,
        }
        if max_tokens:
            options["num_predict"] = max_tokens

        request_body = {
            "model": model_config.name,
            "messages": prepared_messages,
            "stream": True,
            "options": options
        }

        logger.info(
            "llm_stream_start",
            model=model_config.name,
            context_type=context_type.value
        )

        try:
            client = await self._get_client()

            async with client.stream("POST", "/api/chat", json=request_body) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content

                            # Check if done
                            if data.get("done", False):
                                break

                        except json.JSONDecodeError:
                            continue

            logger.info("llm_stream_complete", model=model_config.name)

        except Exception as e:
            logger.exception(
                "llm_stream_error",
                model=model_config.name,
                **safe_error_log(e)
            )
            raise

    async def check_health(self) -> Dict[str, Any]:
        """Prueft die Verbindung zu Ollama.

        Returns:
            Health-Status mit verfuegbaren Modellen
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()

            data = response.json()
            models = [m.get("name") for m in data.get("models", [])]

            return {
                "status": "healthy",
                "ollama_url": self.base_url,
                "available_models": models,
                "configured_realtime": settings.DEFAULT_LLM_REALTIME,
                "configured_analysis": settings.DEFAULT_LLM_ANALYSIS
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": safe_error_detail(e, "Vorgang"),
                "ollama_url": self.base_url
            }

    async def list_models(self) -> List[str]:
        """Listet alle verfuegbaren Modelle.

        Returns:
            Liste von Modellnamen
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()

            data = response.json()
            return [m.get("name") for m in data.get("models", [])]

        except Exception as e:
            logger.error("llm_list_models_error", **safe_error_log(e))
            return []

    async def pull_model(self, model_name: str) -> bool:
        """Laedt ein Modell herunter.

        Args:
            model_name: Name des Modells (z.B. "qwen3:8b")

        Returns:
            True bei Erfolg
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/api/pull",
                json={"name": model_name},
                timeout=httpx.Timeout(3600.0)  # 1 Stunde fuer Download
            )
            response.raise_for_status()

            logger.info("llm_model_pulled", model=model_name)
            return True

        except Exception as e:
            logger.error("llm_pull_model_error", model=model_name, **safe_error_log(e))
            return False


# Singleton-Instanz
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Gibt die LLM-Service-Instanz zurueck."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
