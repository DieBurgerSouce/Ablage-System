"""ValidationSampleService - Stichproben-Auswahl und Regel-Verwaltung.

Dieser Service verwaltet die automatische und regelbasierte Auswahl
von Dokumenten fuer die Validierungswarteschlange.

Verwendung:
    from app.services.validation_sample_service import get_validation_sample_service

    service = get_validation_sample_service(db)
    should_validate = await service.should_sample_document(document_id)
"""
import uuid
import random
from datetime import datetime
from app.core.datetime_utils import utc_now
from typing import Optional, List, Dict, Any
import structlog

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ValidationSampleConfig,
    ValidationRule,
    ValidationQueueItem,
    Document,
    ValidationRuleType,
    SampleSource
)
from app.db.schemas import (
    ValidationRuleCreate,
    ValidationRuleUpdate,
    ValidationRuleResponse,
    ValidationSampleConfigUpdate,
    ValidationSampleConfigResponse,
    SampleSourceEnum,
    ValidationRuleTypeEnum,
)

logger = structlog.get_logger(__name__)


class ValidationSampleService:
    """Service fuer Stichproben-Auswahl und Regel-Verwaltung."""

    def __init__(self, db: AsyncSession):
        """Initialisiere den Service."""
        self.db = db

    # =========================================================================
    # SAMPLE CONFIG
    # =========================================================================

    async def get_sample_config(self) -> Optional[ValidationSampleConfig]:
        """Holt die aktive Stichproben-Konfiguration.

        Returns:
            Die aktive Konfiguration oder None
        """
        result = await self.db.execute(
            select(ValidationSampleConfig)
            .where(ValidationSampleConfig.is_active == True)
            .order_by(ValidationSampleConfig.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_sample_config(
        self,
        config_id: uuid.UUID,
        update_data: ValidationSampleConfigUpdate
    ) -> Optional[ValidationSampleConfig]:
        """Aktualisiert die Stichproben-Konfiguration.

        Args:
            config_id: ID der Konfiguration
            update_data: Zu aktualisierende Felder

        Returns:
            Die aktualisierte Konfiguration oder None
        """
        result = await self.db.execute(
            select(ValidationSampleConfig).where(ValidationSampleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(config, key, value)

        config.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(config)

        logger.info(
            "sample_config_updated",
            config_id=str(config_id),
            updated_fields=list(update_dict.keys())
        )

        return config

    # =========================================================================
    # SAMPLING LOGIC
    # =========================================================================

    async def should_sample_document(
        self,
        document: Document,
        force_check_rules: bool = True
    ) -> tuple[bool, Optional[str], Optional[uuid.UUID]]:
        """Prueft ob ein Dokument zur Validierung ausgewaehlt werden soll.

        Args:
            document: Das zu pruefende Dokument
            force_check_rules: Ob Regeln geprueft werden sollen

        Returns:
            Tuple aus (sollte_validiert_werden, sample_source, rule_id)
        """
        # 1. Regelbasierte Pruefung
        if force_check_rules:
            matched_rule = await self.evaluate_rules(document)
            if matched_rule:
                logger.info(
                    "document_matched_rule",
                    document_id=str(document.id),
                    rule_name=matched_rule.name
                )
                return (True, SampleSource.RULE_BASED.value, matched_rule.id)

        # 2. Low Confidence Check
        config = await self.get_sample_config()
        if config and document.ocr_confidence is not None:
            if document.ocr_confidence < config.min_confidence_threshold:
                logger.info(
                    "document_low_confidence",
                    document_id=str(document.id),
                    confidence=document.ocr_confidence,
                    threshold=config.min_confidence_threshold
                )
                return (True, SampleSource.LOW_CONFIDENCE.value, None)

        # 3. Prozent-basierte Stichprobe
        if config and config.sample_percentage > 0:
            # Deterministische Zufallsauswahl basierend auf Document-ID
            # So wird dasselbe Dokument immer gleich behandelt
            random.seed(str(document.id))
            roll = random.randint(1, 100)
            random.seed()  # Reset seed

            if roll <= config.sample_percentage:
                logger.debug(
                    "document_randomly_sampled",
                    document_id=str(document.id),
                    roll=roll,
                    threshold=config.sample_percentage
                )
                return (True, SampleSource.AUTOMATIC.value, None)

        return (False, None, None)

    async def apply_stratified_sampling(
        self,
        documents: List[Document],
        sample_percentage: Optional[int] = None
    ) -> List[Document]:
        """Wendet stratifizierte Stichprobenauswahl an.

        Waehlt Dokumente gleichmaessig ueber Dokumenttypen verteilt aus.

        Args:
            documents: Liste aller Dokumente
            sample_percentage: Optionaler Override fuer Prozentsatz

        Returns:
            Liste der ausgewaehlten Dokumente
        """
        if not documents:
            return []

        config = await self.get_sample_config()
        percentage = sample_percentage or (config.sample_percentage if config else 10)

        if percentage <= 0:
            return []

        if not config or not config.stratify_by_document_type:
            # Einfache Zufallsauswahl
            sample_size = max(1, int(len(documents) * percentage / 100))
            return random.sample(documents, min(sample_size, len(documents)))

        # Stratifizierte Auswahl nach Dokumenttyp
        by_type: Dict[str, List[Document]] = {}
        for doc in documents:
            doc_type = doc.document_type or "unknown"
            if doc_type not in by_type:
                by_type[doc_type] = []
            by_type[doc_type].append(doc)

        selected = []
        for doc_type, type_docs in by_type.items():
            sample_size = max(1, int(len(type_docs) * percentage / 100))
            type_sample = random.sample(type_docs, min(sample_size, len(type_docs)))
            selected.extend(type_sample)

        logger.info(
            "stratified_sampling_applied",
            total_documents=len(documents),
            selected_count=len(selected),
            by_type={k: len(v) for k, v in by_type.items()}
        )

        return selected

    # =========================================================================
    # RULES MANAGEMENT
    # =========================================================================

    async def evaluate_rules(
        self,
        document: Document
    ) -> Optional[ValidationRule]:
        """Evaluiert aktive Regeln gegen ein Dokument.

        Args:
            document: Das zu pruefende Dokument

        Returns:
            Die erste passende Regel oder None
        """
        result = await self.db.execute(
            select(ValidationRule)
            .where(ValidationRule.is_active == True)
            .order_by(ValidationRule.priority.asc())  # Niedrigste Prioritaet zuerst
        )
        rules = result.scalars().all()

        for rule in rules:
            if self._matches_rule(document, rule):
                # Statistik aktualisieren
                rule.documents_matched = (rule.documents_matched or 0) + 1
                rule.last_triggered_at = utc_now()
                await self.db.commit()
                return rule

        return None

    def _matches_rule(self, document: Document, rule: ValidationRule) -> bool:
        """Prueft ob ein Dokument eine Regel erfuellt.

        Args:
            document: Das zu pruefende Dokument
            rule: Die zu pruefende Regel

        Returns:
            True wenn Regel erfuellt
        """
        conditions = rule.conditions or {}

        if rule.rule_type == ValidationRuleType.CONFIDENCE_THRESHOLD.value:
            # Confidence unter Schwellenwert
            threshold = conditions.get("confidence_below", 0.85)
            if document.ocr_confidence is not None:
                return document.ocr_confidence < threshold

            # Min Field Confidence
            min_field_threshold = conditions.get("min_field_confidence_below")
            if min_field_threshold is not None:
                # Muesste aus extracted_data gelesen werden
                # Vereinfachte Implementierung
                return False

        elif rule.rule_type == ValidationRuleType.FIELD_PATTERN.value:
            # Feld fehlt oder ist ungueltig
            required_doc_type = conditions.get("document_type")
            if required_doc_type and document.document_type != required_doc_type:
                return False

            field = conditions.get("field")
            pattern = conditions.get("pattern")

            if field and pattern == "empty_or_invalid":
                extracted = document.extracted_data or {}
                field_value = extracted.get(field)
                return field_value is None or field_value == ""

        elif rule.rule_type == ValidationRuleType.DOCUMENT_TYPE.value:
            # Bestimmter Dokumenttyp immer validieren
            required_types = conditions.get("document_types", [])
            return document.document_type in required_types

        elif rule.rule_type == ValidationRuleType.ERROR_PATTERN.value:
            # Fehler-Pattern erkannt
            error_type = conditions.get("error_type")
            if error_type == "umlaut_error":
                # Umlaut-Fehler in extracted_data pruefen
                extracted = document.extracted_data or {}
                for value in extracted.values():
                    if isinstance(value, str):
                        # Vereinfachte Pruefung: typische Umlaut-Ersetzungen
                        if "ae" in value.lower() or "oe" in value.lower() or "ue" in value.lower():
                            return True

        return False

    async def get_active_rules(self) -> List[ValidationRule]:
        """Holt alle aktiven Regeln.

        Returns:
            Liste der aktiven Regeln
        """
        result = await self.db.execute(
            select(ValidationRule)
            .where(ValidationRule.is_active == True)
            .order_by(ValidationRule.priority.asc())
        )
        return list(result.scalars().all())

    async def get_all_rules(self) -> List[ValidationRule]:
        """Holt alle Regeln.

        Returns:
            Liste aller Regeln
        """
        result = await self.db.execute(
            select(ValidationRule).order_by(ValidationRule.priority.asc())
        )
        return list(result.scalars().all())

    async def get_rule(self, rule_id: uuid.UUID) -> Optional[ValidationRule]:
        """Holt eine einzelne Regel.

        Args:
            rule_id: ID der Regel

        Returns:
            Die Regel oder None
        """
        result = await self.db.execute(
            select(ValidationRule).where(ValidationRule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def create_rule(
        self,
        rule_data: ValidationRuleCreate,
        created_by_id: Optional[uuid.UUID] = None
    ) -> ValidationRule:
        """Erstellt eine neue Regel.

        Args:
            rule_data: Regel-Daten
            created_by_id: ID des Erstellers

        Returns:
            Die erstellte Regel
        """
        rule = ValidationRule(
            name=rule_data.name,
            description=rule_data.description,
            rule_type=rule_data.rule_type.value,
            conditions=rule_data.conditions,
            priority=rule_data.priority,
            is_active=rule_data.is_active,
            is_system=False,
            created_by_id=created_by_id
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            "validation_rule_created",
            rule_id=str(rule.id),
            rule_name=rule.name,
            rule_type=rule.rule_type
        )

        return rule

    async def update_rule(
        self,
        rule_id: uuid.UUID,
        update_data: ValidationRuleUpdate
    ) -> Optional[ValidationRule]:
        """Aktualisiert eine Regel.

        Args:
            rule_id: ID der Regel
            update_data: Zu aktualisierende Felder

        Returns:
            Die aktualisierte Regel oder None
        """
        rule = await self.get_rule(rule_id)
        if not rule:
            return None

        if rule.is_system:
            raise ValueError("System-Regeln koennen nicht bearbeitet werden")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(rule, key, value)

        rule.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            "validation_rule_updated",
            rule_id=str(rule_id),
            updated_fields=list(update_dict.keys())
        )

        return rule

    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        """Loescht eine Regel.

        Args:
            rule_id: ID der Regel

        Returns:
            True wenn geloescht, False wenn nicht gefunden

        Raises:
            ValueError: Wenn System-Regel
        """
        rule = await self.get_rule(rule_id)
        if not rule:
            return False

        if rule.is_system:
            raise ValueError("System-Regeln koennen nicht geloescht werden")

        await self.db.delete(rule)
        await self.db.commit()

        logger.info("validation_rule_deleted", rule_id=str(rule_id))
        return True


def get_validation_sample_service(db: AsyncSession) -> ValidationSampleService:
    """Factory-Funktion fuer den ValidationSampleService.

    Args:
        db: Async-Datenbankverbindung

    Returns:
        ValidationSampleService Instanz
    """
    return ValidationSampleService(db)
