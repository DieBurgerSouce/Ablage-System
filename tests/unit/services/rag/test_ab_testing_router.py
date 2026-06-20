"""Unit Tests fuer ABTestingRouter.

Testet den A/B Testing Traffic-Router fuer Vector Search.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import hashlib

# Pre-import um Modul zu laden (wichtig fuer patch-Pfad)
import app.services.rag.ab_testing_router  # noqa: F401


# Mock settings vor dem Import
@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings fuer alle Tests."""
    with patch('app.services.rag.ab_testing_router.settings') as mock:
        mock.VECTOR_AB_TESTING_ENABLED = True
        mock.VECTOR_AB_TRAFFIC_SPLIT = 10  # 10% Treatment
        mock.VECTOR_AB_CONTROL_BACKEND = "pgvector"
        mock.VECTOR_AB_TREATMENT_BACKEND = "qdrant"
        mock.VECTOR_AB_CONTROL_EMBEDDING = "intfloat/multilingual-e5-large"
        mock.VECTOR_AB_TREATMENT_EMBEDDING = "jinaai/jina-embeddings-v2-base-de"
        mock.VECTOR_AB_METRICS_ENABLED = True
        yield mock


@pytest.fixture
def reset_singleton():
    """Reset ABTestingRouter Singleton zwischen Tests."""
    from app.services.rag.ab_testing_router import ABTestingRouter

    # Reset vor dem Test
    ABTestingRouter._instance = None

    yield

    # Cleanup nach dem Test
    ABTestingRouter._instance = None


class TestABTestingRouterInit:
    """Tests fuer ABTestingRouter Initialisierung."""

    def test_singleton_pattern(self, mock_settings, reset_singleton):
        """Test dass ABTestingRouter Singleton ist."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router1 = ABTestingRouter()
        router2 = ABTestingRouter()

        assert router1 is router2

    def test_initialization_with_settings(self, mock_settings, reset_singleton):
        """Test Initialisierung liest Settings korrekt."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        assert router._enabled is True
        assert router._traffic_split == 10

    def test_get_ab_testing_router_returns_singleton(self, mock_settings, reset_singleton):
        """Test dass get_ab_testing_router() Singleton zurueckgibt."""
        from app.services.rag.ab_testing_router import get_ab_testing_router

        router1 = get_ab_testing_router()
        router2 = get_ab_testing_router()

        assert router1 is router2


class TestABTestingRouterAssignment:
    """Tests fuer A/B Test Zuordnung."""

    def test_disabled_returns_control(self, mock_settings, reset_singleton):
        """Test dass deaktiviertes A/B Testing Control zurueckgibt."""
        mock_settings.VECTOR_AB_TESTING_ENABLED = False

        from app.services.rag.ab_testing_router import ABTestingRouter, ExperimentVariant

        router = ABTestingRouter()
        assignment = router.get_assignment(user_id="user123")

        assert assignment.variant == ExperimentVariant.CONTROL
        assert assignment.assignment_reason == "ab_testing_disabled"

    def test_forced_treatment(self, mock_settings, reset_singleton):
        """Test erzwungene Treatment-Zuordnung."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(
            user_id="user123",
            force_variant=ExperimentVariant.TREATMENT
        )

        assert assignment.variant == ExperimentVariant.TREATMENT
        assert assignment.assignment_reason == "forced_treatment"

    def test_forced_control(self, mock_settings, reset_singleton):
        """Test erzwungene Control-Zuordnung."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(
            user_id="user123",
            force_variant=ExperimentVariant.CONTROL
        )

        assert assignment.variant == ExperimentVariant.CONTROL
        assert assignment.assignment_reason == "forced_control"

    def test_consistent_user_assignment(self, mock_settings, reset_singleton):
        """Test dass gleicher User immer gleiche Zuordnung bekommt."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        # Gleicher User sollte immer gleiche Zuordnung bekommen
        assignment1 = router.get_assignment(user_id="consistent-user")
        assignment2 = router.get_assignment(user_id="consistent-user")
        assignment3 = router.get_assignment(user_id="consistent-user")

        assert assignment1.variant == assignment2.variant == assignment3.variant
        assert assignment1.bucket_id == assignment2.bucket_id == assignment3.bucket_id

    def test_different_users_different_buckets(self, mock_settings, reset_singleton):
        """Test dass verschiedene User verschiedene Buckets haben koennen."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        # Sammle Buckets von vielen verschiedenen Usern
        buckets = set()
        for i in range(100):
            assignment = router.get_assignment(user_id=f"user-{i}")
            buckets.add(assignment.bucket_id)

        # Sollte verschiedene Buckets geben (nicht alle gleich)
        assert len(buckets) > 1

    def test_traffic_split_distribution(self, mock_settings, reset_singleton):
        """Test dass Traffic-Split ungefaehr eingehalten wird."""
        mock_settings.VECTOR_AB_TRAFFIC_SPLIT = 50  # 50% Treatment

        from app.services.rag.ab_testing_router import ABTestingRouter, ExperimentVariant

        router = ABTestingRouter()

        treatment_count = 0
        total = 1000

        for i in range(total):
            assignment = router.get_assignment(user_id=f"distribution-test-user-{i}")
            if assignment.variant == ExperimentVariant.TREATMENT:
                treatment_count += 1

        # Bei 50% Split sollte ca. 40-60% Treatment sein (Toleranz fuer Hashing)
        ratio = treatment_count / total
        assert 0.35 < ratio < 0.65, f"Treatment ratio {ratio} outside expected range"

    def test_session_based_assignment(self, mock_settings, reset_singleton):
        """Test Session-basierte Zuordnung."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        assignment = router.get_assignment(session_id="session-123")

        assert "session_bucket" in assignment.assignment_reason

    def test_document_based_assignment(self, mock_settings, reset_singleton):
        """Test Dokument-basierte Zuordnung."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        assignment = router.get_assignment(document_id="doc-456")

        assert "document_bucket" in assignment.assignment_reason

    def test_random_assignment_without_identifier(self, mock_settings, reset_singleton):
        """Test Random-Zuordnung ohne Identifier (timestamp-basierter Bucket)."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        assignment = router.get_assignment()

        # Ohne Identifier nutzt der Router einen deterministischen
        # Timestamp-Bucket fuer anonyme Anfragen.
        assert "timestamp_bucket" in assignment.assignment_reason
        assert assignment.assignment_reason.endswith(("control", "treatment"))


class TestABTestingRouterBackendSelection:
    """Tests fuer Backend-Auswahl."""

    def test_control_uses_pgvector(self, mock_settings, reset_singleton):
        """Test dass Control pgvector verwendet."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant, VectorBackend
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        assert assignment.backend == VectorBackend.PGVECTOR

    def test_treatment_uses_qdrant(self, mock_settings, reset_singleton):
        """Test dass Treatment Qdrant verwendet."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant, VectorBackend
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.TREATMENT)

        assert assignment.backend == VectorBackend.QDRANT


class TestABTestingRouterEmbeddingModel:
    """Tests fuer Embedding-Modell-Auswahl."""

    def test_control_uses_e5(self, mock_settings, reset_singleton):
        """Test dass Control E5-Modell verwendet."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )
        from app.services.embedding_service import EmbeddingModelType

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        assert assignment.embedding_model == EmbeddingModelType.E5_MULTILINGUAL

    def test_treatment_uses_jina(self, mock_settings, reset_singleton):
        """Test dass Treatment Jina-Modell verwendet."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )
        from app.services.embedding_service import EmbeddingModelType

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.TREATMENT)

        assert assignment.embedding_model == EmbeddingModelType.JINA_GERMAN


class TestABTestingRouterMetrics:
    """Tests fuer Metriken-Aufzeichnung."""

    def test_record_result(self, mock_settings, reset_singleton):
        """Test Ergebnis-Aufzeichnung."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        # Ergebnis aufzeichnen
        router.record_result(
            assignment=assignment,
            query_time_ms=50.0,
            result_count=10,
            avg_score=0.85
        )

        metrics = router.get_metrics()

        assert metrics["control"]["total_requests"] == 1
        assert metrics["control"]["avg_latency_ms"] == 50.0

    def test_metrics_accumulate(self, mock_settings, reset_singleton):
        """Test dass Metriken akkumulieren."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        # Mehrere Ergebnisse aufzeichnen
        for i in range(5):
            router.record_result(
                assignment=assignment,
                query_time_ms=100.0,
                result_count=10,
                avg_score=0.8
            )

        metrics = router.get_metrics()

        assert metrics["control"]["total_requests"] == 5
        assert metrics["control"]["avg_latency_ms"] == 100.0

    def test_reset_metrics(self, mock_settings, reset_singleton):
        """Test Metriken-Reset."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        router.record_result(
            assignment=assignment,
            query_time_ms=50.0,
            result_count=10,
            avg_score=0.85
        )

        router.reset_metrics()
        metrics = router.get_metrics()

        assert metrics["control"]["total_requests"] == 0

    def test_disabled_metrics(self, mock_settings, reset_singleton):
        """Test dass deaktivierte Metriken nicht aufzeichnen."""
        mock_settings.VECTOR_AB_METRICS_ENABLED = False

        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        router.record_result(
            assignment=assignment,
            query_time_ms=50.0,
            result_count=10,
            avg_score=0.85
        )

        # Metriken sollten leer sein
        metrics = router.get_metrics()
        assert metrics["control"]["total_requests"] == 0


class TestABTestingRouterTrafficSplit:
    """Tests fuer Traffic-Split Management."""

    def test_update_traffic_split(self, mock_settings, reset_singleton):
        """Test Traffic-Split Update."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()
        initial_split = router._traffic_split

        router.update_traffic_split(50)

        assert router._traffic_split == 50
        assert router._traffic_split != initial_split

    def test_update_traffic_split_validates_range(self, mock_settings, reset_singleton):
        """Test dass Traffic-Split-Range validiert wird."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        with pytest.raises(ValueError):
            router.update_traffic_split(-1)

        with pytest.raises(ValueError):
            router.update_traffic_split(101)


class TestABTestingRouterStatus:
    """Tests fuer Status-Abruf."""

    def test_get_status(self, mock_settings, reset_singleton):
        """Test Status-Abruf."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()
        status = router.get_status()

        assert "enabled" in status
        assert "traffic_split" in status
        assert "control" in status
        assert "treatment" in status
        assert "metrics" in status

    def test_status_reflects_config(self, mock_settings, reset_singleton):
        """Test dass Status Config widerspiegelt."""
        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()
        status = router.get_status()

        assert status["enabled"] is True
        assert status["traffic_split"] == 10
        assert status["control"]["backend"] == "pgvector"
        assert status["treatment"]["backend"] == "qdrant"


class TestABTestingRouterIsHelper:
    """Tests fuer is_treatment() Hilfsfunktion."""

    def test_is_treatment_for_treatment_user(self, mock_settings, reset_singleton):
        """Test is_treatment() fuer Treatment-User."""
        # Traffic auf 100% setzen
        mock_settings.VECTOR_AB_TRAFFIC_SPLIT = 100

        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        # Bei 100% sollten alle Treatment sein
        assert router.is_treatment(user_id="any-user") is True

    def test_is_treatment_for_control_user(self, mock_settings, reset_singleton):
        """Test is_treatment() fuer Control-User."""
        # Traffic auf 0% setzen
        mock_settings.VECTOR_AB_TRAFFIC_SPLIT = 0

        from app.services.rag.ab_testing_router import ABTestingRouter

        router = ABTestingRouter()

        # Bei 0% sollten alle Control sein
        assert router.is_treatment(user_id="any-user") is False


class TestABTestContext:
    """Tests fuer ABTestContext Context Manager."""

    def test_context_records_timing(self, mock_settings, reset_singleton):
        """Test dass Context-Manager Timing aufzeichnet."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ABTestContext, ExperimentVariant
        )
        import time

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        with ABTestContext(router, assignment) as ctx:
            time.sleep(0.01)  # 10ms
            ctx.set_results(result_count=5, avg_score=0.9)

        metrics = router.get_metrics()

        assert metrics["control"]["total_requests"] == 1
        assert metrics["control"]["avg_latency_ms"] >= 10  # Mindestens 10ms

    def test_context_records_error(self, mock_settings, reset_singleton):
        """Test dass Context-Manager Fehler aufzeichnet."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ABTestContext, ExperimentVariant
        )

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.CONTROL)

        with pytest.raises(ValueError):
            with ABTestContext(router, assignment):
                raise ValueError("Test error")

        metrics = router.get_metrics()

        assert metrics["control"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_async_context(self, mock_settings, reset_singleton):
        """Test async Context-Manager."""
        from app.services.rag.ab_testing_router import (
            ABTestingRouter, ABTestContext, ExperimentVariant
        )
        import asyncio

        router = ABTestingRouter()
        assignment = router.get_assignment(force_variant=ExperimentVariant.TREATMENT)

        async with ABTestContext(router, assignment) as ctx:
            await asyncio.sleep(0.01)
            ctx.set_results(result_count=3, avg_score=0.75)

        metrics = router.get_metrics()

        assert metrics["treatment"]["total_requests"] == 1
