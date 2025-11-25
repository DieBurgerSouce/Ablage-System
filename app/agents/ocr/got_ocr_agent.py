"""
GOT-OCR 2.0 Agent.

Fast transformer-based OCR agent for standard text documents.

Best for:
- High throughput requirements
- Standard German text documents
- Clean scans with minimal noise
- Batch processing workflows
"""

from pathlib import Path
from typing import Any, Dict

import torch
from PIL import Image

from app.agents.base import AgentResourceError, OCRAgent
from app.gpu_manager import GPUManager


class GOTOCRAgent(OCRAgent):
    """
    GOT-OCR 2.0 processing agent.

    Requires:
    - 10GB VRAM (GPU mode)
    - Can fallback to CPU
    - GOT-OCR 2.0 model weights
    """

    MODEL_NAME = "got-ocr2_0"
    VRAM_REQUIRED_GB = 10
    MAX_BATCH_SIZE = 8

    def __init__(self):
        super().__init__(
            name="got_ocr_agent",
            gpu_required=False,  # Can fallback to CPU
            vram_gb=self.VRAM_REQUIRED_GB,
        )
        self.gpu_manager = GPUManager()
        self.model = None
        self.tokenizer = None
        self._model_loaded = False

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process document with GOT-OCR 2.0.

        Input:
            document_id: str
            image_path: str
            language: str (default: "de")
            mode: str - "ocr" or "format" (preserve formatting)

        Returns:
            text: str - Extracted text
            confidence: float - Average confidence
            processing_time_ms: int
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]
        image_path = Path(input_data["image_path"])
        language = input_data.get("language", "de")
        mode = input_data.get("mode", "format")  # Preserve formatting by default

        self.logger.info(
            "got_ocr_processing_started",
            document_id=document_id,
            image_path=str(image_path),
            mode=mode,
        )

        # Try to allocate GPU, fallback to CPU
        device = await self._allocate_device()

        # Load model
        await self._load_model(device)

        try:
            # Load image
            image = await self._load_image(image_path)

            # Run OCR
            result = await self._run_ocr(image, mode, device)

            # Post-process for German text
            if language == "de":
                result = await self._postprocess_german(result)

            self.logger.info(
                "got_ocr_processing_completed",
                document_id=document_id,
                text_length=len(result["text"]),
                device=device,
            )

            return result

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
        """Load GOT-OCR model."""
        if self._model_loaded:
            return

        self.logger.info("got_ocr_loading_model", device=device)

        try:
            # TODO: Import actual GOT-OCR model
            # from GOT import GOTQwenForCausalLM, GOTImageProcessor
            #
            # self.model = GOTQwenForCausalLM.from_pretrained(
            #     MODEL_PATH, torch_dtype=torch.bfloat16
            # ).to(device)
            #
            # self.tokenizer = GOTImageProcessor.from_pretrained(MODEL_PATH)

            # Placeholder for now
            self.model = "GOT_OCR_MODEL_PLACEHOLDER"
            self.tokenizer = "GOT_TOKENIZER_PLACEHOLDER"

            self._model_loaded = True
            self.logger.info("got_ocr_model_loaded", device=device)

        except Exception as e:
            raise AgentResourceError(f"Failed to load GOT-OCR model: {e}")

    async def _load_image(self, image_path: Path) -> Image.Image:
        """Load image."""
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Use context manager to ensure file handle is closed
        with Image.open(image_path) as img:
            # Convert and create in-memory copy (detaches from file handle)
            return img.convert("RGB").copy()

    async def _run_ocr(
        self, image: Image.Image, mode: str, device: str
    ) -> Dict[str, Any]:
        """Run GOT-OCR inference."""
        # TODO: Actual GOT-OCR inference
        # outputs = self.model.chat(
        #     self.tokenizer,
        #     image,
        #     ocr_type=mode,  # 'ocr' or 'format'
        # )

        # Placeholder
        text = f"[GOT-OCR PLACEHOLDER - Image size: {image.size}]"
        confidence = 0.92

        return {
            "text": text,
            "confidence": confidence,
            "model": self.MODEL_NAME,
            "device": device,
        }

    async def _postprocess_german(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process for German language specifics."""
        # TODO: German-specific corrections
        # - Fix common OCR errors (ue -> ü, etc.)
        # - Spell-check with German dictionary

        return result
