#!/usr/bin/env python3
"""
Cross-Reference Validator for Ablage-System Knowledge Architecture
Validates all internal file references and ensures no broken links.

Usage:
    python cross_reference_validator.py [--fix] [--verbose]
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict
import yaml
import json


@dataclass
class Reference:
    """Represents a file reference."""
    source_file: Path
    target_file: str
    line_number: int
    reference_type: str  # 'markdown_link', 'yaml_reference', 'python_import', etc.

    def __str__(self) -> str:
        return f"{self.source_file}:{self.line_number} -> {self.target_file}"


@dataclass
class ValidationResult:
    """Results of validation."""
    total_references: int = 0
    valid_references: int = 0
    broken_references: List[Reference] = None
    orphan_files: List[Path] = None
    circular_references: List[Tuple[Path, Path]] = None

    def __post_init__(self):
        if self.broken_references is None:
            self.broken_references = []
        if self.orphan_files is None:
            self.orphan_files = []
        if self.circular_references is None:
            self.circular_references = []

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_references == 0:
            return 100.0
        return (self.valid_references / self.total_references) * 100

    def is_valid(self) -> bool:
        """Check if validation passed (no broken references)."""
        return len(self.broken_references) == 0 and len(self.orphan_files) == 0


class CrossReferenceValidator:
    """Validates cross-references in Knowledge Architecture."""

    # File patterns to scan
    MARKDOWN_PATTERN = "**/*.md"
    YAML_PATTERN = "**/*.yaml"
    PYTHON_PATTERN = "**/*.py"

    # Reference patterns
    MARKDOWN_LINK_PATTERN = r'\[([^\]]+)\]\(([^\)]+)\)'
    YAML_FILE_PATTERN = r'file:\s*["\']?([^"\'\s]+)["\']?'
    PYTHON_IMPORT_PATTERN = r'from\s+([\w\.]+)\s+import'

    # Directories to exclude
    EXCLUDE_DIRS = {'.git', '__pycache__', 'venv', 'node_modules', '.pytest_cache'}

    def __init__(self, root_dir: Path, verbose: bool = False):
        """Initialize validator.

        Args:
            root_dir: Root directory of project
            verbose: Enable verbose output
        """
        self.root_dir = root_dir.resolve()
        self.verbose = verbose
        self.all_files: Set[Path] = set()
        self.references: List[Reference] = []
        self.reference_graph: Dict[Path, Set[Path]] = defaultdict(set)

    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose enabled."""
        if self.verbose or level == "ERROR":
            prefix = "✓" if level == "INFO" else "✗"
            print(f"{prefix} {message}")

    def scan_files(self):
        """Scan all files in project."""
        self.log("Scanning project files...")

        # Find all markdown, yaml, and python files
        for pattern in [self.MARKDOWN_PATTERN, self.YAML_PATTERN, self.PYTHON_PATTERN]:
            for file_path in self.root_dir.rglob(pattern):
                # Skip excluded directories
                if any(excluded in file_path.parts for excluded in self.EXCLUDE_DIRS):
                    continue

                self.all_files.add(file_path.relative_to(self.root_dir))

        self.log(f"Found {len(self.all_files)} files to validate")

    def extract_references_from_markdown(self, file_path: Path):
        """Extract references from Markdown file.

        Args:
            file_path: Path to markdown file
        """
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')

            for line_num, line in enumerate(lines, start=1):
                # Find markdown links: [text](path)
                for match in re.finditer(self.MARKDOWN_LINK_PATTERN, line):
                    link_text = match.group(1)
                    link_target = match.group(2)

                    # Skip external URLs
                    if link_target.startswith(('http://', 'https://', '#', 'mailto:')):
                        continue

                    # Remove anchor links
                    link_target = link_target.split('#')[0]

                    if link_target:
                        ref = Reference(
                            source_file=file_path.relative_to(self.root_dir),
                            target_file=link_target,
                            line_number=line_num,
                            reference_type='markdown_link'
                        )
                        self.references.append(ref)

        except Exception as e:
            self.log(f"Error reading {file_path}: {e}", level="ERROR")

    def extract_references_from_yaml(self, file_path: Path):
        """Extract file references from YAML.

        Args:
            file_path: Path to YAML file
        """
        try:
            content = file_path.read_text(encoding='utf-8')

            # Extract file references
            for match in re.finditer(self.YAML_FILE_PATTERN, content):
                file_ref = match.group(1)

                # Get line number
                line_num = content[:match.start()].count('\n') + 1

                ref = Reference(
                    source_file=file_path.relative_to(self.root_dir),
                    target_file=file_ref,
                    line_number=line_num,
                    reference_type='yaml_reference'
                )
                self.references.append(ref)

        except Exception as e:
            self.log(f"Error reading {file_path}: {e}", level="ERROR")

    def extract_all_references(self):
        """Extract references from all files."""
        self.log("Extracting references...")

        for file_path in self.all_files:
            full_path = self.root_dir / file_path

            if file_path.suffix == '.md':
                self.extract_references_from_markdown(full_path)
            elif file_path.suffix in ['.yaml', '.yml']:
                self.extract_references_from_yaml(full_path)

        self.log(f"Extracted {len(self.references)} references")

    def resolve_reference(self, source_file: Path, target: str) -> Path:
        """Resolve a reference to absolute path.

        Args:
            source_file: File containing the reference
            target: Target path (relative or absolute)

        Returns:
            Resolved path relative to project root
        """
        # If target is absolute (starts with /), resolve from root
        if target.startswith('/'):
            return Path(target.lstrip('/'))

        # Otherwise, resolve relative to source file's directory
        source_dir = source_file.parent
        resolved = (source_dir / target).resolve()

        try:
            return resolved.relative_to(self.root_dir.resolve())
        except ValueError:
            # Path is outside project root
            return resolved

    def validate_references(self) -> ValidationResult:
        """Validate all extracted references.

        Returns:
            Validation result with broken references
        """
        self.log("Validating references...")

        result = ValidationResult()
        result.total_references = len(self.references)

        for ref in self.references:
            # Resolve target path
            resolved_target = self.resolve_reference(ref.source_file, ref.target_file)

            # Check if target exists
            target_path = self.root_dir / resolved_target

            if target_path.exists():
                result.valid_references += 1

                # Build reference graph for circular detection
                source_path = self.root_dir / ref.source_file
                self.reference_graph[source_path].add(target_path)

                self.log(f"  ✓ {ref}", level="DEBUG")
            else:
                result.broken_references.append(ref)
                self.log(f"  ✗ Broken reference: {ref}", level="ERROR")

        self.log(f"Valid references: {result.valid_references}/{result.total_references}")

        return result

    def find_orphan_files(self, result: ValidationResult):
        """Find files not referenced by any other file.

        Args:
            result: Validation result to update
        """
        self.log("Finding orphan files...")

        # Get all referenced files
        referenced_files = set()
        for ref in self.references:
            resolved = self.resolve_reference(ref.source_file, ref.target_file)
            referenced_files.add(resolved)

        # Files that are neither referencing nor referenced
        # Exception: Root-level documents are allowed to be "orphans"
        root_files = {
            Path('README.md'),
            Path('CLAUDE.md'),
            Path('GETTING_STARTED.md'),
            Path('KNOWLEDGE_ARCHITECTURE_COMPLETE.md'),
            Path('.gitignore'),
            Path('requirements.txt'),
        }

        for file_path in self.all_files:
            if file_path not in referenced_files and file_path not in root_files:
                # Check if this file references any other files
                file_has_outgoing_refs = any(
                    ref.source_file == file_path for ref in self.references
                )

                if not file_has_outgoing_refs:
                    result.orphan_files.append(file_path)
                    self.log(f"  Orphan file: {file_path}", level="ERROR")

        self.log(f"Found {len(result.orphan_files)} orphan files")

    def detect_circular_references(self, result: ValidationResult):
        """Detect circular reference chains.

        Args:
            result: Validation result to update
        """
        self.log("Detecting circular references...")

        visited = set()
        recursion_stack = set()

        def has_cycle(node: Path, path: List[Path]) -> bool:
            """DFS to detect cycles."""
            visited.add(node)
            recursion_stack.add(node)
            path.append(node)

            for neighbor in self.reference_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, path):
                        return True
                elif neighbor in recursion_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    for i in range(len(cycle)):
                        source = cycle[i]
                        target = cycle[(i + 1) % len(cycle)]
                        result.circular_references.append((source, target))
                    return True

            path.pop()
            recursion_stack.remove(node)
            return False

        for node in self.reference_graph:
            if node not in visited:
                has_cycle(node, [])

        if result.circular_references:
            self.log(f"Found {len(result.circular_references)} circular references", level="ERROR")
        else:
            self.log("No circular references found")

    def generate_report(self, result: ValidationResult) -> str:
        """Generate validation report.

        Args:
            result: Validation result

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 70)
        report.append("CROSS-REFERENCE VALIDATION REPORT")
        report.append("=" * 70)
        report.append("")

        # Summary
        report.append(f"Total References: {result.total_references}")
        report.append(f"Valid References: {result.valid_references}")
        report.append(f"Broken References: {len(result.broken_references)}")
        report.append(f"Orphan Files: {len(result.orphan_files)}")
        report.append(f"Circular References: {len(result.circular_references)}")
        report.append(f"Success Rate: {result.success_rate:.2f}%")
        report.append("")

        # Status
        if result.is_valid():
            report.append("✅ VALIDATION PASSED - All references valid!")
        else:
            report.append("❌ VALIDATION FAILED - Issues found")

        report.append("")

        # Broken references detail
        if result.broken_references:
            report.append("-" * 70)
            report.append("BROKEN REFERENCES:")
            report.append("-" * 70)
            for ref in result.broken_references:
                report.append(f"  {ref.source_file}:{ref.line_number}")
                report.append(f"    → Missing: {ref.target_file}")
                report.append("")

        # Orphan files detail
        if result.orphan_files:
            report.append("-" * 70)
            report.append("ORPHAN FILES (not referenced by any file):")
            report.append("-" * 70)
            for file_path in result.orphan_files:
                report.append(f"  {file_path}")
            report.append("")

        # Circular references detail
        if result.circular_references:
            report.append("-" * 70)
            report.append("CIRCULAR REFERENCES:")
            report.append("-" * 70)
            for source, target in result.circular_references:
                source_rel = source.relative_to(self.root_dir)
                target_rel = target.relative_to(self.root_dir)
                report.append(f"  {source_rel} ⟷ {target_rel}")
            report.append("")

        report.append("=" * 70)

        return "\n".join(report)

    def run_validation(self) -> ValidationResult:
        """Run full validation process.

        Returns:
            Validation result
        """
        self.scan_files()
        self.extract_all_references()
        result = self.validate_references()
        self.find_orphan_files(result)
        self.detect_circular_references(result)

        return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate cross-references in Knowledge Architecture"
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
        '--output',
        '-o',
        type=Path,
        help='Output report to file'
    )

    args = parser.parse_args()

    # Run validation
    validator = CrossReferenceValidator(args.root_dir, verbose=args.verbose)
    result = validator.run_validation()

    # Generate report
    report = validator.generate_report(result)
    print(report)

    # Save to file if requested
    if args.output:
        args.output.write_text(report, encoding='utf-8')
        print(f"\nReport saved to: {args.output}")

    # Exit with appropriate code
    sys.exit(0 if result.is_valid() else 1)


if __name__ == '__main__':
    main()
