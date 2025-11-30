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
from typing import Any, Dict, List, Optional
from io import BytesIO

import numpy as np
import torch
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

from app.agents.base import AgentResourceError, OCRAgent
from app.gpu_manager import GPUManager

# Platform detection
IS_WINDOWS = sys.platform == "win32"


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
    MODEL_LOADING_TIMEOUT = 300.0  # 5 Minuten Timeout für Model-Loading

    # Class-level lock to prevent concurrent model loading (race condition fix)
    _model_lock: Optional[asyncio.Lock] = None

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

            # Run OCR inference
            ocr_result = await self._run_inference(image, language, options)

            # Post-process results
            result = await self._postprocess_result(ocr_result, options)

            self.logger.info(
                "deepseek_processing_completed",
                document_id=document_id,
                text_length=len(result["text"]),
                confidence=result["confidence"],
                entities_found=len(result.get("entities", [])),
            )

            return result

        except torch.cuda.OutOfMemoryError as e:
            self.logger.error(
                "deepseek_gpu_oom",
                document_id=document_id,
                error=str(e),
            )
            # Try to recover
            await self._handle_gpu_oom()
            raise AgentResourceError(f"GPU out of memory: {e}")

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
        """Load DeepSeek Janus-Pro model and processor with lock and timeout."""
        # Quick check without lock (performance optimization)
        if self._model_loaded:
            return

        # Acquire lock to prevent concurrent model loading (race condition fix)
        async with self._model_lock:
            # Double-check after acquiring lock (another request may have loaded it)
            if self._model_loaded:
                self.logger.debug("deepseek_model_already_loaded_by_other_request")
                return

            self.logger.info("deepseek_loading_model", model_name=self.MODEL_NAME)

            try:
                # Wrap actual loading with timeout
                await asyncio.wait_for(
                    self._do_load_model(),
                    timeout=self.MODEL_LOADING_TIMEOUT
                )
                self._model_loaded = True
            except asyncio.TimeoutError:
                self.logger.error(
                    "deepseek_model_load_timeout",
                    timeout_seconds=self.MODEL_LOADING_TIMEOUT
                )
                raise AgentResourceError(
                    f"Model-Loading Timeout nach {self.MODEL_LOADING_TIMEOUT / 60:.0f} Minuten. "
                    "Überprüfen Sie die Netzwerkverbindung und den verfügbaren Speicher."
                )
            except Exception as e:
                self.logger.error("deepseek_model_load_failed", error=str(e), exc_info=True)
                raise AgentResourceError(f"Fehler beim Laden des DeepSeek-Modells: {e}")

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
                if not IS_WINDOWS and BITSANDBYTES_AVAILABLE:
                    quantization_method = "bitsandbytes"
                elif GPTQ_AVAILABLE:
                    quantization_method = "gptq"
                elif AWQ_AVAILABLE:
                    quantization_method = "awq"
                else:
                    # Fall back to bfloat16 with memory optimization
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
                if quantization_method == "bitsandbytes":
                    # 4-bit quantization for RTX 4080 16GB (Linux)
                    quant_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.bfloat16,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4"
                    )
                    self.model = MultiModalityCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        quantization_config=quant_config,
                        trust_remote_code=True,
                        device_map="auto"
                    )
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
                    # bfloat16 with memory optimization
                    self.model = MultiModalityCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
                        attn_implementation="flash_attention_2" if device == "cuda" else "eager",
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
                        bnb_4bit_compute_dtype=torch.bfloat16,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4"
                    )
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.MODEL_NAME,
                        quantization_config=quant_config,
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
                    except Exception:
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
                    except Exception:
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
        """Load and validate image."""
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            # Use context manager to ensure file handle is closed
            with Image.open(image_path) as img:
                # Convert and create in-memory copy (detaches from file handle)
                image = img.convert("RGB").copy()

            self.logger.debug(
                "image_loaded",
                path=str(image_path),
                size=image.size,
                mode=image.mode,
            )
            return image
        except Exception as e:
            raise ValueError(f"Failed to load image: {e}")

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
            if hasattr(self.model, 'prepare_inputs_embeds'):
                inputs_embeds = self.model.prepare_inputs_embeds(**inputs)

                # Generate with language model component
                with torch.no_grad():
                    outputs = self.model.language_model.generate(
                        inputs_embeds=inputs_embeds,
                        attention_mask=inputs.get('attention_mask'),
                        max_new_tokens=options.get("max_tokens", 4096),
                        do_sample=False,  # Deterministic for OCR
                        temperature=0.1,
                        pad_token_id=self.tokenizer.eos_token_id,
                        eos_token_id=self.tokenizer.eos_token_id
                    )

                # Decode with tokenizer
                generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            else:
                # Fallback to standard generation
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=options.get("max_tokens", 4096),
                        do_sample=False,
                        temperature=0.1,
                        pad_token_id=self.tokenizer.eos_token_id if self.tokenizer else self.processor.tokenizer.eos_token_id
                    )

                if self.tokenizer:
                    generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                else:
                    generated_text = self.processor.batch_decode(outputs, skip_special_tokens=True)[0]
        else:
            # Standard transformers processing
            inputs = self.processor(
                text=prompt,
                images=image,
                return_tensors="pt"
            )

            # Move to device
            inputs = {k: v.to(self.model.device) if torch.is_tensor(v) else v
                     for k, v in inputs.items()}

            # Run inference
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=options.get("max_tokens", 4096),
                    temperature=options.get("temperature", 0.1),
                    do_sample=False,  # Deterministic for OCR
                    pad_token_id=self.processor.tokenizer.eos_token_id,
                )

            # Decode output
            generated_text = self.processor.batch_decode(
                outputs, skip_special_tokens=True
            )[0]

        # Calculate processing time
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Extract just the OCR text (remove prompt if included)
        if prompt in generated_text:
            generated_text = generated_text.replace(prompt, "").strip()

        # Estimate confidence based on text quality
        # Janus-Pro typically has high accuracy
        confidence = 0.95 if generated_text else 0.0

        return {
            "text": generated_text,
            "confidence": confidence,
            "model": self.MODEL_NAME,
            "processing_time_ms": processing_time_ms,
            "backend": "deepseek-janus-pro"
        }

    def _build_prompt(self, language: str, options: Dict[str, Any]) -> str:
        """Build OCR prompt for DeepSeek."""
        if language == "de":
            base_prompt = """
            Extrahiere den gesamten Text aus diesem Bild.

            Wichtig:
            - Bewahre die Formatierung (Absätze, Listen)
            - Erkenne deutsche Umlaute korrekt (ä, ö, ü, ß)
            - Erkenne Tabellen und strukturiere sie
            - Extrahiere Datum, Währung, IBAN, USt-IdNr. wenn vorhanden

            Text:
            """
        else:
            base_prompt = """
            Extract all text from this image.

            Important:
            - Preserve formatting (paragraphs, lists)
            - Recognize tables and structure them
            - Extract dates, currency, IBAN, VAT ID if present

            Text:
            """

        # Add task-specific instructions
        if options.get("extract_tables"):
            base_prompt += "\nFocus on accurately extracting table structures."

        if options.get("extract_handwriting"):
            base_prompt += "\nPay special attention to handwritten text."

        return base_prompt.strip()

    async def _postprocess_result(
        self, ocr_result: Dict[str, Any], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Post-process OCR results."""
        text = ocr_result["text"]

        # Basic text cleaning
        text = text.strip()

        # Extract structured data (IBAN, VAT, dates, phone, email, NER)
        entities = []
        if options.get("extract_entities"):
            entities = self._extract_entities(text)

        # Detect layout structure (headers, tables, lists, signatures)
        layout = {}
        if options.get("detect_layout"):
            layout = self._detect_layout(text)

        return {
            "text": text,
            "confidence": ocr_result["confidence"],
            "entities": entities,
            "layout": layout,
            "model": ocr_result["model"],
        }

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

        # 9. spaCy NER for PERSON, ORGANIZATION, LOCATION (with graceful fallback)
        try:
            import spacy

            # Try to load the large German model
            try:
                nlp = spacy.load("de_core_news_lg")
            except OSError:
                # Fallback to small model
                try:
                    nlp = spacy.load("de_core_news_sm")
                    self.logger.info("spacy_using_small_model")
                except OSError:
                    nlp = None
                    self.logger.warning("spacy_german_model_not_available")

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

        except ImportError:
            self.logger.debug("spacy_not_installed")
        except Exception as e:
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

        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
            torch.cuda.empty_cache()

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
                    results.append(result["result"])

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
