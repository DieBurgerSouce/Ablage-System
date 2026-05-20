#!/usr/bin/env python3
"""
Test-Script für Orchestration-Komponenten.
Testet die grundlegende Funktionalität aller Komponenten.
"""

import sys
import os
from pathlib import Path

# Add current directory to path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Direct imports
from .task_classifier import TaskClassifier, ModelTier
from .context_compressor import ContextCompressor, CompressionLevel
from .decision_cache import DecisionCache
from .quality_gate import QualityGate, QualityLevel


def test_task_classifier():
    """Testet den TaskClassifier."""
    print("🧪 Teste TaskClassifier...")

    classifier = TaskClassifier()

    # Test Cases
    test_cases = [
        ("Implementiere neue API Endpoints für User-Management", ModelTier.SONNET_CAPABLE),
        ("Architektur für Multi-Tenant OCR System", ModelTier.OPUS_REQUIRED),
        ("Formatiere Python Code nach PEP 8", ModelTier.HAIKU_SUFFICIENT),
        ("Security Review für Authentication", ModelTier.OPUS_REQUIRED),
        ("Sortiere Imports in allen Dateien", ModelTier.HAIKU_SUFFICIENT),
        ("DeepSeek OCR Agent Integration", ModelTier.OPUS_REQUIRED),
        ("Pytest Tests für Service Layer", ModelTier.SONNET_CAPABLE),
        ("GPU Memory Management optimieren", ModelTier.OPUS_REQUIRED),
        ("Type-Hints zu Funktionen hinzufügen", ModelTier.HAIKU_SUFFICIENT),
        ("Komplexe Bug-Analyse in Core-Modul", ModelTier.OPUS_REQUIRED),
    ]

    correct = 0
    for task, expected in test_cases:
        result = classifier.classify(task)
        if result.tier == expected:
            print(f"  ✅ {task[:50]}... → {result.tier.value}")
            correct += 1
        else:
            print(f"  ❌ {task[:50]}... → {result.tier.value} (erwartet: {expected.value})")

    print(f"  📊 {correct}/{len(test_cases)} Tests bestanden ({correct/len(test_cases)*100:.0f}%)")
    return correct == len(test_cases)


def test_context_compressor():
    """Testet den ContextCompressor."""
    print("\n🧪 Teste ContextCompressor...")

    compressor = ContextCompressor()

    # Mock Context
    mock_context = {
        "task": "Implementiere User Service",
        "files": {
            "app/services/user_service.py": "class UserService: pass",
            "app/models/user.py": "class User: pass",
            ".env": "SECRET_KEY=abc123",
            "tests/test_user.py": "def test_user(): pass",
        },
        "affected_files": ["app/services/user_service.py"],
    }

    # Test verschiedene Kompression-Level
    models = ["opus", "sonnet", "haiku"]

    for model in models:
        result = compressor.compress(mock_context, model, "implementation")
        print(f"  📦 {model}: {result.token_estimate} Tokens, Ratio: {result.compression_ratio:.1%}")

        # Prüfe dass Secrets gefiltert wurden
        if ".env" in result.included_files:
            print(f"    ❌ Secrets nicht gefiltert!")
            return False
        else:
            print(f"    ✅ Secrets korrekt gefiltert")

    return True


def test_decision_cache():
    """Testet den DecisionCache."""
    print("\n🧪 Teste DecisionCache...")

    cache = DecisionCache()

    # Test Store
    decision_hash = cache.store(
        task_description="Implementiere User Authentication",
        decision="Verwende FastAPI-Users mit JWT",
        reasoning="Bewährte Lösung mit guter Security",
        affected_patterns=["authentication", "jwt", "fastapi"],
        affected_files=["app/auth/", "app/models/user.py"],
        confidence=0.9,
        tags=["auth", "security"]
    )

    print(f"  💾 Entscheidung gespeichert: {decision_hash}")

    # Test Find
    relevant = cache.find_relevant(
        "Implementiere Login System",
        affected_files=["app/auth/login.py"],
        tags=["auth"]
    )

    if relevant:
        print(f"  🔍 {len(relevant)} relevante Entscheidungen gefunden")
        print(f"    📝 {relevant[0].task_description}")
        success = True
    else:
        print(f"  ❌ Keine relevanten Entscheidungen gefunden")
        success = False

    # Test Stats
    stats = cache.get_stats()
    print(f"  📊 Cache Stats: {stats['total_entries']} Einträge, Hit-Rate: {stats['hit_rate']}")

    return success


def test_quality_gate():
    """Testet das QualityGate."""
    print("\n🧪 Teste QualityGate...")

    gate = QualityGate()

    # Test Cases
    test_codes = [
        # Guter Code
        ("""
def add_user(name: str, email: str) -> User:
    \"\"\"Fügt einen neuen Benutzer hinzu.\"\"\"
    return User(name=name, email=email)
""", "good_code.py", True),

        # Code ohne Type-Hints
        ("""
def add_user(name, email):
    return User(name=name, email=email)
""", "bad_types.py", False),

        # Code mit englischen Messages
        ("""
def validate_user(user):
    if not user:
        raise ValueError("User not found")
    return True
""", "english_msg.py", False),

        # Code mit Security-Problem
        ("""
import os
def run_command(cmd):
    os.system(cmd)  # Gefährlich!
""", "security_issue.py", False),
    ]

    passed_tests = 0

    for code, filename, should_pass in test_codes:
        result = gate.validate(code, filename, "sonnet")

        if (result.level == QualityLevel.PASSED) == should_pass:
            status = "✅" if should_pass else "✅ (korrekt abgelehnt)"
            passed_tests += 1
        else:
            status = "❌"

        print(f"  {status} {filename}: {result.level.value}")
        if result.checks_failed:
            print(f"    Fehler: {result.checks_failed[0]}")

    print(f"  📊 {passed_tests}/{len(test_codes)} Tests bestanden")
    return passed_tests == len(test_codes)


def main():
    """Führt alle Tests aus."""
    print("🚀 Teste Multi-Model Orchestration Komponenten\n")

    tests = [
        ("TaskClassifier", test_task_classifier),
        ("ContextCompressor", test_context_compressor),
        ("DecisionCache", test_decision_cache),
        ("QualityGate", test_quality_gate),
    ]

    results = []

    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"  ❌ Fehler in {name}: {e}")
            results.append((name, False))

    # Zusammenfassung
    print(f"\n📋 Test-Zusammenfassung:")
    passed = sum(1 for _, success in results if success)

    for name, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {name}")

    print(f"\n🎯 Gesamt: {passed}/{len(results)} Komponenten funktionieren korrekt")

    if passed == len(results):
        print("🎉 Alle Tests bestanden! Phase 1 Core Infrastructure ist bereit.")
    else:
        print("⚠️  Einige Tests fehlgeschlagen. Bitte Probleme beheben.")

    return passed == len(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
