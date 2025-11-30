"""
GOT-OCR 2.0 Agent.

Fast transformer-based OCR agent optimized for formulas, tables, and markdown output.

Best for:
- Mathematical formulas and scientific notation
- Complex table structures
- Markdown/LaTeX formatted output
- High throughput batch processing
- Multi-format output (plain, markdown, latex)
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoProcessor, AutoModel

from app.agents.base import AgentResourceError, OCRAgent
from app.gpu_manager import GPUManager


class GOTOCRAgent(OCRAgent):
    """
    GOT-OCR 2.0 processing agent (580M parameters).

    Requires:
    - 10GB VRAM (GPU mode)
    - Can fallback to CPU
    - Optimized for formulas and structured text
    """

    # Model configuration - using the HF model as per initial-prompt.md
    MODEL_NAME = "stepfun-ai/GOT-OCR-2.0-hf"
    VRAM_REQUIRED_GB = 10
    MAX_BATCH_SIZE = 8
    MODEL_LOADING_TIMEOUT = 300.0  # 5 Minuten Timeout für Model-Loading

    # Class-level lock to prevent concurrent model loading (race condition fix)
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self):
        super().__init__(
            name="got_ocr_agent",
            gpu_required=False,  # Can fallback to CPU
            vram_gb=self.VRAM_REQUIRED_GB,
        )
        self.gpu_manager = GPUManager()
        self.model = None
        self.processor = None
        self._model_loaded = False

        # Initialize class-level lock if not exists (thread-safe singleton)
        if GOTOCRAgent._model_lock is None:
            GOTOCRAgent._model_lock = asyncio.Lock()

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process document with GOT-OCR 2.0.

        Input:
            document_id: str
            image_path: str
            language: str (default: "de")
            output_format: str - "plain", "markdown", or "latex"
            extract_formulas: bool - Whether to focus on formula extraction
            region: Optional[list] - [x1, y1, x2, y2] for regional OCR

        Returns:
            text: str - Extracted text in requested format
            confidence: float - Average confidence score
            format: str - Output format used
            processing_time_ms: int
            backend: str - "got-ocr-2.0"
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]
        image_path = Path(input_data["image_path"])
        language = input_data.get("language", "de")
        output_format = input_data.get("output_format", "markdown")
        extract_formulas = input_data.get("extract_formulas", False)
        region = input_data.get("region", None)

        self.logger.info(
            "got_ocr_processing_started",
            document_id=document_id,
            image_path=str(image_path),
            output_format=output_format,
            extract_formulas=extract_formulas,
        )

        # Try to allocate GPU, fallback to CPU
        device = await self._allocate_device()

        # Load model
        await self._load_model(device)

        try:
            # Load image
            image = await self._load_image(image_path)

            # Apply region crop if specified
            if region:
                image = self._crop_region(image, region)

            # Run OCR with specified format
            result = await self._run_ocr(
                image,
                output_format=output_format,
                extract_formulas=extract_formulas,
                language=language,
                device=device
            )

            # Post-process for German text
            if language == "de":
                result = await self._postprocess_german(result)

            self.logger.info(
                "got_ocr_processing_completed",
                document_id=document_id,
                text_length=len(result["text"]),
                format=result["format"],
                device=device,
            )

            return result

        except torch.cuda.OutOfMemoryError as e:
            self.logger.error(
                "got_ocr_gpu_oom",
                document_id=document_id,
                error=str(e),
            )
            # Try to recover
            await self._handle_gpu_oom()
            raise AgentResourceError(f"GPU out of memory: {e}")

        except Exception as e:
            self.logger.error(
                "got_ocr_processing_error",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _allocate_device(self) -> str:
        """Allocate GPU or fallback to CPU."""
        allocation = self.gpu_manager.allocate_for_backend("got_ocr")

        if allocation["success"] and allocation.get("mode") == "gpu":
            return "cuda"
        else:
            self.logger.warning(
                "got_ocr_cpu_mode",
                reason="GPU not available, using CPU (slower)",
            )
            return "cpu"

    async def _load_model(self, device: str) -> None:
        """Load GOT-OCR 2.0 model with lock and timeout protection."""
        # Quick check without lock (performance optimization)
        if self._model_loaded:
            return

        # Acquire lock to prevent concurrent model loading (race condition fix)
        async with self._model_lock:
            # Double-check after acquiring lock (another request may have loaded it)
            if self._model_loaded:
                self.logger.debug("got_ocr_model_already_loaded_by_other_request")
                return

            self.logger.info("got_ocr_loading_model", device=device, model=self.MODEL_NAME)

            try:
                # Wrap actual loading with timeout
                await asyncio.wait_for(
                    self._do_load_model(device),
                    timeout=self.MODEL_LOADING_TIMEOUT
                )
                self._model_loaded = True
                self.logger.info("got_ocr_model_loaded", device=device)
            except asyncio.TimeoutError:
                self.logger.error(
                    "got_ocr_model_load_timeout",
                    timeout_seconds=self.MODEL_LOADING_TIMEOUT
                )
                raise AgentResourceError(
                    f"Model-Loading Timeout nach {self.MODEL_LOADING_TIMEOUT / 60:.0f} Minuten. "
                    "Überprüfen Sie die Netzwerkverbindung und den verfügbaren Speicher."
                )
            except Exception as e:
                self.logger.error("got_ocr_model_load_failed", error=str(e), exc_info=True)
                raise AgentResourceError(f"Fehler beim Laden des GOT-OCR-Modells: {e}")

    async def _do_load_model(self, device: str) -> None:
        """Actual model loading logic (called within lock and timeout)."""
        try:
            # Check for GOT-specific implementation
            try:
                # Try to import GOT-specific modules if available
                from transformers import AutoModelForImageTextToText
                model_class = AutoModelForImageTextToText
            except ImportError:
                # Fallback to general AutoModel
                from transformers import AutoModel
                model_class = AutoModel

            # Load processor
            self.processor = AutoProcessor.from_pretrained(
                self.MODEL_NAME,
                trust_remote_code=True,
                use_fast=True
            )

            # Load model with appropriate dtype and device
            if device == "cuda":
                self.model = model_class.from_pretrained(
                    self.MODEL_NAME,
                    torch_dtype=torch.bfloat16,
                    trust_remote_code=True,
                    device_map="auto"
                )
            else:
                self.model = model_class.from_pretrained(
                    self.MODEL_NAME,
                    torch_dtype=torch.float32,
                    trust_remote_code=True,
                    low_cpu_mem_usage=True
                )
                self.model = self.model.to(device)

            self.model.eval()  # Inference mode

            # Warm-up inference
            if device == "cuda":
                dummy_image = Image.new("RGB", (224, 224), color="white")
                _ = await self._run_ocr(
                    dummy_image,
                    output_format="plain",
                    extract_formulas=False,
                    language="de",
                    device=device,
                    warmup=True
                )
                torch.cuda.empty_cache()

        except ImportError as e:
            # Re-raise ImportError so caller can handle model not available
            raise AgentResourceError(f"GOT-OCR Model nicht verfügbar: {e}")

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

    def _crop_region(self, image: Image.Image, region: List[int]) -> Image.Image:
        """Crop image to specified region."""
        x1, y1, x2, y2 = region
        return image.crop((x1, y1, x2, y2))

    def _calculate_token_confidence(
        self,
        scores: Tuple[torch.Tensor, ...],
        generated_ids: torch.Tensor,
        skip_special_tokens: bool = True
    ) -> Dict[str, Any]:
        """
        Berechne Token-Level Confidence aus Model Output Logits.

        Args:
            scores: Tuple von Logit-Tensoren für jeden generierten Token
            generated_ids: Die generierten Token-IDs
            skip_special_tokens: Spezielle Tokens überspringen

        Returns:
            Dictionary mit Confidence-Metriken
        """
        if not scores or len(scores) == 0:
            return {
                "mean_confidence": 0.0,
                "min_confidence": 0.0,
                "weighted_confidence": 0.0,
                "token_confidences": [],
                "low_confidence_positions": [],
                "confidence_method": "no_scores"
            }

        token_confidences = []
        low_confidence_positions = []

        # Tokenizer für Special Token Detection
        tokenizer = getattr(self.processor, 'tokenizer', None)
        special_token_ids = set()
        if tokenizer:
            special_token_ids = set(tokenizer.all_special_ids) if hasattr(tokenizer, 'all_special_ids') else set()

        try:
            for idx, logits in enumerate(scores):
                # logits shape: (batch_size, vocab_size)
                if logits.dim() == 3:
                    logits = logits.squeeze(0)

                # Softmax für Wahrscheinlichkeiten
                probs = F.softmax(logits, dim=-1)

                # Hole die Wahrscheinlichkeit des tatsächlich generierten Tokens
                if idx < len(generated_ids[0]) - len(scores):
                    continue

                token_idx = idx
                if token_idx < probs.shape[0]:
                    gen_token_id = generated_ids[0, -(len(scores) - idx)].item() if len(scores) > idx else None

                    if gen_token_id is not None:
                        if skip_special_tokens and gen_token_id in special_token_ids:
                            continue

                        if probs.dim() == 1:
                            token_prob = probs[gen_token_id].item()
                        else:
                            token_prob = probs[0, gen_token_id].item()

                        token_confidences.append(token_prob)

                        if token_prob < 0.7:
                            low_confidence_positions.append({
                                "position": idx,
                                "confidence": token_prob,
                                "token_id": gen_token_id
                            })

            if token_confidences:
                mean_conf = float(np.mean(token_confidences))
                min_conf = float(np.min(token_confidences))
                weighted_conf = 0.7 * mean_conf + 0.3 * min_conf
            else:
                mean_conf = 0.0
                min_conf = 0.0
                weighted_conf = 0.0

            return {
                "mean_confidence": mean_conf,
                "min_confidence": min_conf,
                "weighted_confidence": weighted_conf,
                "token_confidences": token_confidences[:100],
                "low_confidence_positions": low_confidence_positions[:20],
                "total_tokens": len(token_confidences),
                "confidence_method": "token_logits"
            }

        except Exception as e:
            self.logger.warning(
                "got_confidence_calculation_error",
                error=str(e),
                fallback="heuristic"
            )
            return {
                "mean_confidence": 0.85,
                "min_confidence": 0.70,
                "weighted_confidence": 0.80,
                "token_confidences": [],
                "low_confidence_positions": [],
                "confidence_method": "fallback_error"
            }

    async def _run_ocr(
        self,
        image: Image.Image,
        output_format: str,
        extract_formulas: bool,
        language: str,
        device: str,
        warmup: bool = False
    ) -> Dict[str, Any]:
        """Run GOT-OCR 2.0 inference with format-specific processing."""
        start_time = time.perf_counter()

        # Warmup pass
        if warmup:
            return {"text": "", "confidence": 0.0, "format": "plain"}

        try:
            # GOT-OCR 2.0 HF uses a specific input format
            # The processor expects images directly, not text prompts

            # Ensure image is RGB and has reasonable size
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Resize if too small (GOT-OCR needs minimum size)
            min_size = 224
            if image.width < min_size or image.height < min_size:
                # Scale up maintaining aspect ratio
                scale = max(min_size / image.width, min_size / image.height)
                new_size = (int(image.width * scale), int(image.height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            # Process image with GOT-OCR processor
            # The processor handles image preprocessing automatically
            inputs = self.processor(images=image, return_tensors="pt")

            # Move to device
            inputs = {k: v.to(device) if torch.is_tensor(v) else v
                     for k, v in inputs.items()}

            # Run inference mit output_scores für Confidence
            # Mixed-precision inference for better GPU performance
            confidence_data = None
            with torch.no_grad(), torch.cuda.amp.autocast(enabled=(device == "cuda"), dtype=torch.bfloat16):
                if hasattr(self.model, 'generate'):
                    # Get tokenizer for special tokens
                    tokenizer = getattr(self.processor, 'tokenizer', None)

                    generate_kwargs = {
                        "max_new_tokens": 4096,
                        "do_sample": False,
                        "output_scores": True,
                        "return_dict_in_generate": True,
                    }

                    # Add token IDs if tokenizer available
                    if tokenizer is not None:
                        if hasattr(tokenizer, 'eos_token_id') and tokenizer.eos_token_id is not None:
                            generate_kwargs["eos_token_id"] = tokenizer.eos_token_id
                            generate_kwargs["pad_token_id"] = tokenizer.eos_token_id

                    outputs = self.model.generate(**inputs, **generate_kwargs)

                    # Extrahiere Sequenzen und Scores
                    generated_ids = outputs.sequences if hasattr(outputs, 'sequences') else outputs
                    scores = outputs.scores if hasattr(outputs, 'scores') else None

                    # Berechne Token-Level Confidence
                    if scores:
                        confidence_data = self._calculate_token_confidence(scores, generated_ids)

                    # Decode output
                    if hasattr(outputs, 'sequences'):
                        if hasattr(self.processor, 'batch_decode'):
                            text = self.processor.batch_decode(outputs.sequences, skip_special_tokens=True)[0]
                        elif tokenizer is not None and hasattr(tokenizer, 'decode'):
                            text = tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)
                        else:
                            text = str(outputs.sequences)
                    else:
                        if hasattr(self.processor, 'batch_decode'):
                            text = self.processor.batch_decode(outputs, skip_special_tokens=True)[0]
                        elif tokenizer is not None and hasattr(tokenizer, 'decode'):
                            text = tokenizer.decode(outputs[0], skip_special_tokens=True)
                        else:
                            text = str(outputs)
                else:
                    # Direct prediction model (less common)
                    outputs = self.model(**inputs)
                    if hasattr(outputs, 'logits'):
                        predicted_ids = torch.argmax(outputs.logits, dim=-1)
                        text = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
                    else:
                        text = str(outputs)

            # Calculate processing time
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Clean up text
            text = text.strip()

            # Berechne finale Confidence aus Token-Level Daten
            if confidence_data and confidence_data.get("confidence_method") == "token_logits":
                confidence = confidence_data.get("weighted_confidence", 0.0)

                # Bonus für erkannte Formeln
                if extract_formulas and "$" in text:
                    confidence = min(1.0, confidence * 1.05)

                # Sicherstelle gültigen Bereich
                confidence = max(0.0, min(1.0, confidence))
            else:
                # Fallback: Heuristische Confidence
                if not text:
                    confidence = 0.0
                elif len(text) < 10:
                    confidence = 0.5
                elif extract_formulas and "$" in text:
                    confidence = 0.90
                else:
                    confidence = 0.85

            # Baue Result mit Confidence-Details
            result = {
                "text": text,
                "confidence": confidence,
                "format": output_format,
                "model": self.MODEL_NAME,
                "device": device,
                "processing_time_ms": processing_time_ms,
                "backend": "got-ocr-2.0",
                "success": True,
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

        except Exception as e:
            self.logger.error("got_ocr_inference_error", error=str(e), exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "format": output_format,
                "model": self.MODEL_NAME,
                "device": device,
                "processing_time_ms": int((time.perf_counter() - start_time) * 1000),
                "backend": "got-ocr-2.0",
                "success": False,
                "error": str(e),
            }

    async def _postprocess_german(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process for German language specifics with context-aware correction."""
        import re

        text = result["text"]
        corrections: List[Dict[str, str]] = []

        # German words that commonly need umlaut restoration
        # These are words where ae/oe/ue should become umlauts
        german_umlaut_words = {
            # Common business/document words
            'über', 'überprüfung', 'überweisung', 'übersicht', 'übernahme',
            'für', 'führung', 'ausführung', 'durchführung',
            'büro', 'gebühr', 'gebühren',
            'größe', 'größer', 'größte',
            'öffentlich', 'öffnung', 'eröffnung',
            'änderung', 'ändern', 'ergänzung',
            'prüfung', 'prüfen', 'überprüfen',
            'erklärung', 'klärung', 'aufklärung',
            'möglich', 'möglichkeit', 'unmöglich',
            'geschäft', 'geschäftsführer', 'geschäftlich',
            'gültig', 'gültigkeit', 'ungültig',
            'straße', 'hauptstraße',
            'müller', 'schröder', 'köhler', 'bäcker',
            'münchen', 'köln', 'düsseldorf', 'nürnberg', 'würzburg',
            'träger', 'empfänger', 'absender',
            'währung', 'erläuterung', 'begründung',
            'verfügung', 'verfügbar', 'zuständig',
            'ausländisch', 'inländisch',
            'stück', 'rückgabe', 'rücksendung',
            'kürzlich', 'natürlich', 'persönlich',
        }

        # Words where ss should become ß (after long vowels/diphthongs)
        eszett_words = {
            'groß', 'größe', 'größer', 'größte',
            'straße', 'hauptstraße',
            'gruß', 'grüße', 'begrüßung',
            'fuß', 'füße',
            'maß', 'maße', 'maßnahme',
            'spaß',
            'weiß', 'weißer',
            'heiß', 'heißt', 'heißen',
            'außen', 'außer', 'außerdem', 'außerhalb',
            'schließen', 'schließlich', 'abschließend',
            'gemäß',
        }

        # Build reverse mapping for detection
        umlaut_to_ascii = {
            'ü': 'ue', 'ö': 'oe', 'ä': 'ae',
            'Ü': 'Ue', 'Ö': 'Oe', 'Ä': 'Ae',
        }

        # Apply context-aware umlaut restoration
        words = re.findall(r'\b\w+\b', text)
        for word in words:
            word_lower = word.lower()

            # Try umlaut replacements
            test_word = word_lower
            for umlaut, ascii_form in umlaut_to_ascii.items():
                test_word = test_word.replace(ascii_form.lower(), umlaut.lower())

            # Check if the corrected word is in our vocabulary
            if test_word in german_umlaut_words and test_word != word_lower:
                # Preserve original case pattern
                if word[0].isupper():
                    corrected = test_word.capitalize()
                elif word.isupper():
                    corrected = test_word.upper()
                else:
                    corrected = test_word

                # Apply replacement
                pattern = r'\b' + re.escape(word) + r'\b'
                if re.search(pattern, text):
                    text = re.sub(pattern, corrected, text, count=1)
                    corrections.append({
                        "original": word,
                        "corrected": corrected,
                        "type": "umlaut_restoration"
                    })

        # Apply ß corrections for known words
        for eszett_word in eszett_words:
            ss_version = eszett_word.replace('ß', 'ss')
            # Case variations
            for original, replacement in [
                (ss_version, eszett_word),
                (ss_version.capitalize(), eszett_word.capitalize()),
                (ss_version.upper(), eszett_word.upper()),
            ]:
                pattern = r'\b' + re.escape(original) + r'\b'
                if re.search(pattern, text):
                    text = re.sub(pattern, replacement, text)
                    corrections.append({
                        "original": original,
                        "corrected": replacement,
                        "type": "eszett_restoration"
                    })

        # Validate with GermanValidator if available
        validation_result = None
        try:
            from app.german_validator import GermanValidator
            validator = GermanValidator()
            validation_result = validator.validate_umlauts(text)
        except ImportError:
            self.logger.debug("german_validator_not_available")

        result["text"] = text
        result["german_processed"] = True
        result["corrections"] = corrections
        result["corrections_count"] = len(corrections)
        if validation_result:
            result["umlaut_validation"] = validation_result

        return result

    async def _handle_gpu_oom(self) -> None:
        """Handle GPU out-of-memory error."""
        self.logger.warning("got_ocr_gpu_oom_recovery", action="clearing_cache")

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
        self.logger.info("got_ocr_gpu_oom_recovered", recovery_info=recovery)

    async def process_batch(
        self, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents in batch for better GPU utilization.
        GOT-OCR 2.0 is optimized for batch processing.

        Args:
            documents: List of input documents

        Returns:
            List of OCR results
        """
        batch_size = min(len(documents), self.MAX_BATCH_SIZE)
        batch_size = min(
            batch_size, self.gpu_manager.get_optimal_batch_size("got_ocr")
        )

        self.logger.info(
            "got_ocr_batch_processing",
            total_documents=len(documents),
            batch_size=batch_size,
        )

        results = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            # Process batch concurrently
            batch_results = await asyncio.gather(
                *[self.process(doc) for doc in batch],
                return_exceptions=True
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    self.logger.error(
                        "got_ocr_batch_item_failed",
                        error=str(result)
                    )
                    results.append({"error": str(result)})
                else:
                    results.append(result)

        return results

    async def cleanup(self) -> None:
        """Clean up GPU resources and unload model."""
        self.logger.info("got_ocr_cleanup_started")

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
        self.gpu_manager.deallocate_backend("got_ocr")

        # Call parent cleanup
        await super().cleanup()

        self.logger.info("got_ocr_cleanup_completed")

    def get_status(self) -> Dict[str, Any]:
        """Get agent status information."""
        status = {
            "name": self.name,
            "category": self.category.value,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "model_loaded": self._model_loaded,
            "model_name": self.MODEL_NAME,
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