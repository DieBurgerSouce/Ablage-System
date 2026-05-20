# -*- coding: utf-8 -*-
"""
AIMentorService - Proaktive Hilfe und personalisierte Tipps.

Verantwortlich für:
- Kontextuelle Tipps basierend auf aktueller Seite
- Verhaltensmuster-Analyse
- Personalisierte Empfehlungen
- Progressive Disclosure (Anfaenger -> Fortgeschrittener)
- Shortcut-Vorschläge

Vision 2.0 - Feature #9 (Januar 2026)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import User, UserBehaviorLog

logger = structlog.get_logger(__name__)


class TipCategory(str, Enum):
    """Kategorie eines Tipps."""

    SHORTCUT = "shortcut"
    AUTOMATION = "automation"
    PATTERN = "pattern"
    OPTIMIZATION = "optimization"
    WARNING = "warning"
    FEATURE = "feature"
    BEST_PRACTICE = "best_practice"


class TipPriority(str, Enum):
    """Priorität eines Tipps."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UserExperience(str, Enum):
    """Erfahrungsstufe des Benutzers."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class Tip:
    """Ein personalisierter Tipp."""

    id: str
    title: str
    content: str
    category: TipCategory
    priority: TipPriority
    context_pages: List[str] = field(default_factory=list)
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    shortcut: Optional[str] = None
    experience_level: UserExperience = UserExperience.BEGINNER
    created_at: datetime = field(default_factory=utc_now)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BehaviorPattern:
    """Ein erkanntes Verhaltensmuster."""

    id: str
    pattern_type: str
    description: str
    frequency: int
    last_occurrence: datetime
    recommendation: str
    potential_savings_minutes: int = 0


@dataclass
class MentorPreferences:
    """Benutzer-Praeferenzen für den AI-Mentor."""

    enabled: bool = True
    show_shortcuts: bool = True
    show_automation_tips: bool = True
    show_pattern_insights: bool = True
    experience_level: UserExperience = UserExperience.BEGINNER
    dismissed_tips: Set[str] = field(default_factory=set)
    max_tips_per_session: int = 5
    tip_frequency_hours: int = 24


# ============================================================================
# TIP LIBRARY - Vordefinierte Tipps auf Deutsch
# ============================================================================

TIP_LIBRARY: List[Dict[str, Any]] = [
    # Shortcuts
    {
        "id": "tip_shortcut_search",
        "title": "Schnellsuche",
        "content": "Drücken Sie Ctrl+K oder Cmd+K, um die Schnellsuche zu öffnen. "
                   "So finden Sie Dokumente in Sekunden.",
        "category": TipCategory.SHORTCUT,
        "priority": TipPriority.HIGH,
        "context_pages": ["documents", "dashboard", "inbox"],
        "shortcut": "Ctrl+K",
        "experience_level": UserExperience.BEGINNER,
    },
    {
        "id": "tip_shortcut_upload",
        "title": "Schnell-Upload",
        "content": "Mit Ctrl+U können Sie direkt ein neues Dokument hochladen, "
                   "ohne den Upload-Button zu suchen.",
        "category": TipCategory.SHORTCUT,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["documents", "dashboard"],
        "shortcut": "Ctrl+U",
        "experience_level": UserExperience.BEGINNER,
    },
    {
        "id": "tip_shortcut_navigation",
        "title": "Schnelle Navigation",
        "content": "Nutzen Sie Pfeiltasten + Enter, um durch Dokumente zu navigieren. "
                   "J/K bewegen Sie nach unten/oben.",
        "category": TipCategory.SHORTCUT,
        "priority": TipPriority.LOW,
        "context_pages": ["documents", "inbox", "validation"],
        "shortcut": "J/K",
        "experience_level": UserExperience.INTERMEDIATE,
    },
    {
        "id": "tip_shortcut_approve",
        "title": "Schnelles Genehmigen",
        "content": "In der Validierungsansicht: A für Genehmigen, R für Ablehnen. "
                   "Das spart viele Klicks!",
        "category": TipCategory.SHORTCUT,
        "priority": TipPriority.HIGH,
        "context_pages": ["validation"],
        "shortcut": "A/R",
        "experience_level": UserExperience.BEGINNER,
    },
    # Automation
    {
        "id": "tip_auto_tagging",
        "title": "Automatische Tags",
        "content": "Wussten Sie, dass das System automatisch Tags basierend auf dem "
                   "Dokumentinhalt vorschlägt? Aktivieren Sie dies in den Einstellungen.",
        "category": TipCategory.AUTOMATION,
        "priority": TipPriority.HIGH,
        "context_pages": ["documents", "settings", "tags"],
        "action_url": "/settings/ocr",
        "action_label": "Einstellungen öffnen",
        "experience_level": UserExperience.BEGINNER,
    },
    {
        "id": "tip_auto_workflow",
        "title": "Workflow-Automatisierung",
        "content": "Erstellen Sie Regeln, um Dokumente automatisch zu genehmigen, "
                   "weiterzuleiten oder zu taggen. Unter Admin -> Workflows.",
        "category": TipCategory.AUTOMATION,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["admin", "workflows"],
        "action_url": "/admin/workflows",
        "action_label": "Workflows erstellen",
        "experience_level": UserExperience.INTERMEDIATE,
    },
    {
        "id": "tip_email_import",
        "title": "Email-Import aktivieren",
        "content": "Rechnungen per Email empfangen? Richten Sie den automatischen "
                   "Email-Import ein und sparen Sie manuelle Uploads.",
        "category": TipCategory.AUTOMATION,
        "priority": TipPriority.HIGH,
        "context_pages": ["settings", "imports", "admin"],
        "action_url": "/admin/imports/email",
        "action_label": "Email-Import einrichten",
        "experience_level": UserExperience.INTERMEDIATE,
    },
    {
        "id": "tip_folder_watch",
        "title": "Ordner-Überwachung",
        "content": "Lassen Sie Dokumente automatisch aus einem Ordner importieren. "
                   "Ideal für Scanner-Ausgabe-Ordner!",
        "category": TipCategory.AUTOMATION,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["settings", "imports"],
        "action_url": "/admin/imports/folder",
        "action_label": "Ordner-Import einrichten",
        "experience_level": UserExperience.INTERMEDIATE,
    },
    # Optimization
    {
        "id": "tip_ocr_template",
        "title": "OCR-Templates erstellen",
        "content": "Für wiederkehrende Lieferanten: Erstellen Sie ein OCR-Template "
                   "und erreichen Sie 99%+ Genauigkeit statt 95%.",
        "category": TipCategory.OPTIMIZATION,
        "priority": TipPriority.HIGH,
        "context_pages": ["documents", "ocr", "entities"],
        "action_url": "/admin/ocr/templates",
        "action_label": "Templates verwalten",
        "experience_level": UserExperience.ADVANCED,
    },
    {
        "id": "tip_batch_processing",
        "title": "Stapelverarbeitung",
        "content": "Verarbeiten Sie mehrere Dokumente gleichzeitig! Wählen Sie "
                   "mehrere Dateien beim Upload aus.",
        "category": TipCategory.OPTIMIZATION,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["documents", "upload"],
        "experience_level": UserExperience.BEGINNER,
    },
    {
        "id": "tip_skonto_alerts",
        "title": "Skonto-Erinnerungen",
        "content": "Verpassen Sie keine Skonto-Fristen mehr! Das System warnt Sie "
                   "automatisch vor ablaufenden Skonti.",
        "category": TipCategory.OPTIMIZATION,
        "priority": TipPriority.HIGH,
        "context_pages": ["invoices", "banking", "dashboard"],
        "action_url": "/banking/skonto",
        "action_label": "Skonto-Übersicht",
        "experience_level": UserExperience.BEGINNER,
    },
    # Features
    {
        "id": "tip_feature_search_syntax",
        "title": "Erweiterte Suchsyntax",
        "content": "Nutzen Sie Suchoperatoren: 'betrag:>1000', 'datum:2024-01', "
                   "'lieferant:Mueller' für praezise Ergebnisse.",
        "category": TipCategory.FEATURE,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["documents", "search"],
        "experience_level": UserExperience.INTERMEDIATE,
    },
    {
        "id": "tip_feature_communication_hub",
        "title": "360-Grad Kundensicht",
        "content": "Im Kommunikations-Hub sehen Sie alle Interaktionen mit einem "
                   "Geschäftspartner: Emails, Rechnungen, Mahnungen, Notizen.",
        "category": TipCategory.FEATURE,
        "priority": TipPriority.HIGH,
        "context_pages": ["entities", "customers", "suppliers"],
        "action_url": "/entities",
        "action_label": "Geschäftspartner öffnen",
        "experience_level": UserExperience.BEGINNER,
    },
    {
        "id": "tip_feature_risk_score",
        "title": "Risiko-Score verstehen",
        "content": "Jeder Geschäftspartner hat einen Risiko-Score (0-100). "
                   "Hohe Werte bedeuten erhöhtes Ausfallrisiko.",
        "category": TipCategory.FEATURE,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["entities", "risk", "invoices"],
        "experience_level": UserExperience.INTERMEDIATE,
    },
    {
        "id": "tip_feature_document_chains",
        "title": "Dokumenten-Ketten",
        "content": "Verknüpfen Sie Angebot -> Auftrag -> Lieferschein -> Rechnung "
                   "für lückenlose Nachverfolgung.",
        "category": TipCategory.FEATURE,
        "priority": TipPriority.MEDIUM,
        "context_pages": ["documents", "chains"],
        "action_url": "/document-chains",
        "action_label": "Ketten anzeigen",
        "experience_level": UserExperience.INTERMEDIATE,
    },
    # Best Practices
    {
        "id": "tip_bp_regular_backup",
        "title": "Regelmäßige Exports",
        "content": "Exportieren Sie regelmäßig wichtige Daten für Ihr Backup. "
                   "Nutzen Sie den Steuerberater-Export monatlich.",
        "category": TipCategory.BEST_PRACTICE,
        "priority": TipPriority.LOW,
        "context_pages": ["admin", "exports", "settings"],
        "experience_level": UserExperience.INTERMEDIATE,
    },
    {
        "id": "tip_bp_entity_cleanup",
        "title": "Dubletten-Prüfung",
        "content": "Prüfen Sie regelmäßig auf doppelte Geschäftspartner. "
                   "Das verbessert Ihre Datenqualität und Reports.",
        "category": TipCategory.BEST_PRACTICE,
        "priority": TipPriority.LOW,
        "context_pages": ["entities", "admin"],
        "experience_level": UserExperience.ADVANCED,
    },
    # Warnings
    {
        "id": "tip_warn_incomplete_profile",
        "title": "Firmenprofil vervollständigen",
        "content": "Ihr Firmenprofil ist unvollständig. Für korrekte Mahnungen "
                   "und Exporte sollten alle Angaben gepflegt sein.",
        "category": TipCategory.WARNING,
        "priority": TipPriority.HIGH,
        "context_pages": ["settings", "admin", "company"],
        "action_url": "/settings/company",
        "action_label": "Profil vervollständigen",
        "experience_level": UserExperience.BEGINNER,
    },
]


class AIMentorService:
    """Service für proaktive Hilfe und personalisierte Tipps.

    Analysiert Benutzerverhalten und gibt kontextuelle Empfehlungen:
    - Shortcuts für häufige Aktionen
    - Automatisierungsmöglichkeiten
    - Feature-Entdeckung
    - Best Practices
    """

    # Pattern Detection Thresholds
    REPETITIVE_ACTION_THRESHOLD = 5  # Gleiche Aktion X mal = Pattern
    PATTERN_ANALYSIS_DAYS = 7  # Letzte X Tage analysieren
    MIN_ACTIONS_FOR_PATTERN = 10  # Mindestaktionen für Analyse

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._tip_index: Dict[str, Tip] = {}
        self._build_tip_index()

    def _build_tip_index(self) -> None:
        """Baut den Tipp-Index auf."""
        for tip_data in TIP_LIBRARY:
            tip = Tip(
                id=tip_data["id"],
                title=tip_data["title"],
                content=tip_data["content"],
                category=tip_data["category"],
                priority=tip_data["priority"],
                context_pages=tip_data.get("context_pages", []),
                action_url=tip_data.get("action_url"),
                action_label=tip_data.get("action_label"),
                shortcut=tip_data.get("shortcut"),
                experience_level=tip_data.get("experience_level", UserExperience.BEGINNER),
            )
            self._tip_index[tip.id] = tip

    async def get_contextual_tips(
        self,
        user_id: uuid.UUID,
        context_page: str,
        preferences: Optional[MentorPreferences] = None,
        max_tips: int = 3,
    ) -> List[Tip]:
        """Holt kontextuelle Tipps für die aktuelle Seite.

        Args:
            user_id: Benutzer-ID
            context_page: Aktuelle Seite (z.B. "documents", "validation")
            preferences: Benutzer-Praeferenzen
            max_tips: Maximale Anzahl Tipps

        Returns:
            Liste von relevanten Tipps
        """
        if preferences and not preferences.enabled:
            return []

        dismissed_tips = preferences.dismissed_tips if preferences else set()
        experience_level = preferences.experience_level if preferences else UserExperience.BEGINNER

        # Alle passenden Tipps sammeln
        matching_tips: List[Tip] = []

        for tip in self._tip_index.values():
            # Skip dismissed
            if tip.id in dismissed_tips:
                continue

            # Context check
            if not self._matches_context(tip, context_page):
                continue

            # Experience level check
            if not self._matches_experience(tip, experience_level):
                continue

            # Category filter
            if preferences:
                if tip.category == TipCategory.SHORTCUT and not preferences.show_shortcuts:
                    continue
                if tip.category == TipCategory.AUTOMATION and not preferences.show_automation_tips:
                    continue
                if tip.category == TipCategory.PATTERN and not preferences.show_pattern_insights:
                    continue

            matching_tips.append(tip)

        # Nach Priorität sortieren
        priority_order = {
            TipPriority.HIGH: 0,
            TipPriority.MEDIUM: 1,
            TipPriority.LOW: 2,
        }
        matching_tips.sort(key=lambda t: priority_order.get(t.priority, 99))

        logger.debug(
            "contextual_tips_fetched",
            user_id=str(user_id),
            context_page=context_page,
            matching_count=len(matching_tips),
            returned_count=min(len(matching_tips), max_tips),
        )

        return matching_tips[:max_tips]

    def _matches_context(self, tip: Tip, context_page: str) -> bool:
        """Prüft ob Tipp zum Kontext passt."""
        if not tip.context_pages:
            return True  # Universeller Tipp

        # Normalize context
        context_normalized = context_page.lower().strip("/")

        for ctx in tip.context_pages:
            if ctx.lower() in context_normalized or context_normalized in ctx.lower():
                return True

        return False

    def _matches_experience(self, tip: Tip, user_level: UserExperience) -> bool:
        """Prüft ob Tipp zur Erfahrungsstufe passt.

        Fortgeschrittene sehen alle Tipps.
        Anfaenger sehen nur Anfaenger-Tipps.
        """
        level_order = {
            UserExperience.BEGINNER: 0,
            UserExperience.INTERMEDIATE: 1,
            UserExperience.ADVANCED: 2,
        }

        tip_level = level_order.get(tip.experience_level, 0)
        user_level_num = level_order.get(user_level, 0)

        # User sieht Tipps bis einschliesslich seines Levels
        return tip_level <= user_level_num

    async def analyze_behavior_patterns(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        days: int = 7,
    ) -> List[BehaviorPattern]:
        """Analysiert Verhaltensmuster des Benutzers.

        Args:
            user_id: Benutzer-ID
            company_id: Firmen-ID
            days: Analyse-Zeitraum in Tagen

        Returns:
            Liste erkannter Muster
        """
        patterns: List[BehaviorPattern] = []

        cutoff_date = utc_now() - timedelta(days=days)

        # Aktionen gruppiert nach Typ und Seite zaehlen
        stmt = (
            select(
                UserBehaviorLog.action,
                UserBehaviorLog.context_page,
                func.count(UserBehaviorLog.id).label("count"),
                func.max(UserBehaviorLog.created_at).label("last_at"),
                func.avg(UserBehaviorLog.time_spent_ms).label("avg_time"),
            )
            .where(
                and_(
                    UserBehaviorLog.user_id == user_id,
                    UserBehaviorLog.company_id == company_id,
                    UserBehaviorLog.created_at >= cutoff_date,
                )
            )
            .group_by(UserBehaviorLog.action, UserBehaviorLog.context_page)
            .having(func.count(UserBehaviorLog.id) >= self.REPETITIVE_ACTION_THRESHOLD)
            .order_by(desc("count"))
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        for row in rows:
            action, context_page, count, last_at, avg_time = row

            # Pattern-spezifische Empfehlungen
            pattern = self._create_pattern_from_behavior(
                action=action,
                context_page=context_page or "unknown",
                frequency=count,
                last_at=last_at,
                avg_time_ms=avg_time or 0,
            )

            if pattern:
                patterns.append(pattern)

        logger.info(
            "behavior_patterns_analyzed",
            user_id=str(user_id),
            days=days,
            patterns_found=len(patterns),
        )

        return patterns

    def _create_pattern_from_behavior(
        self,
        action: str,
        context_page: str,
        frequency: int,
        last_at: datetime,
        avg_time_ms: float,
    ) -> Optional[BehaviorPattern]:
        """Erstellt ein Pattern aus Verhaltensdaten."""
        # Pattern-Erkennung Regeln
        if action == "viewed" and frequency >= 10:
            return BehaviorPattern(
                id=f"pattern_frequent_view_{context_page}",
                pattern_type="frequent_view",
                description=f"Sie besuchen '{context_page}' häufig ({frequency}x)",
                frequency=frequency,
                last_occurrence=last_at,
                recommendation="Erwaegen Sie, diese Seite als Startseite festzulegen.",
                potential_savings_minutes=2,
            )

        if action == "clicked" and "upload" in context_page.lower() and frequency >= 5:
            return BehaviorPattern(
                id="pattern_frequent_upload",
                pattern_type="frequent_upload",
                description=f"Sie laden häufig Dokumente hoch ({frequency}x)",
                frequency=frequency,
                last_occurrence=last_at,
                recommendation="Nutzen Sie den Ordner-Import für automatische Uploads.",
                potential_savings_minutes=frequency * 2,
            )

        if action == "completed" and avg_time_ms > 30000:  # > 30 Sekunden
            return BehaviorPattern(
                id=f"pattern_slow_completion_{context_page}",
                pattern_type="slow_completion",
                description=f"Aktionen auf '{context_page}' dauern durchschnittlich "
                           f"{int(avg_time_ms / 1000)} Sekunden",
                frequency=frequency,
                last_occurrence=last_at,
                recommendation="Nutzen Sie Keyboard-Shortcuts für schnellere Bearbeitung.",
                potential_savings_minutes=int((avg_time_ms / 1000) * frequency / 60),
            )

        return None

    async def generate_personalized_tip(
        self,
        user_id: uuid.UUID,
        pattern: BehaviorPattern,
    ) -> Optional[Tip]:
        """Generiert einen personalisierten Tipp basierend auf Pattern.

        Args:
            user_id: Benutzer-ID
            pattern: Erkanntes Verhaltensmuster

        Returns:
            Personalisierter Tipp oder None
        """
        # Pattern-spezifische Tipps generieren
        if pattern.pattern_type == "frequent_upload":
            return Tip(
                id=f"tip_dynamic_{pattern.id}",
                title="Automatischer Import möglich",
                content=f"Sie haben {pattern.frequency}x manuell Dokumente hochgeladen. "
                       f"Mit dem Ordner-Import könnten Sie etwa {pattern.potential_savings_minutes} "
                       f"Minuten pro Woche sparen.",
                category=TipCategory.AUTOMATION,
                priority=TipPriority.HIGH,
                action_url="/admin/imports/folder",
                action_label="Ordner-Import einrichten",
                metadata={"pattern_id": pattern.id, "personalized": True},
            )

        if pattern.pattern_type == "slow_completion":
            return Tip(
                id=f"tip_dynamic_{pattern.id}",
                title="Schneller arbeiten mit Shortcuts",
                content=f"Ihre durchschnittliche Bearbeitungszeit betraegt "
                       f"{int(pattern.potential_savings_minutes / pattern.frequency * 60)} Sekunden. "
                       f"Mit Shortcuts könnten Sie schneller werden.",
                category=TipCategory.SHORTCUT,
                priority=TipPriority.MEDIUM,
                action_url="/help/shortcuts",
                action_label="Shortcuts anzeigen",
                metadata={"pattern_id": pattern.id, "personalized": True},
            )

        return None

    async def dismiss_tip(
        self,
        user_id: uuid.UUID,
        tip_id: str,
    ) -> bool:
        """Markiert einen Tipp als verworfen.

        Args:
            user_id: Benutzer-ID
            tip_id: Tipp-ID

        Returns:
            True wenn erfolgreich
        """
        # Validiere tip_id Format
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]{2,63}$', tip_id):
            logger.warning("invalid_tip_id", tip_id=tip_id)
            return False

        # In User.preferences speichern
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Preferences aktualisieren
        preferences = user.preferences or {}
        mentor_prefs = preferences.get("mentor", {})
        dismissed = set(mentor_prefs.get("dismissed_tips", []))
        dismissed.add(tip_id)
        mentor_prefs["dismissed_tips"] = list(dismissed)
        preferences["mentor"] = mentor_prefs
        user.preferences = preferences

        await self.db.commit()

        logger.info(
            "tip_dismissed",
            user_id=str(user_id),
            tip_id=tip_id,
        )

        return True

    async def get_tip_history(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> List[str]:
        """Holt die Liste der verworfenen Tipps.

        Args:
            user_id: Benutzer-ID
            limit: Maximale Anzahl

        Returns:
            Liste von Tipp-IDs
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not user.preferences:
            return []

        mentor_prefs = user.preferences.get("mentor", {})
        dismissed = mentor_prefs.get("dismissed_tips", [])

        return dismissed[:limit]

    async def get_mentor_preferences(
        self,
        user_id: uuid.UUID,
    ) -> MentorPreferences:
        """Holt die Mentor-Praeferenzen des Benutzers.

        Args:
            user_id: Benutzer-ID

        Returns:
            MentorPreferences
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not user.preferences:
            return MentorPreferences()

        mentor_prefs = user.preferences.get("mentor", {})

        return MentorPreferences(
            enabled=mentor_prefs.get("enabled", True),
            show_shortcuts=mentor_prefs.get("show_shortcuts", True),
            show_automation_tips=mentor_prefs.get("show_automation_tips", True),
            show_pattern_insights=mentor_prefs.get("show_pattern_insights", True),
            experience_level=UserExperience(
                mentor_prefs.get("experience_level", "beginner")
            ),
            dismissed_tips=set(mentor_prefs.get("dismissed_tips", [])),
            max_tips_per_session=mentor_prefs.get("max_tips_per_session", 5),
            tip_frequency_hours=mentor_prefs.get("tip_frequency_hours", 24),
        )

    async def update_mentor_preferences(
        self,
        user_id: uuid.UUID,
        updates: Dict[str, Any],
    ) -> MentorPreferences:
        """Aktualisiert die Mentor-Praeferenzen.

        Args:
            user_id: Benutzer-ID
            updates: Zu aktualisierende Felder

        Returns:
            Aktualisierte MentorPreferences
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError("Benutzer nicht gefunden")

        preferences = user.preferences or {}
        mentor_prefs = preferences.get("mentor", {})

        # Nur erlaubte Felder aktualisieren
        allowed_fields = {
            "enabled", "show_shortcuts", "show_automation_tips",
            "show_pattern_insights", "experience_level",
            "max_tips_per_session", "tip_frequency_hours"
        }

        for key, value in updates.items():
            if key in allowed_fields:
                mentor_prefs[key] = value

        preferences["mentor"] = mentor_prefs
        user.preferences = preferences

        await self.db.commit()

        logger.info(
            "mentor_preferences_updated",
            user_id=str(user_id),
            updates=list(updates.keys()),
        )

        return await self.get_mentor_preferences(user_id)

    async def get_all_tips(self) -> List[Tip]:
        """Holt alle verfügbaren Tipps.

        Returns:
            Liste aller Tipps
        """
        return list(self._tip_index.values())

    async def get_tip_by_id(self, tip_id: str) -> Optional[Tip]:
        """Holt einen Tipp nach ID.

        Args:
            tip_id: Tipp-ID

        Returns:
            Tip oder None
        """
        return self._tip_index.get(tip_id)


# ============================================================================
# Factory Function
# ============================================================================


async def get_mentor_service(db: AsyncSession) -> AIMentorService:
    """Factory-Funktion für AIMentorService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter AIMentorService
    """
    return AIMentorService(db=db)
