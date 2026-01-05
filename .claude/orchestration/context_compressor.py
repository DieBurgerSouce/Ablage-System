"""
Context Compressor für Multi-Model Orchestration.

Komprimiert Kontext für verschiedene Claude-Modelle:
- Opus: Vollständiger Kontext
- Sonnet: Relevanter Kontext mit Patterns
- Haiku: Minimaler Kontext mit Anweisungen
"""

import json
import fnmatch
from dataclasses import dataclass
from typing import Dict, List, Any, Set
from enum import Enum
from pathlib import Path


class CompressionLevel(Enum):
    """Kompressions-Level für verschiedene Modelle."""
    FULL = "full"           # Für Opus - alles
    STANDARD = "standard"   # Für Sonnet - relevanter Kontext
    MINIMAL = "minimal"     # Für Haiku - nur Anweisungen


@dataclass
class CompressedContext:
    """Komprimierter Kontext für ein Modell."""
    content: str
    token_estimate: int
    included_files: List[str]
    excluded_files: List[str]
    compression_ratio: float
    metadata: Dict[str, Any]


class ContextCompressor:
    """Komprimiert Kontext für verschiedene Modelle."""

    # Token-Limits pro Modell (konservativ)
    TOKEN_LIMITS = {
        "opus": 180000,
        "sonnet": 180000,
        "haiku": 180000,
    }

    # Dateien die IMMER inkludiert werden
    ALWAYS_INCLUDE = [
        "CLAUDE.md",
        "pyproject.toml",
        "requirements*.txt",
        ".claude/steering/*.md",
        "README.md",
    ]

    # Dateien die NIE inkludiert werden (Sicherheit)
    NEVER_INCLUDE = [
        ".env",
        ".env.*",
        "**/secrets/**",
        "**/*_key*",
        "**/*_secret*",
        "**/*.log",
        "**/logs/**",
        "**/__pycache__/**",
        "**/node_modules/**",
        "**/.git/**",
        "**/venv/**",
        "**/*.pyc",
    ]

    # Relevante Patterns für Sonnet
    SONNET_RELEVANT_PATTERNS = [
        "app/services/**",
        "app/api/**",
        "app/models/**",
        "tests/**",
        "alembic/versions/**",
        "frontend/src/**",
        "Skills/**",
    ]

    # Task-spezifische Templates für Haiku
    HAIKU_TEMPLATES = {
        "format": "Formatiere den Code nach den Projekt-Standards.",
        "import": "Sortiere Imports nach isort-Regeln.",
        "type_hint": "Ergänze Type-Hints für alle Funktionen.",
        "boilerplate": "Erstelle Boilerplate nach Template.",
    }

    def compress(
        self,
        full_context: Dict[str, Any],
        target_model: str,
        task_type: str = "general"
    ) -> CompressedContext:
        """
        Komprimiert Kontext für das Zielmodell.

        Args:
            full_context: Vollständiger Kontext
            target_model: Zielmodell (opus/sonnet/haiku)
            task_type: Art der Aufgabe

        Returns:
            CompressedContext für das Modell
        """

        level = self._get_compression_level(target_model)

        if level == CompressionLevel.FULL:
            return self._compress_full(full_context)
        elif level == CompressionLevel.STANDARD:
            return self._compress_standard(full_context, task_type)
        else:
            return self._compress_minimal(full_context, task_type)

    def _get_compression_level(self, model: str) -> CompressionLevel:
        """Bestimmt Kompressions-Level basierend auf Modell."""
        if model == "opus":
            return CompressionLevel.FULL
        elif model == "sonnet":
            return CompressionLevel.STANDARD
        return CompressionLevel.MINIMAL

    def _compress_full(self, context: Dict) -> CompressedContext:
        """
        Voller Kontext für Opus (nur Secrets filtern).

        Args:
            context: Vollständiger Kontext

        Returns:
            CompressedContext mit gefiltertem Inhalt
        """
        # Filtere nur Secrets und gefährliche Dateien
        filtered = self._filter_secrets(context)
        content_str = self._serialize_context(filtered)

        return CompressedContext(
            content=content_str,
            token_estimate=self._estimate_tokens(content_str),
            included_files=list(filtered.get("files", {}).keys()),
            excluded_files=self._get_excluded_files(context, filtered),
            compression_ratio=1.0,
            metadata={"level": "full", "model": "opus"}
        )

    def _compress_standard(
        self,
        context: Dict,
        task_type: str
    ) -> CompressedContext:
        """
        Standard-Kompression für Sonnet.

        Args:
            context: Vollständiger Kontext
            task_type: Art der Aufgabe

        Returns:
            CompressedContext mit relevantem Inhalt
        """
        relevant_context = {
            "task": context.get("task"),
            "affected_files": context.get("affected_files", []),
            "relevant_files": self._extract_relevant_files(
                context.get("files", {}),
                context.get("affected_files", [])
            ),
            "patterns": self._extract_relevant_patterns(context, task_type),
            "cached_decisions": self._get_relevant_cache(task_type),
            "coding_standards": self._get_coding_standards(),
            "project_structure": self._get_project_structure(context),
        }

        content_str = self._serialize_context(relevant_context)

        return CompressedContext(
            content=content_str,
            token_estimate=self._estimate_tokens(content_str),
            included_files=list(relevant_context.get("relevant_files", {}).keys()),
            excluded_files=self._get_excluded_files(context, relevant_context),
            compression_ratio=0.4,
            metadata={"level": "standard", "model": "sonnet", "task_type": task_type}
        )

    def _compress_minimal(
        self,
        context: Dict,
        task_type: str
    ) -> CompressedContext:
        """
        Minimale Kompression für Haiku.

        Args:
            context: Vollständiger Kontext
            task_type: Art der Aufgabe

        Returns:
            CompressedContext mit minimalen Anweisungen
        """
        minimal_context = {
            "task": context.get("task"),
            "template": self._get_task_template(task_type),
            "example": self._get_example(task_type),
            "rules": self._get_basic_rules(),
            "affected_files": context.get("affected_files", [])[:3],  # Max 3 Dateien
        }

        content_str = self._serialize_context(minimal_context)

        return CompressedContext(
            content=content_str,
            token_estimate=self._estimate_tokens(content_str),
            included_files=minimal_context.get("affected_files", []),
            excluded_files=list(context.get("files", {}).keys()),
            compression_ratio=0.1,
            metadata={"level": "minimal", "model": "haiku", "task_type": task_type}
        )

    def _filter_secrets(self, context: Dict) -> Dict:
        """
        Entfernt sensible Daten aus Kontext.

        Args:
            context: Kontext zum Filtern

        Returns:
            Gefilterter Kontext
        """
        filtered = context.copy()

        # Filtere Dateien
        if "files" in filtered:
            safe_files = {}
            for file_path, content in filtered["files"].items():
                if not self._is_excluded_file(file_path):
                    # Filtere sensible Inhalte aus Datei-Content
                    safe_content = self._filter_sensitive_content(content)
                    safe_files[file_path] = safe_content
            filtered["files"] = safe_files

        # Filtere Environment Variables
        if "env" in filtered:
            filtered["env"] = {k: "***" for k in filtered["env"].keys()}

        return filtered

    def _is_excluded_file(self, file_path: str) -> bool:
        """Prüft ob Datei ausgeschlossen werden soll."""
        for pattern in self.NEVER_INCLUDE:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    def _filter_sensitive_content(self, content: str) -> str:
        """Filtert sensible Inhalte aus Text."""
        if not isinstance(content, str):
            return content

        # Einfache Regex-Filter für häufige Secrets
        import re

        # API Keys
        content = re.sub(r'api[_-]?key["\s]*[:=]["\s]*[a-zA-Z0-9_-]+', 'api_key="***"', content, flags=re.IGNORECASE)

        # Passwords
        content = re.sub(r'password["\s]*[:=]["\s]*[^\s"]+', 'password="***"', content, flags=re.IGNORECASE)

        # Tokens
        content = re.sub(r'token["\s]*[:=]["\s]*[a-zA-Z0-9_.-]+', 'token="***"', content, flags=re.IGNORECASE)

        return content

    def _extract_relevant_files(
        self,
        all_files: Dict[str, str],
        affected_files: List[str]
    ) -> Dict[str, str]:
        """Extrahiert relevante Dateien für Sonnet."""
        relevant = {}

        # Immer betroffene Dateien
        for file_path in affected_files:
            if file_path in all_files:
                relevant[file_path] = all_files[file_path]

        # Relevante Patterns
        for file_path, content in all_files.items():
            if self._is_excluded_file(file_path):
                continue

            for pattern in self.SONNET_RELEVANT_PATTERNS:
                if fnmatch.fnmatch(file_path, pattern):
                    relevant[file_path] = content
                    break

        # Immer inkludieren
        for file_path, content in all_files.items():
            for pattern in self.ALWAYS_INCLUDE:
                if fnmatch.fnmatch(file_path, pattern):
                    relevant[file_path] = content
                    break

        return relevant

    def _estimate_tokens(self, content: str) -> int:
        """Schätzt Token-Anzahl (grobe Approximation)."""
        return len(content) // 4

    def _serialize_context(self, context: Dict) -> str:
        """Serialisiert Kontext zu String."""
        return json.dumps(context, indent=2, ensure_ascii=False)

    def _extract_relevant_patterns(self, context: Dict, task_type: str) -> Dict:
        """Extrahiert relevante Code-Patterns."""
        return {
            "task_type": task_type,
            "common_patterns": ["FastAPI", "SQLAlchemy", "Pydantic", "pytest"],
        }

    def _get_relevant_cache(self, task_type: str) -> List[Dict]:
        """Holt relevante gecachte Entscheidungen."""
        # Placeholder - wird von DecisionCache implementiert
        return []

    def _get_coding_standards(self) -> Dict:
        """Lädt Coding-Standards aus Steering."""
        return {
            "type_hints": "required",
            "language": "de",
            "docstrings": "google_style",
            "imports": "isort",
            "formatting": "black",
        }

    def _get_project_structure(self, context: Dict) -> Dict:
        """Extrahiert Projekt-Struktur."""
        return {
            "backend": "FastAPI + SQLAlchemy",
            "frontend": "React + TypeScript",
            "database": "PostgreSQL",
            "testing": "pytest + Playwright",
        }

    def _get_task_template(self, task_type: str) -> str:
        """Holt Template für Aufgabentyp."""
        return self.HAIKU_TEMPLATES.get(task_type, "Führe die Aufgabe aus.")

    def _get_example(self, task_type: str) -> str:
        """Holt Beispiel für Aufgabentyp."""
        examples = {
            "format": "# Vorher\ndef func(x,y):\n    return x+y\n\n# Nachher\ndef func(x: int, y: int) -> int:\n    return x + y",
            "import": "# Vorher\nimport os\nfrom typing import List\nimport sys\n\n# Nachher\nimport os\nimport sys\nfrom typing import List",
        }
        return examples.get(task_type, "")

    def _get_basic_rules(self) -> List[str]:
        """Grundregeln für Haiku."""
        return [
            "Verwende deutsche Kommentare",
            "Füge Type-Hints hinzu",
            "Folge PEP 8",
            "Keine Secrets im Code",
        ]

    def _get_excluded_files(self, full: Dict, compressed: Dict) -> List[str]:
        """Berechnet ausgeschlossene Dateien."""
        full_files = set(full.get("files", {}).keys())
        included_files = set()

        if "files" in compressed:
            included_files.update(compressed["files"].keys())
        if "relevant_files" in compressed:
            included_files.update(compressed["relevant_files"].keys())

        return list(full_files - included_files)
