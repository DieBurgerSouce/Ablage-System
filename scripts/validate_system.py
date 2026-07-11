#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path

# Professional Hygiene Policy: Allowed entries in Root
# Synchronisiert 2026-07-11 (Root-Cleanup): jest.config.js/.eslintrc.js entfernt
# (geloescht), reale Compose-Varianten/Configs/Verzeichnisse ergaenzt.
ALLOWED_ROOT_ENTRIES = {
    # Git/CI/Tooling
    ".git", ".githooks", ".github", ".gitignore", ".gitattributes", ".vscode",
    ".devcontainer", ".kiro", ".mcp.json", ".claude", ".claude-flow", ".swarm",
    ".claudeignore", ".pre-commit-config.yaml", ".releaserc.json",
    ".secrets.baseline", ".yamllint.yml", ".prettierignore", ".markdownlint.json",
    ".editorconfig", ".dockerignore", ".playwright-mcp",
    # Env-Vorlagen + lokale Laufzeit-Config
    ".env", ".env.example", ".env.rag.example", ".env.production.example",
    # Quellcode + Infrastruktur
    "app", "frontend", "infrastructure", "docs", "tests", "scripts", "alembic",
    "alembic.ini", "docker", "config", "security", "examples", "notebooks",
    "Dockerfile", "docker-compose.yml", "docker-compose.dev.yml",
    "docker-compose.prod.yml", "docker-compose.rag.yaml", "docker-compose.test.yml",
    "docker-compose.override.yml", "docker-compose.airgap.yml",
    "docker-compose.canary.yml", "docker-compose.cpu-ocr.yml",
    # Build-/Paket-Konfiguration
    "pyproject.toml", "pytest.ini", "package.json", "package-lock.json",
    "requirements.txt", "requirements-dev.txt", "requirements-gpu.txt",
    "playwright.config.ts", "tsconfig.json", "Makefile",
    "bootstrap_project.py", "startup.sh", "jupyter.config.py", "import_lexware.ps1",
    # Standard-Doku
    "README.md", "CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "DEPLOYMENT.md",
    "API_REFERENCE.md", "LICENSE", "VERSION", "CONTRIBUTING.md", "SECURITY.md",
    "CHANGELOG.md", "CONVENTIONS.md", "CODE_OF_CONDUCT.md",
    # Knowledge-Layer (AGENTS.md-Kontrakt)
    "Static_Knowledge", "Dynamic_Knowledge", "Meta_Layer", "Execution_Layer",
    "Relations", "Skills", "Trainings_Data",
    # Laufzeit-/Datenverzeichnisse (nie committen, aber legitim auf Platte)
    "data", "logs", "uploads", "models", "backups", "Firmendaten", "ARCHIVE",
    "test_documents", "node_modules", "venv", ".venv",
    # Generierte Caches
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".hypothesis",
    # Parallel-Session-Worktrees + Plugins
    ".hardening-worktrees", "plan-breakdown-plugin",
    # Debug-/Report-Verzeichnisse (Aufraeumkandidaten, separater Scope)
    "browser-diagnostics", "temp_paddle_test", "temp_results",
    "playwright-report", "test-results",
}

def check_root_hygiene():
    print("🔍 Checking Root Hygiene Environment...")
    root_path = Path(".")
    violations = []

    for item in root_path.iterdir():
        if item.name not in ALLOWED_ROOT_ENTRIES:
            violations.append(item.name)

    if violations:
        print(f"❌ VIOLATION: Unsanctioned entries in root: {violations}")
        return False
    print("✅ Root hygiene passed.")
    return True

def check_absolute_paths():
    print("🔍 Searching for leaked absolute paths (C:\\Users\\...)...")
    violations = []
    # Identify the user path to detect (simulated for enterprise safety)
    pattern = re.compile(r"[A-Z]:\\Users\\[a-zA-Z0-9_\-\\]+")

    # We only scan tracked files or common config types to be fast
    for ext in [".py", ".json", ".yaml", ".yml", ".md", ".sh", ".bat"]:
        for path in Path(".").rglob(f"*{ext}"):
            if any(part in str(path) for part in ["venv", "node_modules", ".git", ".next", "validate_system.py"]):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if pattern.search(content):
                    violations.append(str(path))
            except Exception:
                pass

    if violations:
        print(f"❌ VIOLATION: Absolute paths found in: {violations[:5]}...")
        return False
    print("✅ No absolute paths detected.")
    return True

def main():
    print("🚀 Running Global Tier-1 Professional Pre-Push Sync...")

    h_pass = check_root_hygiene()
    p_pass = check_absolute_paths()

    if not (h_pass and p_pass):
        print("\n🛑 VALIDATION FAILED. Please clean up before pushing.")
        sys.exit(1)

    print("\n🌟 ALL SYSTEMS NOMINAL. Repository is Enterprise-Ready.")
    sys.exit(0)

if __name__ == "__main__":
    main()
