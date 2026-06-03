"""
Unit Tests fuer ValidationSampleService.

Testet Stichproben-Logik: automatisch, regelbasiert und manuell.
Inkl. Prozent-basierte Auswahl und stratifizierte Stichproben.

Hinweis zur Mock-Strategie:
    Die SQLAlchemy-ORM-Modelle (ValidationRule, ValidationSampleConfig, Document)
    koennen in diesem Unit-Test-Kontext nicht instanziiert werden, da die globale
    Mapper-Konfiguration ueber das gesamte models-Registry laeuft und an einer
    projektweiten, hier nicht behebbaren Relationship-Ambiguitaet scheitert
    (folders <-> folder_permissions / OCRCorrectionFeedback). Da der Service die
    Objekte ausschliesslich ueber einfache Attribut-Zugriffe verwendet, werden die
    Test-Objekte als SimpleNamespace gebaut. Alle Werte sind synthetisch.

    Async-DB-Mock-Muster (SQLAlchemy 2.0):
        db.execute = AsyncMock(return_value=mock_result)   # await db.execute(...)
        mock_result.scalar_one_or_none.return_value = obj  # synchron auf dem Result
        mock_result.scalars.return_value.all.return_value = [obj, ...]
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

import app.services.validation_sample_service as svc_module
from app.services.validation_sample_service import ValidationSampleService
from app.db.schemas import (
    ValidationRuleCreate,
    ValidationRuleUpdate,
    ValidationSampleConfigUpdate,
    ValidationRuleTypeEnum,
)


@pytest.fixture
def mock_db():
    """Erstellt einen Mock fuer die Datenbankverbindung."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def validation_sample_service(mock_db):
    """Erstellt eine ValidationSampleService-Instanz mit Mock-DB."""
    return ValidationSampleService(mock_db)


def _make_result(*, scalar=None, scalar_list=None):
    """Baut ein synchrones SQLAlchemy-Result-Mock.

    Args:
        scalar: Rueckgabewert fuer result.scalar_one_or_none()
        scalar_list: Rueckgabe-Liste fuer result.scalars().all()
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = scalar_list or []
    return result


@pytest.fixture
def sample_rule():
    """Erstellt eine Beispiel-Validierungsregel (SimpleNamespace, synthetisch)."""
    return SimpleNamespace(
        id=uuid4(),
        name="Low Confidence Rule",
        description="Trigger bei Konfidenz unter 70%",
        # Service vergleicht rule_type gegen ValidationRuleType.X.value (String)
        rule_type=ValidationRuleTypeEnum.CONFIDENCE_THRESHOLD.value,
        conditions={"confidence_below": 0.7},
        priority=5,
        is_active=True,
        is_system=False,
        documents_matched=0,
        last_triggered_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_config():
    """Erstellt eine Beispiel-Stichproben-Konfiguration (SimpleNamespace)."""
    return SimpleNamespace(
        id=uuid4(),
        sample_percentage=10,
        min_confidence_threshold=0.7,
        stratify_by_document_type=True,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestValidationSampleServiceShouldSample:
    """Tests fuer should_sample_document-Logik."""

    @pytest.mark.asyncio
    async def test_should_sample_low_confidence(self, validation_sample_service, mock_db, sample_config):
        """Test: Dokument mit niedriger Konfidenz wird gesamplet (LOW_CONFIDENCE)."""
        # Regel-Query (leer) zuerst, danach Config-Query
        mock_db.execute.side_effect = [
            _make_result(scalar_list=[]),
            _make_result(scalar=sample_config),
        ]

        document = SimpleNamespace(id=uuid4(), ocr_confidence=0.5)

        should_sample, source, rule_id = await validation_sample_service.should_sample_document(document)

        # ocr_confidence 0.5 < min_confidence_threshold 0.7 -> LOW_CONFIDENCE
        assert should_sample is True
        assert source == "low_confidence"
        assert rule_id is None

    @pytest.mark.asyncio
    async def test_should_sample_high_confidence(self, validation_sample_service, mock_db, sample_config):
        """Test: Dokument mit hoher Konfidenz wird nicht ueber Konfidenz gesamplet."""
        # sample_percentage 0 -> keine Zufallsauswahl, deterministisch False
        sample_config.sample_percentage = 0
        mock_db.execute.side_effect = [
            _make_result(scalar_list=[]),
            _make_result(scalar=sample_config),
        ]

        document = SimpleNamespace(id=uuid4(), ocr_confidence=0.95)

        should_sample, source, rule_id = await validation_sample_service.should_sample_document(document)

        # Hohe Konfidenz + 0% Sample -> nicht ausgewaehlt
        assert should_sample is False
        assert source is None
        assert rule_id is None

    @pytest.mark.asyncio
    async def test_should_sample_respects_percentage(self, validation_sample_service, mock_db, sample_config):
        """Test: Bei 100% Stichprobe wird auch hohe Konfidenz immer gesamplet."""
        sample_config.sample_percentage = 100  # 100% = alle samplen
        sample_config.min_confidence_threshold = 0.0  # Konfidenz-Pfad ausschliessen
        mock_db.execute.side_effect = [
            _make_result(scalar_list=[]),
            _make_result(scalar=sample_config),
        ]

        document = SimpleNamespace(id=uuid4(), ocr_confidence=0.9)

        should_sample, source, rule_id = await validation_sample_service.should_sample_document(document)

        # Bei 100% wird jeder Roll (1..100) ausgewaehlt -> AUTOMATIC
        assert should_sample is True
        assert source == "automatic"

    @pytest.mark.asyncio
    async def test_should_sample_rule_match(self, validation_sample_service, mock_db, sample_rule):
        """Test: Eine passende Regel fuehrt zu RULE_BASED-Auswahl."""
        # CONFIDENCE_THRESHOLD-Regel matcht bei Konfidenz unter Schwellenwert
        sample_rule.conditions = {"confidence_below": 0.85}
        # evaluate_rules: Regeln laden -> commit nach Match
        mock_db.execute.return_value = _make_result(scalar_list=[sample_rule])

        document = SimpleNamespace(id=uuid4(), ocr_confidence=0.5)

        should_sample, source, rule_id = await validation_sample_service.should_sample_document(document)

        assert should_sample is True
        assert source == "rule_based"
        assert rule_id == sample_rule.id
        assert mock_db.commit.called


class TestValidationSampleServiceRules:
    """Tests fuer Regel-Management."""

    @pytest.mark.asyncio
    async def test_get_active_rules(self, validation_sample_service, mock_db, sample_rule):
        """Test: Aktive Regeln abrufen."""
        mock_db.execute.return_value = _make_result(scalar_list=[sample_rule])

        result = await validation_sample_service.get_active_rules()

        assert isinstance(result, list)
        assert result == [sample_rule]

    @pytest.mark.asyncio
    async def test_create_rule(self, validation_sample_service, mock_db):
        """Test: Neue Regel erstellen (ueber ValidationRuleCreate-Schema)."""
        # Der Service nimmt ein Schema-Objekt, nicht einzelne kwargs.
        # ValidationRule(...) wuerde die ORM-Mapper-Konfiguration triggern, daher
        # wird der ORM-Konstruktor durch einen SimpleNamespace ersetzt.
        rule_data = ValidationRuleCreate(
            name="Test Rule",
            rule_type=ValidationRuleTypeEnum.CONFIDENCE_THRESHOLD,
            conditions={"confidence_below": 0.5},
            priority=5,
        )

        created_id = uuid4()

        def _fake_rule(**kwargs):
            return SimpleNamespace(id=created_id, **kwargs)

        with patch.object(svc_module, "ValidationRule", side_effect=_fake_rule):
            result = await validation_sample_service.create_rule(rule_data)

        assert mock_db.add.called
        assert mock_db.commit.called
        assert result.name == "Test Rule"
        assert result.rule_type == ValidationRuleTypeEnum.CONFIDENCE_THRESHOLD.value

    @pytest.mark.asyncio
    async def test_update_rule(self, validation_sample_service, mock_db, sample_rule):
        """Test: Regel aktualisieren (ueber ValidationRuleUpdate-Schema)."""
        # update_rule ruft intern get_rule() -> db.execute().scalar_one_or_none()
        mock_db.execute.return_value = _make_result(scalar=sample_rule)

        update_data = ValidationRuleUpdate(name="Updated Rule Name", priority=8)

        result = await validation_sample_service.update_rule(
            rule_id=sample_rule.id,
            update_data=update_data,
        )

        assert mock_db.commit.called
        assert result is sample_rule
        assert sample_rule.name == "Updated Rule Name"
        assert sample_rule.priority == 8

    @pytest.mark.asyncio
    async def test_delete_rule(self, validation_sample_service, mock_db, sample_rule):
        """Test: Regel loeschen."""
        sample_rule.is_system = False
        # delete_rule ruft intern get_rule() -> scalar_one_or_none()
        mock_db.execute.return_value = _make_result(scalar=sample_rule)

        deleted = await validation_sample_service.delete_rule(sample_rule.id)

        assert deleted is True
        assert mock_db.delete.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_delete_system_rule_fails(self, validation_sample_service, mock_db, sample_rule):
        """Test: System-Regel kann nicht geloescht werden."""
        sample_rule.is_system = True
        mock_db.execute.return_value = _make_result(scalar=sample_rule)

        with pytest.raises(ValueError, match="System"):
            await validation_sample_service.delete_rule(sample_rule.id)


class TestValidationSampleServiceRuleEvaluation:
    """Tests fuer Regel-Auswertung."""

    @pytest.mark.asyncio
    async def test_evaluate_confidence_threshold_rule(self, validation_sample_service, mock_db, sample_rule):
        """Test: Konfidenz-Schwellenwert-Regel auswerten."""
        sample_rule.rule_type = ValidationRuleTypeEnum.CONFIDENCE_THRESHOLD.value
        sample_rule.conditions = {"confidence_below": 0.7}
        mock_db.execute.return_value = _make_result(scalar_list=[sample_rule])

        # Dokument mit niedriger Konfidenz
        document = SimpleNamespace(
            id=uuid4(), ocr_confidence=0.5, document_type="invoice"
        )

        result = await validation_sample_service.evaluate_rules(document)

        # 0.5 < 0.7 -> Regel matcht
        assert result is sample_rule
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_evaluate_document_type_rule(self, validation_sample_service, mock_db, sample_rule):
        """Test: Dokumenttyp-Regel auswerten."""
        sample_rule.rule_type = ValidationRuleTypeEnum.DOCUMENT_TYPE.value
        sample_rule.conditions = {"document_types": ["invoice", "order"]}
        mock_db.execute.return_value = _make_result(scalar_list=[sample_rule])

        document = SimpleNamespace(
            id=uuid4(), ocr_confidence=0.99, document_type="invoice"
        )

        result = await validation_sample_service.evaluate_rules(document)

        # document_type 'invoice' in Liste -> Regel matcht
        assert result is sample_rule

    @pytest.mark.asyncio
    async def test_evaluate_field_pattern_rule(self, validation_sample_service, mock_db, sample_rule):
        """Test: Feld-Muster-Regel auswerten (Feld leer/ungueltig)."""
        sample_rule.rule_type = ValidationRuleTypeEnum.FIELD_PATTERN.value
        # Service-Logik: pattern == 'empty_or_invalid' bei passendem document_type
        sample_rule.conditions = {
            "document_type": "invoice",
            "field": "invoice_number",
            "pattern": "empty_or_invalid",
        }
        mock_db.execute.return_value = _make_result(scalar_list=[sample_rule])

        document = SimpleNamespace(
            id=uuid4(),
            ocr_confidence=0.99,
            document_type="invoice",
            extracted_data={"invoice_number": ""},  # leeres Pflichtfeld
        )

        result = await validation_sample_service.evaluate_rules(document)

        # Leeres Feld -> Regel matcht
        assert result is sample_rule


class TestValidationSampleServiceConfig:
    """Tests fuer Stichproben-Konfiguration."""

    @pytest.mark.asyncio
    async def test_get_sample_config(self, validation_sample_service, mock_db, sample_config):
        """Test: Aktive Konfiguration abrufen."""
        mock_db.execute.return_value = _make_result(scalar=sample_config)

        result = await validation_sample_service.get_sample_config()

        assert result is sample_config

    @pytest.mark.asyncio
    async def test_update_sample_config(self, validation_sample_service, mock_db, sample_config):
        """Test: Konfiguration aktualisieren (ueber ValidationSampleConfigUpdate)."""
        mock_db.execute.return_value = _make_result(scalar=sample_config)

        update_data = ValidationSampleConfigUpdate(
            sample_percentage=25,
            min_confidence_threshold=0.8,
        )

        result = await validation_sample_service.update_sample_config(
            config_id=sample_config.id,
            update_data=update_data,
        )

        assert mock_db.commit.called
        assert result is sample_config
        assert sample_config.sample_percentage == 25
        assert sample_config.min_confidence_threshold == 0.8

    @pytest.mark.asyncio
    async def test_sample_percentage_bounds(self, validation_sample_service, mock_db, sample_config):
        """Test: Stichproben-Prozentsatz wird auf 0-100 begrenzt (Schema-Validierung).

        Die Wertebereichs-Pruefung liegt im ValidationSampleConfigUpdate-Schema
        (Field ge=0, le=100), nicht im Service. Ein ungueltiger Wert fuehrt daher
        bereits beim Erzeugen des Update-Schemas zu einer ValidationError
        (Subklasse von ValueError).
        """
        with pytest.raises(ValueError):
            ValidationSampleConfigUpdate(sample_percentage=150)  # Ungueltig!


class TestValidationSampleServiceStratifiedSampling:
    """Tests fuer stratifizierte Stichprobenauswahl."""

    @pytest.mark.asyncio
    async def test_apply_stratified_sampling(self, validation_sample_service, mock_db, sample_config):
        """Test: Stratifizierte Stichprobenauswahl anwenden."""
        sample_config.stratify_by_document_type = True
        sample_config.sample_percentage = 100  # alles auswaehlen -> deterministisch
        mock_db.execute.return_value = _make_result(scalar=sample_config)

        # Dokumente verschiedener Typen
        documents = [
            SimpleNamespace(document_type="invoice", id=uuid4()),
            SimpleNamespace(document_type="invoice", id=uuid4()),
            SimpleNamespace(document_type="order", id=uuid4()),
            SimpleNamespace(document_type="contract", id=uuid4()),
        ]

        result = await validation_sample_service.apply_stratified_sampling(documents)

        assert isinstance(result, list)
        # Bei 100% werden alle Dokumente jeder Strate ausgewaehlt
        assert len(result) == len(documents)

    @pytest.mark.asyncio
    async def test_stratified_sampling_balances_types(self, validation_sample_service, mock_db, sample_config):
        """Test: Stratifizierung beruecksichtigt jeden Dokumenttyp (min. 1)."""
        sample_config.stratify_by_document_type = True
        sample_config.sample_percentage = 50
        mock_db.execute.return_value = _make_result(scalar=sample_config)

        # Unbalancierte Dokumente: 10 invoice, 1 order
        documents = [
            *[SimpleNamespace(document_type="invoice", id=uuid4()) for _ in range(10)],
            SimpleNamespace(document_type="order", id=uuid4()),
        ]

        result = await validation_sample_service.apply_stratified_sampling(documents)

        assert isinstance(result, list)
        result_types = {d.document_type for d in result}
        # Jeder Typ wird repraesentiert (max(1, ...) garantiert min. 1 order)
        assert "invoice" in result_types
        assert "order" in result_types
        # 50% von 10 invoice = 5, plus min. 1 order
        assert len([d for d in result if d.document_type == "invoice"]) == 5
        assert len([d for d in result if d.document_type == "order"]) == 1


class TestValidationSampleServiceEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_no_active_rules(self, validation_sample_service, mock_db):
        """Test: Keine aktiven Regeln vorhanden."""
        mock_db.execute.return_value = _make_result(scalar_list=[])

        document = SimpleNamespace(
            id=uuid4(), ocr_confidence=0.9, document_type="invoice", extracted_data={}
        )

        result = await validation_sample_service.evaluate_rules(document)

        # Keine Regel matcht -> None
        assert result is None

    @pytest.mark.asyncio
    async def test_no_config(self, validation_sample_service, mock_db):
        """Test: Keine Konfiguration vorhanden."""
        mock_db.execute.return_value = _make_result(scalar=None)

        result = await validation_sample_service.get_sample_config()

        # Keine aktive Konfiguration -> None
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_document_list(self, validation_sample_service, mock_db, sample_config):
        """Test: Leere Dokumentliste fuer Stratifizierung."""
        mock_db.execute.return_value = _make_result(scalar=sample_config)

        result = await validation_sample_service.apply_stratified_sampling([])

        assert result == []
