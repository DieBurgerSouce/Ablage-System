# -*- coding: utf-8 -*-
"""
Backend i18n Implementation for Ablage-System

Provides:
- Translation function with interpolation
- Thread-safe language context
- Accept-Language header parsing
- Fallback chain (requested -> default -> key)

CRITICAL: German is the source of truth. All keys must exist in German first.
"""

import re
from contextvars import ContextVar
from typing import Dict, List, Optional, Tuple, Type

import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

SUPPORTED_LANGUAGES: Tuple[str, ...] = ("de", "en")
DEFAULT_LANGUAGE: str = "de"
FALLBACK_LANGUAGE: str = "de"

# Thread-safe context for current language
_current_language: ContextVar[str] = ContextVar("current_language", default=DEFAULT_LANGUAGE)

# =============================================================================
# Translation Catalogs
# =============================================================================

# German translations (source of truth)
_TRANSLATIONS_DE: Dict[str, str] = {
    # Common
    "common.success": "Erfolgreich",
    "common.error": "Fehler",
    "common.loading": "Wird geladen...",
    "common.saving": "Wird gespeichert...",
    "common.deleting": "Wird gelöscht...",
    "common.processing": "Wird verarbeitet...",

    # HTTP Errors
    "error.bad_request": "Ungültige Anfrage",
    "error.unauthorized": "Nicht autorisiert",
    "error.forbidden": "Zugriff verweigert",
    "error.not_found": "Nicht gefunden",
    "error.conflict": "Konflikt",
    "error.validation": "Validierungsfehler",
    "error.rate_limit": "Zu viele Anfragen. Bitte warten Sie {seconds} Sekunden.",
    "error.server_error": "Interner Serverfehler",
    "error.service_unavailable": "Dienst vorübergehend nicht verfügbar",
    "error.timeout": "Zeitüberschreitung",

    # Authentication
    "auth.invalid_credentials": "Ungültige Anmeldedaten",
    "auth.session_expired": "Sitzung abgelaufen. Bitte erneut anmelden.",
    "auth.token_invalid": "Ungültiger Authentifizierungstoken",
    "auth.account_disabled": "Konto deaktiviert",
    "auth.account_locked": "Konto gesperrt. Bitte kontaktieren Sie den Administrator.",
    "auth.too_many_attempts": "Zu viele Anmeldeversuche. Bitte warten Sie {minutes} Minuten.",
    "auth.password_changed": "Passwort erfolgreich geändert",
    "auth.logged_out": "Erfolgreich abgemeldet",

    # Documents
    "document.not_found": "Dokument nicht gefunden",
    "document.uploaded_successfully": "Dokument erfolgreich hochgeladen",
    "document.upload_failed": "Fehler beim Hochladen des Dokuments",
    "document.processing": "Dokument wird verarbeitet...",
    "document.processed_successfully": "Dokument erfolgreich verarbeitet",
    "document.processing_failed": "Dokumentverarbeitung fehlgeschlagen",
    "document.deleted_successfully": "Dokument erfolgreich gelöscht",
    "document.delete_failed": "Fehler beim Löschen des Dokuments",
    "document.page_count": "{count} Seiten",
    "document.file_too_large": "Datei zu gross: {size_mb:.1f}MB (max: {max_mb:.1f}MB)",
    "document.invalid_type": "Ungültiger Dateityp. Erlaubt: {allowed}",
    "document.access_denied": "Kein Zugriff auf dieses Dokument",

    # OCR
    "ocr.processing_started": "OCR-Verarbeitung gestartet",
    "ocr.processing_completed": "OCR-Verarbeitung abgeschlossen",
    "ocr.processing_failed": "OCR-Verarbeitung fehlgeschlagen",
    "ocr.backend_not_available": "OCR-Backend nicht verfügbar: {backend}",
    "ocr.gpu_oom": "GPU-Speicher voll. Fallback auf CPU wird verwendet.",
    "ocr.timeout": "OCR-Zeitüberschreitung",
    "ocr.confidence": "Erkennungssicherheit: {percent}%",
    "ocr.processing_page": "Verarbeite Seite {current} von {total}",

    # Entities
    "entity.not_found": "Geschäftspartner nicht gefunden",
    "entity.created": "Geschäftspartner erfolgreich erstellt",
    "entity.updated": "Geschäftspartner erfolgreich aktualisiert",
    "entity.deleted": "Geschäftspartner erfolgreich gelöscht",
    "entity.duplicate_customer_number": "Kundennummer bereits vergeben",
    "entity.duplicate_supplier_number": "Lieferantennummer bereits vergeben",
    "entity.invalid_vat_id": "Ungültige USt-IdNr.",
    "entity.invalid_iban": "Ungültige IBAN",

    # Banking
    "banking.account_not_found": "Konto nicht gefunden",
    "banking.transaction_not_found": "Transaktion nicht gefunden",
    "banking.payment_created": "Zahlung erfolgreich erstellt",
    "banking.payment_executed": "Zahlung erfolgreich ausgeführt",
    "banking.payment_failed": "Zahlung fehlgeschlagen",
    "banking.reconciliation_complete": "Kontoabstimmung abgeschlossen",
    "banking.insufficient_funds": "Unzureichende Deckung",

    # Workflow
    "workflow.not_found": "Workflow nicht gefunden",
    "workflow.started": "Workflow gestartet",
    "workflow.completed": "Workflow abgeschlossen",
    "workflow.approval_required": "Genehmigung erforderlich",
    "workflow.approved": "Genehmigt",
    "workflow.rejected": "Abgelehnt",
    "workflow.escalated": "Eskaliert an {user}",

    # System
    "system.healthy": "System betriebsbereit",
    "system.degraded": "System eingeschraenkt",
    "system.unhealthy": "System nicht verfügbar",
    "system.maintenance": "Wartungsarbeiten. Bitte versuchen Sie es später.",
    "system.backup_started": "Sicherung gestartet",
    "system.backup_completed": "Sicherung abgeschlossen",
    "system.backup_failed": "Sicherung fehlgeschlagen",

    # Validation
    "validation.required": "Dieses Feld ist erforderlich",
    "validation.email": "Bitte geben Sie eine gültige E-Mail-Adresse ein",
    "validation.min_length": "Mindestens {min} Zeichen erforderlich",
    "validation.max_length": "Maximal {max} Zeichen erlaubt",
    "validation.invalid_format": "Ungültiges Format",
    "validation.password_weak": "Passwort entspricht nicht den Anforderungen",
    "validation.passwords_mismatch": "Passwoerter stimmen nicht überein",

    # Retention
    "retention.active_lock": "Aufbewahrungsfrist aktiv - Löschung gesperrt",
    "retention.expires_in_days": "Aufbewahrungsfrist laeuft in {days} Tagen ab",
    "retention.expired": "Aufbewahrungsfrist abgelaufen",
    "retention.gdpr_conflict": "DSGVO-Löschantrag kollidiert mit Aufbewahrungspflicht",
    "retention.gdpr_retention_wins": "Aufbewahrungspflicht hat Vorrang (§147 AO)",
    "retention.review_scheduled": "Prüfung nach Fristablauf geplant",
    "retention.compliance_ok": "Alle Aufbewahrungsfristen eingehalten",
    "retention.violation_found": "Aufbewahrungsfrist-Verletzung gefunden",

    # Compliance
    "compliance.gobd_compliant": "GoBD-konform",
    "compliance.gobd_violation": "GoBD-Verstoss",
    "compliance.audit_trail_complete": "Audit-Trail vollständig",
    "compliance.data_integrity_verified": "Datenintegritaet verifiziert",
    "compliance.report_generated": "Compliance-Bericht erstellt",

    # Reporting
    "reporting.generating": "Bericht wird erstellt...",
    "reporting.export_ready": "Export bereit zum Herunterladen",
    "reporting.no_data": "Keine Daten für den gewaehlten Zeitraum",
    "reporting.date_range_invalid": "Ungültiger Zeitraum",

    # Procurement
    "procurement.po_created": "Bestellung erfolgreich erstellt",
    "procurement.delivery_confirmed": "Wareneingang bestätigt",
    "procurement.invoice_matched": "Rechnung zugeordnet",
    "procurement.matching_failed": "Zuordnung fehlgeschlagen",
    "procurement.three_way_match": "Drei-Wege-Abgleich erfolgreich",

    # AI
    "ai.trust_level_auto": "Automatische Verarbeitung (Trust Level 1)",
    "ai.trust_level_confirm": "Bestätigung erforderlich (Trust Level 2)",
    "ai.trust_level_explicit": "Explizite Genehmigung erforderlich (Trust Level 3)",
    "ai.confidence_high": "Hohe Erkennungssicherheit",
    "ai.confidence_low": "Niedrige Erkennungssicherheit - manuelle Prüfung empfohlen",
    "ai.decision_explanation": "KI-Entscheidungserklärung",

    # Archive
    "archive.signed_successfully": "Dokument erfolgreich signiert",
    "archive.signature_verified": "Signatur verifiziert",
    "archive.signature_invalid": "Signatur ungültig",
    "archive.pdf_a3_created": "PDF/A-3 Archiv erstellt",
}

# English translations
_TRANSLATIONS_EN: Dict[str, str] = {
    # Common
    "common.success": "Success",
    "common.error": "Error",
    "common.loading": "Loading...",
    "common.saving": "Saving...",
    "common.deleting": "Deleting...",
    "common.processing": "Processing...",

    # HTTP Errors
    "error.bad_request": "Bad request",
    "error.unauthorized": "Unauthorized",
    "error.forbidden": "Access denied",
    "error.not_found": "Not found",
    "error.conflict": "Conflict",
    "error.validation": "Validation error",
    "error.rate_limit": "Too many requests. Please wait {seconds} seconds.",
    "error.server_error": "Internal server error",
    "error.service_unavailable": "Service temporarily unavailable",
    "error.timeout": "Request timeout",

    # Authentication
    "auth.invalid_credentials": "Invalid credentials",
    "auth.session_expired": "Session expired. Please sign in again.",
    "auth.token_invalid": "Invalid authentication token",
    "auth.account_disabled": "Account disabled",
    "auth.account_locked": "Account locked. Please contact administrator.",
    "auth.too_many_attempts": "Too many login attempts. Please wait {minutes} minutes.",
    "auth.password_changed": "Password changed successfully",
    "auth.logged_out": "Signed out successfully",

    # Documents
    "document.not_found": "Document not found",
    "document.uploaded_successfully": "Document uploaded successfully",
    "document.upload_failed": "Error uploading document",
    "document.processing": "Processing document...",
    "document.processed_successfully": "Document processed successfully",
    "document.processing_failed": "Document processing failed",
    "document.deleted_successfully": "Document deleted successfully",
    "document.delete_failed": "Error deleting document",
    "document.page_count": "{count} pages",
    "document.file_too_large": "File too large: {size_mb:.1f}MB (max: {max_mb:.1f}MB)",
    "document.invalid_type": "Invalid file type. Allowed: {allowed}",
    "document.access_denied": "No access to this document",

    # OCR
    "ocr.processing_started": "OCR processing started",
    "ocr.processing_completed": "OCR processing completed",
    "ocr.processing_failed": "OCR processing failed",
    "ocr.backend_not_available": "OCR backend unavailable: {backend}",
    "ocr.gpu_oom": "GPU out of memory. Falling back to CPU.",
    "ocr.timeout": "OCR timeout",
    "ocr.confidence": "Confidence: {percent}%",
    "ocr.processing_page": "Processing page {current} of {total}",

    # Entities
    "entity.not_found": "Business partner not found",
    "entity.created": "Business partner created successfully",
    "entity.updated": "Business partner updated successfully",
    "entity.deleted": "Business partner deleted successfully",
    "entity.duplicate_customer_number": "Customer number already exists",
    "entity.duplicate_supplier_number": "Supplier number already exists",
    "entity.invalid_vat_id": "Invalid VAT ID",
    "entity.invalid_iban": "Invalid IBAN",

    # Banking
    "banking.account_not_found": "Account not found",
    "banking.transaction_not_found": "Transaction not found",
    "banking.payment_created": "Payment created successfully",
    "banking.payment_executed": "Payment executed successfully",
    "banking.payment_failed": "Payment failed",
    "banking.reconciliation_complete": "Reconciliation completed",
    "banking.insufficient_funds": "Insufficient funds",

    # Workflow
    "workflow.not_found": "Workflow not found",
    "workflow.started": "Workflow started",
    "workflow.completed": "Workflow completed",
    "workflow.approval_required": "Approval required",
    "workflow.approved": "Approved",
    "workflow.rejected": "Rejected",
    "workflow.escalated": "Escalated to {user}",

    # System
    "system.healthy": "System operational",
    "system.degraded": "System degraded",
    "system.unhealthy": "System unavailable",
    "system.maintenance": "Maintenance in progress. Please try later.",
    "system.backup_started": "Backup started",
    "system.backup_completed": "Backup completed",
    "system.backup_failed": "Backup failed",

    # Validation
    "validation.required": "This field is required",
    "validation.email": "Please enter a valid email address",
    "validation.min_length": "Minimum {min} characters required",
    "validation.max_length": "Maximum {max} characters allowed",
    "validation.invalid_format": "Invalid format",
    "validation.password_weak": "Password does not meet requirements",
    "validation.passwords_mismatch": "Passwords do not match",

    # Retention
    "retention.active_lock": "Retention period active - deletion locked",
    "retention.expires_in_days": "Retention expires in {days} days",
    "retention.expired": "Retention period expired",
    "retention.gdpr_conflict": "GDPR deletion request conflicts with retention obligation",
    "retention.gdpr_retention_wins": "Retention obligation takes precedence (§147 AO)",
    "retention.review_scheduled": "Review after expiry scheduled",
    "retention.compliance_ok": "All retention periods complied with",
    "retention.violation_found": "Retention period violation found",

    # Compliance
    "compliance.gobd_compliant": "GoBD compliant",
    "compliance.gobd_violation": "GoBD violation",
    "compliance.audit_trail_complete": "Audit trail complete",
    "compliance.data_integrity_verified": "Data integrity verified",
    "compliance.report_generated": "Compliance report generated",

    # Reporting
    "reporting.generating": "Generating report...",
    "reporting.export_ready": "Export ready for download",
    "reporting.no_data": "No data for the selected period",
    "reporting.date_range_invalid": "Invalid date range",

    # Procurement
    "procurement.po_created": "Purchase order created successfully",
    "procurement.delivery_confirmed": "Delivery confirmed",
    "procurement.invoice_matched": "Invoice matched",
    "procurement.matching_failed": "Matching failed",
    "procurement.three_way_match": "Three-way match successful",

    # AI
    "ai.trust_level_auto": "Automatic processing (Trust Level 1)",
    "ai.trust_level_confirm": "Confirmation required (Trust Level 2)",
    "ai.trust_level_explicit": "Explicit approval required (Trust Level 3)",
    "ai.confidence_high": "High recognition confidence",
    "ai.confidence_low": "Low recognition confidence - manual review recommended",
    "ai.decision_explanation": "AI decision explanation",

    # Archive
    "archive.signed_successfully": "Document signed successfully",
    "archive.signature_verified": "Signature verified",
    "archive.signature_invalid": "Signature invalid",
    "archive.pdf_a3_created": "PDF/A-3 archive created",
}

# Translation catalog by language
_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "de": _TRANSLATIONS_DE,
    "en": _TRANSLATIONS_EN,
}


# =============================================================================
# Translation Functions
# =============================================================================

def get_language() -> str:
    """Get the current language from context."""
    return _current_language.get()


def set_language(language: str) -> None:
    """
    Set the current language in context.

    Args:
        language: Language code (de, en)
    """
    if language not in SUPPORTED_LANGUAGES:
        logger.warning(
            "unsupported_language",
            language=language,
            fallback=DEFAULT_LANGUAGE,
        )
        language = DEFAULT_LANGUAGE

    _current_language.set(language)


def get_available_languages() -> List[str]:
    """Get list of available languages."""
    return list(SUPPORTED_LANGUAGES)


def detect_language_from_header(accept_language: Optional[str]) -> str:
    """
    Parse Accept-Language header and return best matching language.

    Args:
        accept_language: Accept-Language header value

    Returns:
        Best matching language code

    Example:
        detect_language_from_header("de-DE,de;q=0.9,en;q=0.8") -> "de"
        detect_language_from_header("en-US,en;q=0.9") -> "en"
        detect_language_from_header("fr-FR,fr;q=0.9") -> "de" (fallback)
    """
    if not accept_language:
        return DEFAULT_LANGUAGE

    # Parse Accept-Language header
    # Format: "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
    languages: List[Tuple[str, float]] = []

    for part in accept_language.split(","):
        part = part.strip()
        if not part:
            continue

        # Split language and quality
        if ";q=" in part:
            lang, q = part.split(";q=", 1)
            try:
                quality = float(q)
            except ValueError:
                quality = 1.0
        else:
            lang = part
            quality = 1.0

        # Extract primary language tag (e.g., "de-DE" -> "de")
        lang = lang.strip().lower()
        if "-" in lang:
            lang = lang.split("-")[0]

        languages.append((lang, quality))

    # Sort by quality (descending)
    languages.sort(key=lambda x: x[1], reverse=True)

    # Find first supported language
    for lang, _ in languages:
        if lang in SUPPORTED_LANGUAGES:
            return lang

    return DEFAULT_LANGUAGE


def t(key: str, **kwargs: object) -> str:
    """
    Translate a key to the current language.

    Args:
        key: Translation key (e.g., "document.uploaded_successfully")
        **kwargs: Interpolation values

    Returns:
        Translated string with interpolated values

    Example:
        t("document.page_count", count=5) -> "5 Seiten" (German)
        t("error.rate_limit", seconds=30) -> "Too many requests. Please wait 30 seconds." (English)
    """
    language = get_language()

    # Get translation from current language
    catalog = _TRANSLATIONS.get(language, {})
    message = catalog.get(key)

    # Fallback to default language
    if message is None and language != FALLBACK_LANGUAGE:
        catalog = _TRANSLATIONS.get(FALLBACK_LANGUAGE, {})
        message = catalog.get(key)

    # Fallback to key itself
    if message is None:
        logger.warning("missing_translation", key=key, language=language)
        return key

    # Interpolate values
    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError as e:
            logger.warning(
                "translation_interpolation_error",
                key=key,
                missing_key=str(e),
            )

    return message


def tn(namespace: str, key: str, **kwargs: object) -> str:
    """
    Translate a key with explicit namespace.

    Args:
        namespace: Namespace (e.g., "document", "error")
        key: Translation key within namespace
        **kwargs: Interpolation values

    Returns:
        Translated string

    Example:
        tn("document", "uploaded_successfully") -> "Dokument erfolgreich hochgeladen"
    """
    full_key = f"{namespace}.{key}"
    return t(full_key, **kwargs)


class TranslationContext:
    """
    Context manager for temporarily setting language.

    Example:
        with TranslationContext("en"):
            message = t("document.uploaded_successfully")  # English
    """

    def __init__(self, language: str):
        self.language = language
        self.previous_language: Optional[str] = None

    def __enter__(self) -> "TranslationContext":
        self.previous_language = get_language()
        set_language(self.language)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        if self.previous_language is not None:
            set_language(self.previous_language)
