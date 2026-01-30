#!/usr/bin/env python3
"""
Fix CRLF injection vulnerabilities in Content-Disposition headers.
Replaces f-string patterns with secure build_content_disposition() function.
"""

import re
from pathlib import Path

# Files to fix
FILES_TO_FIX = [
    "app/api/v1/accounting.py",
    "app/api/v1/audit_trail_visualization.py",
    "app/api/v1/archive.py",
    "app/api/v1/banking.py",
    "app/api/v1/audit_chain.py",
    "app/api/v1/template_engine.py",
    "app/api/v1/tax_advisor_packages.py",
    "app/api/v1/compliance_autopilot.py",
    "app/api/v1/document_templates.py",
    "app/api/v1/invoices.py",
    "app/api/v1/ocr.py",
]

IMPORT_LINE = "from app.core.security_auth import build_content_disposition"

def needs_import(content: str) -> bool:
    """Check if file needs the import added."""
    return IMPORT_LINE not in content

def add_import_after_safe_errors(content: str) -> str:
    """Add import after safe_errors import."""
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'from app.core.safe_errors import' in line:
            lines.insert(i + 1, IMPORT_LINE)
            return '\n'.join(lines)

    # Fallback: add after other app.core imports
    for i, line in enumerate(lines):
        if line.startswith('from app.core.') and not line.startswith('from app.core.security'):
            lines.insert(i + 1, IMPORT_LINE)
            return '\n'.join(lines)

    # Last resort: add after app.api.dependencies
    for i, line in enumerate(lines):
        if 'from app.api.dependencies import' in line:
            lines.insert(i + 1, IMPORT_LINE)
            return '\n'.join(lines)

    return content

def fix_content_disposition_patterns(content: str) -> tuple[str, int]:
    """Fix all Content-Disposition f-string patterns."""
    count = 0

    # Pattern 1: "Content-Disposition": f'attachment; filename="{variable}"'
    pattern1 = r'"Content-Disposition":\s*f[\'"]attachment;\s*filename="(\{[^}]+\})"[\'"']
    def repl1(match):
        nonlocal count
        count += 1
        var_name = match.group(1)[1:-1]  # Remove { }
        return f'"Content-Disposition": build_content_disposition({var_name}, "attachment")'

    content = re.sub(pattern1, repl1, content)

    # Pattern 2: "Content-Disposition": f"attachment; filename={variable}" (no quotes around filename)
    pattern2 = r'"Content-Disposition":\s*f[\'"]attachment;\s*filename=(\{[^}]+\})[\'"]'
    def repl2(match):
        nonlocal count
        count += 1
        var_name = match.group(1)[1:-1]  # Remove { }
        return f'"Content-Disposition": build_content_disposition({var_name}, "attachment")'

    content = re.sub(pattern2, repl2, content)

    # Pattern 3: headers={"Content-Disposition": f"attachment; filename={var}"} (inline)
    pattern3 = r'headers\s*=\s*\{\s*"Content-Disposition":\s*f[\'"]attachment;\s*filename=(\{[^}]+\})[\'"]'
    def repl3(match):
        nonlocal count
        count += 1
        var_name = match.group(1)[1:-1]
        return f'headers={{"Content-Disposition": build_content_disposition({var_name}, "attachment")'

    content = re.sub(pattern3, repl3, content)

    # Pattern 4: Hardcoded filenames like "audit_trail_{document_id}.csv"
    pattern4 = r'"Content-Disposition":\s*f[\'"]attachment;\s*filename="([^"]+)"[\'"']
    def repl4(match):
        nonlocal count
        count += 1
        filename_expr = match.group(1)
        # Convert f-string expression to regular string concatenation
        return f'"Content-Disposition": build_content_disposition(f"{filename_expr}", "attachment")'

    content = re.sub(pattern4, repl4, content)

    return content, count

def fix_file(filepath: Path) -> tuple[bool, int]:
    """Fix a single file. Returns (success, num_fixes)."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original_content = content

        # Add import if needed
        if needs_import(content):
            content = add_import_after_safe_errors(content)

        # Fix Content-Disposition patterns
        content, num_fixes = fix_content_disposition_patterns(content)

        # Only write if changed
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            return True, num_fixes

        return False, 0

    except Exception as e:
        print(f"ERROR fixing {filepath}: {e}")
        return False, 0

def main():
    """Main entry point."""
    base_path = Path(__file__).parent
    total_fixes = 0
    total_files = 0

    print("=" * 70)
    print("CRLF Injection Vulnerability Fix")
    print("=" * 70)
    print()

    for file_rel_path in FILES_TO_FIX:
        filepath = base_path / file_rel_path

        if not filepath.exists():
            print(f"SKIP: {file_rel_path} (not found)")
            continue

        success, num_fixes = fix_file(filepath)

        if success:
            total_files += 1
            total_fixes += num_fixes
            print(f"FIXED: {file_rel_path} ({num_fixes} patterns)")
        else:
            print(f"NO CHANGE: {file_rel_path}")

    print()
    print("=" * 70)
    print(f"Summary: Fixed {total_fixes} patterns in {total_files} files")
    print("=" * 70)

if __name__ == "__main__":
    main()
