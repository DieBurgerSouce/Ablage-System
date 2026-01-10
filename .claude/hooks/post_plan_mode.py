#!/usr/bin/env python3
"""
Post-Plan-Mode Hook - Enterprise-Level v4.0

Triggered AFTER ExitPlanMode, checks if plan needs breakdown into feature specs.

Features:
- P0-1: Case-insensitive meta-file detection
- P0-2: Content-hash based session reuse (SHA256)
- P0-3/P0-4: TOCTTOU-safe file reading with encoding fallback
- P0-5: Word-boundary feature counting (no false positives)
- P0-14: Config.json integration
- P1-17: Symlink protection
- P2-26: Performance protection (max plans limit)

Author: Enterprise Fix Initiative v4.0
Date: 2026-01-04
"""

import hashlib
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION (P0-14 FIX)
# ============================================================================

def _load_config() -> Dict[str, Any]:
    """Load config.json with fallback to defaults.

    Returns:
        Configuration dictionary with hook settings
    """
    config_path = Path(__file__).parent / "config.json"

    # Default settings
    defaults = {
        "plan_freshness_minutes": 5,
        "feature_count_threshold": 3,
        "phase_count_threshold": 2,
        "task_count_threshold": 1,
        "max_spec_lines": 500,
        "enable_logging": True,
        "log_level": "INFO",
        "max_plans_to_scan": 1000  # P2-26: Performance protection
    }

    if not config_path.exists():
        logger.warning(f"config.json nicht gefunden bei {config_path}, nutze Defaults")
        return defaults

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)
            settings = config_data.get("settings", {})
            # Merge with defaults
            return {**defaults, **settings}
    except (json.JSONDecodeError, KeyError, IOError) as e:
        logger.error(f"Fehler beim Laden von config.json: {e}")
        return defaults


# Load config at module level
CONFIG = _load_config()

# Configure logging level from config
if CONFIG.get("enable_logging", True):
    log_level = getattr(logging, CONFIG.get("log_level", "INFO").upper())
    logger.setLevel(log_level)


# ============================================================================
# UTILITY FUNCTIONS (P0-1, P0-2, P0-3, P0-5)
# ============================================================================

def _is_meta_file(file_path: Path) -> bool:
    """Check if file is a meta-file (should be skipped).

    P0-1 FIX: Case-insensitive detection of meta files.

    Args:
        file_path: Path to check

    Returns:
        True if file is a meta file (PROGRESS.json, README.md, TEMPLATE_*, etc.)
    """
    name_lower = file_path.name.lower()

    # Skip PROGRESS.json, README.md (case-insensitive)
    if name_lower in ["progress.json", "readme.md", "plan_overview.md"]:
        return True

    # Skip TEMPLATE_* files (case-insensitive)
    if name_lower.startswith("template_"):
        return True

    return False


def _calculate_content_hash(content: str) -> str:
    """Calculate SHA256 hash of content.

    P0-2 FIX: Content-based change detection instead of mtime.

    Args:
        content: Text content to hash

    Returns:
        SHA256 hex digest
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _read_file_safe(file_path: Path) -> Optional[str]:
    """TOCTTOU-safe file reading with encoding fallback.

    P0-3/P0-4 FIX: Prevents race conditions and handles multiple encodings.
    P1-16 FIX: Uses cp1252 for Windows compatibility.

    Args:
        file_path: Path to file

    Returns:
        File content as string, or None if error
    """
    encodings = ['utf-8', 'cp1252', 'latin-1']  # P1-16: cp1252 before latin-1

    for encoding in encodings:
        try:
            # Atomic read - minimize TOCTTOU window
            content = file_path.read_text(encoding=encoding)
            return content
        except UnicodeDecodeError:
            continue  # Try next encoding
        except (FileNotFoundError, PermissionError, OSError) as e:
            # P0-4 FIX: Catch all file errors
            logger.warning(f"Fehler beim Lesen von {file_path}: {e}")
            return None

    logger.error(f"Konnte {file_path} mit keinem Encoding lesen")
    return None


def _count_with_word_boundaries(content: str, keyword: str) -> int:
    """Count keyword occurrences with word boundaries.

    P0-5 FIX: Prevents false positives like "feature-branch" matching "feature".
    P1-22 FIX: Uses regex word boundaries with hyphen exclusion.

    Args:
        content: Text to search
        keyword: Keyword to count

    Returns:
        Number of whole-word matches (case-insensitive)
    """
    # P1-21 FIX: Unicode normalization
    content_normalized = unicodedata.normalize('NFC', content.lower())
    keyword_normalized = keyword.lower()

    # Negative lookahead/lookbehind to exclude hyphenated compounds
    # (?<![-\w]) = NOT preceded by hyphen or word char
    # (?![-\w]) = NOT followed by hyphen or word char
    pattern = rf'(?<![-\w]){re.escape(keyword_normalized)}(?![-\w])'

    matches = re.findall(pattern, content_normalized)
    return len(matches)


# ============================================================================
# PLAN ANALYSIS (P0-5)
# ============================================================================

def _analyze_plan_complexity(content: str, config: Dict[str, Any]) -> Tuple[bool, int, int, int]:
    """Analyze if plan is complex enough to warrant breakdown.

    Args:
        content: Plan file content
        config: Configuration dictionary

    Returns:
        Tuple of (is_complex, feature_count, phase_count, task_count)
    """
    # P1-20 FIX: Whitespace sanitization
    if not content or not content.strip():
        return False, 0, 0, 0

    # Count features with word boundaries
    feature_count = _count_with_word_boundaries(content, "feature")

    # Count phases
    phase_count = _count_with_word_boundaries(content, "phase")

    # Count task tables (look for markdown table headers)
    task_table_pattern = r'\|.*Task.*\|.*Status.*\|'
    task_tables = re.findall(task_table_pattern, content, re.IGNORECASE)
    task_count = len(task_tables)

    # Check thresholds from config
    feature_threshold = config.get("feature_count_threshold", 3)
    phase_threshold = config.get("phase_count_threshold", 2)
    task_threshold = config.get("task_count_threshold", 1)

    is_complex = (
        feature_count >= feature_threshold or
        phase_count >= phase_threshold or
        task_count >= task_threshold
    )

    return is_complex, feature_count, phase_count, task_count


# ============================================================================
# PROGRESS TRACKING (P0-2, P0-3, P0-4)
# ============================================================================

def _check_progress_file(plans_dir: Path, plan_file: Path, plan_content: str) -> bool:
    """Check if plan already has been processed (via PROGRESS.json).

    P0-2 FIX: Uses content hash instead of mtime for session reuse.
    P0-3/P0-4 FIX: TOCTTOU-safe file operations.

    Args:
        plans_dir: Directory containing plans
        plan_file: Plan file path
        plan_content: Current plan content

    Returns:
        True if plan already processed (can skip breakdown)
    """
    progress_file = plans_dir / "PROGRESS.json"

    # Check if PROGRESS.json exists
    if not progress_file.exists():
        return False

    # Read PROGRESS.json safely
    progress_content = _read_file_safe(progress_file)
    if not progress_content:
        return False

    try:
        progress_data = json.loads(progress_content)
    except json.JSONDecodeError as e:
        logger.error(f"PROGRESS.json ist fehlerhaft: {e}")
        return False

    # Check if status is "done"
    if progress_data.get("status") != "done":
        logger.info("PROGRESS.json existiert, aber status != 'done' - Breakdown fortsetzen")
        return False

    # P0-2 FIX: Compare content hash instead of mtime
    current_hash = _calculate_content_hash(plan_content)
    stored_hash = progress_data.get("metadata", {}).get("plan_content_hash", "")

    if current_hash == stored_hash:
        logger.info(f"Plan unverändert (Hash: {current_hash[:8]}...), überspringe Breakdown")
        return True
    else:
        logger.info(f"Plan wurde modifiziert (alter Hash: {stored_hash[:8]}..., neuer: {current_hash[:8]}...)")
        return False


# ============================================================================
# MAIN HOOK LOGIC
# ============================================================================

def check_plan_needs_breakdown() -> Tuple[bool, Optional[str]]:
    """Check if any plan needs breakdown into feature specs.

    Returns:
        Tuple of (needs_breakdown: bool, plan_name: Optional[str])
    """
    # Find .claude/plans directory
    current_dir = Path.cwd()
    plans_dir = current_dir / ".claude" / "plans"

    if not plans_dir.exists():
        logger.debug(f"Kein .claude/plans Verzeichnis gefunden bei {plans_dir}")
        return False, None

    # P1-17 FIX: Symlink-Schutz
    try:
        if plans_dir.is_symlink():
            logger.warning(f"plans_dir ist ein Symlink: {plans_dir} -> {plans_dir.resolve()}")
            # Continue but log warning (could also reject symlinks)
    except OSError as e:
        logger.error(f"Fehler beim Pruefen von Symlink-Status: {e}")
        return False, None

    # Find all .md files (exclude meta files)
    try:
        all_md_files = list(plans_dir.glob("*.md"))
    except OSError as e:
        logger.error(f"Fehler beim Lesen von {plans_dir}: {e}")
        return False, None

    # P2-26 FIX: Performance protection
    max_plans = CONFIG.get("max_plans_to_scan", 1000)
    if len(all_md_files) > max_plans:
        logger.warning(
            f"Zu viele Plan-Dateien ({len(all_md_files)}), "
            f"limitiere auf {max_plans} neueste Dateien"
        )
        # Sort by modification time, newest first
        all_md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        all_md_files = all_md_files[:max_plans]

    plan_files: List[Path] = []
    for pf in all_md_files:
        # P1-17 FIX: Symlink-Check
        try:
            if pf.is_symlink():
                logger.warning(f"Ueberspringe Symlink: {pf} -> {pf.resolve()}")
                continue
        except OSError:
            continue

        # P0-1 FIX: Skip meta files (case-insensitive)
        if _is_meta_file(pf):
            logger.debug(f"Ueberspringe Meta-Datei: {pf.name}")
            continue

        plan_files.append(pf)

    if not plan_files:
        logger.debug("Keine Plan-Dateien gefunden")
        return False, None

    # Check each plan file
    for plan_file in plan_files:
        # Read plan content safely
        plan_content = _read_file_safe(plan_file)
        if not plan_content:
            continue

        # Check if already processed
        if _check_progress_file(plans_dir, plan_file, plan_content):
            continue

        # Analyze complexity
        is_complex, feature_count, phase_count, task_count = _analyze_plan_complexity(
            plan_content, CONFIG
        )

        if is_complex:
            logger.info(
                f"Plan '{plan_file.name}' braucht Breakdown: "
                f"{feature_count} Features, {phase_count} Phasen, {task_count} Task-Tabellen"
            )
            return True, plan_file.name

    logger.debug("Alle Plaene sind entweder fertig oder zu einfach")
    return False, None


# ============================================================================
# HOOK ENTRY POINT
# ============================================================================

def main() -> int:
    """Main hook entry point.

    Returns:
        0 if success, 1 if breakdown needed, 2 if error
    """
    try:
        needs_breakdown, plan_name = check_plan_needs_breakdown()

        if needs_breakdown:
            print(f"[!] Plan '{plan_name}' braucht detaillierte Feature-Specs!")
            print(f"[*] Starte: Task(subagent_type='plan-breakdown', prompt='Expandiere {plan_name}')")
            return 1
        else:
            logger.info("Kein Breakdown noetig")
            return 0

    except Exception as e:
        logger.exception(f"Unerwarteter Fehler im post-plan-mode Hook: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
