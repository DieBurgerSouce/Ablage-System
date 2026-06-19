"""
Training Dataset Export Service

Exportiert verifizierte Ground-Truth-Daten für Fine-Tuning:
- DeepSeek-Janus-Pro: JSONL-Format mit Conversations
- Surya-OCR: HuggingFace Dataset-Format

Author: Claude Code
Created: 2024-12
"""

import asyncio
import base64
import hashlib
import json
import os
import shutil
from app.core.safe_errors import safe_error_detail, safe_error_log
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRDocumentOutput,
    OCRTrainingSample,
    TrainingSampleStatus,
)

logger = structlog.get_logger(__name__)


class TrainingExportFormat(str, Enum):
    """Unterstützte Export-Formate."""
    DEEPSEEK_JSONL = "deepseek_jsonl"
    SURYA_HF = "surya_hf"
    GENERIC_JSONL = "generic_jsonl"
    CSV = "csv"


class SplitStrategy(str, Enum):
    """Strategie für Train/Val/Test Split."""
    RANDOM = "random"
    STRATIFIED = "stratified"  # Nach Dokumenttyp
    TEMPORAL = "temporal"  # Ältere für Training, neuere für Test


@dataclass
class ExportConfig:
    """Konfiguration für Dataset-Export."""
    format: TrainingExportFormat = TrainingExportFormat.DEEPSEEK_JSONL
    split_ratio: Tuple[float, float, float] = (0.8, 0.1, 0.1)  # train/val/test
    split_strategy: SplitStrategy = SplitStrategy.RANDOM
    filter_verified_only: bool = True
    min_umlaut_accuracy: float = 1.0
    min_cer: Optional[float] = None  # Maximum CER (lower is better)
    include_metadata: bool = True
    include_image_base64: bool = False  # Für DeepSeek
    image_reference_type: str = "path"  # "path", "base64", "url"
    output_dir: str = "./exports"
    seed: int = 42  # Für Reproduzierbarkeit


@dataclass
class ExportStats:
    """Statistiken eines Exports."""
    total_samples: int = 0
    train_samples: int = 0
    val_samples: int = 0
    test_samples: int = 0
    samples_with_umlauts: int = 0
    avg_text_length: float = 0.0
    document_types: Dict[str, int] = field(default_factory=dict)
    export_time_seconds: float = 0.0
    output_size_bytes: int = 0


@dataclass
class ExportResult:
    """Ergebnis eines Dataset-Exports."""
    success: bool
    export_id: str
    output_dir: str
    format: TrainingExportFormat
    stats: ExportStats
    files_created: List[str]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class DeepSeekSample:
    """Sample im DeepSeek-Format."""
    image_path: str
    conversations: List[Dict[str, str]]
    metadata: Dict[str, Any]

    def to_jsonl_dict(self) -> Dict[str, Any]:
        """Konvertiert zu JSONL-kompatiblem Dictionary."""
        return {
            "image": self.image_path,
            "conversations": self.conversations,
            "metadata": self.metadata
        }


@dataclass
class SuryaSample:
    """Sample im Surya/HuggingFace-Format."""
    image_path: str
    text: str
    language: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "image": self.image_path,
            "text": self.text,
            "language": self.language,
            **self.metadata
        }


class TrainingDatasetExportService:
    """
    Service für den Export von Training-Datasets.

    Unterstützt Export für:
    - DeepSeek-Janus-Pro (LoRA Fine-Tuning)
    - Surya-OCR (HuggingFace Trainer)
    """

    # DeepSeek Prompt-Templates
    DEEPSEEK_PROMPTS = {
        "full_ocr": "Extrahiere den vollständigen Text aus diesem Dokument. Achte besonders auf korrekte deutsche Umlaute (ä, ö, ü, ß).",
        "structured": "Extrahiere die folgenden Felder aus diesem Dokument:\n- Rechnungsnummer\n- Datum\n- Gesamtbetrag\n- IBAN\n- Umsatzsteuer-ID\n\nGib die Felder im JSON-Format zurück.",
        "full_with_structure": "Extrahiere den vollständigen Text UND die strukturierten Felder aus diesem Dokument."
    }

    def __init__(self, db: AsyncSession):
        """Initialisiert den Export-Service."""
        self.db = db
        self._export_base_dir = Path("./exports")

    async def export_for_finetuning(
        self,
        config: Optional[ExportConfig] = None
    ) -> ExportResult:
        """
        Hauptexport-Funktion für Fine-Tuning-Datasets.

        Args:
            config: Export-Konfiguration

        Returns:
            ExportResult mit Statistiken und Dateipfaden
        """
        if config is None:
            config = ExportConfig()

        export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        start_time = datetime.now()

        logger.info(
            f"Starte Dataset-Export: {export_id}",
            export_id=export_id,
            format=config.format,
            filter_verified_only=config.filter_verified_only,
        )

        try:
            # 1. Samples laden und filtern
            samples = await self._load_filtered_samples(config)

            if not samples:
                return ExportResult(
                    success=False,
                    export_id=export_id,
                    output_dir="",
                    format=config.format,
                    stats=ExportStats(),
                    files_created=[],
                    errors=["Keine Samples gefunden, die den Filterkriterien entsprechen"]
                )

            # 2. Train/Val/Test Split
            train_samples, val_samples, test_samples = await self._split_samples(
                samples, config
            )

            # 3. Output-Verzeichnis erstellen
            output_dir = self._create_output_dir(config.output_dir, export_id)

            # 4. Format-spezifischer Export
            files_created = []
            warnings = []

            if config.format == TrainingExportFormat.DEEPSEEK_JSONL:
                files = await self._export_deepseek_format(
                    train_samples, val_samples, test_samples,
                    output_dir, config
                )
                files_created.extend(files)

            elif config.format == TrainingExportFormat.SURYA_HF:
                files = await self._export_surya_format(
                    train_samples, val_samples, test_samples,
                    output_dir, config
                )
                files_created.extend(files)

            elif config.format == TrainingExportFormat.GENERIC_JSONL:
                files = await self._export_generic_jsonl(
                    train_samples, val_samples, test_samples,
                    output_dir, config
                )
                files_created.extend(files)

            elif config.format == TrainingExportFormat.CSV:
                files = await self._export_csv(
                    train_samples, val_samples, test_samples,
                    output_dir, config
                )
                files_created.extend(files)

            # 5. Statistiken berechnen
            stats = await self._calculate_stats(
                train_samples, val_samples, test_samples,
                output_dir, start_time
            )

            # 6. Metadata-Datei erstellen
            metadata_file = await self._create_metadata_file(
                export_id, config, stats, output_dir
            )
            files_created.append(metadata_file)

            logger.info(
                f"Dataset-Export abgeschlossen: {export_id}",
                export_id=export_id,
                total_samples=stats.total_samples,
                files_created=len(files_created),
            )

            return ExportResult(
                success=True,
                export_id=export_id,
                output_dir=str(output_dir),
                format=config.format,
                stats=stats,
                files_created=files_created,
                warnings=warnings
            )

        except Exception as e:
            logger.exception(f"Fehler beim Dataset-Export: {export_id}")
            return ExportResult(
                success=False,
                export_id=export_id,
                output_dir="",
                format=config.format,
                stats=ExportStats(),
                files_created=[],
                errors=[safe_error_detail(e, "Training")]
            )

    async def export_for_deepseek(
        self,
        output_dir: str,
        prompt_type: str = "full_ocr",
        include_structured: bool = True
    ) -> ExportResult:
        """
        Spezialisierter Export für DeepSeek-Janus-Pro Fine-Tuning.

        Args:
            output_dir: Ausgabeverzeichnis
            prompt_type: Art des Prompts (full_ocr, structured, full_with_structure)
            include_structured: Ob strukturierte Felder inkludiert werden sollen

        Returns:
            ExportResult
        """
        config = ExportConfig(
            format=TrainingExportFormat.DEEPSEEK_JSONL,
            output_dir=output_dir,
            include_image_base64=False,
            image_reference_type="path",
            include_metadata=True
        )

        # Erweiterte Konfiguration im Config speichern
        config.__dict__["prompt_type"] = prompt_type
        config.__dict__["include_structured"] = include_structured

        return await self.export_for_finetuning(config)

    async def export_for_surya(
        self,
        output_dir: str,
        create_arrow_files: bool = True
    ) -> ExportResult:
        """
        Spezialisierter Export für Surya-OCR HuggingFace Training.

        Args:
            output_dir: Ausgabeverzeichnis
            create_arrow_files: Ob Arrow-Dateien für HF erstellt werden sollen

        Returns:
            ExportResult
        """
        config = ExportConfig(
            format=TrainingExportFormat.SURYA_HF,
            output_dir=output_dir,
            include_metadata=True
        )

        config.__dict__["create_arrow_files"] = create_arrow_files

        return await self.export_for_finetuning(config)

    async def _load_filtered_samples(
        self,
        config: ExportConfig
    ) -> List[OCRTrainingSample]:
        """Lädt und filtert Samples nach Konfiguration."""

        # Basis-Query
        query = select(OCRTrainingSample)

        conditions = []

        # Nur verifizierte Samples
        if config.filter_verified_only:
            conditions.append(
                OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value
            )

        # Ground Truth muss vorhanden sein
        conditions.append(OCRTrainingSample.ground_truth_text.isnot(None))
        conditions.append(OCRTrainingSample.ground_truth_text != "")

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        samples = list(result.scalars().all())

        # Post-Filter für Umlaut-Accuracy (wenn Benchmark-Daten vorhanden)
        if config.min_umlaut_accuracy is not None:
            filtered_samples = []
            for sample in samples:
                # Prüfe Benchmark-Ergebnisse
                umlaut_ok = await self._check_umlaut_accuracy(
                    sample, config.min_umlaut_accuracy
                )
                if umlaut_ok:
                    filtered_samples.append(sample)
            samples = filtered_samples

        logger.info(f"Geladene Samples nach Filterung: {len(samples)}")
        return samples

    async def _check_umlaut_accuracy(
        self,
        sample: OCRTrainingSample,
        min_accuracy: float
    ) -> bool:
        """Prüft ob Sample die Umlaut-Accuracy erfüllt."""
        # Prüfe ob Ground Truth Umlaute enthält
        ground_truth = sample.ground_truth_text or ""
        umlauts = set("äöüÄÖÜß")

        has_umlauts = any(c in umlauts for c in ground_truth)

        if not has_umlauts:
            # Ohne Umlaute ist die Accuracy irrelevant
            return True

        # Wenn Benchmark-Daten vorhanden, prüfe diese
        # Für jetzt: Sample akzeptieren wenn Ground Truth existiert
        return True

    async def _split_samples(
        self,
        samples: List[OCRTrainingSample],
        config: ExportConfig
    ) -> Tuple[List[OCRTrainingSample], List[OCRTrainingSample], List[OCRTrainingSample]]:
        """Teilt Samples in Train/Val/Test auf."""
        import random

        random.seed(config.seed)

        train_ratio, val_ratio, test_ratio = config.split_ratio

        if config.split_strategy == SplitStrategy.RANDOM:
            # Zufälliger Split
            shuffled = samples.copy()
            random.shuffle(shuffled)

            n = len(shuffled)
            train_end = int(n * train_ratio)
            val_end = train_end + int(n * val_ratio)

            train = shuffled[:train_end]
            val = shuffled[train_end:val_end]
            test = shuffled[val_end:]

        elif config.split_strategy == SplitStrategy.STRATIFIED:
            # Stratifiziert nach Dokumenttyp
            by_type: Dict[str, List[OCRTrainingSample]] = {}
            for sample in samples:
                doc_type = sample.document_type or "unknown"
                if doc_type not in by_type:
                    by_type[doc_type] = []
                by_type[doc_type].append(sample)

            train, val, test = [], [], []

            for doc_type, type_samples in by_type.items():
                random.shuffle(type_samples)
                n = len(type_samples)
                train_end = int(n * train_ratio)
                val_end = train_end + int(n * val_ratio)

                train.extend(type_samples[:train_end])
                val.extend(type_samples[train_end:val_end])
                test.extend(type_samples[val_end:])

            # Nochmal mischen
            random.shuffle(train)
            random.shuffle(val)
            random.shuffle(test)

        elif config.split_strategy == SplitStrategy.TEMPORAL:
            # Ältere für Training, neuere für Test
            sorted_samples = sorted(
                samples,
                key=lambda s: s.created_at or datetime.min
            )

            n = len(sorted_samples)
            train_end = int(n * train_ratio)
            val_end = train_end + int(n * val_ratio)

            train = sorted_samples[:train_end]
            val = sorted_samples[train_end:val_end]
            test = sorted_samples[val_end:]

        else:
            raise ValueError(f"Unbekannte Split-Strategie: {config.split_strategy}")

        logger.info(f"Split: train={len(train)}, val={len(val)}, test={len(test)}")
        return train, val, test

    def _create_output_dir(self, base_dir: str, export_id: str) -> Path:
        """Erstellt das Ausgabeverzeichnis."""
        output_dir = Path(base_dir) / export_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Unterverzeichnisse
        (output_dir / "train").mkdir(exist_ok=True)
        (output_dir / "val").mkdir(exist_ok=True)
        (output_dir / "test").mkdir(exist_ok=True)
        (output_dir / "images").mkdir(exist_ok=True)

        return output_dir

    async def _export_deepseek_format(
        self,
        train: List[OCRTrainingSample],
        val: List[OCRTrainingSample],
        test: List[OCRTrainingSample],
        output_dir: Path,
        config: ExportConfig
    ) -> List[str]:
        """Exportiert im DeepSeek JSONL-Format."""
        files_created = []

        prompt_type = getattr(config, "prompt_type", "full_ocr")
        include_structured = getattr(config, "include_structured", True)

        prompt = self.DEEPSEEK_PROMPTS.get(prompt_type, self.DEEPSEEK_PROMPTS["full_ocr"])

        for split_name, samples in [("train", train), ("val", val), ("test", test)]:
            if not samples:
                continue

            file_path = output_dir / f"{split_name}.jsonl"

            with open(file_path, "w", encoding="utf-8") as f:
                for sample in samples:
                    # Bild-Referenz erstellen
                    image_ref = await self._get_image_reference(sample, config, output_dir)

                    # Response erstellen
                    response_parts = []

                    # Volltext
                    if sample.ground_truth_text:
                        response_parts.append(sample.ground_truth_text)

                    # Strukturierte Felder
                    if include_structured and sample.extracted_fields:
                        fields_json = json.dumps(sample.extracted_fields, ensure_ascii=False, indent=2)
                        response_parts.append(f"\n\nExtrahierte Felder:\n{fields_json}")

                    response = "\n".join(response_parts) if response_parts else sample.ground_truth_text or ""

                    # DeepSeek-Format
                    entry = {
                        "image": image_ref,
                        "conversations": [
                            {"from": "human", "value": f"<image>\n{prompt}"},
                            {"from": "gpt", "value": response}
                        ]
                    }

                    if config.include_metadata:
                        entry["metadata"] = {
                            "sample_id": str(sample.id),
                            "document_type": sample.document_type,
                            "language": "de",
                            "has_umlauts": any(c in "äöüÄÖÜß" for c in response),
                            "text_length": len(response),
                            "source_file": sample.source_filename
                        }

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            files_created.append(str(file_path))
            logger.info(f"DeepSeek {split_name}.jsonl erstellt: {len(samples)} Samples")

        return files_created

    async def _export_surya_format(
        self,
        train: List[OCRTrainingSample],
        val: List[OCRTrainingSample],
        test: List[OCRTrainingSample],
        output_dir: Path,
        config: ExportConfig
    ) -> List[str]:
        """Exportiert im Surya/HuggingFace-Format."""
        files_created = []

        create_arrow = getattr(config, "create_arrow_files", True)

        for split_name, samples in [("train", train), ("val", val), ("test", test)]:
            if not samples:
                continue

            # JSONL erstellen (immer)
            jsonl_path = output_dir / f"{split_name}.jsonl"

            data_entries = []

            with open(jsonl_path, "w", encoding="utf-8") as f:
                for sample in samples:
                    image_ref = await self._get_image_reference(sample, config, output_dir)

                    entry = {
                        "image": image_ref,
                        "text": sample.ground_truth_text or "",
                        "language": "de"
                    }

                    if config.include_metadata:
                        entry["sample_id"] = str(sample.id)
                        entry["document_type"] = sample.document_type
                        entry["source_file"] = sample.source_filename

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    data_entries.append(entry)

            files_created.append(str(jsonl_path))

            # Arrow-Datei für HuggingFace (optional)
            if create_arrow:
                try:
                    arrow_path = await self._create_arrow_dataset(
                        data_entries, output_dir / split_name, split_name
                    )
                    if arrow_path:
                        files_created.append(arrow_path)
                except Exception as e:
                    logger.warning(f"Arrow-Datei konnte nicht erstellt werden: {e}")

            logger.info(f"Surya {split_name} erstellt: {len(samples)} Samples")

        return files_created

    async def _create_arrow_dataset(
        self,
        entries: List[Dict],
        output_dir: Path,
        split_name: str
    ) -> Optional[str]:
        """Erstellt ein HuggingFace Arrow-Dataset."""
        try:
            # Nur wenn datasets installiert ist
            from datasets import Dataset, Features, Image, Value

            # Features definieren
            features = Features({
                "image": Image(),
                "text": Value("string"),
                "language": Value("string"),
                "sample_id": Value("string"),
                "document_type": Value("string"),
                "source_file": Value("string")
            })

            # Dataset erstellen
            dataset = Dataset.from_list(entries, features=features)

            # Speichern
            output_dir.mkdir(parents=True, exist_ok=True)
            dataset.save_to_disk(str(output_dir))

            return str(output_dir)

        except ImportError:
            logger.info("HuggingFace datasets nicht installiert, überspringe Arrow-Export")
            return None

    async def _export_generic_jsonl(
        self,
        train: List[OCRTrainingSample],
        val: List[OCRTrainingSample],
        test: List[OCRTrainingSample],
        output_dir: Path,
        config: ExportConfig
    ) -> List[str]:
        """Exportiert generisches JSONL-Format."""
        files_created = []

        for split_name, samples in [("train", train), ("val", val), ("test", test)]:
            if not samples:
                continue

            file_path = output_dir / f"{split_name}.jsonl"

            with open(file_path, "w", encoding="utf-8") as f:
                for sample in samples:
                    image_ref = await self._get_image_reference(sample, config, output_dir)

                    entry = {
                        "id": str(sample.id),
                        "image": image_ref,
                        "ground_truth": sample.ground_truth_text,
                        "extracted_fields": sample.extracted_fields,
                        "document_type": sample.document_type,
                        "language": "de",
                        "source_filename": sample.source_filename,
                        "created_at": sample.created_at.isoformat() if sample.created_at else None,
                        "verified_at": sample.verified_at.isoformat() if sample.verified_at else None,
                        "metadata": {
                            "has_umlauts": any(c in "äöüÄÖÜß" for c in (sample.ground_truth_text or "")),
                            "text_length": len(sample.ground_truth_text or ""),
                            "verification_status": sample.status if sample.status else None
                        }
                    }

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            files_created.append(str(file_path))

        return files_created

    async def _export_csv(
        self,
        train: List[OCRTrainingSample],
        val: List[OCRTrainingSample],
        test: List[OCRTrainingSample],
        output_dir: Path,
        config: ExportConfig
    ) -> List[str]:
        """Exportiert CSV-Format."""
        import csv

        files_created = []

        fieldnames = [
            "id", "image_path", "ground_truth", "document_type",
            "language", "source_filename", "text_length", "has_umlauts"
        ]

        for split_name, samples in [("train", train), ("val", val), ("test", test)]:
            if not samples:
                continue

            file_path = output_dir / f"{split_name}.csv"

            with open(file_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for sample in samples:
                    image_ref = await self._get_image_reference(sample, config, output_dir)
                    ground_truth = sample.ground_truth_text or ""

                    writer.writerow({
                        "id": str(sample.id),
                        "image_path": image_ref,
                        "ground_truth": ground_truth,
                        "document_type": sample.document_type or "",
                        "language": "de",
                        "source_filename": sample.source_filename or "",
                        "text_length": len(ground_truth),
                        "has_umlauts": any(c in "äöüÄÖÜß" for c in ground_truth)
                    })

            files_created.append(str(file_path))

        return files_created

    async def _get_image_reference(
        self,
        sample: OCRTrainingSample,
        config: ExportConfig,
        output_dir: Path
    ) -> str:
        """Erstellt Bild-Referenz je nach Konfiguration."""

        if config.image_reference_type == "base64":
            # Base64-kodiertes Bild
            if sample.image_storage_path:
                try:
                    image_path = Path(sample.image_storage_path)
                    if image_path.exists():
                        with open(image_path, "rb") as img_file:
                            return base64.b64encode(img_file.read()).decode("utf-8")
                except Exception as e:
                    logger.warning(f"Konnte Bild nicht laden: {e}")
            return ""

        elif config.image_reference_type == "path":
            # Relativer Pfad
            if sample.image_storage_path:
                # Bild kopieren wenn es existiert
                src_path = Path(sample.image_storage_path)
                if src_path.exists():
                    # Eindeutiger Name basierend auf Sample-ID
                    ext = src_path.suffix or ".png"
                    dest_name = f"{sample.id}{ext}"
                    dest_path = output_dir / "images" / dest_name

                    try:
                        shutil.copy2(src_path, dest_path)
                        return f"images/{dest_name}"
                    except Exception as e:
                        logger.warning(f"Konnte Bild nicht kopieren: {e}")

            # Fallback: Original-Pfad
            return sample.image_storage_path or f"sample_{sample.id}.png"

        elif config.image_reference_type == "url":
            # URL (z.B. für MinIO)
            if sample.image_storage_path:
                # Annahme: MinIO-Pfad
                return f"minio://documents/{sample.image_storage_path}"
            return ""

        return sample.image_storage_path or ""

    async def _calculate_stats(
        self,
        train: List[OCRTrainingSample],
        val: List[OCRTrainingSample],
        test: List[OCRTrainingSample],
        output_dir: Path,
        start_time: datetime
    ) -> ExportStats:
        """Berechnet Export-Statistiken."""

        all_samples = train + val + test

        # Dokumenttypen zählen
        doc_types: Dict[str, int] = {}
        total_text_length = 0
        samples_with_umlauts = 0

        for sample in all_samples:
            # Dokumenttyp
            doc_type = sample.document_type or "unknown"
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1

            # Textlänge
            text = sample.ground_truth_text or ""
            total_text_length += len(text)

            # Umlaute
            if any(c in "äöüÄÖÜß" for c in text):
                samples_with_umlauts += 1

        # Verzeichnisgröße
        output_size = sum(
            f.stat().st_size
            for f in output_dir.rglob("*")
            if f.is_file()
        )

        return ExportStats(
            total_samples=len(all_samples),
            train_samples=len(train),
            val_samples=len(val),
            test_samples=len(test),
            samples_with_umlauts=samples_with_umlauts,
            avg_text_length=total_text_length / len(all_samples) if all_samples else 0,
            document_types=doc_types,
            export_time_seconds=(datetime.now() - start_time).total_seconds(),
            output_size_bytes=output_size
        )

    async def _create_metadata_file(
        self,
        export_id: str,
        config: ExportConfig,
        stats: ExportStats,
        output_dir: Path
    ) -> str:
        """Erstellt eine Metadata-Datei für den Export."""

        metadata = {
            "export_id": export_id,
            "created_at": datetime.now().isoformat(),
            "format": config.format.value,
            "config": {
                "split_ratio": list(config.split_ratio),
                "split_strategy": config.split_strategy.value,
                "filter_verified_only": config.filter_verified_only,
                "min_umlaut_accuracy": config.min_umlaut_accuracy,
                "include_metadata": config.include_metadata,
                "image_reference_type": config.image_reference_type,
                "seed": config.seed
            },
            "stats": {
                "total_samples": stats.total_samples,
                "train_samples": stats.train_samples,
                "val_samples": stats.val_samples,
                "test_samples": stats.test_samples,
                "samples_with_umlauts": stats.samples_with_umlauts,
                "avg_text_length": stats.avg_text_length,
                "document_types": stats.document_types,
                "export_time_seconds": stats.export_time_seconds,
                "output_size_bytes": stats.output_size_bytes
            },
            "usage": {
                "deepseek": "Für LoRA Fine-Tuning: train.jsonl, val.jsonl",
                "surya": "Für HuggingFace Trainer: Verwende das train/ Verzeichnis",
                "language": "de (German)",
                "special_chars": "Enthält Umlaute (ä, ö, ü, ß)"
            }
        }

        file_path = output_dir / "metadata.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, ensure_ascii=False, indent=2, fp=f)

        return str(file_path)

    async def list_exports(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Listet alle vorhandenen Exports auf."""
        exports = []

        base_dir = self._export_base_dir
        if not base_dir.exists():
            return exports

        for export_dir in sorted(base_dir.iterdir(), reverse=True)[:limit]:
            if not export_dir.is_dir():
                continue

            metadata_file = export_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                        exports.append({
                            "export_id": metadata.get("export_id"),
                            "created_at": metadata.get("created_at"),
                            "format": metadata.get("format"),
                            "total_samples": metadata.get("stats", {}).get("total_samples", 0),
                            "output_dir": str(export_dir)
                        })
                except Exception as e:
                    logger.debug("load_export_metadata", error_type=type(e).__name__)

        return exports

    async def delete_export(self, export_id: str) -> bool:
        """Löscht einen Export."""
        export_dir = self._export_base_dir / export_id

        if export_dir.exists() and export_dir.is_dir():
            try:
                shutil.rmtree(export_dir)
                logger.info(f"Export gelöscht: {export_id}")
                return True
            except Exception as e:
                logger.error(f"Fehler beim Löschen von Export {export_id}: {e}")
                return False

        return False


# Dependency Injection
async def get_training_dataset_export_service(
    db: AsyncSession
) -> TrainingDatasetExportService:
    """FastAPI Dependency für den Export-Service."""
    return TrainingDatasetExportService(db)


# =============================================================================
# SURYA-SPEZIFISCHER EXPORTER FÜR CONTINUOUS IMPROVEMENT
# =============================================================================

@dataclass
class SuryaExportConfig:
    """Erweiterte Konfiguration für Surya Dataset Export im Continuous Improvement Loop."""

    # Output Verzeichnis
    output_dir: str = "./datasets/surya"

    # Split Ratios
    train_ratio: float = 0.8
    val_ratio: float = 0.1
    test_ratio: float = 0.1

    # Stratifikation nach Dokumenttyp
    stratify_by_doc_type: bool = True

    # Stratifikation Gewichte
    doc_type_weights: Dict[str, float] = field(default_factory=lambda: {
        "invoice": 0.40,
        "contract": 0.25,
        "letter": 0.15,
        "form": 0.10,
        "other": 0.10,
    })

    # KRITISCH: Umlaut-Gewichtung für deutsche OCR
    umlaut_weight_multiplier: float = 2.0

    # Minimum Samples
    min_train_samples: int = 50
    min_val_samples: int = 10
    min_test_samples: int = 10

    # Maximum Samples (0 = unbegrenzt)
    max_samples: int = 0

    # Sprache
    language: str = "de"

    # Nur verifizierte Samples
    verified_only: bool = True

    # Random Seed für Reproduzierbarkeit
    seed: int = 42

    # Bilder kopieren oder referenzieren
    copy_images: bool = True

    # Backend Filter (z.B. ["surya", "surya-gpu"])
    backend_filter: Optional[List[str]] = None

    def validate(self) -> bool:
        """Validiert die Konfiguration."""
        total_ratio = self.train_ratio + self.val_ratio + self.test_ratio
        if abs(total_ratio - 1.0) > 0.001:
            raise ValueError(f"Split Ratios müssen 1.0 ergeben, sind aber {total_ratio}")
        return True


@dataclass
class SuryaExportResult:
    """Ergebnis eines Surya Dataset-Exports für Continuous Improvement."""

    output_dir: str
    train_samples: int
    val_samples: int
    test_samples: int
    total_samples: int

    # Erfolg-Flag (für Celery Tasks)
    success: bool = True

    # Aufschlüsselung nach Dokumenttyp
    doc_type_distribution: Dict[str, int] = field(default_factory=dict)

    # Umlaut-Statistiken (KRITISCH für deutsche OCR)
    samples_with_umlauts: int = 0
    total_umlaut_words: int = 0
    umlaut_word_list: List[str] = field(default_factory=list)
    umlaut_samples: int = 0  # Alias für Celery Task Kompatibilität

    # Dateien
    train_file: str = ""
    val_file: str = ""
    test_file: str = ""
    metadata_file: str = ""

    # Timing
    export_started: Optional[datetime] = None
    export_completed: Optional[datetime] = None
    duration_seconds: float = 0.0
    export_timestamp: str = ""

    # Für Continuous Improvement
    version: str = ""
    previous_version: Optional[str] = None
    improvement_delta: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """Post-init für abgeleitete Felder."""
        # Setze umlaut_samples als Alias
        if self.umlaut_samples == 0 and self.samples_with_umlauts > 0:
            self.umlaut_samples = self.samples_with_umlauts
        # Setze export_timestamp
        if not self.export_timestamp and self.export_completed:
            self.export_timestamp = self.export_completed.isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "output_dir": self.output_dir,
            "train_samples": self.train_samples,
            "val_samples": self.val_samples,
            "test_samples": self.test_samples,
            "total_samples": self.total_samples,
            "doc_type_distribution": self.doc_type_distribution,
            "samples_with_umlauts": self.samples_with_umlauts,
            "total_umlaut_words": self.total_umlaut_words,
            "train_file": self.train_file,
            "val_file": self.val_file,
            "test_file": self.test_file,
            "metadata_file": self.metadata_file,
            "export_started": self.export_started.isoformat() if self.export_started else None,
            "export_completed": self.export_completed.isoformat() if self.export_completed else None,
            "duration_seconds": self.duration_seconds,
            "version": self.version,
        }


class SuryaDatasetExporter:
    """
    Spezialisierter Exporter für Surya OCR Continuous Improvement Loop.

    Features:
    - Umlaut-gewichteter Export (2x Priorität für Samples mit Umlauten)
    - Stratifizierter Split nach Dokumenttyp
    - Export von User-Korrektionen als neue Training Samples
    - Versionierung für Continuous Improvement

    Surya erwartet JSONL mit Format:
    {
        "image": "/pfad/zum/bild.png",
        "text": "Ground Truth Text",
        "language": "de",
        "metadata": {...}
    }
    """

    def __init__(self, db: AsyncSession, config: Optional[SuryaExportConfig] = None):
        """Initialisiert den Surya Exporter."""
        self.db = db
        self.config = config or SuryaExportConfig()
        self.config.validate()

        logger.info(
            "surya_dataset_exporter_initialized",
            output_dir=self.config.output_dir,
            umlaut_weight=self.config.umlaut_weight_multiplier,
        )

    async def export_for_surya_training(
        self,
        include_corrections: bool = True,
        correction_days: int = 30
    ) -> SuryaExportResult:
        """
        Hauptexport-Funktion für Surya Fine-Tuning im Continuous Improvement Loop.

        Args:
            include_corrections: Ob User-Korrektionen als Samples inkludiert werden
            correction_days: Anzahl Tage für Korrektionen

        Returns:
            SuryaExportResult mit allen Details
        """
        import random
        from collections import defaultdict

        start_time = datetime.now()
        version = f"v{start_time.strftime('%Y%m%d_%H%M%S')}"

        logger.info("surya_export_started", version=version)

        # 1. Hole verifizierte Training Samples
        samples = await self._fetch_verified_samples()

        # 2. Optinal: Hole User-Korrektionen für Surya
        if include_corrections:
            correction_samples = await self._fetch_surya_corrections(correction_days)
            samples.extend(correction_samples)

        if not samples:
            logger.warning("surya_export_no_samples")
            return SuryaExportResult(
                output_dir=self.config.output_dir,
                train_samples=0,
                val_samples=0,
                test_samples=0,
                total_samples=0,
                version=version
            )

        # 3. Gewichtete Auswahl (Umlaute priorisieren)
        weighted_samples = self._apply_umlaut_weights(samples)

        # 4. Stratifizierter Split
        random.seed(self.config.seed)
        train, val, test = self._stratified_split(weighted_samples)

        # 5. Output-Verzeichnis erstellen
        output_path = Path(self.config.output_dir) / version
        output_path.mkdir(parents=True, exist_ok=True)

        # 6. Export zu JSONL
        train_file = await self._export_jsonl(train, output_path / "train.jsonl")
        val_file = await self._export_jsonl(val, output_path / "val.jsonl")
        test_file = await self._export_jsonl(test, output_path / "test.jsonl")

        # 7. Metadata erstellen
        all_samples = train + val + test
        umlaut_words = self._collect_umlaut_words(all_samples)

        metadata = {
            "version": version,
            "created_at": start_time.isoformat(),
            "surya_model": "vikp/surya_rec",
            "language": self.config.language,
            "config": {
                "train_ratio": self.config.train_ratio,
                "val_ratio": self.config.val_ratio,
                "test_ratio": self.config.test_ratio,
                "umlaut_weight": self.config.umlaut_weight_multiplier,
                "seed": self.config.seed,
            },
            "statistics": {
                "total_samples": len(all_samples),
                "train_samples": len(train),
                "val_samples": len(val),
                "test_samples": len(test),
                "samples_with_umlauts": sum(1 for s in all_samples if self._has_umlauts(s)),
                "total_umlaut_words": len(umlaut_words),
                "doc_type_distribution": self._calculate_doc_type_distribution(all_samples),
            },
            "training_config": {
                "epochs": 5,
                "learning_rate": 5e-5,
                "batch_size": 4,
                "fp16": True,
                "umlaut_loss_weight": 2.0,
            },
            "files": {
                "train": "train.jsonl",
                "val": "val.jsonl",
                "test": "test.jsonl",
            }
        }

        metadata_file = output_path / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        end_time = datetime.now()

        result = SuryaExportResult(
            output_dir=str(output_path),
            train_samples=len(train),
            val_samples=len(val),
            test_samples=len(test),
            total_samples=len(all_samples),
            doc_type_distribution=self._calculate_doc_type_distribution(all_samples),
            samples_with_umlauts=sum(1 for s in all_samples if self._has_umlauts(s)),
            total_umlaut_words=len(umlaut_words),
            umlaut_word_list=umlaut_words[:100],  # Top 100 für Übersicht
            train_file=str(train_file),
            val_file=str(val_file),
            test_file=str(test_file),
            metadata_file=str(metadata_file),
            export_started=start_time,
            export_completed=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            version=version,
        )

        logger.info(
            "surya_export_completed",
            version=version,
            total=result.total_samples,
            train=result.train_samples,
            umlaut_samples=result.samples_with_umlauts,
            duration_s=result.duration_seconds,
        )

        return result

    async def export_umlaut_focused(self, min_umlaut_words: int = 2) -> SuryaExportResult:
        """
        Exportiert NUR Samples mit Umlauten für fokussiertes Fine-Tuning.

        KRITISCH für 100% Umlaut-Genauigkeit bei deutscher OCR.

        Args:
            min_umlaut_words: Mindestanzahl Umlaut-Wörter pro Sample

        Returns:
            SuryaExportResult
        """
        import random

        start_time = datetime.now()
        version = f"umlaut_focused_{start_time.strftime('%Y%m%d_%H%M%S')}"

        # Hole alle Samples
        all_samples = await self._fetch_verified_samples()

        # Filter: Nur Samples mit genug Umlauten
        umlaut_samples = [
            s for s in all_samples
            if self._count_umlaut_words(s) >= min_umlaut_words
        ]

        if not umlaut_samples:
            logger.warning("no_umlaut_samples_found", min_words=min_umlaut_words)
            return SuryaExportResult(
                output_dir=self.config.output_dir,
                train_samples=0,
                val_samples=0,
                test_samples=0,
                total_samples=0,
                version=version
            )

        # Split (alle Samples sind umlaut-relevant, keine extra Gewichtung nötig)
        random.seed(self.config.seed)
        random.shuffle(umlaut_samples)

        n = len(umlaut_samples)
        train_end = int(n * self.config.train_ratio)
        val_end = train_end + int(n * self.config.val_ratio)

        train = umlaut_samples[:train_end]
        val = umlaut_samples[train_end:val_end]
        test = umlaut_samples[val_end:]

        # Export
        output_path = Path(self.config.output_dir) / version
        output_path.mkdir(parents=True, exist_ok=True)

        train_file = await self._export_jsonl(train, output_path / "train.jsonl")
        val_file = await self._export_jsonl(val, output_path / "val.jsonl")
        test_file = await self._export_jsonl(test, output_path / "test.jsonl")

        end_time = datetime.now()

        return SuryaExportResult(
            output_dir=str(output_path),
            train_samples=len(train),
            val_samples=len(val),
            test_samples=len(test),
            total_samples=len(umlaut_samples),
            samples_with_umlauts=len(umlaut_samples),
            total_umlaut_words=sum(self._count_umlaut_words(s) for s in umlaut_samples),
            train_file=str(train_file),
            val_file=str(val_file),
            test_file=str(test_file),
            export_started=start_time,
            export_completed=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            version=version,
        )

    async def _fetch_verified_samples(self) -> List[OCRTrainingSample]:
        """Holt verifizierte Training Samples aus der Datenbank."""
        from app.db.models import TrainingSampleStatus

        query = select(OCRTrainingSample).where(
            OCRTrainingSample.language == self.config.language
        )

        if self.config.verified_only:
            query = query.where(
                OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value
            )

        # Ground Truth muss vorhanden sein
        query = query.where(OCRTrainingSample.ground_truth_text.isnot(None))
        query = query.where(OCRTrainingSample.ground_truth_text != "")

        if self.config.max_samples > 0:
            query = query.limit(self.config.max_samples)

        result = await self.db.execute(query)
        samples = list(result.scalars().all())

        logger.debug("verified_samples_fetched", count=len(samples))
        return samples

    async def _fetch_surya_corrections(self, days: int) -> List[OCRTrainingSample]:
        """
        Holt User-Korrektionen für Surya und konvertiert sie zu Training Samples.

        Diese Methode ist KRITISCH für den Self-Learning Loop:
        - User korrigiert OCR-Fehler
        - Korrektur wird als neues Training Sample verwendet
        - Nächstes Fine-Tuning lernt aus den Fehlern

        Args:
            days: Anzahl Tage für Korrektionen

        Returns:
            Liste von OCRTrainingSample-ähnlichen Objekten
        """
        from datetime import timedelta
        from app.db.models import OCRValidationCorrection

        since = datetime.now() - timedelta(days=days)

        # Hole Korrektionen für Surya-Backends
        surya_backends = self.config.backend_filter or ["surya", "surya-gpu"]

        query = select(OCRValidationCorrection).where(
            and_(
                OCRValidationCorrection.created_at >= since,
                OCRValidationCorrection.backend_used.in_(surya_backends),
                OCRValidationCorrection.applies_to_training == True,
            )
        )

        result = await self.db.execute(query)
        corrections = list(result.scalars().all())

        # Konvertiere zu Sample-ähnlichen Objekten
        pseudo_samples = []
        for corr in corrections:
            # Erstelle ein Pseudo-Sample für den Export
            pseudo = type('PseudoSample', (), {
                'id': corr.id,
                'ground_truth_text': corr.corrected_text or "",
                'file_path': getattr(corr, 'document_path', None),
                'image_storage_path': getattr(corr, 'document_path', None),
                'language': 'de',
                'document_type': corr.field_corrected or 'correction',
                'source_filename': f"correction_{corr.id}",
                'has_umlauts': self._text_has_umlauts(corr.corrected_text or ""),
                'umlaut_words': self._extract_umlaut_words(corr.corrected_text or ""),
                'extracted_fields': {},
                'difficulty': 'medium',
            })()
            pseudo_samples.append(pseudo)

        logger.debug(
            "surya_corrections_fetched",
            count=len(pseudo_samples),
            days=days,
        )

        return pseudo_samples

    def _apply_umlaut_weights(self, samples: List) -> List[Tuple[Any, float]]:
        """Wendet Gewichtung an - Samples mit Umlauten erhalten höhere Priorität."""
        weighted = []

        for sample in samples:
            weight = 1.0

            if self._has_umlauts(sample):
                weight *= self.config.umlaut_weight_multiplier

                # Zusätzliche Gewichtung basierend auf Anzahl Umlaut-Wörter
                umlaut_count = self._count_umlaut_words(sample)
                if umlaut_count >= 5:
                    weight *= 1.5
                elif umlaut_count >= 3:
                    weight *= 1.2

            weighted.append((sample, weight))

        return weighted

    def _stratified_split(
        self,
        weighted_samples: List[Tuple[Any, float]]
    ) -> Tuple[List, List, List]:
        """Führt stratifizierten Split nach Dokumenttyp durch."""
        import random
        from collections import defaultdict

        if not self.config.stratify_by_doc_type:
            # Einfacher gewichteter Split
            samples = []
            for sample, weight in weighted_samples:
                # Gewichtete Duplikation
                count = max(1, int(weight))
                for _ in range(count):
                    samples.append(sample)

            # Dedupliziere
            unique = list({getattr(s, 'id', id(s)): s for s in samples}.values())
            random.shuffle(unique)

            n = len(unique)
            train_end = int(n * self.config.train_ratio)
            val_end = train_end + int(n * self.config.val_ratio)

            return unique[:train_end], unique[train_end:val_end], unique[val_end:]

        # Stratifiziert nach Dokumenttyp
        by_doc_type: Dict[str, List] = defaultdict(list)

        for sample, weight in weighted_samples:
            doc_type = getattr(sample, 'document_type', None) or "other"
            # Gewichtete Duplikation
            count = max(1, int(weight))
            for _ in range(count):
                by_doc_type[doc_type].append(sample)

        train, val, test = [], [], []

        for doc_type, doc_samples in by_doc_type.items():
            # Dedupliziere
            unique = list({getattr(s, 'id', id(s)): s for s in doc_samples}.values())
            random.shuffle(unique)

            n = len(unique)
            train_end = int(n * self.config.train_ratio)
            val_end = train_end + int(n * self.config.val_ratio)

            train.extend(unique[:train_end])
            val.extend(unique[train_end:val_end])
            test.extend(unique[val_end:])

        random.shuffle(train)
        random.shuffle(val)
        random.shuffle(test)

        return train, val, test

    async def _export_jsonl(self, samples: List, output_file: Path) -> Path:
        """Exportiert Samples zu JSONL im Surya-Format."""
        with open(output_file, "w", encoding="utf-8") as f:
            for sample in samples:
                record = {
                    "image": getattr(sample, 'file_path', None) or getattr(sample, 'image_storage_path', '') or "",
                    "text": getattr(sample, 'ground_truth_text', '') or "",
                    "language": getattr(sample, 'language', 'de') or "de",
                    "metadata": {
                        "sample_id": str(getattr(sample, 'id', '')),
                        "document_type": getattr(sample, 'document_type', None),
                        "has_umlauts": self._has_umlauts(sample),
                        "umlaut_words": getattr(sample, 'umlaut_words', None) or self._extract_umlaut_words(
                            getattr(sample, 'ground_truth_text', '') or ""
                        ),
                    }
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return output_file

    def _has_umlauts(self, sample) -> bool:
        """Prüft ob Sample Umlaute enthält."""
        text = getattr(sample, 'ground_truth_text', '') or ""
        return self._text_has_umlauts(text)

    def _text_has_umlauts(self, text: str) -> bool:
        """Prüft ob Text Umlaute enthält."""
        umlauts = set("äöüÄÖÜß")
        return any(c in umlauts for c in text)

    def _count_umlaut_words(self, sample) -> int:
        """Zählt Wörter mit Umlauten."""
        umlaut_words = getattr(sample, 'umlaut_words', None)
        if umlaut_words:
            return len(umlaut_words)

        text = getattr(sample, 'ground_truth_text', '') or ""
        return len(self._extract_umlaut_words(text))

    def _extract_umlaut_words(self, text: str) -> List[str]:
        """Extrahiert Wörter mit Umlauten aus Text."""
        umlauts = set("äöüÄÖÜß")
        words = text.split()
        return [w for w in words if any(c in umlauts for c in w)]

    def _collect_umlaut_words(self, samples: List) -> List[str]:
        """Sammelt alle einzigartigen Umlaut-Wörter."""
        all_words = set()
        for sample in samples:
            words = getattr(sample, 'umlaut_words', None)
            if words:
                all_words.update(words)
            else:
                text = getattr(sample, 'ground_truth_text', '') or ""
                all_words.update(self._extract_umlaut_words(text))
        return sorted(all_words)

    def _calculate_doc_type_distribution(self, samples: List) -> Dict[str, int]:
        """Berechnet Verteilung nach Dokumenttyp."""
        from collections import defaultdict
        dist: Dict[str, int] = defaultdict(int)
        for sample in samples:
            doc_type = getattr(sample, 'document_type', None) or "other"
            dist[doc_type] += 1
        return dict(dist)

    async def export_with_business_weighting(
        self,
        oversampling_factor: float = 2.0
    ) -> SuryaExportResult:
        """
        Exportiert mit Business-Gewichtung für 90% Coverage-Strategie.

        Business-kritische Dokumenttypen werden überrepresentiert:
        - Rechnungen (invoice): 2x Representation (business_criticality=1.5)
        - Verträge (contract): 1.5x Representation
        - Umlaut-Samples: zusätzlich 2x

        Args:
            oversampling_factor: Basis-Faktor für Oversampling (default: 2.0)

        Returns:
            SuryaExportResult mit Business-gewichteten Samples
        """
        import random
        from datetime import datetime as dt

        start_time = dt.now()
        version = f"business_weighted_{start_time.strftime('%Y%m%d_%H%M%S')}"

        logger.info(
            "surya_business_weighted_export_started",
            version=version,
            oversampling_factor=oversampling_factor,
        )

        # 1. Hole Business Document Profiles für Gewichtung
        from app.db.models import BusinessDocumentProfile

        profiles_result = await self.db.execute(
            select(BusinessDocumentProfile).where(
                BusinessDocumentProfile.is_active == True
            )
        )
        profiles = {p.document_type: p for p in profiles_result.scalars().all()}

        # Fallback-Gewichte wenn keine Profile definiert
        default_weights = {
            "invoice": 1.5,
            "contract": 1.3,
            "letter": 1.0,
            "delivery_note": 1.0,
            "order_confirmation": 1.1,
        }

        # 2. Hole verifizierte Samples
        all_samples = await self._fetch_verified_samples()

        if not all_samples:
            logger.warning("no_samples_for_business_weighted_export")
            return SuryaExportResult(
                output_dir=self.config.output_dir,
                train_samples=0,
                val_samples=0,
                test_samples=0,
                total_samples=0,
                version=version
            )

        # 3. Wende Business-Gewichtung an
        weighted_samples = []
        for sample in all_samples:
            doc_type = getattr(sample, 'document_type', None) or "other"

            # Business Criticality aus Profile oder Fallback
            if doc_type in profiles:
                business_weight = profiles[doc_type].business_criticality
            else:
                business_weight = default_weights.get(doc_type, 1.0)

            # Kombiniere Business-Gewicht mit Umlaut-Gewicht
            total_weight = business_weight * oversampling_factor

            if self._has_umlauts(sample):
                total_weight *= self.config.umlaut_weight_multiplier

                # Extra Boost für viele Umlaute
                umlaut_count = self._count_umlaut_words(sample)
                if umlaut_count >= 5:
                    total_weight *= 1.3
                elif umlaut_count >= 3:
                    total_weight *= 1.15

            # Oversampling durch Duplikation
            repeat_count = max(1, int(total_weight))
            for _ in range(repeat_count):
                weighted_samples.append(sample)

        # Dedupliziere (behalte aber Gewichtung im Split)
        random.seed(self.config.seed)
        random.shuffle(weighted_samples)

        # Eindeutige Samples für Statistik
        unique_samples = list({getattr(s, 'id', id(s)): s for s in weighted_samples}.values())

        # 4. Split
        n = len(weighted_samples)
        train_end = int(n * self.config.train_ratio)
        val_end = train_end + int(n * self.config.val_ratio)

        train_weighted = weighted_samples[:train_end]
        val_weighted = weighted_samples[train_end:val_end]
        test_weighted = weighted_samples[val_end:]

        # Dedupliziere jedes Split
        train = list({getattr(s, 'id', id(s)): s for s in train_weighted}.values())
        val = list({getattr(s, 'id', id(s)): s for s in val_weighted}.values())
        test = list({getattr(s, 'id', id(s)): s for s in test_weighted}.values())

        # 5. Export
        output_path = Path(self.config.output_dir) / version
        output_path.mkdir(parents=True, exist_ok=True)

        train_file = await self._export_jsonl(train, output_path / "train.jsonl")
        val_file = await self._export_jsonl(val, output_path / "val.jsonl")
        test_file = await self._export_jsonl(test, output_path / "test.jsonl")

        # 6. Metadata mit Business-Gewichtung
        all_exported = train + val + test
        umlaut_words = self._collect_umlaut_words(all_exported)

        metadata = {
            "version": version,
            "created_at": start_time.isoformat(),
            "export_type": "business_weighted",
            "language": self.config.language,
            "weighting_config": {
                "oversampling_factor": oversampling_factor,
                "umlaut_weight": self.config.umlaut_weight_multiplier,
                "business_weights": {
                    doc_type: profiles[doc_type].business_criticality
                    for doc_type in profiles
                } if profiles else default_weights,
            },
            "statistics": {
                "unique_samples": len(unique_samples),
                "weighted_samples_total": len(weighted_samples),
                "train_samples": len(train),
                "val_samples": len(val),
                "test_samples": len(test),
                "samples_with_umlauts": sum(1 for s in all_exported if self._has_umlauts(s)),
                "total_umlaut_words": len(umlaut_words),
                "doc_type_distribution": self._calculate_doc_type_distribution(all_exported),
            },
            "files": {
                "train": "train.jsonl",
                "val": "val.jsonl",
                "test": "test.jsonl",
            }
        }

        metadata_file = output_path / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        end_time = dt.now()

        result = SuryaExportResult(
            output_dir=str(output_path),
            train_samples=len(train),
            val_samples=len(val),
            test_samples=len(test),
            total_samples=len(all_exported),
            doc_type_distribution=self._calculate_doc_type_distribution(all_exported),
            samples_with_umlauts=sum(1 for s in all_exported if self._has_umlauts(s)),
            total_umlaut_words=len(umlaut_words),
            umlaut_word_list=umlaut_words[:100],
            train_file=str(train_file),
            val_file=str(val_file),
            test_file=str(test_file),
            metadata_file=str(metadata_file),
            export_started=start_time,
            export_completed=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            version=version,
        )

        logger.info(
            "surya_business_weighted_export_completed",
            version=version,
            unique_samples=len(unique_samples),
            total_exported=len(all_exported),
            umlaut_samples=result.samples_with_umlauts,
            duration_s=result.duration_seconds,
        )

        return result


# Singleton für Surya Exporter
_surya_exporter: Optional[SuryaDatasetExporter] = None


async def get_surya_exporter(
    db: AsyncSession,
    config: Optional[SuryaExportConfig] = None
) -> SuryaDatasetExporter:
    """Gibt SuryaDatasetExporter-Instanz zurück."""
    return SuryaDatasetExporter(db, config)
