# -*- coding: utf-8 -*-
"""
Query Expansion Service.

Erweitert Suchanfragen mit deutschen Geschäftsbegriff-Synonymen.
"""

import json
import re
from pathlib import Path
from typing import Any, List, Dict, Set, Optional, Tuple
from functools import lru_cache

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class QueryExpansionService:
    """
    Service für Query-Expansion mit Synonymen.

    Features:
    - Ladet Synonym-Woerterbuch aus JSON
    - Bidirektionale Synonym-Suche (A->B und B->A)
    - Normalisierung (Umlaute, Gross/Kleinschreibung)
    - Kategorisierte Synonyme (Dokumente, Finanzen, etc.)
    """

    _instance: Optional["QueryExpansionService"] = None
    _synonyms: Dict[str, Dict[str, List[str]]] = {}
    _reverse_index: Dict[str, Set[str]] = {}

    def __new__(cls) -> "QueryExpansionService":
        """Singleton-Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_synonyms()
        return cls._instance

    def _load_synonyms(self) -> None:
        """Ladet Synonym-Woerterbuch aus JSON-Datei."""
        synonyms_path = Path(__file__).parent.parent / "data" / "synonyms" / "business_german.json"

        try:
            if synonyms_path.exists():
                with open(synonyms_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Filtere Metadaten-Keys
                self._synonyms = {
                    k: v for k, v in data.items()
                    if not k.startswith("_")
                }

                # Baue Reverse-Index auf
                self._build_reverse_index()

                logger.info(
                    "synonyms_loaded",
                    categories=len(self._synonyms),
                    total_terms=sum(len(cat) for cat in self._synonyms.values()),
                )
            else:
                logger.warning("synonyms_file_not_found", path=str(synonyms_path))

        except Exception as e:
            logger.error("synonyms_load_error", **safe_error_log(e))
            self._synonyms = {}

    def _build_reverse_index(self) -> None:
        """
        Baut bidirektionalen Index auf.

        Für jeden Begriff (Hauptbegriff und Synonyme) wird
        eine Menge aller zugehoerigen Begriffe gespeichert.
        """
        self._reverse_index = {}

        for category, terms in self._synonyms.items():
            for main_term, synonyms in terms.items():
                # Normalisiere Hauptbegriff
                normalized_main = self._normalize(main_term)

                # Sammle alle Begriffe für diese Gruppe
                all_terms = {normalized_main}
                for syn in synonyms:
                    all_terms.add(self._normalize(syn))

                # Trage alle Begriffe in den Index ein
                for term in all_terms:
                    if term not in self._reverse_index:
                        self._reverse_index[term] = set()
                    self._reverse_index[term].update(all_terms - {term})

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalisiert Text für Synonym-Lookup."""
        text = text.lower().strip()
        # Umlaute normalisieren
        replacements = {
            "ae": "ae", "ä": "ae",
            "oe": "oe", "ö": "oe",
            "ue": "ue", "ü": "ue",
            "ss": "ss", "ß": "ss",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def get_synonyms(self, term: str) -> List[str]:
        """
        Gibt Synonyme für einen Begriff zurück.

        Args:
            term: Der zu erweiternde Begriff

        Returns:
            Liste von Synonymen (ohne den urspruenglichen Begriff)
        """
        normalized = self._normalize(term)
        synonyms = self._reverse_index.get(normalized, set())
        return list(synonyms)

    def expand_query(
        self,
        query: str,
        max_expansions_per_term: int = 3
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Erweitert eine Suchanfrage mit Synonymen.

        Args:
            query: Die urspruengliche Suchanfrage
            max_expansions_per_term: Maximale Synonyme pro Begriff

        Returns:
            Tuple aus:
            - Erweiterter Query-String (für PostgreSQL Volltext)
            - Liste der Erweiterungen für UI-Anzeige
        """
        # Tokenize Query
        tokens = self._tokenize(query)
        expanded_parts = []
        expansions_info = []

        for token in tokens:
            synonyms = self.get_synonyms(token)

            if synonyms:
                # Begrenzen auf max_expansions_per_term
                selected_synonyms = synonyms[:max_expansions_per_term]

                # Baue OR-Gruppe: (original | syn1 | syn2)
                all_terms = [token] + selected_synonyms
                expanded_parts.append(f"({' | '.join(all_terms)})")

                expansions_info.append({
                    "original": token,
                    "synonyms": selected_synonyms,
                })
            else:
                expanded_parts.append(token)

        expanded_query = " & ".join(expanded_parts)

        return expanded_query, expansions_info

    def expand_query_simple(
        self,
        query: str,
        max_expansions_per_term: int = 3
    ) -> str:
        """
        Vereinfachte Query-Expansion für allgemeine Suche.

        Gibt einen erweiterten Such-String zurück, der für
        LIKE-Suche oder einfache Volltext-Suche geeignet ist.

        Args:
            query: Die urspruengliche Suchanfrage
            max_expansions_per_term: Maximale Synonyme pro Begriff

        Returns:
            String mit allen Suchbegriffen (Original + Synonyme)
        """
        tokens = self._tokenize(query)
        all_terms = set(tokens)

        for token in tokens:
            synonyms = self.get_synonyms(token)[:max_expansions_per_term]
            all_terms.update(synonyms)

        return " ".join(all_terms)

    def get_expansion_preview(self, query: str) -> Dict[str, Any]:
        """
        Gibt eine Vorschau der Query-Expansion zurück.

        Nützlich für UI-Feedback, bevor die Suche ausgeführt wird.

        Args:
            query: Die Suchanfrage

        Returns:
            Dict mit original, expanded und expansions
        """
        expanded, expansions = self.expand_query(query)

        return {
            "original": query,
            "expanded": expanded,
            "expansions": expansions,
            "term_count": len(expansions),
        }

    @staticmethod
    def _tokenize(query: str) -> List[str]:
        """Zerlegt Query in Tokens."""
        # Entferne Sonderzeichen ausser Umlaute
        query = re.sub(r'[^\w\säöüÄÖÜß]', ' ', query)
        # Teile in Worte und filtere leere Strings
        tokens = [t.strip().lower() for t in query.split() if t.strip()]
        return tokens

    def get_category_terms(self, category: str) -> Dict[str, List[str]]:
        """
        Gibt alle Begriffe einer Kategorie zurück.

        Args:
            category: Name der Kategorie (z.B. "document_types")

        Returns:
            Dict mit Hauptbegriffen und ihren Synonymen
        """
        return self._synonyms.get(category, {})

    def get_all_categories(self) -> List[str]:
        """Gibt alle verfügbaren Kategorien zurück."""
        return list(self._synonyms.keys())

    def reload_synonyms(self) -> None:
        """Laedt Synonyme neu (nach Datei-Änderung)."""
        self._load_synonyms()


# Singleton-Instanz
query_expansion_service = QueryExpansionService()
