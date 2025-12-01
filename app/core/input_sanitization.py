# -*- coding: utf-8 -*-
"""
Input Sanitization fuer sichere API-Verarbeitung.

Bietet zentrale Validierungs- und Sanitierungsfunktionen:
- Search Query Sanitization (XSS, ReDoS-Schutz)
- Filename Sanitization
- HTML-Tag-Entfernung
- Unicode Normalization
- SQL-Injection-Schutz (Ergaenzung zu SQLAlchemy)

Konfiguration via Umgebungsvariablen:
- INPUT_MAX_QUERY_LENGTH: Max. Suchquery-Laenge (default: 500)
- INPUT_MAX_FILENAME_LENGTH: Max. Dateiname-Laenge (default: 255)
"""

import html
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class SanitizationConfig:
    """Konfiguration fuer Input Sanitization."""

    # Maximale Laengen
    MAX_QUERY_LENGTH = int(os.environ.get("INPUT_MAX_QUERY_LENGTH", "500"))
    MAX_FILENAME_LENGTH = int(os.environ.get("INPUT_MAX_FILENAME_LENGTH", "255"))
    MAX_TAG_LENGTH = int(os.environ.get("INPUT_MAX_TAG_LENGTH", "50"))
    MAX_PATH_LENGTH = int(os.environ.get("INPUT_MAX_PATH_LENGTH", "1024"))

    # Erlaubte Zeichen fuer verschiedene Kontexte
    # Suchquery: Alphanumerisch + Umlaute + Leerzeichen + einige Sonderzeichen
    QUERY_ALLOWED_PATTERN = re.compile(r'^[\w\säöüÄÖÜß\-_.,:;!?@#&()\[\]"\'*/+]+$', re.UNICODE)

    # Dateinamen: Alphanumerisch + Umlaute + einige Sonderzeichen
    FILENAME_ALLOWED_PATTERN = re.compile(r'^[\w\säöüÄÖÜß\-_.()]+$', re.UNICODE)

    # Tag-Namen: Alphanumerisch + Umlaute + Bindestrich + Unterstrich
    TAG_ALLOWED_PATTERN = re.compile(r'^[\w\säöüÄÖÜß\-_]+$', re.UNICODE)

    # Gefaehrliche Patterns fuer ReDoS (Backtracking-Angriffe)
    REDOS_DANGEROUS_PATTERNS = [
        r'(a+)+',            # Nested quantifiers
        r'(a|aa)+',          # Overlapping alternatives
        r'(.*a){100}',       # Long repetition with wildcard
        r'(\w+)+',           # Nested word quantifiers
    ]

    # Verbotene SQL-Fragmente (Defense in Depth)
    SQL_DANGEROUS_KEYWORDS = [
        'UNION', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP',
        'CREATE', 'ALTER', 'EXEC', 'EXECUTE', 'TRUNCATE',
        'DECLARE', '--', '/*', '*/', ';--', 'xp_', 'sp_'
    ]


class SanitizationError(Exception):
    """Exception fuer Sanitization-Fehler."""

    def __init__(self, message: str, field: str = "", user_message_de: str = ""):
        self.message = message
        self.field = field
        self.user_message_de = user_message_de or f"Ungueltiger Wert fuer {field}"
        super().__init__(self.message)


def sanitize_search_query(
    query: str,
    max_length: Optional[int] = None,
    allow_wildcards: bool = True,
    strict_mode: bool = False
) -> Tuple[str, List[str]]:
    """
    Sanitiert eine Suchanfrage gegen XSS und ReDoS-Angriffe.

    Args:
        query: Originale Suchanfrage
        max_length: Maximale Laenge (default: Config-Wert)
        allow_wildcards: Ob * und ? erlaubt sind
        strict_mode: Strengere Validierung (nur alphanumerisch + Umlaute)

    Returns:
        Tuple von (sanitized_query, warnings)

    Raises:
        SanitizationError: Bei kritischen Validierungsfehlern
    """
    warnings: List[str] = []
    max_len = max_length or SanitizationConfig.MAX_QUERY_LENGTH

    if not query:
        return "", []

    # 1. Unicode-Normalisierung (NFC)
    sanitized = unicodedata.normalize('NFC', query)

    # 2. Null-Bytes entfernen (Injection-Schutz)
    if '\x00' in sanitized:
        warnings.append("Null-Bytes entfernt")
        sanitized = sanitized.replace('\x00', '')

    # 3. Steuerzeichen entfernen (ausser Leerzeichen und Zeilenumbruch)
    control_chars = ''.join(chr(i) for i in range(32) if i not in [9, 10, 13, 32])
    if any(c in sanitized for c in control_chars):
        warnings.append("Steuerzeichen entfernt")
        sanitized = ''.join(c for c in sanitized if c not in control_chars or c in ' \t\n\r')

    # 4. HTML-Tags entfernen (XSS-Schutz)
    if '<' in sanitized or '>' in sanitized:
        warnings.append("HTML-Tags entfernt")
        # Einfache Tag-Entfernung
        sanitized = re.sub(r'<[^>]*>', '', sanitized)
        # HTML-Entities escapen
        sanitized = html.escape(sanitized)

    # 5. Script-Injection-Patterns entfernen
    dangerous_patterns = [
        (r'javascript:', 'JavaScript-Injection blockiert'),
        (r'data:', 'Data-URI blockiert'),
        (r'vbscript:', 'VBScript-Injection blockiert'),
        (r'on\w+\s*=', 'Event-Handler blockiert'),
    ]
    for pattern, warning in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            warnings.append(warning)
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)

    # 6. ReDoS-gefaehrliche Patterns pruefen
    for dangerous in SanitizationConfig.REDOS_DANGEROUS_PATTERNS:
        if re.search(dangerous, sanitized, re.IGNORECASE):
            logger.warning(
                "redos_pattern_detected",
                pattern=dangerous,
                query_preview=sanitized[:50]
            )
            warnings.append("Potentiell gefaehrliches Pattern entfernt")
            # Gefaehrliche Wiederholungen abschwaechechechwaechen
            sanitized = re.sub(r'(.)\1{10,}', r'\1\1\1', sanitized)

    # 7. Wildcards behandeln
    if not allow_wildcards:
        if '*' in sanitized or '?' in sanitized:
            warnings.append("Wildcards entfernt")
            sanitized = sanitized.replace('*', '').replace('?', '')

    # 8. Laenge begrenzen
    if len(sanitized) > max_len:
        warnings.append(f"Auf {max_len} Zeichen gekuerzt")
        sanitized = sanitized[:max_len]

    # 9. Strict Mode: Nur erlaubte Zeichen
    if strict_mode:
        if not SanitizationConfig.QUERY_ALLOWED_PATTERN.match(sanitized):
            # Nicht erlaubte Zeichen entfernen
            allowed = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789äöüÄÖÜß -_.')
            original_len = len(sanitized)
            sanitized = ''.join(c for c in sanitized if c in allowed)
            if len(sanitized) < original_len:
                warnings.append("Nicht erlaubte Zeichen entfernt")

    # 10. Whitespace normalisieren
    sanitized = ' '.join(sanitized.split())

    if warnings:
        logger.info(
            "search_query_sanitized",
            original_length=len(query),
            sanitized_length=len(sanitized),
            warnings=warnings
        )

    return sanitized, warnings


def sanitize_filename(
    filename: str,
    max_length: Optional[int] = None,
    preserve_extension: bool = True
) -> str:
    """
    Sanitiert einen Dateinamen gegen Path-Traversal und Injection.

    Args:
        filename: Originaler Dateiname
        max_length: Maximale Laenge (default: Config-Wert)
        preserve_extension: Ob Dateiendung erhalten bleiben soll

    Returns:
        Sanitierter Dateiname

    Raises:
        SanitizationError: Bei ungueltigem Dateinamen
    """
    max_len = max_length or SanitizationConfig.MAX_FILENAME_LENGTH

    if not filename:
        raise SanitizationError(
            "Dateiname darf nicht leer sein",
            field="filename",
            user_message_de="Bitte geben Sie einen Dateinamen an"
        )

    # 1. Unicode-Normalisierung
    sanitized = unicodedata.normalize('NFC', filename)

    # 2. Null-Bytes entfernen
    sanitized = sanitized.replace('\x00', '')

    # 3. Path-Traversal verhindern
    # Entferne .. und absolute Pfade
    sanitized = sanitized.replace('..', '')
    sanitized = sanitized.replace('/', '')
    sanitized = sanitized.replace('\\', '')

    # 4. Nur Dateiname, kein Pfad
    # Falls noch ein Pfad vorhanden, nur den Dateinamen nehmen
    import os.path
    sanitized = os.path.basename(sanitized)

    # 5. Gefaehrliche Windows-Zeichen entfernen
    windows_forbidden = '<>:"|?*'
    for char in windows_forbidden:
        sanitized = sanitized.replace(char, '_')

    # 6. Steuerzeichen entfernen
    sanitized = ''.join(c for c in sanitized if ord(c) >= 32)

    # 7. Extension separat behandeln
    if preserve_extension and '.' in sanitized:
        name, ext = sanitized.rsplit('.', 1)
        # Extension validieren (max 10 Zeichen, nur alphanumerisch)
        if len(ext) <= 10 and ext.isalnum():
            max_name_len = max_len - len(ext) - 1
            name = name[:max_name_len]
            sanitized = f"{name}.{ext}"
        else:
            sanitized = sanitized[:max_len]
    else:
        sanitized = sanitized[:max_len]

    # 8. Leerer Name nach Sanitization?
    if not sanitized or sanitized == '.':
        raise SanitizationError(
            "Dateiname nach Sanitization leer",
            field="filename",
            user_message_de="Ungueltiger Dateiname - bitte verwenden Sie nur Buchstaben, Zahlen und Unterstriche"
        )

    return sanitized


def sanitize_tag(tag: str, max_length: Optional[int] = None) -> str:
    """
    Sanitiert einen Tag-Namen.

    Args:
        tag: Originaler Tag-Name
        max_length: Maximale Laenge (default: Config-Wert)

    Returns:
        Sanitierter Tag-Name

    Raises:
        SanitizationError: Bei ungueltigem Tag
    """
    max_len = max_length or SanitizationConfig.MAX_TAG_LENGTH

    if not tag:
        raise SanitizationError(
            "Tag darf nicht leer sein",
            field="tag",
            user_message_de="Bitte geben Sie einen Tag-Namen an"
        )

    # 1. Unicode-Normalisierung
    sanitized = unicodedata.normalize('NFC', tag)

    # 2. Whitespace trimmen und normalisieren
    sanitized = ' '.join(sanitized.split())

    # 3. Nur erlaubte Zeichen
    if not SanitizationConfig.TAG_ALLOWED_PATTERN.match(sanitized):
        # Nicht erlaubte Zeichen durch Unterstrich ersetzen
        allowed = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789äöüÄÖÜß-_ ')
        sanitized = ''.join(c if c in allowed else '_' for c in sanitized)

    # 4. Doppelte Unterstriche/Bindestriche reduzieren
    sanitized = re.sub(r'[-_]{2,}', '-', sanitized)

    # 5. Laenge begrenzen
    sanitized = sanitized[:max_len]

    # 6. Fuehrende/folgende Sonderzeichen entfernen
    sanitized = sanitized.strip('-_')

    if not sanitized:
        raise SanitizationError(
            "Tag nach Sanitization leer",
            field="tag",
            user_message_de="Ungueltiger Tag - bitte verwenden Sie nur Buchstaben, Zahlen und Bindestriche"
        )

    return sanitized


def sanitize_html_content(html_content: str, allowed_tags: Optional[List[str]] = None) -> str:
    """
    Entfernt gefaehrliche HTML-Tags, behaelt sichere Tags.

    Args:
        html_content: HTML-Inhalt
        allowed_tags: Liste erlaubter Tag-Namen (default: mark, b, i, em, strong)

    Returns:
        Bereinigter HTML-Inhalt
    """
    if allowed_tags is None:
        allowed_tags = ['mark', 'b', 'i', 'em', 'strong']

    if not html_content:
        return ""

    # 1. Script-Tags komplett entfernen (inkl. Inhalt)
    sanitized = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # 2. Style-Tags komplett entfernen
    sanitized = re.sub(r'<style[^>]*>.*?</style>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)

    # 3. Event-Handler entfernen
    sanitized = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'\s+on\w+\s*=\s*\S+', '', sanitized, flags=re.IGNORECASE)

    # 4. Nur erlaubte Tags behalten
    def tag_replacer(match: re.Match) -> str:
        tag_content = match.group(0)
        # Tag-Namen extrahieren
        tag_match = re.match(r'</?(\w+)', tag_content)
        if tag_match:
            tag_name = tag_match.group(1).lower()
            if tag_name in allowed_tags:
                # Tag behalten, aber Attribute entfernen (ausser fuer mark)
                if tag_name == 'mark':
                    return tag_content
                # Nur einfaches Tag zurueckgeben
                if tag_content.startswith('</'):
                    return f'</{tag_name}>'
                return f'<{tag_name}>'
        return ''  # Tag entfernen

    sanitized = re.sub(r'<[^>]+>', tag_replacer, sanitized)

    return sanitized


def check_sql_injection_patterns(value: str) -> Tuple[bool, Optional[str]]:
    """
    Prueft auf potentielle SQL-Injection-Patterns.

    Dies ist eine Defense-in-Depth-Massnahme zusaetzlich zu parametrisierten Queries.

    Args:
        value: Zu pruefender Wert

    Returns:
        Tuple von (is_safe, detected_pattern)
    """
    if not value:
        return True, None

    value_upper = value.upper()

    for keyword in SanitizationConfig.SQL_DANGEROUS_KEYWORDS:
        # Nur wenn Keyword als ganzes Wort vorkommt
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, value_upper):
            logger.warning(
                "sql_injection_pattern_detected",
                keyword=keyword,
                value_preview=value[:50]
            )
            return False, keyword

    return True, None


def validate_uuid(value: str, field_name: str = "id") -> UUID:
    """
    Validiert und konvertiert einen UUID-String.

    Args:
        value: UUID als String
        field_name: Feldname fuer Fehlermeldung

    Returns:
        UUID-Objekt

    Raises:
        SanitizationError: Bei ungueltigem UUID-Format
    """
    if not value:
        raise SanitizationError(
            f"{field_name} darf nicht leer sein",
            field=field_name,
            user_message_de=f"Bitte geben Sie eine gueltige {field_name} an"
        )

    try:
        return UUID(value)
    except ValueError:
        raise SanitizationError(
            f"Ungueltiges UUID-Format: {value[:50]}",
            field=field_name,
            user_message_de=f"Ungueltige {field_name} - bitte verwenden Sie ein gueltiges UUID-Format"
        )


def sanitize_pagination_params(
    page: int,
    per_page: int,
    max_page: int = 10000,
    max_per_page: int = 100,
    default_per_page: int = 20
) -> Tuple[int, int]:
    """
    Sanitiert Pagination-Parameter.

    Args:
        page: Seitennummer
        per_page: Eintraege pro Seite
        max_page: Maximale Seitennummer
        max_per_page: Maximale Eintraege pro Seite
        default_per_page: Standard-Eintraege pro Seite

    Returns:
        Tuple von (sanitized_page, sanitized_per_page)
    """
    # Page validieren
    if page < 1:
        page = 1
    elif page > max_page:
        page = max_page

    # Per-Page validieren
    if per_page < 1:
        per_page = default_per_page
    elif per_page > max_per_page:
        per_page = max_per_page

    return page, per_page


def create_safe_highlight(text: str, query: str, tag: str = "mark") -> str:
    """
    Erstellt sicheres HTML-Highlighting ohne ReDoS-Gefahr.

    Args:
        text: Zu highlightender Text
        query: Suchbegriff
        tag: HTML-Tag fuer Highlighting (default: mark)

    Returns:
        Text mit HTML-Highlighting
    """
    if not text or not query:
        return text or ""

    # Query sanitieren (keine Regex-Sonderzeichen)
    safe_query = re.escape(query)

    # Nur wenn Tag erlaubt ist
    if tag not in ['mark', 'b', 'em', 'strong']:
        tag = 'mark'

    try:
        # Case-insensitive Ersetzung mit Limit
        pattern = re.compile(safe_query, re.IGNORECASE)
        # Maximal 50 Ersetzungen (DoS-Schutz)
        count = 0
        max_replacements = 50

        def replace_with_limit(match: re.Match) -> str:
            nonlocal count
            if count >= max_replacements:
                return match.group(0)
            count += 1
            return f'<{tag}>{html.escape(match.group(0))}</{tag}>'

        result = pattern.sub(replace_with_limit, text)
        return result

    except re.error as e:
        logger.warning("highlight_regex_error", error=str(e), query=query[:50])
        return html.escape(text)


def get_sanitization_stats() -> Dict[str, Any]:
    """
    Gibt Statistiken ueber Sanitization-Konfiguration zurueck.

    Returns:
        Dict mit Konfigurationswerten
    """
    return {
        "max_query_length": SanitizationConfig.MAX_QUERY_LENGTH,
        "max_filename_length": SanitizationConfig.MAX_FILENAME_LENGTH,
        "max_tag_length": SanitizationConfig.MAX_TAG_LENGTH,
        "max_path_length": SanitizationConfig.MAX_PATH_LENGTH,
        "sql_keywords_blocked": len(SanitizationConfig.SQL_DANGEROUS_KEYWORDS),
        "redos_patterns_checked": len(SanitizationConfig.REDOS_DANGEROUS_PATTERNS),
    }
