# -*- coding: utf-8 -*-
"""
OlmOCR-2 Agent fuer Ablage-System.

State-of-the-Art OCR von Allen Institute for AI (Ai2).
Basiert auf Qwen2.5-VL-7B, trainiert auf olmOCR-mix-1025 (270k PDF-Seiten).

VRAM: ~14GB (FP16)
Staerken: Akademische Paper, historische Scans, komplexe Layouts, Tabellen, LaTeX
Benchmark: 82.4 Score (besser als DeepSeek 75.4)
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog
import torch
from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent, OCRResult

logger = structlog.get_logger(__name__)


# OCR Prompt optimiert fuer deutsche Geschaeftsdokumente
OCR_PROMPT = """Extrahiere den gesamten sichtbaren Text aus diesem Dokument.
Gib NUR den extrahierten Text zurueck, ohne Erklaerungen.
Achte besonders auf:
- Deutsche Umlaute (ae, oe, ue, ss)
- IBAN und BIC Nummern
- Zahlen und Datumsangaben
- Firmennamen und Adressen

Bei Tabellen: Verwende strukturiertes Format.
Bei mathematischen Formeln: Verwende LaTeX-Format."""


class OlmOCRAgent(OCRAgent):
    """
    OlmOCR-2 Agent - State-of-the-Art OCR von Allen AI.

    Verwendet das allenai/olmOCR-2-7B-1025 Modell fuer hochpraezise
    Textextraktion mit besonderer Staerke bei:
    - Akademischen Papers
    - Historischen Scans
    - Komplexen Layouts
    - Tabellen (HTML Output)
    - Mathematik (LaTeX Output)
    """

    MODEL_NAME = "allenai/olmOCR-2-7B-1025"
    VRAM_REQUIRED_GB = 14
    MODEL_LOADING_TIMEOUT = 600.0  # 10 Minuten fuer grosses Modell

    # Class-level Lock fuer Thread-Safe Model Loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self):
        """Initialisiere OlmOCR Agent mit GPU-Optimierungen."""
        # Class-level Lock initialisieren
        if OlmOCRAgent._model_lock is None:
            OlmOCRAgent._model_lock = asyncio.Lock()

        # GPU-Verfuegbarkeit pruefen
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        # Base-Class initialisieren
        gpu_required = torch.cuda.is_available()
        vram_gb = self.VRAM_REQUIRED_GB if gpu_required else 0

        super().__init__(
            name="olmocr_agent",
            gpu_required=gpu_required,
            vram_gb=vram_gb
        )

        # Model-Referenzen
        self._model = None
        self._processor = None
        self._models_loaded = False

        # GPU-Optimierungen aktivieren
        if torch.cuda.is_available():
            # TensorFloat-32 fuer RTX 40xx Serie
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cudnn.benchmark = True

            logger.info(
                "olmocr_agent_gpu_detected",
                device=torch.cuda.get_device_name(0),
                cuda_version=torch.version.cuda,
                vram_gb=round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
            )
        else:
            logger.warning("olmocr_agent_no_gpu_cpu_fallback")

        logger.info(
            "olmocr_agent_initialized",
            device=str(self.device),
            dtype=str(self.dtype),
            model=self.MODEL_NAME
        )

    async def _load_models_async(self, timeout_seconds: float = MODEL_LOADING_TIMEOUT):
        """
        Lade OlmOCR-2 Modell mit Thread-Safe Locking und Timeout.

        Args:
            timeout_seconds: Maximale Wartezeit fuer Model-Loading

        Raises:
            asyncio.TimeoutError: Bei Timeout-Ueberschreitung
        """
        async with OlmOCRAgent._model_lock:
            # Double-Check Pattern
            if self._models_loaded:
                return

            loop = asyncio.get_event_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._load_models_sync),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    "olmocr_model_loading_timeout",
                    timeout_seconds=timeout_seconds,
                    device=str(self.device),
                    message="Model-Loading hat Timeout ueberschritten"
                )
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                raise

    def _load_models_sync(self):
        """Synchrones Model-Loading (intern verwendet)."""
        if self._models_loaded:
            return

        try:
            logger.info(
                "olmocr_loading_models",
                model=self.MODEL_NAME,
                device=str(self.device)
            )

            # GPU Cache leeren vor dem Laden
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Importiere Qwen-spezifische Klassen (OlmOCR basiert auf Qwen2.5-VL)
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

            # Lade Processor
            logger.info("olmocr_loading_processor")
            self._processor = AutoProcessor.from_pretrained(
                self.MODEL_NAME,
                trust_remote_code=True
            )

            # Lade Model mit FP16 fuer VRAM-Effizienz
            logger.info("olmocr_loading_model", dtype=str(self.dtype))
            self._model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.MODEL_NAME,
                torch_dtype=self.dtype,
                device_map="cuda" if torch.cuda.is_available() else "cpu",
                trust_remote_code=True
            )

            # Model in Inference-Modus setzen
            self._model.train(False)

            # VRAM-Verbrauch loggen
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                logger.info(
                    "olmocr_models_loaded",
                    vram_used_gb=round(allocated, 2)
                )

            self._models_loaded = True
            logger.info("olmocr_models_loaded_successfully")

            # Warmup fuer CUDA Kernel Compilation
            self._warmup_model()

        except Exception as e:
            logger.error("olmocr_model_load_failed", error=str(e), exc_info=True)
            raise

    def _warmup_model(self):
        """Warmup-Inference um CUDA Kernels zu kompilieren."""
        if not torch.cuda.is_available() or not self._models_loaded:
            return

        try:
            start = time.perf_counter()
            logger.info("olmocr_warmup_starting")

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
                "olmocr_warmup_completed",
                warmup_time_ms=round(elapsed_ms, 1)
            )

        except Exception as e:
            # Warmup-Fehler sind nicht kritisch
            logger.warning("olmocr_warmup_failed", error=str(e))

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
            logger.info("olmocr_processing_pdf", path=image_path)
            try:
                pdf = pdfium.PdfDocument(image_path)
                for page_num in range(len(pdf)):
                    page = pdf[page_num]
                    # 300 DPI fuer gute Qualitaet
                    pil_image = page.render(scale=300/72).to_pil()
                    images.append(pil_image)
                    logger.debug(
                        "olmocr_pdf_page_loaded",
                        page=page_num + 1,
                        total=len(pdf)
                    )
                pdf.close()
            except Exception as e:
                logger.error("olmocr_pdf_load_failed", error=str(e))
                raise
        else:
            # Bild-Verarbeitung (PNG, JPG, TIF, etc.)
            logger.info("olmocr_processing_image", path=image_path)
            try:
                image = Image.open(image_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)
            except Exception as e:
                logger.error("olmocr_image_load_failed", error=str(e))
                raise

        return images

    def _process_single_image(self, image: Image.Image, language: str = "de") -> Dict[str, Any]:
        """
        Verarbeite ein einzelnes Bild mit OlmOCR-2.

        Args:
            image: PIL Image
            language: Sprache (Standard: Deutsch)

        Returns:
            Dict mit text, confidence, etc.
        """
        if not self._models_loaded:
            self._load_models_sync()

        # GPU Cache vor Verarbeitung leeren
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        try:
            # Nachricht fuer Qwen-basiertes Vision-Language Model
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
                logger.debug("olmocr_german_chars_detected", chars=found_german)

            # GPU Memory loggen
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                peak = torch.cuda.max_memory_allocated() / 1024**3
                logger.debug(
                    "olmocr_gpu_memory",
                    current_gb=round(allocated, 2),
                    peak_gb=round(peak, 2)
                )

            return {
                "text": extracted_text,
                "confidence": 0.95,  # OlmOCR hat keine native Confidence-Ausgabe
                "text_regions": len(extracted_text.split('\n')),
                "german_chars_found": found_german
            }

        except torch.cuda.OutOfMemoryError as e:
            logger.error("olmocr_gpu_oom", error=str(e))
            torch.cuda.empty_cache()
            return {
                "text": "",
                "confidence": 0.0,
                "text_regions": 0,
                "german_chars_found": [],
                "error": f"GPU Out of Memory: {e}"
            }

        except Exception as e:
            logger.error("olmocr_image_processing_failed", error=str(e), exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "text_regions": 0,
                "german_chars_found": [],
                "error": str(e)
            }

    async def process(
        self,
        input_data: Union[str, Dict[str, Any]],
        language: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Verarbeite Dokument mit OlmOCR-2.

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
                "olmocr_starting",
                image_path=image_path,
                language=language
            )

            # Models laden (async mit Timeout)
            await self._load_models_async()

            # Bilder laden
            images = self._load_image(image_path)
            logger.info("olmocr_pages_loaded", count=len(images))

            # Jede Seite verarbeiten
            all_text = []
            all_confidences = []
            pages_data = []

            for i, image in enumerate(images):
                logger.info("olmocr_processing_page", page=i + 1, total=len(images))

                # GPU Cache zwischen Seiten leeren
                if torch.cuda.is_available() and i > 0:
                    torch.cuda.empty_cache()

                result = self._process_single_image(image, language)

                # Fehler-Check
                if "error" in result and result["error"]:
                    logger.warning(
                        "olmocr_page_error",
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
                    "olmocr_processing_complete",
                    final_vram_gb=round(final_memory, 2),
                    processing_time_ms=processing_time_ms
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
                "olmocr_completed",
                chars_extracted=len(full_text),
                pages=len(images),
                has_umlauts=has_umlauts,
                processing_time_ms=processing_time_ms
            )

            return result.to_dict()

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "olmocr_failed",
                error=str(e),
                processing_time_ms=processing_time_ms,
                exc_info=True
            )

            result = self.create_error_result(
                error=str(e),
                error_code="OLMOCR_ERROR",
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
        logger.info("olmocr_cleanup_starting")

        # Model-Referenzen loeschen
        self._model = None
        self._processor = None
        self._models_loaded = False

        # GPU Memory freigeben
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("olmocr_gpu_memory_cleared")

        await super().cleanup()
        logger.info("olmocr_cleanup_completed")
