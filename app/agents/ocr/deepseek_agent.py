"""
DeepSeek-Janus-Pro OCR Agent.

Specialized agent for complex document layouts using DeepSeek's
multimodal vision-language model.

Best for:
- Complex table structures
- Handwritten text and Fraktur fonts
- Mixed German/English documents
- Documents requiring semantic understanding
- Formula recognition
- Multimodal document analysis
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoModelForCausalLM

# BitsAndBytes has limited Windows support - import conditionally
BITSANDBYTES_AVAILABLE = False
BitsAndBytesConfig = None
try:
    from transformers import BitsAndBytesConfig as _BitsAndBytesConfig
    import bitsandbytes
    BitsAndBytesConfig = _BitsAndBytesConfig
    BITSANDBYTES_AVAILABLE = True
except ImportError:
    pass

# GPTQ quantization - works on Windows
GPTQ_AVAILABLE = False
try:
    from auto_gptq import AutoGPTQForCausalLM
    GPTQ_AVAILABLE = True
except ImportError:
    AutoGPTQForCausalLM = None

# AWQ quantization - works on Windows
AWQ_AVAILABLE = False
try:
    from awq import AutoAWQForCausalLM
    AWQ_AVAILABLE = True
except ImportError:
    AutoAWQForCausalLM = None

from app.agents.base import AgentResourceError, OCRAgent, OCRResult
from app.gpu_manager import GPUManager
from app.core.exceptions import OCRGPUOutOfMemoryError, InferenceTimeoutError
from app.services.circuit_breaker import circuit_breaker_protected, get_circuit_breaker_registry
from transformers import LogitsProcessor

# Platform detection
IS_WINDOWS = sys.platform == "win32"


class VRAMMonitorLogitsProcessor(LogitsProcessor):
    """
    Logits processor that monitors VRAM usage during token generation.

    Checks VRAM every N tokens and logs warnings if memory pressure is detected.
    Can optionally trigger early stopping on critical memory levels.
    """

    def __init__(
        self,
        check_interval: int = 100,
        warning_threshold_gb: float = 13.6,  # 85% of 16GB RTX 4080
        critical_threshold_gb: float = 15.0,  # ~94% - near OOM
        logger: Optional[Any] = None
    ):
        self.check_interval = check_interval
        self.warning_threshold_gb = warning_threshold_gb
        self.critical_threshold_gb = critical_threshold_gb
        self.logger = logger
        self.token_count = 0
        self.vram_warnings: List[Dict[str, Any]] = []

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        """Called for each generated token. Monitor VRAM periodically."""
        self.token_count += 1

        # Check VRAM every N tokens
        if self.token_count % self.check_interval == 0:
            if torch.cuda.is_available():
                current_vram_gb = torch.cuda.memory_allocated() / 1024**3

                if current_vram_gb > self.critical_threshold_gb:
                    # Critical: Log error and consider stopping
                    if self.logger:
                        self.logger.error(
                            "vram_critical_pressure",
                            current_gb=round(current_vram_gb, 2),
                            threshold_gb=self.critical_threshold_gb,
                            tokens_generated=self.token_count,
                            message="Kritischer VRAM-Druck erkannt - OOM-Risiko!"
                        )
                    self.vram_warnings.append({
                        "level": "critical",
                        "vram_gb": current_vram_gb,
                        "token": self.token_count
                    })
                elif current_vram_gb > self.warning_threshold_gb:
                    # Warning: Log and continue
                    if self.logger:
                        self.logger.warning(
                            "vram_pressure_detected",
                            current_gb=round(current_vram_gb, 2),
                            threshold_gb=self.warning_threshold_gb,
                            tokens_generated=self.token_count
                        )
                    self.vram_warnings.append({
                        "level": "warning",
                        "vram_gb": current_vram_gb,
                        "token": self.token_count
                    })

        # Return scores unchanged (we're only monitoring)
        return scores

    def get_warnings(self) -> List[Dict[str, Any]]:
        """Return collected VRAM warnings."""
        return self.vram_warnings

    def reset(self) -> None:
        """Reset counters for next inference."""
        self.token_count = 0
        self.vram_warnings = []


class DeepSeekAgent(OCRAgent):
    """
    DeepSeek-Janus-Pro OCR processing agent.

    Requires:
    - 24GB VRAM for 7B model (or 12GB with quantization)
    - CUDA-capable GPU
    - DeepSeek-Janus-Pro model weights
    """

    # Model configuration - using 7B as per initial-prompt.md
    MODEL_NAME = "deepseek-ai/Janus-Pro-7B"
    VRAM_REQUIRED_GB = 24  # Can be reduced to 12GB with 4-bit quantization
    MAX_BATCH_SIZE = 4
    ENABLE_QUANTIZATION = True  # Enable for RTX 4080 16GB
    MODEL_LOADING_TIMEOUT = 600.0  # 10 Minuten Timeout für Model-Loading (erste Initialisierung kann langsam sein)
    INFERENCE_TIMEOUT = 300.0  # 5 Minuten Timeout für Inference (kann bei grossen Dokumenten lange dauern)

    # Fallback configuration
    FALLBACK_BACKENDS = ["surya", "got_ocr"]  # CPU-capable backends for OOM fallback
    SUPPORTS_CPU_FALLBACK = False  # DeepSeek requires GPU, but can signal fallback to other backends

    # Class-level lock to prevent concurrent model loading (race condition fix)
    _model_lock: Optional[asyncio.Lock] = None
    # Class-level flag to track if model loading has permanently failed
    _model_load_failed: bool = False
    _model_load_error: Optional[str] = None

    # Class-level spaCy model cache (loaded once, shared across instances)
    _spacy_nlp: Optional[Any] = None
    _spacy_initialized: bool = False

    # Timeout for acquiring the model lock (prevents deadlock on failed load)
    LOCK_ACQUISITION_TIMEOUT = 300.0  # 5 minutes

    def __init__(self):
        super().__init__(
            name="deepseek_ocr_agent",
            gpu_required=True,
            vram_gb=self.VRAM_REQUIRED_GB,
        )
        self.gpu_manager = GPUManager()
        self.model = None
        self.processor = None
        self._model_loaded = False
        self._quantization_active = False  # Set during model loading

        # Initialize class-level lock if not exists (thread-safe singleton)
        if DeepSeekAgent._model_lock is None:
            DeepSeekAgent._model_lock = asyncio.Lock()

        # Initialize spaCy model once (lazy loading on first use)
        if not DeepSeekAgent._spacy_initialized:
            self._init_spacy_model()

    @property
    def supports_cpu_fallback(self) -> bool:
        """
        Indicates whether this backend can fall back to CPU.

        DeepSeek requires GPU but can signal that other backends should be tried.
        """
        return self.SUPPORTS_CPU_FALLBACK

    @property
    def fallback_backends(self) -> List[str]:
        """
        List of backends that can be used as fallback when this backend fails with OOM.
        """
        return self.FALLBACK_BACKENDS

    def _init_spacy_model(self) -> None:
        """
        Initialize spaCy German model once for all instances.

        OPTIMIERUNG: spaCy wird nur einmal geladen statt bei jedem _extract_entities Aufruf.
        Dies spart ~200ms pro Dokument.
        """
        DeepSeekAgent._spacy_initialized = True  # Mark as initialized even if loading fails

        try:
            import spacy

            # Try models in order of preference: lg > md > sm
            models_to_try = ["de_core_news_lg", "de_core_news_md", "de_core_news_sm"]

            for model_name in models_to_try:
                try:
                    DeepSeekAgent._spacy_nlp = spacy.load(model_name)
                    self.logger.info(
                        "spacy_model_preloaded",
                        model=model_name,
                        message="spaCy Model erfolgreich geladen"
                    )
                    return
                except OSError:
                    continue

            # Kein Modell verfügbar
            self.logger.warning(
                "spacy_model_not_available",
                message="Kein deutsches spaCy-Modell gefunden. "
                        "Installieren mit: python -m spacy download de_core_news_lg"
            )
            DeepSeekAgent._spacy_nlp = None

        except ImportError:
            self.logger.debug("spacy_not_installed")
            DeepSeekAgent._spacy_nlp = None
        except Exception as e:
            self.logger.warning("spacy_init_error", error=str(e))
            DeepSeekAgent._spacy_nlp = None

    @circuit_breaker_protected("deepseek")
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process document with DeepSeek OCR.

        Input:
            document_id: str - Document identifier
            image_path: str - Path to image file
            language: str - Primary language (default: "de")
            options: dict - Additional processing options

        Returns:
            text: str - Extracted text
            confidence: float - Overall confidence score
            layout: dict - Detected layout structure
            entities: list - Extracted business entities

        Raises:
            OCRGPUOutOfMemoryError: When GPU runs out of memory (signals fallback available)
            InferenceTimeoutError: When inference takes too long
            CircuitBreakerError: When backend is in circuit-open state
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]
        image_path = Path(input_data["image_path"])
        language = input_data.get("language", "de")
        options = input_data.get("options", {})

        self.logger.info(
            "deepseek_processing_started",
            document_id=document_id,
            image_path=str(image_path),
            language=language,
        )

        # Allocate GPU resources
        await self._ensure_gpu_allocated()

        # Load model if not already loaded
        await self._load_model()

        try:
            # Load and preprocess image
            image = await self._load_image(image_path)

            # Run OCR inference with timeout protection
            inference_timeout = options.get("inference_timeout", self.INFERENCE_TIMEOUT)
            ocr_result = await self._run_inference_with_timeout(
                image, language, options, timeout_seconds=inference_timeout, document_id=document_id
            )

            # Post-process results - returns OCRResult
            result = await self._postprocess_result(ocr_result, options)

            self.logger.info(
                "deepseek_processing_completed",
                document_id=document_id,
                text_length=len(result.text),
                confidence=result.confidence,
            )

            # Rueckgabe als standardisiertes Dictionary
            return result.to_dict()

        except torch.cuda.OutOfMemoryError as e:
            self.logger.error(
                "deepseek_gpu_oom",
                document_id=document_id,
                error=str(e),
                fallback_backends=self.FALLBACK_BACKENDS,
            )
            # Record OOM metric
            from app.ml.metrics import get_ml_metrics
            metrics = get_ml_metrics()
            metrics.record_ocr_oom_error("deepseek")

            # Try to recover GPU resources
            await self._handle_gpu_oom()

            # Get current GPU memory info for detailed error
            available_gb = None
            if torch.cuda.is_available():
                try:
                    free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
                    available_gb = round(free_mem, 2)
                except Exception as e:
                    self.logger.debug(
                        "gpu_mem_info_failed",
                        error_type=type(e).__name__,
                    )

            # Raise specific exception that signals fallback availability
            raise OCRGPUOutOfMemoryError(
                backend="deepseek",
                document_id=document_id,
                required_gb=self.VRAM_REQUIRED_GB,
                available_gb=available_gb,
                fallback_backends=self.FALLBACK_BACKENDS
            )

        except InferenceTimeoutError:
            # Re-raise timeout errors (already properly formatted)
            raise

        except Exception as e:
            self.logger.error(
                "deepseek_processing_error",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            # Cleanup GPU resources if needed
            await self._cleanup_gpu_resources()

    async def _run_inference_with_timeout(
        self,
        image: Image.Image,
        language: str,
        options: Dict[str, Any],
        timeout_seconds: float,
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run inference with timeout protection.

        Wraps _run_inference with asyncio.wait_for to prevent indefinite hangs
        during model generation.

        Args:
            image: Input image
            language: Target language
            options: Processing options
            timeout_seconds: Maximum time allowed for inference
            document_id: Document ID for error reporting

        Returns:
            OCR result dictionary

        Raises:
            InferenceTimeoutError: When inference exceeds timeout
        """
        try:
            result = await asyncio.wait_for(
                self._run_inference(image, language, options),
                timeout=timeout_seconds
            )
            return result

        except asyncio.TimeoutError:
            self.logger.error(
                "deepseek_inference_timeout",
                document_id=document_id,
                timeout_seconds=timeout_seconds
            )
            # Cleanup GPU resources after timeout
            await self._cleanup_gpu_resources()
            raise InferenceTimeoutError(
                backend="deepseek",
                timeout_seconds=timeout_seconds,
                document_id=document_id
            )

    async def _ensure_gpu_allocated(self) -> None:
        """Ensure GPU resources are allocated for DeepSeek."""
        allocation = self.gpu_manager.allocate_for_backend("deepseek")

        if not allocation["success"]:
            raise AgentResourceError(
                f"Failed to allocate GPU for DeepSeek: {allocation.get('reason')}"
            )

        if allocation.get("mode") == "cpu":
            self.logger.warning(
                "deepseek_fallback_cpu",
                reason="GPU not available, falling back to CPU (slow)",
            )

    async def _load_model(self) -> None:
        """Load DeepSeek Janus-Pro model and processor with lock and timeout.

        Implements deadlock prevention:
        1. Timeout on lock acquisition to prevent infinite waiting
        2. Tracks permanent failures to avoid repeated failed attempts
        3. Clear error messaging for debugging
        """
        # Quick check without lock (performance optimization)
        if self._model_loaded:
            return

        # Check if model loading has permanently failed (prevents repeated attempts)
        if DeepSeekAgent._model_load_failed:
            raise AgentResourceError(
                f"DeepSeek-Modell wurde bereits als fehlerhaft markiert: {DeepSeekAgent._model_load_error}. "
                "Neustart des Services erforderlich."
            )

        # Acquire lock with timeout to prevent deadlock
        try:
            await asyncio.wait_for(
                self._model_lock.acquire(),
                timeout=self.LOCK_ACQUISITION_TIMEOUT
            )
        except asyncio.TimeoutError:
            self.logger.error(
                "deepseek_model_lock_timeout",
                timeout_seconds=self.LOCK_ACQUISITION_TIMEOUT,
                message="Lock-Akquisition Timeout - moeglicherweise haengt ein anderer Ladevorgang"
            )
            raise AgentResourceError(
                f"Model-Lock Timeout nach {self.LOCK_ACQUISITION_TIMEOUT / 60:.0f} Minuten. "
                "Ein anderer Ladevorgang haengt moeglicherweise."
            )

        try:
            # Double-check after acquiring lock (another request may have loaded it)
            if self._model_loaded:
                self.logger.debug("deepseek_model_already_loaded_by_other_request")
                return

            # Also check for failure after lock (another request may have failed)
            if DeepSeekAgent._model_load_failed:
                raise AgentResourceError(
                    f"DeepSeek-Modell wurde bereits als fehlerhaft markiert: {DeepSeekAgent._model_load_error}"
                )

            self.logger.info("deepseek_loading_model", model_name=self.MODEL_NAME)

            try:
                # Wrap actual loading with timeout
                await asyncio.wait_for(
                    self._do_load_model(),
                    timeout=self.MODEL_LOADING_TIMEOUT
                )
                self._model_loaded = True
            except asyncio.TimeoutError:
                # Mark as permanently failed to prevent infinite retry loops
                DeepSeekAgent._model_load_failed = True
                DeepSeekAgent._model_load_error = f"Timeout nach {self.MODEL_LOADING_TIMEOUT / 60:.0f} Minuten"
                self.logger.error(
                    "deepseek_model_load_timeout",
                    timeout_seconds=self.MODEL_LOADING_TIMEOUT,
                    permanent_failure=True
                )
                raise AgentResourceError(
                    f"Model-Loading Timeout nach {self.MODEL_LOADING_TIMEOUT / 60:.0f} Minuten. "
                    "Ueberpruefen Sie die Netzwerkverbindung und den verfuegbaren Speicher."
                )
            except Exception as e:
                # Mark as permanently failed to prevent infinite retry loops
                DeepSeekAgent._model_load_failed = True
                DeepSeekAgent._model_load_error = str(e)
                self.logger.error(
                    "deepseek_model_load_failed",
                    error=str(e),
                    exc_info=True,
                    permanent_failure=True
                )
                raise AgentResourceError(f"Fehler beim Laden des DeepSeek-Modells: {e}")
        finally:
            # Always release the lock, even on failure
            self._model_lock.release()

    async def _do_load_model(self) -> None:
        """Actual model loading logic (called within lock and timeout)."""
        try:
            # Check if we need to use a custom Janus implementation
            # Note: DeepSeek Janus uses custom multimodal architecture
            try:
                from janus.models import MultiModalityCausalLM, VLChatProcessor
                use_janus_implementation = True
            except ImportError:
                self.logger.warning("Janus library not found, using standard transformers")
                use_janus_implementation = False

            device = "cuda" if torch.cuda.is_available() else "cpu"

            # Determine quantization strategy based on platform
            # Priority on Windows: GPTQ > AWQ > bfloat16
            # Priority on Linux: BitsAndBytes > GPTQ > AWQ > bfloat16
            quantization_method = None

            if self.ENABLE_QUANTIZATION and device == "cuda":
                # BitsAndBytes ist inkompatibel mit Janus Vision Encoder (dtype mismatch)
                # Verwende float16 direkt für beste Kompatibilität
                if GPTQ_AVAILABLE:
                    quantization_method = "gptq"
                elif AWQ_AVAILABLE:
                    quantization_method = "awq"
                else:
                    # Fall back to bfloat16 - Janus ist dafür konzipiert
                    quantization_method = "bfloat16"
                    self.logger.warning(
                        "deepseek_no_quantization_available",
                        platform="Windows" if IS_WINDOWS else "Linux",
                        bitsandbytes=BITSANDBYTES_AVAILABLE,
                        gptq=GPTQ_AVAILABLE,
                        awq=AWQ_AVAILABLE,
                        fallback="bfloat16 mit Speicheroptimierung"
                    )

            self.logger.info(
                "deepseek_quantization_strategy",
                method=quantization_method,
                platform="Windows" if IS_WINDOWS else "Linux"
            )

            if use_janus_implementation:
                # Use Janus-specific implementation as per initial-prompt.md
                # SECURITY WARNING: trust_remote_code=True is REQUIRED for DeepSeek-Janus models
                # This allows execution of model-specific code from HuggingFace Hub.
                # Risk: Malicious model code could execute arbitrary commands.
                # Mitigation: Only use official deepseek-ai/Janus-Pro-7B model.
                # Alternative: Use local model copy after manual code review.
                # See: https://huggingface.co/docs/transformers/main_classes/model#trust-remote-code
                if quantization_method == "bitsandbytes":
                    # 4-bit quantization for RTX 4080 16GB (Linux)
                    # Use float16 instead of bfloat16 to avoid dtype mismatch with Janus model
                    quant_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4"
                    )
                    self.model = MultiModalityCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        quantization_config=quant_config,
                        torch_dtype=torch.float16,  # Explizit float16 um dtype-Mismatch zu vermeiden
                        trust_remote_code=True,
                        device_map="auto"
                    )
                    # Konvertiere Vision-Encoder und andere nicht-quantisierte Module zu float16
                    # BitsAndBytes quantisiert nur Linear Layers, Vision Encoder bleibt in bfloat16
                    for name, module in self.model.named_modules():
                        if hasattr(module, 'weight') and module.weight is not None:
                            if module.weight.dtype == torch.bfloat16:
                                module.to(torch.float16)
                        if hasattr(module, 'bias') and module.bias is not None:
                            if module.bias.dtype == torch.bfloat16:
                                module.bias.data = module.bias.data.to(torch.float16)
                elif quantization_method == "gptq":
                    # GPTQ quantization (Windows compatible)
                    self.logger.info("deepseek_loading_gptq", model=self.MODEL_NAME)
                    # Note: Requires GPTQ-quantized model variant
                    gptq_model_name = f"{self.MODEL_NAME}-GPTQ"
                    try:
                        self.model = AutoGPTQForCausalLM.from_quantized(
                            gptq_model_name,
                            device_map="auto",
                            trust_remote_code=True,
                            use_safetensors=True
                        )
                    except Exception as gptq_err:
                        self.logger.warning("deepseek_gptq_failed", error=str(gptq_err))
                        # Fall back to bfloat16
                        quantization_method = "bfloat16"
                        self.model = MultiModalityCausalLM.from_pretrained(
                            self.MODEL_NAME,
                            torch_dtype=torch.bfloat16,
                            trust_remote_code=True,
                            device_map="auto",
                            low_cpu_mem_usage=True
                        )
                elif quantization_method == "awq":
                    # AWQ quantization (Windows compatible)
                    self.logger.info("deepseek_loading_awq", model=self.MODEL_NAME)
                    awq_model_name = f"{self.MODEL_NAME}-AWQ"
                    try:
                        self.model = AutoAWQForCausalLM.from_quantized(
                            awq_model_name,
                            device_map="auto",
                            trust_remote_code=True
                        )
                    except Exception as awq_err:
                        self.logger.warning("deepseek_awq_failed", error=str(awq_err))
                        quantization_method = "bfloat16"
                        self.model = MultiModalityCausalLM.from_pretrained(
                            self.MODEL_NAME,
                            torch_dtype=torch.bfloat16,
                            trust_remote_code=True,
                            device_map="auto",
                            low_cpu_mem_usage=True
                        )
                else:
                    # bfloat16 - native Janus-Konfiguration
                    # Note: Flash Attention wird von Janus nicht unterstützt
                    self.model = MultiModalityCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
                        attn_implementation="eager",  # Janus unterstützt kein Flash Attention 2.0
                        trust_remote_code=True,
                        device_map="auto" if device == "cuda" else None,
                        low_cpu_mem_usage=True
                    )

                self.processor = VLChatProcessor.from_pretrained(self.MODEL_NAME)
                self.tokenizer = self.processor.tokenizer
            else:
                # Fallback to standard transformers implementation
                from transformers import AutoModelForCausalLM, AutoProcessor

                if quantization_method == "bitsandbytes":
                    quant_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,  # float16 statt bfloat16 für Janus-Kompatibilität
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4"
                    )
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        quantization_config=quant_config,
                        torch_dtype=torch.float16,  # Explizit float16
                        trust_remote_code=True,
                        device_map="auto"
                    )
                elif quantization_method == "gptq":
                    gptq_model_name = f"{self.MODEL_NAME}-GPTQ"
                    try:
                        self.model = AutoGPTQForCausalLM.from_quantized(
                            gptq_model_name,
                            device_map="auto",
                            trust_remote_code=True,
                            use_safetensors=True
                        )
                    except Exception as e:
                        self.logger.debug(
                            "gptq_load_failed_fallback_bfloat16",
                            error_type=type(e).__name__,
                        )
                        quantization_method = "bfloat16"
                        self.model = AutoModelForCausalLM.from_pretrained(
                            self.MODEL_NAME,
                            torch_dtype=torch.bfloat16,
                            trust_remote_code=True,
                            device_map="auto",
                            low_cpu_mem_usage=True
                        )
                elif quantization_method == "awq":
                    awq_model_name = f"{self.MODEL_NAME}-AWQ"
                    try:
                        self.model = AutoAWQForCausalLM.from_quantized(
                            awq_model_name,
                            device_map="auto",
                            trust_remote_code=True
                        )
                    except Exception as e:
                        self.logger.debug(
                            "awq_load_failed_fallback_bfloat16",
                            error_type=type(e).__name__,
                        )
                        quantization_method = "bfloat16"
                        self.model = AutoModelForCausalLM.from_pretrained(
                            self.MODEL_NAME,
                            torch_dtype=torch.bfloat16,
                            trust_remote_code=True,
                            device_map="auto",
                            low_cpu_mem_usage=True
                        )
                else:
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
                        trust_remote_code=True,
                        device_map="auto" if device == "cuda" else None,
                        low_cpu_mem_usage=True
                    )

                self.processor = AutoProcessor.from_pretrained(
                    self.MODEL_NAME, trust_remote_code=True
                )
                self.tokenizer = None  # Will use processor's tokenizer

            # Track quantization status
            self._quantization_active = quantization_method in ["bitsandbytes", "gptq", "awq"]
            self._quantization_method = quantization_method

            if quantization_method == "bfloat16" and device == "cuda":
                # Clear cache before moving to GPU for bfloat16
                torch.cuda.empty_cache()

            self.model.eval()  # Inference mode

            # Warm-up inference (compile CUDA kernels)
            if device == "cuda":
                dummy_image = Image.new("RGB", (224, 224), color="white")
                _ = await self._run_inference(
                    dummy_image, language="de", options={"warmup": True}
                )
                torch.cuda.empty_cache()

            # Note: _model_loaded is set in the wrapper (_load_model) after successful completion
            quantization_status = f"{quantization_method} quantized" if self._quantization_active else f"{quantization_method} (full precision)"
            self.logger.info(
                "deepseek_model_loaded",
                device=device,
                quantization=quantization_status,
                method=quantization_method,
                platform="Windows" if IS_WINDOWS else "Linux"
            )

        except Exception as e:
            # Re-raise to be handled by the wrapper with timeout context
            raise

    async def _load_image(self, image_path: Path) -> Image.Image:
        """Load, validate and resize image for optimal Janus processing.

        Janus arbeitet am besten mit Bildern bis 1536x1536 Pixel.
        Groessere Bilder werden proportional skaliert.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Maximale Bildgroesse fuer Janus (verhindert OOM und lange Inference)
        MAX_SIZE = 1536

        try:
            # Use context manager to ensure file handle is closed
            with Image.open(image_path) as img:
                # Convert and create in-memory copy (detaches from file handle)
                image = img.convert("RGB").copy()

            original_size = image.size

            # Skaliere grosse Bilder proportional herunter
            if image.width > MAX_SIZE or image.height > MAX_SIZE:
                ratio = min(MAX_SIZE / image.width, MAX_SIZE / image.height)
                new_width = int(image.width * ratio)
                new_height = int(image.height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                self.logger.info(
                    "image_resized_for_janus",
                    path=str(image_path),
                    original_size=original_size,
                    new_size=image.size,
                    scale_ratio=round(ratio, 3)
                )

            self.logger.debug(
                "image_loaded",
                path=str(image_path),
                size=image.size,
                mode=image.mode,
            )
            return image
        except Exception as e:
            raise ValueError(f"Failed to load image: {e}")

    def _calculate_token_confidence(
        self,
        scores: Tuple[torch.Tensor, ...],
        generated_ids: torch.Tensor,
        skip_special_tokens: bool = True
    ) -> Dict[str, Any]:
        """
        Berechne Token-Level Confidence aus Model Output Logits.

        OPTIMIERT: Vektorisierte Berechnung statt Loop für ~10x Speedup.

        Args:
            scores: Tuple von Logit-Tensoren für jeden generierten Token
            generated_ids: Die generierten Token-IDs
            skip_special_tokens: Spezielle Tokens überspringen

        Returns:
            Dictionary mit Confidence-Metriken:
            - mean_confidence: Durchschnittliche Confidence über alle Tokens
            - min_confidence: Minimale Token-Confidence
            - token_confidences: Liste der Confidences pro Token
            - low_confidence_positions: Positionen mit Confidence < 0.7
        """
        if not scores or len(scores) == 0:
            return {
                "mean_confidence": 0.0,
                "min_confidence": 0.0,
                "token_confidences": [],
                "low_confidence_positions": [],
                "confidence_method": "no_scores"
            }

        # Tokenizer für Special Token Detection
        tokenizer = self.tokenizer if self.tokenizer else getattr(self.processor, 'tokenizer', None)
        special_token_ids = set()
        if tokenizer:
            special_token_ids = set(tokenizer.all_special_ids) if hasattr(tokenizer, 'all_special_ids') else set()

        try:
            num_scores = len(scores)
            input_length = len(generated_ids[0]) - num_scores

            # Validiere Grenzen
            if input_length < 0 or input_length + num_scores > len(generated_ids[0]):
                self.logger.warning(
                    "token_position_bounds_invalid",
                    input_length=input_length,
                    num_scores=num_scores,
                    generated_len=len(generated_ids[0])
                )
                return {
                    "mean_confidence": 0.85,
                    "min_confidence": 0.70,
                    "token_confidences": [],
                    "low_confidence_positions": [],
                    "confidence_method": "bounds_error"
                }

            # ===== VEKTORISIERTE BERECHNUNG =====
            # Stack alle Logits zu einem Tensor (num_tokens, batch, vocab) oder (num_tokens, vocab)
            stacked_logits = torch.stack([
                s.squeeze(0) if s.dim() == 3 else s for s in scores
            ])  # Shape: (num_tokens, batch?, vocab)

            # Falls batch-Dimension vorhanden, entfernen (wir verarbeiten nur batch=0)
            if stacked_logits.dim() == 3:
                stacked_logits = stacked_logits[:, 0, :]  # Shape: (num_tokens, vocab)

            # Batch-Softmax über alle Tokens gleichzeitig
            all_probs = F.softmax(stacked_logits, dim=-1)  # Shape: (num_tokens, vocab)

            # Extrahiere generierte Token-IDs
            gen_token_ids = generated_ids[0, input_length:input_length + num_scores]

            # Vektorisiertes Lookup: Confidence für alle Tokens auf einmal
            token_indices = torch.arange(num_scores, device=all_probs.device)
            all_confidences = all_probs[token_indices, gen_token_ids].cpu().numpy()

            # Special Token Filtering (falls nötig)
            if skip_special_tokens and special_token_ids:
                gen_ids_list = gen_token_ids.cpu().tolist()
                mask = np.array([tid not in special_token_ids for tid in gen_ids_list])
                filtered_confidences = all_confidences[mask]
                filtered_positions = np.where(mask)[0]
                filtered_token_ids = np.array(gen_ids_list)[mask]
            else:
                filtered_confidences = all_confidences
                filtered_positions = np.arange(num_scores)
                filtered_token_ids = gen_token_ids.cpu().numpy()

            # Low confidence Positionen (vektorisiert)
            low_conf_mask = filtered_confidences < 0.7
            low_confidence_positions = [
                {
                    "position": int(filtered_positions[i]),
                    "confidence": float(filtered_confidences[i]),
                    "token_id": int(filtered_token_ids[i])
                }
                for i in np.where(low_conf_mask)[0][:20]  # Limit auf 20
            ]

            # Aggregiere Confidences
            if len(filtered_confidences) > 0:
                mean_conf = float(np.mean(filtered_confidences))
                min_conf = float(np.min(filtered_confidences))
                weighted_conf = 0.7 * mean_conf + 0.3 * min_conf
            else:
                mean_conf = 0.0
                min_conf = 0.0
                weighted_conf = 0.0

            return {
                "mean_confidence": mean_conf,
                "min_confidence": min_conf,
                "weighted_confidence": weighted_conf,
                "token_confidences": filtered_confidences[:100].tolist(),  # Limit für Speicher
                "low_confidence_positions": low_confidence_positions,
                "total_tokens": len(filtered_confidences),
                "confidence_method": "token_logits_vectorized"
            }

        except Exception as e:
            self.logger.warning(
                "confidence_calculation_error",
                error=str(e),
                fallback="heuristic"
            )
            return {
                "mean_confidence": 0.85,  # Konservativer Fallback
                "min_confidence": 0.70,
                "token_confidences": [],
                "low_confidence_positions": [],
                "confidence_method": "fallback_error"
            }

    async def _run_inference(
        self, image: Image.Image, language: str, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run DeepSeek Janus-Pro OCR inference with multimodal conversation format."""
        start_time = time.perf_counter()

        # Check for warmup pass
        if options.get("warmup", False):
            # Simple warmup without actual OCR
            return {"text": "", "confidence": 0.0, "model": self.MODEL_NAME}

        # Prepare prompt for German OCR
        prompt = self._build_prompt(language, options)

        # Check if we have Janus-specific processor
        if hasattr(self, 'tokenizer') and self.tokenizer is not None:
            # Use Janus conversation format as per initial-prompt.md
            conversation = [
                {
                    "role": "User",
                    "content": f"<image_placeholder>\n{prompt}",
                    "images": [image]
                },
                {"role": "Assistant", "content": ""}
            ]

            # Process with Janus VLChatProcessor
            inputs = self.processor(
                conversations=conversation,
                images=[image],
                force_batchify=True
            )

            # Move to device
            if hasattr(inputs, 'to'):
                inputs = inputs.to(self.model.device)
            else:
                # Handle dict of tensors
                inputs = {k: v.to(self.model.device) if torch.is_tensor(v) else v
                         for k, v in inputs.items()}

            # Prepare inputs for multimodal model
            confidence_data = None

            if hasattr(self.model, 'prepare_inputs_embeds'):
                # Konvertiere BatchedVLChatProcessorOutput zu Dict falls nötig
                if hasattr(inputs, '__dict__') and not isinstance(inputs, dict):
                    inputs_dict = {k: v for k, v in inputs.__dict__.items() if v is not None}
                else:
                    inputs_dict = inputs if isinstance(inputs, dict) else dict(inputs)

                inputs_embeds = self.model.prepare_inputs_embeds(**inputs_dict)

                # Hole attention_mask sicher
                attention_mask = inputs_dict.get('attention_mask') if isinstance(inputs_dict, dict) else getattr(inputs, 'attention_mask', None)

                # Generate with language model component - mit output_scores für Confidence
                # OPTIMIERT: max_new_tokens=512 (OCR braucht nicht mehr), use_cache=True
                # VRAM Monitoring: Check every 100 tokens for memory pressure
                vram_monitor = VRAMMonitorLogitsProcessor(
                    check_interval=100,
                    warning_threshold_gb=13.6,  # 85% of 16GB
                    critical_threshold_gb=15.0,  # ~94% - near OOM
                    logger=self.logger
                )
                with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.bfloat16):
                    outputs = self.model.language_model.generate(
                        inputs_embeds=inputs_embeds,
                        attention_mask=attention_mask,
                        max_new_tokens=options.get("max_tokens", 512),
                        do_sample=False,
                        num_beams=1,
                        use_cache=True,
                        pad_token_id=self.tokenizer.eos_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                        output_scores=True,
                        return_dict_in_generate=True,
                        logits_processor=[vram_monitor]
                    )

                # Extrahiere Sequenzen und Scores
                generated_ids = outputs.sequences if hasattr(outputs, 'sequences') else outputs
                scores = outputs.scores if hasattr(outputs, 'scores') else None

                # Berechne Token-Level Confidence
                if scores:
                    confidence_data = self._calculate_token_confidence(scores, generated_ids)

                # Decode with tokenizer
                if hasattr(outputs, 'sequences'):
                    generated_text = self.tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)
                else:
                    generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            else:
                # Fallback to standard generation - OPTIMIERT
                # VRAM Monitoring: Check every 100 tokens for memory pressure
                vram_monitor = VRAMMonitorLogitsProcessor(
                    check_interval=100,
                    warning_threshold_gb=13.6,  # 85% of 16GB
                    critical_threshold_gb=15.0,  # ~94% - near OOM
                    logger=self.logger
                )
                with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.bfloat16):
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=options.get("max_tokens", 512),
                        do_sample=False,
                        num_beams=1,
                        use_cache=True,
                        pad_token_id=self.tokenizer.eos_token_id if self.tokenizer else self.processor.tokenizer.eos_token_id,
                        output_scores=True,
                        return_dict_in_generate=True,
                        logits_processor=[vram_monitor]
                    )

                # Extrahiere Sequenzen und Scores
                generated_ids = outputs.sequences if hasattr(outputs, 'sequences') else outputs
                scores = outputs.scores if hasattr(outputs, 'scores') else None

                # Berechne Token-Level Confidence
                if scores:
                    confidence_data = self._calculate_token_confidence(scores, generated_ids)

                if hasattr(outputs, 'sequences'):
                    if self.tokenizer:
                        generated_text = self.tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)
                    else:
                        generated_text = self.processor.batch_decode(outputs.sequences, skip_special_tokens=True)[0]
                else:
                    if self.tokenizer:
                        generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                    else:
                        generated_text = self.processor.batch_decode(outputs, skip_special_tokens=True)[0]
        else:
            # Standard transformers processing
            confidence_data = None

            inputs = self.processor(
                text=prompt,
                images=image,
                return_tensors="pt"
            )

            # Move to device
            inputs = {k: v.to(self.model.device) if torch.is_tensor(v) else v
                     for k, v in inputs.items()}

            # Run inference - OPTIMIERT fuer schnelle Generation
            # VRAM Monitoring: Check every 100 tokens for memory pressure
            vram_monitor = VRAMMonitorLogitsProcessor(
                check_interval=100,
                warning_threshold_gb=13.6,  # 85% of 16GB
                critical_threshold_gb=15.0,  # ~94% - near OOM
                logger=self.logger
            )
            with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.bfloat16):
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=options.get("max_tokens", 512),
                    do_sample=False,
                    num_beams=1,
                    use_cache=True,
                    pad_token_id=self.processor.tokenizer.eos_token_id,
                    output_scores=True,
                    return_dict_in_generate=True,
                    logits_processor=[vram_monitor]
                )

            # Extrahiere Sequenzen und Scores
            generated_ids = outputs.sequences if hasattr(outputs, 'sequences') else outputs
            scores = outputs.scores if hasattr(outputs, 'scores') else None

            # Berechne Token-Level Confidence
            if scores:
                confidence_data = self._calculate_token_confidence(scores, generated_ids)

            # Decode output
            if hasattr(outputs, 'sequences'):
                generated_text = self.processor.batch_decode(
                    outputs.sequences, skip_special_tokens=True
                )[0]
            else:
                generated_text = self.processor.batch_decode(
                    outputs, skip_special_tokens=True
                )[0]

        # Calculate processing time
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Extract just the OCR text (remove prompt if included)
        if prompt in generated_text:
            generated_text = generated_text.replace(prompt, "").strip()

        # Berechne finale Confidence aus Token-Level Daten
        # Prüfe auf beide möglichen Methoden-Namen (legacy und aktuell)
        if confidence_data and confidence_data.get("confidence_method") in ("token_logits", "token_logits_vectorized"):
            # Verwende gewichtete Confidence (70% mean + 30% min)
            confidence = confidence_data.get("weighted_confidence", 0.0)

            # Zusätzliche Heuristik: Falls Text sehr kurz, reduziere Confidence
            if len(generated_text) < 10:
                confidence *= 0.8

            # Sicherstelle dass Confidence im gültigen Bereich
            confidence = max(0.0, min(1.0, confidence))
        else:
            # Fallback: Heuristische Confidence basierend auf Textqualität
            if not generated_text:
                confidence = 0.0
            elif len(generated_text) < 10:
                confidence = 0.5
            elif len(generated_text) < 50:
                confidence = 0.7
            else:
                # Längerer Text = wahrscheinlich erfolgreich
                confidence = 0.85

        # Baue erweiterte Response mit Confidence-Details
        result = {
            "text": generated_text,
            "confidence": confidence,
            "model": self.MODEL_NAME,
            "processing_time_ms": processing_time_ms,
            "backend": "deepseek-janus-pro"
        }

        # Füge detaillierte Confidence-Metriken hinzu wenn verfügbar
        if confidence_data:
            result["confidence_details"] = {
                "method": confidence_data.get("confidence_method", "unknown"),
                "mean_confidence": confidence_data.get("mean_confidence", 0.0),
                "min_confidence": confidence_data.get("min_confidence", 0.0),
                "total_tokens": confidence_data.get("total_tokens", 0),
                "low_confidence_count": len(confidence_data.get("low_confidence_positions", []))
            }

        return result

    def _build_prompt(self, language: str, options: Dict[str, Any]) -> str:
        """Build simple OCR prompt for DeepSeek-Janus.

        Janus arbeitet am besten mit kurzen, direkten Prompts.
        """
        if language == "de":
            return "Lies den gesamten Text aus diesem Dokument vor. Gib nur den Text zurueck, keine Erklaerungen."
        else:
            return "Read all the text from this document. Return only the text, no explanations."

    async def _postprocess_result(
        self, ocr_result: Dict[str, Any], options: Dict[str, Any]
    ) -> OCRResult:
        """Post-process OCR results with German text optimization.

        Returns:
            Standardisiertes OCRResult-Objekt fuer konsistente API.
        """
        text = ocr_result["text"]

        # Basic text cleaning
        text = text.strip()

        # OPTIMIERUNG: Deutsche Textnachbearbeitung mit Unified Postprocessor
        german_corrections = []
        german_validation_score = 0.0
        has_umlauts = False
        language = options.get("language", "de")

        if language == "de" and text:
            try:
                from app.services.german_text_postprocessor import get_german_postprocessor
                postprocessor = get_german_postprocessor()
                german_result = postprocessor.postprocess(text)
                text = german_result["text"]
                german_corrections = german_result.get("corrections", [])

                # Extrahiere deutsche Qualitaetsmetriken
                stats = german_result.get("stats", {})
                german_validation_score = stats.get("quality_score", 0.0)
                has_umlauts = any(c in text for c in "äöüÄÖÜß")

                if german_corrections:
                    self.logger.debug(
                        "deepseek_german_postprocessing",
                        corrections_count=len(german_corrections),
                        umlaut_fixes=stats.get("umlaut_corrections", 0),
                        eszett_fixes=stats.get("eszett_corrections", 0)
                    )
            except ImportError:
                self.logger.debug("german_postprocessor_not_available")
                has_umlauts = any(c in text for c in "äöüÄÖÜß")
            except Exception as e:
                # Log error and track metric for postprocessor failure
                self.logger.warning(
                    "deepseek_german_postprocessing_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                # Track postprocessor error in metrics
                from app.ml.metrics import get_ml_metrics
                metrics = get_ml_metrics()
                metrics.record_ocr_postprocessor_error(
                    backend="deepseek",
                    postprocessor="german_text"
                )
                # Fallback: Keep original text, check for German characters
                has_umlauts = any(c in text for c in "äöüÄÖÜß")

        # Extract structured data (IBAN, VAT, dates, phone, email, NER)
        entities = []
        if options.get("extract_entities"):
            entities = self._extract_entities(text)

        # Detect layout structure (headers, tables, lists, signatures)
        layout = {}
        if options.get("detect_layout"):
            layout = self._detect_layout(text)

        # Record OCR metrics
        processing_time_ms = ocr_result.get("processing_time_ms", 0)
        confidence = ocr_result["confidence"]

        from app.ml.metrics import get_ml_metrics
        metrics = get_ml_metrics()
        if processing_time_ms > 0:
            metrics.record_ocr_inference_time("deepseek", processing_time_ms / 1000.0)
        metrics.record_ocr_confidence_score("deepseek", confidence)

        # Erstelle standardisiertes OCRResult
        result = self.create_success_result(
            text=text,
            confidence=confidence,
            processing_time_ms=processing_time_ms,
            language=language,
            layout=layout if layout else None,
            has_umlauts=has_umlauts,
            german_validation_score=german_validation_score,
        )

        return result

    def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract business entities from German text using regex patterns and spaCy NER."""
        import re
        from typing import Match

        entities: List[Dict[str, Any]] = []

        if not text or len(text.strip()) < 5:
            return entities

        # Import GermanValidator for pattern matching and validation
        try:
            from app.german_validator import GermanValidator
            validator = GermanValidator()
            has_validator = True
        except ImportError:
            has_validator = False
            self.logger.debug("german_validator_not_available_for_entity_extraction")

        # 1. IBAN extraction (German format: DE + 20 digits)
        iban_pattern = r'\b([A-Z]{2}\s?\d{2}[\s]?(?:\d{4}[\s]?){4}\d{2})\b'
        for match in re.finditer(iban_pattern, text):
            iban_value = match.group(1).replace(' ', '').replace('\t', '')
            is_valid = False
            if has_validator:
                is_valid = validator.validate_iban(iban_value)

            entities.append({
                "type": "IBAN",
                "value": iban_value,
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.95 if is_valid else 0.7,
                "validated": is_valid,
                "source": "regex"
            })

        # 2. VAT ID extraction (German: DE + 9 digits)
        vat_pattern = r'\b(DE\s?\d{3}\s?\d{3}\s?\d{3})\b'
        for match in re.finditer(vat_pattern, text, re.IGNORECASE):
            vat_value = match.group(1).replace(' ', '').upper()
            is_valid = False
            if has_validator:
                is_valid = validator.validate_vat_id(vat_value)

            entities.append({
                "type": "VAT_ID",
                "value": vat_value,
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.95 if is_valid else 0.7,
                "validated": is_valid,
                "source": "regex"
            })

        # 3. Date extraction (German formats)
        if has_validator:
            dates = validator.validate_date_format(text)
            for date_str in dates:
                # Find position in text
                date_match = re.search(re.escape(date_str), text)
                entities.append({
                    "type": "DATE",
                    "value": date_str,
                    "start": date_match.start() if date_match else -1,
                    "end": date_match.end() if date_match else -1,
                    "confidence": 0.9,
                    "source": "german_validator"
                })
        else:
            # Fallback date pattern
            date_pattern = r'\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b'
            for match in re.finditer(date_pattern, text):
                entities.append({
                    "type": "DATE",
                    "value": match.group(1),
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.85,
                    "source": "regex"
                })

        # 4. Currency amounts (German format: 1.234,56 EUR)
        if has_validator:
            amounts = validator.validate_currency_format(text)
            for amount in amounts:
                amount_match = re.search(re.escape(amount), text)
                entities.append({
                    "type": "CURRENCY",
                    "value": amount,
                    "start": amount_match.start() if amount_match else -1,
                    "end": amount_match.end() if amount_match else -1,
                    "confidence": 0.9,
                    "source": "german_validator"
                })
        else:
            # Fallback currency pattern
            currency_pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(€|EUR|Euro)'
            for match in re.finditer(currency_pattern, text, re.IGNORECASE):
                entities.append({
                    "type": "CURRENCY",
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.85,
                    "source": "regex"
                })

        # 5. Business terms extraction
        if has_validator:
            terms = validator.extract_business_terms(text)
            for abbr, info in terms.items():
                # Find all occurrences
                for match in re.finditer(r'\b' + re.escape(abbr) + r'\b', text):
                    entities.append({
                        "type": "BUSINESS_TERM",
                        "value": abbr,
                        "full_name": info["full_name"],
                        "start": match.start(),
                        "end": match.end(),
                        "confidence": 0.95,
                        "source": "german_validator"
                    })

        # 6. Phone numbers (German formats)
        phone_pattern = r'\b(\+49[\s]?\d{2,4}[\s]?\d{3,8}[\s]?\d{0,6}|\d{3,5}[\s/-]?\d{3,8})\b'
        for match in re.finditer(phone_pattern, text):
            phone_value = match.group(1)
            # Only add if it looks like a phone number (has enough digits)
            if len(re.sub(r'\D', '', phone_value)) >= 6:
                entities.append({
                    "type": "PHONE",
                    "value": phone_value,
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.75,
                    "source": "regex"
                })

        # 7. Email addresses
        email_pattern = r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'
        for match in re.finditer(email_pattern, text):
            entities.append({
                "type": "EMAIL",
                "value": match.group(1),
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.95,
                "source": "regex"
            })

        # 8. Tax numbers (Steuernummer: varies by state, typically 10-13 digits with slashes)
        tax_pattern = r'\b(\d{2,3}/\d{3}/\d{4,5})\b'
        for match in re.finditer(tax_pattern, text):
            entities.append({
                "type": "TAX_NUMBER",
                "value": match.group(1),
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.85,
                "source": "regex"
            })

        # 9. spaCy NER for PERSON, ORGANIZATION, LOCATION (using pre-loaded model)
        try:
            # Use pre-loaded model from class-level cache (initialized in __init__)
            nlp = DeepSeekAgent._spacy_nlp

            if nlp:
                doc = nlp(text)
                spacy_entity_map = {
                    "PER": "PERSON",
                    "ORG": "ORGANIZATION",
                    "LOC": "LOCATION",
                    "GPE": "LOCATION",
                    "MISC": "MISCELLANEOUS",
                }

                for ent in doc.ents:
                    mapped_type = spacy_entity_map.get(ent.label_)
                    if mapped_type:
                        # Avoid duplicates from regex patterns
                        is_duplicate = any(
                            e["value"].lower() == ent.text.lower() and e["type"] == mapped_type
                            for e in entities
                        )
                        if not is_duplicate:
                            entities.append({
                                "type": mapped_type,
                                "value": ent.text,
                                "start": ent.start_char,
                                "end": ent.end_char,
                                "confidence": 0.85,
                                "source": "spacy_ner",
                                "spacy_label": ent.label_
                            })

        except Exception as e:
            # Pre-loaded model should not fail, but log if it does
            self.logger.warning("spacy_ner_error", error=str(e))

        # Sort entities by position in text
        entities.sort(key=lambda x: x.get("start", 0))

        return entities

    def _detect_layout(self, text: str) -> Dict[str, Any]:
        """Detect document layout structure from OCR text."""
        import re

        layout: Dict[str, Any] = {
            "type": "unknown",
            "sections": [],
            "has_tables": False,
            "has_lists": False,
            "has_signature": False,
            "has_header": False,
            "has_footer": False,
            "line_count": 0,
            "word_count": 0,
            "confidence": 0.0
        }

        if not text or len(text.strip()) < 10:
            return layout

        lines = text.split('\n')
        layout["line_count"] = len(lines)
        layout["word_count"] = len(text.split())

        # 1. Detect document type based on keywords
        text_lower = text.lower()

        # Invoice detection
        invoice_keywords = [
            'rechnung', 'rechnungsnummer', 'rechnungsdatum', 'invoice',
            'nettobetrag', 'bruttobetrag', 'mwst', 'mehrwertsteuer',
            'zahlungsziel', 'bankverbindung', 'iban', 'ust-idnr',
            'leistungszeitraum', 'rechnungsempfänger', 'rechnungsbetrag'
        ]
        invoice_score = sum(1 for kw in invoice_keywords if kw in text_lower)

        # Letter detection
        letter_keywords = [
            'sehr geehrte', 'sehr geehrter', 'mit freundlichen grüßen',
            'hochachtungsvoll', 'betreff:', 'betrifft:', 'anlage:',
            'liebe', 'lieber', 'herzliche grüße', 'beste grüße'
        ]
        letter_score = sum(1 for kw in letter_keywords if kw in text_lower)

        # Contract detection
        contract_keywords = [
            'vertrag', 'vereinbarung', 'paragraph', '§', 'haftung',
            'kündigung', 'kündigungsfrist', 'laufzeit', 'vertragspartner',
            'gerichtsstand', 'salvatorische klausel', 'unterschrift'
        ]
        contract_score = sum(1 for kw in contract_keywords if kw in text_lower)

        # Report/documentation detection
        report_keywords = [
            'bericht', 'zusammenfassung', 'analyse', 'dokumentation',
            'inhaltsverzeichnis', 'kapitel', 'abschnitt', 'fazit',
            'einleitung', 'schlussfolgerung'
        ]
        report_score = sum(1 for kw in report_keywords if kw in text_lower)

        # Determine document type
        scores = {
            "invoice": invoice_score,
            "letter": letter_score,
            "contract": contract_score,
            "report": report_score
        }
        max_score = max(scores.values())
        if max_score >= 3:
            layout["type"] = max(scores, key=scores.get)
            layout["confidence"] = min(0.95, 0.5 + (max_score * 0.1))
        elif max_score >= 1:
            layout["type"] = max(scores, key=scores.get)
            layout["confidence"] = 0.4 + (max_score * 0.1)
        else:
            layout["type"] = "general"
            layout["confidence"] = 0.3

        # 2. Detect tables (multiple indicators)
        tab_lines = sum(1 for line in lines if '\t' in line)
        pipe_lines = sum(1 for line in lines if '|' in line)
        aligned_number_pattern = r'\d+[\s\t]+\d+[\s\t]+\d+'
        aligned_numbers = len(re.findall(aligned_number_pattern, text))

        layout["has_tables"] = (tab_lines >= 3 or pipe_lines >= 2 or aligned_numbers >= 3)
        if layout["has_tables"]:
            layout["sections"].append({
                "type": "table",
                "indicator": "tab_aligned" if tab_lines >= 3 else "pipe_delimited" if pipe_lines >= 2 else "number_columns"
            })

        # 3. Detect lists
        list_patterns = [
            r'^\s*[-*•]\s+',      # Bullet points
            r'^\s*\d+\.\s+',       # Numbered lists (1. 2. 3.)
            r'^\s*\d+\)\s+',       # Numbered lists (1) 2) 3))
            r'^\s*[a-z]\)\s+',     # Letter lists (a) b) c))
            r'^\s*[IVX]+\.\s+',    # Roman numerals
        ]
        list_line_count = 0
        for line in lines:
            if any(re.match(pattern, line, re.IGNORECASE) for pattern in list_patterns):
                list_line_count += 1

        layout["has_lists"] = list_line_count >= 2
        if layout["has_lists"]:
            layout["sections"].append({
                "type": "list",
                "item_count": list_line_count
            })

        # 4. Detect signature block
        signature_keywords = [
            'mit freundlichen grüßen', 'hochachtungsvoll', 'mfg',
            'gez.', 'i.a.', 'i.v.', 'ppa.', 'unterschrift'
        ]
        has_signature = any(kw in text_lower for kw in signature_keywords)
        layout["has_signature"] = has_signature
        if has_signature:
            layout["sections"].append({"type": "signature_block"})

        # 5. Detect header (company info, date at top)
        first_lines = '\n'.join(lines[:5]).lower() if len(lines) >= 5 else text_lower
        header_indicators = ['gmbh', 'ag', 'kg', 'tel:', 'fax:', 'www.', 'email:', '@']
        layout["has_header"] = any(ind in first_lines for ind in header_indicators)
        if layout["has_header"]:
            layout["sections"].insert(0, {"type": "header"})

        # 6. Detect footer (page numbers, legal info at bottom)
        last_lines = '\n'.join(lines[-3:]).lower() if len(lines) >= 3 else text_lower
        footer_indicators = ['seite', 'page', 'amtsgericht', 'handelsregister', 'hrb', 'geschäftsführer']
        layout["has_footer"] = any(ind in last_lines for ind in footer_indicators)
        if layout["has_footer"]:
            layout["sections"].append({"type": "footer"})

        # Add main content section
        if layout["has_header"] or layout["has_footer"] or layout["has_signature"]:
            # Insert body section between header and other sections
            body_position = 1 if layout["has_header"] else 0
            layout["sections"].insert(body_position, {"type": "body"})

        return layout

    async def _handle_gpu_oom(self) -> None:
        """Handle GPU out-of-memory error."""
        self.logger.warning("deepseek_gpu_oom_recovery", action="clearing_cache")

        # Clear CUDA cache - synchronize first to ensure all operations complete
        if torch.cuda.is_available():
            torch.cuda.synchronize()  # Wait for all GPU operations to complete
            torch.cuda.empty_cache()  # Now safe to clear cache

        # Unload model to free memory
        if self.model is not None:
            del self.model
            self.model = None
            self._model_loaded = False

        # Notify GPU manager
        recovery = self.gpu_manager.handle_oom_error()
        self.logger.info("deepseek_gpu_oom_recovered", recovery_info=recovery)

    async def _cleanup_gpu_resources(self) -> None:
        """Cleanup GPU resources after processing."""
        if torch.cuda.is_available():
            torch.cuda.synchronize()  # Wait for all GPU operations to complete
            torch.cuda.empty_cache()  # Now safe to clear cache

    async def process_batch(
        self, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents in batch for better GPU utilization.

        Args:
            documents: List of input documents

        Returns:
            List of OCR results
        """
        batch_size = min(len(documents), self.MAX_BATCH_SIZE)
        batch_size = min(
            batch_size, self.gpu_manager.get_optimal_batch_size("deepseek")
        )

        self.logger.info(
            "deepseek_batch_processing",
            total_documents=len(documents),
            batch_size=batch_size,
        )

        results = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            # Process batch concurrently
            batch_results = await asyncio.gather(
                *[self.process(doc) for doc in batch], return_exceptions=True
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    self.logger.error(
                        "deepseek_batch_item_failed", error=str(result)
                    )
                    results.append({"error": str(result)})
                else:
                    # result ist bereits das Dict von to_dict(), nicht {"result": ...}
                    results.append(result)

        return results

    async def cleanup(self) -> None:
        """Clean up GPU resources and unload model."""
        self.logger.info("deepseek_cleanup_started")

        # Unload model
        if self.model is not None:
            del self.model
            self.model = None

        if self.processor is not None:
            del self.processor
            self.processor = None

        self._model_loaded = False

        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        # Deallocate from GPU manager
        self.gpu_manager.deallocate_backend("deepseek")

        # Call parent cleanup
        await super().cleanup()

        self.logger.info("deepseek_cleanup_completed")

    def get_status(self) -> Dict[str, Any]:
        """Get agent status information."""
        status = {
            "name": self.name,
            "category": self.category.value,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "model_loaded": self._model_loaded,
            "model_name": self.MODEL_NAME,
            "quantization_enabled": self.ENABLE_QUANTIZATION,
            "quantization_active": self._quantization_active,
            "quantization_method": getattr(self, "_quantization_method", None),
            "bitsandbytes_available": BITSANDBYTES_AVAILABLE,
            "gptq_available": GPTQ_AVAILABLE,
            "awq_available": AWQ_AVAILABLE,
            "platform": "windows" if IS_WINDOWS else "linux/other",
        }

        # Add GPU info if available
        if torch.cuda.is_available():
            status["gpu_info"] = {
                "device_name": torch.cuda.get_device_name(0),
                "total_memory_gb": torch.cuda.get_device_properties(0).total_memory / 1024**3,
                "allocated_memory_gb": torch.cuda.memory_allocated() / 1024**3,
                "cached_memory_gb": torch.cuda.memory_reserved() / 1024**3,
            }
        else:
            status["gpu_info"] = {"available": False}

        return status
