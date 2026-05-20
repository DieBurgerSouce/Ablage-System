#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model-Verifikations-Script fuer Docker Build.

Prueft ob alle benoetigten OCR-Modelle im Cache verfuegbar sind.
Wird waehrend `docker-compose build` oder als Healthcheck ausgefuehrt.

Usage:
    python scripts/verify_models.py [--download] [--verbose]

Flags:
    --download: Fehlende Modelle automatisch herunterladen
    --verbose:  Detaillierte Ausgabe

Exit Codes:
    0: Alle Modelle verfuegbar
    1: Mindestens ein Modell fehlt (ohne --download)
    2: Download fehlgeschlagen
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# Bekannte Model-Verzeichnisse im HuggingFace Cache
REQUIRED_MODELS: Dict[str, Dict[str, str]] = {
    "surya_docling": {
        "description": "Surya OCR + Docling Layout (CPU)",
        "hf_repo": "vikp/surya_rec2",
        "check_pattern": "surya_rec",
    },
    "surya_det": {
        "description": "Surya Text-Erkennung",
        "hf_repo": "vikp/surya_det3",
        "check_pattern": "surya_det",
    },
    "surya_layout": {
        "description": "Surya Layout-Analyse",
        "hf_repo": "vikp/surya_layout3",
        "check_pattern": "surya_layout",
    },
}

GPU_MODELS: Dict[str, Dict[str, str]] = {
    "got_ocr": {
        "description": "GOT-OCR 2.0 (GPU, ~10GB VRAM)",
        "hf_repo": "stepfun-ai/GOT-OCR2_0",
        "check_pattern": "GOT-OCR",
    },
    "deepseek": {
        "description": "DeepSeek-Janus-Pro (GPU, ~12GB VRAM)",
        "hf_repo": "deepseek-ai/Janus-Pro-7B",
        "check_pattern": "Janus-Pro",
    },
}


def get_cache_dir() -> Path:
    """Bestimme HuggingFace Cache-Verzeichnis."""
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return Path(hf_home) / "hub"


def check_model_cached(cache_dir: Path, check_pattern: str) -> bool:
    """Pruefe ob ein Modell im Cache vorhanden ist."""
    if not cache_dir.exists():
        return False

    for entry in cache_dir.iterdir():
        if check_pattern.lower() in entry.name.lower():
            # Pruefe ob das Verzeichnis Snapshot-Daten hat
            snapshots = entry / "snapshots"
            if snapshots.exists() and any(snapshots.iterdir()):
                return True
            # Oder direkte Modelldateien
            if any(entry.glob("*.bin")) or any(entry.glob("*.safetensors")):
                return True
    return False


def download_model(hf_repo: str, verbose: bool = False) -> bool:
    """Lade ein Modell herunter via huggingface_hub."""
    try:
        from huggingface_hub import snapshot_download

        if verbose:
            print(f"  Lade herunter: {hf_repo}...")

        snapshot_download(
            repo_id=hf_repo,
            local_dir_use_symlinks=True,
        )
        return True
    except ImportError:
        print("FEHLER: huggingface_hub nicht installiert.")
        print("  pip install huggingface_hub")
        return False
    except Exception as e:
        print(f"FEHLER beim Download von {hf_repo}: {e}")
        return False


def verify_models(
    include_gpu: bool = False,
    download: bool = False,
    verbose: bool = False,
) -> Tuple[List[str], List[str]]:
    """
    Verifiziere ob Modelle verfuegbar sind.

    Returns:
        Tuple von (verfuegbare, fehlende) Modell-Listen
    """
    cache_dir = get_cache_dir()
    models = dict(REQUIRED_MODELS)
    if include_gpu:
        models.update(GPU_MODELS)

    available: List[str] = []
    missing: List[str] = []

    if verbose:
        print(f"Cache-Verzeichnis: {cache_dir}")
        print(f"Cache existiert: {cache_dir.exists()}")
        print()

    for name, info in models.items():
        cached = check_model_cached(cache_dir, info["check_pattern"])

        if cached:
            available.append(name)
            if verbose:
                print(f"  [OK] {name}: {info['description']}")
        else:
            if download:
                if verbose:
                    print(f"  [DL] {name}: {info['description']} - wird heruntergeladen...")
                success = download_model(info["hf_repo"], verbose)
                if success:
                    available.append(name)
                    if verbose:
                        print(f"  [OK] {name}: erfolgreich heruntergeladen")
                else:
                    missing.append(name)
                    print(f"  [!!] {name}: Download fehlgeschlagen")
            else:
                missing.append(name)
                if verbose:
                    print(f"  [--] {name}: {info['description']} - FEHLT")

    return available, missing


def main() -> int:
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(
        description="Verifiziere OCR-Modell-Verfuegbarkeit"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Fehlende Modelle automatisch herunterladen",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Auch GPU-Modelle pruefen (GOT-OCR, DeepSeek)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Detaillierte Ausgabe",
    )

    args = parser.parse_args()

    print("=== OCR-Modell-Verifikation ===")
    print()

    available, missing = verify_models(
        include_gpu=args.gpu,
        download=args.download,
        verbose=args.verbose,
    )

    print()
    print(f"Ergebnis: {len(available)} verfuegbar, {len(missing)} fehlend")

    if missing:
        print()
        print("Fehlende Modelle:")
        all_models = {**REQUIRED_MODELS, **GPU_MODELS}
        for name in missing:
            info = all_models.get(name, {})
            print(f"  - {name}: {info.get('description', '?')}")
            print(f"    Download: huggingface-cli download {info.get('hf_repo', '?')}")

        if not args.download:
            print()
            print("Tipp: Mit --download werden fehlende Modelle automatisch geladen.")
            return 1
        else:
            return 2

    print("Alle benoetigten Modelle sind verfuegbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
