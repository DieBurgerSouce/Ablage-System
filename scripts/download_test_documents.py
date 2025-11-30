#!/usr/bin/env python
"""
Download public domain German test documents for OCR validation.

Downloads documents from:
- Wikimedia Commons (CC0/Public Domain)
- Archive.org (Public Domain)
- Public German government templates

Usage:
    python scripts/download_test_documents.py
    python scripts/download_test_documents.py --output tests/fixtures/german_docs/downloaded
    python scripts/download_test_documents.py --category fraktur
"""

import argparse
import hashlib
import json
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class DocumentSource:
    """Source information for a downloadable document."""
    url: str
    filename: str
    category: str
    description: str
    license: str
    source_name: str
    expected_hash: Optional[str] = None  # SHA256 for verification


# Public domain German document sources
# Note: These are example URLs - some may need to be updated
DOCUMENT_SOURCES = [
    # Fraktur texts from Wikimedia Commons
    DocumentSource(
        url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/8d/Fraktur_A-Z.svg/800px-Fraktur_A-Z.svg.png",
        filename="fraktur_alphabet.png",
        category="fraktur",
        description="Fraktur alphabet reference",
        license="Public Domain",
        source_name="Wikimedia Commons",
    ),

    # Note: Additional URLs would be added here
    # The following are placeholder examples - actual URLs need verification

    # Example historical German text
    # DocumentSource(
    #     url="https://upload.wikimedia.org/wikipedia/commons/...",
    #     filename="fraktur_sample_001.png",
    #     category="fraktur",
    #     description="Historical German Fraktur text sample",
    #     license="Public Domain",
    #     source_name="Wikimedia Commons",
    # ),
]


class DocumentDownloader:
    """Download and manage public domain test documents."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.categories = ["fraktur", "historical", "forms", "handwritten"]

        # Create output directories
        for cat in self.categories:
            (output_dir / cat).mkdir(parents=True, exist_ok=True)

    def download_file(self, source: DocumentSource) -> bool:
        """Download a single document."""
        filepath = self.output_dir / source.category / source.filename

        if filepath.exists():
            print(f"  [SKIP] {source.filename} (already exists)")
            return True

        print(f"  [DOWNLOAD] {source.filename}...")

        try:
            # Create request with user agent
            req = urllib.request.Request(
                source.url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read()

            # Verify hash if provided
            if source.expected_hash:
                actual_hash = hashlib.sha256(content).hexdigest()
                if actual_hash != source.expected_hash:
                    print(f"  [ERROR] Hash mismatch for {source.filename}")
                    return False

            # Save file
            filepath.write_bytes(content)

            # Create metadata file
            metadata = {
                "filename": source.filename,
                "source_url": source.url,
                "source_name": source.source_name,
                "license": source.license,
                "description": source.description,
                "category": source.category,
                "download_date": datetime.now().isoformat(),
            }

            metadata_path = filepath.with_suffix(".json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            print(f"  [OK] {source.filename}")
            return True

        except urllib.error.HTTPError as e:
            print(f"  [ERROR] HTTP {e.code}: {source.filename}")
            return False
        except urllib.error.URLError as e:
            print(f"  [ERROR] URL error: {e.reason}")
            return False
        except Exception as e:
            print(f"  [ERROR] {e}")
            return False

    def download_all(self, category: Optional[str] = None) -> dict:
        """Download all documents, optionally filtered by category."""
        sources = DOCUMENT_SOURCES

        if category:
            sources = [s for s in sources if s.category == category]

        if not sources:
            print(f"No sources found for category: {category}")
            return {"downloaded": 0, "skipped": 0, "failed": 0}

        print(f"\nDownloading {len(sources)} documents...")
        print("=" * 50)

        stats = {"downloaded": 0, "skipped": 0, "failed": 0}

        for source in sources:
            filepath = self.output_dir / source.category / source.filename
            if filepath.exists():
                stats["skipped"] += 1
            elif self.download_file(source):
                stats["downloaded"] += 1
            else:
                stats["failed"] += 1

        print("\n" + "=" * 50)
        print(f"Downloaded: {stats['downloaded']}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Failed: {stats['failed']}")

        return stats

    def create_manifest(self):
        """Create a manifest of all downloaded documents."""
        manifest = {
            "generated": datetime.now().isoformat(),
            "documents": [],
        }

        for cat in self.categories:
            cat_dir = self.output_dir / cat
            if not cat_dir.exists():
                continue

            for json_file in cat_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                        manifest["documents"].append(metadata)
                except Exception:
                    pass

        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print(f"\nManifest created: {manifest_path}")
        print(f"Total documents: {len(manifest['documents'])}")


def print_available_sources():
    """Print information about available document sources."""
    print("\nAvailable Document Sources:")
    print("=" * 60)

    categories = {}
    for source in DOCUMENT_SOURCES:
        if source.category not in categories:
            categories[source.category] = []
        categories[source.category].append(source)

    for cat, sources in categories.items():
        print(f"\n{cat.upper()} ({len(sources)} documents):")
        for source in sources:
            print(f"  - {source.filename}: {source.description}")
            print(f"    License: {source.license}")

    print("\n" + "=" * 60)
    print(f"Total: {len(DOCUMENT_SOURCES)} documents available")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download public domain German test documents for OCR validation"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("tests/fixtures/german_docs/downloaded"),
        help="Output directory (default: tests/fixtures/german_docs/downloaded)"
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        choices=["fraktur", "historical", "forms", "handwritten", "all"],
        default="all",
        help="Category to download (default: all)"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available sources without downloading"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    if args.list:
        print_available_sources()
        return

    if not DOCUMENT_SOURCES:
        print("NOTE: Document sources list is currently minimal.")
        print("Most test documents should be generated using:")
        print("  python scripts/generate_test_documents.py")
        print("\nThis script is for supplementing with real-world documents.")

    downloader = DocumentDownloader(args.output)

    category = None if args.category == "all" else args.category
    downloader.download_all(category)
    downloader.create_manifest()


if __name__ == "__main__":
    main()
