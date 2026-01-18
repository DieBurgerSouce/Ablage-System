"""Unit Tests fuer LLM Service.

Testet:
- Model Routing
- Message Preparation
- Thinking Extraction
- Health Check
- Streaming (Mock)
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json

from app.services.rag.llm_service import (
    LLMService,
    LLMMessage,
    LLMResponse,
    LLMContextType,
    ModelRouter,
    ModelConfig,
    get_llm_service,
)


class TestModelConfig:
    """Tests fuer ModelConfig Dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration."""
        config = ModelConfig(name="test-model")

        assert config.name == "test-model"
        assert config.context_window == 8192
        assert config.max_output_tokens == 4096
        assert config.temperature == 0.7
        assert config.top_p == 0.9

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = ModelConfig(
            name="qwen3:14b",
            context_window=16384,
            temperature=0.5,
            use_case=LLMContextType.REALTIME
        )

        assert config.name == "qwen3:14b"
        assert config.context_window == 16384
        assert config.temperature == 0.5
        assert config.use_case == LLMContextType.REALTIME


class TestModelRouter:
    """Tests fuer ModelRouter."""

    @pytest.fixture
    def router(self) -> ModelRouter:
        return ModelRouter()

    def test_select_model_realtime(self, router: ModelRouter) -> None:
        """Test model selection for realtime context."""
        config = router.select_model(LLMContextType.REALTIME)
        assert "8b" in config.name.lower() or config.use_case == LLMContextType.REALTIME

    def test_select_model_analysis(self, router: ModelRouter) -> None:
        """Test model selection for analysis context."""
        config = router.select_model(LLMContextType.EXTRACTION)
        # Analysis model should be larger
        assert config == router.models["analysis"]

    def test_select_model_require_fast(self, router: ModelRouter) -> None:
        """Test model selection with require_fast flag."""
        config = router.select_model(LLMContextType.GENERAL, require_fast=True)
        assert config == router.models["realtime"]

    def test_select_model_report(self, router: ModelRouter) -> None:
        """Test model selection for reports."""
        config = router.select_model(LLMContextType.REPORT)
        assert config == router.models["analysis"]


class TestLLMMessage:
    """Tests fuer LLMMessage Dataclass."""

    def test_system_message(self) -> None:
        """Test creating system message."""
        msg = LLMMessage(role="system", content="Du bist ein Assistent.")
        assert msg.role == "system"
        assert msg.content == "Du bist ein Assistent."

    def test_user_message(self) -> None:
        """Test creating user message."""
        msg = LLMMessage(role="user", content="Was ist 2+2?")
        assert msg.role == "user"

    def test_assistant_message(self) -> None:
        """Test creating assistant message."""
        msg = LLMMessage(role="assistant", content="4")
        assert msg.role == "assistant"


class TestLLMResponse:
    """Tests fuer LLMResponse Dataclass."""

    def test_basic_response(self) -> None:
        """Test basic response."""
        response = LLMResponse(
            content="Die Antwort ist 42.",
            model="qwen3:8b"
        )

        assert response.content == "Die Antwort ist 42."
        assert response.model == "qwen3:8b"
        assert response.thinking_content is None

    def test_response_with_thinking(self) -> None:
        """Test response with thinking content."""
        response = LLMResponse(
            content="Die Antwort ist 42.",
            thinking_content="Ich muss nachdenken...",
            model="qwen3:14b",
            tokens_input=100,
            tokens_output=50,
            generation_time_ms=1500
        )

        assert response.thinking_content == "Ich muss nachdenken..."
        assert response.tokens_input == 100
        assert response.tokens_output == 50
        assert response.generation_time_ms == 1500


class TestLLMService:
    """Tests fuer LLMService."""

    @pytest.fixture
    def service(self) -> LLMService:
        return LLMService()

    # ==========================================================================
    # Message Preparation Tests
    # ==========================================================================

    def test_prepare_messages_basic(self, service: LLMService) -> None:
        """Test basic message preparation."""
        messages = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="Frage")
        ]

        prepared = service._prepare_messages(messages, enable_thinking=True)

        assert len(prepared) == 2
        assert prepared[0]["role"] == "system"
        assert prepared[1]["role"] == "user"

    def test_prepare_messages_no_thinking(self, service: LLMService) -> None:
        """Test message preparation with thinking disabled."""
        messages = [
            LLMMessage(role="user", content="Frage")
        ]

        prepared = service._prepare_messages(messages, enable_thinking=False)

        assert len(prepared) == 1
        # Should have /no_think prefix
        assert "/no_think" in prepared[0]["content"]

    def test_prepare_messages_no_thinking_already_has_prefix(self, service: LLMService) -> None:
        """Test that /no_think is not duplicated."""
        messages = [
            LLMMessage(role="user", content="/no_think\nFrage")
        ]

        prepared = service._prepare_messages(messages, enable_thinking=False)

        # Should not duplicate /no_think
        assert prepared[0]["content"].count("/no_think") == 1

    # ==========================================================================
    # Thinking Extraction Tests
    # ==========================================================================

    def test_extract_thinking_with_tags(self, service: LLMService) -> None:
        """Test extracting thinking from response."""
        content = """<think>
Ich muss ueber die Frage nachdenken.
Dies ist ein komplexes Problem.
</think>

Die Antwort ist 42."""

        clean_content, thinking = service._extract_thinking(content)

        assert "42" in clean_content
        assert "<think>" not in clean_content
        assert thinking is not None
        assert "nachdenken" in thinking

    def test_extract_thinking_without_tags(self, service: LLMService) -> None:
        """Test extracting from response without thinking tags."""
        content = "Die Antwort ist 42."

        clean_content, thinking = service._extract_thinking(content)

        assert clean_content == "Die Antwort ist 42."
        assert thinking is None

    def test_extract_thinking_multiline(self, service: LLMService) -> None:
        """Test extracting multiline thinking."""
        content = """<think>
Schritt 1: Analysiere die Frage
Schritt 2: Recherchiere
Schritt 3: Formuliere Antwort
</think>

Die Antwort basiert auf meiner Analyse."""

        clean_content, thinking = service._extract_thinking(content)

        assert "Schritt 1" in thinking
        assert "Schritt 2" in thinking
        assert "Schritt 3" in thinking
        assert "Analyse" in clean_content

    # ==========================================================================
    # Health Check Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_check_health_success(self, service: LLMService) -> None:
        """Test health check success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen3:8b"},
                {"name": "qwen3:14b"}
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(service, '_get_client', return_value=mock_client):
            health = await service.check_health()

        assert health["status"] == "healthy"
        assert "qwen3:8b" in health["available_models"]
        assert "qwen3:14b" in health["available_models"]

    @pytest.mark.asyncio
    async def test_check_health_failure(self, service: LLMService) -> None:
        """Test health check failure."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

        with patch.object(service, '_get_client', return_value=mock_client):
            health = await service.check_health()

        assert health["status"] == "unhealthy"
        assert "error" in health

    # ==========================================================================
    # Generate Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_generate_success(self, service: LLMService) -> None:
        """Test successful generation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Die Antwort ist 42."},
            "prompt_eval_count": 50,
            "eval_count": 20,
            "done_reason": "stop"
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(service, '_get_client', return_value=mock_client):
            messages = [LLMMessage(role="user", content="Was ist 6*7?")]
            response = await service.generate(messages)

        assert response.content == "Die Antwort ist 42."
        assert response.tokens_input == 50
        assert response.tokens_output == 20
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_generate_with_thinking(self, service: LLMService) -> None:
        """Test generation with thinking content."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "<think>Rechnung: 6*7=42</think>\n\nDie Antwort ist 42."
            },
            "prompt_eval_count": 50,
            "eval_count": 30,
            "done_reason": "stop"
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(service, '_get_client', return_value=mock_client):
            messages = [LLMMessage(role="user", content="Was ist 6*7?")]
            response = await service.generate(messages, enable_thinking=True)

        assert "42" in response.content
        assert response.thinking_content is not None
        assert "Rechnung" in response.thinking_content

    @pytest.mark.asyncio
    async def test_generate_realtime_context(self, service: LLMService) -> None:
        """Test generation uses fast model for realtime context."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Schnelle Antwort."},
            "prompt_eval_count": 20,
            "eval_count": 10,
            "done_reason": "stop"
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(service, '_get_client', return_value=mock_client):
            messages = [LLMMessage(role="user", content="Telefon-Anfrage")]
            response = await service.generate(
                messages,
                context_type=LLMContextType.REALTIME
            )

        # Check that a small/fast model was used (7b or 8b)
        call_args = mock_client.post.call_args
        request_body = call_args[1]["json"]
        model_name = request_body["model"].lower()
        assert "7b" in model_name or "8b" in model_name, f"Expected fast model (7b/8b), got: {model_name}"

    @pytest.mark.asyncio
    async def test_generate_timeout(self, service: LLMService) -> None:
        """Test generation timeout handling."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with patch.object(service, '_get_client', return_value=mock_client):
            messages = [LLMMessage(role="user", content="Frage")]

            with pytest.raises(RuntimeError, match="Timeout"):
                await service.generate(messages)

    # ==========================================================================
    # List Models Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_list_models_success(self, service: LLMService) -> None:
        """Test listing available models."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:8b"},
                {"name": "qwen3:8b"},
                {"name": "mistral:7b"}
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(service, '_get_client', return_value=mock_client):
            models = await service.list_models()

        assert len(models) == 3
        assert "llama3:8b" in models
        assert "qwen3:8b" in models

    @pytest.mark.asyncio
    async def test_list_models_error(self, service: LLMService) -> None:
        """Test listing models handles errors."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Error"))

        with patch.object(service, '_get_client', return_value=mock_client):
            models = await service.list_models()

        assert models == []

    # ==========================================================================
    # Close Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_close_client(self, service: LLMService) -> None:
        """Test closing HTTP client."""
        mock_client = AsyncMock()
        service._client = mock_client

        await service.close()

        mock_client.aclose.assert_called_once()
        assert service._client is None


class TestGetLLMService:
    """Tests fuer get_llm_service Factory."""

    def test_returns_llm_service(self) -> None:
        """Test that factory returns correct type."""
        # Reset singleton
        import app.services.rag.llm_service as module
        module._llm_service = None

        service = get_llm_service()
        assert isinstance(service, LLMService)

    def test_singleton_pattern(self) -> None:
        """Test singleton pattern."""
        import app.services.rag.llm_service as module
        module._llm_service = None

        service1 = get_llm_service()
        service2 = get_llm_service()

        assert service1 is service2


class TestLLMContextType:
    """Tests fuer LLMContextType Enum."""

    def test_all_context_types(self) -> None:
        """Test all context types exist."""
        assert LLMContextType.GENERAL.value == "general"
        assert LLMContextType.CUSTOMER.value == "customer"
        assert LLMContextType.REPORT.value == "report"
        assert LLMContextType.REALTIME.value == "realtime"
        assert LLMContextType.EXTRACTION.value == "extraction"
