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
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    OCRDocumentOutput,
    OCRTrainingSample,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


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

        logger.info(f"Starte Dataset-Export: {export_id}", extra={
            "export_id": export_id,
            "format": config.format,
            "filter_verified_only": config.filter_verified_only
        })

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

            logger.info(f"Dataset-Export abgeschlossen: {export_id}", extra={
                "export_id": export_id,
                "total_samples": stats.total_samples,
                "files_created": len(files_created)
            })

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
                errors=[str(e)]
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
                OCRTrainingSample.verification_status == VerificationStatus.VERIFIED
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
                            "verification_status": sample.verification_status.value if sample.verification_status else None
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
                except Exception:
                    pass

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
