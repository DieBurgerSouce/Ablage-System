"""
Batch OCR Runner

Command-line tool for processing multiple documents with OCR in batch mode.
Useful for bulk document processing, migration, or testing.

Features:
- Process multiple files/directories
- Parallel processing with GPU batching
- Progress tracking and reporting
- Resume capability (skip already processed)
- Export results to CSV/JSON
"""

import asyncio
import argparse
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import sys

import structlog
from tqdm import tqdm

from app.services.ocr_service import OCRService
from app.db.session import async_session_maker
from app.db.models import Document, OCRResult
from sqlalchemy import select


logger = structlog.get_logger(__name__)


class BatchOCRRunner:
    """
    Batch OCR processing runner.

    Processes multiple documents with OCR, tracking progress and results.
    """

    def __init__(
        self,
        backend: str = "auto",
        max_concurrent: int = 5,
        output_dir: Optional[str] = None,
        skip_existing: bool = True
    ):
        """
        Initialize batch runner.

        Args:
            backend: OCR backend to use (auto, deepseek, got_ocr, surya)
            max_concurrent: Maximum concurrent OCR processes
            output_dir: Directory for results (default: ./batch_ocr_results)
            skip_existing: Skip files already processed
        """
        self.backend = backend
        self.max_concurrent = max_concurrent
        self.output_dir = Path(output_dir or "./batch_ocr_results")
        self.skip_existing = skip_existing

        self.ocr_service = OCRService()

        # Statistics
        self.stats = {
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None
        }

        # Results
        self.results = []

        # Setup output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "batch_runner_initialized",
            backend=backend,
            max_concurrent=max_concurrent,
            output_dir=str(self.output_dir)
        )

    async def run(
        self,
        input_paths: List[str],
        recursive: bool = False,
        file_pattern: str = "*.*"
    ) -> Dict:
        """
        Run batch OCR processing.

        Args:
            input_paths: List of files or directories to process
            recursive: Process directories recursively
            file_pattern: File pattern to match (e.g., "*.pdf")

        Returns:
            Processing statistics and results
        """
        self.stats["start_time"] = datetime.utcnow()

        try:
            # Collect all files to process
            files_to_process = self._collect_files(
                input_paths,
                recursive=recursive,
                pattern=file_pattern
            )

            self.stats["total"] = len(files_to_process)

            logger.info(
                "batch_processing_started",
                total_files=len(files_to_process),
                backend=self.backend
            )

            # Process files with progress bar
            with tqdm(total=len(files_to_process), desc="Processing documents") as pbar:
                # Process in batches for better GPU utilization
                semaphore = asyncio.Semaphore(self.max_concurrent)

                async def process_with_semaphore(file_path: Path):
                    async with semaphore:
                        result = await self._process_file(file_path)
                        pbar.update(1)
                        return result

                # Run all tasks
                results = await asyncio.gather(
                    *[process_with_semaphore(f) for f in files_to_process],
                    return_exceptions=True
                )

                # Collect results
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("processing_exception", error=str(result))
                        self.stats["errors"] += 1
                    elif result:
                        self.results.append(result)

            self.stats["end_time"] = datetime.utcnow()

            # Export results
            await self._export_results()

            # Print summary
            self._print_summary()

            return {
                "stats": self.stats,
                "results": self.results
            }

        except Exception as e:
            logger.exception("batch_processing_failed", error=str(e))
            raise

    def _collect_files(
        self,
        input_paths: List[str],
        recursive: bool = False,
        pattern: str = "*.*"
    ) -> List[Path]:
        """
        Collect all files to process from input paths.

        Args:
            input_paths: List of file or directory paths
            recursive: Process directories recursively
            pattern: File pattern to match

        Returns:
            List of file Path objects
        """
        files = []

        for input_path_str in input_paths:
            input_path = Path(input_path_str)

            if not input_path.exists():
                logger.warning("path_not_found", path=str(input_path))
                continue

            if input_path.is_file():
                files.append(input_path)

            elif input_path.is_dir():
                if recursive:
                    # Recursive glob
                    matched_files = input_path.rglob(pattern)
                else:
                    # Non-recursive glob
                    matched_files = input_path.glob(pattern)

                for file_path in matched_files:
                    if file_path.is_file():
                        files.append(file_path)

        logger.info("files_collected", count=len(files))
        return files

    async def _process_file(self, file_path: Path) -> Optional[Dict]:
        """
        Process a single file with OCR.

        Args:
            file_path: Path to file

        Returns:
            Processing result dict or None if skipped/failed
        """
        try:
            # Check if already processed (if skip_existing enabled)
            if self.skip_existing:
                if await self._is_already_processed(file_path):
                    logger.info("file_skipped_already_processed", file=str(file_path))
                    self.stats["skipped"] += 1
                    return None

            # Process with OCR
            logger.info("processing_file", file=str(file_path))

            start_time = datetime.utcnow()

            ocr_result = await self.ocr_service.process_document(
                document_path=str(file_path),
                backend=self.backend
            )

            end_time = datetime.utcnow()
            processing_time = (end_time - start_time).total_seconds()

            # Build result
            result = {
                "file_path": str(file_path),
                "file_name": file_path.name,
                "status": "success",
                "backend": ocr_result.get("backend", self.backend),
                "confidence": ocr_result.get("confidence", 0.0),
                "text_length": len(ocr_result.get("text", "")),
                "processing_time_seconds": processing_time,
                "timestamp": datetime.utcnow().isoformat()
            }

            self.stats["processed"] += 1

            logger.info(
                "file_processed",
                file=str(file_path),
                confidence=result["confidence"],
                time_seconds=processing_time
            )

            return result

        except Exception as e:
            logger.exception("file_processing_failed", file=str(file_path), error=str(e))

            self.stats["errors"] += 1

            return {
                "file_path": str(file_path),
                "file_name": file_path.name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def _is_already_processed(self, file_path: Path) -> bool:
        """
        Check if file has already been processed.

        Checks database for existing OCR result with same file path.

        Args:
            file_path: Path to file

        Returns:
            True if already processed
        """
        try:
            async with async_session_maker() as db:
                # Check if document exists with this path
                result = await db.execute(
                    select(Document).where(Document.file_path == str(file_path))
                )
                document = result.scalar_one_or_none()

                if not document:
                    return False

                # Check if OCR result exists for this document
                result = await db.execute(
                    select(OCRResult).where(OCRResult.document_id == document.id)
                )
                ocr_result = result.scalar_one_or_none()

                return ocr_result is not None

        except Exception as e:
            logger.error("database_check_failed", error=str(e))
            # Assume not processed on error
            return False

    async def _export_results(self):
        """Export results to CSV and JSON files."""
        # Export to JSON
        json_file = self.output_dir / f"results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "stats": self.stats,
                    "results": self.results
                },
                f,
                indent=2,
                ensure_ascii=False,
                default=str  # Handle datetime serialization
            )

        logger.info("results_exported_json", file=str(json_file))

        # Export to CSV
        if self.results:
            csv_file = self.output_dir / f"results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                # Get all unique keys from results
                all_keys = set()
                for result in self.results:
                    all_keys.update(result.keys())

                writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
                writer.writeheader()
                writer.writerows(self.results)

            logger.info("results_exported_csv", file=str(csv_file))

    def _print_summary(self):
        """Print processing summary to console."""
        print("\n" + "=" * 60)
        print("BATCH OCR PROCESSING SUMMARY")
        print("=" * 60)

        print(f"\nTotal Files:      {self.stats['total']}")
        print(f"Processed:        {self.stats['processed']} ✓")
        print(f"Skipped:          {self.stats['skipped']}")
        print(f"Errors:           {self.stats['errors']} ✗")

        if self.stats["start_time"] and self.stats["end_time"]:
            duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
            print(f"\nTotal Time:       {duration:.2f} seconds")

            if self.stats["processed"] > 0:
                avg_time = duration / self.stats["processed"]
                print(f"Avg Time/File:    {avg_time:.2f} seconds")

        # Success rate
        if self.stats["total"] > 0:
            success_rate = (self.stats["processed"] / self.stats["total"]) * 100
            print(f"\nSuccess Rate:     {success_rate:.1f}%")

        print(f"\nResults saved to: {self.output_dir}")
        print("=" * 60 + "\n")


# ============================================================================
# CLI
# ============================================================================

async def main():
    """Command-line interface for batch OCR runner."""
    parser = argparse.ArgumentParser(
        description="Batch OCR processing tool for Ablage-System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs in a directory
  python batch_ocr_runner.py /path/to/documents/*.pdf

  # Process directory recursively
  python batch_ocr_runner.py /path/to/documents/ --recursive

  # Use specific backend
  python batch_ocr_runner.py /path/to/docs/ --backend deepseek

  # Process with custom concurrency
  python batch_ocr_runner.py /path/to/docs/ --max-concurrent 10

  # Force reprocessing (don't skip existing)
  python batch_ocr_runner.py /path/to/docs/ --no-skip-existing
        """
    )

    parser.add_argument(
        "input_paths",
        nargs="+",
        help="Files or directories to process"
    )

    parser.add_argument(
        "-b", "--backend",
        choices=["auto", "deepseek", "got_ocr", "surya"],
        default="auto",
        help="OCR backend to use (default: auto)"
    )

    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Process directories recursively"
    )

    parser.add_argument(
        "-p", "--pattern",
        default="*.*",
        help="File pattern to match (default: *.*)"
    )

    parser.add_argument(
        "-c", "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent OCR processes (default: 5)"
    )

    parser.add_argument(
        "-o", "--output-dir",
        default="./batch_ocr_results",
        help="Output directory for results (default: ./batch_ocr_results)"
    )

    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Reprocess files even if already processed"
    )

    args = parser.parse_args()

    # Initialize runner
    runner = BatchOCRRunner(
        backend=args.backend,
        max_concurrent=args.max_concurrent,
        output_dir=args.output_dir,
        skip_existing=not args.no_skip_existing
    )

    # Run batch processing
    try:
        await runner.run(
            input_paths=args.input_paths,
            recursive=args.recursive,
            file_pattern=args.pattern
        )

    except KeyboardInterrupt:
        print("\n\nProcessing interrupted by user.")
        sys.exit(1)

    except Exception as e:
        logger.exception("batch_processing_failed", error=str(e))
        print(f"\n\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Setup logging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run
    asyncio.run(main())
