"""
DeepSeek-Janus-Pro LoRA Fine-Tuning Trainer

Verwendet LoRA (Low-Rank Adaptation) für effizientes Fine-Tuning
des DeepSeek-Janus-Pro Vision-Language Modells auf deutschen OCR-Daten.

Features:
- QLoRA für 4-bit Quantisierung (weniger VRAM)
- Gradient Checkpointing
- Automatisches Checkpoint-Management
- Umlaut-spezifische Validation

Hardware-Anforderungen:
- RTX 4080 16GB: LoRA rank 32, batch_size 2-4
- QLoRA reduziert VRAM-Bedarf auf ~8GB

Author: Claude Code
Created: 2024-12
"""

import gc
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import torch
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


@dataclass
class LoRAConfig:
    """Konfiguration für LoRA Fine-Tuning."""
    r: int = 32
    lora_alpha: int = 64
    lora_dropout: float = 0.1
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "v_proj", "k_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ])
    bias: str = "none"
    use_qlora: bool = True
    bnb_4bit_compute_dtype: str = "float16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True


@dataclass
class TrainingConfig:
    """Konfiguration für das Training."""
    num_epochs: int = 3
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    per_device_train_batch_size: int = 2
    per_device_validation_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    gradient_checkpointing: bool = True
    fp16: bool = True
    bf16: bool = False
    validation_strategy: str = "steps"
    validation_steps: int = 100
    save_steps: int = 500
    logging_steps: int = 50
    output_dir: str = "./models/finetuned/deepseek"
    save_total_limit: int = 3
    seed: int = 42


@dataclass
class TrainingMetrics:
    """Metriken während des Trainings."""
    epoch: float
    step: int
    loss: float
    learning_rate: float
    validation_loss: Optional[float] = None
    validation_cer: Optional[float] = None
    validation_umlaut_accuracy: Optional[float] = None
    gpu_memory_mb: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ValidationResult:
    """Ergebnis der Validation."""
    loss: float
    cer: float
    wer: float
    umlaut_accuracy: float
    exact_match: float
    samples_validated: int
    inference_time_ms: float
    details: Dict[str, Any] = field(default_factory=dict)


class DeepSeekOCRDataset(Dataset):
    """Dataset für DeepSeek OCR Fine-Tuning."""

    def __init__(
        self,
        data_path: str,
        tokenizer: Any,
        processor: Any,
        max_length: int = 2048,
        is_training: bool = True
    ):
        self.tokenizer = tokenizer
        self.processor = processor
        self.max_length = max_length
        self.is_training = is_training
        self.samples = []

        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.samples.append(json.loads(line))

        logger.info(f"Geladen: {len(self.samples)} Samples aus {data_path}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.samples[idx]
        image_path = sample.get("image", "")

        if os.path.exists(image_path):
            from PIL import Image
            image = Image.open(image_path).convert("RGB")
        else:
            from PIL import Image
            image = Image.new("RGB", (224, 224), color="white")
            logger.warning(f"Bild nicht gefunden: {image_path}")

        conversations = sample.get("conversations", [])
        if len(conversations) >= 2:
            user_message = conversations[0].get("value", "")
            assistant_message = conversations[1].get("value", "")
        else:
            user_message = "Extrahiere den Text aus diesem Bild."
            assistant_message = sample.get("text", "")

        full_text = f"User: {user_message}\nAssistant: {assistant_message}"

        pixel_values = self.processor(
            images=image,
            return_tensors="pt"
        ).pixel_values.squeeze(0)

        encoding = self.tokenizer(
            full_text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )

        return {
            "input_ids": encoding.input_ids.squeeze(0),
            "attention_mask": encoding.attention_mask.squeeze(0),
            "pixel_values": pixel_values,
            "labels": encoding.input_ids.squeeze(0).clone()
        }


class DeepSeekLoRATrainer:
    """LoRA Fine-Tuning Trainer für DeepSeek-Janus-Pro."""

    def __init__(
        self,
        model_name: str = "deepseek-ai/Janus-Pro-7B",
        lora_config: Optional[LoRAConfig] = None,
        training_config: Optional[TrainingConfig] = None,
        device: Optional[str] = None
    ):
        self.model_name = model_name
        self.lora_config = lora_config or LoRAConfig()
        self.training_config = training_config or TrainingConfig()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.tokenizer = None
        self.processor = None
        self.optimizer = None
        self.scheduler = None
        self._metrics_history: List[TrainingMetrics] = []
        self._best_validation_loss = float("inf")
        self._checkpoint_dir: Optional[Path] = None
        logger.info(f"DeepSeekLoRATrainer initialisiert auf {self.device}")

    def setup(self) -> None:
        """Lädt Modell, Tokenizer und bereitet LoRA vor."""
        try:
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                AutoProcessor,
                BitsAndBytesConfig
            )
            from peft import (
                LoraConfig as PeftLoraConfig,
                get_peft_model,
                prepare_model_for_kbit_training
            )

            logger.info(f"Lade Basis-Modell: {self.model_name}")

            if self.lora_config.use_qlora:
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=getattr(
                        torch, self.lora_config.bnb_4bit_compute_dtype
                    ),
                    bnb_4bit_quant_type=self.lora_config.bnb_4bit_quant_type,
                    bnb_4bit_use_double_quant=self.lora_config.bnb_4bit_use_double_quant
                )
                logger.info("QLoRA (4-bit) aktiviert")
            else:
                bnb_config = None

            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            try:
                self.processor = AutoProcessor.from_pretrained(
                    self.model_name,
                    trust_remote_code=True
                )
            except Exception:
                from transformers import AutoImageProcessor
                self.processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    trust_remote_code=True
                )

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                quantization_config=bnb_config,
                device_map="auto" if self.lora_config.use_qlora else None,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.training_config.fp16 else torch.float32
            )

            if self.lora_config.use_qlora:
                self.model = prepare_model_for_kbit_training(
                    self.model,
                    use_gradient_checkpointing=self.training_config.gradient_checkpointing
                )

            peft_config = PeftLoraConfig(
                r=self.lora_config.r,
                lora_alpha=self.lora_config.lora_alpha,
                lora_dropout=self.lora_config.lora_dropout,
                target_modules=self.lora_config.target_modules,
                bias=self.lora_config.bias,
                task_type="CAUSAL_LM"
            )

            self.model = get_peft_model(self.model, peft_config)

            trainable_params, all_params = self._count_parameters()
            logger.info(
                f"Trainierbare Parameter: {trainable_params:,} / {all_params:,} "
                f"({100 * trainable_params / all_params:.2f}%)"
            )

            if self.training_config.gradient_checkpointing:
                self.model.gradient_checkpointing_enable()

            logger.info("Setup abgeschlossen")

        except ImportError as e:
            logger.error(f"Fehlende Abhängigkeit: {e}")
            raise RuntimeError(
                "Bitte installieren: pip install transformers peft bitsandbytes"
            ) from e

    def _count_parameters(self) -> Tuple[int, int]:
        """Zählt trainierbare und alle Parameter."""
        trainable = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in self.model.parameters())
        return trainable, total

    def _create_optimizer_and_scheduler(self, num_training_steps: int) -> None:
        """Erstellt Optimizer und Learning Rate Scheduler."""
        from transformers import get_linear_schedule_with_warmup

        optimizer_grouped_parameters = [
            {
                "params": [
                    p for n, p in self.model.named_parameters()
                    if p.requires_grad and "bias" not in n
                ],
                "weight_decay": self.training_config.weight_decay,
            },
            {
                "params": [
                    p for n, p in self.model.named_parameters()
                    if p.requires_grad and "bias" in n
                ],
                "weight_decay": 0.0,
            },
        ]

        self.optimizer = torch.optim.AdamW(
            optimizer_grouped_parameters,
            lr=self.training_config.learning_rate
        )

        num_warmup_steps = int(num_training_steps * self.training_config.warmup_ratio)
        self.scheduler = get_linear_schedule_with_warmup(
            self.optimizer,
            num_warmup_steps=num_warmup_steps,
            num_training_steps=num_training_steps
        )

    async def train(
        self,
        train_data_path: str,
        validation_data_path: Optional[str] = None,
        resume_from_checkpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Führt das Training durch."""
        if self.model is None:
            self.setup()

        train_dataset = DeepSeekOCRDataset(
            train_data_path,
            self.tokenizer,
            self.processor,
            is_training=True
        )

        validation_dataset = None
        if validation_data_path and os.path.exists(validation_data_path):
            validation_dataset = DeepSeekOCRDataset(
                validation_data_path,
                self.tokenizer,
                self.processor,
                is_training=False
            )

        train_loader = DataLoader(
            train_dataset,
            batch_size=self.training_config.per_device_train_batch_size,
            shuffle=True,
            num_workers=0,
            pin_memory=True
        )

        validation_loader = None
        if validation_dataset:
            validation_loader = DataLoader(
                validation_dataset,
                batch_size=self.training_config.per_device_validation_batch_size,
                shuffle=False,
                num_workers=0,
                pin_memory=True
            )

        num_update_steps_per_epoch = (
            len(train_loader) // self.training_config.gradient_accumulation_steps
        )
        num_training_steps = num_update_steps_per_epoch * self.training_config.num_epochs

        self._create_optimizer_and_scheduler(num_training_steps)
        self._checkpoint_dir = Path(self.training_config.output_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Starte Training...")
        logger.info(f"  Epochs: {self.training_config.num_epochs}")
        logger.info(f"  Training Samples: {len(train_dataset)}")
        logger.info(f"  Validation Samples: {len(validation_dataset) if validation_dataset else 0}")
        logger.info(f"  Total Steps: {num_training_steps}")

        self.model.train()
        global_step = 0
        start_epoch = 0

        if resume_from_checkpoint:
            start_epoch, global_step = self._load_checkpoint(resume_from_checkpoint)

        scaler = torch.cuda.amp.GradScaler() if self.training_config.fp16 else None

        for epoch in range(start_epoch, self.training_config.num_epochs):
            epoch_loss = 0.0
            self.model.train()

            for step, batch in enumerate(train_loader):
                batch = {k: v.to(self.device) for k, v in batch.items()}

                with torch.cuda.amp.autocast(enabled=self.training_config.fp16):
                    outputs = self.model(**batch)
                    loss = outputs.loss / self.training_config.gradient_accumulation_steps

                if scaler:
                    scaler.scale(loss).backward()
                else:
                    loss.backward()

                epoch_loss += loss.item() * self.training_config.gradient_accumulation_steps

                if (step + 1) % self.training_config.gradient_accumulation_steps == 0:
                    if scaler:
                        scaler.unscale_(self.optimizer)
                        torch.nn.utils.clip_grad_norm_(
                            self.model.parameters(),
                            self.training_config.max_grad_norm
                        )
                        scaler.step(self.optimizer)
                        scaler.update()
                    else:
                        torch.nn.utils.clip_grad_norm_(
                            self.model.parameters(),
                            self.training_config.max_grad_norm
                        )
                        self.optimizer.step()

                    self.scheduler.step()
                    self.optimizer.zero_grad()
                    global_step += 1

                    if global_step % self.training_config.logging_steps == 0:
                        current_lr = self.scheduler.get_last_lr()[0]
                        gpu_mem = (
                            torch.cuda.memory_allocated() / 1024**2
                            if torch.cuda.is_available() else 0
                        )

                        metrics = TrainingMetrics(
                            epoch=epoch + (step / len(train_loader)),
                            step=global_step,
                            loss=loss.item() * self.training_config.gradient_accumulation_steps,
                            learning_rate=current_lr,
                            gpu_memory_mb=gpu_mem
                        )
                        self._metrics_history.append(metrics)

                        logger.info(
                            f"Epoch {epoch+1} | Step {global_step} | "
                            f"Loss: {metrics.loss:.4f} | LR: {current_lr:.2e} | "
                            f"GPU: {gpu_mem:.0f}MB"
                        )

                    if (
                        validation_loader and
                        global_step % self.training_config.validation_steps == 0
                    ):
                        validation_result = await self._run_validation(validation_loader)
                        self._metrics_history[-1].validation_loss = validation_result.loss
                        self._metrics_history[-1].validation_cer = validation_result.cer
                        self._metrics_history[-1].validation_umlaut_accuracy = validation_result.umlaut_accuracy

                        logger.info(
                            f"  Validation - Loss: {validation_result.loss:.4f} | "
                            f"CER: {validation_result.cer:.4f} | "
                            f"Umlaut-Acc: {validation_result.umlaut_accuracy:.4f}"
                        )

                        if validation_result.loss < self._best_validation_loss:
                            self._best_validation_loss = validation_result.loss
                            self._save_checkpoint(epoch, global_step, is_best=True)

                        self.model.train()

                    if global_step % self.training_config.save_steps == 0:
                        self._save_checkpoint(epoch, global_step)

            avg_epoch_loss = epoch_loss / len(train_loader)
            logger.info(f"Epoch {epoch+1} abgeschlossen - Avg Loss: {avg_epoch_loss:.4f}")

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        self._save_checkpoint(
            self.training_config.num_epochs - 1,
            global_step,
            is_final=True
        )

        return {
            "status": "completed",
            "total_steps": global_step,
            "final_loss": self._metrics_history[-1].loss if self._metrics_history else None,
            "best_validation_loss": self._best_validation_loss,
            "output_dir": str(self._checkpoint_dir),
            "metrics_history": [vars(m) for m in self._metrics_history[-100:]]
        }

    async def _run_validation(self, validation_loader: DataLoader) -> ValidationResult:
        """Führt Validation durch."""
        import time

        self.model.eval()  # Use method call not variable
        total_loss = 0.0
        all_predictions = []
        all_references = []

        start_time = time.time()

        with torch.no_grad():
            for batch in validation_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}

                with torch.cuda.amp.autocast(enabled=self.training_config.fp16):
                    outputs = self.model(**batch)
                    total_loss += outputs.loss.item()

                generated_ids = self.model.generate(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    pixel_values=batch.get("pixel_values"),
                    max_new_tokens=512,
                    do_sample=False
                )

                predictions = self.tokenizer.batch_decode(
                    generated_ids, skip_special_tokens=True
                )
                references = self.tokenizer.batch_decode(
                    batch["labels"], skip_special_tokens=True
                )

                all_predictions.extend(predictions)
                all_references.extend(references)

        inference_time = (time.time() - start_time) * 1000 / len(validation_loader.dataset)

        avg_loss = total_loss / len(validation_loader)
        cer = self._calculate_cer(all_predictions, all_references)
        wer = self._calculate_wer(all_predictions, all_references)
        umlaut_acc = self._calculate_umlaut_accuracy(all_predictions, all_references)
        exact_match = sum(
            1 for p, r in zip(all_predictions, all_references)
            if p.strip() == r.strip()
        ) / len(all_predictions) if all_predictions else 0.0

        return ValidationResult(
            loss=avg_loss,
            cer=cer,
            wer=wer,
            umlaut_accuracy=umlaut_acc,
            exact_match=exact_match,
            samples_validated=len(all_predictions),
            inference_time_ms=inference_time
        )

    def _calculate_cer(self, predictions: List[str], references: List[str]) -> float:
        """Berechnet Character Error Rate."""
        total_chars = 0
        total_errors = 0

        for pred, ref in zip(predictions, references):
            errors = self._levenshtein_distance(pred, ref)
            total_errors += errors
            total_chars += len(ref)

        return total_errors / total_chars if total_chars > 0 else 0.0

    def _calculate_wer(self, predictions: List[str], references: List[str]) -> float:
        """Berechnet Word Error Rate."""
        total_words = 0
        total_errors = 0

        for pred, ref in zip(predictions, references):
            pred_words = pred.split()
            ref_words = ref.split()
            errors = self._levenshtein_distance(pred_words, ref_words)
            total_errors += errors
            total_words += len(ref_words)

        return total_errors / total_words if total_words > 0 else 0.0

    def _calculate_umlaut_accuracy(self, predictions: List[str], references: List[str]) -> float:
        """Berechnet Umlaut-spezifische Genauigkeit."""
        umlauts = set("äöüÄÖÜß")
        correct = 0
        total = 0

        for pred, ref in zip(predictions, references):
            for i, char in enumerate(ref):
                if char in umlauts:
                    total += 1
                    if i < len(pred) and pred[i] == char:
                        correct += 1

        return correct / total if total > 0 else 1.0

    def _levenshtein_distance(self, s1: Union[str, List[str]], s2: Union[str, List[str]]) -> int:
        """Berechnet Levenshtein-Distanz."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _save_checkpoint(
        self,
        epoch: int,
        step: int,
        is_best: bool = False,
        is_final: bool = False
    ) -> str:
        """Speichert ein Checkpoint."""
        if is_best:
            checkpoint_name = "best_model"
        elif is_final:
            checkpoint_name = "final_model"
        else:
            checkpoint_name = f"checkpoint-{step}"

        checkpoint_path = self._checkpoint_dir / checkpoint_name
        checkpoint_path.mkdir(parents=True, exist_ok=True)

        self.model.save_pretrained(checkpoint_path)

        state = {
            "epoch": epoch,
            "step": step,
            "optimizer_state": self.optimizer.state_dict(),
            "scheduler_state": self.scheduler.state_dict(),
            "lora_config": vars(self.lora_config),
            "training_config": vars(self.training_config),
            "best_validation_loss": self._best_validation_loss
        }
        torch.save(state, checkpoint_path / "training_state.pt")

        metrics_file = checkpoint_path / "metrics.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(
                [vars(m) for m in self._metrics_history],
                f,
                indent=2,
                ensure_ascii=False
            )

        logger.info(f"Checkpoint gespeichert: {checkpoint_path}")
        self._cleanup_old_checkpoints()

        return str(checkpoint_path)

    def _load_checkpoint(self, checkpoint_path: str) -> Tuple[int, int]:
        """Lädt ein Checkpoint."""
        from peft import PeftModel

        checkpoint_path = Path(checkpoint_path)
        self.model = PeftModel.from_pretrained(
            self.model.get_base_model(),
            checkpoint_path
        )

        state_path = checkpoint_path / "training_state.pt"
        if state_path.exists():
            # SECURITY: weights_only=True prevents arbitrary code execution
            state = torch.load(state_path, weights_only=True)
            self.optimizer.load_state_dict(state["optimizer_state"])
            self.scheduler.load_state_dict(state["scheduler_state"])
            self._best_validation_loss = state.get("best_validation_loss", float("inf"))
            return state["epoch"], state["step"]

        return 0, 0

    def _cleanup_old_checkpoints(self) -> None:
        """Entfernt alte Checkpoints."""
        if not self._checkpoint_dir:
            return

        checkpoints = sorted([
            d for d in self._checkpoint_dir.iterdir()
            if d.is_dir() and d.name.startswith("checkpoint-")
        ], key=lambda x: int(x.name.split("-")[1]))

        while len(checkpoints) > self.training_config.save_total_limit:
            oldest = checkpoints.pop(0)
            import shutil
            shutil.rmtree(oldest)
            logger.info(f"Altes Checkpoint gelöscht: {oldest}")

    async def merge_lora_weights(self, checkpoint_path: str, output_path: str) -> str:
        """Merged LoRA-Gewichte mit Basis-Modell."""
        from peft import PeftModel
        from transformers import AutoModelForCausalLM

        logger.info(f"Merge LoRA-Gewichte: {checkpoint_path}")

        base_model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.float16
        )

        model = PeftModel.from_pretrained(base_model, checkpoint_path)
        merged_model = model.merge_and_unload()

        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        merged_model.save_pretrained(output_path)
        self.tokenizer.save_pretrained(output_path)

        logger.info(f"Merged Modell gespeichert: {output_path}")
        return str(output_path)

    async def run_test_validation(self, test_data_path: str) -> ValidationResult:
        """Führt Validation auf Test-Daten durch."""
        if self.model is None:
            self.setup()

        test_dataset = DeepSeekOCRDataset(
            test_data_path,
            self.tokenizer,
            self.processor,
            is_training=False
        )

        test_loader = DataLoader(
            test_dataset,
            batch_size=self.training_config.per_device_validation_batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=True
        )

        return await self._run_validation(test_loader)

    def get_gpu_memory_usage(self) -> Dict[str, float]:
        """Gibt aktuelle GPU-Speichernutzung zurück."""
        if not torch.cuda.is_available():
            return {"available": False}

        return {
            "allocated_mb": torch.cuda.memory_allocated() / 1024**2,
            "reserved_mb": torch.cuda.memory_reserved() / 1024**2,
            "max_allocated_mb": torch.cuda.max_memory_allocated() / 1024**2,
            "total_mb": torch.cuda.get_device_properties(0).total_memory / 1024**2
        }
