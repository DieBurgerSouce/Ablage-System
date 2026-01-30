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
class SuryaGermanConfig(SuryaTrainingConfig):
    """
    Optimierte Konfiguration für deutsches Fine-Tuning mit Umlaut-Fokus.

    Enterprise-Grade Konfiguration für deutsche Dokumente:
    - Umlaut-gewichtete Loss-Function (2x Penalty für ä, ö, ü, ß Fehler)
    - Focal Loss Option für schwierige Zeichen
    - Angepasste Learning Rate für Fine-Tuning
    - Frakturschrift-Unterstützung

    Zielmetriken:
    - CER: < 3%
    - WER: < 8%
    - Umlaut-Accuracy: 100%
    """

    # UMLAUT-FOKUS EINSTELLUNGEN
    umlaut_loss_weight: float = 2.0  # Höhere Strafe für Umlaut-Fehler
    eszett_loss_weight: float = 2.0  # Extra Gewicht für ß
    use_focal_loss: bool = True  # Focal Loss für schwierige Fälle
    focal_gamma: float = 2.0  # Focal Loss Gamma
    focal_alpha: float = 0.25  # Focal Loss Alpha
    label_smoothing: float = 0.1  # Label Smoothing für Robustheit
    confusion_penalty: float = 1.5  # Extra Strafe für typische Verwechslungen

    # Zeichen-spezifische Gewichte
    char_weights: Dict[str, float] = field(default_factory=lambda: {
        "ä": 2.0, "ö": 2.0, "ü": 2.0, "ß": 2.0,
        "Ä": 2.0, "Ö": 2.0, "Ü": 2.0,
    })

    # Deutsche Sprach-Einstellungen
    language: str = "de"
    detect_fraktur: bool = True
    german_dictionary: bool = True

    # Angepasste Training-Parameter für Deutsch
    num_train_epochs: int = 5
    learning_rate: float = 3e-5  # Etwas niedriger für Fine-Tuning
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4  # Effektive Batch Size: 16
    warmup_ratio: float = 0.15  # Längere Warmup-Phase
    fp16: bool = True

    # Output
    output_dir: str = "./models/finetuned/surya-german"
    metric_for_best_model: str = "umlaut_accuracy"
    greater_is_better: bool = True  # Höhere Umlaut-Accuracy ist besser

    @classmethod
    def create_default(cls) -> "SuryaGermanConfig":
        """Erstellt Standard-Konfiguration für deutsches Fine-Tuning."""
        return cls()

    @classmethod
    def create_aggressive_umlaut(cls) -> "SuryaGermanConfig":
        """Erstellt aggressive Konfiguration mit maximalem Umlaut-Fokus."""
        return cls(
            umlaut_loss_weight=3.0,
            eszett_loss_weight=3.0,
            use_focal_loss=True,
            focal_gamma=3.0,
            confusion_penalty=2.0,
            char_weights={
                "ä": 3.0, "ö": 3.0, "ü": 3.0, "ß": 3.0,
                "Ä": 3.0, "Ö": 3.0, "Ü": 3.0,
            },
            num_train_epochs=8,
            learning_rate=2e-5,
        )

    @classmethod
    def create_fraktur_focused(cls) -> "SuryaGermanConfig":
        """Erstellt Konfiguration optimiert für Frakturschrift."""
        return cls(
            detect_fraktur=True,
            umlaut_loss_weight=2.5,
            use_focal_loss=True,
            focal_gamma=2.5,
            num_train_epochs=10,
            learning_rate=2e-5,
            per_device_train_batch_size=2,  # Kleinere Batches für komplexe Layouts
            gradient_accumulation_steps=8,
        )

    @classmethod
    def create_quick_finetune(cls) -> "SuryaGermanConfig":
        """Erstellt schnelle Konfiguration für inkrementelles Training."""
        return cls(
            num_train_epochs=2,
            learning_rate=5e-5,
            use_focal_loss=False,
            save_steps=100,
            check_steps=50,
            logging_steps=25,
        )

    def get_umlaut_loss_config(self) -> Dict[str, Any]:
        """Gibt Konfiguration für UmlautWeightedCrossEntropy zurück."""
        return {
            "umlaut_weight": self.umlaut_loss_weight,
            "eszett_weight": self.eszett_loss_weight,
            "label_smoothing": self.label_smoothing,
            "confusion_penalty": self.confusion_penalty,
            "char_weights": self.char_weights,
        }

    def get_focal_loss_config(self) -> Dict[str, Any]:
        """Gibt Konfiguration für FocalUmlautLoss zurück."""
        return {
            "gamma": self.focal_gamma,
            "alpha": self.focal_alpha,
            "umlaut_weight": self.umlaut_loss_weight,
            "char_weights": self.char_weights,
        }


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
            return {"status": "failed", **safe_error_log(e)}

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


class SuryaGermanTrainer(SuryaOCRTrainer):
    """
    Spezialisierter Trainer für deutsches Fine-Tuning mit Umlaut-Fokus.

    Erweitert SuryaOCRTrainer um:
    - UmlautWeightedCrossEntropy Loss-Function
    - FocalUmlautLoss für schwierige Fälle
    - Verbesserte Umlaut-Metriken
    - Integration mit Feedback Learning

    Verwendung:
        trainer = SuryaGermanTrainer.create_default()
        result = await trainer.train("train.jsonl", "test.jsonl")
    """

    def __init__(
        self,
        config: Optional[SuryaGermanConfig] = None,
        device: Optional[str] = None
    ):
        """
        Initialisiert den German-spezialisierten Trainer.

        Args:
            config: SuryaGermanConfig für deutsches Training
            device: CUDA oder CPU Device
        """
        german_config = config or SuryaGermanConfig.create_default()
        super().__init__(
            model_name="vikp/surya_rec",
            config=german_config,
            device=device
        )
        self.german_config = german_config
        self._custom_loss = None
        logger.info(
            f"SuryaGermanTrainer initialisiert: "
            f"umlaut_weight={german_config.umlaut_loss_weight}, "
            f"focal_loss={german_config.use_focal_loss}"
        )

    @classmethod
    def create_default(cls) -> "SuryaGermanTrainer":
        """Erstellt Trainer mit Standard-Konfiguration."""
        return cls(config=SuryaGermanConfig.create_default())

    @classmethod
    def create_aggressive(cls) -> "SuryaGermanTrainer":
        """Erstellt Trainer mit aggressiver Umlaut-Konfiguration."""
        return cls(config=SuryaGermanConfig.create_aggressive_umlaut())

    @classmethod
    def create_for_fraktur(cls) -> "SuryaGermanTrainer":
        """Erstellt Trainer für Frakturschrift."""
        return cls(config=SuryaGermanConfig.create_fraktur_focused())

    @classmethod
    def create_quick(cls) -> "SuryaGermanTrainer":
        """Erstellt Trainer für schnelles inkrementelles Training."""
        return cls(config=SuryaGermanConfig.create_quick_finetune())

    def _setup_custom_loss(self) -> None:
        """Initialisiert die Umlaut-gewichtete Loss-Function."""
        try:
            from app.core.safe_errors import safe_error_log
            from app.ml.finetuning.umlaut_weighted_loss import (
                UmlautWeightedCrossEntropy,
                FocalUmlautLoss,
                UmlautLossConfig,
            )

            loss_config = UmlautLossConfig(
                umlaut_weight=self.german_config.umlaut_loss_weight,
                eszett_weight=self.german_config.eszett_loss_weight,
                label_smoothing=self.german_config.label_smoothing,
                confusion_penalty=self.german_config.confusion_penalty,
                char_weights=self.german_config.char_weights,
            )

            if self.german_config.use_focal_loss:
                self._custom_loss = FocalUmlautLoss(
                    gamma=self.german_config.focal_gamma,
                    alpha=self.german_config.focal_alpha,
                    umlaut_config=loss_config,
                )
                logger.info("FocalUmlautLoss aktiviert")
            else:
                self._custom_loss = UmlautWeightedCrossEntropy(config=loss_config)
                logger.info("UmlautWeightedCrossEntropy aktiviert")

            self._custom_loss.to(self.device)

        except ImportError as e:
            logger.warning(f"Umlaut-Loss nicht verfügbar, nutze Standard-Loss: {e}")
            self._custom_loss = None

    def setup(self) -> None:
        """Lädt Modell, Processor und Custom Loss."""
        super().setup()
        self._setup_custom_loss()

    async def train(
        self,
        train_data_path: str,
        test_data_path: Optional[str] = None,
        resume_from_checkpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Führt deutsches Fine-Tuning mit Umlaut-Fokus durch.

        Args:
            train_data_path: Pfad zu Training-JSONL
            test_data_path: Pfad zu Test-JSONL (optional)
            resume_from_checkpoint: Checkpoint zum Fortsetzen

        Returns:
            Training-Ergebnis mit Metriken
        """
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

        logger.info("Starte deutsches Fine-Tuning...")
        logger.info(f"  Epochs: {self.config.num_train_epochs}")
        logger.info(f"  Training Samples: {len(train_dataset)}")
        logger.info(f"  Umlaut-Gewicht: {self.german_config.umlaut_loss_weight}")
        logger.info(f"  Focal Loss: {self.german_config.use_focal_loss}")

        training_args = self._create_training_args()

        def data_collator(features: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
            batch = {}
            for key in features[0].keys():
                if features[0][key] is not None:
                    batch[key] = torch.stack([f[key] for f in features if f[key] is not None])
            return batch

        # Custom Trainer mit Umlaut-Loss
        class GermanOCRTrainer(Trainer):
            def __init__(self, custom_loss_fn=None, **kwargs):
                super().__init__(**kwargs)
                self._custom_loss_fn = custom_loss_fn

            def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
                labels = inputs.pop("labels", None)
                outputs = model(**inputs)

                if self._custom_loss_fn is not None and labels is not None:
                    logits = outputs.logits if hasattr(outputs, "logits") else outputs[0]
                    loss = self._custom_loss_fn(logits, labels)
                elif hasattr(outputs, "loss") and outputs.loss is not None:
                    loss = outputs.loss
                else:
                    from torch.nn import CrossEntropyLoss
                    logits = outputs.logits if hasattr(outputs, "logits") else outputs[0]
                    loss_fct = CrossEntropyLoss()
                    loss = loss_fct(
                        logits.view(-1, logits.size(-1)),
                        labels.view(-1)
                    )

                return (loss, outputs) if return_outputs else loss

        self.trainer = GermanOCRTrainer(
            custom_loss_fn=self._custom_loss,
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

            # Speichere German-spezifische Config
            german_config_file = Path(self.config.output_dir) / "german_config.json"
            with open(german_config_file, "w", encoding="utf-8") as f:
                config_dict = {
                    "umlaut_loss_weight": self.german_config.umlaut_loss_weight,
                    "eszett_loss_weight": self.german_config.eszett_loss_weight,
                    "use_focal_loss": self.german_config.use_focal_loss,
                    "focal_gamma": self.german_config.focal_gamma,
                    "char_weights": self.german_config.char_weights,
                    "language": self.german_config.language,
                    "detect_fraktur": self.german_config.detect_fraktur,
                }
                json.dump(config_dict, f, indent=2, ensure_ascii=False)

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            return {
                "status": "completed",
                "train_loss": metrics.get("train_loss"),
                "train_runtime": metrics.get("train_runtime"),
                "train_samples_per_second": metrics.get("train_samples_per_second"),
                "output_dir": str(self.config.output_dir),
                "german_config": {
                    "umlaut_weight": self.german_config.umlaut_loss_weight,
                    "focal_loss": self.german_config.use_focal_loss,
                },
                "metrics_history": self._metrics_history[-50:]
            }

        except Exception as e:
            logger.exception("Deutsches Fine-Tuning fehlgeschlagen")
            return {"status": "failed", **safe_error_log(e)}

    def _calculate_umlaut_accuracy(self, predictions: List[str], references: List[str]) -> float:
        """
        Erweiterte Umlaut-Genauigkeit mit Konfusions-Analyse.

        Prüft nicht nur exakte Übereinstimmung, sondern auch:
        - Position-basierte Genauigkeit
        - Verwechslungs-Erkennung (ä→a, ö→o, etc.)
        """
        umlauts = set("äöüÄÖÜß")
        correct, total = 0, 0
        confusion_counts: Dict[str, Dict[str, int]] = {u: {} for u in umlauts}

        for pred, ref in zip(predictions, references):
            for i, char in enumerate(ref):
                if char in umlauts:
                    total += 1
                    if i < len(pred):
                        pred_char = pred[i]
                        if pred_char == char:
                            correct += 1
                        else:
                            # Track confusion
                            if pred_char not in confusion_counts[char]:
                                confusion_counts[char][pred_char] = 0
                            confusion_counts[char][pred_char] += 1

        # Log top confusions
        for umlaut, confusions in confusion_counts.items():
            if confusions:
                top_confusion = max(confusions.items(), key=lambda x: x[1])
                if top_confusion[1] > 5:  # Nur signifikante Verwechslungen
                    logger.debug(
                        f"Umlaut-Verwechslung: {umlaut} → {top_confusion[0]} "
                        f"({top_confusion[1]} mal)"
                    )

        return correct / total if total > 0 else 1.0

    async def evaluate_umlaut_performance(
        self,
        test_data_path: str
    ) -> Dict[str, Any]:
        """
        Detaillierte Umlaut-Performance-Analyse.

        Returns:
            Detaillierte Metriken pro Umlaut-Zeichen
        """
        if self.model is None:
            self.setup()

        test_dataset = SuryaOCRDataset(
            test_data_path, self.processor,
            max_length=self.config.max_seq_length, is_training=False
        )

        from torch.utils.data import DataLoader
        test_loader = DataLoader(
            test_dataset, batch_size=self.config.per_device_test_batch_size,
            shuffle=False, num_workers=0
        )

        self.model.train(False)
        umlauts = list("äöüÄÖÜß")
        per_char_stats = {u: {"correct": 0, "total": 0, "confusions": {}} for u in umlauts}

        with torch.no_grad():
            for batch in test_loader:
                batch = {k: v.to(self.device) for k, v in batch.items() if v is not None}

                with torch.cuda.amp.autocast(enabled=self.config.fp16):
                    if hasattr(self.model, "generate"):
                        generated_ids = self.model.generate(
                            pixel_values=batch.get("pixel_values"),
                            max_new_tokens=self.config.max_seq_length,
                            do_sample=False
                        )
                        pred_ids = generated_ids
                    else:
                        outputs = self.model(**batch)
                        pred_ids = outputs.logits.argmax(-1)

                predictions = self.processor.batch_decode(pred_ids, skip_special_tokens=True)

                if "labels" in batch:
                    labels = batch["labels"].clone()
                    labels[labels == -100] = self.processor.tokenizer.pad_token_id
                    references = self.processor.batch_decode(labels, skip_special_tokens=True)

                    # Analysiere jedes Zeichen
                    for pred, ref in zip(predictions, references):
                        for i, char in enumerate(ref):
                            if char in umlauts:
                                per_char_stats[char]["total"] += 1
                                if i < len(pred):
                                    pred_char = pred[i]
                                    if pred_char == char:
                                        per_char_stats[char]["correct"] += 1
                                    else:
                                        if pred_char not in per_char_stats[char]["confusions"]:
                                            per_char_stats[char]["confusions"][pred_char] = 0
                                        per_char_stats[char]["confusions"][pred_char] += 1

        # Berechne Statistiken
        results = {
            "overall_umlaut_accuracy": 0.0,
            "per_character": {},
            "total_umlauts": 0,
            "correct_umlauts": 0,
        }

        total_correct = 0
        total_count = 0

        for char, stats in per_char_stats.items():
            total = stats["total"]
            correct = stats["correct"]
            total_correct += correct
            total_count += total

            accuracy = correct / total if total > 0 else 1.0
            top_confusions = sorted(
                stats["confusions"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]

            results["per_character"][char] = {
                "accuracy": accuracy,
                "total": total,
                "correct": correct,
                "top_confusions": top_confusions,
            }

        results["overall_umlaut_accuracy"] = total_correct / total_count if total_count > 0 else 1.0
        results["total_umlauts"] = total_count
        results["correct_umlauts"] = total_correct

        logger.info(f"Umlaut-Performance: {results['overall_umlaut_accuracy']:.2%}")
        return results
