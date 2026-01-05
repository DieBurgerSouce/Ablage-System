#!/usr/bin/env python3
"""
Feature Type Detection Utility - Enterprise-Level v4.0

Analyzes feature descriptions and detects types (API, UI, DB, Service, etc.)
based on keyword matching.

Features:
- P0-10: TypedDict for proper type safety
- P0-11: Logging instead of silent pass
- P0-12: DRY - centralized score calculation
- P1-20: Whitespace sanitization
- P1-21: Unicode normalization (NFC)
- P1-22: Word-boundary keyword matching
- P2-27: Keyword caching (avoid repeated I/O)
- P2-28: Correct CLI exit codes

Author: Enterprise Fix Initiative v4.0
Date: 2026-01-04
"""

import json
import logging
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, TypedDict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TYPE DEFINITIONS (P0-10 FIX)
# ============================================================================

class FeatureAnalysis(TypedDict):
    """Type-safe feature analysis result.

    P0-10 FIX: TypedDict instead of Dict[str, object]
    """
    primary_type: str
    all_types: List[str]
    template: str
    confidence: str  # "low" | "medium" | "high"
    scores: Dict[str, int]


# ============================================================================
# KEYWORD LOADING (P2-27 FIX)
# ============================================================================

@lru_cache(maxsize=1)
def load_keywords() -> Dict[str, List[str]]:
    """Load feature keywords from config.json.

    P2-27 FIX: Cached to avoid repeated I/O.
    P0-11 FIX: Logs errors instead of silent pass.

    Returns:
        Dictionary mapping feature types to keyword lists
    """
    config_path = Path(__file__).parent / "config.json"

    # Default keywords
    defaults = {
        "api": ["endpoint", "api", "rest", "graphql", "route", "controller"],
        "ui": ["component", "page", "display", "frontend", "view", "react", "vue"],
        "db": ["schema", "migration", "model", "database", "table", "sql"],
        "service": ["service", "business logic", "process", "workflow"],
        "test": ["test", "testing", "pytest", "unittest", "e2e"],
        "infra": ["docker", "kubernetes", "ci", "cd", "deployment", "infrastructure"],
        "docs": ["documentation", "readme", "guide", "manual"]
    }

    if not config_path.exists():
        logger.warning(f"config.json nicht gefunden bei {config_path}, nutze Default-Keywords")
        return defaults

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
            keywords = config.get("feature_detection", {}).get("keywords", {})

            if not keywords:
                logger.warning("Keine feature_detection.keywords in config.json, nutze Defaults")
                return defaults

            # Merge with defaults (config overwrites defaults)
            return {**defaults, **keywords}

    except (json.JSONDecodeError, KeyError, IOError) as e:
        # P0-11 FIX: Log error instead of silent pass
        logger.error(f"Fehler beim Laden von Keywords aus config.json: {e}")
        return defaults


# ============================================================================
# SCORE CALCULATION (P0-12 FIX - DRY)
# ============================================================================

def _calculate_scores(content: str) -> Dict[str, int]:
    """Calculate keyword match scores for all feature types.

    P0-12 FIX: Centralized score calculation (DRY).
    P1-20 FIX: Whitespace sanitization.
    P1-21 FIX: Unicode normalization.
    P1-22 FIX: Word-boundary matching.

    Args:
        content: Feature description text

    Returns:
        Dictionary mapping feature types to scores
    """
    # P1-20 FIX: Whitespace sanitization
    if not content or not content.strip():
        return {}

    # P1-21 FIX: Unicode normalization (NFC)
    content_normalized = unicodedata.normalize('NFC', content.lower())

    # P2-27 FIX: Load keywords (cached)
    keywords = load_keywords()

    scores: Dict[str, int] = {}

    for feature_type, type_keywords in keywords.items():
        score = 0
        for keyword in type_keywords:
            # P1-22 FIX: Word-boundary matching (no false positives)
            pattern = rf'\b{re.escape(keyword.lower())}\b'
            matches = re.findall(pattern, content_normalized)
            score += len(matches)

        if score > 0:
            scores[feature_type] = score

    return scores


# ============================================================================
# FEATURE TYPE DETECTION
# ============================================================================

def detect_feature_type(content: str) -> str:
    """Detect primary feature type from content.

    Args:
        content: Feature description

    Returns:
        Primary feature type (e.g., "api", "ui", "db")
    """
    scores = _calculate_scores(content)

    if not scores:
        # Default to service if no keywords match
        return "service"

    # Return type with highest score
    return max(scores, key=scores.get)


def detect_feature_types(content: str) -> List[str]:
    """Detect all matching feature types (for multi-type features).

    Args:
        content: Feature description

    Returns:
        List of all matching feature types
    """
    scores = _calculate_scores(content)

    if not scores:
        return ["service"]

    # Return all types with score > 0, sorted by score
    return sorted(scores.keys(), key=lambda k: scores[k], reverse=True)


def analyze_feature(content: str) -> FeatureAnalysis:
    """Complete feature analysis with confidence rating.

    P0-10 FIX: Returns TypedDict for type safety.

    Args:
        content: Feature description

    Returns:
        FeatureAnalysis dict with primary_type, all_types, template, confidence, scores
    """
    scores = _calculate_scores(content)

    if not scores:
        return FeatureAnalysis(
            primary_type="service",
            all_types=["service"],
            template="TEMPLATE_SERVICE.md",
            confidence="low",
            scores={}
        )

    # Primary type = highest score
    primary_type = max(scores, key=scores.get)
    primary_score = scores[primary_type]

    # All types sorted by score
    all_types = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

    # Template name
    template = f"TEMPLATE_{primary_type.upper()}.md"

    # Confidence based on score
    # P2-29 FIX: Configurable thresholds
    config_path = Path(__file__).parent / "config.json"
    thresholds = {"high": 5, "medium": 3, "low": 0}  # Defaults

    try:
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
                custom_thresholds = config.get("feature_detection", {}).get("confidence_thresholds", {})
                thresholds.update(custom_thresholds)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Konnte confidence_thresholds nicht laden: {e}")

    if primary_score >= thresholds["high"]:
        confidence = "high"
    elif primary_score >= thresholds["medium"]:
        confidence = "medium"
    else:
        confidence = "low"

    return FeatureAnalysis(
        primary_type=primary_type,
        all_types=all_types,
        template=template,
        confidence=confidence,
        scores=scores
    )


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main() -> int:
    """CLI entry point.

    P2-28 FIX: Correct exit codes.

    Returns:
        0 for success, 1 for errors, 2 for invalid usage
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect feature type from description text"
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Feature description text (or read from stdin)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Enable verbose logging
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Get input text
    if args.text:
        text = args.text
    else:
        # Read from stdin
        try:
            text = sys.stdin.read()
        except (IOError, KeyboardInterrupt) as e:
            logger.error(f"Fehler beim Lesen von stdin: {e}")
            return 1

    if not text.strip():
        logger.error("Keine Input-Text erhalten")
        return 1

    # Analyze feature
    try:
        result = analyze_feature(text)

        if args.json:
            # P0-12 FIX: Handle JSON serialization errors
            try:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            except (TypeError, ValueError) as e:
                logger.error(f"JSON-Serialisierung fehlgeschlagen: {e}")
                return 1
        else:
            print(f"Primary Type: {result['primary_type']}")
            print(f"Confidence: {result['confidence']}")
            print(f"All Types: {', '.join(result['all_types'])}")
            print(f"Template: {result['template']}")
            if args.verbose:
                print(f"Scores: {result['scores']}")

        return 0

    except Exception as e:
        logger.exception(f"Unerwarteter Fehler: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
