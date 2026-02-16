"""
Import Services Package.

E-Mail- und Ordner-Import für das Ablage-System.
"""

from .email_import_service import EmailImportService
from .folder_import_service import FolderImportService
from .import_rule_service import ImportRuleService
from .email_sender_matcher import (
    EmailSenderMatcherService,
    EmailMatchResult,
    EmailMatchSuggestion,
    EmailSenderInfo,
    get_email_sender_matcher,
)

__all__ = [
    "EmailImportService",
    "FolderImportService",
    "ImportRuleService",
    "EmailSenderMatcherService",
    "EmailMatchResult",
    "EmailMatchSuggestion",
    "EmailSenderInfo",
    "get_email_sender_matcher",
]
