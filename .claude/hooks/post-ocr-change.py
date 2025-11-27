#!/usr/bin/env python3
"""
Post-OCR-Change Hook for Ablage-System.
Triggered when OCR-related files are modified.

Automatically runs relevant tests and validates GPU compatibility.
"""

import subprocess
import sys
from pathlib import Path
from typing import List


def get_affected_ocr_components(files: List[str]) -> List[str]:
    """Identify which OCR components were modified."""
    components = set()

    for filepath in files:
        path = Path(filepath)
        if 'deepseek' in filepath.lower():
            components.add('deepseek')
        elif 'got_ocr' in filepath.lower() or 'got-ocr' in filepath.lower():
            components.add('got_ocr')
        elif 'surya' in filepath.lower():
            components.add('surya')
        elif 'ocr_service' in filepath.lower():
            components.add('ocr_service')
        elif 'gpu_manager' in filepath.lower():
            components.add('gpu_manager')
        elif 'backend_manager' in filepath.lower():
            components.add('backend_manager')

    return list(components)


def run_component_tests(components: List[str]) -> bool:
    """Run tests for affected components."""
    test_mapping = {
        'deepseek': 'tests/unit/test_deepseek_agent.py',
        'got_ocr': 'tests/unit/test_got_ocr_agent.py',
        'surya': 'tests/unit/test_surya_agent.py',
        'ocr_service': 'tests/unit/test_ocr_service.py',
        'gpu_manager': 'tests/unit/test_gpu_manager.py',
        'backend_manager': 'tests/unit/test_backend_manager.py',
    }

    all_passed = True
    for component in components:
        test_file = test_mapping.get(component)
        if test_file and Path(test_file).exists():
            print(f"\nTeste {component}...")
            result = subprocess.run(
                ['pytest', test_file, '-v', '--tb=short'],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"❌ Tests für {component} fehlgeschlagen:")
                print(result.stdout)
                print(result.stderr)
                all_passed = False
            else:
                print(f"✓ {component} Tests bestanden")

    return all_passed


def validate_gpu_requirements(components: List[str]) -> bool:
    """Validate GPU VRAM requirements for modified backends."""
    vram_requirements = {
        'deepseek': 12,  # GB
        'got_ocr': 10,
        'surya': 0,  # CPU only
    }

    max_vram = 16  # RTX 4080
    safety_buffer = 4

    for component in components:
        required = vram_requirements.get(component, 0)
        if required > max_vram - safety_buffer:
            print(f"⚠ WARNUNG: {component} benötigt {required}GB VRAM")
            print(f"  Verfügbar: {max_vram - safety_buffer}GB (nach Safety Buffer)")

    return True


def main() -> int:
    """Run post-OCR-change validations."""
    # Get changed files from command line or git
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1'],
            capture_output=True,
            text=True
        )
        files = [f.strip() for f in result.stdout.split('\n') if f.strip()]

    # Filter for OCR-related files
    ocr_files = [f for f in files if any(
        pattern in f.lower()
        for pattern in ['ocr', 'deepseek', 'surya', 'got', 'gpu']
    )]

    if not ocr_files:
        print("Keine OCR-relevanten Änderungen gefunden.")
        return 0

    print("=== OCR-Änderungs-Validierung ===\n")
    print(f"Betroffene Dateien: {len(ocr_files)}")
    for f in ocr_files:
        print(f"  - {f}")

    components = get_affected_ocr_components(ocr_files)
    if components:
        print(f"\nBetroffene Komponenten: {', '.join(components)}")

        # Validate GPU requirements
        validate_gpu_requirements(components)

        # Run component tests
        if not run_component_tests(components):
            print("\n❌ Einige Tests sind fehlgeschlagen!")
            return 1

    print("\n✓ OCR-Validierung abgeschlossen!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
