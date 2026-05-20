#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path

# Professional Hygiene Policy: Allowed entries in Root
ALLOWED_ROOT_ENTRIES = {
    ".git", ".github", ".vscode", ".gitignore", ".env.example", ".env.rag.example",
    ".env.production.example", "app", "frontend", "infrastructure", "docs",
    "tests", "scripts", "alembic", "alembic.ini", "Dockerfile", "docker-compose.yml",
    "docker-compose.dev.yml", "docker-compose.prod.yml", "docker-compose.rag.yaml",
    "pyproject.toml", "package.json", "package-lock.json", "requirements.txt",
    "requirements-dev.txt", "requirements-gpu.txt", "README.md", "CLAUDE.md",
    "ARCHITECTURE.md", "DEPLOYMENT.md", "LICENSE", "VERSION", "CONTRIBUTING.md",
    "SECURITY.md", "CHANGELOG.md", "CONVENTIONS.md", "Makefile", "jest.config.js",
    "playwright.config.ts", "tsconfig.json", "node_modules", "venv", ".venv",
    ".kiro", ".mcp.json", ".claude", ".claudeignore", ".devcontainer",
    ".dockerignore", ".editorconfig", ".eslintrc.js", ".hypothesis",
    ".markdownlint.json", ".playwright-mcp", ".pre-commit-config.yaml",
    ".pytest_cache", ".releaserc.json", ".secrets.baseline", ".yamllint.yml",
    "bootstrap_project.py", "startup.sh", "jupyter.config.py", ".env"
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
