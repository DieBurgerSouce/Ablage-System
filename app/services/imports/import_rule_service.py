"""Import Rule Service.

Implementiert eine flexible Rule Engine für Import-Automatisierung:
- Bedingungsbasierte Regeln (AND/OR Logik)
- Aktionen (Ordner-Zuweisung, Tags, OCR-Priorität, Benachrichtigungen)
- Prioritätsbasierte Regelauswertung
- Test-Modus für Regel-Validierung

Feinpoliert und durchdacht - Enterprise-grade Import Rules.
"""

import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_regex import safe_search

logger = structlog.get_logger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Unterstützte Bedingungsfelder
CONDITION_FIELDS = {
    # Email-spezifisch
    "sender_email": "E-Mail-Absender",
    "sender_name": "Absender-Name",
    "subject": "Betreff",
    "email_date": "E-Mail-Datum",

    # Datei-spezifisch
    "filename": "Dateiname",
    "file_extension": "Dateiendung",
    "file_size": "Dateigröße (Bytes)",
    "mime_type": "MIME-Type",

    # Ordner-spezifisch (für Folder-Import)
    "source_path": "Quellpfad",
    "parent_folder": "Überordner",
}

# Unterstützte Operatoren
OPERATORS = {
    "equals": "ist gleich",
    "not_equals": "ist nicht gleich",
    "contains": "enthält",
    "not_contains": "enthält nicht",
    "starts_with": "beginnt mit",
    "ends_with": "endet mit",
    "regex": "entspricht RegEx",
    "gt": "größer als",
    "gte": "größer oder gleich",
    "lt": "kleiner als",
    "lte": "kleiner oder gleich",
    "in_list": "in Liste",
    "not_in_list": "nicht in Liste",
    "is_empty": "ist leer",
    "is_not_empty": "ist nicht leer",
}

# Unterstützte Aktionen
ACTIONS = {
    "assign_folder_id": "In Ordner verschieben",
    "assign_tags": "Tags zuweisen",
    "assign_document_type": "Dokumenttyp setzen",
    "skip_ocr": "OCR überspringen",
    "priority_ocr": "Prioritäts-OCR",
    "notify_users": "Benutzer benachrichtigen",
    "set_status": "Status setzen",
    "add_metadata": "Metadaten hinzufuegen",
}


# ============================================================================
# Data Classes
# ============================================================================

class RuleCondition:
    """Repraesentiert eine einzelne Regel-Bedingung."""

    def __init__(
        self,
        field: str,
        operator: str,
        value: Optional[str] = None,
    ):
        self.field = field
        self.operator = operator
        self.value = value

    def to_dict(self) -> Dict:
        """Konvertiert zu Dictionary."""
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "RuleCondition":
        """Erstellt aus Dictionary."""
        return cls(
            field=data.get("field", ""),
            operator=data.get("operator", "equals"),
            value=data.get("value"),
        )


class RuleMatch:
    """Ergebnis einer Regel-Auswertung."""

    def __init__(
        self,
        rule_id: UUID,
        rule_name: str,
        priority: int,
        actions: Dict,
        matched_conditions: List[str],
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.priority = priority
        self.actions = actions
        self.matched_conditions = matched_conditions


# ============================================================================
# Import Rule Service
# ============================================================================

class ImportRuleService:
    """Service für Import-Regel-Verwaltung und -Auswertung.

    Features:
    - CRUD für Import-Regeln
    - Flexible Bedingungen (AND/OR Logik)
    - Prioritätsbasierte Auswertung
    - Test-Modus für Validierung
    - Statistik-Tracking (Match-Count)
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Import Rule Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    # ========================================================================
    # Rule Evaluation
    # ========================================================================

    async def evaluate_rules(
        self,
        user_id: UUID,
        metadata: Dict,
        source_type: str = "email",
        config_id: Optional[UUID] = None,
    ) -> List[RuleMatch]:
        """Wertet alle zutreffenden Regeln für gegebene Metadaten aus.

        Args:
            user_id: User-ID
            metadata: Metadaten des zu importierenden Elements
            source_type: Quelle ("email" oder "folder")
            config_id: Optional spezifische Config-ID

        Returns:
            Liste von RuleMatch-Objekten, sortiert nach Priorität
        """
        from app.db.models import ImportRule

        # Aktive Regeln laden
        query = select(ImportRule).where(
            and_(
                ImportRule.user_id == user_id,
                ImportRule.is_active == True,
            )
        )
        query = query.order_by(ImportRule.priority.asc())

        result = await self.db.execute(query)
        rules = result.scalars().all()

        matches = []

        for rule in rules:
            # Prüfen ob Regel auf diese Quelle anwendbar ist
            if not self._rule_applies_to_source(rule, source_type, config_id):
                continue

            # Bedingungen auswerten
            match_result = self._evaluate_conditions(
                rule.conditions,
                metadata,
            )

            if match_result["matched"]:
                matches.append(RuleMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    priority=rule.priority,
                    actions=rule.actions or {},
                    matched_conditions=match_result["matched_conditions"],
                ))

                # Match-Count aktualisieren
                await self._increment_match_count(rule.id)

        logger.info(
            "rules_evaluated",
            user_id=str(user_id),
            rules_checked=len(rules),
            matches_found=len(matches),
        )

        return matches

    def _rule_applies_to_source(
        self,
        rule,
        source_type: str,
        config_id: Optional[UUID],
    ) -> bool:
        """Prüft ob Regel auf diese Quelle anwendbar ist."""
        # Wenn "applies_to_all" gesetzt ist
        if rule.applies_to_all:
            return True

        # Email-Configs prüfen
        if source_type == "email" and rule.applies_to_email_configs:
            if config_id and str(config_id) in [
                str(c) for c in rule.applies_to_email_configs
            ]:
                return True
            # Wenn keine config_id aber Regel hat Email-Configs: False
            if config_id is None and rule.applies_to_email_configs:
                return False

        # Folder-Configs prüfen
        if source_type == "folder" and rule.applies_to_folder_configs:
            if config_id and str(config_id) in [
                str(c) for c in rule.applies_to_folder_configs
            ]:
                return True
            if config_id is None and rule.applies_to_folder_configs:
                return False

        # Keine spezifischen Configs definiert = auf alles anwendbar
        if not rule.applies_to_email_configs and not rule.applies_to_folder_configs:
            return True

        return False

    def _evaluate_conditions(
        self,
        conditions: Dict,
        metadata: Dict,
    ) -> Dict:
        """Wertet Bedingungen gegen Metadaten aus.

        Args:
            conditions: Bedingungs-Struktur
            metadata: Metadaten

        Returns:
            Dict mit "matched" (bool) und "matched_conditions" (List)
        """
        if not conditions or "rules" not in conditions:
            # Keine Bedingungen = immer Match
            return {"matched": True, "matched_conditions": []}

        operator = conditions.get("operator", "AND")
        rules = conditions.get("rules", [])
        matched_conditions = []

        results = []
        for rule in rules:
            field = rule.get("field", "")
            op = rule.get("operator", "equals")
            value = rule.get("value")

            # Verschachtelte Gruppe?
            if "rules" in rule:
                nested_result = self._evaluate_conditions(rule, metadata)
                results.append(nested_result["matched"])
                if nested_result["matched"]:
                    matched_conditions.extend(nested_result["matched_conditions"])
            else:
                # Einzelne Bedingung
                matched = self._evaluate_single_condition(
                    field=field,
                    operator=op,
                    expected_value=value,
                    actual_value=metadata.get(field),
                )
                results.append(matched)
                if matched:
                    matched_conditions.append(
                        f"{field} {op} {value}"
                    )

        if not results:
            return {"matched": True, "matched_conditions": []}

        if operator == "AND":
            matched = all(results)
        elif operator == "OR":
            matched = any(results)
        else:
            matched = all(results)

        return {
            "matched": matched,
            "matched_conditions": matched_conditions if matched else [],
        }

    def _evaluate_single_condition(
        self,
        field: str,
        operator: str,
        expected_value: Optional[str],
        actual_value,
    ) -> bool:
        """Wertet eine einzelne Bedingung aus.

        Args:
            field: Feldname
            operator: Operator
            expected_value: Erwarteter Wert
            actual_value: Tatsaechlicher Wert aus Metadaten

        Returns:
            True wenn Bedingung erfuellt
        """
        # is_empty / is_not_empty - brauchen keinen expected_value
        if operator == "is_empty":
            return not actual_value or str(actual_value).strip() == ""
        if operator == "is_not_empty":
            return actual_value and str(actual_value).strip() != ""

        # Wenn actual_value None ist, kann nichts matchen
        if actual_value is None:
            return False

        # String-Vergleiche
        actual_str = str(actual_value).lower() if actual_value else ""
        expected_str = str(expected_value).lower() if expected_value else ""

        if operator == "equals":
            return actual_str == expected_str
        elif operator == "not_equals":
            return actual_str != expected_str
        elif operator == "contains":
            return expected_str in actual_str
        elif operator == "not_contains":
            return expected_str not in actual_str
        elif operator == "starts_with":
            return actual_str.startswith(expected_str)
        elif operator == "ends_with":
            return actual_str.endswith(expected_str)
        elif operator == "regex":
            try:
                return bool(safe_search(expected_value or "", str(actual_value), re.IGNORECASE))
            except re.error:
                logger.warning(
                    "invalid_regex_pattern",
                    pattern=expected_value,
                )
                return False

        # Numerische Vergleiche
        elif operator in ("gt", "gte", "lt", "lte"):
            try:
                actual_num = float(actual_value)
                expected_num = float(expected_value)

                if operator == "gt":
                    return actual_num > expected_num
                elif operator == "gte":
                    return actual_num >= expected_num
                elif operator == "lt":
                    return actual_num < expected_num
                elif operator == "lte":
                    return actual_num <= expected_num
            except (ValueError, TypeError):
                return False

        # Listen-Vergleiche
        elif operator == "in_list":
            expected_list = [
                s.strip().lower()
                for s in str(expected_value).split(",")
            ]
            return actual_str in expected_list
        elif operator == "not_in_list":
            expected_list = [
                s.strip().lower()
                for s in str(expected_value).split(",")
            ]
            return actual_str not in expected_list

        return False

    # ========================================================================
    # Apply Actions
    # ========================================================================

    def apply_actions(
        self,
        matches: List[RuleMatch],
    ) -> Dict:
        """Konsolidiert Aktionen aus allen Matches.

        Bei Konflikten gewinnt die Regel mit höherer Priorität
        (niedrigerer Prioritäts-Wert).

        Args:
            matches: Liste von RuleMatch-Objekten

        Returns:
            Konsolidiertes Actions-Dict
        """
        if not matches:
            return {}

        # Nach Priorität sortieren (niedrigster Wert = hoechste Priorität)
        sorted_matches = sorted(matches, key=lambda m: m.priority)

        # Aktionen konsolidieren
        consolidated = {}

        for match in sorted_matches:
            for action_key, action_value in match.actions.items():
                # Erste Regel (hoechste Priorität) gewinnt bei Konflikten
                if action_key not in consolidated:
                    consolidated[action_key] = action_value
                elif action_key in ("assign_tags", "notify_users"):
                    # Listen werden gemerged
                    if isinstance(consolidated[action_key], list):
                        existing = set(consolidated[action_key])
                        if isinstance(action_value, list):
                            existing.update(action_value)
                        consolidated[action_key] = list(existing)

        logger.debug(
            "actions_consolidated",
            rule_count=len(matches),
            actions=list(consolidated.keys()),
        )

        return consolidated

    # ========================================================================
    # Test Mode
    # ========================================================================

    async def test_rule(
        self,
        rule_id: UUID,
        user_id: UUID,
        test_metadata: Dict,
    ) -> Dict:
        """Testet eine Regel gegen Test-Metadaten.

        Args:
            rule_id: Regel-ID
            user_id: User-ID
            test_metadata: Test-Metadaten

        Returns:
            Dict mit Test-Ergebnis
        """
        from app.db.models import ImportRule

        # Regel laden
        rule = await self._get_rule(rule_id, user_id)
        if not rule:
            return {
                "success": False,
                "error": "Regel nicht gefunden",
            }

        # Bedingungen auswerten
        result = self._evaluate_conditions(rule.conditions, test_metadata)

        return {
            "success": True,
            "rule_name": rule.name,
            "matched": result["matched"],
            "matched_conditions": result["matched_conditions"],
            "would_apply_actions": rule.actions if result["matched"] else {},
            "test_metadata": test_metadata,
        }

    async def test_all_rules(
        self,
        user_id: UUID,
        test_metadata: Dict,
        source_type: str = "email",
    ) -> Dict:
        """Testet alle Regeln gegen Test-Metadaten.

        Args:
            user_id: User-ID
            test_metadata: Test-Metadaten
            source_type: Quelle

        Returns:
            Dict mit Test-Ergebnissen
        """
        matches = await self.evaluate_rules(
            user_id=user_id,
            metadata=test_metadata,
            source_type=source_type,
        )

        consolidated_actions = self.apply_actions(matches)

        return {
            "success": True,
            "rules_matched": len(matches),
            "matches": [
                {
                    "rule_id": str(m.rule_id),
                    "rule_name": m.rule_name,
                    "priority": m.priority,
                    "matched_conditions": m.matched_conditions,
                    "actions": m.actions,
                }
                for m in matches
            ],
            "consolidated_actions": consolidated_actions,
            "test_metadata": test_metadata,
        }

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    async def create_rule(
        self,
        user_id: UUID,
        name: str,
        conditions: Dict,
        actions: Dict,
        priority: int = 100,
        description: Optional[str] = None,
        applies_to_email_configs: Optional[List[UUID]] = None,
        applies_to_folder_configs: Optional[List[UUID]] = None,
        applies_to_all: bool = False,
        is_active: bool = True,
    ) -> UUID:
        """Erstellt eine neue Import-Regel.

        Args:
            user_id: User-ID
            name: Regel-Name
            conditions: Bedingungs-Struktur
            actions: Aktions-Struktur
            priority: Priorität (niedriger = höher)
            description: Beschreibung
            applies_to_email_configs: Email-Config-IDs
            applies_to_folder_configs: Folder-Config-IDs
            applies_to_all: Auf alle anwenden
            is_active: Aktiv

        Returns:
            Regel-ID
        """
        from app.db.models import ImportRule

        # Validierung
        if not self._validate_conditions(conditions):
            raise ValueError("Ungültige Bedingungs-Struktur")

        if not self._validate_actions(actions):
            raise ValueError("Ungültige Aktions-Struktur")

        rule_id = uuid4()

        rule = ImportRule(
            id=rule_id,
            user_id=user_id,
            name=name,
            description=description,
            priority=priority,
            applies_to_email_configs=[str(c) for c in applies_to_email_configs] if applies_to_email_configs else [],
            applies_to_folder_configs=[str(c) for c in applies_to_folder_configs] if applies_to_folder_configs else [],
            applies_to_all=applies_to_all,
            conditions=conditions,
            actions=actions,
            is_active=is_active,
        )

        self.db.add(rule)
        await self.db.commit()

        logger.info(
            "import_rule_created",
            rule_id=str(rule_id),
            user_id=str(user_id),
            name=name,
        )

        return rule_id

    async def update_rule(
        self,
        rule_id: UUID,
        user_id: UUID,
        **updates,
    ) -> bool:
        """Aktualisiert eine Import-Regel."""
        rule = await self._get_rule(rule_id, user_id)
        if not rule:
            return False

        # Validierung
        if "conditions" in updates:
            if not self._validate_conditions(updates["conditions"]):
                raise ValueError("Ungültige Bedingungs-Struktur")

        if "actions" in updates:
            if not self._validate_actions(updates["actions"]):
                raise ValueError("Ungültige Aktions-Struktur")

        # Config-IDs konvertieren
        if "applies_to_email_configs" in updates:
            updates["applies_to_email_configs"] = [
                str(c) for c in updates["applies_to_email_configs"]
            ]
        if "applies_to_folder_configs" in updates:
            updates["applies_to_folder_configs"] = [
                str(c) for c in updates["applies_to_folder_configs"]
            ]

        # Updates anwenden
        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        await self.db.commit()

        logger.info(
            "import_rule_updated",
            rule_id=str(rule_id),
            updated_fields=list(updates.keys()),
        )

        return True

    async def delete_rule(
        self,
        rule_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Löscht eine Import-Regel."""
        rule = await self._get_rule(rule_id, user_id)
        if not rule:
            return False

        await self.db.delete(rule)
        await self.db.commit()

        logger.info(
            "import_rule_deleted",
            rule_id=str(rule_id),
        )

        return True

    async def get_rule(
        self,
        rule_id: UUID,
        user_id: UUID,
    ) -> Optional[Dict]:
        """Holt eine Import-Regel."""
        rule = await self._get_rule(rule_id, user_id)
        if not rule:
            return None

        return {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "priority": rule.priority,
            "applies_to_email_configs": rule.applies_to_email_configs,
            "applies_to_folder_configs": rule.applies_to_folder_configs,
            "applies_to_all": rule.applies_to_all,
            "conditions": rule.conditions,
            "actions": rule.actions,
            "is_active": rule.is_active,
            "match_count": rule.match_count,
            "last_matched_at": rule.last_matched_at,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    async def list_rules(
        self,
        user_id: UUID,
        active_only: bool = False,
    ) -> List[Dict]:
        """Listet alle Import-Regeln eines Users."""
        from app.db.models import ImportRule

        query = select(ImportRule).where(
            ImportRule.user_id == user_id
        )

        if active_only:
            query = query.where(ImportRule.is_active == True)

        query = query.order_by(ImportRule.priority.asc())

        result = await self.db.execute(query)
        rules = result.scalars().all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "priority": r.priority,
                "is_active": r.is_active,
                "match_count": r.match_count,
                "last_matched_at": r.last_matched_at,
                "applies_to_all": r.applies_to_all,
            }
            for r in rules
        ]

    async def reorder_rules(
        self,
        user_id: UUID,
        rule_priorities: List[Tuple[UUID, int]],
    ) -> bool:
        """Ändert die Prioritäten mehrerer Regeln.

        Args:
            user_id: User-ID
            rule_priorities: Liste von (rule_id, new_priority) Tupeln

        Returns:
            True wenn erfolgreich
        """
        from app.db.models import ImportRule

        for rule_id, new_priority in rule_priorities:
            await self.db.execute(
                update(ImportRule)
                .where(
                    and_(
                        ImportRule.id == rule_id,
                        ImportRule.user_id == user_id,
                    )
                )
                .values(priority=new_priority)
            )

        await self.db.commit()

        logger.info(
            "import_rules_reordered",
            user_id=str(user_id),
            rule_count=len(rule_priorities),
        )

        return True

    # ========================================================================
    # Metadata Extraction
    # ========================================================================

    def extract_email_metadata(
        self,
        email_from: str,
        email_subject: str,
        email_date: Optional[datetime],
        attachment_filename: str,
        attachment_size: int,
        attachment_mime_type: str,
    ) -> Dict:
        """Extrahiert Metadaten aus Email-Informationen.

        Args:
            email_from: Absender
            email_subject: Betreff
            email_date: Datum
            attachment_filename: Dateiname des Anhangs
            attachment_size: Dateigröße
            attachment_mime_type: MIME-Type

        Returns:
            Metadaten-Dict für Regelauswertung
        """
        # Sender-Email und Name extrahieren
        sender_email = ""
        sender_name = ""
        if "<" in email_from and ">" in email_from:
            parts = email_from.split("<")
            sender_name = parts[0].strip().strip('"')
            sender_email = parts[1].rstrip(">").strip()
        else:
            sender_email = email_from.strip()

        # Dateiendung extrahieren
        extension = ""
        if "." in attachment_filename:
            extension = "." + attachment_filename.rsplit(".", 1)[-1].lower()

        return {
            "sender_email": sender_email,
            "sender_name": sender_name,
            "subject": email_subject,
            "email_date": email_date.isoformat() if email_date else None,
            "filename": attachment_filename,
            "file_extension": extension,
            "file_size": attachment_size,
            "mime_type": attachment_mime_type,
        }

    def extract_folder_metadata(
        self,
        file_path: str,
        filename: str,
        file_size: int,
        mime_type: str,
        modified_at: Optional[datetime] = None,
    ) -> Dict:
        """Extrahiert Metadaten aus Datei-Informationen.

        Args:
            file_path: Vollständiger Dateipfad
            filename: Dateiname
            file_size: Dateigröße
            mime_type: MIME-Type
            modified_at: Änderungsdatum

        Returns:
            Metadaten-Dict für Regelauswertung
        """
        import os

        # Dateiendung extrahieren
        extension = ""
        if "." in filename:
            extension = "." + filename.rsplit(".", 1)[-1].lower()

        # Parent-Ordner extrahieren
        parent_folder = os.path.basename(os.path.dirname(file_path))

        return {
            "source_path": file_path,
            "parent_folder": parent_folder,
            "filename": filename,
            "file_extension": extension,
            "file_size": file_size,
            "mime_type": mime_type,
        }

    # ========================================================================
    # Validation
    # ========================================================================

    def _validate_conditions(self, conditions: Dict) -> bool:
        """Validiert eine Bedingungs-Struktur."""
        if not conditions:
            return True  # Leere Bedingungen sind erlaubt

        if not isinstance(conditions, dict):
            return False

        operator = conditions.get("operator")
        if operator and operator not in ("AND", "OR"):
            return False

        rules = conditions.get("rules", [])
        if not isinstance(rules, list):
            return False

        for rule in rules:
            if not isinstance(rule, dict):
                return False

            # Verschachtelte Gruppe
            if "rules" in rule:
                if not self._validate_conditions(rule):
                    return False
            else:
                # Einzelne Bedingung
                field = rule.get("field")
                op = rule.get("operator")

                if not field or not op:
                    return False

                if field not in CONDITION_FIELDS:
                    logger.warning(
                        "unknown_condition_field",
                        field=field,
                    )
                    # Unbekannte Felder erlauben für Erweiterbarkeit

                if op not in OPERATORS:
                    return False

        return True

    def _validate_actions(self, actions: Dict) -> bool:
        """Validiert eine Aktions-Struktur."""
        if not actions:
            return True

        if not isinstance(actions, dict):
            return False

        for key, value in actions.items():
            if key not in ACTIONS:
                logger.warning(
                    "unknown_action_key",
                    key=key,
                )
                # Unbekannte Aktionen erlauben für Erweiterbarkeit

        return True

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_rule(self, rule_id: UUID, user_id: UUID):
        """Holt Regel mit Berechtigungsprüfung."""
        from app.db.models import ImportRule

        result = await self.db.execute(
            select(ImportRule).where(
                and_(
                    ImportRule.id == rule_id,
                    ImportRule.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _increment_match_count(self, rule_id: UUID) -> None:
        """Erhöht den Match-Counter einer Regel."""
        from app.db.models import ImportRule

        await self.db.execute(
            update(ImportRule)
            .where(ImportRule.id == rule_id)
            .values(
                match_count=ImportRule.match_count + 1,
                last_matched_at=datetime.now(timezone.utc),
            )
        )
        # Kein Commit - wird mit übergeordneter Transaktion committed

    # ========================================================================
    # Schema Helpers
    # ========================================================================

    @staticmethod
    def get_available_fields() -> Dict:
        """Gibt verfügbare Bedingungsfelder zurück."""
        return CONDITION_FIELDS.copy()

    @staticmethod
    def get_available_operators() -> Dict:
        """Gibt verfügbare Operatoren zurück."""
        return OPERATORS.copy()

    @staticmethod
    def get_available_actions() -> Dict:
        """Gibt verfügbare Aktionen zurück."""
        return ACTIONS.copy()
