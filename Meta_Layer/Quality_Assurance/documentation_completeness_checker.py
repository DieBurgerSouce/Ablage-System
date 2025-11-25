#!/usr/bin/env python3
"""
Documentation Completeness Checker for Ablage-System
Ensures all documentation files have required sections and quality standards.

Usage:
    python documentation_completeness_checker.py [--verbose] [--fix]
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from enum import Enum
import yaml


class DocumentType(Enum):
    """Types of documentation."""
    RUNBOOK = "runbook"
    ADR = "adr"
    GUIDE = "guide"
    API_DOC = "api_doc"
    CHECKLIST = "checklist"
    TRAINING = "training"
    README = "readme"
    OTHER = "other"


@dataclass
class RequiredSection:
    """A required section in documentation."""
    name: str
    pattern: str
    required: bool = True
    alternative_patterns: List[str] = field(default_factory=list)

    def matches(self, content: str) -> bool:
        """Check if section exists in content."""
        # Check main pattern
        if re.search(self.pattern, content, re.MULTILINE | re.IGNORECASE):
            return True

        # Check alternatives
        for alt in self.alternative_patterns:
            if re.search(alt, content, re.MULTILINE | re.IGNORECASE):
                return True

        return False


@dataclass
class DocumentIssue:
    """An issue found in documentation."""
    file_path: Path
    issue_type: str  # 'missing_section', 'line_too_long', 'no_metadata', etc.
    description: str
    line_number: Optional[int] = None
    severity: str = "WARNING"  # 'ERROR', 'WARNING', 'INFO'

    def __str__(self) -> str:
        location = f"{self.file_path}"
        if self.line_number:
            location += f":{self.line_number}"
        return f"[{self.severity}] {location} - {self.description}"


@dataclass
class DocumentReport:
    """Report for a single document."""
    file_path: Path
    document_type: DocumentType
    total_lines: int = 0
    has_metadata: bool = False
    has_toc: bool = False
    missing_sections: List[str] = field(default_factory=list)
    issues: List[DocumentIssue] = field(default_factory=list)
    word_count: int = 0

    def is_complete(self) -> bool:
        """Check if document is complete (no ERROR issues)."""
        return not any(issue.severity == "ERROR" for issue in self.issues)

    def quality_score(self) -> float:
        """Calculate quality score (0-100)."""
        score = 100.0

        # Deductions
        score -= len([i for i in self.issues if i.severity == "ERROR"]) * 20
        score -= len([i for i in self.issues if i.severity == "WARNING"]) * 5
        score -= len(self.missing_sections) * 10

        # Bonuses
        if self.has_metadata:
            score += 5
        if self.has_toc and self.total_lines > 100:
            score += 5

        return max(0.0, min(100.0, score))


class DocumentationChecker:
    """Checks documentation completeness."""

    # Required sections by document type
    REQUIRED_SECTIONS = {
        DocumentType.RUNBOOK: [
            RequiredSection("Purpose", r"^##?\s*Purpose", required=True),
            RequiredSection("Prerequisites", r"^##?\s*Prerequisites", required=True),
            RequiredSection("Steps", r"^##?\s*(Steps|Procedure|Instructions)", required=True),
            RequiredSection("Verification", r"^##?\s*(Verification|Checkpoint|Success Criteria)", required=False),
            RequiredSection("Rollback", r"^##?\s*(Rollback|Recovery|Failure)", required=False),
        ],
        DocumentType.ADR: [
            RequiredSection("Status", r"^##?\s*Status", required=True, alternative_patterns=[r"Status:\s*\w+"]),
            RequiredSection("Context", r"^##?\s*Context", required=True),
            RequiredSection("Decision", r"^##?\s*Decision", required=True),
            RequiredSection("Consequences", r"^##?\s*Consequences", required=True),
            RequiredSection("Alternatives", r"^##?\s*(Alternatives|Options Considered)", required=False),
        ],
        DocumentType.GUIDE: [
            RequiredSection("Overview", r"^##?\s*(Overview|Introduction)", required=True),
            RequiredSection("Prerequisites", r"^##?\s*Prerequisites", required=True),
            RequiredSection("Instructions", r"^##?\s*(Instructions|Steps|Getting Started)", required=True),
            RequiredSection("Examples", r"^##?\s*(Examples|Usage)", required=False),
        ],
        DocumentType.CHECKLIST: [
            RequiredSection("Purpose", r"^##?\s*Purpose", required=True),
            RequiredSection("Checklist Items", r"^[-*]\s*\[[ x]\]", required=True),  # Markdown checkbox
        ],
        DocumentType.README: [
            RequiredSection("Project Title", r"^#\s+.+", required=True),
            RequiredSection("Description", r"^##?\s*(Description|About|Overview)", required=True),
            RequiredSection("Installation", r"^##?\s*Installation", required=False),
            RequiredSection("Usage", r"^##?\s*Usage", required=False),
        ],
    }

    # Quality standards
    MAX_LINE_LENGTH = 120
    MIN_DOC_LENGTH_LINES = 20
    MIN_WORD_COUNT = 100

    def __init__(self, root_dir: Path, verbose: bool = False):
        """Initialize checker.

        Args:
            root_dir: Root directory of project
            verbose: Enable verbose output
        """
        self.root_dir = root_dir.resolve()
        self.verbose = verbose
        self.reports: List[DocumentReport] = []

    def log(self, message: str, level: str = "INFO"):
        """Log message."""
        if self.verbose or level == "ERROR":
            prefix = {"INFO": "ℹ", "WARNING": "⚠", "ERROR": "✗", "SUCCESS": "✓"}[level]
            print(f"{prefix} {message}")

    def detect_document_type(self, file_path: Path) -> DocumentType:
        """Detect type of documentation.

        Args:
            file_path: Path to document

        Returns:
            Detected document type
        """
        name_lower = file_path.name.lower()

        # Check by filename pattern
        if 'runbook' in name_lower or 'playbook' in name_lower:
            return DocumentType.RUNBOOK
        elif file_path.name.startswith('ADR_') or 'adr_' in name_lower:
            return DocumentType.ADR
        elif 'checklist' in name_lower:
            return DocumentType.CHECKLIST
        elif 'guide' in name_lower or 'tutorial' in name_lower or 'curriculum' in name_lower:
            return DocumentType.TRAINING if 'training' in name_lower else DocumentType.GUIDE
        elif file_path.name == 'README.md':
            return DocumentType.README
        else:
            return DocumentType.OTHER

    def extract_metadata(self, content: str) -> Optional[Dict]:
        """Extract YAML frontmatter metadata.

        Args:
            content: Document content

        Returns:
            Metadata dict or None
        """
        # Match YAML frontmatter (---\n...content...\n---)
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1))
            except yaml.YAMLError:
                return None

        return None

    def check_document(self, file_path: Path) -> DocumentReport:
        """Check single document.

        Args:
            file_path: Path to document

        Returns:
            Document report
        """
        self.log(f"Checking {file_path.relative_to(self.root_dir)}...", level="INFO")

        # Read content
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            report = DocumentReport(file_path=file_path, document_type=DocumentType.OTHER)
            report.issues.append(
                DocumentIssue(
                    file_path=file_path,
                    issue_type='read_error',
                    description=f"Cannot read file: {e}",
                    severity="ERROR"
                )
            )
            return report

        # Detect type
        doc_type = self.detect_document_type(file_path)

        # Create report
        report = DocumentReport(
            file_path=file_path,
            document_type=doc_type,
            total_lines=len(content.split('\n')),
            word_count=len(content.split())
        )

        # Check metadata
        metadata = self.extract_metadata(content)
        report.has_metadata = metadata is not None

        if not report.has_metadata and doc_type in [DocumentType.RUNBOOK, DocumentType.ADR]:
            report.issues.append(
                DocumentIssue(
                    file_path=file_path,
                    issue_type='missing_metadata',
                    description="Missing YAML frontmatter metadata (Version, Last Updated, Owner)",
                    severity="WARNING"
                )
            )

        # Check table of contents (for long documents)
        if report.total_lines > 200:
            has_toc = bool(re.search(r'##\s*Table of Contents', content, re.IGNORECASE))
            report.has_toc = has_toc

            if not has_toc:
                report.issues.append(
                    DocumentIssue(
                        file_path=file_path,
                        issue_type='missing_toc',
                        description="Long document (>200 lines) should have Table of Contents",
                        severity="WARNING"
                    )
                )

        # Check required sections
        if doc_type in self.REQUIRED_SECTIONS:
            for required_section in self.REQUIRED_SECTIONS[doc_type]:
                if not required_section.matches(content):
                    if required_section.required:
                        report.missing_sections.append(required_section.name)
                        report.issues.append(
                            DocumentIssue(
                                file_path=file_path,
                                issue_type='missing_section',
                                description=f"Missing required section: {required_section.name}",
                                severity="ERROR"
                            )
                        )
                    else:
                        report.issues.append(
                            DocumentIssue(
                                file_path=file_path,
                                issue_type='missing_optional_section',
                                description=f"Missing recommended section: {required_section.name}",
                                severity="INFO"
                            )
                        )

        # Check line length
        lines = content.split('\n')
        long_lines = []
        for i, line in enumerate(lines, start=1):
            # Skip code blocks
            if line.strip().startswith('```') or line.strip().startswith('|'):
                continue

            if len(line) > self.MAX_LINE_LENGTH:
                long_lines.append((i, len(line)))

        if long_lines:
            report.issues.append(
                DocumentIssue(
                    file_path=file_path,
                    issue_type='line_too_long',
                    description=f"{len(long_lines)} lines exceed {self.MAX_LINE_LENGTH} characters",
                    severity="WARNING"
                )
            )

        # Check minimum content length
        if report.total_lines < self.MIN_DOC_LENGTH_LINES:
            report.issues.append(
                DocumentIssue(
                    file_path=file_path,
                    issue_type='too_short',
                    description=f"Document too short ({report.total_lines} lines, minimum: {self.MIN_DOC_LENGTH_LINES})",
                    severity="WARNING"
                )
            )

        if report.word_count < self.MIN_WORD_COUNT:
            report.issues.append(
                DocumentIssue(
                    file_path=file_path,
                    issue_type='too_short',
                    description=f"Document too short ({report.word_count} words, minimum: {self.MIN_WORD_COUNT})",
                    severity="INFO"
                )
            )

        # Check for code examples (in guides/training)
        if doc_type in [DocumentType.GUIDE, DocumentType.TRAINING]:
            has_code_blocks = bool(re.search(r'```', content))
            if not has_code_blocks:
                report.issues.append(
                    DocumentIssue(
                        file_path=file_path,
                        issue_type='missing_code_examples',
                        description="Guide/Training document should include code examples",
                        severity="WARNING"
                    )
                )

        return report

    def check_all_markdown_files(self):
        """Check all markdown files in project."""
        self.log("Scanning markdown files...")

        markdown_files = list(self.root_dir.rglob("*.md"))

        # Exclude certain directories
        exclude_dirs = {'.git', 'node_modules', 'venv', '__pycache__'}
        markdown_files = [
            f for f in markdown_files
            if not any(excluded in f.parts for excluded in exclude_dirs)
        ]

        self.log(f"Found {len(markdown_files)} markdown files to check")

        for file_path in markdown_files:
            report = self.check_document(file_path)
            self.reports.append(report)

    def generate_summary_report(self) -> str:
        """Generate summary report.

        Returns:
            Formatted report string
        """
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DOCUMENTATION COMPLETENESS REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Overall statistics
        total_docs = len(self.reports)
        complete_docs = len([r for r in self.reports if r.is_complete()])
        avg_quality = sum(r.quality_score() for r in self.reports) / total_docs if total_docs > 0 else 0

        report_lines.append("OVERALL STATISTICS")
        report_lines.append("-" * 80)
        report_lines.append(f"Total Documents: {total_docs}")
        report_lines.append(f"Complete Documents: {complete_docs}/{total_docs} ({complete_docs/total_docs*100:.1f}%)")
        report_lines.append(f"Average Quality Score: {avg_quality:.2f}/100")
        report_lines.append("")

        # Issues by severity
        all_issues = [issue for report in self.reports for issue in report.issues]
        errors = len([i for i in all_issues if i.severity == "ERROR"])
        warnings = len([i for i in all_issues if i.severity == "WARNING"])
        infos = len([i for i in all_issues if i.severity == "INFO"])

        report_lines.append(f"Total Issues: {len(all_issues)}")
        report_lines.append(f"  - Errors: {errors}")
        report_lines.append(f"  - Warnings: {warnings}")
        report_lines.append(f"  - Info: {infos}")
        report_lines.append("")

        # Documents with issues
        docs_with_errors = [r for r in self.reports if any(i.severity == "ERROR" for i in r.issues)]

        if docs_with_errors:
            report_lines.append("DOCUMENTS WITH ERRORS")
            report_lines.append("-" * 80)
            for doc_report in docs_with_errors:
                rel_path = doc_report.file_path.relative_to(self.root_dir)
                quality = doc_report.quality_score()
                report_lines.append(f"  {rel_path} (Quality: {quality:.1f}/100)")

                for issue in doc_report.issues:
                    if issue.severity == "ERROR":
                        report_lines.append(f"    ✗ {issue.description}")

                report_lines.append("")

        # Quality breakdown by document type
        report_lines.append("QUALITY BY DOCUMENT TYPE")
        report_lines.append("-" * 80)

        docs_by_type: Dict[DocumentType, List[DocumentReport]] = {}
        for report in self.reports:
            if report.document_type not in docs_by_type:
                docs_by_type[report.document_type] = []
            docs_by_type[report.document_type].append(report)

        for doc_type, reports in sorted(docs_by_type.items(), key=lambda x: x[0].value):
            avg_quality = sum(r.quality_score() for r in reports) / len(reports)
            complete = len([r for r in reports if r.is_complete()])
            report_lines.append(f"  {doc_type.value.upper()}: {complete}/{len(reports)} complete, "
                               f"avg quality {avg_quality:.1f}/100")

        report_lines.append("")

        # Top quality documents
        top_docs = sorted(self.reports, key=lambda r: r.quality_score(), reverse=True)[:10]
        report_lines.append("TOP 10 QUALITY DOCUMENTS")
        report_lines.append("-" * 80)
        for doc_report in top_docs:
            rel_path = doc_report.file_path.relative_to(self.root_dir)
            quality = doc_report.quality_score()
            report_lines.append(f"  {quality:5.1f}/100 - {rel_path}")

        report_lines.append("")

        # Overall status
        if complete_docs == total_docs and avg_quality >= 90:
            report_lines.append("✅ EXCELLENT - All documentation complete and high quality!")
        elif complete_docs == total_docs:
            report_lines.append("✅ PASSED - All documentation complete")
        elif complete_docs / total_docs >= 0.9:
            report_lines.append("⚠️  MOSTLY COMPLETE - Some documents need attention")
        else:
            report_lines.append("❌ NEEDS WORK - Many documents incomplete or low quality")

        report_lines.append("")
        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    def generate_detailed_report(self) -> str:
        """Generate detailed report with all issues.

        Returns:
            Formatted detailed report
        """
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DETAILED DOCUMENTATION REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")

        for doc_report in sorted(self.reports, key=lambda r: r.quality_score()):
            rel_path = doc_report.file_path.relative_to(self.root_dir)
            quality = doc_report.quality_score()

            report_lines.append(f"{rel_path}")
            report_lines.append(f"  Type: {doc_report.document_type.value}")
            report_lines.append(f"  Quality Score: {quality:.1f}/100")
            report_lines.append(f"  Lines: {doc_report.total_lines}, Words: {doc_report.word_count}")
            report_lines.append(f"  Metadata: {'✓' if doc_report.has_metadata else '✗'}")

            if doc_report.issues:
                report_lines.append("  Issues:")
                for issue in sorted(doc_report.issues, key=lambda i: i.severity):
                    symbol = {"ERROR": "✗", "WARNING": "⚠", "INFO": "ℹ"}[issue.severity]
                    report_lines.append(f"    {symbol} [{issue.severity}] {issue.description}")

            report_lines.append("")

        return "\n".join(report_lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check documentation completeness and quality"
    )
    parser.add_argument(
        '--root-dir',
        type=Path,
        default=Path.cwd().parent.parent,  # Assume running from Meta_Layer/Quality_Assurance
        help='Root directory of project'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--detailed',
        '-d',
        action='store_true',
        help='Generate detailed report (all issues)'
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        help='Output report to file'
    )

    args = parser.parse_args()

    # Run checks
    checker = DocumentationChecker(args.root_dir, verbose=args.verbose)
    checker.check_all_markdown_files()

    # Generate report
    if args.detailed:
        report = checker.generate_detailed_report()
    else:
        report = checker.generate_summary_report()

    print(report)

    # Save to file if requested
    if args.output:
        args.output.write_text(report, encoding='utf-8')
        print(f"\nReport saved to: {args.output}")

    # Exit code based on completion
    complete_docs = len([r for r in checker.reports if r.is_complete()])
    total_docs = len(checker.reports)
    sys.exit(0 if complete_docs == total_docs else 1)


if __name__ == '__main__':
    main()
