"""
Log scanner for detecting errors and anomalies in container logs.

Provides pattern-based error detection with configurable patterns
and ignore rules for known harmless messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class LogMatch:
    """A matched error pattern in logs."""

    pattern: str
    line: str
    line_number: int
    severity: str


@dataclass
class ScanResult:
    """Result of scanning container logs."""

    container_name: str
    total_lines: int
    error_count: int
    matches: list[LogMatch] = field(default_factory=list)
    ignored_count: int = 0

    @property
    def has_errors(self) -> bool:
        """Check if any errors were found."""
        return self.error_count > 0


class LogScanner:
    """Scanner for detecting errors in container logs."""

    def __init__(
        self,
        error_patterns: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        """Initialize the log scanner.

        Args:
            error_patterns: Regex patterns to match as errors
            ignore_patterns: Regex patterns to ignore (false positives)
        """
        self.error_patterns = error_patterns or self._default_error_patterns()
        self.ignore_patterns = ignore_patterns or self._default_ignore_patterns()

        # Compile patterns for performance
        self._error_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.error_patterns
        ]
        self._ignore_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.ignore_patterns
        ]

    def _default_error_patterns(self) -> list[str]:
        """Return default error patterns."""
        return [
            r"CRITICAL",
            r"FATAL",
            r"panic:",
            r"Traceback \(most recent call last\)",
            r"OOMKilled",
            r"out of memory",
            r"OutOfMemoryError",
            r"ECONNREFUSED",
            r"connection refused",
            r"no route to host",
            r"ETIMEDOUT",
            r"error.*failed",
            r"failed.*error",
            r"Exception:",
            r"ERROR.*exception",
        ]

    def _default_ignore_patterns(self) -> list[str]:
        """Return default ignore patterns."""
        return [
            r"level=warning",
            r"level=warn",
            r"WARNING",
            r"retry",
            r"retrying",
            r"deprecated",
            r"DEPRECATED",
            r"healthcheck",
            r"health check",
            r"graceful shutdown",
            r"shutting down",
            r"starting up",
            r"initialization complete",
        ]

    def scan(
        self,
        log_content: str,
        container_name: str = "unknown",
        additional_ignore: list[str] | None = None,
    ) -> ScanResult:
        """Scan log content for errors.

        Args:
            log_content: The log content to scan
            container_name: Name of the container (for reporting)
            additional_ignore: Additional patterns to ignore for this scan

        Returns:
            ScanResult with all matches found
        """
        lines = log_content.split("\n")
        matches: list[LogMatch] = []
        ignored_count = 0

        # Compile additional ignore patterns if provided
        extra_ignores = []
        if additional_ignore:
            extra_ignores = [re.compile(p, re.IGNORECASE) for p in additional_ignore]

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue

            # Check if line should be ignored
            if self._should_ignore(line, extra_ignores):
                ignored_count += 1
                continue

            # Check for error patterns
            for pattern, regex in zip(self.error_patterns, self._error_regexes, strict=True):
                if regex.search(line):
                    severity = self._determine_severity(pattern, line)
                    matches.append(
                        LogMatch(
                            pattern=pattern,
                            line=line.strip()[:500],  # Truncate very long lines
                            line_number=line_num,
                            severity=severity,
                        )
                    )
                    break  # Only match first pattern per line

        return ScanResult(
            container_name=container_name,
            total_lines=len(lines),
            error_count=len(matches),
            matches=matches,
            ignored_count=ignored_count,
        )

    def _should_ignore(
        self,
        line: str,
        extra_ignores: list[re.Pattern[str]],
    ) -> bool:
        """Check if a line should be ignored.

        Args:
            line: The log line
            extra_ignores: Additional compiled patterns

        Returns:
            True if line should be ignored
        """
        for regex in self._ignore_regexes:
            if regex.search(line):
                return True

        for regex in extra_ignores:
            if regex.search(line):
                return True

        return False

    def _determine_severity(self, pattern: str, line: str) -> str:
        """Determine severity level based on pattern and line content.

        Args:
            pattern: The matched pattern
            line: The full log line

        Returns:
            Severity level: 'critical', 'error', 'warning'
        """
        critical_indicators = [
            "CRITICAL",
            "FATAL",
            "panic",
            "OOMKilled",
            "OutOfMemoryError",
        ]

        for indicator in critical_indicators:
            if indicator.lower() in pattern.lower() or indicator.lower() in line.lower():
                return "critical"

        return "error"

    def scan_for_specific_patterns(
        self,
        log_content: str,
        patterns: list[str],
        container_name: str = "unknown",
    ) -> ScanResult:
        """Scan logs for specific patterns only.

        Args:
            log_content: The log content to scan
            patterns: Specific patterns to look for
            container_name: Name of the container

        Returns:
            ScanResult with matches
        """
        lines = log_content.split("\n")
        matches: list[LogMatch] = []

        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue

            for pattern, regex in zip(patterns, compiled_patterns, strict=True):
                if regex.search(line):
                    matches.append(
                        LogMatch(
                            pattern=pattern,
                            line=line.strip()[:500],
                            line_number=line_num,
                            severity="error",
                        )
                    )
                    break

        return ScanResult(
            container_name=container_name,
            total_lines=len(lines),
            error_count=len(matches),
            matches=matches,
        )

    def format_results(self, result: ScanResult) -> str:
        """Format scan results as a human-readable string.

        Args:
            result: The scan result to format

        Returns:
            Formatted string
        """
        lines = [
            f"=== Log Scan: {result.container_name} ===",
            f"Total lines: {result.total_lines}",
            f"Errors found: {result.error_count}",
            f"Ignored: {result.ignored_count}",
        ]

        if result.matches:
            lines.append("\nMatched errors:")
            for match in result.matches[:20]:  # Limit output
                lines.append(f"  [{match.severity.upper()}] Line {match.line_number}:")
                lines.append(f"    Pattern: {match.pattern}")
                lines.append(f"    Content: {match.line[:100]}...")

            if len(result.matches) > 20:
                lines.append(f"\n  ... and {len(result.matches) - 20} more errors")

        return "\n".join(lines)
