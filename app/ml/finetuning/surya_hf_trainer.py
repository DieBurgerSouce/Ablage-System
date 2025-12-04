"""
Surya-OCR HuggingFace Trainer

Fine-Tuning für Surya-OCR mit HuggingFace Trainer API.
Optimiert für deutsche Dokumente mit Umlaut-Fokus.

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
from torch.utils.data import Dataset

logger = logging.getLogger(__name__)


@dataclass
class SuryaTrainingConfig:
    """Konfiguration für Surya Fine-Tuning."""
    num_train_epochs: int = 5
    learning_rate: float = 5e-5
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    per_device_train_batch_size: int = 4
    per_device_test_batch_size: int = 8
    gradient_accumulation_steps: int = 2
    fp16: bool = True
    bf16: bool = False
    check_strategy: str = "steps"
    check_steps: int = 200
    save_strategy: str = "steps"
    save_steps: int = 500
    save_total_limit: int = 3
    logging_steps: int = 50
    output_dir: str = "./models/finetuned/surya"
    dataloader_num_workers: int = 0
    load_best_model_at_end: bool = True
    metric_for_best_model: str = "test_loss"
    greater_is_better: bool = False
    report_to: List[str] = field(default_factory=lambda: ["tensorboard"])
    seed: int = 42
    max_seq_length: int = 1024


@dataclass
class SuryaTestMetrics:
    """Metriken für Surya Testing."""
    loss: float
    cer: float
    wer: float
    umlaut_accuracy: float
    exact_match_ratio: float
    samples_count: int
    avg_inference_time_ms: float


class SuryaOCRDataset(Dataset):
    """Dataset für Surya-OCR Fine-Tuning."""

    def __init__(
        self,
        data_path: str,
        processor: Any,
        max_length: int = 1024,
        is_training: bool = True
    ):
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
        text = sample.get("text", "")

        if os.path.exists(image_path):
            from PIL import Image
            image = Image.open(image_path).convert("RGB")
        else:
            from PIL import Image
            image = Image.new("RGB", (224, 224), color="white")
            logger.warning(f"Bild nicht gefunden: {image_path}")

        try:
            encoding = self.processor(
                images=image,
                text=text,
                max_length=self.max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            )

            return {
                "pixel_values": encoding.pixel_values.squeeze(0),
                "input_ids": encoding.input_ids.squeeze(0) if hasattr(encoding, "input_ids") else None,
                "attention_mask": encoding.attention_mask.squeeze(0) if hasattr(encoding, "attention_mask") else None,
                "labels": encoding.input_ids.squeeze(0).clone() if hasattr(encoding, "input_ids") else None,
            }
        except Exception as e:
            logger.warning(f"Fehler beim Verarbeiten von Sample {idx}: {e}")
            return {
                "pixel_values": torch.zeros(3, 224, 224),
                "input_ids": torch.zeros(self.max_length, dtype=torch.long),
                "attention_mask": torch.zeros(self.max_length, dtype=torch.long),
                "labels": torch.zeros(self.max_length, dtype=torch.long),
            }


class SuryaOCRTrainer:
    """HuggingFace Trainer für Surya-OCR Fine-Tuning."""

    def __init__(
        self,
        model_name: str = "vikp/surya_rec",
        config: Optional[SuryaTrainingConfig] = None,
        device: Optional[str] = None
    ):
        self.model_name = model_name
        self.config = config or SuryaTrainingConfig()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        self.trainer = None
        self._metrics_history: List[Dict[str, Any]] = []
        self._best_test_loss = float("inf")
        logger.info(f"SuryaOCRTrainer initialisiert auf {self.device}")

    def setup(self) -> None:
        """Lädt Modell und Processor."""
        try:
            from transformers import (
                AutoModelForVision2Seq,
                AutoProcessor,
                VisionEncoderDecoderModel,
                DonutProcessor
            )

            logger.info(f"Lade Surya-Modell: {self.model_name}")

            try:
                self.processor = AutoProcessor.from_pretrained(
                    self.model_name, trust_remote_code=True
                )
            except Exception:
                logger.info("Fallback zu DonutProcessor")
                self.processor = DonutProcessor.from_pretrained(
                    self.model_name, trust_remote_code=True
                )

            try:
                self.model = AutoModelForVision2Seq.from_pretrained(
                    self.model_name, trust_remote_code=True,
                    torch_dtype=torch.float16 if self.config.fp16 else torch.float32
                )
            except Exception:
                logger.info("Fallback zu VisionEncoderDecoderModel")
                self.model = VisionEncoderDecoderModel.from_pretrained(
                    self.model_name, trust_remote_code=True,
                    torch_dtype=torch.float16 if self.config.fp16 else torch.float32
                )

            self.model.to(self.device)
            total_params = sum(p.numel() for p in self.model.parameters())
            trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
            logger.info(f"Parameter: {trainable_params:,} trainierbar / {total_params:,} gesamt")
            logger.info("Setup abgeschlossen")

        except ImportError as e:
            logger.error(f"Fehlende Abhängigkeit: {e}")
            raise RuntimeError("Bitte installieren: pip install transformers[vision]") from e

    def _create_training_args(self) -> Any:
        """Erstellt HuggingFace TrainingArguments."""
        from transformers import TrainingArguments

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        return TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=self.config.num_train_epochs,
            per_device_train_batch_size=self.config.per_device_train_batch_size,
            per_device_eval_batch_size=self.config.per_device_test_batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            warmup_ratio=self.config.warmup_ratio,
            weight_decay=self.config.weight_decay,
            max_grad_norm=self.config.max_grad_norm,
            fp16=self.config.fp16,
            bf16=self.config.bf16,
            logging_steps=self.config.logging_steps,
            save_strategy=self.config.save_strategy,
            save_steps=self.config.save_steps,
            save_total_limit=self.config.save_total_limit,
            eval_strategy=self.config.check_strategy,
            eval_steps=self.config.check_steps,
            load_best_model_at_end=self.config.load_best_model_at_end,
            metric_for_best_model=self.config.metric_for_best_model,
            greater_is_better=self.config.greater_is_better,
            dataloader_num_workers=self.config.dataloader_num_workers,
            report_to=self.config.report_to,
            seed=self.config.seed,
            remove_unused_columns=False,
        )

    def _compute_metrics(self, pred_output: Any) -> Dict[str, float]:
        """Berechnet Metriken für Trainer."""
        predictions = pred_output.predictions
        labels = pred_output.label_ids

        if isinstance(predictions, tuple):
            predictions = predictions[0]

        pred_ids = predictions.argmax(-1) if len(predictions.shape) > 2 else predictions
        pred_texts = self.processor.batch_decode(pred_ids, skip_special_tokens=True)

        labels[labels == -100] = self.processor.tokenizer.pad_token_id
        label_texts = self.processor.batch_decode(labels, skip_special_tokens=True)

        cer = self._calculate_cer(pred_texts, label_texts)
        wer = self._calculate_wer(pred_texts, label_texts)
        umlaut_acc = self._calculate_umlaut_accuracy(pred_texts, label_texts)
        exact_match = sum(
            1 for p, r in zip(pred_texts, label_texts) if p.strip() == r.strip()
        ) / len(pred_texts) if pred_texts else 0.0

        metrics = {"cer": cer, "wer": wer, "umlaut_accuracy": umlaut_acc, "exact_match": exact_match}
        self._metrics_history.append({"timestamp": datetime.now().isoformat(), **metrics})
        return metrics

    def _calculate_cer(self, predictions: List[str], references: List[str]) -> float:
        """Berechnet Character Error Rate."""
        total_chars, total_errors = 0, 0
        for pred, ref in zip(predictions, references):
            errors = self._levenshtein_distance(pred, ref)
            total_errors += errors
            total_chars += len(ref)
        return total_errors / total_chars if total_chars > 0 else 0.0

    def _calculate_wer(self, predictions: List[str], references: List[str]) -> float:
        """Berechnet Word Error Rate."""
        total_words, total_errors = 0, 0
        for pred, ref in zip(predictions, references):
            pred_words, ref_words = pred.split(), ref.split()
            errors = self._levenshtein_distance(pred_words, ref_words)
            total_errors += errors
            total_words += len(ref_words)
        return total_errors / total_words if total_words > 0 else 0.0

    def _calculate_umlaut_accuracy(self, predictions: List[str], references: List[str]) -> float:
        """Berechnet Umlaut-spezifische Genauigkeit."""
        umlauts = set("äöüÄÖÜß")
        correct, total = 0, 0
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

    async def train(
        self,
        train_data_path: str,
        test_data_path: Optional[str] = None,
        resume_from_checkpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Führt das Training durch."""
        from transformers import Trainer

        if self.model is None:
            self.setup()

        train_dataset = SuryaOCRDataset(
            train_data_path, self.processor,
            max_length=self.config.max_seq_length, is_training=True
        )

        test_dataset = None
        if test_data_path and os.path.exists(test_data_path):
            test_dataset = SuryaOCRDataset(
                test_data_path, self.processor,
                max_length=self.config.max_seq_length, is_training=False
            )

        logger.info("Starte Training...")
        logger.info(f"  Epochs: {self.config.num_train_epochs}")
        logger.info(f"  Training Samples: {len(train_dataset)}")
        logger.info(f"  Test Samples: {len(test_dataset) if test_dataset else 0}")

        training_args = self._create_training_args()

        def data_collator(features: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
            batch = {}
            for key in features[0].keys():
                if features[0][key] is not None:
                    batch[key] = torch.stack([f[key] for f in features if f[key] is not None])
            return batch

        self.trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=test_dataset,
            data_collator=data_collator,
            compute_metrics=self._compute_metrics if test_dataset else None,
        )

        try:
            train_result = self.trainer.train(resume_from_checkpoint=resume_from_checkpoint)
            self.trainer.save_model()
            self.processor.save_pretrained(self.config.output_dir)

            metrics = train_result.metrics
            self.trainer.log_metrics("train", metrics)
            self.trainer.save_metrics("train", metrics)
            self.trainer.save_state()

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            return {
                "status": "completed",
                "train_loss": metrics.get("train_loss"),
                "train_runtime": metrics.get("train_runtime"),
                "train_samples_per_second": metrics.get("train_samples_per_second"),
                "output_dir": str(self.config.output_dir),
                "metrics_history": self._metrics_history[-50:]
            }

        except Exception as e:
            logger.exception("Training fehlgeschlagen")
            return {"status": "failed", "error": str(e)}

    async def run_test(self, test_data_path: str) -> SuryaTestMetrics:
        """Führt Test auf Daten durch."""
        import time

        if self.model is None:
            self.setup()

        test_dataset = SuryaOCRDataset(
            test_data_path, self.processor,
            max_length=self.config.max_seq_length, is_training=False
        )

        from torch.utils.data import DataLoader
        test_loader = DataLoader(
            test_dataset, batch_size=self.config.per_device_test_batch_size,
            shuffle=False, num_workers=0, pin_memory=True
        )

        self.model.train(False)  # Set to inference mode
        total_loss = 0.0
        all_predictions, all_references = [], []
        start_time = time.time()

        with torch.no_grad():
            for batch in test_loader:
                batch = {k: v.to(self.device) for k, v in batch.items() if v is not None}

                with torch.cuda.amp.autocast(enabled=self.config.fp16):
                    outputs = self.model(**batch)
                    if hasattr(outputs, "loss") and outputs.loss is not None:
                        total_loss += outputs.loss.item()

                if hasattr(outputs, "logits"):
                    pred_ids = outputs.logits.argmax(-1)
                else:
                    generated_ids = self.model.generate(
                        pixel_values=batch.get("pixel_values"),
                        max_new_tokens=self.config.max_seq_length,
                        do_sample=False
                    )
                    pred_ids = generated_ids

                predictions = self.processor.batch_decode(pred_ids, skip_special_tokens=True)

                if "labels" in batch:
                    labels = batch["labels"].clone()
                    labels[labels == -100] = self.processor.tokenizer.pad_token_id
                    references = self.processor.batch_decode(labels, skip_special_tokens=True)
                    all_references.extend(references)

                all_predictions.extend(predictions)

        total_time = time.time() - start_time
        avg_inference_time = (total_time * 1000) / len(test_dataset) if test_dataset else 0

        if all_references:
            cer = self._calculate_cer(all_predictions, all_references)
            wer = self._calculate_wer(all_predictions, all_references)
            umlaut_acc = self._calculate_umlaut_accuracy(all_predictions, all_references)
            exact_match = sum(
                1 for p, r in zip(all_predictions, all_references) if p.strip() == r.strip()
            ) / len(all_predictions) if all_predictions else 0.0
        else:
            cer = wer = 0.0
            umlaut_acc = exact_match = 1.0

        return SuryaTestMetrics(
            loss=total_loss / len(test_loader) if test_loader else 0.0,
            cer=cer, wer=wer, umlaut_accuracy=umlaut_acc,
            exact_match_ratio=exact_match, samples_count=len(all_predictions),
            avg_inference_time_ms=avg_inference_time
        )

    def save_model(self, output_path: str) -> str:
        """Speichert das Modell."""
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(output_path)
        self.processor.save_pretrained(output_path)

        config_file = output_path / "training_config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(vars(self.config), f, indent=2, ensure_ascii=False)

        metrics_file = output_path / "metrics_history.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(self._metrics_history, f, indent=2, ensure_ascii=False)

        logger.info(f"Modell gespeichert: {output_path}")
        return str(output_path)

    def load_model(self, model_path: str) -> None:
        """Lädt ein gespeichertes Modell."""
        from transformers import AutoModelForVision2Seq, AutoProcessor
        logger.info(f"Lade Modell: {model_path}")
        self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        self.model = AutoModelForVision2Seq.from_pretrained(
            model_path, trust_remote_code=True,
            torch_dtype=torch.float16 if self.config.fp16 else torch.float32
        )
        self.model.to(self.device)
        logger.info("Modell geladen")

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
