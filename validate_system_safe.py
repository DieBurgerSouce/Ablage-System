#!/usr/bin/env python3
"""
Validation script for Ablage-System OCR (ASCII-safe version)
Tests core functionality without requiring full model downloads

Usage:
    python validate_system_safe.py
"""

import sys
import json
from pathlib import Path
from typing import Dict, List
import importlib.util

# Add app to path
sys.path.append(str(Path(__file__).parent))


def check_module(module_path: str, module_name: str) -> bool:
    """Check if a Python module can be imported."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return True
    except Exception as e:
        print(f"  [X] Error loading {module_name}: {str(e)[:50]}...")
        return False
    return False


def validate_structure():
    """Validate project structure."""
    print("\n[STRUCTURE] Validating Project Structure")
    print("=" * 60)

    required_dirs = [
        "app",
        "app/agents",
        "app/agents/ocr",
        "app/core",
        "app/services",
        "app/db",
        "app/api",
        "Execution_Layer",
        "Execution_Layer/routers",
        "Static_Knowledge",
        "Dynamic_Knowledge",
        "infrastructure",
        "infrastructure/docker"
    ]

    missing_dirs = []
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"  [OK] {dir_path}")
        else:
            print(f"  [X] {dir_path} (missing)")
            missing_dirs.append(dir_path)

    return len(missing_dirs) == 0


def validate_ocr_backends():
    """Validate OCR backend implementations."""
    print("\n[OCR] Validating OCR Backends")
    print("=" * 60)

    backends = {
        "DeepSeek-Janus-Pro": "app/agents/ocr/deepseek_agent.py",
        "GOT-OCR 2.0": "app/agents/ocr/got_ocr_agent.py",
        "Surya-Docling": "app/agents/ocr/surya_docling_agent.py"
    }

    all_valid = True
    for name, path in backends.items():
        file_path = Path(path)
        if file_path.exists():
            # Check if module loads
            module_name = path.replace("/", ".").replace("\\", ".").replace(".py", "")
            if check_module(path, module_name):
                print(f"  [OK] {name}: Implemented and loadable")

                # Check for key classes
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "class DeepSeekAgent" in content or "class GOTOCRAgent" in content or "class SuryaDoclingAgent" in content:
                        print(f"    -> Agent class found")
                    if "async def process" in content:
                        print(f"    -> Process method implemented")
            else:
                print(f"  [!] {name}: File exists but has import issues")
                all_valid = False
        else:
            print(f"  [X] {name}: Not found at {path}")
            all_valid = False

    return all_valid


def validate_routing():
    """Validate routing logic."""
    print("\n[ROUTING] Validating Routing Logic")
    print("=" * 60)

    router_path = Path("Execution_Layer/routers/ocr_router.py")
    if not router_path.exists():
        print(f"  [X] Router not found")
        return False

    try:
        # Import and test routing logic
        from Execution_Layer.routers.ocr_router import OCRRouter, DocumentAnalysis, BackendType

        print(f"  [OK] OCRRouter imported successfully")

        # Test routing scenarios
        router = OCRRouter()

        test_cases = [
            ("Formula document", DocumentAnalysis(has_formulas=True), BackendType.GOT_OCR),
            ("Complex multimodal", DocumentAnalysis(requires_image_understanding=True), BackendType.JANUS_PRO),
            ("Structured PDF", DocumentAnalysis(is_structured_pdf=True, document_type="invoice"), BackendType.SURYA_DOCLING),
        ]

        all_correct = True
        for name, analysis, expected in test_cases:
            try:
                selected = router.select_backend(analysis)
                if selected == expected:
                    print(f"  [OK] {name}: {selected.value}")
                else:
                    print(f"  [X] {name}: Expected {expected.value}, got {selected.value}")
                    all_correct = False
            except Exception as e:
                print(f"  [X] {name}: Error - {str(e)[:50]}...")
                all_correct = False

        return all_correct

    except Exception as e:
        print(f"  [X] Failed to import router: {e}")
        return False


def validate_infrastructure():
    """Validate infrastructure files."""
    print("\n[INFRA] Validating Infrastructure")
    print("=" * 60)

    files = {
        "Docker Compose": "docker-compose.yml",
        "Requirements": "requirements.txt",
        "Environment Example": ".env.example",
        "Main API": "app/main.py",
        "Database Models": "app/db/models.py",
        "GPU Manager": "app/gpu_manager.py"
    }

    all_exist = True
    for name, path in files.items():
        file_path = Path(path)
        if file_path.exists():
            size_kb = file_path.stat().st_size / 1024
            print(f"  [OK] {name}: {size_kb:.1f} KB")

            # Check for key content
            if name == "Docker Compose":
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    services = ["postgres", "redis", "minio", "backend", "worker"]
                    for service in services:
                        if service in content:
                            print(f"    -> {service} service configured")
        else:
            print(f"  [X] {name}: Missing")
            all_exist = False

    return all_exist


def validate_dependencies():
    """Check if required Python packages are in requirements.txt."""
    print("\n[DEPS] Validating Dependencies")
    print("=" * 60)

    req_file = Path("requirements.txt")
    if not req_file.exists():
        print(f"  [X] requirements.txt not found")
        return False

    with open(req_file, 'r', encoding='utf-8') as f:
        requirements = f.read().lower()

    essential_packages = [
        ("fastapi", "Web framework"),
        ("torch", "Deep learning"),
        ("transformers", "Model loading"),
        ("sqlalchemy", "Database ORM"),
        ("celery", "Task queue"),
        ("redis", "Cache/Queue"),
        ("minio", "Object storage"),
        ("pillow", "Image processing"),
        ("surya-ocr", "Surya OCR backend"),
        ("pypdfium2", "PDF processing"),
        ("bitsandbytes", "Model quantization"),
        ("spacy", "German NLP")
    ]

    all_found = True
    for package, description in essential_packages:
        if package in requirements:
            print(f"  [OK] {package}: {description}")
        else:
            print(f"  [X] {package}: {description} (missing)")
            all_found = False

    return all_found


def validate_german_support():
    """Validate German language support components."""
    print("\n[GERMAN] Validating German Language Support")
    print("=" * 60)

    components = {
        "German Validator": "app/german_validator.py",
        "German Text Processing Skill": "Static_Knowledge/Skills/german_text_processing_skill.yaml",
        "Business Terms Glossary": "Static_Knowledge/Glossar/business_terms_de.yaml"
    }

    all_exist = True
    for name, path in components.items():
        file_path = Path(path)
        if file_path.exists():
            print(f"  [OK] {name}")

            # Check for umlaut handling
            if name == "German Validator":
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Check for German characters (avoiding direct Unicode)
                        if "umlaut" in content.lower():
                            print(f"    -> Umlaut support detected")
                except Exception:
                    pass
        else:
            print(f"  [!] {name}: Not found (optional)")

    return True  # German support is optional for basic functionality


def generate_summary(results: Dict[str, bool]):
    """Generate validation summary."""
    print("\n[SUMMARY] Validation Results")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    percentage = (passed / total) * 100 if total > 0 else 0

    for component, status in results.items():
        icon = "[OK]" if status else "[X]"
        print(f"  {icon} {component}")

    print(f"\n  Score: {passed}/{total} ({percentage:.0f}%)")

    if percentage >= 80:
        print("\n  *** SYSTEM READY FOR TESTING ***")
        print("  The core components are properly implemented.")
    elif percentage >= 60:
        print("\n  *** SYSTEM PARTIALLY READY ***")
        print("  Some components need attention before full testing.")
    else:
        print("\n  *** SYSTEM NEEDS MORE WORK ***")
        print("  Please complete the implementation of core components.")

    # Provide next steps
    print("\n[NEXT STEPS]")
    if not results.get("Dependencies", True):
        print("  1. Install missing dependencies: pip install -r requirements.txt")
    if not results.get("Infrastructure", True):
        print("  2. Check infrastructure files are properly created")
    if not results.get("OCR Backends", True):
        print("  3. Verify OCR backend implementations")
    if percentage >= 80:
        print("  1. Copy .env.example to .env and configure")
        print("  2. Start services: docker-compose up -d")
        print("  3. Run tests: python test_ocr_system.py")


def main():
    """Main validation function."""
    print("\n" + "=" * 60)
    print("        Ablage-System OCR - System Validation")
    print("              Enterprise Document Processing")
    print("=" * 60)

    results = {
        "Project Structure": validate_structure(),
        "Dependencies": validate_dependencies(),
        "OCR Backends": validate_ocr_backends(),
        "Routing Logic": validate_routing(),
        "Infrastructure": validate_infrastructure(),
        "German Support": validate_german_support()
    }

    generate_summary(results)

    print("\n*** Validation complete! ***\n")

    # Return exit code based on results
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())