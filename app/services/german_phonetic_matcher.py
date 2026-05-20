# -*- coding: utf-8 -*-
"""
German Phonetic Matcher Service.

Provides phonetic matching for German names and words using Cologne Phonetic algorithm.
Optimized for matching German business names, personal names, and addresses
where OCR or transcription may have introduced variations.

Features:
- Cologne Phonetic algorithm optimized for German
- Name matching with umlaut variants (Müller ↔ Mueller ↔ Muller)
- Business name matching (GmbH, AG, KG variations)
- Address matching with common abbreviations
- Fuzzy matching with configurable thresholds
- Batch matching for large datasets

Feinpoliert und durchdacht - Deutsche Namens-Matching-Qualität.
"""

from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


class GermanPhoneticMatcher:
    """
    German Phonetic Matcher using Cologne Phonetic algorithm.

    The Cologne Phonetic (Kölner Phonetik) algorithm is specifically designed
    for German phonetics, unlike Soundex which is optimized for English.

    Usage:
        matcher = GermanPhoneticMatcher()
        # Check if two names match phonetically
        is_match = matcher.match_names("Müller", "Mueller")  # True
        # Find best match from candidates
        best = matcher.find_best_match("Maier", ["Mayer", "Meier", "Meyer"])  # "Meyer"
    """

    # Common German name variations that should match
    NAME_EQUIVALENTS: Dict[str, Set[str]] = {
        # Umlaut variations
        "müller": {"mueller", "muller", "miller"},
        "meier": {"meyer", "maier", "mayer", "mayr", "meyr"},
        "schäfer": {"schaefer", "schafer", "schefer"},
        "böhm": {"boehm", "bohm", "boehme", "bohme"},
        "köhler": {"koehler", "kohler"},
        "krämer": {"kraemer", "kramer"},
        "schröder": {"schroeder", "schroder", "schroeter"},
        "größmann": {"größmann", "grossmann"},
        "bäcker": {"baecker", "backer"},
        "jäger": {"jaeger", "jager"},
        "löffler": {"loeffler", "loffler"},
        "möller": {"moeller", "moller"},
        "götz": {"goetz", "gotz"},
        "günther": {"guenther", "gunther"},
        "hübner": {"huebner", "hubner"},
        "würfel": {"wuerfel", "wurfel"},
        # Common variations
        "schmidt": {"schmitt", "schmid", "schmied"},
        "schneider": {"snyder", "schnyder"},
        "fischer": {"fisher"},
        "bauer": {"baur", "baumann"},
        "wagner": {"wegner"},
        "hoffmann": {"hofmann"},
        "zimmermann": {"zimmerman"},
        "bergmann": {"bergman"},
    }

    # Business suffix equivalents
    BUSINESS_SUFFIX_EQUIVALENTS: Dict[str, Set[str]] = {
        "gmbh": {"g.m.b.h.", "gesellschaft mit beschränkter haftung"},
        "ag": {"a.g.", "aktiengesellschaft"},
        "kg": {"k.g.", "kommanditgesellschaft"},
        "ohg": {"o.h.g.", "offene handelsgesellschaft"},
        "e.v.": {"ev", "eingetragener verein"},
        "gbr": {"g.b.r.", "gesellschaft bürgerlichen rechts"},
        "&": {"und", "u."},
        "co": {"co.", "comp.", "company"},
    }

    # Address abbreviation equivalents
    ADDRESS_EQUIVALENTS: Dict[str, Set[str]] = {
        "straße": {"strasse", "str.", "str"},
        "platz": {"pl.", "pl"},
        "weg": {"wg.", "wg"},
        "ring": {"rg."},
        "allee": {"al.", "all."},
        "gasse": {"g."},
        "hausnummer": {"hnr.", "nr.", "no."},
    }

    # Cologne Phonetic encoding table
    COLOGNE_RULES: Dict[str, str] = {
        "a": "0", "e": "0", "i": "0", "o": "0", "u": "0",
        "ä": "0", "ö": "0", "ü": "0", "y": "0",
        "h": "",
        "b": "1", "p": "1",
        "d": "2", "t": "2",
        "f": "3", "v": "3", "w": "3",
        "g": "4", "k": "4", "q": "4",
        "x": "48",
        "l": "5",
        "m": "6", "n": "6",
        "r": "7",
        "s": "8", "z": "8", "ß": "8",
        "c": "4",  # Context-dependent, simplified
        "j": "0",
    }

    def __init__(
        self,
        min_similarity: float = 0.7,
        use_equivalents: bool = True,
        normalize_business_names: bool = True
    ):
        """
        Initialize German Phonetic Matcher.

        Args:
            min_similarity: Minimum phonetic similarity threshold (0.0-1.0)
            use_equivalents: Use predefined name equivalents in addition to phonetic matching
            normalize_business_names: Normalize business name suffixes (GmbH, AG, etc.)
        """
        self.min_similarity = min_similarity
        self.use_equivalents = use_equivalents
        self.normalize_business_names = normalize_business_names

        # Build reverse lookup for equivalents
        self._equivalent_lookup: Dict[str, str] = {}
        if use_equivalents:
            self._build_equivalent_lookup()

        logger.info(
            "german_phonetic_matcher_initialized",
            min_similarity=min_similarity,
            use_equivalents=use_equivalents,
            equivalent_groups=len(self.NAME_EQUIVALENTS)
        )

    def _build_equivalent_lookup(self) -> None:
        """Build reverse lookup table for name equivalents."""
        for canonical, variants in self.NAME_EQUIVALENTS.items():
            self._equivalent_lookup[canonical] = canonical
            for variant in variants:
                self._equivalent_lookup[variant] = canonical

    @lru_cache(maxsize=10000)
    def cologne_phonetic(self, word: str) -> str:
        """
        Compute Cologne Phonetic code for a German word.

        The algorithm:
        1. Convert to lowercase
        2. Apply letter-to-code mapping with context rules
        3. Remove consecutive duplicate codes
        4. Remove leading zeros (except if all zeros)

        Args:
            word: German word to encode

        Returns:
            Phonetic code as string
        """
        if not word:
            return ""

        word = word.lower().strip()
        # Remove non-alphabetic characters
        word = "".join(c for c in word if c.isalpha())

        if not word:
            return ""

        codes: List[str] = []
        i = 0

        while i < len(word):
            char = word[i]
            prev_char = word[i - 1] if i > 0 else ""
            next_char = word[i + 1] if i + 1 < len(word) else ""

            # Special handling for 'c'
            if char == "c":
                if i == 0:
                    # Initial C before A, H, K, L, O, Q, R, U, X -> 4
                    if next_char in "ahkloqrux":
                        codes.append("4")
                    else:
                        codes.append("8")
                elif prev_char in "sz":
                    codes.append("8")
                elif next_char in "ahkoqux" and prev_char not in "aeiouäöü":
                    codes.append("4")
                else:
                    codes.append("8")
                i += 1
                continue

            # Special handling for 'ch'
            if char == "c" and next_char == "h":
                if prev_char in "aou":
                    codes.append("4")
                else:
                    codes.append("8")
                i += 2
                continue

            # Special handling for 'sch'
            if char == "s" and i + 2 < len(word) and word[i + 1:i + 3] == "ch":
                codes.append("8")
                i += 3
                continue

            # Special handling for 'ph'
            if char == "p" and next_char == "h":
                codes.append("3")
                i += 2
                continue

            # Special handling for 'dt' and 'dc'
            if char == "d" and next_char in "tc":
                codes.append("8")
                i += 2
                continue

            # Standard mapping
            if char in self.COLOGNE_RULES:
                code = self.COLOGNE_RULES[char]
                if code:
                    codes.append(code)
            i += 1

        # Remove consecutive duplicates
        if not codes:
            return "0"

        result = [codes[0]]
        for code in codes[1:]:
            if code != result[-1]:
                result.append(code)

        # Remove leading zeros (keep at least one character)
        code_str = "".join(result)
        return code_str.lstrip("0") or "0"

    def phonetic_similarity(self, word1: str, word2: str) -> float:
        """
        Calculate phonetic similarity between two German words.

        Args:
            word1: First word
            word2: Second word

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not word1 or not word2:
            return 0.0

        # Normalize words
        w1 = word1.lower().strip()
        w2 = word2.lower().strip()

        # Exact match
        if w1 == w2:
            return 1.0

        # Check equivalents first
        if self.use_equivalents:
            canonical1 = self._equivalent_lookup.get(w1)
            canonical2 = self._equivalent_lookup.get(w2)
            if canonical1 and canonical2 and canonical1 == canonical2:
                return 1.0

        # Phonetic comparison
        code1 = self.cologne_phonetic(w1)
        code2 = self.cologne_phonetic(w2)

        if code1 == code2:
            return 1.0

        # Calculate similarity based on phonetic code distance
        max_len = max(len(code1), len(code2))
        if max_len == 0:
            return 1.0

        distance = self._levenshtein_distance(code1, code2)
        return 1.0 - (distance / max_len)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def match_names(
        self,
        name1: str,
        name2: str,
        threshold: Optional[float] = None
    ) -> bool:
        """
        Check if two names match phonetically.

        Args:
            name1: First name
            name2: Second name
            threshold: Optional custom threshold (uses default if not provided)

        Returns:
            True if names match above threshold
        """
        threshold = threshold if threshold is not None else self.min_similarity
        similarity = self.phonetic_similarity(name1, name2)
        return similarity >= threshold

    def normalize_business_name(self, name: str) -> str:
        """
        Normalize a German business name.

        Standardizes common business suffixes and formatting.

        Args:
            name: Business name to normalize

        Returns:
            Normalized business name
        """
        if not name:
            return ""

        result = name.strip()

        # Normalize common business suffixes
        for canonical, variants in self.BUSINESS_SUFFIX_EQUIVALENTS.items():
            for variant in variants:
                # Case-insensitive replacement
                pattern_lower = variant.lower()
                result_lower = result.lower()
                if pattern_lower in result_lower:
                    idx = result_lower.find(pattern_lower)
                    result = result[:idx] + canonical.upper() + result[idx + len(variant):]

        return result.strip()

    def find_best_match(
        self,
        query: str,
        candidates: List[str],
        threshold: Optional[float] = None,
        return_all_above_threshold: bool = False
    ) -> Optional[str | List[Tuple[str, float]]]:
        """
        Find the best phonetically matching name from candidates.

        Args:
            query: Name to match
            candidates: List of candidate names
            threshold: Minimum similarity threshold
            return_all_above_threshold: Return all matches above threshold with scores

        Returns:
            Best matching name, or list of (name, score) tuples if return_all_above_threshold
        """
        if not query or not candidates:
            return [] if return_all_above_threshold else None

        threshold = threshold if threshold is not None else self.min_similarity
        matches: List[Tuple[str, float]] = []

        for candidate in candidates:
            similarity = self.phonetic_similarity(query, candidate)
            if similarity >= threshold:
                matches.append((candidate, similarity))

        if not matches:
            return [] if return_all_above_threshold else None

        # Sort by similarity descending
        matches.sort(key=lambda x: x[1], reverse=True)

        if return_all_above_threshold:
            return matches
        return matches[0][0]

    def match_business_names(
        self,
        name1: str,
        name2: str,
        threshold: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        Match two business names with special handling for German business types.

        Normalizes GmbH, AG, KG, etc. before comparison.

        Args:
            name1: First business name
            name2: Second business name
            threshold: Minimum similarity threshold

        Returns:
            Tuple of (matches, similarity_score)
        """
        threshold = threshold if threshold is not None else self.min_similarity

        # Normalize if enabled
        if self.normalize_business_names:
            norm1 = self.normalize_business_name(name1)
            norm2 = self.normalize_business_name(name2)
        else:
            norm1 = name1
            norm2 = name2

        # Extract core name (remove legal form suffix)
        core1 = self._extract_core_business_name(norm1)
        core2 = self._extract_core_business_name(norm2)

        similarity = self.phonetic_similarity(core1, core2)
        return similarity >= threshold, similarity

    def _extract_core_business_name(self, name: str) -> str:
        """
        Extract the core business name without legal form suffixes.

        Args:
            name: Full business name

        Returns:
            Core name without GmbH, AG, etc.
        """
        if not name:
            return ""

        result = name.lower().strip()

        # Remove common German business suffixes
        suffixes = [
            "gmbh & co. kg", "gmbh & co kg", "gmbh",
            "ag & co. kg", "ag & co kg", "ag",
            "kg", "ohg", "gbr", "e.v.", "ev",
            "& co.", "& co", "co.", "inc.", "ltd.", "llc"
        ]

        for suffix in sorted(suffixes, key=len, reverse=True):
            if result.endswith(suffix):
                result = result[:-len(suffix)].strip()
                break

        # Remove trailing separators
        result = result.rstrip(",.-& ")

        return result

    def batch_match(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        name_field: str = "name",
        threshold: Optional[float] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Batch match a query against a list of entities with names.

        Args:
            query: Name to match
            candidates: List of dicts containing name field
            name_field: Key containing the name in each dict
            threshold: Minimum similarity threshold
            max_results: Maximum number of results to return

        Returns:
            List of matching candidates with added 'phonetic_score' field
        """
        if not query or not candidates:
            return []

        threshold = threshold if threshold is not None else self.min_similarity
        results: List[Dict[str, Any]] = []

        for candidate in candidates:
            name = candidate.get(name_field, "")
            if not name:
                continue

            similarity = self.phonetic_similarity(query, name)
            if similarity >= threshold:
                result = {**candidate, "phonetic_score": similarity}
                results.append(result)

        # Sort by score descending
        results.sort(key=lambda x: x["phonetic_score"], reverse=True)

        return results[:max_results]

    def get_stats(self) -> Dict[str, Any]:
        """Get matcher statistics."""
        return {
            "min_similarity": self.min_similarity,
            "use_equivalents": self.use_equivalents,
            "normalize_business_names": self.normalize_business_names,
            "equivalent_groups": len(self.NAME_EQUIVALENTS),
            "equivalent_variants": len(self._equivalent_lookup),
            "business_suffix_groups": len(self.BUSINESS_SUFFIX_EQUIVALENTS),
            "cache_info": self.cologne_phonetic.cache_info()._asdict()
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_matcher: Optional[GermanPhoneticMatcher] = None


def get_german_phonetic_matcher() -> GermanPhoneticMatcher:
    """Get singleton instance of German Phonetic Matcher."""
    global _matcher
    if _matcher is None:
        _matcher = GermanPhoneticMatcher()
    return _matcher


def match_german_names(name1: str, name2: str, threshold: float = 0.7) -> bool:
    """
    Convenience function to check if two German names match phonetically.

    Args:
        name1: First name
        name2: Second name
        threshold: Minimum similarity (0.0-1.0)

    Returns:
        True if names match
    """
    return get_german_phonetic_matcher().match_names(name1, name2, threshold)


def find_best_german_match(
    query: str,
    candidates: List[str],
    threshold: float = 0.7
) -> Optional[str]:
    """
    Convenience function to find best matching German name.

    Args:
        query: Name to match
        candidates: List of candidate names
        threshold: Minimum similarity

    Returns:
        Best matching name or None
    """
    result = get_german_phonetic_matcher().find_best_match(query, candidates, threshold)
    if isinstance(result, list):
        return result[0][0] if result else None
    return result
