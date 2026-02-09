# -*- coding: utf-8 -*-
"""
Chandra OCR Agent fuer Ablage-System.

State-of-the-Art 9B Vision-Language Model von Datalab (Surya/Marker Entwickler).
Benchmark-Score: 83.1 - beste Open-Source Performance (olmOCR-Bench).

VRAM: ~14-16GB (Standard) / ~8-9GB (8-bit) / ~4-5GB (4-bit)
Staerken: Tabellen (88%), Tiny Text (92.3%), Mathematik (80.3%), Handschrift
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Literal

import structlog
import torch
from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent, OCRResult
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# OCR Prompt optimiert fuer deutsche Geschaeftsdokumente
OCR_PROMPT = """Extrahiere den gesamten sichtbaren Text aus diesem Dokument.
Gib NUR den extrahierten Text zurueck, ohne Erklaerungen oder Formatierung.
Achte besonders auf:
- Deutsche Umlaute (ae, oe, ue, ss)
- IBAN und BIC Nummern
- Zahlen und Datumsangaben
- Firmennamen und Adressen
- Tabellenstrukturen"""


# Quantisierungs-Modus Typ
QuantizationMode = Literal["none", "4bit", "8bit"]


class ChandraOCRAgent(OCRAgent):
    """
    Chandra OCR Agent - State-of-the-Art 9B VLM von Datalab.

    Verwendet das Chandra-Modell fuer hochpraezise Textextraktion
    mit herausragender Tabellen- und Tiny-Text-Erkennung.

    Features:
    - 9B Parameter Vision-Language Model
    - Basiert auf Qwen-3-VL
    - Unterstuetzt Standard, 8-bit und 4-bit Quantisierung
    - Automatischer OOM-Fallback auf niedrigere Quantisierung
    """

    MODEL_NAME = "datalab-to/chandra"
    VRAM_REQUIRED_GB = 15  # Standard FP16
    VRAM_8BIT_GB = 9       # 8-bit Quantisierung
    VRAM_4BIT_GB = 5       # 4-bit Quantisierung
    MODEL_LOADING_TIMEOUT = 1800.0  # 30 Minuten fuer initialen Download

    # Class-level Lock fuer Thread-Safe Model Loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self, quantization: QuantizationMode = "none"):
        """
        Initialisiere Chandra OCR Agent.

        Args:
            quantization: Quantisierungs-Modus
                - "none": Volle FP16 Praezision (~15GB VRAM)
                - "8bit": 8-bit Quantisierung (~9GB VRAM)
                - "4bit": 4-bit Quantisierung (~5GB VRAM)
        """
        # Class-level Lock initialisieren
        if ChandraOCRAgent._model_lock is None:
            ChandraOCRAgent._model_lock = asyncio.Lock()

        self.quantization = quantization

        # GPU-Verfuegbarkeit pruefen
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        # VRAM basierend auf Quantisierung
        if quantization == "4bit":
            vram_gb = self.VRAM_4BIT_GB
        elif quantization == "8bit":
            vram_gb = self.VRAM_8BIT_GB
        else:
            vram_gb = self.VRAM_REQUIRED_GB

        # Base-Class initialisieren
        gpu_required = torch.cuda.is_available()
        if not gpu_required:
            vram_gb = 0

        super().__init__(
            name="chandra_ocr_agent",
            gpu_required=gpu_required,
            vram_gb=vram_gb
        )

        # Model-Referenzen
        self._model = None
        self._processor = None
        self._models_loaded = False
        self._current_quantization = quantization

        # GPU-Optimierungen aktivieren
        if torch.cuda.is_available():
            # TensorFloat-32 fuer RTX 40xx Serie
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cudnn.benchmark = True

            logger.info(
                "chandra_agent_gpu_detected",
                device=torch.cuda.get_device_name(0),
                cuda_version=torch.version.cuda,
                vram_gb=round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
                quantization=quantization
            )
        else:
            logger.warning("chandra_agent_no_gpu_cpu_fallback")

        logger.info(
            "chandra_ocr_agent_initialized",
            device=str(self.device),
            dtype=str(self.dtype),
            model=self.MODEL_NAME,
            quantization=quantization
        )

    async def _load_models_async(
        self,
        timeout_seconds: float = MODEL_LOADING_TIMEOUT,
        quantization: Optional[QuantizationMode] = None
    ):
        """
        Lade Chandra Modell mit Thread-Safe Locking und Timeout.

        Args:
            timeout_seconds: Maximale Wartezeit fuer Model-Loading
            quantization: Optional - ueberschreibt self.quantization

        Raises:
            asyncio.TimeoutError: Bei Timeout-Ueberschreitung
        """
        async with ChandraOCRAgent._model_lock:
            target_quantization = quantization or self.quantization

            # Pruefen ob Reload noetig
            if self._models_loaded and self._current_quantization == target_quantization:
                return

            # Bei Wechsel der Quantisierung: erst entladen
            if self._models_loaded and self._current_quantization != target_quantization:
                logger.info(
                    "chandra_reloading_with_different_quantization",
                    old=self._current_quantization,
                    new=target_quantization
                )
                await self._unload_models()

            loop = asyncio.get_event_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self._load_models_sync(target_quantization)
                    ),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    "chandra_model_loading_timeout",
                    timeout_seconds=timeout_seconds,
                    device=str(self.device),
                    quantization=target_quantization,
                    message="Model-Loading hat Timeout ueberschritten"
                )
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                raise

    def _load_models_sync(self, quantization: QuantizationMode = "none"):
        """Synchrones Model-Loading (intern verwendet)."""
        if self._models_loaded and self._current_quantization == quantization:
            return

        try:
            import os
            import sys

            # Disable tqdm progress bars to avoid Windows encoding issues
            os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
            os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

            # Force UTF-8 encoding for Windows
            if sys.platform == "win32":
                try:
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
                except Exception as e:
                    logger.debug(
                        "windows_encoding_reconfigure_failed",
                        error_type=type(e).__name__,
                    )

            logger.info(
                "chandra_loading_models",
                model=self.MODEL_NAME,
                device=str(self.device),
                quantization=quantization
            )

            # GPU Cache leeren vor dem Laden
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Importiere benoetigte Klassen
            # Chandra basiert auf Qwen3-VL, also brauchen wir die richtige Vision-Language Klasse
            from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
            from transformers import logging as transformers_logging

            # Suppress transformers warnings during loading
            transformers_logging.set_verbosity_error()

            # Lade Processor
            logger.info("chandra_loading_processor")
            self._processor = AutoProcessor.from_pretrained(
                self.MODEL_NAME,
                trust_remote_code=True
            )

            # Model-Loading basierend auf Quantisierung
            if quantization == "4bit":
                logger.info("chandra_loading_model_4bit")
                from transformers import BitsAndBytesConfig

                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )

                self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                    self.MODEL_NAME,
                    quantization_config=bnb_config,
                    device_map="cuda",
                    trust_remote_code=True,
                    attn_implementation="sdpa"  # Optimiertes Attention
                )

            elif quantization == "8bit":
                logger.info("chandra_loading_model_8bit")
                from transformers import BitsAndBytesConfig

                bnb_config = BitsAndBytesConfig(
                    load_in_8bit=True
                )

                self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                    self.MODEL_NAME,
                    quantization_config=bnb_config,
                    device_map="cuda",
                    trust_remote_code=True,
                    attn_implementation="sdpa"  # Optimiertes Attention
                )

            else:
                # Standard FP16
                logger.info("chandra_loading_model_fp16", dtype=str(self.dtype))
                self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                    self.MODEL_NAME,
                    dtype=self.dtype,  # Neuer Parameter statt torch_dtype
                    device_map="cuda" if torch.cuda.is_available() else "cpu",
                    trust_remote_code=True,
                    attn_implementation="sdpa"  # Optimiertes Attention
                )

            # Model in Inference-Modus setzen
            self._model.eval()  # Standard PyTorch Inference-Modus

            self._models_loaded = True
            self._current_quantization = quantization

            # VRAM-Verbrauch loggen
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                logger.info(
                    "chandra_models_loaded",
                    vram_used_gb=round(allocated, 2),
                    quantization=quantization
                )

            logger.info("chandra_models_loaded_successfully")

            # Warmup fuer CUDA Kernel Compilation
            self._warmup_model()

        except Exception as e:
            logger.error("chandra_model_load_failed", **safe_error_log(e), exc_info=True)
            raise

    async def _unload_models(self):
        """Entlade Modelle und gib GPU-Speicher frei."""
        logger.info("chandra_unloading_models")

        self._model = None
        self._processor = None
        self._models_loaded = False

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        logger.info("chandra_models_unloaded")

    def _warmup_model(self):
        """Warmup-Inference um CUDA Kernels zu kompilieren."""
        if not torch.cuda.is_available() or not self._models_loaded:
            return

        try:
            start = time.perf_counter()
            logger.info("chandra_warmup_starting")

            # Kleines Dummy-Bild fuer Warmup
            dummy_image = Image.new('RGB', (224, 224), color='white')

            # Minimale Inference
            with torch.no_grad():
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": dummy_image},
                            {"type": "text", "text": "test"}
                        ]
                    }
                ]

                # Nur Text-Teil fuer Warmup
                text = self._processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )

            torch.cuda.synchronize()

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "chandra_warmup_completed",
                warmup_time_ms=round(elapsed_ms, 1)
            )

        except Exception as e:
            # Warmup-Fehler sind nicht kritisch
            logger.warning("chandra_warmup_failed", **safe_error_log(e))

    def _load_image(self, image_path: str) -> List[Image.Image]:
        """
        Lade Bild(er) aus Datei - unterstuetzt PDFs und Bildformate.

        Args:
            image_path: Pfad zur Bild- oder PDF-Datei

        Returns:
            Liste von PIL Images (eine pro Seite)
        """
        path = Path(image_path)
        images = []

        if not path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {image_path}")

        if path.suffix.lower() == '.pdf':
            # PDF-Verarbeitung
            logger.info("chandra_processing_pdf", path=image_path)
            try:
                pdf = pdfium.PdfDocument(image_path)
                for page_num in range(len(pdf)):
                    page = pdf[page_num]
                    # 300 DPI fuer gute Qualitaet
                    pil_image = page.render(scale=300/72).to_pil()
                    images.append(pil_image)
                    logger.debug(
                        "chandra_pdf_page_loaded",
                        page=page_num + 1,
                        total=len(pdf)
                    )
                pdf.close()
            except Exception as e:
                logger.error("chandra_pdf_load_failed", **safe_error_log(e))
                raise
        else:
            # Bild-Verarbeitung (PNG, JPG, TIF, etc.)
            logger.info("chandra_processing_image", path=image_path)
            try:
                image = Image.open(image_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)
            except Exception as e:
                logger.error("chandra_image_load_failed", **safe_error_log(e))
                raise

        return images

    def _process_single_image(self, image: Image.Image, language: str = "de") -> Dict[str, Any]:
        """
        Verarbeite ein einzelnes Bild mit Chandra.

        Args:
            image: PIL Image
            language: Sprache (Standard: Deutsch)

        Returns:
            Dict mit text, confidence, etc.
        """
        if not self._models_loaded:
            self._load_models_sync(self.quantization)

        # GPU Cache vor Verarbeitung leeren
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        try:
            # Nachricht fuer Chandra Vision-Language Model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": OCR_PROMPT}
                    ]
                }
            ]

            # Chat-Template anwenden
            text_prompt = self._processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            # Inputs vorbereiten
            inputs = self._processor(
                text=[text_prompt],
                images=[image],
                padding=True,
                return_tensors="pt"
            )

            # Auf GPU verschieben wenn verfuegbar
            if torch.cuda.is_available():
                inputs = inputs.to("cuda")

            # Inference
            with torch.no_grad():
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=4096,  # Viel Text fuer Dokumente
                    do_sample=False,      # Deterministische Ausgabe fuer OCR
                    num_beams=1,          # Greedy fuer Geschwindigkeit
                    pad_token_id=self._processor.tokenizer.pad_token_id,
                )

            # Output dekodieren
            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]

            output_text = self._processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            # Text bereinigen
            extracted_text = output_text.strip()

            # Deutsche Zeichen pruefen
            german_chars = ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue', 'ss']
            found_german = [c for c in german_chars if c in extracted_text]

            if found_german:
                logger.debug("chandra_german_chars_detected", chars=found_german)

            # GPU Memory loggen
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                peak = torch.cuda.max_memory_allocated() / 1024**3
                logger.debug(
                    "chandra_gpu_memory",
                    current_gb=round(allocated, 2),
                    peak_gb=round(peak, 2)
                )

            return {
                "text": extracted_text,
                "confidence": 0.95,  # Chandra hat keine native Confidence-Ausgabe
                "text_regions": len(extracted_text.split('\n')),
                "german_chars_found": found_german
            }

        except torch.cuda.OutOfMemoryError as e:
            error_info = safe_error_log(e)
            logger.error("chandra_gpu_oom", **error_info)
            torch.cuda.empty_cache()
            return {
                "text": "",
                "confidence": 0.0,
                "text_regions": 0,
                "german_chars_found": [],
                "error": "GPU Out of Memory",
                "oom": True
            }

        except Exception as e:
            error_info = safe_error_log(e)
            logger.error("chandra_image_processing_failed", **error_info, exc_info=True)
            safe_msg = error_info.get("error_message", error_info["error_type"])
            return {
                "text": "",
                "confidence": 0.0,
                "text_regions": 0,
                "german_chars_found": [],
                "error": safe_msg
            }

    async def _process_with_oom_fallback(
        self,
        image: Image.Image,
        language: str = "de"
    ) -> Dict[str, Any]:
        """
        Verarbeite Bild mit automatischem OOM-Fallback.

        Bei OOM wird automatisch auf niedrigere Quantisierung gewechselt:
        - none -> 8bit -> 4bit

        Args:
            image: PIL Image
            language: Sprache

        Returns:
            Verarbeitungsergebnis
        """
        quantization_fallback = ["none", "8bit", "4bit"]

        # Starte mit aktueller Quantisierung
        start_idx = quantization_fallback.index(self._current_quantization) \
            if self._current_quantization in quantization_fallback else 0

        for i, quant_mode in enumerate(quantization_fallback[start_idx:], start=start_idx):
            if i > start_idx:
                # Wechsel zu niedrigerer Quantisierung
                logger.warning(
                    "chandra_oom_fallback",
                    from_mode=self._current_quantization,
                    to_mode=quant_mode
                )
                await self._unload_models()
                await self._load_models_async(quantization=quant_mode)

            result = self._process_single_image(image, language)

            if not result.get("oom", False):
                return result

            # OOM aufgetreten - versuche naechste Stufe
            logger.warning(
                "chandra_oom_trying_lower_quantization",
                current=quant_mode,
                next=quantization_fallback[i + 1] if i + 1 < len(quantization_fallback) else None
            )

        # Alle Stufen fehlgeschlagen
        return {
            "text": "",
            "confidence": 0.0,
            "text_regions": 0,
            "german_chars_found": [],
            "error": "GPU Out of Memory - auch mit 4-bit Quantisierung. Bitte andere Modelle entladen."
        }

    async def process(
        self,
        input_data: Union[str, Dict[str, Any]],
        language: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Verarbeite Dokument mit Chandra OCR.

        Args:
            input_data: Pfad zur Datei oder Dict mit image_path
            language: Sprache (Standard: "de")
            **kwargs: Zusaetzliche Parameter

        Returns:
            Standardisiertes OCRResult als Dict
        """
        start_time = time.time()

        try:
            # Input normalisieren
            if isinstance(input_data, dict):
                image_path = input_data.get('image_path')
                if not language:
                    language = input_data.get('language', 'de')
            else:
                image_path = input_data

            if not language:
                language = 'de'

            if not isinstance(image_path, str):
                raise ValueError(f"Erwarte String-Pfad, bekommen: {type(image_path)}")

            logger.info(
                "chandra_ocr_starting",
                image_path=image_path,
                language=language,
                quantization=self.quantization
            )

            # Models laden (async mit Timeout)
            await self._load_models_async()

            # Bilder laden
            images = self._load_image(image_path)
            logger.info("chandra_pages_loaded", count=len(images))

            # Jede Seite verarbeiten
            all_text = []
            all_confidences = []
            pages_data = []

            for i, image in enumerate(images):
                logger.info("chandra_processing_page", page=i + 1, total=len(images))

                # GPU Cache zwischen Seiten leeren
                if torch.cuda.is_available() and i > 0:
                    torch.cuda.empty_cache()

                # Verarbeitung mit OOM-Fallback
                result = await self._process_with_oom_fallback(image, language)

                # Fehler-Check
                if "error" in result and result["error"]:
                    logger.warning(
                        "chandra_page_error",
                        page=i + 1,
                        error=result["error"]
                    )

                all_text.append(result["text"])
                all_confidences.append(result["confidence"])

                # Seiten-Daten sammeln
                page_data = {
                    "page_number": i + 1,
                    "text": result["text"],
                    "page_confidence": round(result["confidence"], 3),
                    "text_regions": result.get("text_regions", 0),
                    "german_chars_found": result.get("german_chars_found", []),
                }
                pages_data.append(page_data)

            # Ergebnisse kombinieren
            full_text = "\n\n".join(all_text)
            avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Finale GPU Cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                final_memory = torch.cuda.memory_allocated() / 1024**3
                logger.info(
                    "chandra_processing_complete",
                    final_vram_gb=round(final_memory, 2),
                    processing_time_ms=processing_time_ms,
                    quantization_used=self._current_quantization
                )

            # Umlaut-Check (echte Umlaute)
            umlaut_chars = "\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df"
            has_umlauts = any(c in full_text for c in umlaut_chars)

            # Standardisiertes OCRResult erstellen
            result = self.create_success_result(
                text=full_text,
                confidence=avg_confidence,
                processing_time_ms=processing_time_ms,
                page_count=len(images),
                language=language,
                pages=pages_data,
                has_umlauts=has_umlauts,
            )

            logger.info(
                "chandra_ocr_completed",
                chars_extracted=len(full_text),
                pages=len(images),
                has_umlauts=has_umlauts,
                processing_time_ms=processing_time_ms,
                quantization_used=self._current_quantization
            )

            return result.to_dict()

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            error_info = safe_error_log(e)
            logger.error(
                "chandra_ocr_failed",
                **error_info,
                processing_time_ms=processing_time_ms,
                exc_info=True
            )

            safe_msg = error_info.get("error_message", error_info["error_type"])
            result = self.create_error_result(
                error=safe_msg,
                error_code="CHANDRA_OCR_ERROR",
                processing_time_ms=processing_time_ms
            )
            return result.to_dict()

        finally:
            # Sicherstellen dass GPU Memory freigegeben wird
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def get_status(self) -> Dict[str, Any]:
        """Hole Agent-Status inklusive GPU-Informationen."""
        status = super().get_status()

        status["model_name"] = self.MODEL_NAME
        status["models_loaded"] = self._models_loaded
        status["quantization_mode"] = self._current_quantization
        status["supported_quantizations"] = ["none", "8bit", "4bit"]

        if torch.cuda.is_available():
            status["gpu_info"] = {
                "device_name": torch.cuda.get_device_name(0),
                "cuda_version": torch.version.cuda,
                "total_vram_gb": round(
                    torch.cuda.get_device_properties(0).total_memory / 1024**3, 2
                ),
                "allocated_vram_gb": round(
                    torch.cuda.memory_allocated() / 1024**3, 2
                ),
                "cached_vram_gb": round(
                    torch.cuda.memory_reserved() / 1024**3, 2
                ),
                "tf32_enabled": torch.backends.cuda.matmul.allow_tf32,
            }
        else:
            status["gpu_info"] = {"available": False}

        return status

    async def cleanup(self):
        """Ressourcen freigeben und GPU-Speicher leeren."""
        logger.info("chandra_cleanup_starting")

        # Model-Referenzen loeschen
        self._model = None
        self._processor = None
        self._models_loaded = False

        # GPU Memory freigeben
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("chandra_gpu_memory_cleared")

        await super().cleanup()
        logger.info("chandra_cleanup_completed")
