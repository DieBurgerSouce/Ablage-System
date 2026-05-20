#!/usr/bin/env python3
"""
Umlaut cleanup script for app/services/.

Replaces ASCII umlaut patterns with real umlauts ONLY inside:
- String literals (single/double/triple-quoted)
- Comments (# ...)
- Docstrings

NEVER modifies:
- Python identifiers (function names, variable names, parameters, class names)
- Keyword arguments in function calls (e.g., fuer_dokument=...)
- Import statements
- Enum values used as identifiers
"""
import re
import sys
import os
import tokenize
import io
from pathlib import Path
from typing import List, Tuple, Dict

# Replacement patterns: (pattern, replacement)
# Order matters - more specific patterns first to avoid partial matches
REPLACEMENTS: List[Tuple[str, str]] = [
    # Wave A - High-frequency
    # "fuer " and variants (with trailing space, period, comma, quote, paren, etc.)
    # We match "fuer" followed by a non-alphanumeric or end of string
    ("Fuer", "Für"),
    ("fuer", "für"),
    ("Muess", "Müss"),
    ("muess", "müss"),
    ("Pruef", "Prüf"),
    ("pruef", "prüf"),
    ("Bestaeti", "Bestäti"),
    ("bestaeti", "bestäti"),
    # "ueber"/"Ueber" - careful, also covers Ueberpr
    ("Ueber", "Über"),
    ("ueber", "über"),

    # Wave B - Medium-frequency
    ("Loesch", "Lösch"),
    ("loesch", "lösch"),
    ("Aender", "Änder"),
    ("aender", "änder"),
    ("Geschaeft", "Geschäft"),
    ("geschaeft", "geschäft"),
    ("Groess", "Größ"),
    ("groess", "größ"),
    ("Vollstaendig", "Vollständig"),
    ("vollstaendig", "vollständig"),
    ("Faellig", "Fällig"),
    ("faellig", "fällig"),
    ("Zurueck", "Zurück"),
    ("zurueck", "zurück"),

    # Wave C - Lower-frequency
    ("Naechst", "Nächst"),
    ("naechst", "nächst"),
    ("Hoehe", "Höhe"),
    ("hoehe", "höhe"),
    ("Moeglic", "Möglic"),
    ("moeglic", "möglic"),
    ("Gueltig", "Gültig"),
    ("gueltig", "gültig"),
    ("Vorschlaeg", "Vorschläg"),
    ("vorschlaeg", "vorschläg"),
    ("Enthaelt", "Enthält"),
    ("enthaelt", "enthält"),
    ("Gebuehr", "Gebühr"),
    ("gebuehr", "gebühr"),
    ("Identitaet", "Identität"),
    ("Einschraenk", "Einschränk"),
    ("einschraenk", "einschränk"),
    ("Koennen", "Können"),
    ("koennen", "können"),
    ("Oeffen", "Öffen"),
    ("oeffen", "öffen"),
    ("Portabilitaet", "Portabilität"),
    ("Saetze", "Sätze"),
    ("saetze", "sätze"),
    ("Aerger", "Ärger"),
    ("aerger", "ärger"),
    ("Verstaerk", "Verstärk"),
    ("verstaerk", "verstärk"),
    ("Verfueg", "Verfüg"),
    ("verfueg", "verfüg"),
    ("Durchfuehr", "Durchführ"),
    ("durchfuehr", "durchführ"),
    ("ausgefuehrt", "ausgeführt"),
    ("Ausgefuehrt", "Ausgeführt"),
    ("zusammenfuehr", "zusammenführ"),
    ("Zusammenfuehr", "Zusammenführ"),
    ("Verknuepf", "Verknüpf"),
    ("verknuepf", "verknüpf"),
    ("Ueberfaellig", "Überfällig"),
    ("ueberfaellig", "überfällig"),
    ("Unguelt", "Ungült"),
    ("unguelt", "ungült"),
    ("Rueckgaengig", "Rückgängig"),
    ("rueckgaengig", "rückgängig"),
    ("Rueck", "Rück"),
    ("rueck", "rück"),
    # Ueberpr is already covered by Ueber->Über

    # Wave D - Additional common patterns found in remaining files
    ("Benoeti", "Benöti"),
    ("benoeti", "benöti"),
    ("Oeffn", "Öffn"),
    ("oeffn", "öffn"),
    ("Gewuensch", "Gewünsch"),
    ("gewuensch", "gewünsch"),
    ("Ausfuehr", "Ausführ"),
    ("ausfuehr", "ausführ"),
    ("Natuerlich", "Natürlich"),
    ("natuerlich", "natürlich"),
    ("Fuehr", "Führ"),
    ("fuehr", "führ"),
    ("Stoerung", "Störung"),
    ("stoerung", "störung"),
    ("Erhoeh", "Erhöh"),
    ("erhoeh", "erhöh"),
    ("Waehr", "Währ"),
    ("waehr", "währ"),
    ("Unterstuetz", "Unterstütz"),
    ("unterstuetz", "unterstütz"),
    ("Eroeffn", "Eröffn"),
    ("eroeffn", "eröffn"),
    ("Regelmaess", "Regelmäß"),
    ("regelmaess", "regelmäß"),
    ("Zulaess", "Zuläss"),
    ("zulaess", "zuläss"),
    ("Spaet", "Spät"),
    ("spaet", "spät"),
    ("Haeuf", "Häuf"),
    ("haeuf", "häuf"),
    ("Waehle", "Wähle"),
    ("waehle", "wähle"),
    ("Auswaeh", "Auswäh"),
    ("auswaeh", "auswäh"),
    ("Zusaetzl", "Zusätzl"),
    ("zusaetzl", "zusätzl"),
    ("Schaetz", "Schätz"),
    ("schaetz", "schätz"),
    ("Gewaehr", "Gewähr"),
    ("gewaehr", "gewähr"),
    ("Erklaer", "Erklär"),
    ("erklaer", "erklär"),
    ("Abhaengig", "Abhängig"),
    ("abhaengig", "abhängig"),
    ("Eigenstaendig", "Eigenständig"),
    ("eigenstaendig", "eigenständig"),
    ("Staerke", "Stärke"),
    ("staerke", "stärke"),
    ("Taeglich", "Täglich"),
    ("taeglich", "täglich"),
    ("Jaehrlich", "Jährlich"),
    ("jaehrlich", "jährlich"),
    ("Saeumnis", "Säumnis"),
    ("saeumnis", "säumnis"),
    ("Moeglich", "Möglich"),
    ("moeglich", "möglich"),
    ("Veroeffentlich", "Veröffentlich"),
    ("veroeffentlich", "veröffentlich"),
    ("Voellig", "Völlig"),
    ("voellig", "völlig"),
    ("Ueblicherweise", "Üblicherweise"),
    ("ueblicherweise", "üblicherweise"),
    ("Sorgfaeltig", "Sorgfältig"),
    ("sorgfaeltig", "sorgfältig"),
    ("Aehnlich", "Ähnlich"),
    ("aehnlich", "ähnlich"),
    ("Aequivalent", "Äquivalent"),
    ("aequivalent", "äquivalent"),
    ("Ueberschreit", "Überschreit"),
    ("ueberschreit", "überschreit"),
    ("Ueberschuss", "Überschuss"),
    ("ueberschuss", "überschuss"),
    ("Kuendig", "Kündig"),
    ("kuendig", "kündig"),
    ("Stueck", "Stück"),
    ("stueck", "stück"),
    ("Wuensch", "Wünsch"),
    ("wuensch", "wünsch"),
    ("Rueckerstatt", "Rückerstatt"),
    ("rueckerstatt", "rückerstatt"),
    ("Beguenstig", "Begünstig"),
    ("beguenstig", "begünstig"),
    ("Kuerzlich", "Kürzlich"),
    ("kuerzlich", "kürzlich"),
    ("Kuerz", "Kürz"),
    ("kuerz", "kürz"),
    ("Laeng", "Läng"),
    ("laeng", "läng"),
    ("Guenstig", "Günstig"),
    ("guenstig", "günstig"),
    ("Verspaet", "Verspät"),
    ("verspaet", "verspät"),
    ("Bewaeltig", "Bewältig"),
    ("bewaeltig", "bewältig"),
    ("Taetigkeit", "Tätigkeit"),
    ("taetigkeit", "tätigkeit"),
    ("Naehr", "Nähr"),
    ("naehr", "nähr"),
    ("Verlaenger", "Verlänger"),
    ("verlaenger", "verlänger"),
    ("Unzulaessig", "Unzulässig"),
    ("unzulaessig", "unzulässig"),
    ("Aeusser", "Äußer"),
    ("aeusser", "äußer"),
    ("Groesstmoeglich", "Größtmöglich"),
    ("groesstmoeglich", "größtmöglich"),
    ("Vorlaeufig", "Vorläufig"),
    ("vorlaeufig", "vorläufig"),
    ("Beschaeftig", "Beschäftig"),
    ("beschaeftig", "beschäftig"),
    ("Schutzbeduerftig", "Schutzbedürftig"),
    ("schutzbeduerftig", "schutzbedürftig"),
    ("Beduerftig", "Bedürftig"),
    ("beduerftig", "bedürftig"),
    ("Beduerfnis", "Bedürfnis"),
    ("beduerfnis", "bedürfnis"),
    ("Verhaeltnis", "Verhältnis"),
    ("verhaeltnis", "verhältnis"),
    ("Zustaendig", "Zuständig"),
    ("zustaendig", "zuständig"),
    ("Unabhaengig", "Unabhängig"),
    ("unabhaengig", "unabhängig"),
    ("Voruebergehend", "Vorübergehend"),
    ("voruebergehend", "vorübergehend"),
    ("Verzoeger", "Verzöger"),
    ("verzoeger", "verzöger"),
    ("Empfaeng", "Empfäng"),
    ("empfaeng", "empfäng"),
    ("Ertraeg", "Erträg"),
    ("ertraeg", "erträg"),
    ("Eintraeg", "Einträg"),
    ("eintraeg", "einträg"),
    ("Betrueg", "Betrüg"),
    ("betrueg", "betrüg"),
    ("Frueh", "Früh"),
    ("frueh", "früh"),
    ("Aufwaend", "Aufwänd"),
    ("aufwaend", "aufwänd"),
    ("Bestaende", "Bestände"),
    ("bestaende", "bestände"),

    # Wave E - Additional missed patterns (Phase 2 audit)
    ("Koennt", "Könnt"),
    ("koennt", "könnt"),
    ("Lueck", "Lück"),
    ("lueck", "lück"),
    ("Zirkulaer", "Zirkulär"),
    ("zirkulaer", "zirkulär"),
    ("waerts", "wärts"),
    ("Kompatibilitaet", "Kompatibilität"),
    ("kompatibilitaet", "kompatibilität"),

    # schliess patterns
    ("ausschliesslich", "ausschließlich"),
    ("Ausschliesslich", "Ausschließlich"),
    ("schliessen", "schließen"),
    ("Schliessen", "Schließen"),
    ("schliesst", "schließt"),
    ("Schliesst", "Schließt"),
    ("Schliessung", "Schließung"),
    ("schliessung", "schließung"),
    ("abschliessen", "abschließen"),
    ("Abschliessen", "Abschließen"),
    ("anschliessend", "anschließend"),
    ("Anschliessend", "Anschließend"),
]


def apply_replacements(text: str) -> str:
    """Apply all umlaut replacements to a piece of text."""
    result = text
    for old, new in REPLACEMENTS:
        result = result.replace(old, new)
    return result


def process_file(filepath: str, dry_run: bool = False) -> Tuple[bool, int, List[str]]:
    """
    Process a single Python file, replacing ASCII umlauts only in strings and comments.

    Uses Python's tokenizer to identify STRING and COMMENT tokens.
    Only modifies content within those tokens.

    Returns: (changed, replacement_count, changes_list)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    if not source.strip():
        return False, 0, []

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        # File has syntax issues, skip it
        return False, 0, [f"SKIP (tokenize error): {filepath}"]

    # Build a list of (start_offset, end_offset, token_type) for STRING and COMMENT tokens
    lines = source.split("\n")

    # Convert (row, col) to absolute offset
    line_offsets = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line) + 1)  # +1 for newline

    def pos_to_offset(row: int, col: int) -> int:
        """Convert 1-based row and 0-based col to absolute offset."""
        if row - 1 < len(line_offsets):
            return line_offsets[row - 1] + col
        return len(source)

    # Collect regions that are safe to modify (strings, comments, f-string parts)
    # Python 3.12+ tokenizes f-strings with FSTRING_START/FSTRING_MIDDLE/FSTRING_END
    safe_token_types = {tokenize.STRING, tokenize.COMMENT}
    if hasattr(tokenize, "FSTRING_MIDDLE"):
        safe_token_types.add(tokenize.FSTRING_MIDDLE)

    safe_regions: List[Tuple[int, int]] = []

    for tok in tokens:
        if tok.type in safe_token_types:
            start = pos_to_offset(tok.start[0], tok.start[1])
            end = pos_to_offset(tok.end[0], tok.end[1])
            safe_regions.append((start, end))

    if not safe_regions:
        return False, 0, []

    # Now process the source: only replace within safe regions
    result_parts = []
    last_pos = 0
    total_replacements = 0
    changes = []

    for region_start, region_end in sorted(safe_regions):
        # Add unchanged text before this region
        if region_start > last_pos:
            result_parts.append(source[last_pos:region_start])

        # Get the region text and apply replacements
        region_text = source[region_start:region_end]
        modified_text = apply_replacements(region_text)

        if modified_text != region_text:
            # Count replacements
            for old, new in REPLACEMENTS:
                count = region_text.count(old)
                if count > 0:
                    total_replacements += count
                    # Find line number for reporting
                    line_no = source[:region_start].count("\n") + 1
                    changes.append(f"  L{line_no}: '{old}' -> '{new}' ({count}x)")

        result_parts.append(modified_text)
        last_pos = region_end

    # Add remaining text
    if last_pos < len(source):
        result_parts.append(source[last_pos:])

    new_source = "".join(result_parts)

    if new_source == source:
        return False, 0, []

    if not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_source)

    return True, total_replacements, changes


def verify_syntax(filepath: str) -> bool:
    """Verify the file compiles without syntax errors."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        compile(source, filepath, "exec")
        return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {filepath}: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    base_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent / "app"

    # Allow overriding the target directory via CLI argument
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and not arg.startswith("-"):
            candidate = Path(os.path.dirname(os.path.abspath(__file__))).parent / arg
            if candidate.exists():
                base_dir = candidate

    if not base_dir.exists():
        print(f"ERROR: {base_dir} does not exist")
        sys.exit(1)

    # Files to skip (intentional OCR corruption patterns only)
    SKIP_SUFFIXES = {
        "app/ml/finetuning/umlaut_weighted_loss.py",
        "app/ml/quality_metrics.py",
        # Semantic-data files: keys/values must stay ASCII for OCR/DB/enum contracts
        "app/agents/postprocessing/german_correction_agent.py",
        "app/services/privat/tax_optimization_service.py",
        "app/api/v1/entities.py",
        "app/services/umlaut_validation_service.py",      # KNOWN_UMLAUT_WORDS mapping
        "app/german_validator.py",                         # OCR_ERROR_PATTERNS semantic data
        "app/api/schemas/responses.py",                    # seiten_groesse field name in docstring
        "app/services/contextual_umlaut_restorer.py",      # NO_UMLAUT_WORDS must stay ASCII
        "app/services/german_spellchecker.py",             # OCR_ERROR_PATTERNS keys must stay ASCII
        "app/services/german_phonetic_matcher.py",          # NAME_EQUIVALENTS ASCII variants for phonetic matching
    }

    py_files = sorted(base_dir.rglob("*.py"))
    # Filter out __pycache__ and skip files
    py_files = [
        f for f in py_files
        if "__pycache__" not in str(f)
        and not any(str(f).replace("\\", "/").endswith(s) for s in SKIP_SUFFIXES)
    ]
    print(f"Found {len(py_files)} Python files in {base_dir} (after filtering)")

    if dry_run:
        print("DRY RUN - no files will be modified\n")

    total_changed = 0
    total_replacements = 0
    total_errors = 0
    changed_files = []

    for filepath in py_files:
        changed, count, changes = process_file(str(filepath), dry_run=dry_run)

        if changed:
            total_changed += 1
            total_replacements += count
            changed_files.append(str(filepath))

            if verbose:
                print(f"CHANGED: {filepath.relative_to(base_dir.parent.parent)} ({count} replacements)")
                for change in changes[:10]:  # Limit output per file
                    print(change)
                if len(changes) > 10:
                    print(f"  ... and {len(changes) - 10} more")

            # Verify syntax after modification (only if not dry run)
            if not dry_run:
                if not verify_syntax(str(filepath)):
                    total_errors += 1
                    print(f"  ERROR: Syntax error after modification! Restoring is recommended.")

    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Files scanned:  {len(py_files)}")
    print(f"  Files changed:  {total_changed}")
    print(f"  Replacements:   {total_replacements}")
    print(f"  Syntax errors:  {total_errors}")

    if dry_run:
        print(f"\n  (Dry run - no files were actually modified)")

    if total_errors > 0:
        print(f"\n  WARNING: {total_errors} files have syntax errors after modification!")
        sys.exit(1)

    return total_changed


if __name__ == "__main__":
    main()
